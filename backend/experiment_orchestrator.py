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
from typing import Any

from job_store import create_job, get_job_dir, list_all_jobs
from model_contracts import build_job_params, param_family_for
from runtime_paths import data_root, local_jobs_dir

ROOT = data_root()
LOCAL_JOBS_DIR = local_jobs_dir()
EXPERIMENT_MANIFEST_PATH = LOCAL_JOBS_DIR / "experiment_manifest.json"
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


def run_experiment_from_template(
    template_id: str,
    run_name: str,
    files: list[Path],
    notes: str = "",
) -> ExperimentRun:
    """从实验模板运行实验"""
    with _EXPERIMENT_LOCK:
        experiments = _load_experiments()
        if template_id not in experiments:
            raise ValueError(f"实验模板 {template_id} 不存在")
        template = experiments[template_id]
    
    # 生成参数组合
    param_combinations = generate_param_combinations(template.base_params, template.param_grid)
    
    # 创建任务
    job_ids = []
    for i, params in enumerate(param_combinations):
        job_id = create_job(
            model=template.model,
            source_type=template.source_type,
            files=files,
            params=params,
            notes=f"{run_name} - 组合 {i+1}/{len(param_combinations)} - {notes}",
        )
        job_ids.append(job_id)
    
    # 创建实验运行记录
    run_id = f"run-{uuid.uuid4().hex[:8]}"
    now = _now_iso()
    run = ExperimentRun(
        id=run_id,
        template_id=template_id,
        name=run_name,
        status="pending",
        job_ids=job_ids,
        created_at=now,
    )
    
    return run


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
