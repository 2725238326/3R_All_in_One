"""
实验编排模块
支持实验模板、参数网格搜索、自动化实验流程
"""
from __future__ import annotations

import itertools
import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from job_store import (
    create_job,
    get_job_dir,
    iter_input_items,
    list_all_jobs,
    load_job,
    save_inputs,
)
from model_contracts import build_job_params, param_family_for
from runtime_paths import data_root, local_jobs_dir

ROOT = data_root()
LOCAL_JOBS_DIR = local_jobs_dir()
EXPERIMENT_MANIFEST_PATH = LOCAL_JOBS_DIR / "experiment_manifest.json"
EXPERIMENT_RUNS_PATH = LOCAL_JOBS_DIR / "experiment_runs.json"
_EXPERIMENT_LOCK = threading.RLock()


@dataclass
class ExperimentTemplate:
    """实验模板定义"""
    id: str
    name: str
    description: str
    model: str
    source_type: str
    base_params: dict[str, Any]
    param_grid: dict[str, list[Any]]  # 参数网格：key -> [value1, value2, ...]
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "model": self.model,
            "source_type": self.source_type,
            "base_params": self.base_params,
            "param_grid": self.param_grid,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "metadata": self.metadata,
        }


@dataclass
class ExperimentRun:
    """实验运行记录"""
    id: str
    template_id: str
    name: str
    status: str  # pending, running, completed, failed, cancelled
    job_ids: list[str]
    created_at: str = ""
    started_at: str = ""
    completed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "templateId": self.template_id,
            "name": self.name,
            "status": self.status,
            "jobIds": self.job_ids,
            "createdAt": self.created_at,
            "startedAt": self.started_at,
            "completedAt": self.completed_at,
            "metadata": self.metadata,
        }


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _load_experiments() -> dict[str, ExperimentTemplate]:
    """加载实验模板"""
    if not EXPERIMENT_MANIFEST_PATH.exists():
        return {}
    with open(EXPERIMENT_MANIFEST_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {
        k: ExperimentTemplate(
            id=v["id"],
            name=v["name"],
            description=v["description"],
            model=v["model"],
            source_type=v["source_type"],
            base_params=v["base_params"],
            param_grid=v["param_grid"],
            created_at=v.get("createdAt", ""),
            updated_at=v.get("updatedAt", ""),
            metadata=v.get("metadata", {}),
        )
        for k, v in data.items()
    }


def _save_experiments(experiments: dict[str, ExperimentTemplate]) -> None:
    """保存实验模板"""
    EXPERIMENT_MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EXPERIMENT_MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump({k: v.to_dict() for k, v in experiments.items()}, f, indent=2, ensure_ascii=False)


def list_experiment_templates() -> list[ExperimentTemplate]:
    """列出所有实验模板"""
    with _EXPERIMENT_LOCK:
        experiments = _load_experiments()
        return list(experiments.values())


def get_experiment_template(template_id: str) -> ExperimentTemplate | None:
    """获取实验模板"""
    with _EXPERIMENT_LOCK:
        experiments = _load_experiments()
        return experiments.get(template_id)


def create_experiment_template(
    name: str,
    description: str,
    model: str,
    source_type: str,
    base_params: dict[str, Any],
    param_grid: dict[str, list[Any]],
) -> ExperimentTemplate:
    """创建实验模板"""
    with _EXPERIMENT_LOCK:
        experiments = _load_experiments()
        template_id = f"exp-{uuid.uuid4().hex[:8]}"
        now = _now_iso()
        template = ExperimentTemplate(
            id=template_id,
            name=name,
            description=description,
            model=model,
            source_type=source_type,
            base_params=base_params,
            param_grid=param_grid,
            created_at=now,
            updated_at=now,
        )
        experiments[template_id] = template
        _save_experiments(experiments)
        return template


def update_experiment_template(
    template_id: str,
    name: str | None = None,
    description: str | None = None,
    base_params: dict[str, Any] | None = None,
    param_grid: dict[str, list[Any]] | None = None,
) -> ExperimentTemplate:
    """更新实验模板"""
    with _EXPERIMENT_LOCK:
        experiments = _load_experiments()
        if template_id not in experiments:
            raise ValueError(f"实验模板 {template_id} 不存在")
        template = experiments[template_id]
        if name is not None:
            template.name = name
        if description is not None:
            template.description = description
        if base_params is not None:
            template.base_params = base_params
        if param_grid is not None:
            template.param_grid = param_grid
        template.updated_at = _now_iso()
        _save_experiments(experiments)
        return template


def delete_experiment_template(template_id: str) -> bool:
    """删除实验模板"""
    with _EXPERIMENT_LOCK:
        experiments = _load_experiments()
        if template_id not in experiments:
            return False
        del experiments[template_id]
        _save_experiments(experiments)
        return True


def generate_param_combinations(
    base_params: dict[str, Any],
    param_grid: dict[str, list[Any]],
) -> list[dict[str, Any]]:
    """生成参数组合（笛卡尔积）"""
    if not param_grid:
        return [base_params]
    
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = list(itertools.product(*values))
    
    result = []
    for combo in combinations:
        params = base_params.copy()
        for key, value in zip(keys, combo):
            params[key] = value
        result.append(params)
    
    return result


def _resolve_experiment_inputs(
    *,
    files: list[Path] | None = None,
    source_job_id: str | None = None,
) -> list[tuple[str, bytes]]:
    """Resolve the input payload shared by every job in an experiment run.

    Inputs come either from an existing job (reuse its uploaded files — the
    common case: sweep params over the same scene) or from explicit
    server-local file paths. Returns ``(original_name, bytes)`` tuples ready for
    ``save_inputs``."""
    uploaded: list[tuple[str, bytes]] = []
    if source_job_id:
        source = load_job(source_job_id)
        for item in iter_input_items(source):
            local_path = ROOT / item["relative_path"]
            if local_path.exists():
                uploaded.append((item["original_name"], local_path.read_bytes()))
        return uploaded
    for raw_path in files or []:
        path = Path(raw_path)
        if path.exists() and path.is_file():
            uploaded.append((path.name, path.read_bytes()))
    return uploaded


def run_experiment_from_template(
    template_id: str,
    run_name: str,
    *,
    files: list[Path] | None = None,
    source_job_id: str | None = None,
    notes: str = "",
    auto_dispatch: bool = False,
    dispatch: Callable[[str], None] | None = None,
) -> ExperimentRun:
    """Create one runnable job per parameter combination and optionally dispatch.

    Replaces the previous broken implementation that called
    ``create_job(files=...)`` (no such argument), treated the returned
    ``JobRecord`` as a job id, never attached inputs, and never dispatched."""
    with _EXPERIMENT_LOCK:
        experiments = _load_experiments()
        if template_id not in experiments:
            raise ValueError(f"实验模板 {template_id} 不存在")
        template = experiments[template_id]

    param_combinations = generate_param_combinations(template.base_params, template.param_grid)
    uploaded = _resolve_experiment_inputs(files=files, source_job_id=source_job_id)

    job_ids: list[str] = []
    for index, raw_params in enumerate(param_combinations):
        # Normalize/clamp each combination through the same contract the UI uses
        # so experiment jobs carry valid, dispatch-ready params.
        params = build_job_params(template.model, raw_params)
        suffix = f" - {notes}" if notes else ""
        job = create_job(
            model=template.model,
            source_type=template.source_type,
            notes=f"{run_name} - 组合 {index + 1}/{len(param_combinations)}{suffix}",
            params=params,
        )
        if uploaded:
            save_inputs(job, uploaded)
        job_ids.append(job.job_id)

    dispatched = 0
    if auto_dispatch and dispatch is not None:
        for job_id in job_ids:
            try:
                dispatch(job_id)
                dispatched += 1
            except Exception:  # noqa: BLE001 - one undispatchable job must not abort the run
                pass

    run_id = f"run-{uuid.uuid4().hex[:8]}"
    now = _now_iso()
    run = ExperimentRun(
        id=run_id,
        template_id=template_id,
        name=run_name,
        status="running" if dispatched else "pending",
        job_ids=job_ids,
        created_at=now,
        started_at=now if dispatched else "",
        metadata={
            "model": template.model,
            "combination_count": len(param_combinations),
            "input_count": len(uploaded),
            "dispatched": dispatched,
            "source_job_id": source_job_id or "",
        },
    )
    _persist_run(run)
    return run


def _load_runs() -> dict[str, ExperimentRun]:
    if not EXPERIMENT_RUNS_PATH.exists():
        return {}
    try:
        data = json.loads(EXPERIMENT_RUNS_PATH.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    runs: dict[str, ExperimentRun] = {}
    for key, value in data.items():
        runs[key] = ExperimentRun(
            id=value["id"],
            template_id=value.get("templateId", ""),
            name=value.get("name", ""),
            status=value.get("status", "pending"),
            job_ids=value.get("jobIds", []),
            created_at=value.get("createdAt", ""),
            started_at=value.get("startedAt", ""),
            completed_at=value.get("completedAt", ""),
            metadata=value.get("metadata", {}),
        )
    return runs


def _save_runs(runs: dict[str, ExperimentRun]) -> None:
    EXPERIMENT_RUNS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {key: run.to_dict() for key, run in runs.items()}
    EXPERIMENT_RUNS_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _persist_run(run: ExperimentRun) -> None:
    with _EXPERIMENT_LOCK:
        runs = _load_runs()
        runs[run.id] = run
        _save_runs(runs)


def list_experiment_runs() -> list[ExperimentRun]:
    with _EXPERIMENT_LOCK:
        return sorted(_load_runs().values(), key=lambda run: run.created_at, reverse=True)


def get_experiment_run(run_id: str) -> ExperimentRun | None:
    with _EXPERIMENT_LOCK:
        return _load_runs().get(run_id)


def get_experiment_run_summary(job_ids: list[str]) -> dict[str, Any]:
    """获取实验运行摘要"""
    jobs = [j for j in list_all_jobs() if j.job_id in job_ids]
    
    summary = {
        "total": len(job_ids),
        "pending": 0,
        "running": 0,
        "finished": 0,
        "failed": 0,
        "cancelled": 0,
        "jobs": [],
    }
    
    for job in jobs:
        summary[job.status] = summary.get(job.status, 0) + 1
        summary["jobs"].append({
            "job_id": job.job_id,
            "status": job.status,
            "model": job.model,
            "params": job.params,
        })
    
    return summary
