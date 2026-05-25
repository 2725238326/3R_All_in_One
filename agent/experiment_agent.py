"""
Experiment Agent - 批量实验编排与自动收集
"""
from __future__ import annotations

import itertools
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

from .env_builder import ModelSpec, SSHConfig, load_all_specs, run_ssh_command

LOGGER = logging.getLogger("agent.experiment")


@dataclass
class ExperimentConfig:
    """实验配置"""
    name: str
    description: str = ""
    models: list[str] = field(default_factory=list)
    sample_ids: list[str] = field(default_factory=list)
    param_grid: dict[str, list[Any]] = field(default_factory=dict)
    repeat: int = 1
    priority: str = "normal"


@dataclass
class ExperimentJob:
    """单个实验任务"""
    experiment_name: str
    model: str
    sample_id: str
    params: dict
    job_id: str = ""
    status: str = "pending"
    result: Optional[dict] = None


@dataclass
class ExperimentResult:
    """实验结果汇总"""
    experiment_name: str
    total_jobs: int
    completed: int
    failed: int
    jobs: list[ExperimentJob] = field(default_factory=list)
    started_at: float = 0
    finished_at: float = 0

    @property
    def success_rate(self) -> float:
        if self.total_jobs == 0:
            return 0
        return self.completed / self.total_jobs

    @property
    def duration_sec(self) -> float:
        return self.finished_at - self.started_at


def generate_param_combinations(param_grid: dict[str, list]) -> list[dict]:
    """Generate all parameter combinations from a grid."""
    if not param_grid:
        return [{}]

    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = []

    for combo in itertools.product(*values):
        combinations.append(dict(zip(keys, combo)))

    return combinations


def plan_experiment(
    config: ExperimentConfig,
    specs_dir: Path,
) -> list[ExperimentJob]:
    """Plan experiment jobs from config."""
    specs = {s.name.lower(): s for s in load_all_specs(specs_dir)}
    param_combos = generate_param_combinations(config.param_grid)

    jobs = []
    for model_name in config.models:
        spec = specs.get(model_name.lower())
        if not spec:
            LOGGER.warning(f"Model spec not found: {model_name}")
            continue

        for sample_id in config.sample_ids:
            for params in param_combos:
                # Merge default params with experiment params
                merged_params = {**spec.runner.get("default_params", {}), **params}

                for repeat_idx in range(config.repeat):
                    jobs.append(ExperimentJob(
                        experiment_name=config.name,
                        model=model_name,
                        sample_id=sample_id,
                        params=merged_params,
                    ))

    LOGGER.info(
        f"Experiment '{config.name}': {len(jobs)} jobs planned "
        f"({len(config.models)} models × {len(config.sample_ids)} samples × "
        f"{len(param_combos)} param combos × {config.repeat} repeats)"
    )
    return jobs


def dispatch_experiment_job(
    job: ExperimentJob,
    api_base: str = "http://127.0.0.1:8765",
) -> bool:
    """Dispatch a single experiment job to the backend."""
    import urllib.request

    payload = json.dumps({
        "model": job.model,
        "sample_id": job.sample_id,
        "params": job.params,
        "priority": "normal",
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{api_base}/api/jobs",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            job.job_id = data.get("job_id", "")
            job.status = "dispatched"
            return True
    except Exception as e:
        LOGGER.error(f"Failed to dispatch job: {e}")
        job.status = "dispatch_failed"
        return False


def run_experiment(
    config: ExperimentConfig,
    specs_dir: Path,
    api_base: str = "http://127.0.0.1:8765",
    poll_interval: float = 10.0,
    timeout: float = 3600.0,
) -> ExperimentResult:
    """Run a complete experiment: plan → dispatch → collect."""
    result = ExperimentResult(
        experiment_name=config.name,
        total_jobs=0,
        completed=0,
        failed=0,
        started_at=time.time(),
    )

    # Plan
    jobs = plan_experiment(config, specs_dir)
    result.total_jobs = len(jobs)
    result.jobs = jobs

    if not jobs:
        result.finished_at = time.time()
        return result

    # Dispatch
    for job in jobs:
        dispatch_experiment_job(job, api_base)

    # Collect (poll until all done or timeout)
    start = time.time()
    while time.time() - start < timeout:
        pending = [j for j in jobs if j.status in ("dispatched", "running")]
        if not pending:
            break

        for job in pending:
            if not job.job_id:
                continue
            try:
                import urllib.request
                with urllib.request.urlopen(
                    f"{api_base}/api/jobs/{job.job_id}", timeout=10
                ) as resp:
                    data = json.loads(resp.read())
                    status = data.get("status", "unknown")
                    if status in ("finished", "completed"):
                        job.status = "completed"
                        job.result = data
                    elif status in ("failed", "error"):
                        job.status = "failed"
                        job.result = data
                    else:
                        job.status = "running"
            except Exception:
                pass

        time.sleep(poll_interval)

    # Summarize
    result.completed = sum(1 for j in jobs if j.status == "completed")
    result.failed = sum(1 for j in jobs if j.status == "failed")
    result.finished_at = time.time()

    LOGGER.info(
        f"Experiment '{config.name}' finished: "
        f"{result.completed}/{result.total_jobs} completed, "
        f"{result.failed} failed, {result.duration_sec:.1f}s"
    )
    return result


def load_experiment_config(path: Path) -> ExperimentConfig:
    """Load experiment config from YAML."""
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return ExperimentConfig(**data)
