"""4D 可视化 (viser) 远端会话管理。

为 MonST3R 等支持 viser 可视化的任务，启动一个 SSH 端口转发进程：

    ssh -L <local_port>:127.0.0.1:<remote_port> alias \
        "cd <repo> && conda run -n <env> python viser/visualizer_monst3r.py \
            --data <remote_demo_dir> --port <remote_port> --host 127.0.0.1"

进程的生命周期由本模块的 ``ViserSessionManager`` 单例托管，可通过
``/api/jobs/{job_id}/viser/...`` REST 接口启动 / 停止 / 查询状态。
"""
from __future__ import annotations

import shlex
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from job_store import get_job_dir, load_job
from ssh_runner import SSH_CONNECT_OPTIONS, ServerConfig

WINDOWS_NO_WINDOW = 0x08000000


@dataclass
class ViserSession:
    job_id: str
    pid: int
    local_port: int
    remote_port: int
    remote_data_dir: str
    started_at: float
    log_path: Path
    status: str = "starting"  # starting | ready | failed | stopped
    last_error: Optional[str] = None
    process: Optional[subprocess.Popen] = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        return {
            "jobId": self.job_id,
            "pid": self.pid,
            "localPort": self.local_port,
            "remotePort": self.remote_port,
            "remoteDataDir": self.remote_data_dir,
            "startedAt": self.started_at,
            "url": f"http://127.0.0.1:{self.local_port}",
            "status": self.status,
            "lastError": self.last_error,
            "uptimeSeconds": max(0, int(time.time() - self.started_at)),
        }


class ViserSessionManager:
    """每个 ``job_id`` 只允许同时存在一个 viser 会话。"""

    def __init__(self) -> None:
        self._sessions: dict[str, ViserSession] = {}
        self._lock = threading.RLock()

    # ────────────────────────── 公共 API ──────────────────────────

    def get(self, job_id: str) -> Optional[ViserSession]:
        with self._lock:
            session = self._sessions.get(job_id)
            if session is None:
                return None
            self._refresh_status(session)
            return session

    def start(self, job_id: str, config: ServerConfig) -> ViserSession:
        with self._lock:
            existing = self._sessions.get(job_id)
            if existing is not None:
                self._refresh_status(existing)
                if existing.status in {"starting", "ready"}:
                    return existing
                self._cleanup_locked(job_id)

            job = load_job(job_id)
            if job.model != "monst3r":
                raise ValueError(f"viser 当前仅支持 monst3r 任务，当前任务为 {job.model}。")

            remote_data_dir = self._resolve_remote_data_dir(config, job_id)
            local_port = _allocate_free_port()
            remote_port = local_port  # 复用同一端口号便于排查

            log_path = get_job_dir(job_id) / "logs" / "viser.live.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)

            remote_cmd = (
                f"set -o pipefail && "
                f"cd {shlex.quote(config.remote_monst3r_repo)} && "
                f"conda run --no-capture-output -n {shlex.quote(config.remote_monst3r_env)} "
                f"python -u viser/visualizer_monst3r.py "
                f"--data {shlex.quote(remote_data_dir)} "
                f"--port {remote_port} "
                f"--host 127.0.0.1"
            )
            argv = [
                "ssh",
                "-T",
                "-N" if False else "-tt",  # 保留交互式 TTY，方便子进程被信号杀掉
                *SSH_CONNECT_OPTIONS,
                "-L",
                f"{local_port}:127.0.0.1:{remote_port}",
                config.alias,
                f"bash -lc {shlex.quote(remote_cmd)}",
            ]

            log_handle = log_path.open("ab", buffering=0)
            log_handle.write(f"\n=== viser session start @ {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n".encode("utf-8"))
            log_handle.write(("argv: " + " ".join(argv) + "\n").encode("utf-8"))
            log_handle.flush()

            popen_kwargs: dict = {
                "stdout": log_handle,
                "stderr": subprocess.STDOUT,
                "stdin": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = WINDOWS_NO_WINDOW

            try:
                proc = subprocess.Popen(argv, **popen_kwargs)
            except FileNotFoundError as exc:
                log_handle.close()
                raise RuntimeError(f"找不到 ssh 可执行文件：{exc}") from exc

            session = ViserSession(
                job_id=job_id,
                pid=proc.pid,
                local_port=local_port,
                remote_port=remote_port,
                remote_data_dir=remote_data_dir,
                started_at=time.time(),
                log_path=log_path,
                process=proc,
            )
            self._sessions[job_id] = session

            # 异步轮询本地端口，等到 viser 监听后切换到 ready
            threading.Thread(
                target=self._await_ready,
                args=(job_id,),
                daemon=True,
                name=f"viser-await-{job_id}",
            ).start()
            return session

    def stop(self, job_id: str) -> Optional[ViserSession]:
        with self._lock:
            session = self._sessions.get(job_id)
            if session is None:
                return None
            self._cleanup_locked(job_id)
            session.status = "stopped"
            return session

    def list_active(self) -> list[ViserSession]:
        with self._lock:
            for sess in list(self._sessions.values()):
                self._refresh_status(sess)
            return list(self._sessions.values())

    # ───────────────────────── 内部方法 ─────────────────────────

    def _resolve_remote_data_dir(self, config: ServerConfig, job_id: str) -> str:
        # demo.py 输出位置：<remote_jobs_dir>/<job_id>/monst3r_demo/<seq_name>
        # 而 monst3r_runner.py 中 seq_name = job_id
        return f"{config.remote_jobs_dir}/{job_id}/monst3r_demo/{job_id}"

    def _refresh_status(self, session: ViserSession) -> None:
        proc = session.process
        if proc is None:
            return
        rc = proc.poll()
        if rc is None:
            return  # 仍在运行
        if session.status == "stopped":
            return
        # 进程已退出，根据返回码判断
        if rc == 0:
            session.status = "stopped"
        else:
            session.status = "failed"
            session.last_error = self._tail_log(session.log_path, max_chars=600)

    def _await_ready(self, job_id: str) -> None:
        deadline = time.time() + 90  # 最多等 90 秒
        while time.time() < deadline:
            with self._lock:
                session = self._sessions.get(job_id)
                if session is None:
                    return
                self._refresh_status(session)
                if session.status in {"failed", "stopped"}:
                    return
                if session.status == "ready":
                    return
                local_port = session.local_port
            if _port_open("127.0.0.1", local_port):
                with self._lock:
                    session = self._sessions.get(job_id)
                    if session is not None and session.status == "starting":
                        session.status = "ready"
                return
            time.sleep(1.0)
        # 超时 → 标记失败
        with self._lock:
            session = self._sessions.get(job_id)
            if session is not None and session.status == "starting":
                session.status = "failed"
                session.last_error = self._tail_log(session.log_path, max_chars=600) or "viser 启动超时（90s）。"

    def _cleanup_locked(self, job_id: str) -> None:
        session = self._sessions.get(job_id)
        if session is None:
            return
        proc = session.process
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception:
                pass
        # 不从 _sessions 移除，保留状态供查询，stop() 调用方自行决定是否再 start

    @staticmethod
    def _tail_log(path: Path, *, max_chars: int) -> str:
        try:
            data = path.read_bytes()
        except OSError:
            return ""
        text = data.decode("utf-8", errors="replace")
        return text[-max_chars:] if len(text) > max_chars else text


def _allocate_free_port(preferred_range: tuple[int, int] = (7860, 7960)) -> int:
    """从 ``preferred_range`` 找一个本机空闲端口，全部占用则让系统随机分配。"""
    for candidate in range(preferred_range[0], preferred_range[1] + 1):
        if _port_free("127.0.0.1", candidate):
            return candidate
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.3)
        try:
            sock.bind((host, port))
        except OSError:
            return False
        return True


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.connect((host, port))
        except OSError:
            return False
        return True


# 全局单例
manager = ViserSessionManager()
