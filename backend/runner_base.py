# ═══════════════════════════════════════════════════════════════
# Runner Base — 模型执行器基类
# 定义统一的 Runner 接口，支持本地、远程、容器等执行方式
# ═══════════════════════════════════════════════════════════════
"""
Runner 抽象基类，所有执行器（SSH、Docker、Local）应继承此类。

用法示例:
    runner = SSHRunner(job_id="xxx", model="monst3r")
    runner.prepare()      # 准备环境
    runner.upload()       # 上传输入
    runner.execute()      # 执行模型
    runner.download()     # 下载结果
    runner.cleanup()      # 清理
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

LOGGER = logging.getLogger("backend.runner")


class RunnerPhase(Enum):
    """执行阶段"""
    INIT = "init"
    PREPARING = "preparing"
    UPLOADING = "uploading"
    EXECUTING = "executing"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RunnerProgress:
    """执行进度"""
    phase: RunnerPhase
    progress: float = 0.0  # 0.0 - 1.0
    message: str = ""
    started_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    def update(self, progress: float, message: str = "") -> None:
        self.progress = min(1.0, max(0.0, progress))
        if message:
            self.message = message
        self.updated_at = datetime.now()
    
    def to_dict(self) -> dict:
        return {
            "phase": self.phase.value,
            "progress": self.progress,
            "message": self.message,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass
class RunnerResult:
    """执行结果"""
    success: bool
    phase: RunnerPhase
    output_files: list[str] = field(default_factory=list)
    error_message: str | None = None
    metrics: dict = field(default_factory=dict)
    duration_seconds: float = 0.0
    
    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "phase": self.phase.value,
            "output_files": self.output_files,
            "error_message": self.error_message,
            "metrics": self.metrics,
            "duration_seconds": self.duration_seconds,
        }


class RunnerBase(ABC):
    """
    模型执行器基类
    
    子类应实现:
    - prepare(): 准备执行环境
    - upload(): 上传输入文件
    - execute(): 执行模型推理
    - download(): 下载结果文件
    - cleanup(): 清理临时文件
    - cancel(): 取消执行
    """
    
    def __init__(
        self,
        job_id: str,
        model: str,
        params: dict | None = None,
        on_progress: Callable[[RunnerProgress], None] | None = None,
    ):
        self.job_id = job_id
        self.model = model
        self.params = params or {}
        self.on_progress = on_progress
        
        self._progress = RunnerProgress(phase=RunnerPhase.INIT)
        self._cancelled = False
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None
    
    # ─────────────── 公共方法 ───────────────
    
    def run(self) -> RunnerResult:
        """完整执行流程"""
        self._started_at = datetime.now()
        
        try:
            self._update_phase(RunnerPhase.PREPARING)
            self.prepare()
            self._check_cancelled()
            
            self._update_phase(RunnerPhase.UPLOADING)
            self.upload()
            self._check_cancelled()
            
            self._update_phase(RunnerPhase.EXECUTING)
            self.execute()
            self._check_cancelled()
            
            self._update_phase(RunnerPhase.DOWNLOADING)
            output_files = self.download()
            
            self._update_phase(RunnerPhase.COMPLETED, progress=1.0)
            self._completed_at = datetime.now()
            
            return RunnerResult(
                success=True,
                phase=RunnerPhase.COMPLETED,
                output_files=output_files,
                duration_seconds=self._duration_seconds(),
            )
            
        except CancelledException:
            self._update_phase(RunnerPhase.CANCELLED)
            return RunnerResult(
                success=False,
                phase=RunnerPhase.CANCELLED,
                error_message="任务已取消",
                duration_seconds=self._duration_seconds(),
            )
            
        except Exception as e:
            LOGGER.exception(f"Runner failed: {self.job_id}")
            self._update_phase(RunnerPhase.FAILED, message=str(e))
            return RunnerResult(
                success=False,
                phase=RunnerPhase.FAILED,
                error_message=str(e),
                duration_seconds=self._duration_seconds(),
            )
            
        finally:
            try:
                self.cleanup()
            except Exception as e:
                LOGGER.warning(f"Cleanup failed: {e}")
    
    def cancel(self) -> None:
        """取消执行"""
        self._cancelled = True
        self._on_cancel()
    
    @property
    def progress(self) -> RunnerProgress:
        return self._progress
    
    # ─────────────── 抽象方法 ───────────────
    
    @abstractmethod
    def prepare(self) -> None:
        """准备执行环境（检查依赖、创建目录等）"""
        pass
    
    @abstractmethod
    def upload(self) -> None:
        """上传输入文件到执行环境"""
        pass
    
    @abstractmethod
    def execute(self) -> None:
        """执行模型推理"""
        pass
    
    @abstractmethod
    def download(self) -> list[str]:
        """下载结果文件，返回本地文件路径列表"""
        pass
    
    @abstractmethod
    def cleanup(self) -> None:
        """清理临时文件和资源"""
        pass
    
    # ─────────────── 可选重写 ───────────────
    
    def _on_cancel(self) -> None:
        """子类可重写以实现取消逻辑"""
        pass
    
    # ─────────────── 内部方法 ───────────────
    
    def _update_phase(
        self,
        phase: RunnerPhase,
        progress: float = 0.0,
        message: str = "",
    ) -> None:
        self._progress = RunnerProgress(
            phase=phase,
            progress=progress,
            message=message,
        )
        if self.on_progress:
            self.on_progress(self._progress)
    
    def _update_progress(self, progress: float, message: str = "") -> None:
        self._progress.update(progress, message)
        if self.on_progress:
            self.on_progress(self._progress)
    
    def _check_cancelled(self) -> None:
        if self._cancelled:
            raise CancelledException()
    
    def _duration_seconds(self) -> float:
        if not self._started_at:
            return 0.0
        end = self._completed_at or datetime.now()
        return (end - self._started_at).total_seconds()


class CancelledException(Exception):
    """任务取消异常"""
    pass


# ─────────────── Runner 工厂 ───────────────

_RUNNER_REGISTRY: dict[str, type[RunnerBase]] = {}


def register_runner(name: str):
    """注册 Runner 类型装饰器"""
    def decorator(cls: type[RunnerBase]):
        _RUNNER_REGISTRY[name] = cls
        return cls
    return decorator


def get_runner(
    runner_type: str,
    job_id: str,
    model: str,
    **kwargs,
) -> RunnerBase:
    """获取 Runner 实例"""
    if runner_type not in _RUNNER_REGISTRY:
        raise ValueError(f"Unknown runner type: {runner_type}")
    return _RUNNER_REGISTRY[runner_type](job_id=job_id, model=model, **kwargs)


def available_runners() -> list[str]:
    """获取所有可用的 Runner 类型"""
    return list(_RUNNER_REGISTRY.keys())
