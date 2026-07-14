#!/usr/bin/env python3
"""
MASt3R server-side job runner.

This script mirrors the DUSt3R runner contract so the local app can reuse
the same upload / download / visualization pipeline with minimal changes.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def write_status(job_dir: Path, phase: str, message: str, progress: str = "") -> None:
    status = {
        "phase": phase,
        "message": message,
        "progress": progress,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    (job_dir / "status.json").write_text(json.dumps(status, indent=2), encoding="utf-8")


def find_images(input_dir: Path) -> list[Path]:
    exts = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
    return sorted(
        p for p in input_dir.iterdir()
        if p.is_file() and p.suffix.lower() in exts
    )


def run_pair(args: argparse.Namespace, images: list[Path], job_dir: Path) -> None:
    sys.path.insert(0, args.repo)
    os.chdir(args.repo)

    output_dir = job_dir / "output"

    write_status(
        job_dir,
        "running_matches",
        f"正在加载模型，并对 {len(images)} 张图片运行 MASt3R...",
        progress=f"0/{len(images)}",
    )

    # MASt3R repo provides a compatibility shim so the DUSt3R global alignment
    # stack can still be reused after importing this module.
    import mast3r.utils.path_to_dust3r  # noqa: F401
    import torch
    from dust3r.cloud_opt import GlobalAlignerMode, global_aligner
    from dust3r.image_pairs import make_pairs
    from dust3r.inference import inference
    from dust3r.utils.image import load_images
    from mast3r.model import AsymmetricMASt3R

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[mast3r_runner] 正在从 {args.model} 加载模型")
    model = AsymmetricMASt3R.from_pretrained(args.model).to(device)

    print(
        f"[mast3r_runner] 参数：image_size={args.image_size}, scene_graph={args.scene_graph}, "
        f"niter={args.niter}, lr={args.lr}, batch_size={args.batch_size}, max_points={args.max_points}"
    )
    print(f"[mast3r_runner] 正在加载图片：{[str(p) for p in images]}")
    imgs = load_images([str(p) for p in images], size=args.image_size)
    pairs = make_pairs(imgs, scene_graph=args.scene_graph, prefilter=None, symmetrize=True)
    print(f"[mast3r_runner] 已构建 {len(pairs)} 个图像配对。")
    output = inference(pairs, model, device, batch_size=args.batch_size)

    print("[mast3r_runner] 正在运行全局对齐...")
    write_status(job_dir, "running_alignment", "正在运行全局对齐...")

    mode = GlobalAlignerMode.PairViewer if len(images) == 2 else GlobalAlignerMode.PointCloudOptimizer
    scene = global_aligner(output, device=device, mode=mode)

    if len(images) > 2:
        loss = scene.compute_global_alignment(init="mst", niter=args.niter, schedule="cosine", lr=args.lr)
        print(f"[mast3r_runner] 全局对齐损失：{loss}")

    write_status(job_dir, "saving_outputs", "正在保存匹配可视化图...")
    print("[mast3r_runner] 正在保存匹配可视化图...")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    imgs_array = scene.imgs
    match_path = output_dir / "matches.png"
    saved_match_lines = False
    match_total = 0
    match_shown = 0

    if len(imgs_array) >= 2 and args.match_viz_count > 0:
        try:
            from dust3r.utils.geometry import find_reciprocal_matches, xy_grid

            pts3d_for_matches = scene.get_pts3d()
            confidence_for_matches = scene.get_masks()
            pts2d_list, pts3d_list = [], []

            for view_idx in range(2):
                conf_i = confidence_for_matches[view_idx]
                if hasattr(conf_i, "detach"):
                    conf_i = conf_i.detach().cpu().numpy()
                conf_i = conf_i.astype(bool)

                pts3d_i = pts3d_for_matches[view_idx]
                if hasattr(pts3d_i, "detach"):
                    pts3d_i = pts3d_i.detach().cpu().numpy()

                pts2d_list.append(xy_grid(*imgs_array[view_idx].shape[:2][::-1])[conf_i])
                pts3d_list.append(pts3d_i[conf_i])

            reciprocal_in_p2, nn2_in_p1, num_matches = find_reciprocal_matches(*pts3d_list)
            n_viz = min(args.match_viz_count, int(num_matches))
            match_total = int(num_matches)
            match_shown = n_viz

            if n_viz > 0:
                matches_im1 = pts2d_list[1][reciprocal_in_p2]
                matches_im0 = pts2d_list[0][nn2_in_p1][reciprocal_in_p2]
                match_idx_to_viz = np.round(np.linspace(0, num_matches - 1, n_viz)).astype(int)
                viz_matches_im0 = matches_im0[match_idx_to_viz]
                viz_matches_im1 = matches_im1[match_idx_to_viz]

                h0, w0, h1, w1 = *imgs_array[0].shape[:2], *imgs_array[1].shape[:2]
                img0 = np.pad(imgs_array[0], ((0, max(h1 - h0, 0)), (0, 0), (0, 0)), "constant")
                img1 = np.pad(imgs_array[1], ((0, max(h0 - h1, 0)), (0, 0), (0, 0)), "constant")
                canvas = np.concatenate((img0, img1), axis=1)

                canvas_ratio = canvas.shape[1] / max(canvas.shape[0], 1)
                fig, ax = plt.subplots(1, 1, figsize=(14, max(4.5, 14 / canvas_ratio)))
                ax.imshow(canvas)
                ax.axis("off")
                ax.set_title(f"MASt3R feature correspondences | shown {n_viz} of {num_matches}", fontsize=12, pad=10)
                ax.axvline(w0 - 0.5, color="white", linewidth=1.2, alpha=0.9)
                label_box = {"facecolor": "black", "alpha": 0.65, "edgecolor": "none", "pad": 3}
                ax.text(10, 22, "View 1", color="white", fontsize=10, bbox=label_box)
                ax.text(w0 + 10, 22, "View 2", color="white", fontsize=10, bbox=label_box)
                cmap = plt.get_cmap("turbo")
                for line_idx in range(n_viz):
                    (x0, y0), (x1, y1) = viz_matches_im0[line_idx].T, viz_matches_im1[line_idx].T
                    color = cmap(line_idx / max(n_viz - 1, 1))
                    ax.plot([x0, x1 + w0], [y0, y1], "-", color=color, linewidth=0.9, alpha=0.72, scalex=False, scaley=False)
                    ax.scatter([x0, x1 + w0], [y0, y1], s=9, color=[color], edgecolors="white", linewidths=0.25)

                fig.subplots_adjust(left=0.01, right=0.99, bottom=0.01, top=0.90)
                plt.savefig(str(match_path), dpi=150, bbox_inches="tight", pad_inches=0.08, facecolor="white")
                plt.close()
                saved_match_lines = True
                print(f"[mast3r_runner] 匹配图已绘制 {n_viz}/{num_matches} 条匹配线。")
        except Exception as exc:
            print(f"[mast3r_runner] 警告：匹配线绘制失败，改为保存输入视图预览：{exc}")

    if not saved_match_lines:
        fig, axes = plt.subplots(1, len(imgs_array), figsize=(5 * len(imgs_array), 5))
        if len(imgs_array) == 1:
            axes = [axes]
        for i, img in enumerate(imgs_array):
            axes[i].imshow(img)
            axes[i].set_title(f"View {i + 1}")
            axes[i].axis("off")
        plt.tight_layout()
        plt.savefig(str(match_path), dpi=150, bbox_inches="tight")
        plt.close()
    print(f"[mast3r_runner] 匹配可视化图已保存到 {match_path}")

    write_status(job_dir, "exporting_pointcloud", "正在导出点云...")
    print("[mast3r_runner] 正在导出点云...")

    pts3d = scene.get_pts3d()
    confidence = scene.get_masks()

    all_pts = []
    all_colors = []

    for i in range(len(imgs_array)):
        pts = pts3d[i].detach().cpu().numpy()
        conf_i = confidence[i]
        if hasattr(conf_i, "detach"):
            mask = conf_i.detach().cpu().numpy().reshape(-1) > 0
        else:
            mask = conf_i.reshape(-1) > 0
        img_np = (np.array(imgs_array[i]) * 255).astype(np.uint8)

        h, w = pts.shape[:2]
        pts_flat = pts.reshape(-1, 3)
        colors_flat = img_np[:h, :w].reshape(-1, 3)

        all_pts.append(pts_flat[mask])
        all_colors.append(colors_flat[mask])

    all_pts = np.concatenate(all_pts, axis=0)
    all_colors = np.concatenate(all_colors, axis=0)
    raw_point_count = len(all_pts)

    if args.max_points and raw_point_count > args.max_points:
        keep = np.linspace(0, raw_point_count - 1, args.max_points).astype(np.int64)
        all_pts = all_pts[keep]
        all_colors = all_colors[keep]
        print(f"[mast3r_runner] 点云已从 {raw_point_count} 个点下采样到 {len(all_pts)} 个点。")

    ply_path = output_dir / "pointcloud.ply"
    with open(str(ply_path), "w", encoding="utf-8") as handle:
        handle.write("ply\n")
        handle.write("format ascii 1.0\n")
        handle.write(f"element vertex {len(all_pts)}\n")
        handle.write("property float x\n")
        handle.write("property float y\n")
        handle.write("property float z\n")
        handle.write("property uchar red\n")
        handle.write("property uchar green\n")
        handle.write("property uchar blue\n")
        handle.write("end_header\n")
        for pt, col in zip(all_pts, all_colors):
            handle.write(f"{pt[0]:.6f} {pt[1]:.6f} {pt[2]:.6f} {col[0]} {col[1]} {col[2]}\n")

    print(f"[mast3r_runner] 点云已保存到 {ply_path}，共 {len(all_pts)} 个点。")

    try:
        focals = scene.get_focals().detach().cpu().numpy().tolist()
        poses = [p.detach().cpu().numpy().tolist() for p in scene.get_im_poses()]
        meta = {
            "focals": focals,
            "poses": poses,
            "n_images": len(images),
            "n_pairs": len(pairs),
            "n_points": len(all_pts),
            "raw_point_count": raw_point_count,
            "match_visualization": {"shown": match_shown, "total": match_total},
            "image_files": [p.name for p in images],
            "params": {
                "image_size": args.image_size,
                "scene_graph": args.scene_graph,
                "niter": args.niter,
                "lr": args.lr,
                "batch_size": args.batch_size,
                "max_points": args.max_points,
                "match_viz_count": args.match_viz_count,
                "model_family": "mast3r",
            },
        }
        (output_dir / "scene_meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        print("[mast3r_runner] 场景元数据已保存。")
    except Exception as exc:
        print(f"[mast3r_runner] 警告：场景元数据保存失败：{exc}")

    write_status(job_dir, "finished", f"已完成。从 {len(images)} 张图片导出 {len(all_pts)} 个点。")
    print("[mast3r_runner] 任务成功完成。")


def main() -> None:
    parser = argparse.ArgumentParser(description="MASt3R server-side job runner")
    parser.add_argument("--job-dir", required=True, help="Path to the job directory")
    parser.add_argument("--model", required=True, help="Path to the MASt3R model weights")
    parser.add_argument("--repo", required=True, help="Path to the mast3r repo")
    parser.add_argument("--image-size", type=int, default=512, help="MASt3R input image size")
    parser.add_argument("--scene-graph", default="complete", help="Scene graph, e.g. complete, swin-5, oneref-0")
    parser.add_argument("--niter", type=int, default=300, help="Global alignment iterations for multi-image jobs")
    parser.add_argument("--lr", type=float, default=0.01, help="Global alignment learning rate")
    parser.add_argument("--batch-size", type=int, default=1, help="Pair inference batch size")
    parser.add_argument("--max-points", type=int, default=250000, help="Maximum exported PLY points after downsampling")
    parser.add_argument("--match-viz-count", type=int, default=30, help="Number of reciprocal match lines to draw for the first image pair")
    args = parser.parse_args()

    job_dir = Path(args.job_dir)
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    logs_dir = job_dir / "logs"

    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    images = find_images(input_dir)
    print(f"[mast3r_runner] 在 {input_dir} 中找到 {len(images)} 张图片。")

    if len(images) < 2:
        write_status(job_dir, "failed", "MASt3R 至少需要 2 张图片。")
        print("[mast3r_runner] 错误：MASt3R 至少需要 2 张图片。", file=sys.stderr)
        sys.exit(1)

    write_status(job_dir, "starting", f"正在启动 MASt3R，输入图片数：{len(images)}。")
    run_pair(args, images, job_dir)


if __name__ == "__main__":
    main()
