from __future__ import annotations

import json
import os
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
LOCAL_JOBS_DIR = ROOT / "local_jobs"
DEVELOPMENT_MANIFEST_PATH = LOCAL_JOBS_DIR / "development_manifest.json"
_DEVELOPMENT_STORE_LOCK = threading.RLock()

CATEGORIES = {"paper_reproduction", "model_runner", "prototype", "evaluation", "ui_workflow"}
STATUSES = {"draft", "scoped", "reproducing", "prototype", "smoke_ready", "validated", "merged", "deferred"}
PRIORITIES = {"P0", "P1", "P2", "P3"}
MERGE_TARGETS = {"runner", "sample_matrix", "advisor", "report", "deferred_research"}

DEFAULT_DEVELOPMENT_ITEMS = [
    {
        "id": "lane-1",
        "title": "MASt3R 视觉对齐优化",
        "category": "model_runner",
        "status": "reproducing",
        "priority": "P0",
        "targetModel": "mast3r",
        "nextAction": "验证新版 align3r 损失函数对大基线图组的稳定性。",
        "blockers": ["远端服务器 GPU 显存限制"],
        "mergeTarget": "runner",
    },
    {
        "id": "lane-2",
        "title": "Spann3R 增量重建原型",
        "category": "prototype",
        "status": "prototype",
        "priority": "P1",
        "targetModel": "spann3r",
        "nextAction": "定义流式输入契约，支持动态增长的帧序列。",
        "blockers": [],
        "mergeTarget": "runner",
    },
    {
        "id": "lane-3",
        "title": "自动评估 Rubric v2",
        "category": "evaluation",
        "status": "scoped",
        "priority": "P2",
        "nextAction": "对齐 Advisor 提示词与人工评分维度。",
        "blockers": [],
        "mergeTarget": "advisor",
    },
]


class DevelopmentStoreError(ValueError):
    pass


@dataclass
class DevelopmentItem:
    id: str
    title: str
    category: str
    status: str
    priority: str
    next_action: str
    blockers: list[str] = field(default_factory=list)
    target_model: str | None = None
    merge_target: str | None = None
    created_at: str = ""
    updated_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "status": self.status,
            "priority": self.priority,
            "targetModel": self.target_model,
            "nextAction": self.next_action,
            "blockers": list(self.blockers),
            "mergeTarget": self.merge_target,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "metadata": dict(self.metadata),
        }


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _make_item_id() -> str:
    return f"dev-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _read_field(payload: dict, snake_name: str, camel_name: str | None = None, default: Any = None) -> Any:
    if snake_name in payload:
        return payload[snake_name]
    if camel_name and camel_name in payload:
        return payload[camel_name]
    return default


def _normalize_blockers(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    raise DevelopmentStoreError("blockers must be a list of strings.")


def _normalize_metadata(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise DevelopmentStoreError("metadata must be an object.")
    return dict(value)


def _normalize_item(payload: dict, *, existing: DevelopmentItem | None = None, partial: bool = False) -> DevelopmentItem:
    if not isinstance(payload, dict):
        raise DevelopmentStoreError("Development item payload must be a JSON object.")

    now = _now_iso()
    item_id = existing.id if existing else str(_read_field(payload, "id", default=_make_item_id())).strip()
    title = _read_field(payload, "title", default=existing.title if existing else None)
    category = _read_field(payload, "category", default=existing.category if existing else "paper_reproduction")
    status = _read_field(payload, "status", default=existing.status if existing else "draft")
    priority = _read_field(payload, "priority", default=existing.priority if existing else "P2")
    target_model = _read_field(payload, "target_model", "targetModel", existing.target_model if existing else None)
    next_action = _read_field(payload, "next_action", "nextAction", existing.next_action if existing else "")
    blockers = _read_field(payload, "blockers", default=existing.blockers if existing else [])
    merge_target = _read_field(payload, "merge_target", "mergeTarget", existing.merge_target if existing else None)
    metadata = _read_field(payload, "metadata", default=existing.metadata if existing else {})

    if not item_id:
        raise DevelopmentStoreError("id cannot be empty.")
    if not title or not str(title).strip():
        if partial and existing:
            title = existing.title
        else:
            raise DevelopmentStoreError("title is required.")

    item = DevelopmentItem(
        id=item_id,
        title=str(title).strip(),
        category=str(category),
        status=str(status),
        priority=str(priority),
        target_model=str(target_model).strip() if target_model else None,
        next_action=str(next_action).strip(),
        blockers=_normalize_blockers(blockers),
        merge_target=str(merge_target) if merge_target else None,
        created_at=existing.created_at if existing else str(_read_field(payload, "created_at", "createdAt", now)),
        updated_at=now if existing else str(_read_field(payload, "updated_at", "updatedAt", now)),
        metadata=_normalize_metadata(metadata),
    )
    _validate_item(item)
    return item


def _validate_item(item: DevelopmentItem) -> None:
    if item.category not in CATEGORIES:
        raise DevelopmentStoreError(f"Unsupported development category: {item.category}.")
    if item.status not in STATUSES:
        raise DevelopmentStoreError(f"Unsupported development status: {item.status}.")
    if item.priority not in PRIORITIES:
        raise DevelopmentStoreError(f"Unsupported development priority: {item.priority}.")
    if item.merge_target and item.merge_target not in MERGE_TARGETS:
        raise DevelopmentStoreError(f"Unsupported merge target: {item.merge_target}.")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp_path, path)


class DevelopmentStore:
    def __init__(self, manifest_path: Path = DEVELOPMENT_MANIFEST_PATH):
        self.manifest_path = manifest_path

    def list_items(self) -> list[DevelopmentItem]:
        with _DEVELOPMENT_STORE_LOCK:
            manifest = self._load_manifest()
            return [_normalize_item(item) for item in manifest["items"]]

    def create_item(self, payload: dict) -> DevelopmentItem:
        with _DEVELOPMENT_STORE_LOCK:
            manifest = self._load_manifest()
            item = _normalize_item(payload)
            if any(existing.get("id") == item.id for existing in manifest["items"]):
                raise DevelopmentStoreError(f"Development item already exists: {item.id}.")
            manifest["items"].append(item.to_dict())
            self._save_manifest(manifest)
            return item

    def update_item(self, item_id: str, payload: dict) -> DevelopmentItem:
        with _DEVELOPMENT_STORE_LOCK:
            manifest = self._load_manifest()
            index, existing = self._find_item(manifest, item_id)
            item = _normalize_item(payload, existing=existing, partial=True)
            manifest["items"][index] = item.to_dict()
            self._save_manifest(manifest)
            return item

    def delete_item(self, item_id: str) -> None:
        with _DEVELOPMENT_STORE_LOCK:
            manifest = self._load_manifest()
            index, _ = self._find_item(manifest, item_id)
            manifest["items"].pop(index)
            self._save_manifest(manifest)

    def get_item(self, item_id: str) -> DevelopmentItem:
        with _DEVELOPMENT_STORE_LOCK:
            _, item = self._find_item(self._load_manifest(), item_id)
            return item

    def _load_manifest(self) -> dict:
        if not self.manifest_path.exists():
            now = _now_iso()
            items = []
            for payload in DEFAULT_DEVELOPMENT_ITEMS:
                seed = dict(payload)
                seed["createdAt"] = now
                seed["updatedAt"] = now
                seed["metadata"] = {}
                items.append(_normalize_item(seed).to_dict())
            manifest = {"version": 1, "items": items}
            self._save_manifest(manifest)
            return manifest

        payload = _read_json(self.manifest_path)
        raw_items = payload if isinstance(payload, list) else payload.get("items", [])
        if not isinstance(raw_items, list):
            raise DevelopmentStoreError("development_manifest.json must contain an items list.")
        return {"version": int(payload.get("version", 1)) if isinstance(payload, dict) else 1, "items": raw_items}

    def _save_manifest(self, manifest: dict) -> None:
        normalized_items = [_normalize_item(item).to_dict() for item in manifest.get("items", [])]
        _atomic_write_json(self.manifest_path, {"version": 1, "items": normalized_items})

    def _find_item(self, manifest: dict, item_id: str) -> tuple[int, DevelopmentItem]:
        for index, payload in enumerate(manifest["items"]):
            item = _normalize_item(payload)
            if item.id == item_id:
                return index, item
        raise FileNotFoundError(f"Development item not found: {item_id}.")


def item_priority_score(priority: str) -> int:
    return {"P0": 100, "P1": 80, "P2": 60, "P3": 40}.get(priority, 50)
