# ═══════════════════════════════════════════════════════════════
# Runner Base Tests — 执行器基类测试
# ═══════════════════════════════════════════════════════════════
"""
测试 backend/runner_base.py:
- RunnerPhase 枚举
- RunnerProgress 数据类
- RunnerResult 数据类
- RunnerBase 抽象类
- Runner 注册机制
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).parent.parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class TestRunnerPhase:
    """执行阶段枚举测试"""
    
    def test_phase_values(self):
        """阶段值正确"""
        from runner_base import RunnerPhase
        
        assert RunnerPhase.INIT.value == "init"
        assert RunnerPhase.EXECUTING.value == "executing"
        assert RunnerPhase.COMPLETED.value == "completed"
        assert RunnerPhase.FAILED.value == "failed"


class TestRunnerProgress:
    """执行进度测试"""
    
    def test_create_progress(self):
        """创建进度对象"""
        from runner_base import RunnerPhase, RunnerProgress
        
        progress = RunnerProgress(phase=RunnerPhase.INIT)
        
        assert progress.phase == RunnerPhase.INIT
        assert progress.progress == 0.0
        assert progress.message == ""
    
    def test_update_progress(self):
        """更新进度"""
        from runner_base import RunnerPhase, RunnerProgress
        
        progress = RunnerProgress(phase=RunnerPhase.EXECUTING)
        progress.update(0.5, "Processing...")
        
        assert progress.progress == 0.5
        assert progress.message == "Processing..."
    
    def test_progress_bounds(self):
        """进度值边界"""
        from runner_base import RunnerPhase, RunnerProgress
        
        progress = RunnerProgress(phase=RunnerPhase.EXECUTING)
        
        progress.update(1.5)  # 超过 1.0
        assert progress.progress == 1.0
        
        progress.update(-0.5)  # 低于 0.0
        assert progress.progress == 0.0
    
    def test_to_dict(self):
        """序列化为字典"""
        from runner_base import RunnerPhase, RunnerProgress
        
        progress = RunnerProgress(phase=RunnerPhase.UPLOADING, progress=0.3)
        data = progress.to_dict()
        
        assert data["phase"] == "uploading"
        assert data["progress"] == 0.3
        assert "started_at" in data
        assert "updated_at" in data


class TestRunnerResult:
    """执行结果测试"""
    
    def test_success_result(self):
        """成功结果"""
        from runner_base import RunnerPhase, RunnerResult
        
        result = RunnerResult(
            success=True,
            phase=RunnerPhase.COMPLETED,
            output_files=["output.ply"],
            duration_seconds=10.5,
        )
        
        assert result.success
        assert result.phase == RunnerPhase.COMPLETED
        assert len(result.output_files) == 1
        assert result.error_message is None
    
    def test_failed_result(self):
        """失败结果"""
        from runner_base import RunnerPhase, RunnerResult
        
        result = RunnerResult(
            success=False,
            phase=RunnerPhase.FAILED,
            error_message="CUDA out of memory",
        )
        
        assert not result.success
        assert result.phase == RunnerPhase.FAILED
        assert "CUDA" in result.error_message
    
    def test_to_dict(self):
        """序列化为字典"""
        from runner_base import RunnerPhase, RunnerResult
        
        result = RunnerResult(
            success=True,
            phase=RunnerPhase.COMPLETED,
            metrics={"accuracy": 0.95},
        )
        data = result.to_dict()
        
        assert data["success"] is True
        assert data["phase"] == "completed"
        assert data["metrics"]["accuracy"] == 0.95


class TestRunnerRegistry:
    """Runner 注册机制测试"""
    
    def test_register_runner(self):
        """注册 Runner"""
        from runner_base import RunnerBase, register_runner, available_runners
        
        @register_runner("test_runner")
        class TestRunner(RunnerBase):
            def prepare(self): pass
            def upload(self): pass
            def execute(self): pass
            def download(self): return []
            def cleanup(self): pass
        
        assert "test_runner" in available_runners()
    
    def test_get_runner(self):
        """获取 Runner 实例"""
        from runner_base import RunnerBase, register_runner, get_runner
        
        @register_runner("mock_runner")
        class MockRunner(RunnerBase):
            def prepare(self): pass
            def upload(self): pass
            def execute(self): pass
            def download(self): return ["output.ply"]
            def cleanup(self): pass
        
        runner = get_runner("mock_runner", job_id="test_001", model="monst3r")
        
        assert runner.job_id == "test_001"
        assert runner.model == "monst3r"
    
    def test_unknown_runner_raises(self):
        """未知 Runner 类型报错"""
        from runner_base import get_runner
        
        with pytest.raises(ValueError, match="Unknown runner type"):
            get_runner("nonexistent", job_id="test", model="test")


class TestRunnerBase:
    """Runner 基类测试"""
    
    def test_run_success(self):
        """完整执行流程"""
        from runner_base import RunnerBase, RunnerPhase, register_runner
        
        execution_order = []
        
        @register_runner("sequence_runner")
        class SequenceRunner(RunnerBase):
            def prepare(self):
                execution_order.append("prepare")
            def upload(self):
                execution_order.append("upload")
            def execute(self):
                execution_order.append("execute")
            def download(self):
                execution_order.append("download")
                return ["result.ply"]
            def cleanup(self):
                execution_order.append("cleanup")
        
        runner = SequenceRunner(job_id="test", model="test")
        result = runner.run()
        
        assert result.success
        assert result.phase == RunnerPhase.COMPLETED
        assert execution_order == ["prepare", "upload", "execute", "download", "cleanup"]
    
    def test_run_failure(self):
        """执行失败"""
        from runner_base import RunnerBase, RunnerPhase, register_runner
        
        @register_runner("fail_runner")
        class FailRunner(RunnerBase):
            def prepare(self): pass
            def upload(self): pass
            def execute(self):
                raise RuntimeError("Execution failed")
            def download(self): return []
            def cleanup(self): pass
        
        runner = FailRunner(job_id="test", model="test")
        result = runner.run()
        
        assert not result.success
        assert result.phase == RunnerPhase.FAILED
        assert "Execution failed" in result.error_message
    
    def test_cancel(self):
        """取消执行"""
        from runner_base import RunnerBase, RunnerPhase, register_runner
        
        @register_runner("cancel_runner")
        class CancelRunner(RunnerBase):
            def prepare(self):
                self.cancel()  # 立即取消
            def upload(self): pass
            def execute(self): pass
            def download(self): return []
            def cleanup(self): pass
        
        runner = CancelRunner(job_id="test", model="test")
        result = runner.run()
        
        assert not result.success
        assert result.phase == RunnerPhase.CANCELLED
    
    def test_progress_callback(self):
        """进度回调"""
        from runner_base import RunnerBase, RunnerProgress, register_runner
        
        progress_updates = []
        
        @register_runner("progress_runner")
        class ProgressRunner(RunnerBase):
            def prepare(self): pass
            def upload(self): pass
            def execute(self): pass
            def download(self): return []
            def cleanup(self): pass
        
        def on_progress(p: RunnerProgress):
            progress_updates.append(p.phase.value)
        
        runner = ProgressRunner(job_id="test", model="test", on_progress=on_progress)
        runner.run()
        
        assert "preparing" in progress_updates
        assert "executing" in progress_updates
        assert "completed" in progress_updates
