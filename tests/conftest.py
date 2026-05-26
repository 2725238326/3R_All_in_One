# ═══════════════════════════════════════════════════════════════
# Pytest Fixtures — 共享测试夹具
# ═══════════════════════════════════════════════════════════════
"""
全局 fixtures，提供:
- 临时目录
- FastAPI TestClient
- Mock SSH
- 样本模型规格
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ─────────────── 路径设置 ───────────────

ROOT = Path(__file__).parent.parent
BACKEND_DIR = ROOT / "backend"
AGENT_DIR = ROOT / "agent"


@pytest.fixture(scope="session")
def project_root() -> Path:
    """项目根目录"""
    return ROOT


@pytest.fixture(scope="session")
def backend_dir() -> Path:
    """后端目录"""
    return BACKEND_DIR


@pytest.fixture(scope="session")
def agent_dir() -> Path:
    """Agent 目录"""
    return AGENT_DIR


# ─────────────── 临时目录 ───────────────

@pytest.fixture
def tmp_dir() -> Generator[Path, None, None]:
    """创建临时目录，测试后自动清理"""
    tmp = Path(tempfile.mkdtemp(prefix="3r_test_"))
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def tmp_job_dir(tmp_dir: Path) -> Path:
    """模拟任务目录结构"""
    job_dir = tmp_dir / "local_jobs" / "test_job_001"
    job_dir.mkdir(parents=True)
    
    # 创建基本结构
    (job_dir / "inputs").mkdir()
    (job_dir / "outputs").mkdir()
    
    # 创建元数据（包含 JobRecord 所有字段）
    meta = {
        "job_id": "test_job_001",
        "created_at": "2026-05-26T12:00:00",
        "model": "monst3r",
        "source_type": "video",
        "notes": "Test job",
        "sample_id": None,
        "params": {"scenegraph_type": "swinstride-5-noncyclic"},
        "status": "pending",
        "phase": "init",
        "input_files": [],
        "input_items": [],
        "output_files": [],
        "remote_job_dir": None,
        "remote_runner": None,
        "error_message": None,
        "progress_message": None,
    }
    (job_dir / "meta.json").write_text(json.dumps(meta, indent=2))
    
    return job_dir


@pytest.fixture
def tmp_model_specs_dir(tmp_dir: Path) -> Path:
    """临时模型规格目录"""
    specs_dir = tmp_dir / "model_specs"
    specs_dir.mkdir()
    return specs_dir


# ─────────────── FastAPI TestClient ───────────────

@pytest.fixture(scope="module")
def test_client() -> Generator[TestClient, None, None]:
    """FastAPI 测试客户端"""
    import sys
    
    # 确保 backend 在路径中
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    
    from app import app
    
    with TestClient(app) as client:
        yield client


@pytest.fixture
def isolated_test_client(tmp_dir: Path) -> Generator[TestClient, None, None]:
    """
    隔离的测试客户端
    使用临时目录，避免污染真实数据
    """
    import sys
    
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    
    # Patch 数据目录
    with patch("runtime_paths._DATA_ROOT", tmp_dir):
        from app import app
        with TestClient(app) as client:
            yield client


# ─────────────── SSH Mock ───────────────

@pytest.fixture
def mock_ssh_client() -> MagicMock:
    """Mock paramiko SSH 客户端"""
    mock = MagicMock()
    
    # Mock exec_command
    mock_stdin = MagicMock()
    mock_stdout = MagicMock()
    mock_stderr = MagicMock()
    
    mock_stdout.read.return_value = b"success"
    mock_stdout.channel.recv_exit_status.return_value = 0
    mock_stderr.read.return_value = b""
    
    mock.exec_command.return_value = (mock_stdin, mock_stdout, mock_stderr)
    
    # Mock SFTP
    mock_sftp = MagicMock()
    mock.open_sftp.return_value = mock_sftp
    
    return mock


@pytest.fixture
def mock_ssh_connection(mock_ssh_client: MagicMock):
    """Patch paramiko.SSHClient"""
    with patch("paramiko.SSHClient") as MockSSH:
        MockSSH.return_value = mock_ssh_client
        yield mock_ssh_client


# ─────────────── 样本数据 ───────────────

@pytest.fixture
def sample_model_spec_yaml() -> str:
    """完整的模型规格 YAML，满足 schema_validator 要求"""
    return """
name: TestModel
key: testmodel
family: dust3r
version: "1.0.0"
status: integrated

paper:
  title: "Test Paper"
  url: https://arxiv.org/abs/0000.00000
  venue: Test 2024
  year: 2024

tags:
  type: static
  input: [images]
  output: [pointcloud]

repo:
  url: https://github.com/test/testmodel
  branch: main
  server_path: /test/path

environment:
  conda_env: testmodel
  python: "3.11"
  torch: "2.0.0"

runner:
  script: run_testmodel.py
  conda_env: testmodel

output_contract:
  required: [output.ply]
  optional: []

checkpoints: []
"""


@pytest.fixture
def sample_job_record() -> dict:
    """样本任务记录，包含 JobRecord 所有字段"""
    return {
        "job_id": "job_test_123",
        "created_at": "2026-05-26T12:00:00",
        "model": "monst3r",
        "source_type": "video",
        "notes": "Test job",
        "sample_id": None,
        "params": {
            "scenegraph_type": "swinstride-5-noncyclic",
            "winsize": 5
        },
        "status": "pending",
        "phase": "init",
        "input_files": ["video.mp4"],
        "input_items": [
            {
                "original_name": "video.mp4",
                "stored_name": "video.mp4",
                "relative_path": "inputs/video.mp4",
                "size_bytes": 1024000
            }
        ],
        "output_files": [],
        "remote_job_dir": None,
        "remote_runner": None,
        "error_message": None,
        "progress_message": None,
    }


# ─────────────── 模型注册表 ───────────────

@pytest.fixture
def sample_registry(tmp_model_specs_dir: Path, sample_model_spec_yaml: str):
    """带有样本数据的模型注册表"""
    # 写入测试 spec
    spec_file = tmp_model_specs_dir / "testmodel.yaml"
    spec_file.write_text(sample_model_spec_yaml)
    
    import sys
    # 添加项目根目录到路径，以支持包导入
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    
    from agent.registry import ModelRegistry
    
    # 重置单例
    ModelRegistry._instance = None
    registry = ModelRegistry(specs_dir=tmp_model_specs_dir)
    
    yield registry
    
    # 清理单例
    ModelRegistry._instance = None


# ─────────────── 辅助函数 ───────────────

@pytest.fixture
def create_test_image(tmp_dir: Path):
    """创建测试图片的工厂函数"""
    def _create(name: str = "test.jpg", size: tuple[int, int] = (100, 100)) -> Path:
        try:
            from PIL import Image
            img = Image.new("RGB", size, color="red")
            path = tmp_dir / name
            img.save(path)
            return path
        except ImportError:
            # 如果没有 PIL，创建空文件
            path = tmp_dir / name
            path.write_bytes(b"\xff\xd8\xff" + b"\x00" * 100)  # 简单的 JPEG header
            return path
    
    return _create


@pytest.fixture
def create_test_video(tmp_dir: Path):
    """创建测试视频的工厂函数（返回空文件）"""
    def _create(name: str = "test.mp4") -> Path:
        path = tmp_dir / name
        # 简单的 MP4 header
        path.write_bytes(b"\x00\x00\x00\x1c\x66\x74\x79\x70" + b"\x00" * 100)
        return path
    
    return _create
