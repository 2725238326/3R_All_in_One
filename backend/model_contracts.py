from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from model_registry import MODEL_OPTIONS, SOURCE_TYPE_OPTIONS, get_model_catalog_options, get_model_spec, param_family_for


@dataclass(frozen=True)
class RunnerSpec:
    model: str
    runner_file: str | None
    dispatch_key: str | None
    download_mode: str
    required_files: tuple[str, ...] = ()
    optional_files: tuple[str, ...] = ()


def _parse_bool(value: str | bool | None, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _int_param(payload: dict[str, Any], key: str, default: int, minimum: int, maximum: int) -> int:
    raw = payload.get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)


def _float_param(payload: dict[str, Any], key: str, default: float, minimum: float, maximum: float | None = None) -> float:
    raw = payload.get(key, default)
    try:
        value = float(raw)
    except (TypeError, ValueError):
        value = default
    value = max(value, minimum)
    if maximum is not None:
        value = min(value, maximum)
    return value


def _choice_param(payload: dict[str, Any], key: str, default: int, choices: set[int]) -> int:
    try:
        value = int(payload.get(key, default))
    except (TypeError, ValueError):
        value = default
    return value if value in choices else default


def _field(
    key: str,
    label: str,
    kind: str,
    default: Any,
    *,
    minimum: int | float | None = None,
    maximum: int | float | None = None,
    choices: list[dict[str, Any]] | None = None,
    help_text: str = "",
) -> dict:
    payload = {
        "key": key,
        "label": label,
        "type": kind,
        "default": default,
        "helpText": help_text,
    }
    if minimum is not None:
        payload["min"] = minimum
    if maximum is not None:
        payload["max"] = maximum
    if choices is not None:
        payload["choices"] = choices
    return payload


PARAM_SCHEMAS: dict[str, dict] = {
    "image_collection": {
        "key": "image_collection",
        "label": "静态图片重建参数",
        "fields": [
            _field("image_size", "Image Size", "select", 512, choices=[{"value": 224, "label": "224"}, {"value": 384, "label": "384"}, {"value": 512, "label": "512"}]),
            _field("scene_graph", "Scene Graph", "select", "complete", choices=[{"value": "complete", "label": "complete"}, {"value": "swin-5", "label": "swin-5"}]),
            _field("niter", "Iterations", "number", 300, minimum=0, maximum=1000),
            _field("lr", "Learning Rate", "number", 0.01, minimum=0),
            _field("batch_size", "Batch Size", "number", 1, minimum=1, maximum=8),
            _field("max_points", "Max Points", "number", 250000, minimum=1000, maximum=2_000_000),
            _field("match_viz_count", "Match Viz Count", "number", 50, minimum=0, maximum=500),
        ],
    },
    "video_sequence": {
        "key": "video_sequence",
        "label": "视频/帧序列参数",
        "fields": [
            _field("image_size", "Image Size", "select", 512, choices=[{"value": 224, "label": "224"}, {"value": 512, "label": "512"}]),
            _field("batch_size", "Batch Size", "number", 1, minimum=1, maximum=16),
            _field("fps", "FPS", "number", 0, minimum=0, maximum=120),
            _field("num_frames", "Num Frames", "number", 48, minimum=1, maximum=2000),
            _field("not_batchify", "Not Batchify", "boolean", True),
            _field("real_time", "Real Time", "boolean", False),
            _field("window_wise", "Window Wise", "boolean", False),
            _field("window_size", "Window Size", "number", 100, minimum=2, maximum=500),
            _field("window_overlap_ratio", "Window Overlap", "number", 0.5, minimum=0, maximum=0.95),
        ],
    },
    "spann3r_sequence": {
        "key": "spann3r_sequence",
        "label": "Spann3R 参数",
        "fields": [
            _field("resolution", "Resolution", "select", 224, choices=[{"value": 224, "label": "224"}]),
            _field("kf_every", "Keyframe Every", "number", 10, minimum=1, maximum=200),
            _field("conf_thresh", "Confidence Threshold", "number", 0.001, minimum=0, maximum=1),
            _field("save_ori", "Save Original", "boolean", True),
            _field("offline", "Offline", "boolean", False),
        ],
    },
    "fast3r_collection": {
        "key": "fast3r_collection",
        "label": "Fast3R 参数",
        "fields": [
            _field("image_size", "Image Size", "select", 512, choices=[{"value": 224, "label": "224"}, {"value": 512, "label": "512"}]),
            _field("max_points", "Max Points", "number", 250000, minimum=1000, maximum=2_000_000),
            _field("attention_backend", "Attention Backend", "select", "pytorch_naive", choices=[{"value": "pytorch_naive", "label": "pytorch_naive"}]),
            _field("pose_iterations", "Pose Iterations", "number", 100, minimum=0, maximum=1000),
            _field("focal_estimation_method", "Focal Estimation", "select", "first_view_from_global_head", choices=[{"value": "first_view_from_global_head", "label": "first_view_from_global_head"}]),
        ],
    },
    "streaming_sequence": {
        "key": "streaming_sequence",
        "label": "流式序列参数",
        "fields": [],
    },
    "research_catalog": {
        "key": "research_catalog",
        "label": "预研目录模型",
        "fields": [],
    },
}


RESULT_CONTRACTS: dict[str, dict] = {
    "static_pointcloud": {
        "key": "static_pointcloud",
        "downloadMode": "required_files",
        "requiredFiles": ["output/matches.png", "output/pointcloud.ply"],
        "optionalFiles": ["logs/runner.log", "output/scene_meta.json"],
        "primaryRoles": ["pointcloud", "matches"],
        "artifactRoles": {
            "pointcloud": {"label": "点云结果", "description": "优先在 MeshLab 中检查结构完整性和噪声。"},
            "matches": {"label": "匹配可视化", "description": "用于快速判断图像重叠和匹配质量。"},
            "metadata": {"label": "运行元数据", "description": "scene_meta.json 和参数记录。"},
        },
    },
    "monst3r_scene": {
        "key": "monst3r_scene",
        "downloadMode": "remote_tree_bundle",
        "requiredFiles": ["output/scene_meta.json"],
        "optionalFiles": [],
        "primaryRoles": ["scene", "trajectory", "intrinsics", "frame_preview"],
        "artifactRoles": {
            "scene": {"label": "三维场景", "description": "优先打开检查主体结构、相机轨迹和动态区域。"},
            "trajectory": {"label": "相机轨迹", "description": "用于判断相机运动是否连续、是否漂移。"},
            "intrinsics": {"label": "相机内参", "description": "用于复查焦距和相机参数。"},
            "frame_preview": {"label": "彩色帧预览", "description": "用于确认抽帧质量、曝光和运动模糊。"},
            "dynamic_mask": {"label": "动态区域", "description": "用于判断运动物体区域识别。"},
            "confidence": {"label": "置信数组", "description": "用于诊断深度/几何估计稳定性。"},
            "initial_confidence": {"label": "初始置信数组", "description": "用于对比初始估计和优化后的置信变化。"},
            "geometry_array": {"label": "几何数组", "description": "逐帧几何中间结果。"},
            "array": {"label": "其他数组", "description": "其他 NPY 中间产物。"},
            "image": {"label": "其他图像", "description": "未归入帧预览或动态区域的图像产物。"},
            "log": {"label": "运行日志", "description": "runner.log 和远端执行日志。"},
            "metadata": {"label": "运行元数据", "description": "scene_meta.json、summary 和其他结构化记录。"},
            "other": {"label": "其他产物", "description": "未归入主检查路径的产物。"},
        },
    },
    "spann3r_pointmap": {
        "key": "spann3r_pointmap",
        "downloadMode": "remote_tree_bundle",
        "requiredFiles": ["output/scene_meta.json"],
        "optionalFiles": [],
        "primaryRoles": ["pointcloud", "transform", "array"],
        "artifactRoles": {
            "pointcloud": {"label": "点云结果", "description": "优先检查全局结构与噪声。"},
            "transform": {"label": "相机与变换", "description": "用于复查相机轨迹与导出兼容性。"},
            "array": {"label": "几何数组", "description": "用于诊断 pointmap 与置信过滤效果。"},
            "metadata": {"label": "运行元数据", "description": "scene_meta.json、transforms 和参数记录。"},
            "log": {"label": "运行日志", "description": "runner.log 和远端执行日志。"},
            "other": {"label": "其他产物", "description": "未归入主检查路径的产物。"},
        },
    },
    "fast3r_pointcloud": {
        "key": "fast3r_pointcloud",
        "downloadMode": "remote_tree_bundle",
        "requiredFiles": ["output/scene_meta.json"],
        "optionalFiles": [],
        "primaryRoles": ["pointcloud", "camera", "confidence", "metadata"],
        "artifactRoles": {
            "pointcloud": {"label": "点云结果", "description": "优先检查结构完整性和稠密程度。"},
            "camera": {"label": "相机信息", "description": "用于复查位姿和焦距估计。"},
            "confidence": {"label": "置信摘要", "description": "用于诊断低置信区域。"},
            "metadata": {"label": "运行元数据", "description": "用于复查 attention backend、profiling 与输入列表。"},
            "log": {"label": "运行日志", "description": "runner.log 和远端执行日志。"},
            "other": {"label": "其他产物", "description": "未归入主检查路径的产物。"},
        },
    },
    "align3r_depth": {
        "key": "align3r_depth",
        "downloadMode": "remote_tree_bundle",
        "requiredFiles": ["output/scene_meta.json"],
        "optionalFiles": [],
        "primaryRoles": ["pointcloud", "depth", "camera"],
        "artifactRoles": {
            "pointcloud": {"label": "点云结果", "description": "全局点云或动态点云，优先检查结构。"},
            "depth": {"label": "深度图", "description": "逐帧深度估计，检查深度连续性与一致性。"},
            "camera": {"label": "相机位姿", "description": "相机外参与轨迹。"},
            "scene": {"label": "三维场景", "description": "GLB 格式场景文件。"},
            "array": {"label": "几何数组", "description": "NPY 中间产物。"},
            "log": {"label": "运行日志", "description": "runner.log 和远端执行日志。"},
            "other": {"label": "其他产物", "description": "未归入主检查路径的产物。"},
        },
    },
    "cut3r_streaming": {
        "key": "cut3r_streaming",
        "downloadMode": "remote_tree_bundle",
        "requiredFiles": ["output/scene_meta.json"],
        "optionalFiles": [],
        "primaryRoles": ["pointcloud", "camera", "depth"],
        "artifactRoles": {
            "pointcloud": {"label": "点云结果", "description": "在线重建全局点云，检查结构完整性与噪声。"},
            "scene": {"label": "三维场景", "description": "GLB 格式场景文件。"},
            "camera": {"label": "相机参数", "description": "相机位姿与内参。"},
            "depth": {"label": "深度图", "description": "逐帧深度图，检查在线估计的时序稳定性。"},
            "confidence": {"label": "置信图", "description": "置信分布可视化。"},
            "array": {"label": "几何数组", "description": "pointmap 等 NPY 中间产物。"},
            "log": {"label": "运行日志", "description": "runner.log 和远端执行日志。"},
            "other": {"label": "其他产物", "description": "未归入主检查路径的产物。"},
        },
    },
    "research_catalog": {
        "key": "research_catalog",
        "downloadMode": "not_runnable",
        "requiredFiles": [],
        "optionalFiles": [],
        "primaryRoles": [],
        "artifactRoles": {},
    },
}


MODEL_RESULT_CONTRACT_KEYS = {
    "dust3r": "static_pointcloud",
    "mast3r": "static_pointcloud",
    "monst3r": "monst3r_scene",
    "spann3r": "spann3r_pointmap",
    "fast3r": "fast3r_pointcloud",
    "align3r": "align3r_depth",
    "cut3r": "cut3r_streaming",
}


def default_params_for_family(param_family: str) -> dict[str, Any]:
    return {field["key"]: field["default"] for field in PARAM_SCHEMAS.get(param_family, PARAM_SCHEMAS["research_catalog"])["fields"]}


def build_job_params(model: str, raw_params: dict[str, Any] | None = None) -> dict:
    raw_params = raw_params or {}
    family = param_family_for(model)
    if family == "image_collection":
        return {
            "image_size": _int_param(raw_params, "image_size", 512, 224, 1024),
            "scene_graph": str(raw_params.get("scene_graph") or "complete").strip() or "complete",
            "niter": _int_param(raw_params, "niter", 300, 0, 1000),
            "lr": _float_param(raw_params, "lr", 0.01, 0.0),
            "batch_size": _int_param(raw_params, "batch_size", 1, 1, 8),
            "max_points": _int_param(raw_params, "max_points", 250000, 1000, 2_000_000),
            "match_viz_count": _int_param(raw_params, "match_viz_count", 50, 0, 500),
        }
    if family == "video_sequence":
        return {
            "image_size": _choice_param(raw_params, "image_size", 512, {224, 512}),
            "batch_size": _int_param(raw_params, "batch_size", 1, 1, 16),
            "fps": _int_param(raw_params, "fps", 0, 0, 120),
            "num_frames": _int_param(raw_params, "num_frames", 48, 1, 2000),
            "not_batchify": _parse_bool(raw_params.get("not_batchify"), True),
            "real_time": _parse_bool(raw_params.get("real_time"), False),
            "window_wise": _parse_bool(raw_params.get("window_wise"), False),
            "window_size": _int_param(raw_params, "window_size", 100, 2, 500),
            "window_overlap_ratio": _float_param(raw_params, "window_overlap_ratio", 0.5, 0.0, 0.95),
        }
    if family == "spann3r_sequence":
        return {
            "resolution": 224,
            "kf_every": _int_param(raw_params, "kf_every", 10, 1, 200),
            "conf_thresh": _float_param(raw_params, "conf_thresh", 0.001, 0.0, 1.0),
            "save_ori": _parse_bool(raw_params.get("save_ori"), True),
            "offline": _parse_bool(raw_params.get("offline"), False),
        }
    if family == "fast3r_collection":
        return {
            "image_size": _choice_param(raw_params, "image_size", 512, {224, 512}),
            "max_points": _int_param(raw_params, "max_points", 250000, 1000, 2_000_000),
            "attention_backend": str(raw_params.get("attention_backend") or "pytorch_naive"),
            "pose_iterations": _int_param(raw_params, "pose_iterations", 100, 0, 1000),
            "focal_estimation_method": str(raw_params.get("focal_estimation_method") or "first_view_from_global_head"),
        }
    if family == "streaming_sequence":
        return {
            "size": _choice_param(raw_params, "size", 512, {224, 512}),
            "vis_threshold": _float_param(raw_params, "vis_threshold", 1.5, 0.0, 10.0),
            "max_frames": _int_param(raw_params, "max_frames", 48, 1, 2000),
        }
    return {}


def minimum_input_count(model: str, source_type: str) -> int:
    family = param_family_for(model)
    if family in ("video_sequence", "streaming_sequence") and source_type == "video":
        return 1
    return 2


def validate_create_request(model: str, source_type: str, file_count: int) -> list[str]:
    model_values = {item["value"] for item in MODEL_OPTIONS}
    source_values = {item["value"] for item in SOURCE_TYPE_OPTIONS}
    errors: list[str] = []
    if model not in model_values:
        catalog_entry = next((item for item in get_model_catalog_options() if item["value"] == model), None)
        if catalog_entry:
            blocker = catalog_entry.get("launch_blocker") or "该模型还没有接入可派发 runner。"
            errors.append(f"{catalog_entry['label']} 当前是目录模型，暂不可创建：{blocker}")
        else:
            errors.append(f"不支持的模型：{model}")
        return errors
    if source_type not in source_values:
        errors.append(f"不支持的输入类型：{source_type}")
        return errors
    allowed = set(get_model_spec(model).source_types)
    if source_type not in allowed:
        allowed_label = " / ".join(get_model_spec(model).source_types)
        errors.append(f"{get_model_spec(model).label} 仅支持这些输入类型：{allowed_label}")
    if file_count <= 0:
        errors.append("没有上传输入文件。")
    if source_type == "video" and file_count != 1:
        errors.append(f"{get_model_spec(model).label} 视频模式请上传 1 个视频文件；多张图片请改选“帧序列”。")
    minimum = minimum_input_count(model, source_type)
    if file_count < minimum:
        unit = "个视频文件" if source_type == "video" else "张图片或帧"
        errors.append(f"{get_model_spec(model).label} 至少需要 {minimum} {unit}。")
    return errors


def runner_spec_for(model: str) -> RunnerSpec:
    try:
        spec = get_model_spec(model)
    except KeyError:
        return RunnerSpec(model=model, runner_file=None, dispatch_key=None, download_mode="not_runnable")
    contract = result_contract_for(model)
    return RunnerSpec(
        model=model,
        runner_file=spec.default_runner,
        dispatch_key=model,
        download_mode=contract["downloadMode"],
        required_files=tuple(contract.get("requiredFiles") or ()),
        optional_files=tuple(contract.get("optionalFiles") or ()),
    )


def result_contract_for(model: str) -> dict:
    key = MODEL_RESULT_CONTRACT_KEYS.get(model, "research_catalog")
    return RESULT_CONTRACTS[key]


def model_contract_for(model: str) -> dict:
    catalog_entry = next((item for item in get_model_catalog_options() if item["value"] == model), None)
    if not catalog_entry:
        raise KeyError(f"未知模型：{model}")
    family = str(catalog_entry.get("param_family") or "research_catalog")
    param_schema = PARAM_SCHEMAS.get(family, PARAM_SCHEMAS["research_catalog"])
    runnable = bool(catalog_entry.get("runnable"))
    runner = runner_spec_for(model)
    return {
        "model": model,
        "label": catalog_entry.get("label") or model,
        "description": catalog_entry.get("description") or "",
        "family": catalog_entry.get("family") or "research_catalog",
        "paramFamily": family,
        "sourceTypes": catalog_entry.get("source_types") or [],
        "runnable": runnable,
        "runnerStatus": catalog_entry.get("runner_status") or "unknown",
        "launchBlocker": catalog_entry.get("launch_blocker"),
        "researchPriority": catalog_entry.get("research_priority") or 0,
        "activeTrack": bool(catalog_entry.get("active_track", True)),
        "paramSchema": param_schema,
        "defaultParams": default_params_for_family(family) if runnable else {},
        "minimumInputs": {
            source_type: minimum_input_count(model, source_type) if runnable else None
            for source_type in catalog_entry.get("source_types") or []
        },
        "runner": {
            "model": runner.model,
            "runnerFile": runner.runner_file,
            "dispatchKey": runner.dispatch_key,
            "downloadMode": runner.download_mode,
            "requiredFiles": list(runner.required_files),
            "optionalFiles": list(runner.optional_files),
        },
        "resultContract": result_contract_for(model),
    }


def all_model_contracts() -> list[dict]:
    return [model_contract_for(item["value"]) for item in get_model_catalog_options()]


def artifact_index_for(model: str, output_files: list[str]) -> dict:
    contract = result_contract_for(model)
    roles = contract.get("artifactRoles") or {}
    primary_roles = list(contract.get("primaryRoles") or [])
    artifacts = [artifact_record_for(model, rel_path) for rel_path in output_files]
    counts: dict[str, int] = {}
    for artifact in artifacts:
        counts[artifact["role"]] = counts.get(artifact["role"], 0) + 1

    groups = []
    for role, count in sorted(counts.items(), key=lambda item: (_role_order(primary_roles, item[0]), item[0])):
        role_meta = roles.get(role) or roles.get("other") or {}
        group_artifacts = [a for a in artifacts if a["role"] == role]
        groups.append(
            {
                "key": role,
                "label": role_meta.get("label") or role.replace("_", " "),
                "count": count,
                "description": role_meta.get("description") or "",
                "artifacts": group_artifacts,
            }
        )

    primary_artifacts = []
    for role in primary_roles:
        primary_artifacts.extend([artifact for artifact in artifacts if artifact["role"] == role][:1])

    return {
        "model": model,
        "contractKey": contract.get("key"),
        "primaryRole": primary_roles[0] if primary_roles else None,
        "groups": groups,
        "artifacts": artifacts,
        "primaryArtifacts": primary_artifacts,
        "artifact_groups": groups,
        "primary_artifacts": [
            {
                "role": item["role"],
                "label": item["label"],
                "name": item["name"],
                "relative_path": item["relativePath"],
                "note": item.get("description") or "",
            }
            for item in primary_artifacts
        ],
    }


def artifact_record_for(model: str, relative_path: str) -> dict:
    role = artifact_role_for(model, relative_path)
    role_meta = (result_contract_for(model).get("artifactRoles") or {}).get(role) or {}
    name = Path(relative_path).name
    kind = artifact_kind_for(relative_path)
    return {
        "role": role,
        "label": role_meta.get("label") or role.replace("_", " "),
        "description": role_meta.get("description") or "",
        "name": name,
        "relativePath": relative_path,
        "relative_path": relative_path,
        "kind": kind,
        "url": "/" + relative_path.replace("\\", "/"),
    }


def artifact_role_for(model: str, relative_path: str) -> str:
    name = Path(relative_path).name
    lower = name.lower()
    suffix = Path(lower).suffix
    normalized_path = relative_path.replace("\\", "/").lower()

    if suffix == ".log" or "/logs/" in normalized_path:
        return "log"
    if lower in {"scene_meta.json", "metadata.json", "result_summary.json"}:
        return "metadata"

    if model in {"dust3r", "mast3r"}:
        if lower == "matches.png":
            return "matches"
        if suffix == ".ply":
            return "pointcloud"
        return _generic_artifact_role(lower, suffix)

    if model == "monst3r":
        if suffix in {".glb", ".gltf"}:
            return "scene"
        if lower == "pred_traj.txt" or "traj" in lower:
            return "trajectory"
        if lower == "pred_intrinsics.txt" or "intrinsics" in lower:
            return "intrinsics"
        if lower.startswith("frame_") and suffix in IMAGE_SUFFIXES:
            return "frame_preview"
        if "dynamic_mask" in lower and suffix in IMAGE_SUFFIXES:
            return "dynamic_mask"
        if lower.startswith("conf_") and suffix == ".npy":
            return "confidence"
        if lower.startswith("init_conf_") and suffix == ".npy":
            return "initial_confidence"
        if lower.startswith("frame_") and suffix == ".npy":
            return "geometry_array"
        return _generic_artifact_role(lower, suffix)

    if model == "spann3r":
        if suffix == ".ply":
            return "pointcloud"
        if "transform" in lower or "pose" in lower or "camera" in lower:
            return "transform"
        if suffix == ".npy":
            return "array"
        return _generic_artifact_role(lower, suffix)

    if model == "fast3r":
        if suffix == ".ply":
            return "pointcloud"
        if "camera" in lower or "pose" in lower or "intrinsics" in lower:
            return "camera"
        if "confidence" in lower or "conf" in lower:
            return "confidence"
        return _generic_artifact_role(lower, suffix)

    return _generic_artifact_role(lower, suffix)


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
POINTCLOUD_SUFFIXES = {".ply", ".pcd", ".xyz"}
MODEL3D_SUFFIXES = {".glb", ".gltf", ".obj"}
DATA_SUFFIXES = {".json", ".npy", ".npz", ".txt", ".csv", ".tsv", ".yaml", ".yml"}


def artifact_kind_for(relative_path: str) -> str:
    suffix = Path(relative_path).suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix in VIDEO_SUFFIXES:
        return "video"
    if suffix in POINTCLOUD_SUFFIXES:
        return "pointcloud"
    if suffix in MODEL3D_SUFFIXES:
        return "model3d"
    if suffix == ".log":
        return "log"
    return "data" if suffix in DATA_SUFFIXES else "other"


def _generic_artifact_role(lower_name: str, suffix: str) -> str:
    if suffix in POINTCLOUD_SUFFIXES:
        return "pointcloud"
    if suffix in MODEL3D_SUFFIXES:
        return "scene"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    if suffix == ".npy":
        return "array"
    if suffix in {".json", ".yaml", ".yml"}:
        return "metadata"
    if suffix == ".log":
        return "log"
    return "other"


def _role_order(primary_roles: list[str], role: str) -> int:
    try:
        return primary_roles.index(role)
    except ValueError:
        return len(primary_roles) + 1


def check_output_contract(
    model: str,
    output_files: list[str],
    scene_meta: dict | None = None,
) -> dict:
    """Validate a finished job's downloaded outputs against the model's result
    contract.

    ``output_files`` are relative-to-data-root paths (as stored on the job
    record); required files are matched by path suffix so the check works
    regardless of the job-id prefix. Returns a structured report; ``ok`` is True
    only when every required file is present."""
    contract = result_contract_for(model)
    required = list(contract.get("requiredFiles") or ())
    optional = list(contract.get("optionalFiles") or ())
    present = [str(path).replace("\\", "/") for path in (output_files or [])]

    def _has(target: str) -> bool:
        normalized = target.replace("\\", "/")
        return any(path == normalized or path.endswith("/" + normalized) for path in present)

    satisfied = [req for req in required if _has(req)]
    missing = [req for req in required if not _has(req)]
    optional_present = [opt for opt in optional if _has(opt)]
    scene_meta_present = _has("output/scene_meta.json") or bool(scene_meta)

    return {
        "model": model,
        "ok": not missing,
        "download_mode": contract.get("downloadMode"),
        "required_files": required,
        "satisfied_files": satisfied,
        "missing_files": missing,
        "optional_present": optional_present,
        "scene_meta_present": scene_meta_present,
        "output_file_count": len(present),
    }
