# ═══════════════════════════════════════════════════════════════
# Health Doctor — AI 诊断模块
# 根据 known_issues 和健康检查结果，智能排障和建议修复
# ═══════════════════════════════════════════════════════════════
"""
HealthDoctor 职责：
1. 分析健康检查失败原因
2. 匹配 known_issues 知识库
3. 生成修复建议
4. 提供一键修复脚本（可选）
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .env_builder import BuildResult, ModelSpec

LOGGER = logging.getLogger("agent.health_doctor")


# ─────────────── 诊断结果 ───────────────

@dataclass
class DiagnosisItem:
    """单项诊断"""
    symptom: str
    cause: str
    solution: str
    confidence: float  # 0.0 - 1.0
    related_issue_id: str = ""
    fix_command: str = ""


@dataclass
class DiagnosisReport:
    """诊断报告"""
    model: str
    overall_status: str  # "healthy" | "fixable" | "needs_attention" | "critical"
    items: list[DiagnosisItem] = field(default_factory=list)
    
    @property
    def has_fixes(self) -> bool:
        return any(i.fix_command for i in self.items)
    
    def summary(self) -> str:
        status_marker = {
            "healthy": "[OK]",
            "fixable": "[WARN]",
            "needs_attention": "[INFO]",
            "critical": "[FAIL]"
        }
        return f"{status_marker.get(self.overall_status, '[?]')} {self.model}: {self.overall_status} ({len(self.items)} issues)"


# ─────────────── 错误模式库 ───────────────

ERROR_PATTERNS = [
    # CUDA / cuROPE
    {
        "pattern": r"undefined symbol.*GLIBC_(\d+\.\d+)",
        "symptom": "GLIBC version mismatch",
        "cause": "The compiled .so requires a newer GLIBC than available",
        "solution": "Recompile curope in the current environment: `cd croco/models/curope && python setup.py build_ext --inplace`",
        "confidence": 0.95,
    },
    {
        "pattern": r"CUDA error.*out of memory",
        "symptom": "GPU out of memory",
        "cause": "Input size exceeds GPU memory capacity",
        "solution": "Reduce num_frames, image_size, or batch_size",
        "confidence": 0.90,
    },
    {
        "pattern": r"No module named ['\"]?(\w+)['\"]?",
        "symptom": "Missing Python module",
        "cause": "Required package not installed",
        "solution": "Install the missing package: `pip install {match}`",
        "confidence": 0.85,
    },
    {
        "pattern": r"cannot find.*curope.*\.so",
        "symptom": "cuROPE not compiled",
        "cause": "CUDA extension not built",
        "solution": "Compile curope: `cd croco/models/curope && CUDA_HOME=/usr/local/cuda-12.6 TORCH_CUDA_ARCH_LIST=7.5 python setup.py build_ext --inplace`",
        "confidence": 0.95,
    },
    {
        "pattern": r"RuntimeError.*CUDA.*arch",
        "symptom": "CUDA architecture mismatch",
        "cause": "Extension compiled for different GPU architecture",
        "solution": "Recompile with correct TORCH_CUDA_ARCH_LIST (e.g., 7.5 for TITAN RTX)",
        "confidence": 0.90,
    },
    {
        "pattern": r"FileNotFoundError.*\.pth",
        "symptom": "Missing checkpoint file",
        "cause": "Model weights not downloaded",
        "solution": "Download checkpoint from HuggingFace or specified URL",
        "confidence": 0.95,
    },
    {
        "pattern": r"torch\.cuda\.is_available\(\).*False",
        "symptom": "CUDA not available",
        "cause": "PyTorch not built with CUDA or driver issue",
        "solution": "Reinstall PyTorch with CUDA: `pip install torch==2.5.1+cu121`",
        "confidence": 0.85,
    },
    {
        "pattern": r"ImportError.*libcudart",
        "symptom": "CUDA runtime library not found",
        "cause": "CUDA_HOME not set or CUDA not in PATH",
        "solution": "Set CUDA_HOME and add to PATH: `export CUDA_HOME=/usr/local/cuda-12.6`",
        "confidence": 0.90,
    },
    {
        "pattern": r"FlashAttention.*sm_(\d+)",
        "symptom": "FlashAttention architecture mismatch",
        "cause": "GPU compute capability not supported by FlashAttention",
        "solution": "Use attention_backend=pytorch_naive for older GPUs (sm75 and below)",
        "confidence": 0.95,
    },
    {
        "pattern": r"CondaError.*already exists",
        "symptom": "Conda environment conflict",
        "cause": "Environment with same name already exists",
        "solution": "Remove old env: `conda env remove -n {env_name}` or use different name",
        "confidence": 0.90,
    },
]


# ─────────────── 诊断器 ───────────────

class HealthDoctor:
    """AI 诊断模块"""

    def __init__(self):
        self.patterns = ERROR_PATTERNS

    def diagnose(
        self,
        spec: ModelSpec,
        results: list[BuildResult],
    ) -> DiagnosisReport:
        """诊断健康检查结果"""
        items: list[DiagnosisItem] = []
        
        for result in results:
            if result.success:
                continue
            
            # 尝试匹配错误模式
            error_text = f"{result.output} {result.error}"
            matched = self._match_patterns(error_text, env_name=spec.conda_env)
            
            if matched:
                items.append(matched)
            else:
                # 尝试匹配 known_issues
                issue_match = self._match_known_issues(spec, error_text, result.step)
                if issue_match:
                    items.append(issue_match)
                else:
                    # 未知错误
                    items.append(DiagnosisItem(
                        symptom=f"Failed step: {result.step}",
                        cause="Unknown error",
                        solution=f"Check logs: {result.error[:200]}",
                        confidence=0.3,
                    ))
        
        # 确定整体状态
        if not items:
            status = "healthy"
        elif all(i.confidence > 0.8 and i.fix_command for i in items):
            status = "fixable"
        elif any(i.confidence < 0.5 for i in items):
            status = "needs_attention"
        else:
            status = "critical"
        
        return DiagnosisReport(
            model=spec.name,
            overall_status=status,
            items=items
        )

    def _match_patterns(self, error_text: str, env_name: str = "") -> DiagnosisItem | None:
        """匹配错误模式"""
        for pattern in self.patterns:
            match = re.search(pattern["pattern"], error_text, re.IGNORECASE)
            if match:
                solution = pattern["solution"]
                # 替换匹配组
                if "{match}" in solution and match.groups():
                    solution = solution.replace("{match}", match.group(1))
                if "{env_name}" in solution:
                    solution = solution.replace("{env_name}", env_name or "<env_name>")
                fix_command = self._extract_fix_command(solution)
                
                return DiagnosisItem(
                    symptom=pattern["symptom"],
                    cause=pattern["cause"],
                    solution=solution,
                    confidence=pattern["confidence"],
                    fix_command=fix_command,
                )
        return None

    def _match_known_issues(
        self,
        spec: ModelSpec,
        error_text: str,
        step: str,
    ) -> DiagnosisItem | None:
        """匹配模型的 known_issues"""
        for issue in spec.known_issues:
            if issue.get("resolved", False):
                continue
            
            desc = issue.get("description", "").lower()
            # 简单关键词匹配
            keywords = desc.split()[:5]  # 取前5个词
            if any(kw in error_text.lower() for kw in keywords if len(kw) > 3):
                return DiagnosisItem(
                    symptom=issue.get("description", ""),
                    cause="Known issue in model spec",
                    solution=issue.get("workaround", "See known_issues in spec"),
                    confidence=0.85,
                    related_issue_id=issue.get("id", ""),
                )
        return None

    def suggest_fixes(self, report: DiagnosisReport) -> list[str]:
        """生成修复命令列表"""
        fixes = []
        for item in report.items:
            if item.fix_command:
                fixes.append(item.fix_command)
            else:
                command = self._extract_fix_command(item.solution)
                if command:
                    fixes.append(command)
        return fixes

    @staticmethod
    def _extract_fix_command(solution: str) -> str:
        """Extract the first shell command wrapped in backticks from a solution."""
        match = re.search(r"`([^`]+)`", solution)
        return match.group(1).strip() if match else ""

    def print_report(self, report: DiagnosisReport) -> None:
        """打印诊断报告"""
        print("\n" + "=" * 70)
        print(f"DIAGNOSIS REPORT: {report.model}")
        print("=" * 70)
        print(f"Overall Status: {report.overall_status.upper()}")
        print("-" * 70)
        
        if not report.items:
            print("[OK] No issues detected")
        else:
            for i, item in enumerate(report.items, 1):
                conf_bar = "#" * int(item.confidence * 5) + "." * (5 - int(item.confidence * 5))
                print(f"\n[{i}] {item.symptom}")
                print(f"    Cause: {item.cause}")
                print(f"    Solution: {item.solution}")
                print(f"    Confidence: [{conf_bar}] {item.confidence:.0%}")
                if item.related_issue_id:
                    print(f"    Related: {item.related_issue_id}")
        
        print("\n" + "-" * 70)
        if report.has_fixes:
            print("Suggested fix commands:")
            for cmd in self.suggest_fixes(report):
                print(f"  $ {cmd}")
        print()


# ─────────────── 便捷函数 ───────────────

def diagnose_model(spec: ModelSpec, results: list[BuildResult]) -> DiagnosisReport:
    """诊断单个模型"""
    doctor = HealthDoctor()
    return doctor.diagnose(spec, results)


def quick_diagnose(error_text: str) -> DiagnosisItem | None:
    """快速诊断错误文本"""
    doctor = HealthDoctor()
    return doctor._match_patterns(error_text)
