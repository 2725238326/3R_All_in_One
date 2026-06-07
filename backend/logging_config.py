# ═══════════════════════════════════════════════════════════════
# Logging Configuration — 结构化日志系统
# ═══════════════════════════════════════════════════════════════
"""
基于 loguru 的统一日志系统，提供：
- 结构化日志输出（JSON 格式可选）
- 自动日志轮转
- 任务级别日志隔离
- 性能追踪
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from typing import TYPE_CHECKING
from contextvars import ContextVar
from functools import wraps
import time

from loguru import logger

if TYPE_CHECKING:
    from typing import Any, Callable

# ─────────────── Context Variables ───────────────

# 当前任务 ID（用于日志关联）
current_job_id: ContextVar[str | None] = ContextVar("current_job_id", default=None)


# ─────────────── Log Directory ───────────────

def get_log_dir() -> Path:
    """获取日志目录"""
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    
    log_dir = base / "3R_All_in_One" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


# ─────────────── Custom Formatters ───────────────

def job_context_filter(record: dict) -> bool:
    """添加任务上下文到日志记录"""
    record["extra"]["job_id"] = current_job_id.get()
    return True


def format_console(record: dict) -> str:
    """控制台格式（彩色、简洁）"""
    job_id = record["extra"].get("job_id")
    job_tag = f"[{job_id[:8]}] " if job_id else ""
    
    return (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <7}</level> | "
        f"<cyan>{job_tag}</cyan>"
        "<level>{message}</level>\n"
        "{exception}"
    )


def format_file(record: dict) -> str:
    """文件格式（完整信息）"""
    job_id = record["extra"].get("job_id")
    job_tag = f"[{job_id}] " if job_id else ""
    
    return (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
        "{level: <7} | "
        "{name}:{function}:{line} | "
        f"{job_tag}"
        "{message}\n"
        "{exception}"
    )


# ─────────────── Setup Functions ───────────────

def setup_logging(
    level: str = "INFO",
    console: bool = True,
    file: bool = True,
    json_file: bool = False,
    rotation: str = "10 MB",
    retention: str = "7 days",
) -> None:
    """
    配置日志系统
    
    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        console: 是否输出到控制台
        file: 是否输出到文件
        json_file: 是否额外输出 JSON 格式
        rotation: 日志轮转大小
        retention: 日志保留时间
    """
    # 移除默认 handler
    logger.remove()
    
    # 控制台输出
    if console:
        logger.add(
            sys.stderr,
            level=level,
            format=format_console,
            filter=job_context_filter,
            colorize=True,
        )
    
    # 文件输出
    if file:
        log_dir = get_log_dir()
        logger.add(
            log_dir / "backend.log",
            level=level,
            format=format_file,
            filter=job_context_filter,
            rotation=rotation,
            retention=retention,
            encoding="utf-8",
        )
    
    # JSON 格式（用于日志分析）
    if json_file:
        log_dir = get_log_dir()
        logger.add(
            log_dir / "backend.json",
            level=level,
            format="{message}",
            filter=job_context_filter,
            rotation=rotation,
            retention=retention,
            serialize=True,
        )
    
    logger.info(f"Logging configured: level={level}, console={console}, file={file}")


# ─────────────── Job Logger ───────────────

class JobLogger:
    """
    任务级别日志器
    
    自动关联任务 ID，支持写入任务专属日志文件。
    
    Usage:
        with JobLogger(job_id) as log:
            log.info("Starting task...")
            log.debug("Processing step 1")
    """
    
    def __init__(self, job_id: str, job_dir: Path | None = None):
        self.job_id = job_id
        self.job_dir = job_dir
        self._token: Any = None
        self._file_handler_id: int | None = None
    
    def __enter__(self) -> "JobLogger":
        self._token = current_job_id.set(self.job_id)
        
        # 添加任务专属日志文件
        if self.job_dir:
            log_path = self.job_dir / "logs" / "job.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            self._file_handler_id = logger.add(
                log_path,
                level="DEBUG",
                format=format_file,
                filter=lambda r: r["extra"].get("job_id") == self.job_id,
                encoding="utf-8",
            )
        
        return self
    
    def __exit__(self, *args: Any) -> None:
        if self._token:
            current_job_id.reset(self._token)
        if self._file_handler_id is not None:
            logger.remove(self._file_handler_id)
    
    def debug(self, msg: str, **kwargs: Any) -> None:
        logger.debug(msg, **kwargs)
    
    def info(self, msg: str, **kwargs: Any) -> None:
        logger.info(msg, **kwargs)
    
    def warning(self, msg: str, **kwargs: Any) -> None:
        logger.warning(msg, **kwargs)
    
    def error(self, msg: str, **kwargs: Any) -> None:
        logger.error(msg, **kwargs)
    
    def exception(self, msg: str, **kwargs: Any) -> None:
        logger.exception(msg, **kwargs)
    
    def success(self, msg: str, **kwargs: Any) -> None:
        logger.success(msg, **kwargs)


# ─────────────── Decorators ───────────────

def log_execution(
    level: str = "DEBUG",
    include_args: bool = False,
    include_result: bool = False,
) -> Callable:
    """
    记录函数执行的装饰器
    
    Args:
        level: 日志级别
        include_args: 是否记录参数
        include_result: 是否记录返回值
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            func_name = f"{func.__module__}.{func.__name__}"
            
            # 开始日志
            if include_args:
                logger.log(level, f"CALL {func_name}(args={args}, kwargs={kwargs})")
            else:
                logger.log(level, f"CALL {func_name}()")
            
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                
                if include_result:
                    logger.log(level, f"DONE {func_name} returned {result!r} in {elapsed:.3f}s")
                else:
                    logger.log(level, f"DONE {func_name} completed in {elapsed:.3f}s")
                
                return result
            except Exception as e:
                elapsed = time.perf_counter() - start
                logger.error(f"FAIL {func_name} failed after {elapsed:.3f}s: {e}")
                raise
        
        return wrapper
    return decorator


def timed(name: str | None = None) -> Callable:
    """
    计时装饰器
    
    Usage:
        @timed("process_images")
        def heavy_work():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            label = name or func.__name__
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                logger.debug(f"⏱ {label}: {elapsed:.3f}s")
        return wrapper
    return decorator


# ─────────────── Convenience Exports ───────────────

# 直接导出 loguru logger 供简单使用
log = logger

__all__ = [
    "logger",
    "log",
    "setup_logging",
    "get_log_dir",
    "JobLogger",
    "current_job_id",
    "log_execution",
    "timed",
]
