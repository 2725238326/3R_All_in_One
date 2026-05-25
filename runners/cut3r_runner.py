#!/usr/bin/env python3
"""
CUT3R server-side job runner.

Runs the official CUT3R demo in non-interactive mode, collects pointmaps,
point clouds, camera parameters, and state metadata into the standard job
output directory.
"""
from __future__ import annotations

import argparse
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
    """Collect outputs from CUT3R workspace into standard output dir.

    CUT3R outputs:
      workspace/camera/  *.npz  (intrinsics + extrinsics per frame)
      workspace/depth/   *.npy  (depth maps per frame)
      workspace/conf/    *.npy  (confidence maps per frame)
      workspace/color/   *.png  (color frames)
    """
    copied = {}

    # Camera parameters (npz)
    cam_dir = workspace / "camera"
    if cam_dir.is_dir():
        cam_out = output_dir / "camera"
        cam_out.mkdir(parents=True, exist_ok=True)
        for f in sorted(cam_dir.glob("*.npz")):
            shutil.copy2(f, cam_out / f.name)
            copied[f"camera_{f.stem}"] = True

    # Depth maps (npy)
    depth_dir = workspace / "depth"
    if depth_dir.is_dir():
        depth_out = output_dir / "depth"
        depth_out.mkdir(parents=True, exist_ok=True)
        for f in sorted(depth_dir.glob("*.npy")):
            shutil.copy2(f, depth_out / f.name)
            copied[f"depth_{f.stem}"] = True

    # Confidence maps (npy)
    conf_dir = workspace / "conf"
    if conf_dir.is_dir():
        conf_out = output_dir / "conf"
        conf_out.mkdir(parents=True, exist_ok=True)
        for f in sorted(conf_dir.glob("*.npy")):
            shutil.copy2(f, conf_out / f.name)
            copied[f"conf_{f.stem}"] = True

    # Color frames
    color_dir = workspace / "color"
    if color_dir.is_dir():
        color_out = output_dir / "color"
        color_out.mkdir(parents=True, exist_ok=True)
        for f in sorted(color_dir.iterdir()):
            if f.suffix.lower() in IMAGE_SUFFIXES:
                shutil.copy2(f, color_out / f.name)
                copied[f"color_{f.stem}"] = True

    # Any PLY point clouds
    for ply in sorted(workspace.glob("**/*.ply")):
        copy_if_exists(ply, output_dir / "pointcloud.ply")
        copied["pointcloud"] = True
        break

    # Any GLB scenes
    for glb in sorted(workspace.glob("**/*.glb")):
        copy_if_exists(glb, output_dir / "scene.glb")
        copied["scene"] = True
        break

    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description="CUT3R server-side job runner")
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--vis-threshold", type=float, default=1.5)
    parser.add_argument("--max-frames", type=int, default=48)
    args = parser.parse_args()

    job_dir = Path(args.job_dir)
    repo = Path(args.repo)
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    logs_dir = job_dir / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    # Determine input mode: video or images (as sequence)
    video = find_video(input_dir)
    if video:
        print(f"[cut3r_runner] 检测到视频输入: {video.name}")
        frames_dir = job_dir / "cut3r_frames"
        frames = extract_frames(video, frames_dir, max_frames=args.max_frames)
        seq_path = str(frames_dir)
        n_inputs = len(frames)
        input_mode = "video"
    else:
        images = find_images(input_dir)
        if len(images) < 2:
            write_status(job_dir, "failed", "CUT3R 至少需要 2 张图片或 1 个视频文件。")
            print("[cut3r_runner] 错误：至少需要 2 张图片或 1 个视频。", file=sys.stderr)
            sys.exit(1)
        seq_path = str(input_dir)
        n_inputs = len(images)
        input_mode = "images"

    workspace = job_dir / "cut3r_workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    # CUT3R demo.py blocks on a viser viewer after inference.
    # We use a wrapper script that calls run_inference() directly and exits.
    wrapper_script = job_dir / "_cut3r_headless.py"
    wrapper_script.write_text(f"""
import sys
sys.path.insert(0, "{repo}")
from demo import parse_args, run_inference
import types

# Monkey-patch: skip viewer launch by making viser_utils a no-op module
class FakeViewer:
    def __init__(self, *a, **kw): pass
    def run(self): pass

fake_mod = types.ModuleType("viser_utils")
fake_mod.PointCloudViewer = FakeViewer
sys.modules["viser_utils"] = fake_mod

# Build args
sys.argv = [
    "demo.py",
    "--model_path", "{args.model_path}",
    "--size", "{args.size}",
    "--seq_path", "{seq_path}",
    "--vis_threshold", "{args.vis_threshold}",
    "--output_dir", "{workspace}",
]
args = parse_args()
run_inference(args)
print("[cut3r_headless] Inference complete, exiting.")
""", encoding="utf-8")

    command = [sys.executable, "-u", str(wrapper_script)]

    write_status(job_dir, "starting", f"正在启动 CUT3R，{input_mode} 输入，帧数：{n_inputs}。")
    write_status(job_dir, "running_matches", "正在运行 CUT3R 在线三维感知...", f"0/{n_inputs}")
    print(f"[cut3r_runner] 命令: {' '.join(command)}", flush=True)

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
        write_status(job_dir, "failed", f"CUT3R demo.py 运行失败，返回码 {completed.returncode}。")
        raise SystemExit(completed.returncode)

    write_status(job_dir, "saving_outputs", "CUT3R 推理完成，正在整理输出。")

    copied = collect_outputs(workspace, output_dir)
    n_artifacts = sum(1 for v in copied.values() if v)
    depth_count = sum(1 for k, v in copied.items() if k.startswith("depth_") and v)
    camera_count = sum(1 for k, v in copied.items() if k.startswith("camera_") and v)
    conf_count = sum(1 for k, v in copied.items() if k.startswith("conf_") and v)

    scene_meta = {
        "model": "cut3r",
        "model_family": "streaming_state_reconstruction",
        "input_mode": input_mode,
        "input_count": n_inputs,
        "artifact_count": n_artifacts,
        "artifacts": {k: {"exists": v} for k, v in copied.items()},
        "params": {
            "size": args.size,
            "vis_threshold": args.vis_threshold,
            "max_frames": args.max_frames,
        },
        "artifact_groups": [
            {"key": "camera", "label": "相机参数", "count": camera_count, "description": "逐帧相机内外参 (npz)。"},
            {"key": "depth", "label": "深度图", "count": depth_count, "description": "逐帧深度图 (npy)，检查在线估计的时序稳定性。"},
            {"key": "confidence", "label": "置信图", "count": conf_count, "description": "逐帧置信分布 (npy)。"},
            {"key": "pointcloud", "label": "点云结果", "count": 1 if copied.get("pointcloud") else 0, "description": "全局点云，检查在线重建的结构完整性。"},
            {"key": "scene", "label": "三维场景", "count": 1 if copied.get("scene") else 0, "description": "GLB 格式场景文件。"},
        ],
        "primary_artifacts": [
            {"role": "camera", "label": "相机参数", "name": "camera/", "relative_path": "output/camera/", "note": "逐帧相机 npz，含 intrinsic + extrinsic。"},
            {"role": "depth", "label": "深度图", "name": "depth/", "relative_path": "output/depth/", "note": "逐帧深度 npy，检查时序稳定性。"},
        ],
        "review_targets": [
            {"role": "camera", "label": "相机参数", "name": "camera/", "relative_path": "output/camera/", "note": "优先检查相机位姿连续性。"},
            {"role": "depth", "label": "深度图", "name": "depth/", "relative_path": "output/depth/", "note": "检查逐帧深度估计稳定性。"},
            {"role": "confidence", "label": "置信图", "name": "conf/", "relative_path": "output/conf/", "note": "检查低置信区域。"},
        ],
    }
    (output_dir / "scene_meta.json").write_text(json.dumps(scene_meta, indent=2, ensure_ascii=False), encoding="utf-8")

    write_status(job_dir, "finished", f"已完成。从 {n_inputs} 帧导出 {n_artifacts} 个产物。")
    print(f"[cut3r_runner] 任务成功完成。{n_artifacts} 个产物。")


if __name__ == "__main__":
    main()
