# ═══════════════════════════════════════════════════════════════
# Schema Validator — 模型蓝图校验器
# 确保每个 model_specs/*.yaml 符合 SCHEMA.md 规范
# ═══════════════════════════════════════════════════════════════
"""
蓝图校验等级：
- ERROR: 阻塞级错误，必须修复
- WARNING: 建议修复，不阻塞
- INFO: 仅提示
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

LOGGER = logging.getLogger("agent.schema_validator")


# ─────────────── 校验结果 ───────────────

@dataclass
class ValidationIssue:
    """单个校验问题"""
    level: str  # "error" | "warning" | "info"
    field: str
    message: str
    suggestion: str = ""


@dataclass
class ValidationResult:
    """蓝图校验结果"""
    model: str
    path: str
    valid: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    
    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "error"]
    
    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.level == "warning"]
    
    def summary(self) -> str:
        e, w = len(self.errors), len(self.warnings)
        status = "[OK] VALID" if self.valid else "[FAIL] INVALID"
        return f"{self.model}: {status} ({e} errors, {w} warnings)"


# ─────────────── Schema 定义 ───────────────

REQUIRED_FIELDS = {
    "name": str,
    "key": str,
    "family": str,
    "tags": dict,
    "repo": dict,
    "environment": dict,
    "checkpoints": list,
    "runner": dict,
    "output_contract": dict,
    "status": str,
}

REQUIRED_REPO_FIELDS = ["url", "server_path"]
REQUIRED_ENV_FIELDS = ["conda_env", "python", "torch"]
REQUIRED_RUNNER_FIELDS = ["script", "conda_env"]

VALID_STATUS_VALUES = ["integrated", "env_ready", "wip", "planned", "deprecated"]
VALID_CREATE_STRATEGIES = ["fresh", "clone_from"]
VALID_CHECK_TYPES = ["import", "cuda_kernel", "file_exists", "command"]


# ─────────────── 校验器 ───────────────

class SchemaValidator:
    """模型蓝图校验器"""

    def __init__(self, specs_dir: Path | str | None = None):
        if specs_dir is None:
            specs_dir = Path(__file__).parent / "model_specs"
        self.specs_dir = Path(specs_dir)

    def validate_file(self, path: Path) -> ValidationResult:
        """校验单个 YAML 文件"""
        issues: list[ValidationIssue] = []
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except Exception as e:
            return ValidationResult(
                model=path.stem,
                path=str(path),
                valid=False,
                issues=[ValidationIssue("error", "file", f"YAML parse error: {e}")]
            )

        if not isinstance(data, dict):
            return ValidationResult(
                model=path.stem,
                path=str(path),
                valid=False,
                issues=[ValidationIssue("error", "file", "Root must be a dict")]
            )

        model_name = data.get("name", path.stem)

        # 1. 检查必填字段
        for field_name, expected_type in REQUIRED_FIELDS.items():
            if field_name not in data:
                issues.append(ValidationIssue(
                    "error", field_name,
                    f"Missing required field: {field_name}"
                ))
            elif not isinstance(data[field_name], expected_type):
                issues.append(ValidationIssue(
                    "error", field_name,
                    f"Expected {expected_type.__name__}, got {type(data[field_name]).__name__}"
                ))

        # 2. 检查 repo 子字段
        repo = data.get("repo", {})
        for rf in REQUIRED_REPO_FIELDS:
            if rf not in repo:
                issues.append(ValidationIssue(
                    "error", f"repo.{rf}",
                    f"Missing required field: repo.{rf}"
                ))

        # 3. 检查 environment 子字段
        env = data.get("environment", {})
        for ef in REQUIRED_ENV_FIELDS:
            if ef not in env:
                issues.append(ValidationIssue(
                    "error", f"environment.{ef}",
                    f"Missing required field: environment.{ef}"
                ))

        # 4. 检查 create_strategy
        strategy = env.get("create_strategy", "fresh")
        if strategy not in VALID_CREATE_STRATEGIES:
            issues.append(ValidationIssue(
                "warning", "environment.create_strategy",
                f"Unknown strategy: {strategy}",
                f"Valid: {VALID_CREATE_STRATEGIES}"
            ))
        if strategy == "clone_from" and not env.get("clone_source"):
            issues.append(ValidationIssue(
                "error", "environment.clone_source",
                "clone_from strategy requires clone_source"
            ))

        # 5. 检查 status
        status = data.get("status", "")
        if status and status not in VALID_STATUS_VALUES:
            issues.append(ValidationIssue(
                "warning", "status",
                f"Unknown status: {status}",
                f"Valid: {VALID_STATUS_VALUES}"
            ))

        # 6. 检查 checkpoints
        checkpoints = data.get("checkpoints", [])
        for i, ckpt in enumerate(checkpoints):
            if not isinstance(ckpt, dict):
                issues.append(ValidationIssue(
                    "error", f"checkpoints[{i}]",
                    "Checkpoint must be a dict"
                ))
                continue
            if "name" not in ckpt:
                issues.append(ValidationIssue(
                    "error", f"checkpoints[{i}].name",
                    "Missing checkpoint name"
                ))
            if "path" not in ckpt:
                issues.append(ValidationIssue(
                    "error", f"checkpoints[{i}].path",
                    "Missing checkpoint path"
                ))

        # 7. 检查 health_checks
        health_checks = data.get("health_checks", [])
        for i, hc in enumerate(health_checks):
            if not isinstance(hc, dict):
                issues.append(ValidationIssue(
                    "error", f"health_checks[{i}]",
                    "Health check must be a dict"
                ))
                continue
            hc_type = hc.get("type", "")
            if hc_type and hc_type not in VALID_CHECK_TYPES:
                issues.append(ValidationIssue(
                    "warning", f"health_checks[{i}].type",
                    f"Unknown check type: {hc_type}",
                    f"Valid: {VALID_CHECK_TYPES}"
                ))

        # 8. 检查 build_steps
        build_steps = data.get("build_steps", []) or []
        for i, step in enumerate(build_steps):
            if not isinstance(step, dict):
                issues.append(ValidationIssue(
                    "error", f"build_steps[{i}]",
                    "Build step must be a dict"
                ))
                continue
            if "cmd" not in step:
                issues.append(ValidationIssue(
                    "error", f"build_steps[{i}].cmd",
                    "Build step missing cmd"
                ))

        # 9. 检查 runner
        runner = data.get("runner", {})
        for rf in REQUIRED_RUNNER_FIELDS:
            if rf not in runner:
                issues.append(ValidationIssue(
                    "error", f"runner.{rf}",
                    f"Missing required field: runner.{rf}"
                ))

        # 10. 检查 output_contract
        output = data.get("output_contract", {})
        if "required" not in output:
            issues.append(ValidationIssue(
                "warning", "output_contract.required",
                "Missing required outputs definition"
            ))

        # 11. 检查 paper（推荐但非必需）
        paper = data.get("paper", {})
        if not paper:
            issues.append(ValidationIssue(
                "info", "paper",
                "Consider adding paper reference"
            ))
        elif "url" not in paper:
            issues.append(ValidationIssue(
                "info", "paper.url",
                "Consider adding paper URL"
            ))

        # 12. 检查 last_verified 格式
        last_verified = data.get("last_verified", "")
        if last_verified and not self._is_valid_date(last_verified):
            issues.append(ValidationIssue(
                "warning", "last_verified",
                f"Invalid date format: {last_verified}",
                "Expected: YYYY-MM-DD"
            ))

        valid = not any(i.level == "error" for i in issues)
        
        return ValidationResult(
            model=model_name,
            path=str(path),
            valid=valid,
            issues=issues
        )

    def validate_all(self) -> list[ValidationResult]:
        """校验所有蓝图"""
        results = []
        for yaml_file in self.specs_dir.glob("*.yaml"):
            if yaml_file.name.startswith("_"):
                continue
            result = self.validate_file(yaml_file)
            results.append(result)
            LOGGER.info(result.summary())
        return results

    def _is_valid_date(self, s: str) -> bool:
        """检查是否为 YYYY-MM-DD 格式"""
        if len(s) != 10:
            return False
        parts = s.split("-")
        if len(parts) != 3:
            return False
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            return 2020 <= y <= 2030 and 1 <= m <= 12 and 1 <= d <= 31
        except ValueError:
            return False


# ─────────────── CLI 入口 ───────────────

def main():
    """命令行入口"""
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    validator = SchemaValidator()
    results = validator.validate_all()
    
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    total_errors = sum(len(r.errors) for r in results)
    total_warnings = sum(len(r.warnings) for r in results)
    valid_count = sum(1 for r in results if r.valid)
    
    for r in results:
        print(r.summary())
        for issue in r.errors:
            print(f"  [ERROR] {issue.field}: {issue.message}")
        for issue in r.warnings:
            print(f"  [WARN] {issue.field}: {issue.message}")
    
    print()
    print(f"Total: {valid_count}/{len(results)} valid, {total_errors} errors, {total_warnings} warnings")
    
    sys.exit(0 if total_errors == 0 else 1)


if __name__ == "__main__":
    main()
