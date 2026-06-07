# ═══════════════════════════════════════════════════════════════
# Agent CLI Tests — 命令行入口测试
# ═══════════════════════════════════════════════════════════════

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _args(model: str = "dust3r") -> argparse.Namespace:
    return argparse.Namespace(model=model, host=None, user=None, alias="KYKT-UI")


def test_cmd_smoke_uses_ready_field(monkeypatch, capsys):
    from agent.cli import cmd_smoke
    from agent.env_builder import ModelSpec
    from agent.smoke_runner import SmokeReport
    import agent.registry
    import agent.smoke_runner

    spec = ModelSpec(
        name="DUSt3R",
        key="dust3r",
        family="dust3r",
        version="test",
        paper={},
        tags={},
        repo={},
        environment={"conda_env": "dust3r"},
        checkpoints=[],
        build_steps=[],
        resources={},
        health_checks=[],
        smoke_test={},
        runner={},
        output_contract={},
        known_issues=[],
        compatibility={},
    )

    class FakeRegistry:
        def get(self, model: str):
            return spec if model == "dust3r" else None

    monkeypatch.setattr(agent.registry, "ModelRegistry", FakeRegistry)
    monkeypatch.setattr(
        agent.smoke_runner,
        "smoke_check_model",
        lambda ssh, model_spec: SmokeReport(
            model=model_spec.name,
            env_exists=True,
            checkpoints_ok=True,
            smoke_ok=True,
            smoke_output="OK",
            duration_sec=0.2,
        ),
    )

    assert cmd_smoke(_args()) == 0
    output = capsys.readouterr().out
    assert "[OK] PASSED: DUSt3R" in output
    assert "Output: OK" in output


def test_cmd_smoke_returns_failure_for_not_ready(monkeypatch, capsys):
    from agent.cli import cmd_smoke
    from agent.env_builder import ModelSpec
    from agent.smoke_runner import SmokeReport
    import agent.registry
    import agent.smoke_runner

    spec = ModelSpec(
        name="DUSt3R",
        key="dust3r",
        family="dust3r",
        version="test",
        paper={},
        tags={},
        repo={},
        environment={"conda_env": "dust3r"},
        checkpoints=[],
        build_steps=[],
        resources={},
        health_checks=[],
        smoke_test={},
        runner={},
        output_contract={},
        known_issues=[],
        compatibility={},
    )

    class FakeRegistry:
        def get(self, model: str):
            return spec

    monkeypatch.setattr(agent.registry, "ModelRegistry", FakeRegistry)
    monkeypatch.setattr(
        agent.smoke_runner,
        "smoke_check_model",
        lambda ssh, model_spec: SmokeReport(
            model=model_spec.name,
            env_exists=True,
            checkpoints_ok=True,
            smoke_ok=False,
            error="Smoke test failed",
            duration_sec=0.2,
        ),
    )

    assert cmd_smoke(_args()) == 1
    output = capsys.readouterr().out
    assert "[FAIL] FAILED: DUSt3R" in output
    assert "Smoke test failed" in output
