"""
scene_meta.json 统一视图

不同 runner 写出的 ``scene_meta.json`` 字段并不一致：
- dust3r/mast3r：``{n_images, n_pairs, n_points, raw_point_count, params, ...}``（没有 ``model``）
- monst3r：``{model, artifacts: [...], artifact_groups, review_targets, ...}``（artifacts 是 list）
- align3r：``{model, artifacts: {...}, artifact_groups, primary_artifacts, ...}``（artifacts 是 dict）

本模块提供一个「读时归一化」器，把任意历史/新格式收敛成一个稳定的规范视图，
供前端对比/检视和合同校验统一消费，而不需要改动已经在跑的 runner 输出。
"""
from __future__ import annotations

from typing import Any

SCENE_META_SCHEMA_VERSION = 1


def _first_int(raw: dict[str, Any], *keys: str) -> int | None:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return int(value)
    return None


def _artifact_count(raw: dict[str, Any]) -> int | None:
    explicit = _first_int(raw, "artifact_count")
    if explicit is not None:
        return explicit
    artifacts = raw.get("artifacts")
    if isinstance(artifacts, list):
        return len(artifacts)
    if isinstance(artifacts, dict):
        # align3r stores {key: {"exists": bool}} — count the ones that exist.
        count = 0
        for value in artifacts.values():
            if isinstance(value, dict):
                if value.get("exists", True):
                    count += 1
            elif value:
                count += 1
        return count
    return None


def normalize_scene_meta(
    model: str,
    raw: dict[str, Any] | None,
    *,
    output_files: list[str] | None = None,
) -> dict[str, Any]:
    """Return a stable canonical view of a runner's scene_meta.json.

    Always populates ``model``, ``schema_version`` and the core numeric/listing
    fields, regardless of which runner produced the original file. The original
    document is preserved verbatim under ``fields``."""
    raw = raw if isinstance(raw, dict) else {}

    artifact_groups = raw.get("artifact_groups")
    if not isinstance(artifact_groups, list):
        artifact_groups = []

    primary_artifacts = raw.get("primary_artifacts")
    if not isinstance(primary_artifacts, list):
        primary_artifacts = raw.get("review_targets") if isinstance(raw.get("review_targets"), list) else []

    params = raw.get("params")
    if not isinstance(params, dict):
        params = {}

    return {
        "schema_version": SCENE_META_SCHEMA_VERSION,
        "model": raw.get("model") or model,
        "source_type": raw.get("source_type") or raw.get("input_mode"),
        "input_count": _first_int(raw, "input_count", "n_images"),
        "point_count": _first_int(raw, "n_points", "point_count", "raw_point_count"),
        "artifact_count": _artifact_count(raw),
        "artifact_groups": artifact_groups,
        "primary_artifacts": primary_artifacts,
        "params": params,
        "has_scene_meta": bool(raw),
        "output_file_count": len(output_files) if output_files is not None else None,
        "fields": raw,
    }
