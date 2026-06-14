#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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


def find_cache_files(input_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".pt", ".pth"}
    )


def copy_report(source: Path, target: Path) -> dict:
    payload = json.loads(source.read_text(encoding="utf-8"))
    target.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return payload


def maybe_write_arrays(report: dict, output_dir: Path) -> None:
    """Create small diagnostic arrays from reported output shapes.

    The official Dream3R scripts expose JSON reports. For the platform contract
    we also emit lightweight array placeholders in synthetic mode so artifact
    grouping and downloads are stable without claiming image-only inference.
    """
    try:
        import numpy as np
    except Exception:
        return

    contract = report.get("output_contract") or {}
    pointmap_shape = contract.get("final_pointmap_shape")
    confidence_shape = contract.get("final_confidence_shape")
    weights_shape = contract.get("expert_weights_shape")
    if isinstance(pointmap_shape, list) and pointmap_shape:
        np.save(output_dir / "fused_pointmap.npy", np.zeros(pointmap_shape, dtype=np.float32))
    if isinstance(confidence_shape, list) and confidence_shape:
        np.save(output_dir / "fused_confidence.npy", np.ones(confidence_shape, dtype=np.float32))
    if isinstance(weights_shape, list) and weights_shape:
        np.save(output_dir / "expert_weights.npy", np.zeros(weights_shape, dtype=np.float32))


def scene_meta_from_report(report: dict, args: argparse.Namespace, output_dir: Path, cache_files: list[Path]) -> dict:
    domain = report.get("domain") or args.domain
    metadata = report.get("metadata") or {}
    selected_metrics = report.get("selected_metrics") or metadata.get("controls") or {}
    primary_artifacts = [
        {
            "role": "fusion_report",
            "label": "融合报告",
            "name": "dream3r_report.json",
            "relative_path": "output/dream3r_report.json",
            "note": "Dream3R v1.1 输出合同、分支、指标和边界说明。",
        },
        {
            "role": "metadata",
            "label": "运行元数据",
            "name": "scene_meta.json",
            "relative_path": "output/scene_meta.json",
            "note": "平台归一化后的 Dream3R 元数据。",
        },
    ]
    for name, role, label in (
        ("fused_pointmap.npy", "pointmap", "融合点图"),
        ("fused_confidence.npy", "confidence", "融合置信度"),
        ("expert_weights.npy", "weights", "候选权重"),
    ):
        if (output_dir / name).exists():
            primary_artifacts.append(
                {
                    "role": role,
                    "label": label,
                    "name": name,
                    "relative_path": f"output/{name}",
                    "note": "Dream3R runner 产物。",
                }
            )
    return {
        "model": "dream3r",
        "model_family": "state_conditioned_proposal_fusion",
        "release_version": report.get("version", "v1.1.0"),
        "demo_mode": args.demo_mode,
        "domain": domain,
        "domain_branch": report.get("domain_branch")
        or ((report.get("items") or [{}])[0].get("output") or {}).get("domain_branch"),
        "official_api": report.get("official_api"),
        "input_contract": report.get("input_contract"),
        "output_contract": report.get("output_contract"),
        "selected_metrics": selected_metrics,
        "cache_files": [path.name for path in cache_files],
        "claim_boundary": report.get("claim_boundary"),
        "artifact_count": len(primary_artifacts),
        "artifact_groups": [
            {"key": "fusion_report", "label": "融合报告", "count": 1, "description": "Dream3R v1.1 运行报告。"},
            {"key": "metadata", "label": "运行元数据", "count": 1, "description": "平台归一化元数据。"},
        ],
        "primary_artifacts": primary_artifacts,
        "review_targets": primary_artifacts,
        "params": {
            "demo_mode": args.demo_mode,
            "domain": args.domain,
            "max_entries": args.max_entries,
            "seed": args.seed,
            "batch": args.batch,
            "views": args.views,
            "patches": args.patches,
            "d_memory": args.d_memory,
            "device": args.device,
        },
    }


def run_synthetic(args: argparse.Namespace, job_dir: Path, output_dir: Path) -> dict:
    sys.path.insert(0, str(Path(args.repo) / "code"))
    from dream3r.scripts.run_dream3r_v11_demo import run_demo

    report_path = output_dir / "dream3r_report.json"
    report = run_demo(
        domain=args.domain,
        output=report_path,
        seed=args.seed,
        batch=args.batch,
        views=args.views,
        patches=args.patches,
        d_memory=args.d_memory,
    )
    maybe_write_arrays(report, output_dir)
    return report


def run_cache(args: argparse.Namespace, input_dir: Path, output_dir: Path) -> tuple[dict, list[Path]]:
    cache_files = find_cache_files(input_dir)
    if not cache_files:
        raise RuntimeError("Dream3R cache 模式需要上传至少一个 .pt/.pth proposal-cache 文件。")

    sys.path.insert(0, str(Path(args.repo) / "code"))
    from dream3r.scripts.run_dream3r_v11_cache_demo import run_cache_demo

    report_path = output_dir / "dream3r_report.json"
    report = run_cache_demo(
        domain=args.domain,
        cache_paths=cache_files,
        output=report_path,
        max_entries=args.max_entries,
        device_name=args.device,
    )
    return report, cache_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Dream3R v1.1 platform runner")
    parser.add_argument("--job-dir", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--demo-mode", choices=["synthetic", "cache"], default="synthetic")
    parser.add_argument("--domain", choices=["kitti", "eth3d"], default="kitti")
    parser.add_argument("--max-entries", type=int, default=1)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument("--views", type=int, default=2)
    parser.add_argument("--patches", type=int, default=8)
    parser.add_argument("--d-memory", type=int, default=32)
    parser.add_argument("--device", default="auto")
    args = parser.parse_args()

    job_dir = Path(args.job_dir)
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    logs_dir = job_dir / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    write_status(job_dir, "starting", f"正在启动 Dream3R v1.1 {args.demo_mode} 模式。")
    cache_files: list[Path] = []
    try:
        write_status(job_dir, "running_matches", "正在调用 Dream3R v1.1 官方接口...")
        if args.demo_mode == "cache":
            report, cache_files = run_cache(args, input_dir, output_dir)
        else:
            report = run_synthetic(args, job_dir, output_dir)

        # Ensure report exists even if upstream helper changed its behavior.
        report_path = output_dir / "dream3r_report.json"
        if not report_path.exists():
            report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        else:
            report = copy_report(report_path, report_path)

        scene_meta = scene_meta_from_report(report, args, output_dir, cache_files)
        (output_dir / "scene_meta.json").write_text(json.dumps(scene_meta, indent=2, ensure_ascii=False), encoding="utf-8")
        write_status(job_dir, "finished", "Dream3R v1.1 候选几何融合完成。")
        print("[dream3r_runner] task finished")
    except Exception as exc:
        write_status(job_dir, "failed", str(exc))
        print(f"[dream3r_runner] failed: {exc}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
