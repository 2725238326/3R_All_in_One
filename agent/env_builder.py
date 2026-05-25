"""
Environment Builder - 一键搭建远程模型环境
读取 model_specs/*.yaml，通过 SSH 自动执行环境搭建流程。
"""
from __future__ import annotations

import logging
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

LOGGER = logging.getLogger("agent.env_builder")

# ═══════════════════════════════════════════════════════════════
# 常量
# ═══════════════════════════════════════════════════════════════

DEFAULT_SSH_HOST = "172.17.140.97"
DEFAULT_SSH_USER = "kykt26"
DEFAULT_SSH_ALIAS = "KYKT-UI"


@dataclass
class ModelSpec:
    """模型蓝图 — Agent 框架的基础标签"""
    # 身份
    name: str
    key: str
    family: str
    version: str
    paper: dict
    # 能力标签
    tags: dict
    # 源码
    repo: dict
    # 环境
    environment: dict
    # 权重
    checkpoints: list[dict]
    # 编译
    build_steps: list[dict]
    # 资源需求
    resources: dict
    # 健康检查
    health_checks: list[dict]
    smoke_test: dict
    # Runner
    runner: dict
    # 输出合同
    output_contract: dict
    # 已知问题
    known_issues: list[dict]
    # 兼容
    compatibility: dict
    # 状态
    status: str = "unknown"
    priority: str = "normal"
    last_verified: str = ""

    @classmethod
    def from_yaml(cls, path: Path) -> "ModelSpec":
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls(
            name=data["name"],
            key=data.get("key", data["name"].lower()),
            family=data.get("family", ""),
            version=data.get("version", ""),
            paper=data.get("paper", {}),
            tags=data.get("tags", {}),
            repo=data.get("repo", {}),
            environment=data.get("environment", {}),
            checkpoints=data.get("checkpoints", []),
            build_steps=data.get("build_steps", []) or [],
            resources=data.get("resources", {}),
            health_checks=data.get("health_checks", []),
            smoke_test=data.get("smoke_test", {}),
            runner=data.get("runner", {}),
            output_contract=data.get("output_contract", {}),
            known_issues=data.get("known_issues", []) or [],
            compatibility=data.get("compatibility", {}),
            status=data.get("status", "unknown"),
            priority=data.get("priority", "normal"),
            last_verified=data.get("last_verified", ""),
        )

    @property
    def model_type(self) -> str:
        return self.tags.get("type", "unknown")

    @property
    def paradigm(self) -> str:
        return self.tags.get("paradigm", "unknown")

    @property
    def conda_env(self) -> str:
        return self.environment.get("conda_env", "")

    @property
    def server_path(self) -> str:
        return self.repo.get("server_path", "")

    @property
    def needs_curope(self) -> bool:
        return any("curope" in s.get("name", "") for s in self.build_steps)

    @property
    def is_ready(self) -> bool:
        return self.status == "integrated"

    @property
    def unresolved_issues(self) -> list[dict]:
        return [i for i in self.known_issues if not i.get("resolved", False)]

    def get_param_tier(self, tier: str = "standard") -> dict:
        """获取指定预设梯度的参数"""
        tiers = self.runner.get("param_tiers", {})
        base = self.runner.get("default_params", {})
        override = tiers.get(tier, {})
        return {**base, **override}

    def summary(self) -> dict:
        """生成简洁的模型摘要"""
        return {
            "name": self.name,
            "key": self.key,
            "type": self.model_type,
            "paradigm": self.paradigm,
            "status": self.status,
            "env": self.conda_env,
            "needs_curope": self.needs_curope,
            "gpu_memory_gb": self.resources.get("gpu_memory_gb", 0),
            "unresolved_issues": len(self.unresolved_issues),
        }


@dataclass
class SSHConfig:
    host: str
    user: str
    port: int = 22
    key_file: Optional[str] = None
    alias: Optional[str] = None

    @property
    def ssh_target(self) -> str:
        return self.alias or f"{self.user}@{self.host}"


@dataclass
class BuildResult:
    model: str
    step: str
    success: bool
    output: str = ""
    error: str = ""
    duration_sec: float = 0


@dataclass
class EnvironmentReport:
    model: str
    steps: list[BuildResult] = field(default_factory=list)
    smoke_passed: bool = False
    total_duration_sec: float = 0

    @property
    def success(self) -> bool:
        return all(s.success for s in self.steps) and self.smoke_passed


def load_all_specs(specs_dir: Path) -> list[ModelSpec]:
    """Load all model specs from directory."""
    specs = []
    for yaml_file in sorted(specs_dir.glob("*.yaml")):
        try:
            specs.append(ModelSpec.from_yaml(yaml_file))
            LOGGER.info(f"Loaded spec: {yaml_file.stem}")
        except Exception as e:
            LOGGER.warning(f"Failed to load {yaml_file}: {e}")
    return specs


def run_ssh_command(
    ssh: SSHConfig,
    command: str,
    timeout: int = 300,
    env: Optional[dict] = None,
) -> tuple[bool, str, str]:
    """Run a command on remote server via SSH."""
    env_prefix = ""
    if env:
        env_parts = [f"export {k}={v}" for k, v in env.items()]
        env_prefix = " && ".join(env_parts) + " && "

    full_cmd = f"{env_prefix}{command}"

    ssh_args = [
        "ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        ssh.ssh_target,
        full_cmd,
    ]

    LOGGER.info(f"SSH: {full_cmd[:200]}")

    try:
        result = subprocess.run(
            ssh_args,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return (
            result.returncode == 0,
            result.stdout,
            result.stderr,
        )
    except subprocess.TimeoutExpired:
        return False, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return False, "", str(e)


def check_env_exists(ssh: SSHConfig, env_name: str) -> bool:
    """Check if a conda environment exists on remote server."""
    ok, stdout, _ = run_ssh_command(ssh, f"conda env list | grep -w {env_name}")
    return ok and env_name in stdout


def check_checkpoint_exists(ssh: SSHConfig, repo_path: str, ckpt: dict) -> bool:
    """Check if a checkpoint file exists on remote server."""
    ckpt_path = ckpt.get('path', '')
    # 如果 path 是绝对路径，直接拼接 name；否则相对 repo_path
    if ckpt_path.startswith('/'):
        full_path = f"{ckpt_path}/{ckpt['name']}"
    else:
        full_path = f"{repo_path}/{ckpt_path}/{ckpt['name']}"
    ok, _, _ = run_ssh_command(ssh, f"test -f {full_path} && echo EXISTS")
    return ok


def create_conda_env(ssh: SSHConfig, spec: ModelSpec) -> BuildResult:
    """Create or clone a conda environment."""
    start = time.time()
    env = spec.environment
    env_name = spec.conda_env

    if check_env_exists(ssh, env_name):
        return BuildResult(
            model=spec.name,
            step="conda_env",
            success=True,
            output=f"Environment '{env_name}' already exists",
            duration_sec=time.time() - start,
        )

    strategy = env.get("create_strategy", "fresh")
    clone_source = env.get("clone_source", "")

    if strategy == "clone_from" and clone_source:
        cmd = f"conda create -n {env_name} --clone {clone_source} -y"
    else:
        python_ver = env.get("python", "3.11")
        cmd = f"conda create -n {env_name} python={python_ver} -y"

    ok, stdout, stderr = run_ssh_command(ssh, cmd, timeout=600)

    return BuildResult(
        model=spec.name,
        step="conda_env",
        success=ok,
        output=stdout[-500:] if stdout else "",
        error=stderr[-500:] if stderr else "",
        duration_sec=time.time() - start,
    )


def install_pip_deps(ssh: SSHConfig, spec: ModelSpec) -> BuildResult:
    """Install pip dependencies."""
    start = time.time()
    env = spec.environment
    env_name = spec.conda_env
    repo_path = spec.server_path

    extra_pip = env.get("extra_pip", [])
    exclude_pip = env.get("exclude_pip", [])

    if not extra_pip and not repo_path:
        return BuildResult(
            model=spec.name, step="pip_install", success=True,
            output="No extra pip packages", duration_sec=0,
        )

    cmds = []
    if extra_pip:
        pkgs = " ".join(f'"{p}"' for p in extra_pip)
        cmds.append(f"conda run -n {env_name} pip install {pkgs}")

    if repo_path:
        exclude_args = ""
        if exclude_pip:
            exclude_args = " | ".join(f"grep -v {p}" for p in exclude_pip)
            cmds.append(
                f"cd {repo_path} && cat requirements.txt | {exclude_args} | "
                f"conda run -n {env_name} pip install -r /dev/stdin"
            )
        else:
            cmds.append(
                f"cd {repo_path} && conda run -n {env_name} pip install -r requirements.txt"
            )

    full_cmd = " && ".join(cmds)
    ok, stdout, stderr = run_ssh_command(ssh, full_cmd, timeout=600)

    return BuildResult(
        model=spec.name,
        step="pip_install",
        success=ok,
        output=stdout[-500:] if stdout else "",
        error=stderr[-500:] if stderr else "",
        duration_sec=time.time() - start,
    )


def run_build_steps(ssh: SSHConfig, spec: ModelSpec) -> list[BuildResult]:
    """Execute build steps (e.g., compile curope)."""
    results = []
    repo_path = spec.server_path

    for i, step in enumerate(spec.build_steps):
        start = time.time()
        step_name = step.get("name", f"build_{i}")
        cmd = step["cmd"]
        cwd = step.get("cwd", "")
        env_vars = step.get("env", {})

        # 构建完整命令（先 cd 到 repo，再 cd 到 cwd）
        cd_chain = f"cd {repo_path}"
        if cwd:
            cd_chain += f" && cd {cwd}"
        full_shell = f"{cd_chain} && {cmd}"

        env_name = spec.conda_env
        full_cmd = f"conda run -n {env_name} bash -c '{full_shell}'"

        ok, stdout, stderr = run_ssh_command(ssh, full_cmd, timeout=300, env=env_vars)

        results.append(BuildResult(
            model=spec.name,
            step=step_name,
            success=ok,
            output=stdout[-500:] if stdout else "",
            error=stderr[-500:] if stderr else "",
            duration_sec=time.time() - start,
        ))

        # 如果有 verify 命令，执行验证
        verify_cmd = step.get("verify")
        if ok and verify_cmd:
            v_cmd = f"cd {repo_path} && {verify_cmd}"
            v_ok, _, v_err = run_ssh_command(ssh, v_cmd, timeout=30)
            if not v_ok:
                results[-1].success = False
                results[-1].error = f"Verify failed: {v_err[:200]}"

        if not results[-1].success:
            break

    return results


def run_smoke_test(ssh: SSHConfig, spec: ModelSpec) -> BuildResult:
    """Run smoke test to verify environment."""
    start = time.time()
    env_name = spec.conda_env
    repo_path = spec.server_path
    script = spec.smoke_test.get("script", "echo OK")
    expected = spec.smoke_test.get("expected", "OK")

    cmd = f"cd {repo_path} && conda run -n {env_name} {script}"
    ok, stdout, stderr = run_ssh_command(ssh, cmd, timeout=120)

    passed = ok and expected in stdout

    return BuildResult(
        model=spec.name,
        step="smoke_test",
        success=passed,
        output=stdout.strip(),
        error=stderr[-200:] if not passed and stderr else "",
        duration_sec=time.time() - start,
    )


def run_health_checks(ssh: SSHConfig, spec: ModelSpec) -> list[BuildResult]:
    """Run all health checks defined in the blueprint."""
    results = []
    repo_path = spec.server_path
    env_name = spec.conda_env

    for check in spec.health_checks:
        start = time.time()
        name = check.get("name", "unnamed")
        command = check.get("command", "echo OK")
        expected = check.get("expected", "")
        critical = check.get("critical", True)

        cmd = f"cd {repo_path} && conda run -n {env_name} {command}"
        ok, stdout, stderr = run_ssh_command(ssh, cmd, timeout=60)

        passed = ok and (not expected or expected in stdout)

        results.append(BuildResult(
            model=spec.name,
            step=f"health:{name}",
            success=passed,
            output=stdout.strip()[:200],
            error=stderr[:200] if not passed else "",
            duration_sec=time.time() - start,
        ))

        if not passed and critical:
            break

    return results


def build_environment(ssh: SSHConfig, spec: ModelSpec) -> EnvironmentReport:
    """Full environment build pipeline for a model."""
    LOGGER.info(f"=== Building environment for {spec.name} ===")
    report = EnvironmentReport(model=spec.name)
    total_start = time.time()

    # Step 1: Create/check conda env
    env_result = create_conda_env(ssh, spec)
    report.steps.append(env_result)
    if not env_result.success:
        report.total_duration_sec = time.time() - total_start
        return report

    # Step 2: Install pip dependencies
    pip_result = install_pip_deps(ssh, spec)
    report.steps.append(pip_result)
    if not pip_result.success:
        report.total_duration_sec = time.time() - total_start
        return report

    # Step 3: Build steps (curope etc.)
    build_results = run_build_steps(ssh, spec)
    report.steps.extend(build_results)
    if build_results and not build_results[-1].success:
        report.total_duration_sec = time.time() - total_start
        return report

    # Step 4: Smoke test
    smoke_result = run_smoke_test(ssh, spec)
    report.steps.append(smoke_result)
    report.smoke_passed = smoke_result.success

    report.total_duration_sec = time.time() - total_start
    LOGGER.info(
        f"=== {spec.name}: {'PASS' if report.success else 'FAIL'} "
        f"({report.total_duration_sec:.1f}s) ==="
    )
    return report


def build_all(
    ssh: SSHConfig,
    specs_dir: Path,
    filter_status: Optional[str] = None,
) -> list[EnvironmentReport]:
    """Build environments for all models (or filtered subset)."""
    specs = load_all_specs(specs_dir)

    if filter_status:
        specs = [s for s in specs if s.status == filter_status]

    reports = []
    for spec in specs:
        report = build_environment(ssh, spec)
        reports.append(report)

    return reports


# ═══════════════════════════════════════════════════════════════
# EnvBuilder 类封装
# ═══════════════════════════════════════════════════════════════

class EnvBuilder:
    """环境搭建器 — 面向对象封装"""

    def __init__(
        self,
        ssh: SSHConfig | None = None,
        host: str = DEFAULT_SSH_HOST,
        user: str = DEFAULT_SSH_USER,
        alias: str = DEFAULT_SSH_ALIAS,
    ):
        if ssh:
            self.ssh = ssh
        else:
            self.ssh = SSHConfig(host=host, user=user, alias=alias)

    def build(self, spec: ModelSpec) -> EnvironmentReport:
        """构建单个模型的环境"""
        return build_environment(self.ssh, spec)

    def build_many(
        self,
        specs: list[ModelSpec],
        stop_on_failure: bool = False,
    ) -> list[EnvironmentReport]:
        """批量构建环境"""
        reports = []
        for spec in specs:
            report = self.build(spec)
            reports.append(report)
            if stop_on_failure and not report.success:
                break
        return reports

    def check_env(self, env_name: str) -> bool:
        """检查 conda 环境是否存在"""
        return check_env_exists(self.ssh, env_name)

    def create_env(self, spec: ModelSpec) -> BuildResult:
        """创建 conda 环境"""
        return create_conda_env(self.ssh, spec)

    def install_deps(self, spec: ModelSpec) -> BuildResult:
        """安装 pip 依赖"""
        return install_pip_deps(self.ssh, spec)

    def run_build(self, spec: ModelSpec) -> list[BuildResult]:
        """执行编译步骤"""
        return run_build_steps(self.ssh, spec)

    def health_check(self, spec: ModelSpec) -> list[BuildResult]:
        """执行健康检查"""
        return run_health_checks(self.ssh, spec)

    def smoke_test(self, spec: ModelSpec) -> BuildResult:
        """执行烟雾测试"""
        return run_smoke_test(self.ssh, spec)

    def check_checkpoint(self, spec: ModelSpec, ckpt: dict) -> bool:
        """检查检查点是否存在"""
        return check_checkpoint_exists(self.ssh, spec.server_path, ckpt)
