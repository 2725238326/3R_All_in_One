#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np


def write_status(job_dir: Path, phase: str, message: str, progress: str = "") -> None:
    payload = {
        "phase": phase,
        "message": message,
        "progress": progress,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (job_dir / "status.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def write_ply(points: np.ndarray, colors: np.ndarray, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        handle.write("ply\n")
        handle.write("format ascii 1.0\n")
        handle.write(f"element vertex {len(points)}\n")
        handle.write("property float x\n")
        handle.write("property float y\n")
        handle.write("property float z\n")
        handle.write("property uchar red\n")
        handle.write("property uchar green\n")
        handle.write("property uchar blue\n")
        handle.write("end_header\n")
        for point, color in zip(points, colors):
            handle.write(f"{point[0]:.6f} {point[1]:.6f} {point[2]:.6f} {int(color[0])} {int(color[1])} {int(color[2])}\n")


def build_attention_fallback(torch_module):
    def scaled_dot_product_attention(q, k, v, attn_mask=None, dropout_p=0.0, is_causal=False, scale=None):
        scale_factor = scale if scale is not None else q.size(-1) ** -0.5
        scores = torch_module.matmul(q, k.transpose(-2, -1)) * scale_factor

        if is_causal:
            target_length = q.size(-2)
            source_length = k.size(-2)
            causal_mask = torch_module.ones(
                (target_length, source_length),
                dtype=torch_module.bool,
                device=q.device,
            ).tril(diagonal=0)
            scores = scores.masked_fill(~causal_mask, float("-inf"))

        if attn_mask is not None:
            if attn_mask.dtype == torch_module.bool:
                scores = scores.masked_fill(~attn_mask, float("-inf"))
            else:
                scores = scores + attn_mask

        weights = torch_module.softmax(scores, dim=-1)
        if dropout_p and dropout_p > 0:
            weights = torch_module.dropout(weights, dropout_p, train=True)
        return torch_module.matmul(weights, v)

    return scaled_dot_product_attention


def main() -> None:
    parser = argparse.ArgumentParser(description="Fast3R server-side job runner")
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--checkpoint-dir", required=True)
    parser.add_argument("--image-size", type=int, default=512)
    parser.add_argument("--max-points", type=int, default=250000)
    parser.add_argument("--attention-backend", default="pytorch_naive")
    parser.add_argument("--pose-iterations", type=int, default=100)
    parser.add_argument("--focal-estimation-method", default="first_view_from_global_head")
    args = parser.parse_args()

    job_dir = Path(args.job_dir)
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    logs_dir = job_dir / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    repo = Path(args.repo)
    sys.path.insert(0, str(repo))

    import torch
    from fast3r.dust3r.utils.image import load_images, rgb
    from fast3r.croco.models import blocks as fast3r_blocks
    from fast3r.models.fast3r import Fast3R
    from fast3r.models.multiview_dust3r_module import estimate_cam_pose_one_sample, estimate_focal

    image_files = sorted(path for path in input_dir.iterdir() if path.is_file() and path.suffix.lower() in {".png", ".jpg", ".jpeg", ".bmp", ".webp"})
    print(f"[fast3r_runner] 在 {input_dir} 中找到 {len(image_files)} 张图片。")
    if len(image_files) < 2:
        write_status(job_dir, "failed", "Fast3R 至少需要 2 张图片。")
        print("[fast3r_runner] 错误：Fast3R 至少需要 2 张图片。", file=sys.stderr)
        sys.exit(1)

    device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda":
        try:
            torch.backends.cuda.enable_flash_sdp(False)
            torch.backends.cuda.enable_mem_efficient_sdp(False)
            torch.backends.cuda.enable_math_sdp(True)
            print("[fast3r_runner] Forced PyTorch math SDP backend for sm75 compatibility.", flush=True)
        except Exception as exc:
            print(f"[fast3r_runner] Could not adjust SDP backend: {exc}", flush=True)
        fast3r_blocks.scaled_dot_product_attention = build_attention_fallback(torch)
        print("[fast3r_runner] Installed local scaled-dot-product attention fallback.", flush=True)
    checkpoint_dir = Path(args.checkpoint_dir)
    write_status(job_dir, "starting", f"正在启动 Fast3R，输入图片数：{len(image_files)}。")
    write_status(job_dir, "running_matches", "正在加载 Fast3R 模型并执行前馈推理...", f"0/{len(image_files)}")

    print(f"Fast3R command: checkpoint_dir={checkpoint_dir} attention_backend={args.attention_backend} image_size={args.image_size}")
    actual_attention_backend = args.attention_backend
    try:
        model = Fast3R.from_pretrained(str(checkpoint_dir), attn_implementation=args.attention_backend)
    except TypeError as exc:
        if "attn_implementation" not in str(exc):
            raise
        actual_attention_backend = f"default_loader(requested={args.attention_backend})"
        print(
            "[fast3r_runner] Fast3R.from_pretrained does not accept attn_implementation; "
            "retrying with the checkpoint default attention backend.",
            flush=True,
        )
        model = Fast3R.from_pretrained(str(checkpoint_dir))
    model.eval().to(device)

    views = load_images([str(path) for path in image_files], size=args.image_size, verbose=True)
    for view in views:
        view["img"] = view["img"].to(device)
        view["true_shape"] = torch.tensor(view["true_shape"], device=device)

    with torch.no_grad():
        preds, profiling_info = model(views, profiling=True)

    write_status(job_dir, "saving_outputs", "Fast3R 推理完成，正在整理点云和相机信息。")

    sample_preds = []
    total_points = []
    total_colors = []
    confidence_values = []
    per_view_stats = []
    for index, pred in enumerate(preds):
        pts = pred["pts3d_in_other_view"][0].detach().cpu().numpy()
        conf = pred.get("conf")
        if conf is None:
            conf_map = np.ones(pts.shape[:2], dtype=np.float32)
        else:
            conf_map = conf[0].detach().cpu().numpy()
        colors = (rgb(views[index]["img"][0].detach().cpu()) * 255).astype(np.uint8)
        mask = conf_map > 1.0
        if not np.any(mask):
            mask = np.ones_like(conf_map, dtype=bool)
        total_points.append(pts[mask].reshape(-1, 3))
        total_colors.append(colors[mask].reshape(-1, 3))
        confidence_values.append(conf_map[mask].reshape(-1))
        estimated_focal = estimate_focal(pred["pts3d_in_other_view"][:1], pred["conf"][:1] if pred.get("conf") is not None else torch.ones_like(pred["pts3d_in_other_view"][:1, :, :, 0]), min_conf_thr_percentile=10)
        sample_pred = {key: value[0].detach().cpu() if hasattr(value, 'detach') else value for key, value in pred.items()}
        sample_pred["focal_length"] = estimated_focal
        sample_preds.append(sample_pred)
        per_view_stats.append({
            "index": index,
            "file": image_files[index].name,
            "kept_points": int(mask.sum()),
            "focal_length": float(estimated_focal),
        })

    points = np.concatenate(total_points, axis=0)
    colors = np.concatenate(total_colors, axis=0)
    raw_point_count = len(points)
    if args.max_points and raw_point_count > args.max_points:
        keep = np.linspace(0, raw_point_count - 1, args.max_points).astype(np.int64)
        points = points[keep]
        colors = colors[keep]

    write_ply(points, colors, output_dir / "pointcloud.ply")

    poses_c2w, estimated_focals = estimate_cam_pose_one_sample(sample_preds, device="cpu", niter_PnP=args.pose_iterations)
    camera_payload = {
        "poses_c2w": [pose.tolist() for pose in poses_c2w],
        "estimated_focals": [float(item) if item is not None else None for item in estimated_focals],
        "focal_estimation_method": args.focal_estimation_method,
        "pose_iterations": args.pose_iterations,
    }
    (output_dir / "camera_poses.json").write_text(json.dumps(camera_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    confidence_summary = {
        "mean": float(np.mean(np.concatenate(confidence_values, axis=0))),
        "median": float(np.median(np.concatenate(confidence_values, axis=0))),
        "min": float(np.min(np.concatenate(confidence_values, axis=0))),
        "max": float(np.max(np.concatenate(confidence_values, axis=0))),
    }
    (output_dir / "confidence_summary.json").write_text(json.dumps(confidence_summary, indent=2, ensure_ascii=False), encoding="utf-8")

    metadata = {
        "input_files": [path.name for path in image_files],
        "profiling_info": profiling_info,
        "attention_backend": actual_attention_backend,
        "requested_attention_backend": args.attention_backend,
        "device": device,
        "image_size": args.image_size,
        "checkpoint_dir": str(checkpoint_dir),
        "per_view_stats": per_view_stats,
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    scene_meta = {
        "model": "fast3r",
        "model_family": "large_image_collection",
        "input_count": len(image_files),
        "image_files": [path.name for path in image_files],
        "artifact_count": 4,
        "n_points": int(len(points)),
        "raw_point_count": int(raw_point_count),
        "attention_backend": actual_attention_backend,
        "requested_attention_backend": args.attention_backend,
        "profiling_info": profiling_info,
        "params": {
            "image_size": args.image_size,
            "max_points": args.max_points,
            "pose_iterations": args.pose_iterations,
            "focal_estimation_method": args.focal_estimation_method,
        },
        "artifact_groups": [
            {"key": "pointcloud", "label": "点云结果", "count": 1, "description": "优先检查结构完整性和稠密程度。"},
            {"key": "camera", "label": "相机信息", "count": 1, "description": "用于复查相机位姿和焦距估计。"},
            {"key": "confidence", "label": "置信摘要", "count": 1, "description": "用于诊断低置信区域与整体可信度。"},
            {"key": "metadata", "label": "运行元数据", "count": 1, "description": "用于复查 attention backend、profiling 与输入列表。"},
        ],
        "primary_artifacts": [
            {"role": "pointcloud", "label": "点云结果", "name": "pointcloud.ply", "relative_path": "output/pointcloud.ply", "note": "优先检查结构完整性和稠密程度。"},
            {"role": "camera", "label": "相机信息", "name": "camera_poses.json", "relative_path": "output/camera_poses.json", "note": "复查相机位姿与焦距估计。"},
            {"role": "confidence", "label": "置信摘要", "name": "confidence_summary.json", "relative_path": "output/confidence_summary.json", "note": "判断低置信区域是否过多。"},
        ],
        "review_targets": [
            {"role": "pointcloud", "label": "点云结果", "name": "pointcloud.ply", "relative_path": "output/pointcloud.ply", "note": "优先检查结构完整性和稠密程度。"},
            {"role": "camera", "label": "相机信息", "name": "camera_poses.json", "relative_path": "output/camera_poses.json", "note": "复查相机位姿与焦距估计。"},
            {"role": "confidence", "label": "置信摘要", "name": "confidence_summary.json", "relative_path": "output/confidence_summary.json", "note": "判断低置信区域是否过多。"},
        ],
    }
    (output_dir / "scene_meta.json").write_text(json.dumps(scene_meta, indent=2, ensure_ascii=False), encoding="utf-8")

    write_status(job_dir, "finished", f"已完成。从 {len(image_files)} 张图片导出 Fast3R 点云。")
    print("[fast3r_runner] 任务成功完成。")


if __name__ == "__main__":
    main()
