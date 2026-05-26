# ═══════════════════════════════════════════════════════════════
# Schema Validator Tests — 蓝图验证器测试
# ═══════════════════════════════════════════════════════════════
"""
测试 agent/schema_validator.py:
- YAML 格式验证
- 必填字段检查
- 类型验证
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class TestSchemaValidation:
    """蓝图 Schema 验证测试"""
    
    def test_valid_spec_passes(self, tmp_model_specs_dir: Path, sample_model_spec_yaml: str):
        """有效的规格应通过验证"""
        yaml_path = tmp_model_specs_dir / "valid.yaml"
        yaml_path.write_text(sample_model_spec_yaml)
        
        from agent.schema_validator import SchemaValidator
        
        validator = SchemaValidator(specs_dir=tmp_model_specs_dir)
        result = validator.validate_file(yaml_path)
        assert len(result.issues) == 0, f"Unexpected errors: {result.issues}"
    
    def test_missing_required_field(self, tmp_model_specs_dir: Path):
        """缺少必填字段应报错"""
        invalid_yaml = """
name: TestModel
# 缺少 key, family 等必填字段
"""
        yaml_path = tmp_model_specs_dir / "invalid.yaml"
        yaml_path.write_text(invalid_yaml)
        
        from agent.schema_validator import SchemaValidator
        
        validator = SchemaValidator(specs_dir=tmp_model_specs_dir)
        result = validator.validate_file(yaml_path)
        assert len(result.issues) > 0
    
    def test_invalid_yaml_syntax(self, tmp_model_specs_dir: Path):
        """无效 YAML 语法应报错"""
        invalid_yaml = """
name: TestModel
key: testmodel
  invalid_indent: true
"""
        yaml_path = tmp_model_specs_dir / "syntax_error.yaml"
        yaml_path.write_text(invalid_yaml)
        
        from agent.schema_validator import SchemaValidator
        
        validator = SchemaValidator(specs_dir=tmp_model_specs_dir)
        result = validator.validate_file(yaml_path)
        assert len(result.issues) > 0


class TestFieldValidation:
    """字段级别验证测试"""
    
    def test_valid_tags(self, tmp_model_specs_dir: Path, sample_model_spec_yaml: str):
        """有效的 tags 配置"""
        yaml_path = tmp_model_specs_dir / "valid_tags.yaml"
        yaml_path.write_text(sample_model_spec_yaml)
        
        from agent.schema_validator import SchemaValidator
        
        validator = SchemaValidator(specs_dir=tmp_model_specs_dir)
        result = validator.validate_file(yaml_path)
        tag_errors = [e for e in result.issues if "tags" in str(e).lower()]
        assert len(tag_errors) == 0
    
    def test_valid_environment(self, tmp_model_specs_dir: Path, sample_model_spec_yaml: str):
        """有效的 environment 配置"""
        yaml_path = tmp_model_specs_dir / "valid_env.yaml"
        yaml_path.write_text(sample_model_spec_yaml)
        
        from agent.schema_validator import SchemaValidator
        
        validator = SchemaValidator(specs_dir=tmp_model_specs_dir)
        result = validator.validate_file(yaml_path)
        env_errors = [e for e in result.issues if "environment" in str(e).lower()]
        assert len(env_errors) == 0


class TestBatchValidation:
    """批量验证测试"""
    
    def test_validate_all_specs(self, agent_dir: Path):
        """验证所有真实的模型规格"""
        from agent.schema_validator import SchemaValidator
        
        specs_dir = agent_dir / "model_specs"
        if not specs_dir.exists():
            pytest.skip("model_specs directory not found")
        
        validator = SchemaValidator(specs_dir=specs_dir)
        all_errors = {}
        
        for yaml_file in specs_dir.glob("*.yaml"):
            if yaml_file.name.startswith("_"):
                continue
            
            result = validator.validate_file(yaml_file)
            if result.issues:
                all_errors[yaml_file.name] = result.issues
        
        # 真实规格应该全部通过验证
        assert len(all_errors) == 0, f"Validation errors: {all_errors}"
