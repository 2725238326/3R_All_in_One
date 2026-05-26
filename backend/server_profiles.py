# ═══════════════════════════════════════════════════════════════
# 多服务器配置管理
# ═══════════════════════════════════════════════════════════════
"""
支持多 SSH 服务器 profile 的存储和切换。
存储为 JSON 文件在 local_jobs/servers/ 目录下。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from job_store import ensure_local_jobs_dir


SERVERS_DIR = ensure_local_jobs_dir() / "servers"
ACTIVE_FILE = SERVERS_DIR / "_active.json"


def _ensure_dir() -> Path:
    SERVERS_DIR.mkdir(parents=True, exist_ok=True)
    return SERVERS_DIR


def list_profiles() -> list[dict]:
    """列出所有服务器 profile"""
    _ensure_dir()
    profiles = []
    for f in SERVERS_DIR.glob("*.json"):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            profiles.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    profiles.sort(key=lambda p: p.get("alias", ""))
    return profiles


def get_profile(profile_id: str) -> dict | None:
    """获取单个 profile"""
    path = SERVERS_DIR / f"{profile_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_profile(profile_id: str, config: dict[str, Any]) -> dict:
    """保存 profile"""
    _ensure_dir()
    config["id"] = profile_id
    config.setdefault("alias", profile_id)
    config["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    
    path = SERVERS_DIR / f"{profile_id}.json"
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    return config


def delete_profile(profile_id: str) -> bool:
    """删除 profile"""
    path = SERVERS_DIR / f"{profile_id}.json"
    if path.exists():
        path.unlink()
        # 如果删的是活跃的，清空
        active = get_active_profile_id()
        if active == profile_id:
            set_active_profile_id(None)
        return True
    return False


def get_active_profile_id() -> str | None:
    """获取当前活跃 profile ID"""
    _ensure_dir()
    if not ACTIVE_FILE.exists():
        return None
    try:
        data = json.loads(ACTIVE_FILE.read_text(encoding="utf-8"))
        return data.get("active_id")
    except (json.JSONDecodeError, OSError):
        return None


def set_active_profile_id(profile_id: str | None) -> None:
    """设置活跃 profile"""
    _ensure_dir()
    ACTIVE_FILE.write_text(
        json.dumps({"active_id": profile_id}, ensure_ascii=False),
        encoding="utf-8",
    )


def get_active_profile() -> dict | None:
    """获取当前活跃 profile 的完整配置"""
    active_id = get_active_profile_id()
    if not active_id:
        return None
    return get_profile(active_id)


def profile_to_server_config(profile: dict):
    """将 profile dict 转为 ServerConfig dataclass"""
    from ssh_runner import ServerConfig
    
    field_names = {f.name for f in ServerConfig.__dataclass_fields__.values()}
    kwargs = {k: v for k, v in profile.items() if k in field_names}
    return ServerConfig(**kwargs)
