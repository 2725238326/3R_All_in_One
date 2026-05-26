# ═══════════════════════════════════════════════════════════════
# 参数模板管理
# ═══════════════════════════════════════════════════════════════
"""
保存和加载模型参数模板，方便复用。
存储为 JSON 文件在 local_jobs/templates/ 目录下。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from job_store import ensure_local_jobs_dir


TEMPLATES_DIR = ensure_local_jobs_dir() / "templates"


def _ensure_templates_dir() -> Path:
    TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
    return TEMPLATES_DIR


def list_templates(model: str | None = None) -> list[dict]:
    """列出所有模板，可按模型筛选"""
    _ensure_templates_dir()
    templates = []
    for f in TEMPLATES_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            if model and data.get("model") != model:
                continue
            templates.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    templates.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
    return templates


def get_template(template_id: str) -> dict | None:
    """获取单个模板"""
    path = TEMPLATES_DIR / f"{template_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_template(
    template_id: str,
    name: str,
    model: str,
    params: dict[str, Any],
    source_type: str = "images",
    notes: str = "",
) -> dict:
    """保存模板"""
    _ensure_templates_dir()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    
    existing = get_template(template_id)
    created_at = existing["created_at"] if existing else now
    
    template = {
        "id": template_id,
        "name": name,
        "model": model,
        "source_type": source_type,
        "params": params,
        "notes": notes,
        "created_at": created_at,
        "updated_at": now,
    }
    
    path = TEMPLATES_DIR / f"{template_id}.json"
    path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
    return template


def delete_template(template_id: str) -> bool:
    """删除模板"""
    path = TEMPLATES_DIR / f"{template_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False


def make_template_id(name: str) -> str:
    """从名称生成模板 ID"""
    import re
    base = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", name).strip("_").lower()
    if not base:
        base = "template"
    return f"{base}_{int(time.time())}"
