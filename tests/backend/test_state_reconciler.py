# ═══════════════════════════════════════════════════════════════
# State Reconciler Tests
# ═══════════════════════════════════════════════════════════════
"""
测试 backend/state_reconciler.py:
- 状态检测
- 孤儿任务处理
- Reconcile 报告
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from datetime import datetime, timedelta

import pytest

BACKEND_DIR = Path(__file__).parent.parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@dataclass
class MockJob:
    """模拟任务对象"""
    job_id: str
    status: str
    retry_count: int = 0
    updated_at: str | None = None


class TestStateReconciler:
    """StateReconciler 测试"""
    
    def test_skip_terminal_jobs(self):
        """跳过终态任务"""
        from state_reconciler import StateReconciler, ReconcileAction
        
        reconciler = StateReconciler()
        
        jobs = [
            MockJob("job_1", "finished"),
            MockJob("job_2", "pending"),
            MockJob("job_3", "cancelled"),
        ]
        
        update_job = MagicMock()
        report = reconciler.reconcile_all(
            load_all_jobs=lambda: jobs,
            update_job=update_job,
        )
        
        assert report.total_jobs == 3
        assert report.skipped == 3
        assert report.reconciled == 0
        update_job.assert_not_called()
    
    def test_mark_orphan_running_job_failed(self):
        """标记孤儿运行中任务为失败"""
        from state_reconciler import StateReconciler, ReconcileAction
        
        reconciler = StateReconciler()
        
        jobs = [MockJob("orphan_job", "running")]
        
        update_job = MagicMock()
        report = reconciler.reconcile_all(
            load_all_jobs=lambda: jobs,
            update_job=update_job,
        )
        
        assert report.reconciled == 1
        update_job.assert_called_once()
        
        call_kwargs = update_job.call_args[1]
        assert call_kwargs["status"] == "failed"
        assert call_kwargs["phase"] == "failed"
    
    def test_auto_retry_disabled(self):
        """自动重试禁用时不重试"""
        from state_reconciler import StateReconciler, ReconcileAction
        
        reconciler = StateReconciler(auto_retry_enabled=False)
        
        jobs = [MockJob("failed_job", "failed")]
        
        retry_job = MagicMock()
        report = reconciler.reconcile_all(
            load_all_jobs=lambda: jobs,
            update_job=MagicMock(),
            retry_job=retry_job,
        )
        
        assert report.skipped == 1
        retry_job.assert_not_called()
    
    def test_auto_retry_enabled(self):
        """自动重试启用时重试失败任务"""
        from state_reconciler import StateReconciler, ReconcileAction
        
        reconciler = StateReconciler(
            auto_retry_enabled=True,
            max_auto_retries=2,
        )
        
        jobs = [MockJob("failed_job", "failed", retry_count=0)]
        
        retry_job = MagicMock()
        report = reconciler.reconcile_all(
            load_all_jobs=lambda: jobs,
            update_job=MagicMock(),
            retry_job=retry_job,
        )
        
        assert report.reconciled == 1
        retry_job.assert_called_once_with("failed_job")
    
    def test_auto_retry_max_reached(self):
        """达到最大重试次数不再重试"""
        from state_reconciler import StateReconciler
        
        reconciler = StateReconciler(
            auto_retry_enabled=True,
            max_auto_retries=2,
        )
        
        jobs = [MockJob("failed_job", "failed", retry_count=2)]
        
        retry_job = MagicMock()
        report = reconciler.reconcile_all(
            load_all_jobs=lambda: jobs,
            update_job=MagicMock(),
            retry_job=retry_job,
        )
        
        assert report.skipped == 1
        retry_job.assert_not_called()


class TestReconcileReport:
    """Reconcile 报告测试"""
    
    def test_report_to_dict(self):
        """报告序列化"""
        from state_reconciler import ReconcileReport, ReconcileResult, ReconcileAction
        
        report = ReconcileReport(
            started_at="2024-01-01T00:00:00",
            finished_at="2024-01-01T00:00:01",
            total_jobs=3,
            reconciled=1,
            skipped=2,
        )
        report.results.append(ReconcileResult(
            job_id="test_job",
            action=ReconcileAction.MARK_FAILED,
            reason="Test reason",
        ))
        
        data = report.to_dict()
        
        assert data["total_jobs"] == 3
        assert data["reconciled"] == 1
        assert len(data["results"]) == 1
        assert data["results"][0]["action"] == "mark_failed"


class TestCheckStaleJobs:
    """卡住任务检测测试"""
    
    def test_detect_stale_job(self):
        """检测卡住的任务"""
        from state_reconciler import StateReconciler
        
        reconciler = StateReconciler(stale_threshold_minutes=30)
        
        old_time = (datetime.now() - timedelta(hours=1)).isoformat()
        jobs = [MockJob("stale_job", "running", updated_at=old_time)]
        
        stale = reconciler.check_stale_jobs(load_all_jobs=lambda: jobs)
        
        assert "stale_job" in stale
    
    def test_skip_recent_job(self):
        """跳过最近更新的任务"""
        from state_reconciler import StateReconciler
        
        reconciler = StateReconciler(stale_threshold_minutes=30)
        
        recent_time = datetime.now().isoformat()
        jobs = [MockJob("active_job", "running", updated_at=recent_time)]
        
        stale = reconciler.check_stale_jobs(load_all_jobs=lambda: jobs)
        
        assert "active_job" not in stale


class TestGlobalFunctions:
    """全局函数测试"""
    
    def test_run_reconcile(self):
        """run_reconcile 函数"""
        from state_reconciler import run_reconcile
        
        jobs = [MockJob("test_job", "finished")]
        
        report = run_reconcile(
            load_all_jobs=lambda: jobs,
            update_job=MagicMock(),
        )
        
        assert report.total_jobs == 1
        assert report.skipped == 1
    
    def test_get_reconcile_report(self):
        """get_reconcile_report 函数"""
        from state_reconciler import run_reconcile, get_reconcile_report
        
        jobs = [MockJob("test_job", "finished")]
        
        run_reconcile(
            load_all_jobs=lambda: jobs,
            update_job=MagicMock(),
        )
        
        report_dict = get_reconcile_report()
        
        assert report_dict is not None
        assert "total_jobs" in report_dict
