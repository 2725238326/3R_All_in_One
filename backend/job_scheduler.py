"""
Job Scheduler - 并发控制、优先级队列、自动重试
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

LOGGER = logging.getLogger("kykt.scheduler")


class JobPriority(str, Enum):
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"

    @property
    def weight(self) -> int:
        return {"high": 100, "normal": 50, "low": 10}[self.value]


@dataclass
class ScheduledJob:
    job_id: str
    priority: JobPriority = JobPriority.NORMAL
    retry_count: int = 0
    max_retries: int = 2
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    
    @property
    def score(self) -> float:
        age_bonus = (time.time() - self.created_at) / 60  # Minutes waiting
        return self.priority.weight + age_bonus


@dataclass
class SchedulerConfig:
    max_concurrent: int = 2
    default_max_retries: int = 2
    retry_delay_seconds: float = 5.0
    poll_interval_seconds: float = 1.0


class JobScheduler:
    """
    任务调度器 - 管理任务队列和并发执行
    """
    
    def __init__(
        self,
        config: Optional[SchedulerConfig] = None,
        dispatch_fn: Optional[Callable[[str], None]] = None,
        get_job_status_fn: Optional[Callable[[str], str]] = None,
    ):
        self.config = config or SchedulerConfig()
        self._dispatch_fn = dispatch_fn
        self._get_job_status_fn = get_job_status_fn
        self._queue: list[ScheduledJob] = []
        self._running: dict[str, ScheduledJob] = {}
        self._lock = threading.RLock()
        self._running_flag = False
        self._worker_thread: Optional[threading.Thread] = None
        self._listeners: list[Callable[[str, str], None]] = []
    
    def configure(
        self,
        dispatch_fn: Callable[[str], None],
        get_job_status_fn: Callable[[str], str],
    ) -> None:
        self._dispatch_fn = dispatch_fn
        self._get_job_status_fn = get_job_status_fn
    
    def add_listener(self, listener: Callable[[str, str], None]) -> None:
        with self._lock:
            self._listeners.append(listener)
    
    def _notify_listeners(self, job_id: str, event: str) -> None:
        for listener in self._listeners:
            try:
                listener(job_id, event)
            except Exception as e:
                LOGGER.warning(f"Listener error: {e}")
    
    def enqueue(
        self,
        job_id: str,
        priority: JobPriority = JobPriority.NORMAL,
        max_retries: Optional[int] = None,
    ) -> bool:
        with self._lock:
            if any(j.job_id == job_id for j in self._queue):
                LOGGER.debug(f"Job {job_id} already in queue")
                return False
            if job_id in self._running:
                LOGGER.debug(f"Job {job_id} already running")
                return False
            
            scheduled = ScheduledJob(
                job_id=job_id,
                priority=priority,
                max_retries=max_retries if max_retries is not None else self.config.default_max_retries,
            )
            self._queue.append(scheduled)
            self._queue.sort(key=lambda j: -j.score)
            LOGGER.info(f"Enqueued job {job_id} with priority {priority.value}")
            self._notify_listeners(job_id, "enqueued")
            return True
    
    def dequeue(self, job_id: str) -> bool:
        with self._lock:
            for i, job in enumerate(self._queue):
                if job.job_id == job_id:
                    self._queue.pop(i)
                    LOGGER.info(f"Dequeued job {job_id}")
                    self._notify_listeners(job_id, "dequeued")
                    return True
            return False
    
    def _try_dispatch_next(self) -> bool:
        with self._lock:
            if len(self._running) >= self.config.max_concurrent:
                return False
            if not self._queue:
                return False
            
            self._queue.sort(key=lambda j: -j.score)
            job = self._queue.pop(0)
            job.started_at = time.time()
            self._running[job.job_id] = job
        
        try:
            if self._dispatch_fn:
                self._dispatch_fn(job.job_id)
                LOGGER.info(f"Dispatched job {job.job_id}")
                self._notify_listeners(job.job_id, "dispatched")
            return True
        except Exception as e:
            LOGGER.error(f"Failed to dispatch {job.job_id}: {e}")
            with self._lock:
                self._running.pop(job.job_id, None)
                if job.retry_count < job.max_retries:
                    job.retry_count += 1
                    self._queue.append(job)
                    LOGGER.info(f"Requeued job {job.job_id} for retry {job.retry_count}")
                    self._notify_listeners(job.job_id, "retry_enqueued")
            return False
    
    def _check_running_jobs(self) -> None:
        if not self._get_job_status_fn:
            return
        
        with self._lock:
            completed = []
            for job_id, job in self._running.items():
                try:
                    status = self._get_job_status_fn(job_id)
                    if status in ("finished", "failed", "cancelled"):
                        completed.append((job_id, status, job))
                except Exception as e:
                    LOGGER.warning(f"Failed to check status of {job_id}: {e}")
            
            for job_id, status, job in completed:
                self._running.pop(job_id, None)
                if status == "failed" and job.retry_count < job.max_retries:
                    job.retry_count += 1
                    job.started_at = None
                    self._queue.append(job)
                    LOGGER.info(f"Auto-retry job {job_id} ({job.retry_count}/{job.max_retries})")
                    self._notify_listeners(job_id, "auto_retry")
                else:
                    self._notify_listeners(job_id, f"completed_{status}")
    
    def _worker_loop(self) -> None:
        LOGGER.info("Scheduler worker started")
        while self._running_flag:
            self._check_running_jobs()
            while self._try_dispatch_next():
                pass
            time.sleep(self.config.poll_interval_seconds)
        LOGGER.info("Scheduler worker stopped")
    
    def start(self) -> None:
        with self._lock:
            if self._running_flag:
                return
            self._running_flag = True
            self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self._worker_thread.start()
    
    def stop(self) -> None:
        with self._lock:
            self._running_flag = False
            if self._worker_thread:
                self._worker_thread.join(timeout=5.0)
                self._worker_thread = None
    
    def status(self) -> dict:
        with self._lock:
            return {
                "running": self._running_flag,
                "max_concurrent": self.config.max_concurrent,
                "queue_length": len(self._queue),
                "running_count": len(self._running),
                "queued_jobs": [
                    {
                        "job_id": j.job_id,
                        "priority": j.priority.value,
                        "retry_count": j.retry_count,
                        "score": round(j.score, 2),
                    }
                    for j in self._queue
                ],
                "running_jobs": [
                    {
                        "job_id": j.job_id,
                        "priority": j.priority.value,
                        "started_at": j.started_at,
                    }
                    for j in self._running.values()
                ],
            }
    
    def set_max_concurrent(self, value: int) -> None:
        if value < 1:
            raise ValueError("max_concurrent must be >= 1")
        with self._lock:
            self.config.max_concurrent = value
            LOGGER.info(f"Set max_concurrent to {value}")


# Global scheduler instance
scheduler = JobScheduler()
