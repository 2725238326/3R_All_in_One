"""
实验记录包 (Experiment Record Bundle)

把一个已完成任务整理成可复现的实验记录：不仅打包原始产物，还生成一份
``experiment_record.json`` manifest 和人类可读的 ``EXPERIMENT_RECORD.md``，
把「用哪个模型蓝图、什么 conda/torch/commit、什么参数、哪台服务器、哪个 runner、
得到什么结果」串成自描述记录，便于后续复现与交付归档。

本模块刻意保持「纯」：manifest 构建只接收普通 dict，不直接依赖 agent 注册表或
SSH，方便单测。app.py 负责把数据源（job / blueprint / contract / scene_meta）
喂进来并完成打包下载。
"""
from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

RECORD_SCHEMA_VERSION = 1


def build_experiment_record(
    *,
    job: dict[str, Any],
    result_summary: dict[str, Any] | None = None,
    scene_meta: dict[str, Any] | None = None,
    blueprint: dict[str, Any] | None = None,
    contract: dict[str, Any] | None = None,
    server: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a self-describing, reproducible experiment-record manifest."""
    job = job or {}
    blueprint = blueprint or {}
    contract = contract or {}
    params = job.get("params") or {}
    model = job.get("model")
    env = blueprint.get("environment") or {}
    repo = blueprint.get("repo") or {}
    runner = blueprint.get("runner") or {}
    result_contract = contract.get("resultContract") or {}
    runner_contract = contract.get("runner") or {}

    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "generated_at": generated_at or datetime.now().isoformat(timespec="seconds"),
        "job": {
            "job_id": job.get("job_id"),
            "model": model,
            "source_type": job.get("source_type"),
            "status": job.get("status"),
            "created_at": job.get("created_at"),
            "notes": job.get("notes"),
            "sample_id": job.get("sample_id"),
            "params": params,
            "input_count": len(job.get("input_files") or []),
            "output_count": len(job.get("output_files") or []),
        },
        # The reproduce block is the heart of the record: everything needed to
        # re-run this experiment on the GPU server.
        "reproduce": {
            "model": model,
            "conda_env": env.get("conda_env") or runner.get("conda_env"),
            "python": env.get("python"),
            "torch": env.get("torch"),
            "cuda_toolkit": env.get("cuda_toolkit"),
            "repo_url": repo.get("url"),
            "repo_branch": repo.get("branch"),
            "repo_commit": blueprint.get("version") or repo.get("commit"),
            "server_path": repo.get("server_path"),
            "runner_script": runner.get("script"),
            "params": params,
            "checkpoints": blueprint.get("checkpoints") or [],
            "build_steps": blueprint.get("build_steps") or [],
            "smoke_test": blueprint.get("smoke_test") or {},
            "server": server or {},
        },
        "result": {
            "duration_seconds": (result_summary or {}).get("duration_seconds"),
            "highlights": (result_summary or {}).get("highlights") or [],
            "next_actions": (result_summary or {}).get("next_actions") or [],
            "artifacts": (result_summary or {}).get("artifacts") or [],
            "scene_meta": scene_meta,
        },
        "contract": {
            "runner_status": contract.get("runnerStatus"),
            "download_mode": runner_contract.get("downloadMode"),
            "required_files": result_contract.get("requiredFiles") or [],
            "optional_files": result_contract.get("optionalFiles") or [],
        },
    }


def render_record_markdown(record: dict[str, Any]) -> str:
    """Render a human-readable EXPERIMENT_RECORD.md from a manifest."""
    job = record.get("job") or {}
    repro = record.get("reproduce") or {}
    result = record.get("result") or {}
    lines: list[str] = [
        f"# 实验记录：{job.get('job_id', 'unknown')}",
        "",
        f"- 模型：{job.get('model', 'unknown')}",
        f"- 状态：{job.get('status', 'unknown')}",
        f"- 输入类型：{job.get('source_type', 'unknown')}",
        f"- 创建时间：{job.get('created_at', '-')}",
        f"- 记录生成时间：{record.get('generated_at', '-')}",
        "",
        "## 复现配置",
        "",
        f"- conda env：{repro.get('conda_env') or '-'}",
        f"- Python：{repro.get('python') or '-'}",
        f"- PyTorch：{repro.get('torch') or '-'}",
        f"- CUDA：{repro.get('cuda_toolkit') or '-'}",
        f"- 仓库：{repro.get('repo_url') or '-'} ({repro.get('repo_commit') or 'commit 未固定'})",
        f"- 服务器路径：{repro.get('server_path') or '-'}",
        f"- Runner：{repro.get('runner_script') or '-'}",
        "",
        "### 运行参数",
        "",
    ]
    params = repro.get("params") or {}
    if params:
        lines.extend([f"- {key}: {value}" for key, value in params.items()])
    else:
        lines.append("- (无)")

    checkpoints = repro.get("checkpoints") or []
    if checkpoints:
        lines.extend(["", "### 依赖权重", ""])
        for ckpt in checkpoints:
            name = ckpt.get("name") if isinstance(ckpt, dict) else str(ckpt)
            lines.append(f"- {name}")

    highlights = result.get("highlights") or []
    if highlights:
        lines.extend(["", "## 结果要点", ""])
        lines.extend([f"- {item}" for item in highlights])

    next_actions = result.get("next_actions") or []
    if next_actions:
        lines.extend(["", "## 建议后续动作", ""])
        lines.extend([f"- {item}" for item in next_actions])

    lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_experiment_record_bundle(
    *,
    job_id: str,
    job_dir: Path,
    record: dict[str, Any],
    out_dir: Path,
) -> Path:
    """Write a curated, reproducible experiment-record zip.

    Contains the manifest, the rendered markdown, and the full job directory
    (job.json, params, inputs, outputs incl. scene_meta.json, logs)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    bundle_path = out_dir / f"{job_id}-experiment-{timestamp}.zip"
    job_dir = job_dir.resolve()

    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            str(Path(job_id) / "experiment_record.json"),
            json.dumps(record, indent=2, ensure_ascii=False),
        )
        archive.writestr(
            str(Path(job_id) / "EXPERIMENT_RECORD.md"),
            render_record_markdown(record),
        )
        if job_dir.exists():
            for path in sorted(job_dir.rglob("*")):
                if not path.is_file():
                    continue
                try:
                    relative = path.resolve().relative_to(job_dir)
                except ValueError:
                    continue
                archive.write(path, arcname=str(Path(job_id) / relative))

    return bundle_path
