"""
Smoke Runner - 自动验证模型环境就绪状态
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .env_builder import (
    BuildResult,
    ModelSpec,
    SSHConfig,
    check_checkpoint_exists,
    check_env_exists,
    load_all_specs,
    run_smoke_test,
    run_ssh_command,
)

LOGGER = logging.getLogger("agent.smoke")


@dataclass
class SmokeReport:
    model: str
    env_exists: bool = False
    checkpoints_ok: bool = False
    missing_checkpoints: list[str] = field(default_factory=list)
    import_ok: bool = False
    smoke_ok: bool = False
    smoke_output: str = ""
    error: str = ""
    duration_sec: float = 0

    @property
    def ready(self) -> bool:
        return self.env_exists and self.checkpoints_ok and self.smoke_ok

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "ready": self.ready,
            "env_exists": self.env_exists,
            "checkpoints_ok": self.checkpoints_ok,
            "missing_checkpoints": self.missing_checkpoints,
            "smoke_ok": self.smoke_ok,
            "smoke_output": self.smoke_output,
            "error": self.error,
            "duration_sec": round(self.duration_sec, 1),
        }


def smoke_check_model(ssh: SSHConfig, spec: ModelSpec) -> SmokeReport:
    """Run full smoke check for a single model."""
    LOGGER.info(f"Smoke checking {spec.name}...")
    start = time.time()
    report = SmokeReport(model=spec.name)

    # 1. Check conda env
    env_name = spec.environment.get("conda_env", "")
    if env_name:
        report.env_exists = check_env_exists(ssh, env_name)
        if not report.env_exists:
            report.error = f"Conda env '{env_name}' not found"
            report.duration_sec = time.time() - start
            return report

    # 2. Check checkpoints
    repo_path = spec.repo.get("server_path", "")
    missing = []
    for ckpt in spec.checkpoints:
        if not check_checkpoint_exists(ssh, repo_path, ckpt):
            missing.append(ckpt["name"])

    report.missing_checkpoints = missing
    report.checkpoints_ok = len(missing) == 0

    if not report.checkpoints_ok:
        report.error = f"Missing checkpoints: {', '.join(missing)}"
        report.duration_sec = time.time() - start
        return report

    # 3. Run smoke test
    smoke_result = run_smoke_test(ssh, spec)
    report.smoke_ok = smoke_result.success
    report.smoke_output = smoke_result.output
    if not smoke_result.success:
        report.error = smoke_result.error or "Smoke test failed"

    report.duration_sec = time.time() - start
    LOGGER.info(
        f"  {spec.name}: {'READY' if report.ready else 'NOT READY'} "
        f"({report.duration_sec:.1f}s)"
    )
    return report


def smoke_check_all(
    ssh: SSHConfig,
    specs_dir: Path,
    filter_models: Optional[list[str]] = None,
) -> list[SmokeReport]:
    """Smoke check all models (or filtered subset)."""
    specs = load_all_specs(specs_dir)

    if filter_models:
        names_lower = [m.lower() for m in filter_models]
        specs = [s for s in specs if s.name.lower() in names_lower]

    reports = []
    for spec in specs:
        report = smoke_check_model(ssh, spec)
        reports.append(report)

    ready_count = sum(1 for r in reports if r.ready)
    LOGGER.info(
        f"Smoke check complete: {ready_count}/{len(reports)} models ready"
    )
    return reports


def smoke_check_summary(reports: list[SmokeReport]) -> dict:
    """Generate summary from smoke check reports."""
    return {
        "total": len(reports),
        "ready": sum(1 for r in reports if r.ready),
        "not_ready": sum(1 for r in reports if not r.ready),
        "models": {r.model: r.to_dict() for r in reports},
        "ready_models": [r.model for r in reports if r.ready],
        "blocked_models": [
            {"model": r.model, "reason": r.error}
            for r in reports if not r.ready
        ],
    }
