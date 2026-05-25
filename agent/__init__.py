# ═══════════════════════════════════════════════════════════════
# 3R_All_in_One Agent Module
# 一键环境搭建、蓝图校验、健康检查、烟雾测试、实验编排、AI 诊断
# ═══════════════════════════════════════════════════════════════
"""
Agent 模块核心职责：

1. **蓝图管理** — 读取/校验 model_specs/*.yaml
2. **环境搭建** — SSH 远程创建 conda env、安装依赖、编译扩展
3. **健康检查** — 逐项验证 import/cuda_kernel/checkpoint
4. **烟雾测试** — 快速验证模型可运行
5. **实验编排** — 批量任务调度与结果收集
6. **AI 诊断**  — 根据 known_issues 智能排障

使用示例::

    from agent import ModelRegistry, EnvBuilder, SmokeRunner

    registry = ModelRegistry()
    spec = registry.get("monst3r")

    builder = EnvBuilder(ssh_config)
    report = builder.build(spec)

    runner = SmokeRunner(ssh_config)
    result = runner.check(spec)
"""

__version__ = "0.4.0"
__author__ = "KYKT"
__all__ = [
    # 版本
    "__version__",
    # 核心类
    "ModelSpec",
    "ModelRegistry",
    "SSHConfig",
    "BuildResult",
    "EnvironmentReport",
    # 环境搭建
    "EnvBuilder",
    "create_conda_env",
    "install_pip_deps",
    "run_build_steps",
    "run_health_checks",
    "run_smoke_test",
    "build_environment",
    # 烟雾测试
    "SmokeRunner",
    "SmokeReport",
    "smoke_check_model",
    "smoke_check_all",
    # 实验编排
    "ExperimentAgent",
    "ExperimentConfig",
    "ExperimentResult",
    # 蓝图校验
    "SchemaValidator",
    "ValidationResult",
    # AI 诊断
    "HealthDoctor",
    "DiagnosisReport",
]

# ─────────────── Lazy Imports ───────────────
# 避免循环导入，按需加载


def __getattr__(name: str):
    """Lazy import to avoid circular dependencies."""
    if name in ("ModelSpec", "SSHConfig", "BuildResult", "EnvironmentReport",
                "create_conda_env", "install_pip_deps", "run_build_steps",
                "run_health_checks", "run_smoke_test", "build_environment"):
        from . import env_builder
        return getattr(env_builder, name)

    if name in ("SmokeRunner", "SmokeReport", "smoke_check_model", "smoke_check_all"):
        from . import smoke_runner
        return getattr(smoke_runner, name)

    if name in ("ExperimentAgent", "ExperimentConfig", "ExperimentResult"):
        from . import experiment_agent
        return getattr(experiment_agent, name)

    if name == "ModelRegistry":
        from . import registry
        return registry.ModelRegistry

    if name in ("SchemaValidator", "ValidationResult"):
        from . import schema_validator
        return getattr(schema_validator, name)

    if name in ("HealthDoctor", "DiagnosisReport"):
        from . import health_doctor
        return getattr(health_doctor, name)

    if name == "EnvBuilder":
        from . import env_builder
        return env_builder.EnvBuilder

    raise AttributeError(f"module 'agent' has no attribute {name!r}")
