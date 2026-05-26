# ═══════════════════════════════════════════════════════════════
# OnlineAPIRunner — 在线 API 执行器
# ═══════════════════════════════════════════════════════════════
"""
通过在线 API 执行模型推理。
支持 HuggingFace Spaces、Replicate 等平台。
无需本地 GPU 或服务器。
"""

from __future__ import annotations

import base64
import json
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Any
from urllib.parse import urljoin

import httpx

from runner_base import (
    RunnerBase,
    RunnerPhase,
    RunnerProgress,
    RunnerResult,
    CancelledException,
    register_runner,
)
from job_store import load_job, update_job, get_job_dir, iter_input_items
from logging_config import log


class APIProvider(str, Enum):
    """API 提供商"""
    HUGGINGFACE = "huggingface"
    REPLICATE = "replicate"
    CUSTOM = "custom"


@dataclass
class APIEndpoint:
    """API 端点配置"""
    provider: APIProvider
    url: str
    model_id: str
    api_key: str | None = None
    timeout: int = 600  # 10 分钟
    poll_interval: int = 5  # 轮询间隔


@dataclass
class OnlineAPIConfig:
    """在线 API 配置"""
    # 模型到端点的映射
    endpoints: dict[str, APIEndpoint] = field(default_factory=dict)
    # 默认超时
    default_timeout: int = 600
    # 最大文件大小 (MB)
    max_file_size_mb: int = 50
    # 最大并发请求
    max_concurrent: int = 3
    
    def get_endpoint(self, model: str) -> APIEndpoint | None:
        """获取模型对应的端点"""
        return self.endpoints.get(model)
    
    @classmethod
    def from_env(cls) -> "OnlineAPIConfig":
        """从环境变量加载配置"""
        config = cls()
        
        # HuggingFace 配置
        hf_token = os.environ.get("HF_TOKEN")
        if hf_token:
            # 添加一些常见的 HuggingFace Spaces
            config.endpoints["dust3r"] = APIEndpoint(
                provider=APIProvider.HUGGINGFACE,
                url="https://api-inference.huggingface.co/models/",
                model_id="naver/DUSt3R",
                api_key=hf_token,
            )
        
        # Replicate 配置
        replicate_token = os.environ.get("REPLICATE_API_TOKEN")
        if replicate_token:
            config.endpoints["monst3r"] = APIEndpoint(
                provider=APIProvider.REPLICATE,
                url="https://api.replicate.com/v1/predictions",
                model_id="example/monst3r:latest",
                api_key=replicate_token,
            )
        
        return config


@register_runner("online_api")
class OnlineAPIRunner(RunnerBase):
    """
    在线 API 执行器
    
    使用方式:
        runner = OnlineAPIRunner(job_id="xxx", model="dust3r")
        result = runner.run()
    
    支持的平台:
    - HuggingFace Inference API
    - Replicate
    - 自定义 API 端点
    """
    
    def __init__(
        self,
        job_id: str,
        model: str,
        params: dict | None = None,
        on_progress: Callable[[RunnerProgress], None] | None = None,
        config: OnlineAPIConfig | None = None,
    ):
        super().__init__(job_id, model, params, on_progress)
        self.config = config or OnlineAPIConfig.from_env()
        self._cancel_event = threading.Event()
        self._prediction_id: str | None = None
        self._client: httpx.Client | None = None
    
    # ─────────────── RunnerBase 实现 ───────────────
    
    def prepare(self) -> None:
        """准备 API 调用"""
        log.info(f"OnlineAPIRunner.prepare: job_id={self.job_id}")
        self._update_progress(0.1, "检查 API 配置...")
        
        endpoint = self.config.get_endpoint(self.model)
        if not endpoint:
            raise RuntimeError(
                f"模型 '{self.model}' 没有配置在线 API 端点。"
                "请在环境变量中设置 HF_TOKEN 或 REPLICATE_API_TOKEN。"
            )
        
        if not endpoint.api_key:
            raise RuntimeError(
                f"API 端点 '{endpoint.provider.value}' 缺少 API Key。"
            )
        
        # 初始化 HTTP 客户端
        self._client = httpx.Client(timeout=endpoint.timeout)
        
        update_job(
            self.job_id,
            status="running",
            phase="preparing_api",
            progress_message="API 配置检查完成",
        )
        
        log.info("OnlineAPIRunner.prepare: done")
    
    def upload(self) -> None:
        """准备上传数据（编码为 base64）"""
        log.info("OnlineAPIRunner.upload: encoding inputs")
        self._update_progress(0.1, "编码输入文件...")
        
        job = load_job(self.job_id)
        job_dir = get_job_dir(self.job_id)
        items = iter_input_items(job)
        
        total_size = 0
        for item in items:
            file_path = job_dir / "input" / item["stored_name"]
            if file_path.exists():
                total_size += file_path.stat().st_size
        
        max_size = self.config.max_file_size_mb * 1024 * 1024
        if total_size > max_size:
            raise RuntimeError(
                f"输入文件总大小 ({total_size / 1024 / 1024:.1f}MB) "
                f"超过限制 ({self.config.max_file_size_mb}MB)"
            )
        
        update_job(
            self.job_id,
            phase="uploading_api",
            progress_message=f"准备上传 {len(items)} 个文件...",
        )
        
        log.info(f"OnlineAPIRunner.upload: {len(items)} files, {total_size} bytes")
    
    def execute(self) -> None:
        """调用在线 API"""
        log.info(f"OnlineAPIRunner.execute: model={self.model}")
        self._update_progress(0.0, "调用在线 API...")
        
        endpoint = self.config.get_endpoint(self.model)
        if not endpoint:
            raise RuntimeError(f"No endpoint for model: {self.model}")
        
        update_job(
            self.job_id,
            phase="running_api",
            progress_message="正在远程执行...",
        )
        
        if endpoint.provider == APIProvider.HUGGINGFACE:
            self._execute_huggingface(endpoint)
        elif endpoint.provider == APIProvider.REPLICATE:
            self._execute_replicate(endpoint)
        else:
            self._execute_custom(endpoint)
        
        log.info("OnlineAPIRunner.execute: done")
    
    def download(self) -> list[str]:
        """下载结果"""
        log.info("OnlineAPIRunner.download: fetching results")
        self._update_progress(0.0, "下载结果...")
        
        job_dir = get_job_dir(self.job_id)
        output_dir = job_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 结果已在 execute 阶段保存
        output_files = []
        for f in output_dir.rglob("*"):
            if f.is_file():
                rel_path = f.relative_to(job_dir)
                output_files.append(str(rel_path))
        
        update_job(
            self.job_id,
            phase="finished",
            progress_message=f"完成，{len(output_files)} 个输出文件",
        )
        
        log.info(f"OnlineAPIRunner.download: {len(output_files)} files")
        return output_files
    
    def cleanup(self) -> None:
        """清理资源"""
        log.info("OnlineAPIRunner.cleanup")
        if self._client:
            self._client.close()
            self._client = None
    
    def _on_cancel(self) -> None:
        """取消执行"""
        self._cancel_event.set()
        # 尝试取消远程预测（如果支持）
        if self._prediction_id:
            self._cancel_prediction()
    
    # ─────────────── Provider 实现 ───────────────
    
    def _execute_huggingface(self, endpoint: APIEndpoint) -> None:
        """HuggingFace Inference API"""
        job = load_job(self.job_id)
        job_dir = get_job_dir(self.job_id)
        items = iter_input_items(job)
        
        # 编码图片
        images_b64 = []
        for item in items:
            file_path = job_dir / "input" / item["stored_name"]
            if file_path.exists():
                with open(file_path, "rb") as f:
                    images_b64.append(base64.b64encode(f.read()).decode())
        
        # 调用 API
        headers = {"Authorization": f"Bearer {endpoint.api_key}"}
        payload = {
            "inputs": images_b64,
            "parameters": self.params or {},
        }
        
        url = urljoin(endpoint.url, endpoint.model_id)
        
        response = self._client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        self._save_result(result)
    
    def _execute_replicate(self, endpoint: APIEndpoint) -> None:
        """Replicate API"""
        job = load_job(self.job_id)
        job_dir = get_job_dir(self.job_id)
        items = iter_input_items(job)
        
        # 编码图片
        images_b64 = []
        for item in items:
            file_path = job_dir / "input" / item["stored_name"]
            if file_path.exists():
                with open(file_path, "rb") as f:
                    data = base64.b64encode(f.read()).decode()
                    images_b64.append(f"data:image/jpeg;base64,{data}")
        
        # 创建预测
        headers = {
            "Authorization": f"Token {endpoint.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "version": endpoint.model_id.split(":")[-1],
            "input": {
                "images": images_b64,
                **(self.params or {}),
            },
        }
        
        response = self._client.post(endpoint.url, json=payload, headers=headers)
        response.raise_for_status()
        
        prediction = response.json()
        self._prediction_id = prediction.get("id")
        
        # 轮询等待完成
        self._poll_replicate(prediction.get("urls", {}).get("get"), headers, endpoint)
    
    def _poll_replicate(self, status_url: str, headers: dict, endpoint: APIEndpoint) -> None:
        """轮询 Replicate 预测状态"""
        start_time = time.time()
        
        while True:
            if self._cancel_event.is_set():
                raise CancelledException()
            
            if time.time() - start_time > endpoint.timeout:
                raise RuntimeError(f"API 超时 ({endpoint.timeout}s)")
            
            response = self._client.get(status_url, headers=headers)
            response.raise_for_status()
            
            prediction = response.json()
            status = prediction.get("status")
            
            if status == "succeeded":
                output = prediction.get("output")
                self._save_result(output)
                return
            elif status == "failed":
                error = prediction.get("error", "Unknown error")
                raise RuntimeError(f"Replicate 执行失败: {error}")
            elif status == "canceled":
                raise CancelledException()
            
            # 更新进度
            self._update_progress(0.5, f"远程执行中... ({status})")
            time.sleep(endpoint.poll_interval)
    
    def _execute_custom(self, endpoint: APIEndpoint) -> None:
        """自定义 API"""
        job = load_job(self.job_id)
        job_dir = get_job_dir(self.job_id)
        items = iter_input_items(job)
        
        # 编码图片
        images_b64 = []
        for item in items:
            file_path = job_dir / "input" / item["stored_name"]
            if file_path.exists():
                with open(file_path, "rb") as f:
                    images_b64.append(base64.b64encode(f.read()).decode())
        
        # 调用自定义 API
        headers = {}
        if endpoint.api_key:
            headers["Authorization"] = f"Bearer {endpoint.api_key}"
        
        payload = {
            "model": self.model,
            "images": images_b64,
            "params": self.params or {},
        }
        
        response = self._client.post(endpoint.url, json=payload, headers=headers)
        response.raise_for_status()
        
        result = response.json()
        self._save_result(result)
    
    def _save_result(self, result: Any) -> None:
        """保存 API 结果"""
        job_dir = get_job_dir(self.job_id)
        output_dir = job_dir / "output"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存原始响应
        with open(output_dir / "api_response.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        
        # 如果结果包含 base64 编码的文件，解码保存
        if isinstance(result, dict):
            for key, value in result.items():
                if isinstance(value, str) and value.startswith("data:"):
                    # data URL 格式
                    try:
                        header, data = value.split(",", 1)
                        ext = self._guess_extension(header)
                        decoded = base64.b64decode(data)
                        with open(output_dir / f"{key}{ext}", "wb") as f:
                            f.write(decoded)
                    except Exception as e:
                        log.warning(f"Failed to decode {key}: {e}")
        elif isinstance(result, list):
            for i, item in enumerate(result):
                if isinstance(item, str) and item.startswith("data:"):
                    try:
                        header, data = item.split(",", 1)
                        ext = self._guess_extension(header)
                        decoded = base64.b64decode(data)
                        with open(output_dir / f"output_{i}{ext}", "wb") as f:
                            f.write(decoded)
                    except Exception as e:
                        log.warning(f"Failed to decode item {i}: {e}")
    
    def _guess_extension(self, data_header: str) -> str:
        """从 data URL header 猜测文件扩展名"""
        if "image/png" in data_header:
            return ".png"
        elif "image/jpeg" in data_header:
            return ".jpg"
        elif "model/gltf" in data_header or "model/glb" in data_header:
            return ".glb"
        elif "application/octet-stream" in data_header:
            return ".ply"
        return ".bin"
    
    def _cancel_prediction(self) -> None:
        """取消远程预测"""
        endpoint = self.config.get_endpoint(self.model)
        if not endpoint or not self._prediction_id:
            return
        
        if endpoint.provider == APIProvider.REPLICATE:
            try:
                cancel_url = f"{endpoint.url}/{self._prediction_id}/cancel"
                headers = {"Authorization": f"Token {endpoint.api_key}"}
                self._client.post(cancel_url, headers=headers)
            except Exception as e:
                log.warning(f"Failed to cancel prediction: {e}")
    
    # ─────────────── 便捷方法 ───────────────
    
    @classmethod
    def from_job_id(cls, job_id: str, **kwargs) -> "OnlineAPIRunner":
        """从 job_id 创建 Runner"""
        job = load_job(job_id)
        return cls(
            job_id=job_id,
            model=job.model,
            params=job.params,
            **kwargs,
        )
    
    @staticmethod
    def available_providers() -> list[str]:
        """获取可用的 API 提供商"""
        providers = []
        if os.environ.get("HF_TOKEN"):
            providers.append("huggingface")
        if os.environ.get("REPLICATE_API_TOKEN"):
            providers.append("replicate")
        return providers
