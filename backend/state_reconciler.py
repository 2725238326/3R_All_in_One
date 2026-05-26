# ═══════════════════════════════════════════════════════════════
# State Reconciler — 状态一致性恢复
# ═══════════════════════════════════════════════════════════════
"""
检测和修复任务状态不一致问题：
- 后端崩溃后的孤儿任务
- 长时间卡住的任务
- 状态与实际不符的任务
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Callable

from logging_config import log


class ReconcileAction(str, Enum):
    """Reconcile 动作类型"""
    MARK_FAILED = "mark_failed"         # 标记为失败
    AUTO_RETRY = "auto_retry"           # 自动重试
    CLEANUP = "cleanup"                 # 清理资源
    SKIP = "skip"                       # 跳过（状态正常）


@dataclass
class ReconcileResult:
    """单个任务的 reconcile 结果"""
    job_id: str
    action: ReconcileAction
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    success: bool = True
    error: str | None = None


@dataclass
class ReconcileReport:
    """Reconcile 报告"""
    started_at: str
    finished_at: str | None = None
    total_jobs: int = 0
    reconciled: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[ReconcileResult] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "total_jobs": self.total_jobs,
            "reconciled": self.reconciled,
            "skipped": self.skipped,
            "failed": self.failed,
            "results": [
                {
                    "job_id": r.job_id,
                    "action": r.action.value,
                    "reason": r.reason,
                    "timestamp": r.timestamp,
                    "success": r.success,
                    "error": r.error,
                }
                for r in self.results
            ],
        }


class StateReconciler:
    """
    状态一致性恢复器
    
    在后端启动时检测和修复不一致的任务状态。
    """
    
    def __init__(
        self,
        stale_threshold_minutes: int = 30,
        auto_retry_enabled: bool = False,
        max_auto_retries: int = 1,
    ):
        """
        Args:
            stale_threshold_minutes: 任务多久没更新算作卡住
            auto_retry_enabled: 是否启用自动重试
            max_auto_retries: 最大自动重试次数
        """
        self.stale_threshold = timedelta(minutes=stale_threshold_minutes)
        self.auto_retry_enabled = auto_retry_enabled
        self.max_auto_retries = max_auto_retries
        self._last_report: ReconcileReport | None = None
        self._lock = threading.Lock()
    
    def reconcile_all(
        self,
        load_all_jobs: Callable[[], list],
        update_job: Callable[[str, ...], None],
        retry_job: Callable[[str], None] | None = None,
    ) -> ReconcileReport:
        """
        执行全量 reconcile
        
        Args:
            load_all_jobs: 加载所有任务的函数
            update_job: 更新任务的函数
            retry_job: 重试任务的函数（可选）
        """
        report = ReconcileReport(started_at=datetime.now().isoformat())
        
        try:
            jobs = load_all_jobs()
            report.total_jobs = len(jobs)
            
            for job in jobs:
                result = self._reconcile_job(job, update_job, retry_job)
                report.results.append(result)
                
                if result.action == ReconcileAction.SKIP:
                    report.skipped += 1
                elif result.success:
                    report.reconciled += 1
                else:
                    report.failed += 1
            
        except Exception as e:
            log.error(f"Reconcile failed: {e}")
            report.failed += 1
        
        report.finished_at = datetime.now().isoformat()
        
        with self._lock:
            self._last_report = report
        
        return report
    
    def _reconcile_job(
        self,
        job,
        update_job: Callable[[str, ...], None],
        retry_job: Callable[[str], None] | None,
    ) -> ReconcileResult:
        """Reconcile 单个任务"""
        job_id = job.job_id
        status = job.status
        
        # 状态正常的任务跳过
        if status in ("pending", "finished", "cancelled"):
            return ReconcileResult(
                job_id=job_id,
                action=ReconcileAction.SKIP,
                reason=f"Status '{status}' is terminal, no action needed",
            )
        
        # 失败的任务检查是否需要自动重试
        if status == "failed":
            if self.auto_retry_enabled and retry_job:
                retry_count = getattr(job, "retry_count", 0)
                if retry_count < self.max_auto_retries:
                    try:
                        log.info(f"Auto-retrying job {job_id} (attempt {retry_count + 1})")
                        retry_job(job_id)
                        return ReconcileResult(
                            job_id=job_id,
                            action=ReconcileAction.AUTO_RETRY,
                            reason=f"Auto-retry attempt {retry_count + 1}",
                        )
                    except Exception as e:
                        return ReconcileResult(
                            job_id=job_id,
                            action=ReconcileAction.AUTO_RETRY,
                            reason=f"Auto-retry failed: {e}",
                            success=False,
                            error=str(e),
                        )
            
            return ReconcileResult(
                job_id=job_id,
                action=ReconcileAction.SKIP,
                reason="Already failed, no auto-retry",
            )
        
        # 运行中的任务 - 检查是否为孤儿任务
        if status == "running":
            # 检查是否有活跃的 runner 线程
            # 如果没有，则标记为失败
            return self._handle_orphan_running_job(job, update_job)
        
        # 其他状态
        return ReconcileResult(
            job_id=job_id,
            action=ReconcileAction.SKIP,
            reason=f"Unknown status '{status}', skipping",
        )
    
    def _handle_orphan_running_job(
        self,
        job,
        update_job: Callable[[str, ...], None],
    ) -> ReconcileResult:
        """处理孤儿运行中任务"""
        job_id = job.job_id
        
        try:
            update_job(
                job_id,
                status="failed",
                phase="failed",
                error_message=(
                    "后端在任务运行中重启或崩溃，调度线程已丢失。"
                    "任务已自动标记为失败，可点击重试重新调度。"
                ),
                progress_message="后端重启后未发现运行线程，已自动标记为失败。",
            )
            
            log.warning(f"Marked orphan job {job_id} as failed")
            
            return ReconcileResult(
                job_id=job_id,
                action=ReconcileAction.MARK_FAILED,
                reason="Orphan running job - no active runner thread",
            )
        except Exception as e:
            return ReconcileResult(
                job_id=job_id,
                action=ReconcileAction.MARK_FAILED,
                reason=f"Failed to mark as failed: {e}",
                success=False,
                error=str(e),
            )
    
    def get_last_report(self) -> ReconcileReport | None:
        """获取最近一次 reconcile 报告"""
        with self._lock:
            return self._last_report
    
    def check_stale_jobs(
        self,
        load_all_jobs: Callable[[], list],
    ) -> list[str]:
        """
        检查卡住的任务（长时间没有进度更新）
        
        Returns:
            卡住的任务 ID 列表
        """
        stale_jobs = []
        now = datetime.now()
        
        try:
            jobs = load_all_jobs()
            
            for job in jobs:
                if job.status != "running":
                    continue
                
                # 检查最后更新时间
                # 假设 job 有 updated_at 字段
                updated_at = getattr(job, "updated_at", None)
                if updated_at:
                    try:
                        last_update = datetime.fromisoformat(updated_at)
                        if now - last_update > self.stale_threshold:
                            stale_jobs.append(job.job_id)
                    except ValueError:
                        pass
        except Exception as e:
            log.error(f"Check stale jobs failed: {e}")
        
        return stale_jobs


# ─────────────── 全局实例 ───────────────

reconciler = StateReconciler(
    stale_threshold_minutes=30,
    auto_retry_enabled=False,  # 默认关闭自动重试
    max_auto_retries=1,
)


def run_reconcile(
    load_all_jobs: Callable[[], list],
    update_job: Callable[[str, ...], None],
    retry_job: Callable[[str], None] | None = None,
) -> ReconcileReport:
    """执行状态 reconcile"""
    return reconciler.reconcile_all(load_all_jobs, update_job, retry_job)


def get_reconcile_report() -> dict | None:
    """获取最近一次 reconcile 报告（字典格式）"""
    report = reconciler.get_last_report()
    return report.to_dict() if report else None


__all__ = [
    "ReconcileAction",
    "ReconcileResult",
    "ReconcileReport",
    "StateReconciler",
    "reconciler",
    "run_reconcile",
    "get_reconcile_report",
]
