# ═══════════════════════════════════════════════════════════════
# Runners — 模型执行器模块
# ═══════════════════════════════════════════════════════════════
"""
统一的 Runner 接口，支持多种执行方式：
- SSHRunner: 远程 SSH 服务器执行
- LocalDockerRunner: 本地 Docker 容器执行（规划中）
- OnlineAPIRunner: 在线 API 执行（规划中）
"""

from runner_base import (
    RunnerBase,
    RunnerPhase,
    RunnerProgress,
    RunnerResult,
    CancelledException,
    register_runner,
    get_runner,
    available_runners,
)

# Lazy imports to avoid circular dependencies in tests
try:
    from .ssh import SSHRunner
except ImportError:
    SSHRunner = None  # type: ignore

try:
    from .docker import LocalDockerRunner, DockerConfig
except ImportError:
    LocalDockerRunner = None  # type: ignore
    DockerConfig = None  # type: ignore

try:
    from .online_api import OnlineAPIRunner, OnlineAPIConfig, APIProvider, APIEndpoint
except ImportError:
    OnlineAPIRunner = None  # type: ignore
    OnlineAPIConfig = None  # type: ignore
    APIProvider = None  # type: ignore
    APIEndpoint = None  # type: ignore

__all__ = [
    "RunnerBase",
    "RunnerPhase",
    "RunnerProgress",
    "RunnerResult",
    "CancelledException",
    "register_runner",
    "get_runner",
    "available_runners",
    "SSHRunner",
    "LocalDockerRunner",
    "DockerConfig",
    "OnlineAPIRunner",
    "OnlineAPIConfig",
    "APIProvider",
    "APIEndpoint",
]
