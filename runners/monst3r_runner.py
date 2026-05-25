#!/usr/bin/env python3
"""
MonST3R server-side runner.

The local client uploads a normalized job folder, then this script runs the
official MonST3R demo in non-interactive mode and copies useful artifacts into
the standard job output directory.
"""
from __future__ import annotations

import argparse
import json
import os
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path


DEFAULT_WEIGHTS = "checkpoints/MonST3R_PO-TA-S-W_ViTLarge_BaseDecoder_512_dpt.pth"
REQUIRED_RELATIVE_PATHS = [
    DEFAULT_WEIGHTS,
    "third_party/RAFT/models/raft-things.pth",
    "third_party/RAFT/models/Tartan-C-T-TSKH-spring540x960-M.pth",
    "third_party/sam2/checkpoints/sam2.1_hiera_large.pt",
]
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
EXPORT_SUFFIXES = {
    ".glb",
    ".ply",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".webp",
    ".mp4",
    ".npy",
    ".json",
}


def write_status(job_dir: Path, phase: str, message: str, progress: str = "") -> None:
    payload = {
        "phase": phase,
        "message": message,
        "progress": progress,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (job_dir / "status.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def load_job(job_dir: Path) -> dict:
    job_json = job_dir / "job.json"
    if not job_json.exists():
        raise FileNotFoundError(f"缺少远端任务清单：{job_json}")
    return json.loads(job_json.read_text(encoding="utf-8-sig"))


def param_bool(params: dict, key: str, default: bool = False) -> bool:
    value = params.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def param_int(params: dict, key: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(params.get(key, default))
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)


def param_float(params: dict, key: str, default: float, *, minimum: float, maximum: float) -> float:
    try:
        value = float(params.get(key, default))
    except (TypeError, ValueError):
        value = default
    return min(max(value, minimum), maximum)


def check_remote_layout(repo: Path, weights: Path) -> list[str]:
    missing = []
    if not repo.exists():
        return [f"缺少 MonST3R 仓库目录：{repo}"]
    if not (repo / "demo.py").exists():
        missing.append(f"缺少官方 demo.py：{repo / 'demo.py'}")
    for rel_path in REQUIRED_RELATIVE_PATHS:
        candidate = repo / rel_path
        if rel_path == DEFAULT_WEIGHTS:
            candidate = weights
        if not candidate.exists():
            missing.append(f"缺少权重或依赖文件：{candidate}")
    return missing


def resolve_input_path(job_dir: Path, source_type: str) -> tuple[Path, list[Path], list[str]]:
    input_dir = job_dir / "input"
    input_files = sorted(path for path in input_dir.iterdir() if path.is_file())
    warnings: list[str] = []

    if not input_files:
        raise RuntimeError("没有发现已上传输入文件。")

    if source_type == "video":
        video_files = [path for path in input_files if path.suffix.lower() in VIDEO_SUFFIXES]
        if len(video_files) == 1:
            return video_files[0], input_files, warnings
        if len(input_files) == 1:
            warnings.append("输入类型是视频，但扩展名不在常见视频列表中；仍按单个视频文件传给 demo.py。")
            return input_files[0], input_files, warnings
        warnings.append("输入类型是视频，但上传了多个文件；已改按帧序列目录传给 demo.py。")

    image_like = [path for path in input_files if path.suffix.lower() in IMAGE_SUFFIXES]
    if not image_like:
        warnings.append("没有检测到常见图片扩展名；MonST3R 会按目录内容排序处理。")
    elif len(image_like) < len(input_files):
        warnings.append("输入目录中混有非图片文件；MonST3R 官方 demo 会按目录内容排序读取。")

    return input_dir, input_files, warnings


def build_demo_command(repo: Path, job_dir: Path, job: dict, weights: Path, input_path: Path) -> tuple[list[str], Path, str, dict]:
    params = job.get("params") or {}
    seq_name = str(job.get("job_id") or job_dir.name)
    demo_output_root = job_dir / "monst3r_demo"
    demo_output_root.mkdir(parents=True, exist_ok=True)

    image_size = param_int(params, "image_size", 512, minimum=224, maximum=512)
    if image_size not in {224, 512}:
        image_size = 512

    normalized = {
        "image_size": image_size,
        "batch_size": param_int(params, "batch_size", 1, minimum=1, maximum=16),
        "fps": param_int(params, "fps", 0, minimum=0, maximum=120),
        "num_frames": param_int(params, "num_frames", 24, minimum=1, maximum=2000),
        "not_batchify": param_bool(params, "not_batchify", True),
        "real_time": param_bool(params, "real_time", False),
        "window_wise": param_bool(params, "window_wise", False),
        "window_size": param_int(params, "window_size", 100, minimum=2, maximum=500),
        "window_overlap_ratio": param_float(params, "window_overlap_ratio", 0.5, minimum=0.0, maximum=0.95),
    }

    command = [
        sys.executable,
        str(repo / "demo.py"),
        "--input_dir",
        str(input_path),
        "--output_dir",
        str(demo_output_root),
        "--seq_name",
        seq_name,
        "--weights",
        str(weights),
        "--image_size",
        str(normalized["image_size"]),
        "--device",
        "cuda",
        "--batch_size",
        str(normalized["batch_size"]),
        "--fps",
        str(normalized["fps"]),
        "--num_frames",
        str(normalized["num_frames"]),
    ]

    if normalized["not_batchify"]:
        command.append("--not_batchify")
    if normalized["real_time"]:
        command.append("--real_time")
    if normalized["window_wise"]:
        command.extend(
            [
                "--window_wise",
                "--window_size",
                str(normalized["window_size"]),
                "--window_overlap_ratio",
                str(normalized["window_overlap_ratio"]),
            ]
        )

    return command, demo_output_root / seq_name, seq_name, normalized


def run_demo(command: list[str], repo: Path, job_dir: Path) -> None:
    write_status(job_dir, "running_matches", "正在启动 MonST3R 官方 demo，首次加载模型会比较慢...", "0/1")
    print("MonST3R command:", " ".join(command), flush=True)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["MPLBACKEND"] = "Agg"
    env["GRADIO_ANALYTICS_ENABLED"] = "False"

    process = subprocess.Popen(
        command,
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=env,
    )

    last_line = ""
    started_at = time.monotonic()
    last_heartbeat = 0.0
    assert process.stdout is not None

    while process.poll() is None:
        ready, _, _ = select.select([process.stdout], [], [], 5)
        if ready:
            raw_line = process.stdout.readline()
            if not raw_line:
                continue
            line = raw_line.rstrip()
            if not line:
                continue
            last_line = line[-500:]
            print(line, flush=True)
            status_line = classify_status_line(line)
            if status_line is not None:
                phase, message = status_line
                write_status(job_dir, phase, message)
            continue

        elapsed = int(time.monotonic() - started_at)
        if elapsed - last_heartbeat >= 15:
            last_heartbeat = float(elapsed)
            write_status(
                job_dir,
                "running_matches",
                f"MonST3R 正在加载模型/读取输入/推理中，已运行 {elapsed} 秒。首次运行几分钟内没有详细日志是正常的。",
            )

    for raw_line in process.stdout:
        line = raw_line.rstrip()
        if line:
            last_line = line[-500:]
            print(line, flush=True)
            status_line = classify_status_line(line)
            if status_line is not None:
                phase, message = status_line
                write_status(job_dir, phase, message)

    return_code = process.wait()
    if return_code != 0:
        write_status(job_dir, "failed", f"MonST3R demo.py 运行失败，返回码 {return_code}。最后日志：{last_line}")
        raise RuntimeError(f"MonST3R demo.py failed with exit code {return_code}: {last_line}")


def classify_status_line(line: str) -> tuple[str, str] | None:
    lower = line.lower()
    if "futurewarning" in lower or "torch.cuda.amp.autocast" in lower:
        return None
    if "processing completed" in lower:
        return ("saving_outputs", "MonST3R 推理完成，正在整理输出。")
    if "global alignment" in lower or "optim" in lower:
        return ("running_alignment", line[-400:])
    if "save" in lower or "output" in lower:
        return ("saving_outputs", line[-400:])
    if "loading" in lower or "loaded" in lower or "model" in lower:
        return ("running_matches", line[-400:])
    return ("running_matches", line[-400:])


def artifact_role(name: str, suffix: str) -> str:
    lower = name.lower()
    if lower.endswith(".glb") or lower.endswith(".gltf"):
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
    if suffix == ".npy":
        return "array"
    if suffix in IMAGE_SUFFIXES:
        return "image"
    return "other"


def summarize_artifacts(artifacts: list[dict]) -> dict:
    role_labels = {
        "scene": ("三维场景", "优先打开检查主体结构、相机轨迹和动态区域。"),
        "trajectory": ("相机轨迹", "用于判断相机运动是否连续、是否出现明显漂移。"),
        "intrinsics": ("相机内参", "用于复查焦距和相机参数是否成功导出。"),
        "frame_preview": ("彩色帧预览", "用于快速确认抽帧质量、曝光和运动模糊。"),
        "dynamic_mask": ("动态区域", "用于判断运动物体或动态区域是否被识别。"),
        "confidence": ("置信数组", "用于后续诊断深度/几何估计稳定性。"),
        "initial_confidence": ("初始置信数组", "MonST3R 中间置信产物。"),
        "geometry_array": ("几何数组", "每帧对应的几何/深度数组。"),
        "array": ("其他数组", "其他 NPY 中间产物。"),
        "image": ("其他图像", "其他可视化图像。"),
        "other": ("其他产物", "未归入主检查路径的产物。"),
    }
    counts: dict[str, int] = {}
    for item in artifacts:
        role = item.get("role") or "other"
        counts[role] = counts.get(role, 0) + 1

    groups = [
        {
            "key": key,
            "label": role_labels[key][0],
            "count": counts[key],
            "description": role_labels[key][1],
        }
        for key in role_labels
        if counts.get(key)
    ]

    def by_role(role: str) -> list[dict]:
        return [item for item in artifacts if item.get("role") == role]

    review_targets: list[dict] = []
    for role in ("scene", "trajectory", "intrinsics"):
        for item in by_role(role)[:1]:
            review_targets.append(
                {
                    "role": role,
                    "label": role_labels[role][0],
                    "name": item["name"],
                    "relative_path": item.get("output_relative_path", item.get("relative_source", item["name"])),
                    "note": role_labels[role][1],
                }
            )

    frame_previews = by_role("frame_preview")
    if len(frame_previews) > 3:
        selected_indexes = sorted({0, len(frame_previews) // 2, len(frame_previews) - 1})
        selected_frames = [frame_previews[index] for index in selected_indexes]
    else:
        selected_frames = frame_previews
    for item in selected_frames:
        review_targets.append(
            {
                "role": "frame_preview",
                "label": role_labels["frame_preview"][0],
                "name": item["name"],
                "relative_path": item.get("output_relative_path", item.get("relative_source", item["name"])),
                "note": role_labels["frame_preview"][1],
            }
        )

    return {
        "artifact_groups": groups,
        "review_targets": review_targets,
        "role_counts": counts,
        "frame_preview_count": counts.get("frame_preview", 0),
        "dynamic_mask_count": counts.get("dynamic_mask", 0),
        "confidence_count": counts.get("confidence", 0) + counts.get("initial_confidence", 0),
        "trajectory_count": counts.get("trajectory", 0),
        "intrinsics_count": counts.get("intrinsics", 0),
        "geometry_array_count": counts.get("geometry_array", 0),
    }


def copy_artifacts(demo_seq_dir: Path, output_dir: Path) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    copied: list[dict] = []
    if not demo_seq_dir.exists():
        raise RuntimeError(f"MonST3R 没有生成预期输出目录：{demo_seq_dir}")

    for source in sorted(path for path in demo_seq_dir.rglob("*") if path.is_file()):
        if source.suffix.lower() not in EXPORT_SUFFIXES:
            continue
        relative_source = source.relative_to(demo_seq_dir)
        target = output_dir / relative_source
        suffix = source.suffix.lower()
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(
            {
                "name": source.name,
                "relative_source": str(relative_source),
                "output_relative_path": str(Path("output") / relative_source),
                "size_bytes": target.stat().st_size,
                "suffix": suffix,
                "role": artifact_role(source.name, suffix),
            }
        )

    if not copied:
        raise RuntimeError(f"MonST3R 输出目录存在，但没有发现可回传产物：{demo_seq_dir}")
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MonST3R for a KYKT remote job")
    parser.add_argument("--job-dir", required=True, help="Path to the remote job directory")
    parser.add_argument("--repo", required=True, help="Remote MonST3R repo path")
    parser.add_argument("--weights", default=None, help="Optional explicit MonST3R checkpoint path")
    args = parser.parse_args()

    job_dir = Path(args.job_dir).resolve()
    repo = Path(args.repo).resolve()
    output_dir = job_dir / "output"
    logs_dir = job_dir / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    try:
        job = load_job(job_dir)
        source_type = str(job.get("source_type") or "frames")
        weights = Path(args.weights).resolve() if args.weights else repo / DEFAULT_WEIGHTS

        write_status(job_dir, "starting", "正在检查 MonST3R 仓库、依赖和权重...")
        missing = check_remote_layout(repo, weights)
        if missing:
            raise RuntimeError("\n".join(missing))

        input_path, input_files, warnings = resolve_input_path(job_dir, source_type)
        command, demo_seq_dir, seq_name, normalized_params = build_demo_command(repo, job_dir, job, weights, input_path)
        (logs_dir / "monst3r_command.json").write_text(
            json.dumps(
                {
                    "command": command,
                    "repo": str(repo),
                    "input_path": str(input_path),
                    "demo_output_dir": str(demo_seq_dir),
                    "warnings": warnings,
                    "params": normalized_params,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        run_demo(command, repo, job_dir)

        write_status(job_dir, "saving_outputs", "MonST3R 已完成推理，正在整理输出文件...")
        artifacts = copy_artifacts(demo_seq_dir, output_dir)
        artifact_summary = summarize_artifacts(artifacts)
        scene_meta = {
            "model": "monst3r",
            "seq_name": seq_name,
            "source_type": source_type,
            "input_count": len(input_files),
            "input_path": str(input_path),
            "weights": str(weights),
            "demo_output_dir": str(demo_seq_dir),
            "params": normalized_params,
            "warnings": warnings,
            "artifacts": artifacts,
            "artifact_count": len(artifacts),
            "glb_count": sum(1 for item in artifacts if item["suffix"] == ".glb"),
            "image_count": sum(1 for item in artifacts if item["suffix"] in IMAGE_SUFFIXES),
            "npy_count": sum(1 for item in artifacts if item["suffix"] == ".npy"),
            **artifact_summary,
        }
        (output_dir / "scene_meta.json").write_text(
            json.dumps(scene_meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        write_status(job_dir, "finished", f"MonST3R 完成，已整理 {len(artifacts)} 个输出产物。")
        print(f"MonST3R finished. Exported {len(artifacts)} artifacts to {output_dir}", flush=True)
    except Exception as exc:
        write_status(job_dir, "failed", str(exc))
        print(str(exc), file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
