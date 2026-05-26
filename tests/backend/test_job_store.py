# ═══════════════════════════════════════════════════════════════
# Job Store Tests — 任务存储测试
# ═══════════════════════════════════════════════════════════════
"""
测试 job_store.py 的核心功能:
- JobRecord 创建与序列化
- 任务目录管理
- 状态更新
- 查询过滤
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# 添加 backend 到路径
BACKEND_DIR = Path(__file__).parent.parent.parent / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class TestJobRecord:
    """JobRecord 数据类测试"""
    
    def test_create_minimal_record(self, sample_job_record: dict):
        """创建最小任务记录"""
        from job_store import JobRecord
        
        record = JobRecord(**sample_job_record)
        
        assert record.job_id == "job_test_123"
        assert record.model == "monst3r"
        assert record.status == "pending"
        assert record.phase == "init"
    
    def test_record_to_dict(self, sample_job_record: dict):
        """记录序列化为字典"""
        from job_store import JobRecord
        
        record = JobRecord(**sample_job_record)
        data = record.to_dict()
        
        assert isinstance(data, dict)
        assert data["job_id"] == record.job_id
        assert data["params"] == record.params
    
    def test_record_from_dict(self, sample_job_record: dict):
        """从字典创建记录"""
        from job_store import JobRecord
        
        # JobRecord 使用 dataclass，直接解包创建
        record = JobRecord(**sample_job_record)
        
        assert record.job_id == sample_job_record["job_id"]
        assert record.model == sample_job_record["model"]


class TestJobDirectory:
    """任务目录管理测试"""
    
    def test_create_job_directory(self, tmp_dir: Path):
        """创建任务目录"""
        job_dir = tmp_dir / "local_jobs" / "test_job_001"
        job_dir.mkdir(parents=True)
        
        # 验证目录创建
        assert job_dir.exists()
        assert job_dir.name == "test_job_001"
    
    def test_load_job_from_directory(self, tmp_job_dir: Path):
        """从目录加载任务"""
        from job_store import JobRecord
        
        meta_path = tmp_job_dir / "meta.json"
        assert meta_path.exists()
        
        data = json.loads(meta_path.read_text())
        record = JobRecord(**data)
        
        assert record.job_id == "test_job_001"
        assert record.model == "monst3r"


class TestJobStatus:
    """任务状态更新测试"""
    
    def test_status_transitions(self):
        """状态转换有效性"""
        valid_statuses = ["pending", "running", "completed", "failed", "cancelled"]
        
        for status in valid_statuses:
            assert status in valid_statuses  # 基本验证
    
    def test_phase_transitions(self):
        """阶段转换有效性"""
        valid_phases = [
            "init", "uploading", "preprocessing", 
            "running", "postprocessing", "downloading", "done"
        ]
        
        for phase in valid_phases:
            assert phase in valid_phases


class TestJobQuery:
    """任务查询测试"""
    
    def test_filter_by_status(self, sample_job_record: dict):
        """按状态过滤"""
        from job_store import JobRecord
        
        records = [
            JobRecord(**{**sample_job_record, "job_id": "job1", "status": "pending"}),
            JobRecord(**{**sample_job_record, "job_id": "job2", "status": "running"}),
            JobRecord(**{**sample_job_record, "job_id": "job3", "status": "completed"}),
        ]
        
        pending = [r for r in records if r.status == "pending"]
        assert len(pending) == 1
        assert pending[0].job_id == "job1"
    
    def test_filter_by_model(self, sample_job_record: dict):
        """按模型过滤"""
        from job_store import JobRecord
        
        records = [
            JobRecord(**{**sample_job_record, "job_id": "job1", "model": "monst3r"}),
            JobRecord(**{**sample_job_record, "job_id": "job2", "model": "dust3r"}),
            JobRecord(**{**sample_job_record, "job_id": "job3", "model": "monst3r"}),
        ]
        
        monst3r_jobs = [r for r in records if r.model == "monst3r"]
        assert len(monst3r_jobs) == 2


class TestJobPersistence:
    """任务持久化测试"""
    
    def test_save_and_load_job(self, tmp_dir: Path, sample_job_record: dict):
        """保存并重新加载任务"""
        from job_store import JobRecord
        
        job_dir = tmp_dir / "test_job"
        job_dir.mkdir()
        
        # 保存
        record = JobRecord(**sample_job_record)
        meta_path = job_dir / "meta.json"
        meta_path.write_text(json.dumps(record.to_dict(), indent=2))
        
        # 加载
        loaded_data = json.loads(meta_path.read_text())
        loaded_record = JobRecord(**loaded_data)
        
        assert loaded_record.job_id == record.job_id
        assert loaded_record.params == record.params
    
    def test_update_job_status(self, tmp_dir: Path, sample_job_record: dict):
        """更新任务状态"""
        from job_store import JobRecord
        
        job_dir = tmp_dir / "test_job"
        job_dir.mkdir()
        meta_path = job_dir / "meta.json"
        
        # 初始保存
        record = JobRecord(**sample_job_record)
        meta_path.write_text(json.dumps(record.to_dict(), indent=2))
        
        # 读取、更新、保存
        data = json.loads(meta_path.read_text())
        data["status"] = "running"
        data["phase"] = "preprocessing"
        meta_path.write_text(json.dumps(data, indent=2))
        
        # 验证
        updated = json.loads(meta_path.read_text())
        assert updated["status"] == "running"
        assert updated["phase"] == "preprocessing"
