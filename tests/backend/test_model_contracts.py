# ═══════════════════════════════════════════════════════════════
# Output contract check tests
# ═══════════════════════════════════════════════════════════════
"""Covers backend/model_contracts.check_output_contract and the
GET /api/jobs/{job_id}/contract-check endpoint."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
for _p in (str(ROOT), str(BACKEND_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from model_contracts import check_output_contract, model_contract_for, validate_create_request  # noqa: E402


class TestCheckOutputContract:
    def test_dust3r_satisfied(self):
        outputs = [
            "local_jobs/20260609-1/output/matches.png",
            "local_jobs/20260609-1/output/pointcloud.ply",
            "local_jobs/20260609-1/output/scene_meta.json",
        ]
        report = check_output_contract("dust3r", outputs)
        assert report["ok"] is True
        assert report["missing_files"] == []
        assert "output/pointcloud.ply" in report["satisfied_files"]
        assert report["scene_meta_present"] is True

    def test_dust3r_missing_pointcloud(self):
        outputs = ["local_jobs/20260609-1/output/matches.png"]
        report = check_output_contract("dust3r", outputs)
        assert report["ok"] is False
        assert "output/pointcloud.ply" in report["missing_files"]

    def test_windows_backslash_paths_normalized(self):
        outputs = [
            "local_jobs\\j\\output\\matches.png",
            "local_jobs\\j\\output\\pointcloud.ply",
        ]
        report = check_output_contract("dust3r", outputs)
        assert report["ok"] is True

    def test_monst3r_bundle_requires_scene_meta(self):
        ok_report = check_output_contract("monst3r", ["local_jobs/j/output/scene_meta.json"])
        assert ok_report["ok"] is True
        assert ok_report["download_mode"] == "remote_tree_bundle"

        missing_report = check_output_contract("monst3r", ["local_jobs/j/output/scene.glb"])
        assert missing_report["ok"] is False
        assert "output/scene_meta.json" in missing_report["missing_files"]

    def test_unknown_model_has_no_required_files(self):
        report = check_output_contract("pi3x", [])
        assert report["ok"] is True
        assert report["required_files"] == []

    def test_dream3r_contract_and_create_validation(self):
        contract = model_contract_for("dream3r")
        assert contract["runnable"] is True
        assert contract["paramFamily"] == "proposal_fusion"
        assert contract["sourceTypes"] == ["proposal_cache"]
        assert contract["minimumInputs"]["proposal_cache"] == 0

        assert validate_create_request("dream3r", "proposal_cache", 0) == []

        report = check_output_contract(
            "dream3r",
            [
                "local_jobs/j/output/scene_meta.json",
                "local_jobs/j/output/dream3r_report.json",
            ],
        )
        assert report["ok"] is True
        assert report["download_mode"] == "remote_tree_bundle"


class TestContractCheckEndpoint:
    def test_contract_check_endpoint(self, test_client: TestClient):
        import job_store

        job = job_store.create_job(model="dust3r", source_type="images", notes="contract test")
        job_id = job.job_id
        # Simulate a finished job whose outputs satisfy the contract.
        job_store.update_job(
            job_id,
            output_files=[
                f"local_jobs/{job_id}/output/matches.png",
                f"local_jobs/{job_id}/output/pointcloud.ply",
            ],
        )
        try:
            response = test_client.get(f"/api/jobs/{job_id}/contract-check")
            assert response.status_code == 200
            check = response.json()["contractCheck"]
            assert check["ok"] is True
            assert check["model"] == "dust3r"
        finally:
            shutil.rmtree(job_store.get_job_dir(job_id), ignore_errors=True)

    def test_contract_check_unknown_job_404(self, test_client: TestClient):
        assert test_client.get("/api/jobs/none-xyz/contract-check").status_code == 404
