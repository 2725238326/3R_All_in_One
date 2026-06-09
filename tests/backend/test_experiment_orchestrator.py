# ═══════════════════════════════════════════════════════════════
# Experiment Orchestration Tests
# ═══════════════════════════════════════════════════════════════
"""Covers the fixed backend/experiment_orchestrator.run_experiment_from_template:
- creates one runnable job per param combination (no create_job(files=...) crash)
- returns real job-id strings
- copies inputs from a source job via save_inputs
- normalizes params through build_job_params
- optional auto_dispatch invokes the dispatch callback per job
- persists the run record (list/get)
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT / "backend"
for _p in (str(ROOT), str(BACKEND_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import experiment_orchestrator as eo  # noqa: E402
import job_store  # noqa: E402


@pytest.fixture
def cleanup_jobs():
    created: list[str] = []
    templates: list[str] = []
    yield {"jobs": created, "templates": templates}
    for job_id in created:
        shutil.rmtree(job_store.get_job_dir(job_id), ignore_errors=True)
    for template_id in templates:
        try:
            eo.delete_experiment_template(template_id)
        except Exception:
            pass


def _make_source_job() -> str:
    job = job_store.create_job(model="dust3r", source_type="images", notes="exp source")
    job_store.save_inputs(job, [("a.png", b"\xff\xd8\xff" + b"0" * 10), ("b.png", b"\xff\xd8\xff" + b"1" * 10)])
    return job.job_id


def test_run_creates_one_job_per_combination(cleanup_jobs):
    template = eo.create_experiment_template(
        name="niter sweep", description="", model="dust3r", source_type="images",
        base_params={}, param_grid={"niter": [100, 300]},
    )
    cleanup_jobs["templates"].append(template.id)
    source_job = _make_source_job()
    cleanup_jobs["jobs"].append(source_job)

    run = eo.run_experiment_from_template(template.id, "run-A", source_job_id=source_job)
    cleanup_jobs["jobs"].extend(run.job_ids)

    assert len(run.job_ids) == 2
    assert all(isinstance(jid, str) for jid in run.job_ids)
    assert run.status == "pending"  # not dispatched

    for jid in run.job_ids:
        job = job_store.load_job(jid)
        assert job.model == "dust3r"
        # inputs copied from the source job
        assert len(job.input_files) == 2
        # params normalized through build_job_params -> niter is one of the grid values
        assert job.params["niter"] in (100, 300)
        assert "image_size" in job.params  # contract-normalized fields present
    # the two jobs use different niter values
    niters = {job_store.load_job(jid).params["niter"] for jid in run.job_ids}
    assert niters == {100, 300}


def test_run_auto_dispatch_invokes_callback(cleanup_jobs):
    template = eo.create_experiment_template(
        name="single", description="", model="dust3r", source_type="images",
        base_params={}, param_grid={},
    )
    cleanup_jobs["templates"].append(template.id)
    source_job = _make_source_job()
    cleanup_jobs["jobs"].append(source_job)

    dispatched: list[str] = []
    run = eo.run_experiment_from_template(
        template.id, "run-B", source_job_id=source_job,
        auto_dispatch=True, dispatch=lambda jid: dispatched.append(jid),
    )
    cleanup_jobs["jobs"].extend(run.job_ids)

    assert len(run.job_ids) == 1  # empty grid -> single base combination
    assert dispatched == run.job_ids
    assert run.status == "running"
    assert run.metadata["dispatched"] == 1
    assert run.metadata["input_count"] == 2


def test_run_persisted_and_listable(cleanup_jobs):
    template = eo.create_experiment_template(
        name="persist", description="", model="dust3r", source_type="images",
        base_params={}, param_grid={"niter": [50]},
    )
    cleanup_jobs["templates"].append(template.id)
    source_job = _make_source_job()
    cleanup_jobs["jobs"].append(source_job)

    run = eo.run_experiment_from_template(template.id, "run-C", source_job_id=source_job)
    cleanup_jobs["jobs"].extend(run.job_ids)

    fetched = eo.get_experiment_run(run.id)
    assert fetched is not None
    assert fetched.job_ids == run.job_ids
    assert run.id in {r.id for r in eo.list_experiment_runs()}


def test_run_unknown_template_raises():
    with pytest.raises(ValueError):
        eo.run_experiment_from_template("exp-does-not-exist", "x")
