# ═══════════════════════════════════════════════════════════════
# Retry Policy — 任务重试策略
# ═══════════════════════════════════════════════════════════════
"""
任务自动重试机制，支持：
- 指数退避重试
- 可配置重试条件
- 重试历史记录
- 最大重试次数限制
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, TypeVar
from functools import wraps

from logging_config import log


class RetryableError(Exception):
    """可重试的错误"""
    pass


class NonRetryableError(Exception):
    """不可重试的错误（如参数错误）"""
    pass


class RetryReason(str, Enum):
    """重试原因"""
    SSH_CONNECTION = "ssh_connection"       # SSH 连接失败
    SSH_TIMEOUT = "ssh_timeout"             # SSH 超时
    NETWORK_ERROR = "network_error"         # 网络错误
    REMOTE_OOM = "remote_oom"               # 远程 OOM
    REMOTE_TIMEOUT = "remote_timeout"       # 远程执行超时
    TRANSIENT_ERROR = "transient_error"     # 临时错误
    UNKNOWN = "unknown"                     # 未知错误


@dataclass
class RetryAttempt:
    """单次重试记录"""
    attempt: int
    timestamp: str
    error: str
    reason: RetryReason
    delay_seconds: float


@dataclass
class RetryState:
    """任务重试状态"""
    job_id: str
    max_attempts: int = 3
    current_attempt: int = 0
    history: list[RetryAttempt] = field(default_factory=list)
    exhausted: bool = False
    
    def record_attempt(self, error: str, reason: RetryReason, delay: float) -> None:
        """记录一次重试"""
        self.current_attempt += 1
        self.history.append(RetryAttempt(
            attempt=self.current_attempt,
            timestamp=datetime.now().isoformat(),
            error=error,
            reason=reason,
            delay_seconds=delay,
        ))
        if self.current_attempt >= self.max_attempts:
            self.exhausted = True
    
    @property
    def can_retry(self) -> bool:
        """是否还可以重试"""
        return not self.exhausted
    
    def to_dict(self) -> dict:
        """序列化"""
        return {
            "job_id": self.job_id,
            "max_attempts": self.max_attempts,
            "current_attempt": self.current_attempt,
            "exhausted": self.exhausted,
            "history": [
                {
                    "attempt": a.attempt,
                    "timestamp": a.timestamp,
                    "error": a.error,
                    "reason": a.reason.value,
                    "delay_seconds": a.delay_seconds,
                }
                for a in self.history
            ],
        }


@dataclass
class RetryPolicy:
    """
    重试策略配置
    
    Args:
        max_attempts: 最大重试次数
        base_delay: 基础延迟（秒）
        max_delay: 最大延迟（秒）
        exponential_base: 指数退避基数
        retryable_errors: 可重试的错误类型
    """
    max_attempts: int = 3
    base_delay: float = 5.0
    max_delay: float = 300.0  # 5 分钟
    exponential_base: float = 2.0
    retryable_errors: tuple[type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        RetryableError,
    )
    
    def calculate_delay(self, attempt: int) -> float:
        """计算第 N 次重试的延迟"""
        delay = self.base_delay * (self.exponential_base ** (attempt - 1))
        return min(delay, self.max_delay)
    
    def should_retry(self, error: Exception) -> bool:
        """判断错误是否可重试"""
        if isinstance(error, NonRetryableError):
            return False
        if isinstance(error, self.retryable_errors):
            return True
        # 检查错误消息中的关键词
        error_msg = str(error).lower()
        retryable_keywords = [
            "connection",
            "timeout",
            "temporarily",
            "network",
            "ssh",
            "oom",
            "memory",
        ]
        return any(kw in error_msg for kw in retryable_keywords)
    
    def classify_error(self, error: Exception) -> RetryReason:
        """分类错误原因"""
        error_msg = str(error).lower()
        
        if "ssh" in error_msg and "connect" in error_msg:
            return RetryReason.SSH_CONNECTION
        if "ssh" in error_msg and "timeout" in error_msg:
            return RetryReason.SSH_TIMEOUT
        if "oom" in error_msg or "out of memory" in error_msg:
            return RetryReason.REMOTE_OOM
        if "timeout" in error_msg:
            return RetryReason.REMOTE_TIMEOUT
        if "network" in error_msg or "connection" in error_msg:
            return RetryReason.NETWORK_ERROR
        if isinstance(error, RetryableError):
            return RetryReason.TRANSIENT_ERROR
        
        return RetryReason.UNKNOWN


# ─────────────── 全局重试状态存储 ───────────────

_retry_states: dict[str, RetryState] = {}


def get_retry_state(job_id: str, policy: RetryPolicy | None = None) -> RetryState:
    """获取或创建任务的重试状态"""
    if job_id not in _retry_states:
        max_attempts = policy.max_attempts if policy else 3
        _retry_states[job_id] = RetryState(job_id=job_id, max_attempts=max_attempts)
    return _retry_states[job_id]


def clear_retry_state(job_id: str) -> None:
    """清除任务的重试状态（任务成功后调用）"""
    _retry_states.pop(job_id, None)


def all_retry_states() -> dict[str, RetryState]:
    """获取所有重试状态"""
    return _retry_states.copy()


# ─────────────── 重试执行器 ───────────────

T = TypeVar("T")


def with_retry(
    policy: RetryPolicy | None = None,
    job_id: str | None = None,
) -> Callable:
    """
    重试装饰器
    
    Usage:
        @with_retry(policy=RetryPolicy(max_attempts=3))
        def run_job(job_id: str):
            ...
    """
    if policy is None:
        policy = RetryPolicy()
    
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            # 尝试从参数获取 job_id
            actual_job_id = job_id or kwargs.get("job_id") or (args[0] if args else None)
            state = get_retry_state(str(actual_job_id), policy) if actual_job_id else None
            
            last_error: Exception | None = None
            
            for attempt in range(1, policy.max_attempts + 1):
                try:
                    result = func(*args, **kwargs)
                    # 成功，清除重试状态
                    if state:
                        clear_retry_state(state.job_id)
                    return result
                except Exception as e:
                    last_error = e
                    
                    if not policy.should_retry(e):
                        log.error(f"Non-retryable error: {e}")
                        raise
                    
                    if attempt >= policy.max_attempts:
                        log.error(f"Max retry attempts ({policy.max_attempts}) exhausted")
                        if state:
                            state.exhausted = True
                        raise
                    
                    delay = policy.calculate_delay(attempt)
                    reason = policy.classify_error(e)
                    
                    if state:
                        state.record_attempt(str(e), reason, delay)
                    
                    log.warning(
                        f"Attempt {attempt}/{policy.max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    
                    time.sleep(delay)
            
            # 不应该到达这里
            if last_error:
                raise last_error
            raise RuntimeError("Unexpected retry loop exit")
        
        return wrapper
    return decorator


async def retry_async(
    func: Callable[..., T],
    *args,
    policy: RetryPolicy | None = None,
    job_id: str | None = None,
    **kwargs,
) -> T:
    """
    异步重试执行
    
    Usage:
        result = await retry_async(
            some_async_func,
            arg1, arg2,
            policy=RetryPolicy(max_attempts=3),
            job_id="xxx"
        )
    """
    import asyncio
    
    if policy is None:
        policy = RetryPolicy()
    
    state = get_retry_state(job_id, policy) if job_id else None
    last_error: Exception | None = None
    
    for attempt in range(1, policy.max_attempts + 1):
        try:
            result = await func(*args, **kwargs)
            if state:
                clear_retry_state(state.job_id)
            return result
        except Exception as e:
            last_error = e
            
            if not policy.should_retry(e):
                raise
            
            if attempt >= policy.max_attempts:
                if state:
                    state.exhausted = True
                raise
            
            delay = policy.calculate_delay(attempt)
            reason = policy.classify_error(e)
            
            if state:
                state.record_attempt(str(e), reason, delay)
            
            log.warning(
                f"Async attempt {attempt}/{policy.max_attempts} failed: {e}. "
                f"Retrying in {delay:.1f}s..."
            )
            
            await asyncio.sleep(delay)
    
    if last_error:
        raise last_error
    raise RuntimeError("Unexpected retry loop exit")


__all__ = [
    "RetryableError",
    "NonRetryableError",
    "RetryReason",
    "RetryAttempt",
    "RetryState",
    "RetryPolicy",
    "get_retry_state",
    "clear_retry_state",
    "all_retry_states",
    "with_retry",
    "retry_async",
]
