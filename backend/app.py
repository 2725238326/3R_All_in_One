from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
import zipfile
from collections import Counter
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from advisor import (
    advisor_config_public,
    advisor_diagnostics,
    advisor_provider_options,
    advisor_status,
    evaluate_job_with_advisor,
    recommend_parameters,
    diagnose_failure,
    batch_evaluate_jobs,
    load_advisor_report,
    save_advisor_config,
    test_advisor_connection,
)
from experiment_orchestrator import (
    create_experiment_template,
    delete_experiment_template,
    generate_param_combinations,
    get_experiment_run,
    get_experiment_template,
    get_experiment_run_summary,
    list_experiment_runs,
    list_experiment_templates,
    run_experiment_from_template,
    update_experiment_template,
)
from experiment_record import build_experiment_record, build_experiment_record_bundle
from scene_meta import normalize_scene_meta
from development_store import DevelopmentItem, DevelopmentStore, DevelopmentStoreError, item_priority_score
from job_store import (
    EVALUATION_SCORE_FIELDS,
    EVALUATION_SCORE_MAX,
    EVALUATION_SCORE_MIN,
    ROOT,
    clear_job_runtime,
    create_job,
    duplicate_job,
    get_job_dir,
    get_log_snippets,
    iter_input_items,
    list_all_jobs,
    list_jobs,
    load_evaluation,
    load_result_summary,
    load_job,
    query_jobs,
    recover_orphan_running_jobs,
    register_job_update_listener,
    save_inputs,
    save_evaluation,
    update_job,
)
from model_contracts import (
    all_model_contracts,
    artifact_index_for,
    artifact_record_for,
    build_job_params as build_contract_job_params,
    check_output_contract,
    minimum_input_count,
    model_contract_for,
    validate_create_request,
)
from model_registry import (
    MODEL_OPTIONS,
    SOURCE_TYPE_OPTIONS,
    draft_local_model_entry,
    get_model_catalog_options,
    get_model_spec,
)
from ssh_runner import ServerConfig, cancel_remote_job, run_remote_job
from viser_manager import manager as viser_manager
from storage_config import load_config, save_config, StorageConfig
from storage_manager import get_storage_stats, evaluate_cleanup_rules, execute_cleanup, auto_clean_if_needed, start_auto_clean, stop_auto_clean, list_trash_items, restore_from_trash, empty_trash
from logging_config import setup_logging, log, JobLogger
from runtime_paths import backend_root, bundle_root, data_root, model_specs_dir
from job_scheduler import JobPriority, scheduler
from resource_monitor import monitor as resource_monitor
from metrics_calculator import compute_job_metrics
from report_exporter import build_job_report, build_compare_report, export_html, export_pdf
from visual_artifacts import generate_job_visuals, generate_compare_visuals

_RUNNER_THREADS: dict[str, threading.Thread] = {}
_RUNNER_THREADS_LOCK = threading.Lock()
_SAMPLES_CACHE_LOCK = threading.RLock()
_SAMPLES_CACHE: tuple[int | None, dict] | None = None
_DEPLOYMENT_STATUS_CACHE_LOCK = threading.Condition(threading.RLock())
_DEPLOYMENT_STATUS_CACHE: dict | None = None
_DEPLOYMENT_STATUS_REFRESHING = False
_AGENT_BUILD_TASKS: dict[str, dict] = {}
_AGENT_BUILD_TASKS_LOCK = threading.Lock()
# Async smoke / health / doctor / batch-smoke tasks. Same lifecycle shape as the
# build tasks above (queued -> running -> finished/failed) so the frontend can
# poll a single status endpoint regardless of which agent check was launched.
_AGENT_CHECK_TASKS: dict[str, dict] = {}
_AGENT_CHECK_TASKS_LOCK = threading.Lock()
_AGENT_CHECK_TASKS_MAX = 200
DEPLOYMENT_STATUS_TTL_SECONDS = 20.0
DEPLOYMENT_STATUS_STALE_SECONDS = 300.0
DEPLOYMENT_STATUS_TIMEOUT_SECONDS = 15.0
LOGGER = logging.getLogger("kykt.development")
development_store = DevelopmentStore()
WS_ALL_JOBS_KEY = "__all__"


async def _recover_orphan_running_jobs() -> None:
    """Mark in-flight jobs from a previous process as failed on startup."""
    try:
        manager.bind_loop()
        rehydrated = recover_orphan_running_jobs()
    except Exception as exc:  # pragma: no cover - defensive
        LOGGER.warning("Orphan job rehydration failed: %s", exc)
        return
    if rehydrated:
        LOGGER.info(
            "Rehydrated %d orphan running job(s) on startup: %s",
            len(rehydrated),
            ", ".join(rehydrated),
        )


async def startup_event() -> None:
    setup_logging(level="INFO", console=True, file=True)
    log.info("Backend starting up...")

    await _recover_orphan_running_jobs()
    resource_monitor.start()

    def dispatch_fn(job_id: str):
        _prepare_job_for_dispatch(job_id, "由调度器自动派发")

    def status_fn(job_id: str) -> str:
        try:
            job = load_job(job_id)
            return job.status
        except FileNotFoundError:
            return "unknown"

    scheduler.configure(dispatch_fn, status_fn)
    scheduler.start()
    start_auto_clean()


async def shutdown_event() -> None:
    scheduler.stop()
    resource_monitor.stop()
    stop_auto_clean()


@asynccontextmanager
async def _app_lifespan(_: FastAPI):
    await startup_event()
    try:
        yield
    finally:
        await shutdown_event()


app = FastAPI(
    title="3R All-in-One API",
    description="MonST3R 应用程序后端 API - 支持 DUSt3R、MASt3R、MonST3R、Spann3R、Fast3R、Align3R、CUT3R 等三维重建模型",
    version="0.5.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=_app_lifespan,
    openapi_tags=[
        {
            "name": "系统状态",
            "description": "系统健康检查和状态查询"
        },
        {
            "name": "任务管理",
            "description": "任务的创建、查询、更新和删除"
        },
        {
            "name": "批量操作",
            "description": "批量任务操作（派发、取消、删除等）"
        },
        {
            "name": "模型管理",
            "description": "模型目录、契约和参数管理"
        },
        {
            "name": "AI 顾问",
            "description": "AI 辅助评估、参数推荐和故障诊断"
        },
        {
            "name": "存储管理",
            "description": "存储配额、清理规则和回收站管理"
        },
        {
            "name": "实验编排",
            "description": "实验模板、参数网格搜索和自动化流程"
        },
        {
            "name": "数据面板",
            "description": "样本数据、开发车道和对比分析"
        },
    ]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
        "http://127.0.0.1:1420",
        "http://localhost:1420",
        "http://tauri.localhost",
        "tauri://localhost",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self) -> None:
        self._loop = asyncio.get_running_loop()

    async def connect(self, job_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.setdefault(job_id, []).append(websocket)

    async def disconnect(self, job_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self.active_connections.get(job_id)
            if not connections:
                return
            if websocket in connections:
                connections.remove(websocket)
            if not connections:
                self.active_connections.pop(job_id, None)

    async def broadcast(self, job_id: str, message: dict) -> None:
        keys = {job_id, WS_ALL_JOBS_KEY}
        async with self._lock:
            targets = [
                (key, websocket)
                for key in keys
                for websocket in self.active_connections.get(key, [])
            ]

        stale: list[tuple[str, WebSocket]] = []
        for key, websocket in targets:
            try:
                await websocket.send_json(message)
            except Exception:
                stale.append((key, websocket))

        if stale:
            async with self._lock:
                for key, websocket in stale:
                    connections = self.active_connections.get(key)
                    if not connections:
                        continue
                    if websocket in connections:
                        connections.remove(websocket)
                    if not connections:
                        self.active_connections.pop(key, None)

    def broadcast_from_thread(self, job_id: str, message: dict) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self.broadcast(job_id, message), loop)


manager = ConnectionManager()


class BatchJobsRequest(BaseModel):
    job_ids: list[str] = Field(..., min_length=1)
    options: dict[str, object] = Field(default_factory=dict)


def _normalize_batch_job_ids(job_ids: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_job_id in job_ids:
        job_id = str(raw_job_id).strip()
        if not job_id or job_id in seen:
            continue
        seen.add(job_id)
        normalized.append(job_id)
    if not normalized:
        raise HTTPException(status_code=400, detail="job_ids 不能为空。")
    return normalized


def _ensure_agent_import_path() -> None:
    """Allow backend/app.py to import the root-level agent package from backend cwd."""
    import sys

    root = str(bundle_root())
    if root not in sys.path:
        sys.path.insert(0, root)


def _agent_modules():
    _ensure_agent_import_path()
    from agent.env_builder import EnvBuilder, SSHConfig
    from agent.registry import ModelRegistry
    from agent.schema_validator import SchemaValidator

    return EnvBuilder, ModelRegistry, SchemaValidator, SSHConfig


def _agent_registry():
    _, ModelRegistry, _, _ = _agent_modules()
    specs_dir = model_specs_dir()
    registry = ModelRegistry(specs_dir=specs_dir)
    if Path(registry.specs_dir).resolve() != specs_dir.resolve():
        ModelRegistry._instance = None
        registry = ModelRegistry(specs_dir=specs_dir)
    return registry


def _agent_issue_to_dict(issue) -> dict:
    return {
        "level": issue.level,
        "field": issue.field,
        "message": issue.message,
        "suggestion": issue.suggestion,
    }


def _agent_validation_to_dict(result) -> dict:
    return {
        "model": result.model,
        "path": result.path,
        "valid": result.valid,
        "errors": [_agent_issue_to_dict(issue) for issue in result.errors],
        "warnings": [_agent_issue_to_dict(issue) for issue in result.warnings],
        "issues": [_agent_issue_to_dict(issue) for issue in result.issues],
        "errorCount": len(result.errors),
        "warningCount": len(result.warnings),
    }


def _agent_spec_to_dict(spec) -> dict:
    unresolved = spec.unresolved_issues
    return {
        **spec.summary(),
        "family": spec.family,
        "version": spec.version,
        "paper": spec.paper,
        "tags": spec.tags,
        "repo": {
            "url": spec.repo.get("url"),
            "branch": spec.repo.get("branch"),
            "server_path": spec.server_path,
            "submodules": spec.repo.get("submodules", []),
        },
        "environment": {
            "conda_env": spec.conda_env,
            "python": spec.environment.get("python"),
            "torch": spec.environment.get("torch"),
            "cuda_toolkit": spec.environment.get("cuda_toolkit"),
            "cuda_arch": spec.environment.get("cuda_arch"),
            "create_strategy": spec.environment.get("create_strategy", "fresh"),
            "clone_source": spec.environment.get("clone_source"),
        },
        "checkpoints": spec.checkpoints,
        "resources": spec.resources,
        "health_checks": spec.health_checks,
        "smoke_test": spec.smoke_test,
        "runner": spec.runner,
        "output_contract": spec.output_contract,
        "known_issues": spec.known_issues,
        "unresolved_issue_items": unresolved,
        "compatibility": spec.compatibility,
        "priority": spec.priority,
        "last_verified": spec.last_verified,
        "param_tiers": {
            tier: spec.get_param_tier(tier)
            for tier in ("fast", "standard", "enhanced")
        },
    }


def _agent_build_step_to_dict(step) -> dict:
    return {
        "model": step.model,
        "step": step.step,
        "success": step.success,
        "output": step.output,
        "error": step.error,
        "duration_sec": round(float(step.duration_sec), 3),
    }


def _agent_environment_report_to_dict(report) -> dict:
    return {
        "model": report.model,
        "success": report.success,
        "smoke_passed": report.smoke_passed,
        "total_duration_sec": round(float(report.total_duration_sec), 3),
        "steps": [_agent_build_step_to_dict(step) for step in report.steps],
    }


def _agent_build_task_update(task_id: str, **updates: object) -> None:
    with _AGENT_BUILD_TASKS_LOCK:
        record = dict(_AGENT_BUILD_TASKS.get(task_id, {}))
        record.update(updates)
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        _AGENT_BUILD_TASKS[task_id] = record


def _agent_check_modules() -> dict:
    """Lazily import the agent smoke/health/doctor helpers (root-level package)."""
    _ensure_agent_import_path()
    from agent.env_builder import run_health_checks
    from agent.health_doctor import HealthDoctor
    from agent.smoke_runner import smoke_check_all, smoke_check_model, smoke_check_summary

    return {
        "smoke_check_model": smoke_check_model,
        "smoke_check_all": smoke_check_all,
        "smoke_check_summary": smoke_check_summary,
        "run_health_checks": run_health_checks,
        "HealthDoctor": HealthDoctor,
    }


def _require_agent_spec(model: str):
    """Return the agent blueprint for ``model`` or raise 404."""
    registry = _agent_registry()
    spec = registry.get(model)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"未知 Agent 模型蓝图：{model}")
    return spec


def _agent_ssh_public(ssh) -> dict:
    return {
        "alias": getattr(ssh, "alias", None),
        "host": getattr(ssh, "host", None),
        "user": getattr(ssh, "user", None),
        "port": getattr(ssh, "port", None),
    }


def _agent_ssh_config_from_payload(payload: dict):
    """Build an agent ``SSHConfig`` from a request payload, defaulting to the
    active backend ``ServerConfig``. Shared by build/smoke/health endpoints."""
    _, _, _, SSHConfig = _agent_modules()
    payload = payload or {}
    alias = (payload.get("alias") or ServerConfig.alias or "").strip() or None
    host = (payload.get("host") or ServerConfig.host or "").strip()
    user = (payload.get("user") or ServerConfig.user or "").strip()
    port = int(payload.get("port") or ServerConfig.port or 22)
    key_file = payload.get("key_file") or payload.get("keyFile")
    if not alias and (not host or not user):
        raise HTTPException(status_code=400, detail="Agent 操作需要 SSH alias，或 host + user。")
    return SSHConfig(host=host or "127.0.0.1", user=user or "", port=port, key_file=key_file, alias=alias)


async def _read_optional_json_body(request: Request) -> dict:
    """Parse an optional JSON request body; empty body -> empty dict."""
    raw_body = await request.body()
    if not raw_body:
        return {}
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"JSON 解析失败：{exc.msg}") from exc
    return payload if isinstance(payload, dict) else {}


def _agent_diagnosis_item_to_dict(item) -> dict:
    return {
        "symptom": item.symptom,
        "cause": item.cause,
        "solution": item.solution,
        "confidence": round(float(item.confidence), 3),
        "related_issue_id": item.related_issue_id,
        "fix_command": item.fix_command,
    }


def _agent_diagnosis_to_dict(report) -> dict:
    return {
        "model": report.model,
        "overall_status": report.overall_status,
        "has_fixes": report.has_fixes,
        "items": [_agent_diagnosis_item_to_dict(item) for item in report.items],
    }


def _agent_check_task_update(task_id: str, **updates: object) -> None:
    with _AGENT_CHECK_TASKS_LOCK:
        record = dict(_AGENT_CHECK_TASKS.get(task_id, {}))
        record.update(updates)
        record["updated_at"] = datetime.now(timezone.utc).isoformat()
        _AGENT_CHECK_TASKS[task_id] = record


def _prune_agent_check_tasks_locked() -> None:
    """Bound the in-memory check-task store so long sessions don't leak."""
    if len(_AGENT_CHECK_TASKS) <= _AGENT_CHECK_TASKS_MAX:
        return
    ordered = sorted(_AGENT_CHECK_TASKS.values(), key=lambda task: str(task.get("created_at", "")))
    for task in ordered[: len(_AGENT_CHECK_TASKS) - _AGENT_CHECK_TASKS_MAX]:
        if task.get("status") in ("finished", "failed"):
            _AGENT_CHECK_TASKS.pop(task.get("taskId", ""), None)


def _start_agent_check_task(kind: str, label: str, ssh, work_fn) -> dict:
    """Run ``work_fn`` on a daemon thread and track it as an agent check task.

    ``work_fn`` must return a JSON-serializable result; exceptions are recorded
    as a failed task. Returns the initial queued task record."""
    task_id = f"agent-{kind}-{label}-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    initial_record = {
        "taskId": task_id,
        "kind": kind,
        "label": label,
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "started_at": None,
        "finished_at": None,
        "ssh": _agent_ssh_public(ssh),
        "result": None,
        "error": None,
    }
    with _AGENT_CHECK_TASKS_LOCK:
        _AGENT_CHECK_TASKS[task_id] = initial_record
        _prune_agent_check_tasks_locked()

    def _run() -> None:
        _agent_check_task_update(task_id, status="running", started_at=datetime.now(timezone.utc).isoformat())
        try:
            result = work_fn()
            _agent_check_task_update(
                task_id,
                status="finished",
                finished_at=datetime.now(timezone.utc).isoformat(),
                result=result,
                error=None,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the UI as task.error
            _agent_check_task_update(
                task_id,
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                result=None,
                error=str(exc),
            )

    threading.Thread(target=_run, name=task_id, daemon=True).start()
    with _AGENT_CHECK_TASKS_LOCK:
        return dict(_AGENT_CHECK_TASKS[task_id])


_BACKEND_ROOT = backend_root()
_BUNDLE_ROOT = bundle_root()
_DATA_ROOT = data_root()

templates = Jinja2Templates(directory=str(_BACKEND_ROOT / "templates"))
templates.env.globals["asset_version"] = "20260410-2130"
SAMPLES_MANIFEST_PATH = _BUNDLE_ROOT / "samples" / "samples_manifest.json"
DEPLOYMENT_SCRIPT_PATH = _BUNDLE_ROOT / "tools" / "check_3r_remote.ps1"

CLIENT_DIST_DIR = _BUNDLE_ROOT / "client" / "dist"
CLIENT_INDEX_HTML = CLIENT_DIST_DIR / "index.html"
CLIENT_ASSETS_DIR = CLIENT_DIST_DIR / "assets"
REACT_CLIENT_AVAILABLE = CLIENT_INDEX_HTML.exists() and CLIENT_ASSETS_DIR.exists()

(_BACKEND_ROOT / "static").mkdir(parents=True, exist_ok=True)
(_DATA_ROOT / "local_jobs").mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(_BACKEND_ROOT / "static")), name="static")
app.mount("/local_jobs", StaticFiles(directory=str(_DATA_ROOT / "local_jobs")), name="local_jobs")
if REACT_CLIENT_AVAILABLE:
    # Vite-built React client. /assets serves chunked JS/CSS bundles; the SPA
    # entry point is delivered by the / and /jobs/{id} routes below.
    app.mount("/assets", StaticFiles(directory=str(CLIENT_ASSETS_DIR)), name="client_assets")
    LOGGER.info("React client detected at %s; serving as default UI.", CLIENT_DIST_DIR)
else:
    LOGGER.info("React client build not found at %s; falling back to Jinja templates.", CLIENT_DIST_DIR)


PHASE_FLOW = [
    ("local_prepared", "本地任务已就绪", "本地任务记录和输入缓存已经准备好。", 4, 8),
    ("preparing_remote", "准备服务器目录", "正在创建远端任务目录和任务文件。", 8, 15),
    ("uploading_inputs", "上传输入文件", "正在把输入文件和任务清单发送到服务器。", 15, 25),
    ("running_remote_matches", "运行模型推理与重建", "正在执行远端模型推理、匹配或序列重建流程。", 25, 70),
    ("running_remote_pointcloud", "整理三维产物", "正在导出点云、三维场景或其他远端输出文件。", 70, 90),
    ("downloading_results", "下载结果", "正在把输出文件和日志拉回本地缓存。", 90, 98),
    ("finished", "已完成", "任务已成功完成。", 100, 100),
    ("failed", "失败", "任务因错误停止，请查看日志后重试。", 0, 0),
    ("cancelled", "已取消", "任务已在本地取消，必要时请检查服务器端是否还有残留进程。", 0, 0),
]

STATUS_LABELS = {
    "created": "已创建",
    "ready": "已就绪",
    "running": "运行中",
    "finished": "已完成",
    "failed": "失败",
    "cancelled": "已取消",
}

DELIVERY_GAPS = [
    {
        "title": "Align3R 暂停创建，等待 runner 适配",
        "detail": "CUT3R 已进入可运行线；Align3R 远端仓库入口与平台 runner 合同不一致，需完成 tool/demo.py 适配和首个 smoke 后再开放创建。",
    },
    {
        "title": "远端取消与清理仍然不够硬",
        "detail": "现在可以本地标记取消并尝试 pkill，但还缺更可靠的远端进程确认和残留目录清理。",
    },
    {
        "title": "模型间对比还缺评分闭环",
        "detail": "样例库和测评矩阵已经有雏形，但还缺每个任务的人工评分、同样例结果对比和最终报告导出。",
    },
    {
        "title": "结果归档仍然不够完整",
        "detail": "现在已经会自动生成任务摘要，但还缺更正式的交付打包、汇总报告和归档策略。",
    },
    {
        "title": "交互恢复能力还需要加强",
        "detail": "Windows 侧旧 uvicorn/ssh 进程卡住时，仍然需要更明确的检测、提示和一键恢复动作。",
    },
]

ACTIVE_PHASE_CODES = [code for code, *_ in PHASE_FLOW[:6]]
PROGRESS_PATTERN = re.compile(r"(\d+)\s*/\s*(\d+)")
PERCENT_PATTERN = re.compile(r"(?<!\d)(\d{1,3})\s*%")
COMPARE_VISUAL_KINDS = {"image", "video", "pointcloud", "model3d"}
COMPARE_PRIMARY_ROLES = {
    "matches",
    "pointcloud",
    "scene",
    "trajectory",
    "frame_preview",
    "dynamic_mask",
    "metadata",
}
EVALUATION_FIELD_LABELS = {
    "structure_completeness": "结构完整性",
    "trajectory_stability": "轨迹稳定性",
    "noise": "噪声",
    "dynamic_handling": "动态处理",
    "depth_continuity": "深度连续性",
    "presentation_usability": "展示可用性",
}
EVALUATION_FIELD_ALIASES = {
    "noise_control": "noise",
    "depth_consistency": "depth_continuity",
}


def status_label(status: str | None) -> str:
    if not status:
        return "未知"
    return STATUS_LABELS.get(status, status)


templates.env.globals["status_label"] = status_label


def build_dashboard_stats(jobs) -> dict:
    summary = {
        "total": len(jobs),
        "running": 0,
        "finished": 0,
        "failed": 0,
        "cancelled": 0,
    }
    for job in jobs:
        key = job.status if job.status in summary else None
        if key:
            summary[key] += 1
    return summary


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _job_duration_seconds(job) -> float | None:
    result_summary = load_result_summary(job.job_id)
    if result_summary:
        duration = result_summary.get("duration_seconds")
        if isinstance(duration, (int, float)) and duration >= 0:
            return float(duration)

        created_at = _parse_iso_datetime(result_summary.get("created_at") or job.created_at)
        generated_at = _parse_iso_datetime(result_summary.get("generated_at"))
        if created_at and generated_at and generated_at >= created_at:
            return (generated_at - created_at).total_seconds()
    return None


def build_stats_overview(jobs) -> dict:
    status_counter = Counter(job.status for job in jobs)
    model_counter = Counter(job.model for job in jobs)
    recent_cutoff = datetime.now() - timedelta(hours=24)
    recent_created = 0
    recent_finished = 0
    by_model = {}

    for job in jobs:
        created_at = _parse_iso_datetime(job.created_at)
        if created_at and created_at >= recent_cutoff:
            recent_created += 1
            if job.status == "finished":
                recent_finished += 1

    for model, count in sorted(model_counter.items()):
        model_jobs = [job for job in jobs if job.model == model]
        finished_jobs = [job for job in model_jobs if job.status == "finished"]
        durations = [
            duration
            for duration in (_job_duration_seconds(job) for job in finished_jobs)
            if duration is not None
        ]
        by_model[model] = {
            "count": count,
            "finished": len(finished_jobs),
            "failed": sum(1 for job in model_jobs if job.status == "failed"),
            "cancelled": sum(1 for job in model_jobs if job.status == "cancelled"),
            "success_rate": round(len(finished_jobs) / count, 4) if count else 0.0,
            "avg_duration_sec": round(sum(durations) / len(durations), 2) if durations else None,
        }

    return {
        "total": len(jobs),
        "total_jobs": len(jobs),
        "by_status": dict(sorted(status_counter.items())),
        "by_model": by_model,
        "recent_24h": {
            "created": recent_created,
            "finished": recent_finished,
        },
    }


def _split_query_list(value: str | None) -> list[str]:
    if not value:
        return []
    items: list[str] = []
    for part in value.split(","):
        item = part.strip()
        if item:
            items.append(item)
    return items


def _job_list_payload(jobs) -> list[dict]:
    payload = []
    for job in jobs:
        payload.append(
            {
                "job": job.to_dict(),
                "phase_display": build_phase_display(job.phase, job.status, job.progress_message),
            }
        )
    return payload


def load_samples_manifest() -> dict:
    global _SAMPLES_CACHE

    if not SAMPLES_MANIFEST_PATH.exists():
        return {
            "last_updated": None,
            "purpose": "Shared sample plan has not been created yet.",
            "active_models": [],
            "deferred_models": [],
            "samples": [],
            "scoring": {},
        }

    try:
        mtime_ns = SAMPLES_MANIFEST_PATH.stat().st_mtime_ns
        with _SAMPLES_CACHE_LOCK:
            if _SAMPLES_CACHE and _SAMPLES_CACHE[0] == mtime_ns:
                return _SAMPLES_CACHE[1]
            payload = json.loads(SAMPLES_MANIFEST_PATH.read_text(encoding="utf-8-sig"))
            _SAMPLES_CACHE = (mtime_ns, payload)
            return payload
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"样例清单读取失败：{exc}") from exc


def build_sample_status_summary(manifest: dict) -> dict:
    samples = manifest.get("samples") or []
    status_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    required_model_counts: dict[str, int] = {}

    for sample in samples:
        status = str(sample.get("status") or "unknown")
        source_type = str(sample.get("source_type") or "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1
        source_counts[source_type] = source_counts.get(source_type, 0) + 1
        for model in sample.get("required_models") or []:
            model_key = str(model)
            required_model_counts[model_key] = required_model_counts.get(model_key, 0) + 1

    return {
        "sample_count": len(samples),
        "status_counts": status_counts,
        "source_counts": source_counts,
        "required_model_counts": required_model_counts,
    }


def _extract_progress_ratio(progress_message: str | None) -> float | None:
    if not progress_message:
        return None

    matches = PROGRESS_PATTERN.findall(progress_message)
    for done_str, total_str in reversed(matches):
        done = int(done_str)
        total = int(total_str)
        if total > 0 and 0 <= done <= total:
            return done / total
    return None


def _extract_stage_progress(progress_message: str | None) -> dict | None:
    if not progress_message:
        return None

    ratio = _extract_progress_ratio(progress_message)
    percent: int | None = None
    percent_matches = PERCENT_PATTERN.findall(progress_message)
    if percent_matches:
        percent = max(0, min(100, int(percent_matches[-1])))
    elif ratio is not None:
        percent = int(round(ratio * 100))

    if ratio is None and percent is None:
        return None

    count_match = None
    matches = PROGRESS_PATTERN.findall(progress_message)
    if matches:
        done_str, total_str = matches[-1]
        count_match = {"done": int(done_str), "total": int(total_str)}

    return {
        "percent": percent,
        "ratio": ratio,
        "count": count_match,
    }


def build_phase_display(phase: str, status: str, progress_message: str | None = None) -> dict:
    known_phases = {code: (label, hint, start, end) for code, label, hint, start, end in PHASE_FLOW}
    if phase not in known_phases:
        phase = "local_prepared"

    label, description, start, end = known_phases[phase]
    ratio = _extract_progress_ratio(progress_message)

    if status == "finished":
        percent = 100
    elif phase == "failed":
        percent = 100 if status == "finished" else 0
    elif ratio is not None and end > start:
        percent = min(end, max(start, int(start + (end - start) * ratio)))
    elif phase == "running_remote_matches":
        percent = 40
    elif phase == "running_remote_pointcloud":
        percent = 80
    else:
        percent = end

    steps = []
    if phase in ACTIVE_PHASE_CODES:
        current_index = ACTIVE_PHASE_CODES.index(phase)
    elif status == "cancelled":
        current_index = 0
    else:
        current_index = len(ACTIVE_PHASE_CODES)
    for idx, code in enumerate(ACTIVE_PHASE_CODES):
        item_label, item_hint, *_ = known_phases[code]
        state = "todo"
        if status == "finished":
            state = "done"
        elif status == "failed":
            if idx < current_index:
                state = "done"
            elif idx == current_index:
                state = "current"
        elif idx < current_index:
            state = "done"
        elif idx == current_index:
            state = "current"
        steps.append({"code": code, "label": item_label, "hint": item_hint, "state": state})

    return {
        "label": label,
        "description": description,
        "percent": percent,
        "stageProgress": _extract_stage_progress(progress_message),
        "stage_progress": _extract_stage_progress(progress_message),
        "steps": steps,
    }


def serialize_outputs(job) -> list[dict]:
    outputs = []
    for rel_path in job.output_files:
        artifact = artifact_record_for(job.model, rel_path)
        if artifact["kind"] in {"data", "log"}:
            continue
        outputs.append(
            {
                "relative_path": rel_path,
                "display_name": artifact["name"],
                "url": artifact["url"],
                "role": artifact["role"],
                "label": artifact["label"],
                "kind": artifact["kind"],
                "is_image": artifact["kind"] == "image",
                "is_pointcloud": artifact["kind"] == "pointcloud",
                "is_model3d": artifact["kind"] == "model3d",
                "is_video": artifact["kind"] == "video",
                "is_log": artifact["kind"] == "log",
            }
        )
    return outputs


def build_job_artifact_index(job) -> dict:
    return artifact_index_for(job.model, job.output_files)


def load_result_summary_with_artifacts(job) -> dict | None:
    summary = load_result_summary(job.job_id)
    if summary is None:
        return None
    artifact_index = build_job_artifact_index(job)
    enriched = dict(summary)
    enriched.setdefault("artifacts", [
        {"name": item["name"], "relative_path": item["relativePath"], "role": item["role"], "label": item["label"], "kind": item["kind"]}
        for item in artifact_index["artifacts"]
    ])
    enriched.setdefault("artifact_groups", artifact_index["artifact_groups"])
    enriched.setdefault("primary_artifacts", artifact_index["primary_artifacts"])
    enriched.setdefault("artifactIndex", artifact_index)
    enriched.setdefault("artifact_index", artifact_index)
    return enriched


def resolve_local_output(job, relative_path: str) -> Path:
    if relative_path not in job.output_files:
        raise HTTPException(status_code=404, detail="任务中没有这个输出文件。")

    root = ROOT.resolve()
    target = (ROOT / relative_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="输出文件路径不合法。") from exc

    if not target.exists():
        raise HTTPException(status_code=404, detail="本地输出文件不存在。")
    return target


def build_job_bundle(job_id: str) -> Path:
    try:
        load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    job_dir = get_job_dir(job_id).resolve()
    root = ROOT.resolve()
    try:
        job_dir.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="任务目录路径不合法。") from exc

    if not job_dir.exists():
        raise HTTPException(status_code=404, detail=f"任务目录不存在：{job_id}。")

    bundle_dir = ROOT / "local_jobs" / "_bundles"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bundle_path = bundle_dir / f"{job_id}-bundle-{timestamp}.zip"

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(job_dir.rglob("*")):
            if not path.is_file():
                continue
            try:
                relative_path = path.resolve().relative_to(job_dir)
            except ValueError:
                continue
            archive.write(path, arcname=str(Path(job_id) / relative_path))

    return bundle_path


def serialize_previews(job) -> list[dict]:
    previews = []
    for item in iter_input_items(job):
        rel_path = item["relative_path"]
        suffix = Path(rel_path).suffix.lower()
        previews.append(
            {
                "relative_path": rel_path,
                "display_name": item["original_name"],
                "stored_name": item["stored_name"],
                "url": "/" + rel_path.replace("\\", "/"),
                "is_image": suffix in {".png", ".jpg", ".jpeg", ".bmp", ".webp"},
            }
        )
    return previews


def _job_payload(job) -> dict:
    artifact_index = build_job_artifact_index(job)
    return {
        "job": job.to_dict(),
        "phase_display": build_phase_display(job.phase, job.status, job.progress_message),
        "outputs": serialize_outputs(job),
        "previews": serialize_previews(job),
        "logs": get_log_snippets(job.job_id),
        "result_summary": load_result_summary_with_artifacts(job),
        "artifact_index": artifact_index,
        "artifactIndex": artifact_index,
        "evaluation": load_evaluation(job.job_id),
        "advisor_report": load_advisor_report(job.job_id),
    }


def build_job_inspection_packet(job) -> dict:
    payload = _job_payload(job)
    contract = None
    try:
        contract = model_contract_for(job.model)
    except KeyError:
        contract = None

    attention = _inspection_attention_items(
        job,
        artifact_index=payload["artifactIndex"],
        result_summary=payload["result_summary"],
        evaluation=payload["evaluation"],
        advisor_report=payload["advisor_report"],
        logs=payload["logs"],
    )
    artifacts = payload["artifactIndex"]["artifacts"] or []
    has_frame_geometry = any(
        a.get("relativePath", "").lower().endswith(".npy") and "frame_" in a.get("name", "").lower()
        for a in artifacts
    )
    viser_supported = job.model == "monst3r" and (has_frame_geometry or job.status == "finished")
    return {
        **payload,
        "contract": contract,
        "phaseDisplay": payload["phase_display"],
        "advisorReport": payload["advisor_report"],
        "inspection": {
            "jobId": job.job_id,
            "status": job.status,
            "phase": job.phase,
            "readyForReview": job.status == "finished" and bool(payload["artifactIndex"]["artifacts"]),
            "primaryArtifacts": payload["artifactIndex"]["primaryArtifacts"],
            "artifactGroups": payload["artifactIndex"]["groups"],
            "attention": attention,
            "recommendedActions": _inspection_recommended_actions(job, attention, payload["artifactIndex"]),
            "logDigest": _log_digest(payload["logs"]),
            "scoreDigest": _score_digest(payload["evaluation"]),
            "viserSupported": viser_supported,
        },
    }


def _job_list_item(job) -> dict:
    return {
        "job": job.to_dict(),
        "phase_display": build_phase_display(job.phase, job.status, job.progress_message),
    }


def _job_ws_event(job) -> dict:
    inspection_packet = build_job_inspection_packet(job)
    return {
        "type": "job.updated",
        "job_id": job.job_id,
        "list_item": _job_list_item(job),
        "inspection": inspection_packet,
    }


def _job_store_update_listener(job) -> None:
    manager.broadcast_from_thread(job.job_id, _job_ws_event(job))


register_job_update_listener(_job_store_update_listener)


def _inspection_attention_items(job, *, artifact_index: dict, result_summary: dict | None, evaluation: dict | None, advisor_report: dict | None, logs: list[dict]) -> list[dict]:
    items: list[dict] = []
    if job.status == "failed":
        items.append({"level": "critical", "title": "任务失败", "detail": job.error_message or job.progress_message or "查看 runner 日志确认失败原因。"})
    elif job.status in {"draft", "running"}:
        items.append({"level": "info", "title": "任务未完成", "detail": job.progress_message or "等待任务完成后再检查产物。"})

    if job.status == "finished" and not artifact_index["artifacts"]:
        items.append({"level": "warning", "title": "没有产物索引", "detail": "任务完成但没有登记输出文件，需要检查远端回传或 result summary。"})
    elif job.status == "finished" and not artifact_index["primaryArtifacts"]:
        items.append({"level": "warning", "title": "缺少核心检查对象", "detail": "已回传文件，但没有匹配到模型合同中的 primaryRoles。"})

    if not result_summary and job.status == "finished":
        items.append({"level": "warning", "title": "缺少结果摘要", "detail": "本地没有 result_summary.json，Advisor 和报告可用信息会减少。"})

    if evaluation and not evaluation.get("updated_at") and job.status == "finished":
        items.append({"level": "info", "title": "尚未人工评分", "detail": "建议完成结构、轨迹、噪声、动态处理等人工评分。"})

    if not advisor_report and job.status == "finished":
        items.append({"level": "info", "title": "尚未生成 AI Advisor 报告", "detail": "配置 Advisor 后可生成结构化实验判断和下一步建议。"})

    critical_log = _first_matching_log_line(logs, ("traceback", "error", "exception", "failed", "失败"))
    if critical_log:
        items.append({"level": "warning", "title": "日志包含异常线索", "detail": critical_log[:300]})
    return items


def _inspection_recommended_actions(job, attention: list[dict], artifact_index: dict) -> list[str]:
    if job.status == "failed":
        return ["先查看日志异常线索。", "确认远端环境、权重路径和 runner 参数。", "修复后使用 Retry 复跑。"]
    if job.status in {"draft", "running"}:
        return ["等待任务完成或继续调度运行。"]
    actions = []
    primary = artifact_index.get("primaryArtifacts") or []
    if primary:
        labels = "、".join(item["label"] for item in primary[:3])
        actions.append(f"先检查核心产物：{labels}。")
    else:
        actions.append("先确认是否缺少核心产物或输出合同配置。")
    actions.append("再查看日志和 result summary，确认参数、耗时和回传是否正常。")
    if any(item["title"] == "尚未人工评分" for item in attention):
        actions.append("完成人工评分，方便后续 Sample Matrix 横向比较。")
    if any(item["title"] == "尚未生成 AI Advisor 报告" for item in attention):
        actions.append("生成 AI Advisor 报告，沉淀问题、证据和下一步动作。")
    return actions


def _log_digest(logs: list[dict]) -> dict:
    latest = ""
    critical = ""
    for log in logs:
        lines = [line for line in str(log.get("tail") or "").splitlines() if line.strip()]
        if lines:
            latest = lines[-1]
        if not critical:
            critical = _first_matching_log_line([log], ("traceback", "error", "exception", "failed", "失败"))
    return {"count": len(logs), "latestLine": latest, "criticalLine": critical}


def _first_matching_log_line(logs: list[dict], patterns: tuple[str, ...]) -> str:
    lowered_patterns = tuple(pattern.lower() for pattern in patterns)
    for log in logs:
        for line in str(log.get("tail") or "").splitlines():
            lower_line = line.lower()
            if any(pattern in lower_line for pattern in lowered_patterns):
                return line.strip()
    return ""


def _score_digest(evaluation: dict | None) -> dict:
    if not evaluation:
        return {"rated": False, "average": None, "filled": 0}
    values = []
    for field_name in EVALUATION_SCORE_FIELDS:
        value = evaluation.get(field_name)
        if isinstance(value, int):
            values.append(value)
    average = round(sum(values) / len(values), 2) if values else None
    return {"rated": bool(evaluation.get("updated_at")), "average": average, "filled": len(values)}


def _parse_evaluation_score(field_name: str, raw_value) -> int | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, str):
        raw_value = raw_value.strip()
        if not raw_value:
            return None
    if isinstance(raw_value, bool):
        raise HTTPException(status_code=400, detail=f"{EVALUATION_FIELD_LABELS[field_name]} 必须是整数分数。")
    if isinstance(raw_value, float):
        if not raw_value.is_integer():
            raise HTTPException(status_code=400, detail=f"{EVALUATION_FIELD_LABELS[field_name]} 必须是整数分数。")
        raw_value = int(raw_value)
    elif isinstance(raw_value, str):
        try:
            raw_value = int(raw_value)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"{EVALUATION_FIELD_LABELS[field_name]} 必须是整数分数。") from exc
    elif not isinstance(raw_value, int):
        raise HTTPException(status_code=400, detail=f"{EVALUATION_FIELD_LABELS[field_name]} 必须是整数分数。")

    if raw_value < EVALUATION_SCORE_MIN or raw_value > EVALUATION_SCORE_MAX:
        raise HTTPException(
            status_code=400,
            detail=f"{EVALUATION_FIELD_LABELS[field_name]} 必须在 {EVALUATION_SCORE_MIN} 到 {EVALUATION_SCORE_MAX} 分之间。",
        )
    return raw_value


def _normalize_evaluation_payload(job_id: str, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="评分请求体必须是 JSON 对象。")

    normalized = load_evaluation(job_id)
    score_source = payload.get("scores")
    if score_source is not None and not isinstance(score_source, dict):
        raise HTTPException(status_code=400, detail="scores 字段必须是对象。")
    score_source = score_source if isinstance(score_source, dict) else {}

    for field_name in EVALUATION_SCORE_FIELDS:
        alias_name = next((alias for alias, canonical in EVALUATION_FIELD_ALIASES.items() if canonical == field_name), None)
        if field_name in payload:
            raw_value = payload[field_name]
        elif alias_name and alias_name in payload:
            raw_value = payload[alias_name]
        elif field_name in score_source:
            raw_value = score_source[field_name]
        elif alias_name and alias_name in score_source:
            raw_value = score_source[alias_name]
        else:
            continue
        normalized[field_name] = _parse_evaluation_score(field_name, raw_value)

    if "notes" in payload:
        notes = payload["notes"]
        if notes is None:
            normalized["notes"] = ""
        elif isinstance(notes, str):
            normalized["notes"] = notes.strip()
        else:
            normalized["notes"] = str(notes).strip()

    return normalized


def _metadata_value(metadata: dict, *keys: str):
    for key in keys:
        if key in metadata and metadata[key] not in (None, ""):
            return metadata[key]
    return None


def _slugify_model_id(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or f"local_model_{int(time.time())}"


def _resolve_metadata_path(raw_path: str | Path) -> Path:
    path = Path(str(raw_path)).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    resolved = path.resolve()
    root = ROOT.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        pass
    return resolved


def _validate_existing_metadata_path(metadata: dict, key: str, errors: list[str]) -> None:
    raw_path = _metadata_value(metadata, key)
    if raw_path is None:
        return
    try:
        path = _resolve_metadata_path(raw_path)
    except OSError as exc:
        errors.append(f"metadata.{key} 路径无法解析：{exc}")
        return
    if not path.exists():
        errors.append(f"metadata.{key} 指向的路径不存在：{path}")


def _validate_promotion_ready(item: DevelopmentItem) -> None:
    if item.merge_target != "runner":
        return

    metadata = item.metadata or {}
    errors: list[str] = []
    prototype_path = _metadata_value(metadata, "runnerPath", "runner_path", "localPath", "local_path", "repoPath", "repo_path")
    if prototype_path is None:
        errors.append("runner 合入需要 metadata.runnerPath、metadata.localPath 或 metadata.repoPath。")
    else:
        path = _resolve_metadata_path(prototype_path)
        if not path.exists():
            errors.append(f"原型路径不存在：{path}")

    env_hint = _metadata_value(metadata, "environmentPath", "environment_path", "envPath", "env_path", "condaEnv", "conda_env", "requirementsPath", "requirements_path")
    if env_hint is None:
        errors.append("runner 合入需要 metadata.environmentPath、metadata.condaEnv 或 metadata.requirementsPath 记录环境。")

    for key in ("environmentPath", "environment_path", "envPath", "env_path", "requirementsPath", "requirements_path"):
        _validate_existing_metadata_path(metadata, key, errors)

    required_files = _metadata_value(metadata, "requiredFiles", "required_files")
    if isinstance(required_files, list):
        for index, raw_path in enumerate(required_files, start=1):
            path = _resolve_metadata_path(raw_path)
            if not path.exists():
                errors.append(f"metadata.requiredFiles[{index}] 不存在：{path}")

    if errors:
        raise HTTPException(status_code=400, detail="Promotion 失败：" + "；".join(errors))


def _draft_registry_entry_for(item: DevelopmentItem) -> dict:
    metadata = item.metadata or {}
    model_id = item.target_model or str(_metadata_value(metadata, "modelId", "model_id") or _slugify_model_id(item.title))
    source_types = _metadata_value(metadata, "sourceTypes", "source_types") or ["images", "video", "frames"]
    return {
        "value": model_id,
        "label": str(_metadata_value(metadata, "label") or item.title),
        "description": str(_metadata_value(metadata, "description") or item.next_action or "Promotion draft from development lane."),
        "family": str(_metadata_value(metadata, "family") or "local_development"),
        "param_family": str(_metadata_value(metadata, "paramFamily", "param_family") or "research_catalog"),
        "source_types": source_types,
        "runner_status": "promotion_draft",
        "research_priority": item_priority_score(item.priority),
        "active_track": True,
        "runnable": False,
        "launch_blocker": "Promotion draft created from Development Acceleration Lane; formal runner dispatch still needs model_registry.py integration.",
        "development_item_id": item.id,
        "metadata": {
            **metadata,
            "developmentItemId": item.id,
            "promotedAt": datetime.now().isoformat(timespec="seconds"),
        },
    }


def _minimum_input_count(model: str, source_type: str) -> int:
    return minimum_input_count(model, source_type)


def _validate_new_job(model: str, source_type: str, files: list[UploadFile]) -> None:
    errors = validate_create_request(model, source_type, len(files))
    if errors:
        raise HTTPException(status_code=400, detail="；".join(errors))


def _validate_new_job_file_count(model: str, source_type: str, file_count: int) -> list[str]:
    return validate_create_request(model, source_type, file_count)


def _validate_dream3r_job_params(model: str, raw_params: dict, files: list[UploadFile]) -> None:
    if model != "dream3r":
        return
    demo_mode = str(raw_params.get("demo_mode") or "synthetic").strip().lower()
    if demo_mode != "cache":
        return
    cache_files = [
        upload
        for upload in files
        if Path(upload.filename or "").suffix.lower() in {".pt", ".pth"}
    ]
    if not cache_files:
        raise HTTPException(status_code=400, detail="Dream3R cache 模式需要上传至少一个 .pt/.pth proposal-cache 文件。")


def _validate_dispatchable(job) -> None:
    errors = validate_create_request(job.model, job.source_type, len(job.input_files))
    if errors:
        raise HTTPException(status_code=400, detail="；".join(errors))


def _parse_json_object(value: str | None, field_name: str) -> dict:
    if not value:
        return {}
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"{field_name} JSON 解析失败：{exc.msg}") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail=f"{field_name} 必须是 JSON object。")
    return payload


def _parse_model_selection(value: str) -> list[str]:
    raw = (value or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="至少选择一个模型。")
    if raw.startswith("["):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"models JSON 解析失败：{exc.msg}") from exc
        if not isinstance(payload, list):
            raise HTTPException(status_code=400, detail="models JSON 必须是数组。")
        candidates = [str(item).strip() for item in payload]
    else:
        candidates = [item.strip() for item in raw.split(",")]

    models: list[str] = []
    seen: set[str] = set()
    for model in candidates:
        if model and model not in seen:
            seen.add(model)
            models.append(model)
    if not models:
        raise HTTPException(status_code=400, detail="至少选择一个模型。")
    return models


def _new_compare_sample_id() -> str:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"compare-{timestamp}-{uuid.uuid4().hex[:6]}"


async def _uploaded_files_to_bytes(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    uploaded = []
    for upload in files:
        uploaded.append((upload.filename or "unnamed.bin", await upload.read()))
    return uploaded


def _build_raw_job_params(
    *,
    params: str,
    image_size: int,
    scene_graph: str,
    niter: int,
    lr: float,
    batch_size: int,
    max_points: int,
    match_viz_count: int,
    fps: int,
    num_frames: int,
    not_batchify: str,
    real_time: str,
    window_wise: str,
    window_size: int,
    window_overlap_ratio: float,
) -> dict:
    raw_params = {
        "image_size": image_size,
        "scene_graph": scene_graph,
        "niter": niter,
        "lr": lr,
        "batch_size": batch_size,
        "max_points": max_points,
        "match_viz_count": match_viz_count,
        "fps": fps,
        "num_frames": num_frames,
        "not_batchify": not_batchify,
        "real_time": real_time,
        "window_wise": window_wise,
        "window_size": window_size,
        "window_overlap_ratio": window_overlap_ratio,
    }
    raw_params.update(_parse_json_object(params, "params"))
    return raw_params


def _create_job_from_uploaded_bytes(
    *,
    model: str,
    source_type: str,
    notes: str,
    sample_id: str,
    raw_params: dict,
    uploaded: list[tuple[str, bytes]],
):
    errors = _validate_new_job_file_count(model, source_type, len(uploaded))
    if errors:
        raise HTTPException(status_code=400, detail="；".join(errors))
    params = build_contract_job_params(model, raw_params)
    job = create_job(model=model, source_type=source_type, notes=notes, params=params, sample_id=sample_id)
    save_inputs(job, uploaded)
    return load_job(job.job_id)


async def _create_job_from_request(
    *,
    model: str,
    source_type: str,
    notes: str,
    sample_id: str,
    params: str,
    image_size: int,
    scene_graph: str,
    niter: int,
    lr: float,
    batch_size: int,
    max_points: int,
    match_viz_count: int,
    fps: int,
    num_frames: int,
    not_batchify: str,
    real_time: str,
    window_wise: str,
    window_size: int,
    window_overlap_ratio: float,
    files: list[UploadFile],
):
    _validate_new_job(model, source_type, files)
    raw_params = _build_raw_job_params(
        params=params,
        image_size=image_size,
        scene_graph=scene_graph,
        niter=niter,
        lr=lr,
        batch_size=batch_size,
        max_points=max_points,
        match_viz_count=match_viz_count,
        fps=fps,
        num_frames=num_frames,
        not_batchify=not_batchify,
        real_time=real_time,
        window_wise=window_wise,
        window_size=window_size,
        window_overlap_ratio=window_overlap_ratio,
    )
    _validate_dream3r_job_params(model, raw_params, files)
    uploaded = await _uploaded_files_to_bytes(files)
    return _create_job_from_uploaded_bytes(
        model=model,
        source_type=source_type,
        notes=notes,
        sample_id=sample_id,
        raw_params=raw_params,
        uploaded=uploaded,
    )


def _prepare_job_for_dispatch(job_id: str, message: str) -> None:
    clear_job_runtime(job_id)
    update_job(
        job_id,
        status="running",
        phase="preparing_remote",
        error_message=None,
        progress_message=message,
    )
    _launch_remote_job(job_id)


def _load_job_or_404(job_id: str):
    try:
        return load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc


def _dispatch_job_for_api(job_id: str, message: str):
    job = _load_job_or_404(job_id)
    _validate_dispatchable(job)
    _prepare_job_for_dispatch(job_id, message)
    return load_job(job_id)


def _cancel_job_for_api(job_id: str):
    _load_job_or_404(job_id)
    cancel_remote_job(job_id)
    return load_job(job_id)


def _job_compare_record(job, sample_id_override: str | None = None) -> dict:
    evaluation = load_evaluation(job.job_id)
    result_summary = load_result_summary(job.job_id)
    primary_artifacts = (result_summary or {}).get("primary_artifacts") or []
    sample_id = sample_id_override if sample_id_override is not None else getattr(job, "sample_id", None)
    return {
        "job_id": job.job_id,
        "model": job.model,
        "status": job.status,
        "status_label": status_label(job.status),
        "phase": job.phase,
        "progress_message": job.progress_message,
        "created_at": job.created_at,
        "sample_id": sample_id,
        "score_snapshot": {
            key: evaluation.get(key)
            for key in EVALUATION_SCORE_FIELDS
            if evaluation.get(key) is not None
        },
        "primary_artifacts": primary_artifacts,
    }


def build_sample_job_matrix(manifest: dict, jobs) -> dict:
    samples = manifest.get("samples") or []
    sample_ids = {str(sample.get("id")) for sample in samples if sample.get("id")}
    seed_job_to_sample_id = {
        str(sample.get("seed_job_id")): str(sample.get("id"))
        for sample in samples
        if sample.get("id") and sample.get("seed_job_id")
    }
    grouped: dict[str, dict[str, dict]] = {sample_id: {} for sample_id in sample_ids}
    unassigned: list[dict] = []

    for job in jobs:
        sample_id = getattr(job, "sample_id", None) or seed_job_to_sample_id.get(job.job_id)
        if sample_id and sample_id in grouped:
            if job.model not in grouped[sample_id]:
                grouped[sample_id][job.model] = _job_compare_record(job, sample_id_override=sample_id)
        elif sample_id:
            unassigned.append(_job_compare_record(job))

    rows = []
    for sample in samples:
        sample_id = str(sample.get("id"))
        rows.append({"sample_id": sample_id, "jobs_by_model": grouped.get(sample_id, {})})

    return {"rows": rows, "unassigned_jobs": unassigned}


def _job_score_snapshot(job) -> dict:
    evaluation = load_evaluation(job.job_id)
    return {
        key: evaluation.get(key)
        for key in EVALUATION_SCORE_FIELDS
        if evaluation.get(key) is not None
    }


def _job_compare_visuals(job) -> list[dict]:
    artifact_index = build_job_artifact_index(job)
    artifacts = artifact_index.get("artifacts") or []
    primary_paths = {
        item.get("relativePath") or item.get("relative_path")
        for item in artifact_index.get("primaryArtifacts") or []
    }
    visuals = []
    for artifact in artifacts:
        if artifact.get("kind") not in COMPARE_VISUAL_KINDS and artifact.get("role") not in COMPARE_PRIMARY_ROLES:
            continue
        rel_path = artifact.get("relativePath")
        visuals.append(
            {
                "role": artifact.get("role"),
                "label": artifact.get("label"),
                "kind": artifact.get("kind"),
                "name": artifact.get("name"),
                "relativePath": rel_path,
                "relative_path": rel_path,
                "url": artifact.get("url"),
                "primary": rel_path in primary_paths,
            }
        )
    return sorted(visuals, key=lambda item: (not item["primary"], item["role"] or "", item["name"] or ""))


def build_sample_compare_packet(sample_id: str) -> dict:
    normalized_sample_id = sample_id.strip()
    if not normalized_sample_id:
        raise HTTPException(status_code=400, detail="sample_id 不能为空。")
    result = query_jobs(limit=200, sample_id=normalized_sample_id, sort="created_asc")
    jobs = result["jobs"]
    model_cells = []
    status_counts: dict[str, int] = {}
    visual_count = 0
    score_values = []

    for job in jobs:
        visuals = _job_compare_visuals(job)
        score_snapshot = _job_score_snapshot(job)
        score_values.extend(value for value in score_snapshot.values() if isinstance(value, (int, float)))
        visual_count += len(visuals)
        status_counts[job.status] = status_counts.get(job.status, 0) + 1
        model_cells.append(
            {
                "model": job.model,
                "jobId": job.job_id,
                "job_id": job.job_id,
                "status": job.status,
                "statusLabel": status_label(job.status),
                "status_label": status_label(job.status),
                "phase": job.phase,
                "progressMessage": job.progress_message,
                "progress_message": job.progress_message,
                "createdAt": job.created_at,
                "created_at": job.created_at,
                "scoreSnapshot": score_snapshot,
                "score_snapshot": score_snapshot,
                "primaryArtifacts": build_job_artifact_index(job).get("primaryArtifacts") or [],
                "primary_artifacts": build_job_artifact_index(job).get("primary_artifacts") or [],
                "visuals": visuals,
                "outputs": serialize_outputs(job),
                "previews": serialize_previews(job),
            }
        )

    average_score = sum(score_values) / len(score_values) if score_values else None
    return {
        "sampleId": normalized_sample_id,
        "sample_id": normalized_sample_id,
        "summary": {
            "jobCount": len(jobs),
            "job_count": len(jobs),
            "finished": status_counts.get("finished", 0),
            "running": status_counts.get("running", 0),
            "attention": status_counts.get("failed", 0) + status_counts.get("cancelled", 0),
            "visualCount": visual_count,
            "visual_count": visual_count,
            "averageScore": average_score,
            "average_score": average_score,
            "statusCounts": status_counts,
            "status_counts": status_counts,
        },
        "modelCells": model_cells,
        "model_cells": model_cells,
        "reportMarkdown": build_sample_compare_markdown(normalized_sample_id, model_cells, average_score),
        "report_markdown": build_sample_compare_markdown(normalized_sample_id, model_cells, average_score),
    }


def build_sample_compare_markdown(sample_id: str, model_cells: list[dict], average_score: float | None) -> str:
    lines = [
        f"# 3R Sample Compare: {sample_id}",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- Jobs: {len(model_cells)}",
        f"- Average score: {average_score:.2f}" if average_score is not None else "- Average score: --",
        "",
        "| Model | Job | Status | Score fields | Visuals | Primary artifact |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for cell in model_cells:
        primary = cell.get("primaryArtifacts") or cell.get("primary_artifacts") or []
        first_primary = primary[0] if primary else {}
        score_snapshot = cell.get("scoreSnapshot") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    str(cell.get("model") or "--"),
                    str(cell.get("jobId") or "--"),
                    str(cell.get("statusLabel") or cell.get("status") or "--"),
                    str(len(score_snapshot)),
                    str(len(cell.get("visuals") or [])),
                    str(first_primary.get("name") or first_primary.get("relative_path") or "--"),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def _runner_thread_target(job_id: str) -> None:
    try:
        run_remote_job(job_id)
    finally:
        with _RUNNER_THREADS_LOCK:
            existing = _RUNNER_THREADS.get(job_id)
            if existing is threading.current_thread():
                _RUNNER_THREADS.pop(job_id, None)


def _launch_remote_job(job_id: str) -> None:
    with _RUNNER_THREADS_LOCK:
        existing = _RUNNER_THREADS.get(job_id)
        if existing and existing.is_alive():
            raise HTTPException(status_code=409, detail=f"任务 {job_id} 已经在后台运行。")
        thread = threading.Thread(
            target=_runner_thread_target,
            args=(job_id,),
            daemon=True,
            name=f"vision-remote-job-{job_id}",
        )
        _RUNNER_THREADS[job_id] = thread
        thread.start()


async def _send_job_ws_snapshot(websocket: WebSocket, job_id: str) -> bool:
    if job_id == WS_ALL_JOBS_KEY:
        result = query_jobs(limit=50)
        await websocket.send_json(
            {
                "type": "jobs.snapshot",
                "jobs": _job_list_payload(result["jobs"]),
                "summary": build_dashboard_stats(result["jobs"]),
                "page": result["page"],
            }
        )
        return True

    try:
        job = load_job(job_id)
    except FileNotFoundError:
        await websocket.send_json({"type": "job.error", "job_id": job_id, "detail": f"未找到任务 {job_id}。"})
        await websocket.close(code=1008)
        return False

    await websocket.send_json(_job_ws_event(job))
    return True


@app.websocket("/ws/jobs/{job_id}")
async def job_websocket(websocket: WebSocket, job_id: str):
    await manager.connect(job_id, websocket)
    connected = await _send_job_ws_snapshot(websocket, job_id)
    if not connected:
        await manager.disconnect(job_id, websocket)
        return

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await manager.disconnect(job_id, websocket)


@app.get("/")
async def index(request: Request):
    if REACT_CLIENT_AVAILABLE:
        return FileResponse(
            str(CLIENT_INDEX_HTML),
            media_type="text/html",
            headers={"Cache-Control": "no-store"},
        )
    jobs = list_jobs(limit=50)
    summary = build_dashboard_stats(jobs)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "jobs": jobs,
            "summary": summary,
            "delivery_gaps": DELIVERY_GAPS,
            "server": ServerConfig(),
            "models": [(item["value"], f"{item['label']}（{item['description']}）") for item in MODEL_OPTIONS],
            "phase_builder": build_phase_display,
        },
    )


@app.post("/jobs")
async def create_job_view(
    model: str = Form(...),
    source_type: str = Form(...),
    notes: str = Form(""),
    sample_id: str = Form(""),
    params: str = Form(""),
    image_size: int = Form(512),
    scene_graph: str = Form("complete"),
    niter: int = Form(300),
    lr: float = Form(0.01),
    batch_size: int = Form(1),
    max_points: int = Form(250000),
    match_viz_count: int = Form(50),
    fps: int = Form(0),
    num_frames: int = Form(24),
    not_batchify: str = Form("true"),
    real_time: str = Form("false"),
    window_wise: str = Form("false"),
    window_size: int = Form(100),
    window_overlap_ratio: float = Form(0.5),
    files: list[UploadFile] = File(default=[]),
):
    job = await _create_job_from_request(
        model=model,
        source_type=source_type,
        notes=notes,
        sample_id=sample_id,
        params=params,
        image_size=image_size,
        scene_graph=scene_graph,
        niter=niter,
        lr=lr,
        batch_size=batch_size,
        max_points=max_points,
        match_viz_count=match_viz_count,
        fps=fps,
        num_frames=num_frames,
        not_batchify=not_batchify,
        real_time=real_time,
        window_wise=window_wise,
        window_size=window_size,
        window_overlap_ratio=window_overlap_ratio,
        files=files,
    )
    return RedirectResponse(url=f"/jobs/{job.job_id}", status_code=303)


@app.get("/jobs/{job_id}")
async def job_detail(request: Request, job_id: str):
    try:
        job = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    if REACT_CLIENT_AVAILABLE:
        # React Router renders the matching detail screen client-side.
        return FileResponse(
            str(CLIENT_INDEX_HTML),
            media_type="text/html",
            headers={"Cache-Control": "no-store"},
        )

    payload = _job_payload(job)
    return templates.TemplateResponse(
        request,
        "job_detail.html",
        {
            **payload,
            "job": job,
        },
    )


@app.post("/jobs/{job_id}/dispatch")
async def dispatch_job(job_id: str):
    try:
        job = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    _validate_dispatchable(job)
    _prepare_job_for_dispatch(job_id, "正在启动远端调度线程...")
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/retry")
async def retry_job(job_id: str):
    try:
        job = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    _validate_dispatchable(job)
    _prepare_job_for_dispatch(job_id, "正在重新启动远端调度线程...")
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/duplicate")
async def duplicate_job_view(job_id: str):
    try:
        new_job = duplicate_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    return RedirectResponse(url=f"/jobs/{new_job.job_id}", status_code=303)


@app.post("/jobs/{job_id}/mark-failed")
async def mark_job_failed(job_id: str):
    try:
        load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    update_job(
        job_id,
        status="failed",
        phase="failed",
        error_message="用户已在本地将任务标记为失败。未尝试清理远端进程。",
        progress_message="已在本地标记为失败。可以点击重试重新调度。",
    )
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/cancel")
async def cancel_job_view(job_id: str):
    try:
        load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    cancel_remote_job(job_id)
    return RedirectResponse(url=f"/jobs/{job_id}", status_code=303)


@app.post("/jobs/{job_id}/open-output")
async def open_output_file(job_id: str, relative_path: str = Form(...)):
    try:
        job = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    target = resolve_local_output(job, relative_path)
    try:
        os.startfile(str(target))  # type: ignore[attr-defined]
    except AttributeError as exc:
        raise HTTPException(status_code=400, detail="当前系统不支持用默认程序打开本地文件。") from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"打开本地文件失败：{exc}") from exc

    return JSONResponse({"ok": True, "path": str(target)})


@app.post("/api/jobs/{job_id}/open-output")
async def open_output_file_api(job_id: str, relative_path: str = Form(...)):
    return await open_output_file(job_id, relative_path)


@app.get("/api/jobs")
async def jobs_api(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    model: str | None = None,
    source_type: str | None = None,
    sample_id: str | None = None,
    search: str | None = None,
    sort: str = "created_desc",
):
    result = query_jobs(
        limit=limit,
        offset=offset,
        statuses=_split_query_list(status),
        models=_split_query_list(model),
        source_types=_split_query_list(source_type),
        sample_id=sample_id,
        search=search,
        sort=sort,
    )
    jobs = result["jobs"]
    page = result["page"]
    filters = result["filters"]
    return JSONResponse(
        {
            "jobs": _job_list_payload(jobs),
            "summary": build_dashboard_stats(jobs),
            "page": page,
            "pageInfo": {
                "limit": page["limit"],
                "offset": page["offset"],
                "total": page["total"],
                "hasMore": page["has_more"],
                "sort": page["sort"],
            },
            "filters": filters,
        }
    )


@app.get("/api/jobs/{job_id}")
async def job_detail_api(job_id: str):
    try:
        job = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    return JSONResponse(_job_payload(job))


@app.get("/api/jobs/{job_id}/bundle")
async def job_bundle_api(job_id: str):
    bundle_path = build_job_bundle(job_id)
    return FileResponse(
        path=str(bundle_path),
        filename=bundle_path.name,
        media_type="application/zip",
    )


@app.get("/api/stats/overview")
async def stats_overview_api():
    return JSONResponse(build_stats_overview(list_all_jobs()))


@app.get("/api/health")
async def health_api():
    return JSONResponse({"ok": True, "service": "kykt-vision-ui", "version": app.version})


@app.get("/api/runners/availability")
async def runners_availability_api():
    """检查各执行器可用性"""
    try:
        from runners import LocalDockerRunner, OnlineAPIRunner
    except ImportError:
        LocalDockerRunner = None
        OnlineAPIRunner = None

    docker_available = False
    if LocalDockerRunner is not None:
        docker_available = bool(LocalDockerRunner.is_available())

    online_api_available = False
    if OnlineAPIRunner is not None:
        online_api_available = len(OnlineAPIRunner.available_providers()) > 0

    return JSONResponse({
        "ssh": True,  # SSH 始终可用（配置由用户提供）
        "docker": docker_available,
        "online_api": online_api_available,
    })


# ─────────────── 参数模板 API ───────────────

@app.get("/api/templates")
async def list_templates_api(model: str | None = None):
    """列出参数模板"""
    from param_templates import list_templates
    return JSONResponse(list_templates(model))


@app.get("/api/templates/{template_id}")
async def get_template_api(template_id: str):
    """获取单个模板"""
    from param_templates import get_template
    tpl = get_template(template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="模板不存在")
    return JSONResponse(tpl)


@app.post("/api/templates")
async def save_template_api(request: Request):
    """保存参数模板"""
    from param_templates import save_template, make_template_id
    body = await request.json()
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="模板名称不能为空")
    template_id = body.get("id") or make_template_id(name)
    tpl = save_template(
        template_id=template_id,
        name=name,
        model=body.get("model", ""),
        params=body.get("params", {}),
        source_type=body.get("source_type", "images"),
        notes=body.get("notes", ""),
    )
    return JSONResponse(tpl)


@app.delete("/api/templates/{template_id}")
async def delete_template_api(template_id: str):
    """删除模板"""
    from param_templates import delete_template
    deleted = delete_template(template_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="模板不存在")
    return JSONResponse({"ok": True})


# ─────────────── 服务器 Profile API ───────────────

@app.get("/api/servers")
async def list_servers_api():
    """列出所有服务器配置"""
    from server_profiles import list_profiles, get_active_profile_id
    profiles = list_profiles()
    active_id = get_active_profile_id()
    return JSONResponse({"profiles": profiles, "active_id": active_id})


@app.post("/api/servers")
async def save_server_api(request: Request):
    """保存服务器配置"""
    from server_profiles import save_profile
    body = await request.json()
    alias = body.get("alias", "").strip()
    if not alias:
        raise HTTPException(status_code=400, detail="服务器别名不能为空")
    profile_id = body.get("id") or alias.lower().replace(" ", "_")
    profile = save_profile(profile_id, body)
    return JSONResponse(profile)


@app.post("/api/servers/active")
async def set_active_server_api(request: Request):
    """设置活跃服务器"""
    from server_profiles import set_active_profile_id, get_profile
    body = await request.json()
    profile_id = body.get("id")
    if profile_id:
        profile = get_profile(profile_id)
        if not profile:
            raise HTTPException(status_code=404, detail="服务器配置不存在")
    set_active_profile_id(profile_id)
    return JSONResponse({"ok": True, "active_id": profile_id})


@app.delete("/api/servers/{profile_id}")
async def delete_server_api(profile_id: str):
    """删除服务器配置"""
    from server_profiles import delete_profile
    deleted = delete_profile(profile_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="服务器配置不存在")
    return JSONResponse({"ok": True})


@app.get("/api/app/state")
async def app_state_api():
    job_query = query_jobs(limit=50)
    jobs = job_query["jobs"]
    job_page = job_query["page"]
    model_catalog = get_model_catalog_options()
    model_contracts_list = all_model_contracts()
    model_contracts = {c["model"]: c for c in model_contracts_list}
    development_lanes = [item.to_dict() for item in development_store.list_items()]
    return JSONResponse(
        {
            "health": {"ok": True, "service": "kykt-vision-ui", "version": app.version},
            "summary": build_dashboard_stats(jobs),
            "job_page": job_page,
            "delivery_gaps": DELIVERY_GAPS,
            "server": {
                "alias": ServerConfig.alias,
                "host": ServerConfig.host,
                "user": ServerConfig.user,
                "port": ServerConfig.port,
                "remote_root": ServerConfig.remote_root,
            },
            "models": MODEL_OPTIONS,
            "model_catalog": model_catalog,
            "model_contracts": model_contracts,
            "source_types": SOURCE_TYPE_OPTIONS,
            "advisor": advisor_status(),
            "development_lanes": development_lanes,
            "deliveryGaps": DELIVERY_GAPS,
            "jobPage": {
                "limit": job_page["limit"],
                "offset": job_page["offset"],
                "total": job_page["total"],
                "hasMore": job_page["has_more"],
                "sort": job_page["sort"],
            },
            "modelCatalog": model_catalog,
            "modelContracts": model_contracts,
            "sourceTypes": SOURCE_TYPE_OPTIONS,
            "developmentLanes": development_lanes,
        }
    )


@app.get("/api/agent/registry")
async def agent_registry_api():
    registry = _agent_registry()
    summary = registry.summary()
    models = [_agent_spec_to_dict(spec) for spec in registry.sorted_by_priority()]
    return JSONResponse(
        {
            "summary": summary,
            "models": models,
            "specs_dir": str(model_specs_dir()),
        }
    )


@app.get("/api/agent/registry/{model}")
async def agent_model_detail_api(model: str):
    registry = _agent_registry()
    spec = registry.get(model)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"未知 Agent 模型蓝图：{model}")
    return JSONResponse(_agent_spec_to_dict(spec))


@app.get("/api/agent/validate")
async def agent_validate_api(model: str | None = None):
    _, _, SchemaValidator, _ = _agent_modules()
    validator = SchemaValidator(specs_dir=model_specs_dir())
    if model:
        path = model_specs_dir() / f"{model.lower()}.yaml"
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"未找到 Agent 蓝图：{model}")
        results = [validator.validate_file(path)]
    else:
        results = validator.validate_all()

    total_errors = sum(len(result.errors) for result in results)
    total_warnings = sum(len(result.warnings) for result in results)
    valid_count = sum(1 for result in results if result.valid)
    return JSONResponse(
        {
            "ok": total_errors == 0,
            "summary": {
                "total": len(results),
                "valid": valid_count,
                "errors": total_errors,
                "warnings": total_warnings,
            },
            "results": [_agent_validation_to_dict(result) for result in results],
        }
    )


@app.get("/api/agent/builds")
async def agent_builds_api():
    with _AGENT_BUILD_TASKS_LOCK:
        tasks = sorted(
            (dict(task) for task in _AGENT_BUILD_TASKS.values()),
            key=lambda task: str(task.get("created_at", "")),
            reverse=True,
        )
    return JSONResponse({"tasks": tasks})


@app.get("/api/agent/builds/{task_id}")
async def agent_build_status_api(task_id: str):
    with _AGENT_BUILD_TASKS_LOCK:
        task = _AGENT_BUILD_TASKS.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"未找到 Agent 构建任务：{task_id}")
        return JSONResponse(task)


@app.post("/api/agent/build/{model}")
async def agent_build_model_api(model: str, request: Request):
    EnvBuilder, _, _, _ = _agent_modules()
    spec = _require_agent_spec(model)
    payload = await _read_optional_json_body(request)
    ssh = _agent_ssh_config_from_payload(payload)
    alias = ssh.alias
    host = ssh.host
    user = ssh.user
    port = ssh.port
    task_id = f"agent-build-{spec.key}-{uuid.uuid4().hex[:8]}"
    now = datetime.now(timezone.utc).isoformat()
    initial_record = {
        "taskId": task_id,
        "model": spec.key,
        "modelName": spec.name,
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "ssh": {
            "alias": alias,
            "host": host,
            "user": user,
            "port": port,
        },
        "report": None,
        "error": None,
    }
    with _AGENT_BUILD_TASKS_LOCK:
        _AGENT_BUILD_TASKS[task_id] = initial_record

    def _run_agent_build() -> None:
        _agent_build_task_update(task_id, status="running", started_at=datetime.now(timezone.utc).isoformat())
        try:
            report = EnvBuilder(ssh=ssh).build(spec)
            _agent_build_task_update(
                task_id,
                status="finished" if report.success else "failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                report=_agent_environment_report_to_dict(report),
                error=None if report.success else "Agent environment build failed.",
            )
        except Exception as exc:
            _agent_build_task_update(
                task_id,
                status="failed",
                finished_at=datetime.now(timezone.utc).isoformat(),
                report=None,
                error=str(exc),
            )

    thread = threading.Thread(target=_run_agent_build, name=task_id, daemon=True)
    thread.start()
    return JSONResponse(_AGENT_BUILD_TASKS[task_id], status_code=202)


@app.post("/api/agent/smoke/{model}")
async def agent_smoke_model_api(model: str, request: Request):
    """Launch a background smoke check (env + checkpoints + smoke_test) for one model."""
    spec = _require_agent_spec(model)
    ssh = _agent_ssh_config_from_payload(await _read_optional_json_body(request))
    smoke_check_model = _agent_check_modules()["smoke_check_model"]

    def _work() -> dict:
        return smoke_check_model(ssh, spec).to_dict()

    return JSONResponse(_start_agent_check_task("smoke", spec.key, ssh, _work), status_code=202)


@app.post("/api/agent/health/{model}")
async def agent_health_model_api(model: str, request: Request):
    """Launch background health checks for one model and attach an AI diagnosis."""
    spec = _require_agent_spec(model)
    ssh = _agent_ssh_config_from_payload(await _read_optional_json_body(request))
    mods = _agent_check_modules()
    run_health_checks = mods["run_health_checks"]
    HealthDoctor = mods["HealthDoctor"]

    def _work() -> dict:
        results = run_health_checks(ssh, spec)
        diagnosis = HealthDoctor().diagnose(spec, results)
        return {
            "checks": [_agent_build_step_to_dict(result) for result in results],
            "all_passed": all(result.success for result in results) if results else True,
            "diagnosis": _agent_diagnosis_to_dict(diagnosis),
        }

    return JSONResponse(_start_agent_check_task("health", spec.key, ssh, _work), status_code=202)


@app.post("/api/agent/smoke-batch")
async def agent_smoke_batch_api(request: Request):
    """Launch one background task that smoke-checks several (or all) models."""
    payload = await _read_optional_json_body(request)
    ssh = _agent_ssh_config_from_payload(payload)
    registry = _agent_registry()

    requested = payload.get("models")
    if isinstance(requested, str):
        requested = [item.strip() for item in requested.split(",") if item.strip()]
    models: list[str] | None = None
    label = "all"
    if requested:
        unknown = [name for name in requested if registry.get(name) is None]
        if unknown:
            raise HTTPException(status_code=404, detail=f"未知 Agent 模型蓝图：{', '.join(unknown)}")
        # spec.name.lower() == key for every registered blueprint, so the key
        # list is an accepted filter for smoke_check_all.
        models = list(requested)
        label = "selected"

    mods = _agent_check_modules()
    smoke_check_all = mods["smoke_check_all"]
    smoke_check_summary = mods["smoke_check_summary"]
    specs_dir = model_specs_dir()

    def _work() -> dict:
        reports = smoke_check_all(ssh, specs_dir, filter_models=models)
        return smoke_check_summary(reports)

    return JSONResponse(_start_agent_check_task("smoke-batch", label, ssh, _work), status_code=202)


@app.get("/api/agent/checks")
async def agent_checks_api():
    with _AGENT_CHECK_TASKS_LOCK:
        tasks = sorted(
            (dict(task) for task in _AGENT_CHECK_TASKS.values()),
            key=lambda task: str(task.get("created_at", "")),
            reverse=True,
        )
    return JSONResponse({"tasks": tasks})


@app.get("/api/agent/checks/{task_id}")
async def agent_check_status_api(task_id: str):
    with _AGENT_CHECK_TASKS_LOCK:
        task = _AGENT_CHECK_TASKS.get(task_id)
        if task is None:
            raise HTTPException(status_code=404, detail=f"未找到 Agent 检查任务：{task_id}")
        return JSONResponse(dict(task))


def _load_job_scene_meta(job_id: str) -> dict | None:
    path = get_job_dir(job_id) / "output" / "scene_meta.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None


def _blueprint_for_record(model: str) -> dict | None:
    """Pull the reproduce-relevant fields from a model's agent blueprint."""
    try:
        spec = _agent_registry().get(model)
    except Exception:  # noqa: BLE001 - blueprint is best-effort metadata
        return None
    if spec is None:
        return None
    return {
        "version": spec.version,
        "environment": spec.environment,
        "repo": spec.repo,
        "runner": spec.runner,
        "checkpoints": spec.checkpoints,
        "build_steps": spec.build_steps,
        "smoke_test": spec.smoke_test,
    }


def _experiment_record_for(job) -> dict:
    contract = None
    try:
        contract = model_contract_for(job.model)
    except KeyError:
        contract = None
    return build_experiment_record(
        job=job.to_dict(),
        result_summary=load_result_summary(job.job_id),
        scene_meta=_load_job_scene_meta(job.job_id),
        blueprint=_blueprint_for_record(job.model),
        contract=contract,
        server={"alias": ServerConfig.alias, "host": ServerConfig.host, "user": ServerConfig.user},
    )


@app.get("/api/agent/experiment-record/{job_id}")
async def agent_experiment_record_api(job_id: str):
    """Return the reproducible experiment-record manifest for a job (preview)."""
    try:
        job = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc
    return JSONResponse(_experiment_record_for(job))


@app.get("/api/agent/experiment-record/{job_id}/download")
async def agent_experiment_record_download_api(job_id: str):
    """Build and download a reproducible experiment-record zip for a job."""
    try:
        job = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc
    record = _experiment_record_for(job)
    bundle_path = build_experiment_record_bundle(
        job_id=job_id,
        job_dir=get_job_dir(job_id),
        record=record,
        out_dir=ROOT / "local_jobs" / "_bundles",
    )
    return FileResponse(path=str(bundle_path), filename=bundle_path.name, media_type="application/zip")


@app.get("/api/models/catalog")
async def models_catalog_api():
    return JSONResponse({"models": get_model_catalog_options(), "contracts": all_model_contracts()})


@app.get("/api/models/{model}/contract")
async def model_contract_api(model: str):
    try:
        return JSONResponse(model_contract_for(model))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"未知模型：{model}") from exc


@app.post("/api/models/{model}/validate-create")
async def validate_model_create_api(model: str, request: Request):
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"模型验证 JSON 解析失败：{exc.msg}") from exc
    source_type = str(payload.get("sourceType") or payload.get("source_type") or "")
    file_count = int(payload.get("fileCount") or payload.get("file_count") or 0)
    errors = validate_create_request(model, source_type, file_count)
    return JSONResponse({"ok": not errors, "model": model, "sourceType": source_type, "fileCount": file_count, "errors": errors})


@app.get("/api/jobs/{job_id}/contract")
async def job_contract_api(job_id: str):
    try:
        job = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc
    try:
        contract = model_contract_for(job.model)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"未知模型：{job.model}") from exc
    return JSONResponse({"jobId": job_id, "model": job.model, "contract": contract})


@app.get("/api/jobs/{job_id}/artifacts")
async def job_artifacts_api(job_id: str):
    try:
        job = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc
    return JSONResponse({"jobId": job_id, "model": job.model, "artifactIndex": build_job_artifact_index(job)})


@app.get("/api/jobs/{job_id}/inspection")
async def job_inspection_api(job_id: str):
    try:
        job = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc
    return JSONResponse(build_job_inspection_packet(job))


@app.get("/api/jobs/{job_id}/scene-meta")
async def job_scene_meta_api(job_id: str):
    """Return a normalized, runner-agnostic view of the job's scene_meta.json."""
    try:
        job = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc
    raw = _load_job_scene_meta(job_id)
    return JSONResponse(
        {
            "jobId": job_id,
            "model": job.model,
            "sceneMeta": normalize_scene_meta(job.model, raw, output_files=job.output_files),
        }
    )


@app.get("/api/jobs/{job_id}/contract-check")
async def job_contract_check_api(job_id: str):
    """Validate the job's downloaded outputs against the model result contract."""
    try:
        job = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc
    raw = _load_job_scene_meta(job_id)
    return JSONResponse(
        {
            "jobId": job_id,
            "contractCheck": check_output_contract(job.model, job.output_files, raw),
        }
    )


@app.get("/api/development/lanes")
async def development_lanes_api():
    try:
        items = development_store.list_items()
    except DevelopmentStoreError as exc:
        raise HTTPException(status_code=500, detail=f"研发车道读取失败：{exc}") from exc
    return JSONResponse([item.to_dict() for item in items])


@app.post("/api/development/lanes")
async def create_development_lane_api(request: Request):
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"研发车道 JSON 解析失败：{exc.msg}") from exc
    try:
        item = development_store.create_item(payload)
    except DevelopmentStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(item.to_dict(), status_code=201)


@app.patch("/api/development/lanes/{item_id}")
async def update_development_lane_api(item_id: str, request: Request):
    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"研发车道 JSON 解析失败：{exc.msg}") from exc
    try:
        item = development_store.update_item(item_id, payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到研发车道条目 {item_id}。") from exc
    except DevelopmentStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if item.status == "merged":
        LOGGER.info("Development lane %s is marked merged and ready for formal model registry integration.", item.id)
    return JSONResponse(item.to_dict())


@app.delete("/api/development/lanes/{item_id}")
async def delete_development_lane_api(item_id: str):
    try:
        development_store.delete_item(item_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到研发车道条目 {item_id}。") from exc
    return JSONResponse({"ok": True, "id": item_id})


@app.post("/api/development/lanes/{item_id}/promote")
async def promote_development_lane_api(item_id: str):
    try:
        item = development_store.get_item(item_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到研发车道条目 {item_id}。") from exc

    _validate_promotion_ready(item)
    registry_entry = None
    if item.merge_target == "runner":
        try:
            registry_entry = draft_local_model_entry(_draft_registry_entry_for(item))
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=500, detail=f"模型目录草稿写入失败：{exc}") from exc

    metadata = dict(item.metadata)
    metadata["promotion"] = {
        "status": "drafted" if registry_entry else "not_required",
        "promotedAt": datetime.now().isoformat(timespec="seconds"),
        "registryEntry": registry_entry,
    }
    try:
        updated = development_store.update_item(item_id, {"status": "merged", "metadata": metadata})
    except DevelopmentStoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    LOGGER.info("Development lane %s promoted with merge target %s.", item.id, item.merge_target or "none")
    return JSONResponse({"ok": True, "item": updated.to_dict(), "registryEntry": registry_entry})


def load_deployment_status(*, force_refresh: bool = False) -> dict:
    global _DEPLOYMENT_STATUS_CACHE, _DEPLOYMENT_STATUS_REFRESHING

    def _utc_iso(ts: float) -> str:
        return datetime.fromtimestamp(ts, timezone.utc).isoformat()

    def _cache_age_seconds(entry: dict, now_mono: float) -> float:
        return max(0.0, now_mono - float(entry["fetched_monotonic"]))

    def _build_response(entry: dict, *, state: str, error: str | None = None) -> dict:
        age_seconds = _cache_age_seconds(entry, time.monotonic())
        payload = copy.deepcopy(entry["payload"])
        payload["ok"] = bool((payload.get("summary") or {}).get("ok"))
        payload["source"] = state
        payload["stale"] = state.startswith("stale")
        payload["fetched_at"] = entry["fetched_at"]
        payload["cache"] = {
            "state": state,
            "hit": state != "live",
            "age_seconds": round(age_seconds, 3),
            "ttl_seconds": DEPLOYMENT_STATUS_TTL_SECONDS,
            "stale_ttl_seconds": DEPLOYMENT_STATUS_STALE_SECONDS,
            "timeout_seconds": DEPLOYMENT_STATUS_TIMEOUT_SECONDS,
            "expires_at": _utc_iso(entry["fetched_wall_time"] + DEPLOYMENT_STATUS_TTL_SECONDS),
            "script_path": str(DEPLOYMENT_SCRIPT_PATH),
            "ssh_alias": ServerConfig.alias,
        }
        if error:
            payload["cache"]["last_error"] = error
        return payload

    def _parse_deployment_payload(stdout: str) -> dict:
        stripped = stdout.strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start == -1 or end <= start:
                raise
            return json.loads(stripped[start : end + 1])

    def _run_status_command() -> dict:
        if not DEPLOYMENT_SCRIPT_PATH.exists():
            raise HTTPException(status_code=500, detail=f"远端部署检查脚本不存在：{DEPLOYMENT_SCRIPT_PATH}")

        powershell_executable = shutil.which("pwsh") or shutil.which("powershell") or "powershell"
        command = [
            powershell_executable,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(DEPLOYMENT_SCRIPT_PATH),
            "-SshAlias",
            ServerConfig.alias,
            "-Json",
        ]
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=DEPLOYMENT_STATUS_TIMEOUT_SECONDS,
                check=True,
            )
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail="远端部署状态检查超时。") from exc
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() or exc.stdout.strip() or "远端部署状态检查失败。"
            raise HTTPException(status_code=502, detail=detail) from exc

        try:
            return _parse_deployment_payload(completed.stdout)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail="远端部署状态返回了无法解析的 JSON。") from exc

    now_mono = time.monotonic()
    with _DEPLOYMENT_STATUS_CACHE_LOCK:
        while _DEPLOYMENT_STATUS_REFRESHING:
            entry = _DEPLOYMENT_STATUS_CACHE
            if entry and _cache_age_seconds(entry, now_mono) < DEPLOYMENT_STATUS_STALE_SECONDS:
                return _build_response(entry, state="stale-refreshing")
            _DEPLOYMENT_STATUS_CACHE_LOCK.wait(timeout=0.25)
            now_mono = time.monotonic()

        entry = _DEPLOYMENT_STATUS_CACHE
        if entry and not force_refresh and _cache_age_seconds(entry, now_mono) < DEPLOYMENT_STATUS_TTL_SECONDS:
            return _build_response(entry, state="cache")

        _DEPLOYMENT_STATUS_REFRESHING = True

    try:
        payload = _run_status_command()
    except HTTPException as exc:
        with _DEPLOYMENT_STATUS_CACHE_LOCK:
            _DEPLOYMENT_STATUS_REFRESHING = False
            _DEPLOYMENT_STATUS_CACHE_LOCK.notify_all()
            entry = _DEPLOYMENT_STATUS_CACHE
            if entry and _cache_age_seconds(entry, time.monotonic()) < DEPLOYMENT_STATUS_STALE_SECONDS:
                return _build_response(entry, state="stale-error", error=str(exc.detail))
        raise

    fetched_wall_time = time.time()
    entry = {
        "payload": payload,
        "fetched_at": _utc_iso(fetched_wall_time),
        "fetched_wall_time": fetched_wall_time,
        "fetched_monotonic": time.monotonic(),
    }
    with _DEPLOYMENT_STATUS_CACHE_LOCK:
        _DEPLOYMENT_STATUS_CACHE = entry
        _DEPLOYMENT_STATUS_REFRESHING = False
        _DEPLOYMENT_STATUS_CACHE_LOCK.notify_all()
    return _build_response(entry, state="live")


@app.get("/api/bootstrap")
async def bootstrap_api():
    job_query = query_jobs(limit=50)
    jobs = job_query["jobs"]
    job_page = job_query["page"]
    model_catalog = get_model_catalog_options()
    return JSONResponse(
        {
            "summary": build_dashboard_stats(jobs),
            "job_page": job_page,
            "delivery_gaps": DELIVERY_GAPS,
            "server": {
                "alias": ServerConfig.alias,
                "host": ServerConfig.host,
                "user": ServerConfig.user,
                "port": ServerConfig.port,
                "remote_root": ServerConfig.remote_root,
            },
            "models": MODEL_OPTIONS,
            "model_catalog": model_catalog,
            "source_types": SOURCE_TYPE_OPTIONS,
            "advisor": advisor_status(),
            "jobPage": {
                "limit": job_page["limit"],
                "offset": job_page["offset"],
                "total": job_page["total"],
                "hasMore": job_page["has_more"],
                "sort": job_page["sort"],
            },
        }
    )


@app.get("/api/deployment/status")
async def deployment_status_api(refresh: bool = False):
    return JSONResponse(await asyncio.to_thread(load_deployment_status, force_refresh=refresh))


@app.get("/api/samples")
async def samples_api():
    manifest = load_samples_manifest()
    jobs = list_jobs(limit=200)
    return JSONResponse(
        {
            "manifest": manifest,
            "summary": build_sample_status_summary(manifest),
            "model_catalog": get_model_catalog_options(),
            "job_matrix": build_sample_job_matrix(manifest, jobs),
        }
    )


@app.get("/api/jobs/{job_id}/evaluation")
async def job_evaluation_api(job_id: str):
    try:
        load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc
    return JSONResponse(load_evaluation(job_id))


@app.post("/api/jobs/{job_id}/evaluation")
async def save_job_evaluation_api(job_id: str, request: Request):
    try:
        load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    try:
        payload = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"评分 JSON 解析失败：{exc.msg}") from exc

    saved = save_evaluation(job_id, _normalize_evaluation_payload(job_id, payload))
    return JSONResponse({"ok": True, "evaluation": saved, **_job_payload(load_job(job_id))})


@app.post("/api/jobs")
async def create_job_api(
    model: str = Form(...),
    source_type: str = Form(...),
    notes: str = Form(""),
    sample_id: str = Form(""),
    params: str = Form(""),
    image_size: int = Form(512),
    scene_graph: str = Form("complete"),
    niter: int = Form(300),
    lr: float = Form(0.01),
    batch_size: int = Form(1),
    max_points: int = Form(250000),
    match_viz_count: int = Form(50),
    fps: int = Form(0),
    num_frames: int = Form(24),
    not_batchify: str = Form("true"),
    real_time: str = Form("false"),
    window_wise: str = Form("false"),
    window_size: int = Form(100),
    window_overlap_ratio: float = Form(0.5),
    files: list[UploadFile] = File(default=[]),
):
    job = await _create_job_from_request(
        model=model,
        source_type=source_type,
        notes=notes,
        sample_id=sample_id,
        params=params,
        image_size=image_size,
        scene_graph=scene_graph,
        niter=niter,
        lr=lr,
        batch_size=batch_size,
        max_points=max_points,
        match_viz_count=match_viz_count,
        fps=fps,
        num_frames=num_frames,
        not_batchify=not_batchify,
        real_time=real_time,
        window_wise=window_wise,
        window_size=window_size,
        window_overlap_ratio=window_overlap_ratio,
        files=files,
    )
    return JSONResponse(_job_payload(job))


@app.post("/api/compare/batches")
async def create_compare_batch_api(
    models: str = Form(...),
    source_type: str = Form(...),
    notes: str = Form(""),
    sample_id: str = Form(""),
    auto_dispatch: bool = Form(False),
    params: str = Form(""),
    model_params: str = Form(""),
    image_size: int = Form(512),
    scene_graph: str = Form("complete"),
    niter: int = Form(300),
    lr: float = Form(0.01),
    batch_size: int = Form(1),
    max_points: int = Form(250000),
    match_viz_count: int = Form(50),
    fps: int = Form(0),
    num_frames: int = Form(24),
    not_batchify: str = Form("true"),
    real_time: str = Form("false"),
    window_wise: str = Form("false"),
    window_size: int = Form(100),
    window_overlap_ratio: float = Form(0.5),
    files: list[UploadFile] = File(default=[]),
):
    selected_models = _parse_model_selection(models)
    normalized_sample_id = sample_id.strip() or _new_compare_sample_id()
    base_params = _build_raw_job_params(
        params=params,
        image_size=image_size,
        scene_graph=scene_graph,
        niter=niter,
        lr=lr,
        batch_size=batch_size,
        max_points=max_points,
        match_viz_count=match_viz_count,
        fps=fps,
        num_frames=num_frames,
        not_batchify=not_batchify,
        real_time=real_time,
        window_wise=window_wise,
        window_size=window_size,
        window_overlap_ratio=window_overlap_ratio,
    )
    per_model_params = _parse_json_object(model_params, "model_params")

    validation_errors: list[str] = []
    for model in selected_models:
        errors = _validate_new_job_file_count(model, source_type, len(files))
        if errors:
            validation_errors.append(f"{model}: {'；'.join(errors)}")
    if validation_errors:
        raise HTTPException(status_code=400, detail="；".join(validation_errors))

    uploaded = await _uploaded_files_to_bytes(files)
    jobs = []
    for model in selected_models:
        model_override = per_model_params.get(model, {})
        if model_override and not isinstance(model_override, dict):
            raise HTTPException(status_code=400, detail=f"model_params.{model} 必须是 JSON object。")
        raw_params = {**base_params, **model_override}
        job = _create_job_from_uploaded_bytes(
            model=model,
            source_type=source_type,
            notes=notes,
            sample_id=normalized_sample_id,
            raw_params=raw_params,
            uploaded=uploaded,
        )
        jobs.append(job)

    dispatch_results = []
    if auto_dispatch:
        for job in jobs:
            _prepare_job_for_dispatch(job.job_id, "批量对比任务已创建，正在启动远端调度线程...")
            dispatch_results.append({"job_id": job.job_id, "model": job.model, "dispatched": True})

    refreshed_jobs = [load_job(job.job_id) for job in jobs]
    compare_packet = build_sample_compare_packet(normalized_sample_id)
    return JSONResponse(
        {
            "ok": True,
            "sampleId": normalized_sample_id,
            "sample_id": normalized_sample_id,
            "models": selected_models,
            "createdJobs": [_job_payload(job) for job in refreshed_jobs],
            "created_jobs": [_job_payload(job) for job in refreshed_jobs],
            "dispatchResults": dispatch_results,
            "dispatch_results": dispatch_results,
            "compare": compare_packet,
        }
    )


@app.get("/api/compare/samples/{sample_id}")
async def sample_compare_api(sample_id: str):
    return JSONResponse(build_sample_compare_packet(sample_id))


@app.get("/api/compare/samples/{sample_id}/report-markdown")
async def sample_compare_report_markdown_api(sample_id: str):
    packet = build_sample_compare_packet(sample_id)
    return PlainTextResponse(packet["reportMarkdown"], media_type="text/markdown; charset=utf-8")


@app.get("/api/advisor/status", tags=["AI 顾问"])
async def advisor_status_api():
    return JSONResponse(advisor_status())


@app.get("/api/advisor/providers")
async def advisor_providers_api():
    return JSONResponse(advisor_provider_options())


@app.get("/api/advisor/diagnostics")
async def advisor_diagnostics_api():
    return JSONResponse(advisor_diagnostics())


@app.get("/api/advisor/config")
async def advisor_config_api():
    return JSONResponse(advisor_config_public())


@app.post("/api/advisor/config")
async def advisor_config_save_api(request: Request):
    payload = await request.json()
    try:
        config = save_advisor_config(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"AI 配置保存失败：{exc}") from exc
    return JSONResponse(config)


@app.post("/api/advisor/test")
async def advisor_test_api():
    try:
        payload = test_advisor_connection()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/advisor/jobs/{job_id}/recommend")
async def advisor_recommend_params_api(job_id: str):
    try:
        payload = recommend_parameters(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}") from exc
    return JSONResponse(payload)


@app.get("/api/advisor/jobs/{job_id}/diagnose")
async def advisor_diagnose_api(job_id: str):
    try:
        payload = diagnose_failure(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}") from exc
    return JSONResponse(payload)


@app.post("/api/advisor/batch-evaluate")
async def advisor_batch_evaluate_api(request: Request):
    payload = await request.json()
    job_ids = payload.get("job_ids", [])
    if not job_ids:
        raise HTTPException(status_code=400, detail="job_ids 不能为空")
    try:
        result = batch_evaluate_jobs(job_ids)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


# ─────────────── 实验编排 API ───────────────

@app.get("/api/experiments/templates", tags=["实验编排"])
async def list_experiment_templates_api():
    """列出所有实验模板"""
    templates = list_experiment_templates()
    return JSONResponse({"templates": [t.to_dict() for t in templates]})


@app.get("/api/experiments/templates/{template_id}", tags=["实验编排"])
async def get_experiment_template_api(template_id: str):
    """获取实验模板详情"""
    template = get_experiment_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail=f"实验模板 {template_id} 不存在")
    return JSONResponse(template.to_dict())


@app.post("/api/experiments/templates", tags=["实验编排"])
async def create_experiment_template_api(request: Request):
    """创建实验模板"""
    payload = await request.json()
    try:
        template = create_experiment_template(
            name=payload.get("name", ""),
            description=payload.get("description", ""),
            model=payload.get("model", ""),
            source_type=payload.get("source_type", ""),
            base_params=payload.get("base_params", {}),
            param_grid=payload.get("param_grid", {}),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(template.to_dict())


@app.patch("/api/experiments/templates/{template_id}", tags=["实验编排"])
async def update_experiment_template_api(template_id: str, request: Request):
    """更新实验模板"""
    payload = await request.json()
    try:
        template = update_experiment_template(
            template_id=template_id,
            name=payload.get("name"),
            description=payload.get("description"),
            base_params=payload.get("base_params"),
            param_grid=payload.get("param_grid"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(template.to_dict())


@app.delete("/api/experiments/templates/{template_id}", tags=["实验编排"])
async def delete_experiment_template_api(template_id: str):
    """删除实验模板"""
    success = delete_experiment_template(template_id)
    if not success:
        raise HTTPException(status_code=404, detail="实验模板不存在")
    return JSONResponse({"ok": True})


@app.post("/api/experiments/templates/{template_id}/run", tags=["实验编排"])
async def run_experiment_api(template_id: str, request: Request):
    """从实验模板运行实验：按参数网格创建可派发任务，可选自动派发。"""
    payload = await request.json()
    source_job_id = payload.get("source_job_id") or payload.get("sourceJobId") or None
    auto_dispatch = bool(payload.get("auto_dispatch") or payload.get("autoDispatch"))
    files = [Path(item) for item in payload.get("files", []) if str(item).strip()]
    dispatch = None
    if auto_dispatch:
        def dispatch(job_id: str) -> None:  # noqa: E306 - local dispatcher reused per job
            _dispatch_job_for_api(job_id, "实验编排任务已派发，正在启动远端调度线程...")
    try:
        run = run_experiment_from_template(
            template_id=template_id,
            run_name=payload.get("run_name") or payload.get("runName") or "",
            files=files,
            source_job_id=source_job_id,
            notes=payload.get("notes", ""),
            auto_dispatch=auto_dispatch,
            dispatch=dispatch,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return JSONResponse(run.to_dict())


@app.get("/api/experiments/runs", tags=["实验编排"])
async def list_experiment_runs_api():
    """列出已记录的实验运行。"""
    return JSONResponse({"runs": [run.to_dict() for run in list_experiment_runs()]})


@app.get("/api/experiments/runs/{run_id}", tags=["实验编排"])
async def get_experiment_run_api(run_id: str):
    """获取单个实验运行记录及其任务摘要。"""
    run = get_experiment_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"实验运行 {run_id} 不存在")
    summary = get_experiment_run_summary(run.job_ids)
    return JSONResponse({**run.to_dict(), "summary": summary})


@app.post("/api/experiments/summary", tags=["实验编排"])
async def experiment_summary_api(request: Request):
    """获取实验运行摘要"""
    payload = await request.json()
    job_ids = payload.get("job_ids", [])
    summary = get_experiment_run_summary(job_ids)
    return JSONResponse(summary)


@app.post("/api/jobs/batch-dispatch")
async def batch_dispatch_api(payload: BatchJobsRequest):
    results = []
    for job_id in _normalize_batch_job_ids(payload.job_ids):
        try:
            job = _dispatch_job_for_api(job_id, "批量派发任务已接收，正在启动远端调度线程...")
            results.append(
                {
                    "job_id": job_id,
                    "success": True,
                    "job": _job_payload(job),
                    "list_item": _job_list_item(job),
                }
            )
        except HTTPException as exc:
            results.append({"job_id": job_id, "success": False, "status_code": exc.status_code, "error": exc.detail})
        except Exception as exc:
            results.append({"job_id": job_id, "success": False, "status_code": 500, "error": str(exc)})
    return JSONResponse({"ok": True, "results": results})


@app.post("/api/jobs/batch-cancel")
async def batch_cancel_api(payload: BatchJobsRequest):
    results = []
    for job_id in _normalize_batch_job_ids(payload.job_ids):
        try:
            job = _cancel_job_for_api(job_id)
            results.append(
                {
                    "job_id": job_id,
                    "success": True,
                    "job": _job_payload(job),
                    "list_item": _job_list_item(job),
                }
            )
        except HTTPException as exc:
            results.append({"job_id": job_id, "success": False, "status_code": exc.status_code, "error": exc.detail})
        except Exception as exc:
            results.append({"job_id": job_id, "success": False, "status_code": 500, "error": str(exc)})
    return JSONResponse({"ok": True, "results": results})


@app.post("/api/jobs/batch-delete")
async def batch_delete_api(payload: BatchJobsRequest):
    results = []
    for job_id in _normalize_batch_job_ids(payload.job_ids):
        try:
            job = load_job(job_id)
            if job.status == "running":
                raise HTTPException(status_code=400, detail=f"任务 {job_id} 正在运行，无法删除")
            job_dir = get_job_dir(job_id)
            if job_dir.exists():
                shutil.rmtree(job_dir)
            results.append({"job_id": job_id, "success": True})
        except HTTPException as exc:
            results.append({"job_id": job_id, "success": False, "status_code": exc.status_code, "error": exc.detail})
        except Exception as exc:
            results.append({"job_id": job_id, "success": False, "status_code": 500, "error": str(exc)})
    return JSONResponse({"ok": True, "results": results})


@app.post("/api/jobs/{job_id}/dispatch")
async def dispatch_job_api(job_id: str):
    try:
        job = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    _validate_dispatchable(job)
    _prepare_job_for_dispatch(job_id, "正在启动远端调度线程...")
    return JSONResponse({"ok": True, **_job_payload(load_job(job_id))})


@app.post("/api/jobs/{job_id}/retry")
async def retry_job_api(job_id: str):
    try:
        job = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    _validate_dispatchable(job)
    _prepare_job_for_dispatch(job_id, "正在重新启动远端调度线程...")
    return JSONResponse({"ok": True, **_job_payload(load_job(job_id))})


@app.post("/api/jobs/{job_id}/duplicate")
async def duplicate_job_api(job_id: str):
    try:
        new_job = duplicate_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    return JSONResponse({"ok": True, **_job_payload(load_job(new_job.job_id))})


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job_api(job_id: str):
    try:
        load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    cancel_remote_job(job_id)
    return JSONResponse({"ok": True, **_job_payload(load_job(job_id))})


@app.post("/api/jobs/{job_id}/advisor/evaluate")
async def advisor_evaluate_api(job_id: str):
    try:
        load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    try:
        evaluate_job_with_advisor(job_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return JSONResponse({"ok": True, **_job_payload(load_job(job_id))})


# ══════════════════════════════════════════════════════════════════
# Viser 4D 可视化（仅 monst3r 等动态重建模型）
# ══════════════════════════════════════════════════════════════════

def _job_or_404(job_id: str):
    try:
        return load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc


@app.get("/api/jobs/{job_id}/viser/status")
async def viser_status_api(job_id: str):
    _job_or_404(job_id)
    session = viser_manager.get(job_id)
    if session is None:
        return JSONResponse({"jobId": job_id, "status": "idle", "url": None})
    return JSONResponse(session.to_dict())


@app.post("/api/jobs/{job_id}/viser/start")
async def viser_start_api(job_id: str):
    job = _job_or_404(job_id)
    if job.model != "monst3r":
        raise HTTPException(status_code=400, detail=f"viser 当前仅支持 monst3r 任务，当前模型：{job.model}。")
    try:
        session = viser_manager.start(job_id, ServerConfig())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return JSONResponse(session.to_dict())


@app.post("/api/jobs/{job_id}/viser/stop")
async def viser_stop_api(job_id: str):
    _job_or_404(job_id)
    session = viser_manager.stop(job_id)
    if session is None:
        return JSONResponse({"jobId": job_id, "status": "idle", "url": None})
    return JSONResponse(session.to_dict())


# ══════════════════════════════════════════════════════════════════
# P1/P2: Scheduler, Resources, Metrics, Reports
# ══════════════════════════════════════════════════════════════════

@app.get("/api/scheduler/status")
async def scheduler_status_api():
    return JSONResponse(scheduler.status())


@app.post("/api/scheduler/config")
async def scheduler_config_api(max_concurrent: int = 2):
    if max_concurrent < 1 or max_concurrent > 10:
        raise HTTPException(status_code=400, detail="max_concurrent must be 1-10")
    scheduler.set_max_concurrent(max_concurrent)
    return JSONResponse({"ok": True, "max_concurrent": max_concurrent})


@app.post("/api/scheduler/enqueue/{job_id}")
async def scheduler_enqueue_api(job_id: str, priority: str = "normal"):
    try:
        load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc
    
    try:
        prio = JobPriority(priority)
    except ValueError:
        prio = JobPriority.NORMAL
    
    success = scheduler.enqueue(job_id, priority=prio)
    return JSONResponse({"ok": success, "job_id": job_id, "priority": prio.value})


@app.delete("/api/scheduler/dequeue/{job_id}")
async def scheduler_dequeue_api(job_id: str):
    success = scheduler.dequeue(job_id)
    return JSONResponse({"ok": success, "job_id": job_id})


@app.get("/api/system/resources")
async def system_resources_api():
    return JSONResponse(resource_monitor.get_dict())


@app.get("/api/jobs/{job_id}/metrics")
async def job_metrics_api(job_id: str):
    try:
        load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc
    
    job_dir = get_job_dir(job_id)
    metrics = compute_job_metrics(job_dir)
    return JSONResponse({"job_id": job_id, "metrics": metrics})


@app.get("/api/jobs/{job_id}/report")
async def job_report_api(job_id: str, format: str = "html"):
    try:
        job = load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc
    
    job_dir = get_job_dir(job_id)
    metrics = compute_job_metrics(job_dir)
    evaluation = load_evaluation(job_id)
    
    report = build_job_report(job.to_dict(), metrics, evaluation)
    
    if format == "json":
        return JSONResponse(report.to_dict())
    
    html_content = export_html(report)
    
    if format == "pdf":
        pdf_path = job_dir / f"report_{job_id}.pdf"
        if export_pdf(report, pdf_path):
            return FileResponse(pdf_path, filename=f"report_{job_id}.pdf", media_type="application/pdf")
        else:
            return PlainTextResponse(html_content, media_type="text/html")
    
    return PlainTextResponse(html_content, media_type="text/html")


@app.get("/api/compare/samples/{sample_id}/report")
async def compare_report_api(sample_id: str, format: str = "html"):
    jobs = [j for j in list_all_jobs() if j.sample_id == sample_id]
    if not jobs:
        raise HTTPException(status_code=404, detail=f"未找到样例 {sample_id} 的任务。")
    
    report = build_compare_report(sample_id, [j.to_dict() for j in jobs])
    
    if format == "json":
        return JSONResponse(report.to_dict())
    
    html_content = export_html(report)
    
    if format == "pdf":
        from pathlib import Path
        pdf_path = Path(f"compare_report_{sample_id}.pdf")
        if export_pdf(report, pdf_path):
            return FileResponse(pdf_path, filename=f"compare_report_{sample_id}.pdf", media_type="application/pdf")
    
    return PlainTextResponse(html_content, media_type="text/html")


@app.post("/api/jobs/{job_id}/visuals/generate")
async def generate_job_visuals_api(job_id: str):
    try:
        load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc
    
    job_dir = get_job_dir(job_id)
    results = generate_job_visuals(job_dir)
    return JSONResponse({"job_id": job_id, "visuals": results})


@app.get("/api/jobs/{job_id}/visuals/{filename}")
async def get_job_visual_api(job_id: str, filename: str):
    try:
        load_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"未找到任务 {job_id}。") from exc

    visual_path = get_job_dir(job_id) / "visuals" / filename
    if not visual_path.exists():
        raise HTTPException(status_code=404, detail=f"未找到可视化文件 {filename}。")

    media_type = "image/png" if filename.endswith(".png") else "image/gif"
    return FileResponse(visual_path, media_type=media_type)


# ══════════════════════════════════════════════════════════════════
# 存储管理 API
# ══════════════════════════════════════════════════════════════════

@app.get("/api/storage/stats")
async def storage_stats_api():
    stats = get_storage_stats()
    return JSONResponse({
        "totalBytes": stats.total_bytes,
        "usedBytes": stats.used_bytes,
        "freeBytes": stats.free_bytes,
        "usagePercent": round((stats.used_bytes / stats.total_bytes) * 100, 2) if stats.total_bytes > 0 else 0,
        "jobCount": stats.job_count,
        "byModel": {k: v for k, v in stats.by_model.items()},
        "byStatus": {k: v for k, v in stats.by_status.items()},
        "largestJobs": [{"jobId": j, "bytes": s} for j, s in stats.largest_jobs],
    })


@app.get("/api/storage/config")
async def storage_config_api():
    config = load_config()
    return JSONResponse(config.to_dict())


@app.post("/api/storage/config")
async def update_storage_config_api(request):
    try:
        data = await request.json()
        config = StorageConfig.from_dict(data)
        save_config(config)
        return JSONResponse({"ok": True, "config": config.to_dict()})
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"配置更新失败: {exc}") from exc


@app.post("/api/storage/clean")
async def storage_clean_api(dry_run: bool = False):
    candidates = evaluate_cleanup_rules()
    result = execute_cleanup(candidates, dry_run=dry_run)
    return JSONResponse({
        "deletedCount": result.deleted_count,
        "freedBytes": result.freed_bytes,
        "candidates": [
            {
                "jobId": c.job_id,
                "reason": c.reason,
                "sizeBytes": c.size_bytes,
                "ruleName": c.rule_name,
            }
            for c in result.candidates
        ],
        "errors": result.errors,
        "dryRun": dry_run,
    })


@app.post("/api/storage/auto-clean")
async def storage_auto_clean_api():
    result = auto_clean_if_needed()
    if result is None:
        return JSONResponse({"triggered": False, "reason": "配额未达到阈值或自动清理未启用"})
    return JSONResponse({
        "triggered": True,
        "deletedCount": result.deleted_count,
        "freedBytes": result.freed_bytes,
        "errors": result.errors,
    })


@app.get("/api/storage/trash")
async def storage_trash_list_api():
    items = list_trash_items()
    return JSONResponse({"items": items})


@app.post("/api/storage/trash/{job_id}/restore")
async def storage_trash_restore_api(job_id: str):
    success = restore_from_trash(job_id)
    if not success:
        raise HTTPException(status_code=400, detail=f"恢复失败：任务 {job_id} 不在回收站或目标位置已存在")
    return JSONResponse({"ok": True, "job_id": job_id})


@app.post("/api/storage/trash/empty")
async def storage_trash_empty_api():
    count = empty_trash()
    return JSONResponse({"ok": True, "deletedCount": count})


@app.post("/api/compare/samples/{sample_id}/visuals/generate")
async def generate_compare_visuals_api(sample_id: str):
    jobs = [j for j in list_all_jobs() if j.sample_id == sample_id]
    if not jobs:
        raise HTTPException(status_code=404, detail=f"未找到样例 {sample_id} 的任务。")
    
    job_dirs = [get_job_dir(j.job_id) for j in jobs]
    labels = [j.model for j in jobs]
    output_dir = Path(f"compare_visuals_{sample_id}")
    
    results = generate_compare_visuals(job_dirs, labels, output_dir)
    return JSONResponse({"sample_id": sample_id, "visuals": results})
