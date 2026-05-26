# ═══════════════════════════════════════════════════════════════
# SSHRunner — 远程 SSH 执行器
# ═══════════════════════════════════════════════════════════════
"""
通过 SSH 在远程 GPU 服务器执行模型推理。
继承 RunnerBase，内部委托给现有 ssh_runner 模块。
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable

from runner_base import (
    RunnerBase,
    RunnerPhase,
    RunnerProgress,
    RunnerResult,
    CancelledException,
    register_runner,
)
from job_store import load_job, update_job, get_job_dir
from ssh_runner import (
    ServerConfig,
    run_remote_job,
    cancel_remote_job,
    _upload_inputs,
    _upload_remote_job_json,
    _upload_runner,
    _download_results,
    _ssh,
    _write_debug_log,
)
import shlex

LOGGER = logging.getLogger("backend.runners.ssh")


@register_runner("ssh")
class SSHRunner(RunnerBase):
    """
    远程 SSH 执行器
    
    使用方式:
        runner = SSHRunner(job_id="xxx", model="monst3r")
        result = runner.run()
    
    或者使用工厂:
        runner = get_runner("ssh", job_id="xxx", model="monst3r")
        result = runner.run()
    """
    
    def __init__(
        self,
        job_id: str,
        model: str,
        params: dict | None = None,
        on_progress: Callable[[RunnerProgress], None] | None = None,
        config: ServerConfig | None = None,
    ):
        super().__init__(job_id, model, params, on_progress)
        self.config = config or ServerConfig()
        self._remote_job_dir: str | None = None
        self._cancel_event = threading.Event()
    
    # ─────────────── RunnerBase 实现 ───────────────
    
    def prepare(self) -> None:
        """准备远程执行环境"""
        self._remote_job_dir = f"{self.config.remote_jobs_dir}/{self.job_id}"
        
        _write_debug_log(self.job_id, f"SSHRunner.prepare: {self._remote_job_dir}")
        self._update_progress(0.1, "正在创建远端任务目录...")
        
        update_job(
            self.job_id,
            status="running",
            phase="preparing_remote",
            remote_job_dir=self._remote_job_dir,
            progress_message="正在创建远端任务目录...",
        )
        
        # 创建远程目录
        _ssh(
            self.config,
            (
                f"mkdir -p {shlex.quote(self._remote_job_dir)}/input "
                f"{shlex.quote(self._remote_job_dir)}/output "
                f"{shlex.quote(self._remote_job_dir)}/logs"
            ),
        )
        
        # 确认 runners 目录
        self._update_progress(0.3, "正在确认远端运行脚本目录...")
        _ssh(self.config, f"mkdir -p {shlex.quote(self.config.remote_runners_dir)}")
        
        _write_debug_log(self.job_id, "SSHRunner.prepare: done")
    
    def upload(self) -> None:
        """上传输入文件到远程服务器"""
        if not self._remote_job_dir:
            raise RuntimeError("prepare() must be called before upload()")
        
        _write_debug_log(self.job_id, "SSHRunner.upload: starting")
        
        # 上传输入文件
        self._update_progress(0.1, "正在上传本地输入文件到服务器...")
        update_job(self.job_id, phase="uploading_inputs", progress_message="正在上传本地输入文件到服务器...")
        _upload_inputs(self.config, self.job_id, self._remote_job_dir)
        
        # 上传任务清单
        self._update_progress(0.6, "正在上传任务清单...")
        update_job(self.job_id, phase="uploading_inputs", progress_message="正在上传任务清单...")
        _upload_remote_job_json(self.config, self.job_id, self._remote_job_dir)
        
        # 上传运行脚本
        self._update_progress(0.9, "正在上传远端运行脚本...")
        update_job(self.job_id, phase="uploading_inputs", progress_message="正在上传远端运行脚本...")
        _upload_runner(self.config, self.model)
        
        _write_debug_log(self.job_id, "SSHRunner.upload: done")
    
    def execute(self) -> None:
        """执行远程模型推理"""
        if not self._remote_job_dir:
            raise RuntimeError("prepare() must be called before execute()")
        
        _write_debug_log(self.job_id, f"SSHRunner.execute: model={self.model}")
        self._update_progress(0.0, "正在远程执行模型推理...")
        
        # 委托给现有的模型分发逻辑
        from ssh_runner import (
            _run_dust3r_v2,
            _run_mast3r_v1,
            _run_monst3r_v1,
            _run_spann3r_v1,
            _run_fast3r_v1,
            _run_align3r_v1,
            _run_cut3r_v1,
        )
        from model_contracts import runner_spec_for
        
        dispatchers = {
            "dust3r": _run_dust3r_v2,
            "mast3r": _run_mast3r_v1,
            "monst3r": _run_monst3r_v1,
            "spann3r": _run_spann3r_v1,
            "fast3r": _run_fast3r_v1,
            "align3r": _run_align3r_v1,
            "cut3r": _run_cut3r_v1,
        }
        
        runner_spec = runner_spec_for(self.model)
        dispatcher = dispatchers.get(runner_spec.dispatch_key or "")
        
        if dispatcher is None:
            raise RuntimeError(f"模型 '{self.model}' 还没有接入远端执行。")
        
        # 执行
        dispatcher(self.config, self.job_id, self._remote_job_dir)
        
        _write_debug_log(self.job_id, "SSHRunner.execute: done")
    
    def download(self) -> list[str]:
        """下载结果文件"""
        if not self._remote_job_dir:
            raise RuntimeError("prepare() must be called before download()")
        
        _write_debug_log(self.job_id, "SSHRunner.download: starting")
        self._update_progress(0.0, "正在下载结果文件...")
        
        update_job(
            self.job_id,
            phase="downloading_results",
            progress_message="正在把输出和日志下载回本地缓存...",
        )
        
        output_files = _download_results(self.config, self.job_id, self._remote_job_dir)
        
        _write_debug_log(self.job_id, f"SSHRunner.download: {len(output_files)} files")
        return output_files
    
    def cleanup(self) -> None:
        """清理（当前无需操作，远程文件保留）"""
        _write_debug_log(self.job_id, "SSHRunner.cleanup: no-op")
    
    def _on_cancel(self) -> None:
        """取消远程任务"""
        self._cancel_event.set()
        try:
            cancel_remote_job(self.job_id)
        except Exception as e:
            LOGGER.warning(f"Failed to cancel remote job: {e}")
    
    # ─────────────── 便捷方法 ───────────────
    
    def run_legacy(self) -> None:
        """
        使用旧版 run_remote_job 执行（向后兼容）
        """
        run_remote_job(self.job_id)
    
    @classmethod
    def from_job_id(cls, job_id: str, **kwargs) -> "SSHRunner":
        """从 job_id 创建 Runner"""
        job = load_job(job_id)
        return cls(
            job_id=job_id,
            model=job.model,
            params=job.params,
            **kwargs,
        )
