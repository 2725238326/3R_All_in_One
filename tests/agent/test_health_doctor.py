# ═══════════════════════════════════════════════════════════════
# Health Doctor Tests — 健康诊断测试
# ═══════════════════════════════════════════════════════════════
"""
测试 agent/health_doctor.py:
- 常见错误模式匹配
- known_issues 回退诊断
- 修复命令提取
- ASCII 控制台输出
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def make_spec(known_issues: list[dict] | None = None):
    from agent.env_builder import ModelSpec

    return ModelSpec(
        name="TestModel",
        key="testmodel",
        family="dust3r",
        version="1.0.0",
        paper={},
        tags={"type": "static", "paradigm": "pairwise"},
        repo={"server_path": "/tmp/testmodel"},
        environment={"conda_env": "testmodel"},
        checkpoints=[],
        build_steps=[],
        resources={},
        health_checks=[],
        smoke_test={},
        runner={},
        output_contract={},
        known_issues=known_issues or [],
        compatibility={},
        status="integrated",
    )


def make_result(step: str, *, success: bool = False, output: str = "", error: str = ""):
    from agent.env_builder import BuildResult

    return BuildResult(
        model="testmodel",
        step=step,
        success=success,
        output=output,
        error=error,
        duration_sec=0.1,
    )


class TestHealthDoctorPatterns:
    """错误模式匹配测试"""

    def test_missing_module_generates_fixable_report(self):
        from agent.health_doctor import HealthDoctor

        doctor = HealthDoctor()
        report = doctor.diagnose(
            make_spec(),
            [make_result("import", error="ModuleNotFoundError: No module named 'roma'")],
        )

        assert report.overall_status == "fixable"
        assert report.items[0].symptom == "Missing Python module"
        assert report.items[0].fix_command == "pip install roma"
        assert doctor.suggest_fixes(report) == ["pip install roma"]

    def test_conda_env_conflict_replaces_env_name(self):
        from agent.health_doctor import HealthDoctor

        report = HealthDoctor().diagnose(
            make_spec(),
            [make_result("create-env", error="CondaError: prefix already exists")],
        )

        assert report.items[0].symptom == "Conda environment conflict"
        assert "testmodel" in report.items[0].solution

    def test_quick_diagnose_matches_cuda_oom(self):
        from agent.health_doctor import quick_diagnose

        item = quick_diagnose("RuntimeError: CUDA error: out of memory")

        assert item is not None
        assert item.symptom == "GPU out of memory"
        assert item.confidence >= 0.9


class TestHealthDoctorKnownIssues:
    """known_issues 回退诊断测试"""

    def test_unresolved_known_issue_is_reported(self):
        from agent.health_doctor import HealthDoctor

        spec = make_spec(
            [
                {
                    "id": "test-001",
                    "description": "curope compile fails on old CUDA",
                    "workaround": "Rebuild curope with the local CUDA toolkit",
                    "resolved": False,
                }
            ]
        )
        report = HealthDoctor().diagnose(
            spec,
            [make_result("build-curope", error="local CUDA curope compile fails")],
        )

        assert report.overall_status == "critical"
        assert report.items[0].related_issue_id == "test-001"
        assert report.items[0].solution == "Rebuild curope with the local CUDA toolkit"

    def test_resolved_known_issue_is_ignored(self):
        from agent.health_doctor import HealthDoctor

        spec = make_spec(
            [
                {
                    "id": "test-002",
                    "description": "checkpoint missing",
                    "workaround": "Download checkpoint",
                    "resolved": True,
                }
            ]
        )
        report = HealthDoctor().diagnose(
            spec,
            [make_result("weights", error="checkpoint missing but issue is resolved")],
        )

        assert report.overall_status == "needs_attention"
        assert report.items[0].cause == "Unknown error"


class TestHealthDoctorReport:
    """诊断报告输出测试"""

    def test_all_successful_checks_are_healthy(self):
        from agent.health_doctor import HealthDoctor

        report = HealthDoctor().diagnose(
            make_spec(),
            [make_result("import", success=True), make_result("smoke", success=True)],
        )

        assert report.overall_status == "healthy"
        assert report.summary() == "[OK] TestModel: healthy (0 issues)"

    def test_print_report_uses_ascii_status_markers(self, capsys):
        from agent.health_doctor import HealthDoctor

        doctor = HealthDoctor()
        report = doctor.diagnose(make_spec(), [make_result("import", success=True)])
        doctor.print_report(report)
        output = capsys.readouterr().out

        assert "[OK] No issues detected" in output
        assert all(symbol not in output for symbol in ("✓", "✗", "⚠", "●", "○"))
