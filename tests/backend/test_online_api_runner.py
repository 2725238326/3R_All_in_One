# ═══════════════════════════════════════════════════════════════
# OnlineAPIRunner Tests
# ═══════════════════════════════════════════════════════════════
"""
测试 backend/runners/online_api.py:
- API 配置
- Runner 注册
- Provider 逻辑
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import os

import pytest

BACKEND_DIR = Path(__file__).parent.parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class TestAPIConfig:
    """API 配置测试"""
    
    def test_api_provider_enum(self):
        """API 提供商枚举"""
        from runners.online_api import APIProvider
        
        assert APIProvider.HUGGINGFACE.value == "huggingface"
        assert APIProvider.REPLICATE.value == "replicate"
        assert APIProvider.CUSTOM.value == "custom"
    
    def test_api_endpoint(self):
        """API 端点配置"""
        from runners.online_api import APIEndpoint, APIProvider
        
        endpoint = APIEndpoint(
            provider=APIProvider.HUGGINGFACE,
            url="https://api.example.com",
            model_id="test/model",
            api_key="test_key",
        )
        
        assert endpoint.provider == APIProvider.HUGGINGFACE
        assert endpoint.api_key == "test_key"
        assert endpoint.timeout == 600
    
    def test_online_api_config(self):
        """在线 API 配置"""
        from runners.online_api import OnlineAPIConfig, APIEndpoint, APIProvider
        
        config = OnlineAPIConfig()
        config.endpoints["test_model"] = APIEndpoint(
            provider=APIProvider.CUSTOM,
            url="https://custom.api.com",
            model_id="custom",
        )
        
        assert config.get_endpoint("test_model") is not None
        assert config.get_endpoint("unknown") is None
    
    @patch.dict(os.environ, {"HF_TOKEN": "test_hf_token"}, clear=False)
    def test_config_from_env_hf(self):
        """从环境变量加载 HF 配置"""
        from runners.online_api import OnlineAPIConfig
        
        config = OnlineAPIConfig.from_env()
        
        endpoint = config.get_endpoint("dust3r")
        assert endpoint is not None
        assert endpoint.api_key == "test_hf_token"


class TestOnlineAPIRunnerRegistration:
    """OnlineAPIRunner 注册测试"""
    
    def test_online_api_runner_registered(self):
        """Online API runner 已注册"""
        from runner_base import available_runners
        import runners.online_api  # noqa: F401
        
        assert "online_api" in available_runners()
    
    def test_get_online_api_runner(self):
        """通过工厂获取 OnlineAPIRunner"""
        from runner_base import get_runner
        import runners.online_api  # noqa: F401
        
        runner = get_runner("online_api", job_id="test_001", model="dust3r")
        
        assert runner.job_id == "test_001"
        assert runner.model == "dust3r"


class TestOnlineAPIRunnerInit:
    """OnlineAPIRunner 初始化测试"""
    
    def test_default_config(self):
        """使用默认配置"""
        from runners.online_api import OnlineAPIRunner
        
        runner = OnlineAPIRunner(job_id="test", model="dust3r")
        
        assert runner.config is not None
    
    def test_custom_config(self):
        """使用自定义配置"""
        from runners.online_api import OnlineAPIRunner, OnlineAPIConfig
        
        custom_config = OnlineAPIConfig(
            default_timeout=300,
            max_file_size_mb=100,
        )
        
        runner = OnlineAPIRunner(
            job_id="test",
            model="dust3r",
            config=custom_config,
        )
        
        assert runner.config.default_timeout == 300
        assert runner.config.max_file_size_mb == 100


class TestResultSaving:
    """结果保存测试"""
    
    def test_guess_extension_png(self):
        """猜测 PNG 扩展名"""
        from runners.online_api import OnlineAPIRunner
        
        runner = OnlineAPIRunner(job_id="test", model="dust3r")
        
        ext = runner._guess_extension("data:image/png;base64")
        assert ext == ".png"
    
    def test_guess_extension_jpeg(self):
        """猜测 JPEG 扩展名"""
        from runners.online_api import OnlineAPIRunner
        
        runner = OnlineAPIRunner(job_id="test", model="dust3r")
        
        ext = runner._guess_extension("data:image/jpeg;base64")
        assert ext == ".jpg"
    
    def test_guess_extension_glb(self):
        """猜测 GLB 扩展名"""
        from runners.online_api import OnlineAPIRunner
        
        runner = OnlineAPIRunner(job_id="test", model="dust3r")
        
        ext = runner._guess_extension("data:model/glb;base64")
        assert ext == ".glb"
    
    def test_guess_extension_unknown(self):
        """未知类型默认 .bin"""
        from runners.online_api import OnlineAPIRunner
        
        runner = OnlineAPIRunner(job_id="test", model="dust3r")
        
        ext = runner._guess_extension("data:application/unknown;base64")
        assert ext == ".bin"


class TestAvailableProviders:
    """可用提供商测试"""
    
    @patch.dict(os.environ, {}, clear=True)
    def test_no_providers(self):
        """无可用提供商"""
        from runners.online_api import OnlineAPIRunner
        
        providers = OnlineAPIRunner.available_providers()
        
        assert providers == []
    
    @patch.dict(os.environ, {"HF_TOKEN": "test"}, clear=True)
    def test_hf_provider(self):
        """HuggingFace 提供商"""
        from runners.online_api import OnlineAPIRunner
        
        providers = OnlineAPIRunner.available_providers()
        
        assert "huggingface" in providers
    
    @patch.dict(os.environ, {"REPLICATE_API_TOKEN": "test"}, clear=True)
    def test_replicate_provider(self):
        """Replicate 提供商"""
        from runners.online_api import OnlineAPIRunner
        
        providers = OnlineAPIRunner.available_providers()
        
        assert "replicate" in providers
