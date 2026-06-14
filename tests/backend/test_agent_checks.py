# ═══════════════════════════════════════════════════════════════
# Agent Check Endpoints Tests — smoke / health / doctor / batch
# ═══════════════════════════════════════════════════════════════
"""
These tests exercise the async agent check API added to backend/app.py:
- POST /api/agent/smoke/{model}
- POST /api/agent/health/{model}
- POST /api/agent/smoke-batch
- GET  /api/agent/checks, GET /api/agent/checks/{task_id}

The real smoke/health helpers shell out over SSH to a GPU server, so they are
mocked at their source module. ``_agent_check_modules`` re-imports the helpers
on every call, so patching ``agent.smoke_runner.*`` / ``agent.env_builder.*``
is picked up by the request handler that captures them into the work closure.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent.env_builder import BuildResult  # noqa: E402
from agent.smoke_runner import SmokeReport  # noqa: E402


def _poll_task(client: TestClient, task_id: str, timeout: float = 10.0) -> dict:
    """Poll a check task until it reaches a terminal state."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        response = client.get(f"/api/agent/checks/{task_id}")
        assert response.status_code == 200
        last = response.json()
        if last["status"] in ("finished", "failed"):
            return last
        time.sleep(0.05)
    raise AssertionError(f"task {task_id} did not finish in {timeout}s (last={last})")


class TestAgentSmokeEndpoint:
    def test_smoke_success(self, test_client: TestClient):
        ready = SmokeReport(
            model="MonST3R", env_exists=True, checkpoints_ok=True, smoke_ok=True, smoke_output="OK"
        )
        with patch("agent.smoke_runner.smoke_check_model", return_value=ready):
            response = test_client.post("/api/agent/smoke/monst3r")
            assert response.status_code == 202
            task = response.json()
            assert task["kind"] == "smoke"
            assert task["status"] in ("queued", "running", "finished")
            finished = _poll_task(test_client, task["taskId"])

        assert finished["status"] == "finished"
        assert finished["result"]["ready"] is True
        assert finished["result"]["model"] == "MonST3R"
        assert finished["error"] is None

    def test_smoke_not_ready_is_reported(self, test_client: TestClient):
        blocked = SmokeReport(
            model="MonST3R", env_exists=True, checkpoints_ok=False,
            missing_checkpoints=["weights.pth"], smoke_ok=False, error="Missing checkpoints: weights.pth",
        )
        with patch("agent.smoke_runner.smoke_check_model", return_value=blocked):
            response = test_client.post("/api/agent/smoke/monst3r")
            task = response.json()
            finished = _poll_task(test_client, task["taskId"])

        assert finished["status"] == "finished"  # the check ran; the model is simply not ready
        assert finished["result"]["ready"] is False
        assert finished["result"]["missing_checkpoints"] == ["weights.pth"]

    def test_smoke_exception_marks_task_failed(self, test_client: TestClient):
        with patch("agent.smoke_runner.smoke_check_model", side_effect=RuntimeError("ssh down")):
            response = test_client.post("/api/agent/smoke/monst3r")
            task = response.json()
            finished = _poll_task(test_client, task["taskId"])

        assert finished["status"] == "failed"
        assert "ssh down" in finished["error"]

    def test_smoke_unknown_model_404(self, test_client: TestClient):
        response = test_client.post("/api/agent/smoke/not_a_model")
        assert response.status_code == 404


class TestAgentHealthEndpoint:
    def test_health_with_diagnosis(self, test_client: TestClient):
        results = [
            BuildResult(model="MonST3R", step="health:import torch", success=True, output="OK"),
            BuildResult(model="MonST3R", step="health:cuda", success=True, output="True"),
        ]
        with patch("agent.env_builder.run_health_checks", return_value=results):
            response = test_client.post("/api/agent/health/monst3r")
            assert response.status_code == 202
            task = response.json()
            assert task["kind"] == "health"
            finished = _poll_task(test_client, task["taskId"])

        assert finished["status"] == "finished"
        assert finished["result"]["all_passed"] is True
        assert finished["result"]["diagnosis"]["overall_status"] == "healthy"
        assert len(finished["result"]["checks"]) == 2

    def test_health_failure_produces_diagnosis_items(self, test_client: TestClient):
        results = [
            BuildResult(
                model="MonST3R", step="health:curope", success=False,
                error="cannot find curope .so; recompile",
            ),
        ]
        with patch("agent.env_builder.run_health_checks", return_value=results):
            response = test_client.post("/api/agent/health/monst3r")
            task = response.json()
            finished = _poll_task(test_client, task["taskId"])

        assert finished["status"] == "finished"
        assert finished["result"]["all_passed"] is False
        diagnosis = finished["result"]["diagnosis"]
        assert diagnosis["overall_status"] != "healthy"
        assert len(diagnosis["items"]) >= 1


class TestAgentSmokeBatchEndpoint:
    def test_smoke_batch_all(self, test_client: TestClient):
        def _fake(ssh, spec):
            return SmokeReport(
                model=spec.name, env_exists=True, checkpoints_ok=True, smoke_ok=True, smoke_output="OK"
            )

        with patch("agent.smoke_runner.smoke_check_model", side_effect=_fake):
            response = test_client.post("/api/agent/smoke-batch", json={})
            assert response.status_code == 202
            task = response.json()
            assert task["kind"] == "smoke-batch"
            assert task["label"] == "all"
            finished = _poll_task(test_client, task["taskId"], timeout=15.0)

        result = finished["result"]
        assert result["total"] == 8
        assert result["ready"] == 8
        assert result["not_ready"] == 0

    def test_smoke_batch_selected(self, test_client: TestClient):
        def _fake(ssh, spec):
            return SmokeReport(model=spec.name, env_exists=True, checkpoints_ok=True, smoke_ok=True)

        with patch("agent.smoke_runner.smoke_check_model", side_effect=_fake):
            response = test_client.post("/api/agent/smoke-batch", json={"models": ["monst3r", "dust3r"]})
            assert response.status_code == 202
            task = response.json()
            assert task["label"] == "selected"
            finished = _poll_task(test_client, task["taskId"])

        assert finished["result"]["total"] == 2

    def test_smoke_batch_unknown_model_404(self, test_client: TestClient):
        response = test_client.post("/api/agent/smoke-batch", json={"models": ["monst3r", "ghost"]})
        assert response.status_code == 404


class TestAgentCheckTaskQuery:
    def test_unknown_task_404(self, test_client: TestClient):
        response = test_client.get("/api/agent/checks/agent-smoke-none-deadbeef")
        assert response.status_code == 404

    def test_checks_list_includes_started_task(self, test_client: TestClient):
        ready = SmokeReport(model="DUSt3R", env_exists=True, checkpoints_ok=True, smoke_ok=True)
        with patch("agent.smoke_runner.smoke_check_model", return_value=ready):
            response = test_client.post("/api/agent/smoke/dust3r")
            task_id = response.json()["taskId"]
            _poll_task(test_client, task_id)

        listing = test_client.get("/api/agent/checks")
        assert listing.status_code == 200
        task_ids = {task["taskId"] for task in listing.json()["tasks"]}
        assert task_id in task_ids
