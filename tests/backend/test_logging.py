# ═══════════════════════════════════════════════════════════════
# Logging Tests
# ═══════════════════════════════════════════════════════════════
"""
测试 backend/logging_config.py:
- 日志配置
- JobLogger 上下文
- 装饰器
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import tempfile

import pytest

BACKEND_DIR = Path(__file__).parent.parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class TestLoggingSetup:
    """日志配置测试"""
    
    def test_get_log_dir(self):
        """获取日志目录"""
        from logging_config import get_log_dir
        
        log_dir = get_log_dir()
        
        assert log_dir.exists()
        assert "3R_All_in_One" in str(log_dir)
    
    def test_setup_logging_console_only(self):
        """仅控制台日志"""
        from logging_config import setup_logging, logger
        
        # 不应抛出异常
        setup_logging(level="DEBUG", console=True, file=False)
        
        logger.info("Test message")
    
    def test_setup_logging_with_file(self):
        """文件日志"""
        from logging_config import setup_logging, get_log_dir, logger
        
        setup_logging(level="INFO", console=False, file=True)
        
        log_file = get_log_dir() / "backend.log"
        logger.info("File log test")
        
        # 日志文件应该存在
        assert log_file.exists()


class TestJobLogger:
    """JobLogger 测试"""
    
    def test_job_logger_context(self):
        """任务日志上下文"""
        from logging_config import JobLogger, current_job_id
        
        assert current_job_id.get() is None
        
        with JobLogger("test_job_123") as log:
            assert current_job_id.get() == "test_job_123"
            log.info("Inside job context")
        
        assert current_job_id.get() is None
    
    def test_job_logger_with_dir(self):
        """任务日志写入专属目录"""
        from logging_config import JobLogger
        
        with tempfile.TemporaryDirectory() as tmpdir:
            job_dir = Path(tmpdir)
            
            with JobLogger("test_job_456", job_dir=job_dir) as log:
                log.info("Test message in job dir")
            
            log_file = job_dir / "logs" / "job.log"
            assert log_file.exists()
            content = log_file.read_text()
            assert "Test message in job dir" in content
    
    def test_job_logger_levels(self):
        """不同日志级别"""
        from logging_config import JobLogger
        
        with JobLogger("test_levels") as log:
            log.debug("Debug message")
            log.info("Info message")
            log.warning("Warning message")
            log.error("Error message")
            log.success("Success message")


class TestDecorators:
    """装饰器测试"""
    
    def test_log_execution(self):
        """log_execution 装饰器"""
        from logging_config import log_execution
        
        @log_execution(level="DEBUG")
        def sample_func(x, y):
            return x + y
        
        result = sample_func(1, 2)
        
        assert result == 3
    
    def test_log_execution_with_args(self):
        """log_execution 记录参数"""
        from logging_config import log_execution
        
        @log_execution(level="DEBUG", include_args=True, include_result=True)
        def multiply(a, b):
            return a * b
        
        result = multiply(3, 4)
        
        assert result == 12
    
    def test_log_execution_exception(self):
        """log_execution 异常处理"""
        from logging_config import log_execution
        
        @log_execution()
        def failing_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            failing_func()
    
    def test_timed_decorator(self):
        """timed 装饰器"""
        from logging_config import timed
        import time
        
        @timed("test_operation")
        def slow_func():
            time.sleep(0.01)
            return "done"
        
        result = slow_func()
        
        assert result == "done"


class TestCurrentJobId:
    """current_job_id 上下文变量测试"""
    
    def test_nested_contexts(self):
        """嵌套上下文"""
        from logging_config import JobLogger, current_job_id
        
        with JobLogger("outer_job"):
            assert current_job_id.get() == "outer_job"
            
            # 内层会覆盖
            with JobLogger("inner_job"):
                assert current_job_id.get() == "inner_job"
            
            # 恢复外层
            assert current_job_id.get() == "outer_job"
        
        assert current_job_id.get() is None
