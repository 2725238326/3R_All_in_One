# ═══════════════════════════════════════════════════════════════
# SSHRunner Tests
# ═══════════════════════════════════════════════════════════════
"""
测试 backend/runners/ssh.py:
- SSHRunner 初始化
- Runner 注册
- 基本属性
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

BACKEND_DIR = Path(__file__).parent.parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class TestSSHRunnerRegistration:
    """SSHRunner 注册测试"""
    
    def test_ssh_runner_registered(self):
        """SSH runner 已注册"""
        from runner_base import available_runners
        # 需要先导入来触发注册
        import runners.ssh  # noqa: F401
        
        assert "ssh" in available_runners()
    
    def test_get_ssh_runner(self):
        """通过工厂获取 SSHRunner"""
        from runner_base import get_runner
        import runners.ssh  # noqa: F401
        
        runner = get_runner("ssh", job_id="test_001", model="monst3r")
        
        assert runner.job_id == "test_001"
        assert runner.model == "monst3r"


class TestSSHRunnerInit:
    """SSHRunner 初始化测试"""
    
    def test_default_config(self):
        """使用默认配置"""
        from runners.ssh import SSHRunner
        
        runner = SSHRunner(job_id="test", model="dust3r")
        
        assert runner.config is not None
        assert runner.config.alias == "KYKT-UI"
    
    def test_custom_config(self):
        """使用自定义配置"""
        from runners.ssh import SSHRunner
        from ssh_runner import ServerConfig
        
        custom_config = ServerConfig(
            alias="custom-server",
            host="192.168.1.100",
            user="testuser",
        )
        
        runner = SSHRunner(
            job_id="test",
            model="dust3r",
            config=custom_config,
        )
        
        assert runner.config.alias == "custom-server"
        assert runner.config.host == "192.168.1.100"
    
    def test_params(self):
        """参数传递"""
        from runners.ssh import SSHRunner
        
        params = {"resolution": 512, "scenegraph_type": "complete"}
        runner = SSHRunner(job_id="test", model="monst3r", params=params)
        
        assert runner.params["resolution"] == 512


class TestSSHRunnerProgress:
    """SSHRunner 进度回调测试"""
    
    def test_progress_callback(self):
        """进度回调触发"""
        from runners.ssh import SSHRunner
        from runner_base import RunnerProgress
        
        progress_updates = []
        
        def on_progress(p: RunnerProgress):
            progress_updates.append(p.phase.value)
        
        runner = SSHRunner(
            job_id="test",
            model="dust3r",
            on_progress=on_progress,
        )
        
        # 手动触发进度更新
        runner._update_progress(0.5, "Testing...")
        
        assert len(progress_updates) == 1


class TestSSHRunnerFromJobId:
    """SSHRunner.from_job_id 测试"""
    
    @patch("runners.ssh.load_job")
    def test_from_job_id(self, mock_load_job):
        """从 job_id 创建 Runner"""
        from runners.ssh import SSHRunner
        
        mock_job = MagicMock()
        mock_job.model = "monst3r"
        mock_job.params = {"winsize": 5}
        mock_load_job.return_value = mock_job
        
        runner = SSHRunner.from_job_id("test_job_123")
        
        assert runner.job_id == "test_job_123"
        assert runner.model == "monst3r"
        assert runner.params["winsize"] == 5
