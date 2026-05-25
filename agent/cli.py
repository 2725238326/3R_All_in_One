#!/usr/bin/env python3
# ═══════════════════════════════════════════════════════════════
# Agent CLI — 命令行接口
# 3R All-in-One 一键环境搭建与模型管理工具
# ═══════════════════════════════════════════════════════════════
"""
用法：
    python -m agent list                    # 列出所有模型
    python -m agent status                  # 显示注册表状态
    python -m agent info <model>            # 查看模型详情
    python -m agent validate                # 校验所有蓝图
    python -m agent validate <model>        # 校验单个蓝图
    python -m agent smoke <model>           # 运行烟雾测试
    python -m agent build <model>           # 构建环境
    python -m agent health <model>          # 运行健康检查
    python -m agent doctor <model>          # AI 诊断
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
LOGGER = logging.getLogger("agent.cli")


def cmd_list(args: argparse.Namespace) -> int:
    """列出所有模型"""
    from .registry import ModelRegistry
    
    registry = ModelRegistry()
    
    if args.format == "json":
        data = [s.summary() for s in registry.all]
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(f"\n{'Key':<12} {'Name':<12} {'Status':<12} {'Type':<18}")
        print("-" * 60)
        for spec in registry.sorted_by_priority():
            print(f"{spec.key:<12} {spec.name:<12} {spec.status:<12} {spec.model_type:<18}")
        print(f"\nTotal: {len(registry)} models")
    
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """显示注册表状态"""
    from .registry import ModelRegistry
    
    registry = ModelRegistry()
    registry.print_status()
    return 0


def cmd_info(args: argparse.Namespace) -> int:
    """查看模型详情"""
    from .registry import ModelRegistry
    
    registry = ModelRegistry()
    spec = registry.get(args.model)
    
    if not spec:
        LOGGER.error(f"Model not found: {args.model}")
        LOGGER.info(f"Available: {', '.join(registry.keys)}")
        return 1
    
    if args.format == "json":
        print(json.dumps(spec.summary(), indent=2, ensure_ascii=False))
    else:
        print(f"\n{'=' * 60}")
        print(f"MODEL: {spec.name}")
        print(f"{'=' * 60}")
        print(f"Key:         {spec.key}")
        print(f"Family:      {spec.family}")
        print(f"Version:     {spec.version}")
        print(f"Type:        {spec.model_type}")
        print(f"Paradigm:    {spec.paradigm}")
        print(f"Status:      {spec.status}")
        print(f"Priority:    {spec.priority}")
        print(f"Conda Env:   {spec.conda_env}")
        print(f"Server Path: {spec.server_path}")
        print(f"Needs cuROPE:{spec.needs_curope}")
        print(f"GPU Memory:  {spec.resources.get('gpu_memory_gb', '?')} GB")
        print(f"Max Frames:  {spec.resources.get('max_frames', 'N/A')}")
        
        if spec.paper:
            print(f"\nPaper: {spec.paper.get('title', '')}")
            print(f"       {spec.paper.get('url', '')}")
        
        if spec.unresolved_issues:
            print(f"\n⚠ Unresolved Issues ({len(spec.unresolved_issues)}):")
            for issue in spec.unresolved_issues:
                print(f"  - [{issue.get('id', '?')}] {issue.get('description', '')[:60]}")
        
        print()
    
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """校验蓝图"""
    from .schema_validator import SchemaValidator
    
    validator = SchemaValidator()
    
    if args.model:
        # 校验单个模型
        spec_path = validator.specs_dir / f"{args.model}.yaml"
        if not spec_path.exists():
            LOGGER.error(f"Spec not found: {spec_path}")
            return 1
        
        result = validator.validate_file(spec_path)
        print(result.summary())
        
        for issue in result.issues:
            prefix = {"error": "✗", "warning": "⚠", "info": "ℹ"}[issue.level]
            print(f"  {prefix} {issue.field}: {issue.message}")
            if issue.suggestion:
                print(f"    → {issue.suggestion}")
        
        return 0 if result.valid else 1
    else:
        # 校验所有
        results = validator.validate_all()
        
        print("\n" + "=" * 60)
        print("VALIDATION RESULTS")
        print("=" * 60)
        
        for r in results:
            print(r.summary())
        
        total_errors = sum(len(r.errors) for r in results)
        valid_count = sum(1 for r in results if r.valid)
        
        print(f"\nTotal: {valid_count}/{len(results)} valid, {total_errors} errors")
        
        return 0 if total_errors == 0 else 1


def cmd_smoke(args: argparse.Namespace) -> int:
    """运行烟雾测试"""
    from .registry import ModelRegistry
    from .smoke_runner import smoke_check_model
    from .env_builder import SSHConfig
    
    registry = ModelRegistry()
    spec = registry.get(args.model)
    
    if not spec:
        LOGGER.error(f"Model not found: {args.model}")
        return 1
    
    # 使用默认 SSH 配置
    ssh = SSHConfig(
        host=args.host or "172.17.140.97",
        user=args.user or "kykt26",
        alias=args.alias or "KYKT-UI",
    )
    
    LOGGER.info(f"Running smoke test for {spec.name}...")
    report = smoke_check_model(ssh, spec)
    
    status = "✓ PASSED" if report.passed else "✗ FAILED"
    print(f"\n{status}: {spec.name}")
    print(f"Duration: {report.duration_sec:.1f}s")
    
    if report.output:
        print(f"Output: {report.output[:200]}")
    if report.error:
        print(f"Error: {report.error[:200]}")
    
    return 0 if report.passed else 1


def cmd_build(args: argparse.Namespace) -> int:
    """构建环境"""
    from .registry import ModelRegistry
    from .env_builder import SSHConfig, build_environment
    
    registry = ModelRegistry()
    spec = registry.get(args.model)
    
    if not spec:
        LOGGER.error(f"Model not found: {args.model}")
        return 1
    
    ssh = SSHConfig(
        host=args.host or "172.17.140.97",
        user=args.user or "kykt26",
        alias=args.alias or "KYKT-UI",
    )
    
    LOGGER.info(f"Building environment for {spec.name}...")
    report = build_environment(ssh, spec)
    
    print(f"\n{'=' * 60}")
    print(f"BUILD REPORT: {spec.name}")
    print(f"{'=' * 60}")
    print(f"Success: {report.success}")
    print(f"Duration: {report.total_duration_sec:.1f}s")
    print(f"\nSteps:")
    
    for step in report.steps:
        status = "✓" if step.success else "✗"
        print(f"  {status} {step.step} ({step.duration_sec:.1f}s)")
        if not step.success and step.error:
            print(f"    Error: {step.error[:100]}")
    
    return 0 if report.success else 1


def cmd_health(args: argparse.Namespace) -> int:
    """运行健康检查"""
    from .registry import ModelRegistry
    from .env_builder import SSHConfig, run_health_checks
    
    registry = ModelRegistry()
    spec = registry.get(args.model)
    
    if not spec:
        LOGGER.error(f"Model not found: {args.model}")
        return 1
    
    ssh = SSHConfig(
        host=args.host or "172.17.140.97",
        user=args.user or "kykt26",
        alias=args.alias or "KYKT-UI",
    )
    
    LOGGER.info(f"Running health checks for {spec.name}...")
    results = run_health_checks(ssh, spec)
    
    print(f"\n{'=' * 60}")
    print(f"HEALTH CHECK: {spec.name}")
    print(f"{'=' * 60}")
    
    all_passed = True
    for r in results:
        status = "✓" if r.success else "✗"
        print(f"  {status} {r.step}")
        if not r.success:
            all_passed = False
            if r.error:
                print(f"    Error: {r.error[:100]}")
    
    return 0 if all_passed else 1


def cmd_doctor(args: argparse.Namespace) -> int:
    """AI 诊断"""
    from .registry import ModelRegistry
    from .env_builder import SSHConfig, run_health_checks
    from .health_doctor import HealthDoctor
    
    registry = ModelRegistry()
    spec = registry.get(args.model)
    
    if not spec:
        LOGGER.error(f"Model not found: {args.model}")
        return 1
    
    ssh = SSHConfig(
        host=args.host or "172.17.140.97",
        user=args.user or "kykt26",
        alias=args.alias or "KYKT-UI",
    )
    
    LOGGER.info(f"Running health checks for {spec.name}...")
    results = run_health_checks(ssh, spec)
    
    LOGGER.info(f"Diagnosing issues...")
    doctor = HealthDoctor()
    report = doctor.diagnose(spec, results)
    doctor.print_report(report)
    
    return 0 if report.overall_status == "healthy" else 1


def main() -> int:
    """CLI 主入口"""
    parser = argparse.ArgumentParser(
        prog="agent",
        description="3R All-in-One Agent CLI",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # list
    p_list = subparsers.add_parser("list", help="List all models")
    p_list.add_argument("--format", choices=["table", "json"], default="table")
    p_list.set_defaults(func=cmd_list)
    
    # status
    p_status = subparsers.add_parser("status", help="Show registry status")
    p_status.set_defaults(func=cmd_status)
    
    # info
    p_info = subparsers.add_parser("info", help="Show model details")
    p_info.add_argument("model", help="Model key")
    p_info.add_argument("--format", choices=["table", "json"], default="table")
    p_info.set_defaults(func=cmd_info)
    
    # validate
    p_validate = subparsers.add_parser("validate", help="Validate blueprints")
    p_validate.add_argument("model", nargs="?", help="Model key (optional)")
    p_validate.set_defaults(func=cmd_validate)
    
    # SSH 公共参数
    def add_ssh_args(p):
        p.add_argument("--host", help="SSH host")
        p.add_argument("--user", help="SSH user")
        p.add_argument("--alias", help="SSH alias from ~/.ssh/config")
    
    # smoke
    p_smoke = subparsers.add_parser("smoke", help="Run smoke test")
    p_smoke.add_argument("model", help="Model key")
    add_ssh_args(p_smoke)
    p_smoke.set_defaults(func=cmd_smoke)
    
    # build
    p_build = subparsers.add_parser("build", help="Build environment")
    p_build.add_argument("model", help="Model key")
    add_ssh_args(p_build)
    p_build.set_defaults(func=cmd_build)
    
    # health
    p_health = subparsers.add_parser("health", help="Run health checks")
    p_health.add_argument("model", help="Model key")
    add_ssh_args(p_health)
    p_health.set_defaults(func=cmd_health)
    
    # doctor
    p_doctor = subparsers.add_parser("doctor", help="AI diagnosis")
    p_doctor.add_argument("model", help="Model key")
    add_ssh_args(p_doctor)
    p_doctor.set_defaults(func=cmd_doctor)
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    if not args.command:
        parser.print_help()
        return 0
    
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
