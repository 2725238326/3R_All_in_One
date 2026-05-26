# ═══════════════════════════════════════════════════════════════
# Retry Policy Tests
# ═══════════════════════════════════════════════════════════════
"""
测试 backend/retry_policy.py:
- 重试策略
- 指数退避
- 错误分类
- 重试状态管理
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch
import time

import pytest

BACKEND_DIR = Path(__file__).parent.parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class TestRetryPolicy:
    """重试策略测试"""
    
    def test_default_policy(self):
        """默认策略"""
        from retry_policy import RetryPolicy
        
        policy = RetryPolicy()
        
        assert policy.max_attempts == 3
        assert policy.base_delay == 5.0
        assert policy.max_delay == 300.0
    
    def test_calculate_delay_exponential(self):
        """指数退避延迟"""
        from retry_policy import RetryPolicy
        
        policy = RetryPolicy(base_delay=1.0, exponential_base=2.0)
        
        assert policy.calculate_delay(1) == 1.0   # 1 * 2^0
        assert policy.calculate_delay(2) == 2.0   # 1 * 2^1
        assert policy.calculate_delay(3) == 4.0   # 1 * 2^2
        assert policy.calculate_delay(4) == 8.0   # 1 * 2^3
    
    def test_calculate_delay_max_cap(self):
        """延迟上限"""
        from retry_policy import RetryPolicy
        
        policy = RetryPolicy(base_delay=100.0, max_delay=200.0)
        
        # 第 3 次: 100 * 4 = 400，应该被限制为 200
        assert policy.calculate_delay(3) == 200.0
    
    def test_should_retry_retryable_error(self):
        """可重试错误"""
        from retry_policy import RetryPolicy, RetryableError
        
        policy = RetryPolicy()
        
        assert policy.should_retry(RetryableError("temp"))
        assert policy.should_retry(ConnectionError("connection reset"))
        assert policy.should_retry(TimeoutError("timeout"))
    
    def test_should_retry_non_retryable_error(self):
        """不可重试错误"""
        from retry_policy import RetryPolicy, NonRetryableError
        
        policy = RetryPolicy()
        
        assert not policy.should_retry(NonRetryableError("invalid param"))
    
    def test_should_retry_keyword_match(self):
        """关键词匹配"""
        from retry_policy import RetryPolicy
        
        policy = RetryPolicy()
        
        assert policy.should_retry(RuntimeError("SSH connection failed"))
        assert policy.should_retry(RuntimeError("Network timeout"))
        assert policy.should_retry(RuntimeError("OOM killed"))


class TestRetryReason:
    """错误分类测试"""
    
    def test_classify_ssh_connection(self):
        """SSH 连接错误"""
        from retry_policy import RetryPolicy, RetryReason
        
        policy = RetryPolicy()
        
        reason = policy.classify_error(RuntimeError("SSH connect failed"))
        assert reason == RetryReason.SSH_CONNECTION
    
    def test_classify_oom(self):
        """OOM 错误"""
        from retry_policy import RetryPolicy, RetryReason
        
        policy = RetryPolicy()
        
        reason = policy.classify_error(RuntimeError("Out of memory"))
        assert reason == RetryReason.REMOTE_OOM
    
    def test_classify_timeout(self):
        """超时错误"""
        from retry_policy import RetryPolicy, RetryReason
        
        policy = RetryPolicy()
        
        reason = policy.classify_error(RuntimeError("Request timeout"))
        assert reason == RetryReason.REMOTE_TIMEOUT


class TestRetryState:
    """重试状态测试"""
    
    def test_record_attempt(self):
        """记录重试"""
        from retry_policy import RetryState, RetryReason
        
        state = RetryState(job_id="test_001", max_attempts=3)
        
        state.record_attempt("error 1", RetryReason.SSH_CONNECTION, 5.0)
        
        assert state.current_attempt == 1
        assert len(state.history) == 1
        assert state.can_retry
    
    def test_exhausted(self):
        """重试耗尽"""
        from retry_policy import RetryState, RetryReason
        
        state = RetryState(job_id="test_002", max_attempts=2)
        
        state.record_attempt("error 1", RetryReason.NETWORK_ERROR, 5.0)
        assert state.can_retry
        
        state.record_attempt("error 2", RetryReason.NETWORK_ERROR, 10.0)
        assert not state.can_retry
        assert state.exhausted
    
    def test_to_dict(self):
        """序列化"""
        from retry_policy import RetryState, RetryReason
        
        state = RetryState(job_id="test_003", max_attempts=3)
        state.record_attempt("test error", RetryReason.UNKNOWN, 5.0)
        
        data = state.to_dict()
        
        assert data["job_id"] == "test_003"
        assert data["current_attempt"] == 1
        assert len(data["history"]) == 1


class TestRetryStateManagement:
    """重试状态管理测试"""
    
    def test_get_retry_state(self):
        """获取重试状态"""
        from retry_policy import get_retry_state, clear_retry_state
        
        state = get_retry_state("job_001")
        
        assert state.job_id == "job_001"
        assert state.current_attempt == 0
        
        # 清理
        clear_retry_state("job_001")
    
    def test_get_same_state(self):
        """获取同一状态"""
        from retry_policy import get_retry_state, clear_retry_state, RetryReason
        
        state1 = get_retry_state("job_002")
        state1.record_attempt("error", RetryReason.UNKNOWN, 5.0)
        
        state2 = get_retry_state("job_002")
        
        assert state2.current_attempt == 1
        
        clear_retry_state("job_002")
    
    def test_clear_retry_state(self):
        """清除重试状态"""
        from retry_policy import get_retry_state, clear_retry_state, all_retry_states
        
        get_retry_state("job_003")
        clear_retry_state("job_003")
        
        assert "job_003" not in all_retry_states()


class TestWithRetryDecorator:
    """with_retry 装饰器测试"""
    
    def test_success_no_retry(self):
        """成功不重试"""
        from retry_policy import with_retry, RetryPolicy
        
        call_count = 0
        
        @with_retry(policy=RetryPolicy(max_attempts=3))
        def success_func():
            nonlocal call_count
            call_count += 1
            return "ok"
        
        result = success_func()
        
        assert result == "ok"
        assert call_count == 1
    
    def test_retry_then_success(self):
        """重试后成功"""
        from retry_policy import with_retry, RetryPolicy, RetryableError
        
        call_count = 0
        
        @with_retry(policy=RetryPolicy(max_attempts=3, base_delay=0.01))
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RetryableError("temp error")
            return "ok"
        
        result = flaky_func()
        
        assert result == "ok"
        assert call_count == 2
    
    def test_max_attempts_exhausted(self):
        """重试耗尽"""
        from retry_policy import with_retry, RetryPolicy, RetryableError
        
        call_count = 0
        
        @with_retry(policy=RetryPolicy(max_attempts=2, base_delay=0.01))
        def always_fail():
            nonlocal call_count
            call_count += 1
            raise RetryableError("always fails")
        
        with pytest.raises(RetryableError):
            always_fail()
        
        assert call_count == 2
    
    def test_non_retryable_no_retry(self):
        """不可重试错误直接抛出"""
        from retry_policy import with_retry, RetryPolicy, NonRetryableError
        
        call_count = 0
        
        @with_retry(policy=RetryPolicy(max_attempts=3))
        def bad_params():
            nonlocal call_count
            call_count += 1
            raise NonRetryableError("invalid input")
        
        with pytest.raises(NonRetryableError):
            bad_params()
        
        assert call_count == 1
