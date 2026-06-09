# ═══════════════════════════════════════════════════════════════
# Experiment Record Bundle Tests
# ═══════════════════════════════════════════════════════════════
"""Covers backend/experiment_record.py (pure manifest + markdown + zip) and the
GET /api/agent/experiment-record/{job_id} endpoints."""
from __future__ import annotations

import io
import shutil
import sys
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
for _p in (str(ROOT), str(BACKEND_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from experiment_record import (  # noqa: E402
    build_experiment_record,
    build_experiment_record_bundle,
    render_record_markdown,
)


def _sample_job() -> dict:
    return {
        "job_id": "20260609-120000",
        "model": "monst3r",
        "source_type": "video",
        "status": "finished",
        "created_at": "2026-06-09T12:00:00",
        "notes": "demo run",
        "sample_id": None,
        "params": {"image_size": 512, "num_frames": 24},
        "input_files": ["local_jobs/x/input/input_01.mp4"],
        "output_files": ["local_jobs/x/output/scene.glb", "local_jobs/x/output/scene_meta.json"],
    }


def _sample_blueprint() -> dict:
    return {
        "version": "po-ta-s-w",
        "environment": {"conda_env": "monst3r", "python": "3.11", "torch": "2.5.1+cu121", "cuda_toolkit": "/usr/local/cuda-12.6"},
        "repo": {"url": "https://github.com/Junyi42/monst3r", "branch": "main", "server_path": "/hdd3/kykt26/code/monst3r"},
        "runner": {"script": "runners/monst3r_runner.py", "conda_env": "monst3r"},
        "checkpoints": [{"name": "MonST3R_PO-TA-S-W.pth", "path": "checkpoints/"}],
        "build_steps": [{"name": "compile curope", "cmd": "python setup.py build_ext --inplace"}],
        "smoke_test": {"script": "python -c 'import torch'", "expected": "OK"},
    }


def _sample_contract() -> dict:
    return {
        "runnerStatus": "validated_standard_sample",
        "runner": {"downloadMode": "remote_tree_bundle"},
        "resultContract": {"requiredFiles": ["output/scene_meta.json"], "optionalFiles": []},
    }


class TestBuildExperimentRecord:
    def test_reproduce_block_pulls_from_blueprint(self):
        record = build_experiment_record(
            job=_sample_job(),
            blueprint=_sample_blueprint(),
            contract=_sample_contract(),
            generated_at="2026-06-09T13:00:00",
        )
        assert record["schema_version"] == 1
        repro = record["reproduce"]
        assert repro["model"] == "monst3r"
        assert repro["conda_env"] == "monst3r"
        assert repro["torch"] == "2.5.1+cu121"
        assert repro["repo_commit"] == "po-ta-s-w"
        assert repro["runner_script"] == "runners/monst3r_runner.py"
        assert repro["params"] == {"image_size": 512, "num_frames": 24}
        assert len(repro["checkpoints"]) == 1
        assert len(repro["build_steps"]) == 1

    def test_job_and_contract_blocks(self):
        record = build_experiment_record(job=_sample_job(), contract=_sample_contract())
        assert record["job"]["job_id"] == "20260609-120000"
        assert record["job"]["input_count"] == 1
        assert record["job"]["output_count"] == 2
        assert record["contract"]["download_mode"] == "remote_tree_bundle"
        assert record["contract"]["required_files"] == ["output/scene_meta.json"]

    def test_tolerates_missing_blueprint_and_contract(self):
        record = build_experiment_record(job=_sample_job())
        assert record["reproduce"]["model"] == "monst3r"
        assert record["reproduce"]["conda_env"] is None
        assert record["contract"]["required_files"] == []

    def test_result_block_uses_summary_and_scene_meta(self):
        record = build_experiment_record(
            job=_sample_job(),
            result_summary={"duration_seconds": 42, "highlights": ["导出 12 个产物"], "next_actions": ["检查 GLB"]},
            scene_meta={"model": "monst3r", "artifact_count": 12},
        )
        assert record["result"]["duration_seconds"] == 42
        assert record["result"]["highlights"] == ["导出 12 个产物"]
        assert record["result"]["scene_meta"]["artifact_count"] == 12


class TestRenderRecordMarkdown:
    def test_markdown_contains_key_sections(self):
        record = build_experiment_record(
            job=_sample_job(),
            blueprint=_sample_blueprint(),
            result_summary={"highlights": ["要点A"], "next_actions": ["动作B"]},
        )
        md = render_record_markdown(record)
        assert "# 实验记录：20260609-120000" in md
        assert "## 复现配置" in md
        assert "monst3r" in md
        assert "image_size: 512" in md
        assert "要点A" in md
        assert "动作B" in md


class TestBuildBundle:
    def test_zip_contains_manifest_markdown_and_job_files(self, tmp_dir: Path):
        job_dir = tmp_dir / "job"
        (job_dir / "output").mkdir(parents=True)
        (job_dir / "logs").mkdir(parents=True)
        (job_dir / "job.json").write_text('{"job_id": "j1"}', encoding="utf-8")
        (job_dir / "output" / "scene_meta.json").write_text('{"model": "monst3r"}', encoding="utf-8")
        (job_dir / "logs" / "runner.log").write_text("ok", encoding="utf-8")

        record = build_experiment_record(job=_sample_job(), blueprint=_sample_blueprint())
        bundle_path = build_experiment_record_bundle(
            job_id="j1", job_dir=job_dir, record=record, out_dir=tmp_dir / "_bundles"
        )
        assert bundle_path.exists()
        with zipfile.ZipFile(bundle_path) as archive:
            names = set(archive.namelist())
        assert "j1/experiment_record.json" in names
        assert "j1/EXPERIMENT_RECORD.md" in names
        assert "j1/job.json" in names
        assert "j1/output/scene_meta.json" in names
        assert "j1/logs/runner.log" in names


class TestExperimentRecordEndpoint:
    def test_manifest_and_download(self, test_client: TestClient):
        import job_store

        job = job_store.create_job(model="dust3r", source_type="images", notes="record test")
        job_id = job.job_id
        (job_store.get_job_dir(job_id) / "output" / "scene_meta.json").write_text(
            '{"model": "dust3r", "n_points": 1000}', encoding="utf-8"
        )
        try:
            manifest = test_client.get(f"/api/agent/experiment-record/{job_id}")
            assert manifest.status_code == 200
            data = manifest.json()
            assert data["job"]["job_id"] == job_id
            assert data["job"]["model"] == "dust3r"
            # dust3r has an agent blueprint, so reproduce config should be populated.
            assert data["reproduce"]["conda_env"]

            download = test_client.get(f"/api/agent/experiment-record/{job_id}/download")
            assert download.status_code == 200
            assert "zip" in download.headers.get("content-type", "")
            with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
                names = set(archive.namelist())
            assert f"{job_id}/experiment_record.json" in names
        finally:
            shutil.rmtree(job_store.get_job_dir(job_id), ignore_errors=True)

    def test_unknown_job_404(self, test_client: TestClient):
        response = test_client.get("/api/agent/experiment-record/nope-not-real")
        assert response.status_code == 404
