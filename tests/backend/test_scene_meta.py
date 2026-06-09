# ═══════════════════════════════════════════════════════════════
# scene_meta normalization tests
# ═══════════════════════════════════════════════════════════════
"""Covers backend/scene_meta.normalize_scene_meta against the three real
historical scene_meta.json shapes (dust3r / monst3r / align3r) and the
GET /api/jobs/{job_id}/scene-meta endpoint."""
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

from scene_meta import SCENE_META_SCHEMA_VERSION, normalize_scene_meta  # noqa: E402


# Real shapes drawn from the runner sources.
DUST3R_RAW = {
    "focals": [1.0],
    "poses": [[1, 0], [0, 1]],
    "n_images": 3,
    "n_pairs": 6,
    "n_points": 1000,
    "raw_point_count": 2000,
    "image_files": ["a.png", "b.png", "c.png"],
    "params": {"image_size": 512, "niter": 300},
}

MONST3R_RAW = {
    "model": "monst3r",
    "source_type": "video",
    "input_count": 24,
    "artifacts": [{"name": "scene.glb", "role": "scene"}, {"name": "pred_traj.txt", "role": "trajectory"}],
    "artifact_count": 2,
    "artifact_groups": [{"key": "scene", "label": "三维场景", "count": 1}],
    "review_targets": [{"role": "scene", "name": "scene.glb", "relative_path": "output/scene.glb"}],
    "params": {"num_frames": 24},
}

ALIGN3R_RAW = {
    "model": "align3r",
    "input_mode": "video",
    "input_count": 48,
    "artifacts": {"depth_0": {"exists": True}, "pointcloud": {"exists": True}},
    "artifact_count": 2,
    "artifact_groups": [{"key": "depth", "label": "深度图", "count": 1}],
    "primary_artifacts": [{"role": "pointcloud", "name": "pointcloud.ply", "relative_path": "output/pointcloud.ply"}],
}


class TestNormalizeSceneMeta:
    def test_dust3r_without_model_field(self):
        norm = normalize_scene_meta("dust3r", DUST3R_RAW)
        assert norm["schema_version"] == SCENE_META_SCHEMA_VERSION
        assert norm["model"] == "dust3r"  # filled from the argument
        assert norm["input_count"] == 3   # from n_images
        assert norm["point_count"] == 1000  # from n_points (not raw_point_count)
        assert norm["params"]["niter"] == 300
        assert norm["artifact_groups"] == []
        assert norm["has_scene_meta"] is True

    def test_monst3r_list_artifacts(self):
        norm = normalize_scene_meta("monst3r", MONST3R_RAW)
        assert norm["model"] == "monst3r"
        assert norm["source_type"] == "video"
        assert norm["input_count"] == 24
        assert norm["artifact_count"] == 2
        assert len(norm["artifact_groups"]) == 1
        # primary_artifacts falls back to review_targets when not present
        assert norm["primary_artifacts"][0]["role"] == "scene"

    def test_align3r_dict_artifacts(self):
        norm = normalize_scene_meta("align3r", ALIGN3R_RAW)
        assert norm["model"] == "align3r"
        assert norm["source_type"] == "video"  # from input_mode
        assert norm["artifact_count"] == 2
        assert norm["primary_artifacts"][0]["role"] == "pointcloud"

    def test_empty_and_none(self):
        for raw in (None, {}):
            norm = normalize_scene_meta("cut3r", raw)
            assert norm["model"] == "cut3r"
            assert norm["has_scene_meta"] is False
            assert norm["point_count"] is None
            assert norm["artifact_groups"] == []

    def test_output_file_count_passthrough(self):
        norm = normalize_scene_meta("dust3r", DUST3R_RAW, output_files=["a", "b", "c"])
        assert norm["output_file_count"] == 3


class TestSceneMetaEndpoint:
    def test_scene_meta_endpoint_normalizes(self, test_client: TestClient):
        import job_store

        job = job_store.create_job(model="dust3r", source_type="images", notes="scene meta test")
        job_id = job.job_id
        import json

        (job_store.get_job_dir(job_id) / "output" / "scene_meta.json").write_text(
            json.dumps(DUST3R_RAW), encoding="utf-8"
        )
        try:
            response = test_client.get(f"/api/jobs/{job_id}/scene-meta")
            assert response.status_code == 200
            data = response.json()
            assert data["model"] == "dust3r"
            assert data["sceneMeta"]["point_count"] == 1000
            assert data["sceneMeta"]["model"] == "dust3r"
        finally:
            shutil.rmtree(job_store.get_job_dir(job_id), ignore_errors=True)

    def test_scene_meta_unknown_job_404(self, test_client: TestClient):
        assert test_client.get("/api/jobs/none-xyz/scene-meta").status_code == 404
