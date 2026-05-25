# ═══════════════════════════════════════════════════════════════
# Model Registry — 模型注册表
# 管理所有 3R 模型的蓝图，提供查询、过滤、排序功能
# ═══════════════════════════════════════════════════════════════
"""
ModelRegistry 是 Agent 框架的核心组件：
- 自动扫描 model_specs/ 目录
- 提供按 key/family/status/type 查询
- 缓存已加载的 ModelSpec
- 支持热重载
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterator

from .env_builder import ModelSpec

LOGGER = logging.getLogger("agent.registry")


class ModelRegistry:
    """模型蓝图注册表"""
    
    _instance: ModelRegistry | None = None
    
    def __new__(cls, *args, **kwargs):
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, specs_dir: Path | str | None = None, auto_load: bool = True):
        if self._initialized:
            return
        
        if specs_dir is None:
            specs_dir = Path(__file__).parent / "model_specs"
        
        self.specs_dir = Path(specs_dir)
        self._specs: dict[str, ModelSpec] = {}
        self._initialized = True
        
        if auto_load:
            self.reload()

    # ─────────────── 加载 ───────────────

    def reload(self) -> int:
        """重新加载所有蓝图，返回加载数量"""
        self._specs.clear()
        count = 0
        
        for yaml_file in self.specs_dir.glob("*.yaml"):
            if yaml_file.name.startswith("_"):
                continue
            try:
                spec = ModelSpec.from_yaml(yaml_file)
                self._specs[spec.key] = spec
                count += 1
                LOGGER.debug(f"Loaded: {spec.key} ({spec.status})")
            except Exception as e:
                LOGGER.warning(f"Failed to load {yaml_file.name}: {e}")
        
        LOGGER.info(f"Registry loaded {count} models")
        return count

    # ─────────────── 查询 ───────────────

    def get(self, key: str) -> ModelSpec | None:
        """按 key 获取模型"""
        return self._specs.get(key.lower())

    def __getitem__(self, key: str) -> ModelSpec:
        """registry["monst3r"]"""
        spec = self.get(key)
        if spec is None:
            raise KeyError(f"Model not found: {key}")
        return spec

    def __contains__(self, key: str) -> bool:
        return key.lower() in self._specs

    def __len__(self) -> int:
        return len(self._specs)

    def __iter__(self) -> Iterator[ModelSpec]:
        return iter(self._specs.values())

    @property
    def keys(self) -> list[str]:
        """所有模型 key"""
        return list(self._specs.keys())

    @property
    def all(self) -> list[ModelSpec]:
        """所有模型"""
        return list(self._specs.values())

    # ─────────────── 过滤 ───────────────

    def filter(
        self,
        *,
        family: str | None = None,
        status: str | None = None,
        model_type: str | None = None,
        paradigm: str | None = None,
        needs_curope: bool | None = None,
        is_ready: bool | None = None,
    ) -> list[ModelSpec]:
        """按条件过滤模型"""
        results = self.all
        
        if family:
            results = [s for s in results if s.family == family]
        if status:
            results = [s for s in results if s.status == status]
        if model_type:
            results = [s for s in results if s.model_type == model_type]
        if paradigm:
            results = [s for s in results if s.paradigm == paradigm]
        if needs_curope is not None:
            results = [s for s in results if s.needs_curope == needs_curope]
        if is_ready is not None:
            results = [s for s in results if s.is_ready == is_ready]
        
        return results

    def by_family(self, family: str) -> list[ModelSpec]:
        """按家族过滤"""
        return self.filter(family=family)

    def by_status(self, status: str) -> list[ModelSpec]:
        """按状态过滤"""
        return self.filter(status=status)

    def integrated(self) -> list[ModelSpec]:
        """获取所有已集成的模型"""
        return self.filter(status="integrated")

    def env_ready(self) -> list[ModelSpec]:
        """获取环境就绪但 runner 未完成的模型"""
        return self.filter(status="env_ready")

    def with_issues(self) -> list[ModelSpec]:
        """获取有未解决问题的模型"""
        return [s for s in self.all if s.unresolved_issues]

    # ─────────────── 排序 ───────────────

    def sorted_by_priority(self) -> list[ModelSpec]:
        """按优先级排序"""
        priority_order = {"high": 0, "baseline": 1, "normal": 2, "low": 3}
        return sorted(
            self.all,
            key=lambda s: priority_order.get(s.priority, 99)
        )

    def sorted_by_gpu_memory(self, ascending: bool = True) -> list[ModelSpec]:
        """按显存需求排序"""
        return sorted(
            self.all,
            key=lambda s: s.resources.get("gpu_memory_gb", 0),
            reverse=not ascending
        )

    # ─────────────── 摘要 ───────────────

    def summary(self) -> dict:
        """生成注册表摘要"""
        all_specs = self.all
        return {
            "total": len(all_specs),
            "integrated": len(self.integrated()),
            "env_ready": len(self.env_ready()),
            "with_issues": len(self.with_issues()),
            "by_family": self._count_by("family"),
            "by_status": self._count_by("status"),
            "by_paradigm": {
                s.paradigm: sum(1 for x in all_specs if x.paradigm == s.paradigm)
                for s in all_specs
            },
        }

    def _count_by(self, attr: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for spec in self.all:
            val = getattr(spec, attr, "unknown")
            counts[val] = counts.get(val, 0) + 1
        return counts

    def print_status(self) -> None:
        """打印状态表"""
        print("\n" + "=" * 70)
        print("MODEL REGISTRY STATUS")
        print("=" * 70)
        print(f"{'Key':<12} {'Name':<12} {'Type':<18} {'Status':<12} {'GPU(GB)':<8}")
        print("-" * 70)
        for spec in self.sorted_by_priority():
            issues = f" ⚠{len(spec.unresolved_issues)}" if spec.unresolved_issues else ""
            print(
                f"{spec.key:<12} {spec.name:<12} {spec.model_type:<18} "
                f"{spec.status:<12} {spec.resources.get('gpu_memory_gb', '?'):<8}{issues}"
            )
        print("-" * 70)
        s = self.summary()
        print(f"Total: {s['total']} | Integrated: {s['integrated']} | "
              f"Env Ready: {s['env_ready']} | With Issues: {s['with_issues']}")
        print()


# ─────────────── 便捷函数 ───────────────

def get_registry() -> ModelRegistry:
    """获取全局注册表实例"""
    return ModelRegistry()


def get_model(key: str) -> ModelSpec | None:
    """快速获取模型"""
    return get_registry().get(key)


# ─────────────── CLI 入口 ───────────────

def main():
    """命令行入口"""
    import sys
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    registry = ModelRegistry()
    
    if len(sys.argv) > 1:
        key = sys.argv[1]
        spec = registry.get(key)
        if spec:
            import json
            print(json.dumps(spec.summary(), indent=2, ensure_ascii=False))
        else:
            print(f"Model not found: {key}")
            print(f"Available: {', '.join(registry.keys)}")
            sys.exit(1)
    else:
        registry.print_status()


if __name__ == "__main__":
    main()
