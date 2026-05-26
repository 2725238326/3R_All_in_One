# ═══════════════════════════════════════════════════════════════
# Model Registry Tests — 模型注册表测试
# ═══════════════════════════════════════════════════════════════
"""
测试 agent/registry.py:
- 模型加载
- 查询功能
- 过滤功能
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestModelRegistryLoading:
    """模型注册表加载测试"""
    
    def test_registry_singleton(self, sample_registry):
        """注册表应为单例"""
        from agent.registry import ModelRegistry
        
        # 在 fixture 中已重置单例
        registry1 = sample_registry
        
        # 重新获取应返回同一实例
        ModelRegistry._instance = registry1
        registry2 = ModelRegistry(auto_load=False)
        
        # 单例模式：同一实例
        assert registry1 is registry2
    
    def test_load_specs_from_directory(self, tmp_model_specs_dir: Path, sample_model_spec_yaml: str):
        """从目录加载模型规格"""
        from agent.registry import ModelRegistry
        
        # 写入测试 spec
        (tmp_model_specs_dir / "model1.yaml").write_text(sample_model_spec_yaml)
        (tmp_model_specs_dir / "model2.yaml").write_text(
            sample_model_spec_yaml.replace("testmodel", "testmodel2").replace("TestModel", "TestModel2")
        )
        
        ModelRegistry._instance = None
        registry = ModelRegistry(specs_dir=tmp_model_specs_dir)
        
        assert len(list(registry.all)) >= 1
        
        ModelRegistry._instance = None
    
    def test_skip_underscore_files(self, tmp_model_specs_dir: Path, sample_model_spec_yaml: str):
        """应跳过下划线开头的文件"""
        from agent.registry import ModelRegistry
        
        (tmp_model_specs_dir / "valid.yaml").write_text(sample_model_spec_yaml)
        (tmp_model_specs_dir / "_template.yaml").write_text(sample_model_spec_yaml)
        
        ModelRegistry._instance = None
        registry = ModelRegistry(specs_dir=tmp_model_specs_dir)
        
        keys = [s.key for s in registry.all]
        assert "_template" not in str(keys)
        
        ModelRegistry._instance = None


class TestModelRegistryQuery:
    """模型注册表查询测试"""
    
    def test_get_by_key(self, sample_registry):
        """按 key 获取模型"""
        spec = sample_registry.get("testmodel")
        
        assert spec is not None
        assert spec.key == "testmodel"
        assert spec.name == "TestModel"
    
    def test_get_nonexistent_returns_none(self, sample_registry):
        """获取不存在的模型返回 None"""
        spec = sample_registry.get("nonexistent_model")
        assert spec is None
    
    def test_getitem_raises_on_missing(self, sample_registry):
        """__getitem__ 对不存在的模型抛出异常"""
        with pytest.raises(KeyError):
            _ = sample_registry["nonexistent_model"]
    
    def test_contains(self, sample_registry):
        """__contains__ 检查"""
        assert "testmodel" in sample_registry
        assert "nonexistent" not in sample_registry


class TestModelRegistryFilter:
    """模型注册表过滤测试"""
    
    def test_filter_by_family(self, sample_registry):
        """按 family 过滤"""
        dust3r_models = list(sample_registry.by_family("dust3r"))
        
        for spec in dust3r_models:
            assert spec.family == "dust3r"
    
    def test_all_iterator(self, sample_registry):
        """all() 返回迭代器"""
        all_specs = list(sample_registry.all)
        
        assert len(all_specs) >= 1
        assert all(hasattr(s, 'key') for s in all_specs)


class TestModelSpec:
    """ModelSpec 数据类测试"""
    
    def test_spec_attributes(self, sample_registry):
        """ModelSpec 应有必要属性"""
        spec = sample_registry.get("testmodel")
        
        assert hasattr(spec, 'key')
        assert hasattr(spec, 'name')
        assert hasattr(spec, 'family')
        assert hasattr(spec, 'version')
    
    def test_spec_from_yaml(self, tmp_model_specs_dir: Path, sample_model_spec_yaml: str):
        """从 YAML 加载 ModelSpec"""
        from agent.env_builder import ModelSpec
        
        yaml_path = tmp_model_specs_dir / "test.yaml"
        yaml_path.write_text(sample_model_spec_yaml)
        
        spec = ModelSpec.from_yaml(yaml_path)
        
        assert spec.key == "testmodel"
        assert spec.family == "dust3r"


class TestModelRegistryReload:
    """模型注册表重载测试"""
    
    def test_reload_updates_registry(self, tmp_model_specs_dir: Path, sample_model_spec_yaml: str):
        """reload() 应更新注册表"""
        from agent.registry import ModelRegistry
        
        # 初始加载
        (tmp_model_specs_dir / "model1.yaml").write_text(sample_model_spec_yaml)
        
        ModelRegistry._instance = None
        registry = ModelRegistry(specs_dir=tmp_model_specs_dir)
        
        initial_count = len(list(registry.all))
        
        # 添加新文件
        (tmp_model_specs_dir / "model2.yaml").write_text(
            sample_model_spec_yaml.replace("testmodel", "newmodel").replace("TestModel", "NewModel")
        )
        
        # 重载
        registry.reload()
        
        new_count = len(list(registry.all))
        assert new_count > initial_count
        
        ModelRegistry._instance = None
