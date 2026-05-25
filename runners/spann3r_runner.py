#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


def write_status(job_dir: Path, phase: str, message: str, progress: str = "") -> None:
    payload = {
        "phase": phase,
        "message": message,
        "progress": progress,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (job_dir / "status.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def find_images(input_dir: Path) -> list[Path]:
    exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
    return sorted(path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in exts)


def stage_demo_inputs(job_dir: Path, images: list[Path]) -> Path:
    demo_dir = job_dir / "spann3r_demo_input"
    if demo_dir.exists():
        shutil.rmtree(demo_dir)
    demo_dir.mkdir(parents=True, exist_ok=True)
    for image in images:
        shutil.copy2(image, demo_dir / image.name)
    return demo_dir


def copy_if_exists(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Spann3R server-side job runner")
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--kf-every", type=int, default=10)
    parser.add_argument("--conf-thresh", type=float, default=0.001)
    args = parser.parse_args()

    job_dir = Path(args.job_dir)
    repo = Path(args.repo)
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    logs_dir = job_dir / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    images = find_images(input_dir)
    print(f"[spann3r_runner] 在 {input_dir} 中找到 {len(images)} 张图片。")
    if len(images) < 2:
        write_status(job_dir, "failed", "Spann3R 至少需要 2 张图片。")
        print("[spann3r_runner] 错误：Spann3R 至少需要 2 张图片。", file=sys.stderr)
        sys.exit(1)

    demo_input_dir = stage_demo_inputs(job_dir, images)
    demo_name = demo_input_dir.name
    save_root = job_dir / "spann3r_workspace"
    save_root.mkdir(parents=True, exist_ok=True)
    save_demo_dir = save_root / demo_name

    command = [
        sys.executable,
        str(repo / "demo.py"),
        "--demo_path",
        str(demo_input_dir),
        "--save_path",
        str(save_root),
        "--ckpt_path",
        str(Path(args.checkpoint)),
        "--kf_every",
        str(max(1, args.kf_every)),
        "--conf_thresh",
        str(args.conf_thresh),
        "--save_ori",
    ]

    write_status(job_dir, "starting", f"正在启动 Spann3R，输入图片数：{len(images)}。")
    write_status(job_dir, "running_matches", "正在启动 Spann3R 重建...", f"0/{len(images)}")
    print("Spann3R command:", " ".join(command), flush=True)

    env = dict(**__import__("os").environ)
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
    if completed.returncode != 0:
        write_status(job_dir, "failed", f"Spann3R demo.py 运行失败，返回码 {completed.returncode}。")
        raise SystemExit(completed.returncode)

    write_status(job_dir, "saving_outputs", "Spann3R 推理完成，正在整理输出。")

    ply_name = f"{demo_name}_conf{args.conf_thresh}.ply"
    npy_name = f"{demo_name}.npy"
    transforms_name = "transforms.json"

    copied = {
        "pointcloud": copy_if_exists(save_demo_dir / ply_name, output_dir / "pointcloud.ply"),
        "pointmap_array": copy_if_exists(save_demo_dir / npy_name, output_dir / npy_name),
        "transforms": copy_if_exists(save_demo_dir / transforms_name, output_dir / transforms_name),
    }

    if not copied["pointcloud"]:
        write_status(job_dir, "failed", f"未找到 Spann3R 点云输出：{save_demo_dir / ply_name}")
        raise SystemExit(1)

    scene_meta = {
        "model": "spann3r",
        "model_family": "memory_global_pointmap",
        "input_count": len(images),
        "image_files": [path.name for path in images],
        "artifact_count": sum(1 for value in copied.values() if value),
        "artifacts": {
            key: {"exists": value} for key, value in copied.items()
        },
        "params": {
            "kf_every": max(1, args.kf_every),
            "conf_thresh": args.conf_thresh,
            "save_ori": True,
        },
        "artifact_groups": [
            {"key": "pointcloud", "label": "点云结果", "count": 1, "description": "优先在 MeshLab 中检查全局结构与噪声。"},
            {"key": "transform", "label": "相机与变换", "count": 1 if copied["transforms"] else 0, "description": "用于复查相机轨迹与 Nerfstudio/3DGS 兼容导出。"},
            {"key": "array", "label": "几何数组", "count": 1 if copied["pointmap_array"] else 0, "description": "用于后续诊断 pointmap 与置信过滤效果。"},
        ],
        "primary_artifacts": [
            {"role": "pointcloud", "label": "点云结果", "name": "pointcloud.ply", "relative_path": "output/pointcloud.ply", "note": "优先在 MeshLab 中检查全局结构与噪声。"},
            {"role": "transform", "label": "相机与变换", "name": "transforms.json", "relative_path": "output/transforms.json", "note": "用于复查相机轨迹与导出兼容性。"},
        ],
        "review_targets": [
            {"role": "pointcloud", "label": "点云结果", "name": "pointcloud.ply", "relative_path": "output/pointcloud.ply", "note": "优先检查整体结构和噪声。"},
            {"role": "transform", "label": "相机与变换", "name": "transforms.json", "relative_path": "output/transforms.json", "note": "复查相机位姿与 transform 导出。"},
        ],
    }
    (output_dir / "scene_meta.json").write_text(json.dumps(scene_meta, indent=2, ensure_ascii=False), encoding="utf-8")

    write_status(job_dir, "finished", f"已完成。从 {len(images)} 张图片导出 Spann3R 点云。")
    print("[spann3r_runner] 任务成功完成。")


if __name__ == "__main__":
    main()
