#!/usr/bin/env python3
"""
Align3R server-side job runner.

Runs the official Align3R demo in non-interactive mode, collects depth maps,
dynamic point clouds, and camera poses into the standard job output directory.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".avi", ".mkv", ".webm"}


def write_status(job_dir: Path, phase: str, message: str, progress: str = "") -> None:
    payload = {
        "phase": phase,
        "message": message,
        "progress": progress,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (job_dir / "status.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def find_images(input_dir: Path) -> list[Path]:
    return sorted(p for p in input_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES)


def find_video(input_dir: Path) -> Path | None:
    for p in sorted(input_dir.iterdir()):
        if p.is_file() and p.suffix.lower() in VIDEO_SUFFIXES:
            return p
    return None


def extract_frames(video_path: Path, output_dir: Path, max_frames: int = 48) -> list[Path]:
    """Extract frames from video using ffmpeg."""
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(output_dir / "frame_%05d.png")
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", f"select=not(mod(n\\,1))",
        "-vsync", "vfr",
        "-frames:v", str(max_frames),
        pattern,
        "-y", "-loglevel", "warning",
    ]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    return sorted(output_dir.glob("frame_*.png"))


def copy_if_exists(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def collect_outputs(workspace: Path, output_dir: Path) -> dict[str, bool]:
    """Collect outputs from Align3R workspace into standard output dir."""
    copied = {}

    # Depth maps
    depth_files = sorted(workspace.glob("depth_*.png")) + sorted(workspace.glob("**/depth_*.png"))
    for i, df in enumerate(depth_files[:100]):
        ok = copy_if_exists(df, output_dir / df.name)
        copied[f"depth_{i}"] = ok

    # Point clouds
    for ply in workspace.glob("**/*.ply"):
        ok = copy_if_exists(ply, output_dir / "pointcloud.ply")
        copied["pointcloud"] = ok
        break

    # Camera poses
    for poses_file in workspace.glob("**/poses*.txt"):
        ok = copy_if_exists(poses_file, output_dir / "camera_poses.txt")
        copied["camera_poses"] = ok
        break
    for poses_file in workspace.glob("**/poses*.json"):
        ok = copy_if_exists(poses_file, output_dir / "camera_poses.json")
        copied["camera_poses_json"] = ok
        break

    # GLB / other 3D files
    for glb in workspace.glob("**/*.glb"):
        ok = copy_if_exists(glb, output_dir / "scene.glb")
        copied["scene"] = ok
        break

    # Confidence / other npy
    for npy in workspace.glob("**/*.npy"):
        ok = copy_if_exists(npy, output_dir / npy.name)
        copied[f"array_{npy.stem}"] = ok

    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description="Align3R server-side job runner")
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--max-frames", type=int, default=48)
    args = parser.parse_args()

    job_dir = Path(args.job_dir)
    repo = Path(args.repo)
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    logs_dir = job_dir / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Determine input mode: video or images
    video = find_video(input_dir)
    if video:
        print(f"[align3r_runner] 检测到视频输入: {video.name}")
        frames_dir = job_dir / "align3r_frames"
        frames = extract_frames(video, frames_dir, max_frames=args.max_frames)
        input_path = str(frames_dir)
        n_inputs = len(frames)
        input_mode = "video"
    else:
        images = find_images(input_dir)
        if len(images) < 2:
            write_status(job_dir, "failed", "Align3R 至少需要 2 张图片或 1 个视频文件。")
            print("[align3r_runner] 错误：至少需要 2 张图片或 1 个视频。", file=sys.stderr)
            sys.exit(1)
        input_path = str(input_dir)
        n_inputs = len(images)
        input_mode = "images"

    workspace = job_dir / "align3r_workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    # Build the Align3R demo command
    # Align3R official demo.sh uses: python demo.py with various flags
    # We call the demo script directly for non-interactive execution
    command = [
        sys.executable,
        str(repo / "demo.py"),
        "--img_path", input_path,
        "--output_path", str(workspace),
    ]

    write_status(job_dir, "starting", f"正在启动 Align3R，{input_mode} 输入，帧数：{n_inputs}。")
    write_status(job_dir, "running_matches", "正在运行 Align3R 深度估计与对齐...", f"0/{n_inputs}")
    print(f"[align3r_runner] 命令: {' '.join(command)}", flush=True)

    env = dict(**os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["MPLBACKEND"] = "Agg"

    completed = subprocess.run(
        command,
        cwd=str(repo),
        env=env,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr)

    # Save logs regardless of exit code
    (logs_dir / "runner_stdout.log").write_text(completed.stdout or "", encoding="utf-8")
    (logs_dir / "runner_stderr.log").write_text(completed.stderr or "", encoding="utf-8")

    if completed.returncode != 0:
        write_status(job_dir, "failed", f"Align3R demo.py 运行失败，返回码 {completed.returncode}。")
        raise SystemExit(completed.returncode)

    write_status(job_dir, "saving_outputs", "Align3R 推理完成，正在整理输出。")

    copied = collect_outputs(workspace, output_dir)
    n_artifacts = sum(1 for v in copied.values() if v)
    depth_count = sum(1 for k, v in copied.items() if k.startswith("depth_") and v)

    scene_meta = {
        "model": "align3r",
        "model_family": "video_depth_consistency",
        "input_mode": input_mode,
        "input_count": n_inputs,
        "artifact_count": n_artifacts,
        "artifacts": {k: {"exists": v} for k, v in copied.items()},
        "params": {
            "max_frames": args.max_frames,
        },
        "artifact_groups": [
            {"key": "depth", "label": "深度图", "count": depth_count, "description": "逐帧深度估计结果，检查深度连续性与一致性。"},
            {"key": "pointcloud", "label": "点云结果", "count": 1 if copied.get("pointcloud") else 0, "description": "全局点云或动态点云。"},
            {"key": "camera", "label": "相机位姿", "count": 1 if copied.get("camera_poses") or copied.get("camera_poses_json") else 0, "description": "相机外参与轨迹。"},
            {"key": "scene", "label": "三维场景", "count": 1 if copied.get("scene") else 0, "description": "GLB 格式三维场景文件。"},
        ],
        "primary_artifacts": [
            {"role": "pointcloud", "label": "点云结果", "name": "pointcloud.ply", "relative_path": "output/pointcloud.ply", "note": "优先检查全局结构。"},
            {"role": "camera", "label": "相机位姿", "name": "camera_poses.txt", "relative_path": "output/camera_poses.txt", "note": "复查相机轨迹稳定性。"},
        ],
        "review_targets": [
            {"role": "pointcloud", "label": "点云结果", "name": "pointcloud.ply", "relative_path": "output/pointcloud.ply", "note": "优先检查整体结构。"},
            {"role": "depth", "label": "深度图", "name": "depth_*.png", "relative_path": "output/", "note": "检查逐帧深度连续性。"},
        ],
    }
    (output_dir / "scene_meta.json").write_text(json.dumps(scene_meta, indent=2, ensure_ascii=False), encoding="utf-8")

    write_status(job_dir, "finished", f"已完成。从 {n_inputs} 帧导出 {n_artifacts} 个产物。")
    print(f"[align3r_runner] 任务成功完成。{n_artifacts} 个产物。")


if __name__ == "__main__":
    main()
