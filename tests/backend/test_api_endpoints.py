# ═══════════════════════════════════════════════════════════════
# API Endpoints Tests — FastAPI 端点测试
# ═══════════════════════════════════════════════════════════════
"""
测试 FastAPI 路由:
- /api/health
- /api/jobs/*
- /api/models/*
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoint:
    """健康检查端点测试"""
    
    def test_health_returns_200(self, test_client: TestClient):
        """健康检查应返回 200"""
        response = test_client.get("/api/health")
        assert response.status_code == 200
    
    def test_health_response_format(self, test_client: TestClient):
        """健康检查响应格式"""
        response = test_client.get("/api/health")
        data = response.json()
        
        assert "status" in data or isinstance(data, dict)


class TestJobsEndpoints:
    """任务相关端点测试"""
    
    def test_list_jobs(self, test_client: TestClient):
        """/api/jobs 应返回任务列表"""
        response = test_client.get("/api/jobs")
        assert response.status_code == 200
        
        data = response.json()
        assert "jobs" in data or isinstance(data, list)
    
    def test_get_nonexistent_job(self, test_client: TestClient):
        """获取不存在的任务应返回 404"""
        response = test_client.get("/api/jobs/nonexistent_job_id")
        assert response.status_code == 404
    
    @pytest.mark.skip(reason="需要完整的任务创建流程")
    def test_create_job(self, test_client: TestClient):
        """创建新任务"""
        payload = {
            "model": "monst3r",
            "source_type": "video",
            "params": {}
        }
        response = test_client.post("/api/jobs", json=payload)
        assert response.status_code in (200, 201)

    def test_create_dream3r_synthetic_without_files(self, test_client: TestClient):
        """Dream3R synthetic 演示模式不要求上传文件"""
        response = test_client.post(
            "/api/jobs",
            data={
                "model": "dream3r",
                "source_type": "proposal_cache",
                "params": json.dumps({"demo_mode": "synthetic"}),
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["job"]["model"] == "dream3r"
        assert data["job"]["source_type"] == "proposal_cache"
        assert data["job"]["params"]["demo_mode"] == "synthetic"
        assert data["job"]["input_files"] == []

    def test_create_dream3r_cache_requires_cache_file(self, test_client: TestClient):
        """Dream3R cache 模式创建阶段就提示缺少 proposal-cache 文件"""
        response = test_client.post(
            "/api/jobs",
            data={
                "model": "dream3r",
                "source_type": "proposal_cache",
                "params": json.dumps({"demo_mode": "cache"}),
            },
        )
        assert response.status_code == 400
        assert ".pt/.pth" in response.json()["detail"]


class TestModelsEndpoints:
    """模型相关端点测试"""
    
    def test_list_models(self, test_client: TestClient):
        """/api/models/catalog 应返回模型列表"""
        response = test_client.get("/api/models/catalog")
        assert response.status_code == 200

        models = {item["value"]: item for item in response.json()["models"]}
        assert models["align3r"]["runnable"] is False
        assert "runner" in models["align3r"]["launch_blocker"].lower()
    
    def test_get_model_contract(self, test_client: TestClient):
        """获取模型契约"""
        response = test_client.get("/api/models/monst3r/contract")
        # 可能返回 200 或 404（如果模型未配置）
        assert response.status_code in (200, 404)

    def test_align3r_catalog_only_contract(self, test_client: TestClient):
        """Align3R runner 未 smoke 前只保留目录条目，不开放创建。"""
        response = test_client.get("/api/models/align3r/contract")
        assert response.status_code == 200

        contract = response.json()
        assert contract["runnable"] is False
        assert contract["runner"]["downloadMode"] == "not_runnable"
        assert contract["runner"]["runnerFile"] is None
        assert contract["launchBlocker"]

    def test_align3r_validate_create_is_blocked(self, test_client: TestClient):
        """旧 UI 或手工请求不能绕过 catalog-only 阻塞。"""
        response = test_client.post(
            "/api/models/align3r/validate-create",
            json={"sourceType": "frames", "fileCount": 12},
        )
        assert response.status_code == 200

        payload = response.json()
        assert payload["ok"] is False
        assert payload["errors"]
        assert "目录模型" in payload["errors"][0]


class TestRunnerEndpoints:
    """执行器可用性端点测试"""

    def test_runner_availability_handles_optional_runners(self, test_client: TestClient):
        """/api/runners/availability 不应因缺少可选 runner 模块崩溃"""
        response = test_client.get("/api/runners/availability")
        assert response.status_code == 200

        data = response.json()
        assert data["ssh"] is True
        assert isinstance(data["docker"], bool)
        assert isinstance(data["online_api"], bool)


class TestAgentEndpoints:
    """Agent 蓝图与编排端点测试"""

    def test_agent_registry(self, test_client: TestClient):
        """/api/agent/registry 应返回所有模型蓝图"""
        response = test_client.get("/api/agent/registry")
        assert response.status_code == 200

        data = response.json()
        assert data["summary"]["total"] == 8
        assert len(data["models"]) == 8
        assert {model["key"] for model in data["models"]} >= {"dust3r", "monst3r", "fast3r", "dream3r"}

    def test_agent_model_detail(self, test_client: TestClient):
        """获取单个 Agent 蓝图详情"""
        response = test_client.get("/api/agent/registry/monst3r")
        assert response.status_code == 200

        data = response.json()
        assert data["key"] == "monst3r"
        assert data["environment"]["conda_env"] == "monst3r"
        assert "param_tiers" in data

    def test_agent_validate_all(self, test_client: TestClient):
        """校验所有 Agent 蓝图"""
        response = test_client.get("/api/agent/validate")
        assert response.status_code == 200

        data = response.json()
        assert data["ok"] is True
        assert data["summary"]["total"] == 8
        assert data["summary"]["errors"] == 0

    def test_agent_unknown_model(self, test_client: TestClient):
        """未知 Agent 模型应返回 404"""
        response = test_client.get("/api/agent/registry/not_a_model")
        assert response.status_code == 404


class TestStaticFiles:
    """静态文件端点测试"""
    
    def test_root_path(self, test_client: TestClient):
        """根路径应返回前端页面或重定向"""
        response = test_client.get("/")
        # 可能返回 200（有前端）或 404（无前端）
        assert response.status_code in (200, 404, 307)


class TestCORS:
    """CORS 配置测试"""
    
    def test_cors_headers(self, test_client: TestClient):
        """检查 CORS 响应头"""
        response = test_client.options(
            "/api/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET"
            }
        )
        # OPTIONS 请求应该被处理
        assert response.status_code in (200, 405)

    def test_preview_origin_allowed(self, test_client: TestClient):
        """Vite production preview 端口也应允许访问后端 API。"""
        response = test_client.get(
            "/api/health",
            headers={"Origin": "http://127.0.0.1:4173"},
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:4173"


class TestErrorHandling:
    """错误处理测试"""
    
    def test_invalid_endpoint(self, test_client: TestClient):
        """访问无效端点应返回 404"""
        response = test_client.get("/api/invalid_endpoint_xyz")
        assert response.status_code == 404
    
    def test_method_not_allowed(self, test_client: TestClient):
        """使用不允许的方法应返回 405"""
        response = test_client.delete("/api/health")
        assert response.status_code in (405, 404)
