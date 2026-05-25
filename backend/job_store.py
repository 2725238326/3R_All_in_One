from __future__ import annotations

import json
import shutil
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterable, Sequence

from model_registry import default_runner_for


ROOT = Path(__file__).resolve().parent
LOCAL_JOBS_DIR = ROOT / "local_jobs"
_JOB_STORE_LOCK = threading.RLock()
_JOB_UPDATE_LISTENERS: list[Callable[[JobRecord], None]] = []
LOG_TAIL_READ_BYTES = 256 * 1024
JOB_LIST_DEFAULT_LIMIT = 50
JOB_LIST_MAX_LIMIT = 500
EVALUATION_RUBRIC_VERSION = 1
EVALUATION_SCORE_MIN = 1
EVALUATION_SCORE_MAX = 5
EVALUATION_SCORE_FIELDS = (
    "structure_completeness",
    "trajectory_stability",
    "noise",
    "dynamic_handling",
    "depth_continuity",
    "presentation_usability",
)
EVALUATION_FIELD_ALIASES = {
    "noise_control": "noise",
    "depth_consistency": "depth_continuity",
}


@dataclass
class JobRecord:
    job_id: str
    created_at: str
    model: str
    source_type: str
    notes: str
    sample_id: str | None = None
    params: dict = field(default_factory=dict)
    status: str = "draft"
    phase: str = "local_prepared"
    input_files: list[str] = field(default_factory=list)
    input_items: list[dict] = field(default_factory=list)
    output_files: list[str] = field(default_factory=list)
    remote_job_dir: str | None = None
    remote_runner: str | None = None
    error_message: str | None = None
    progress_message: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def ensure_local_jobs_dir() -> Path:
    LOCAL_JOBS_DIR.mkdir(parents=True, exist_ok=True)
    return LOCAL_JOBS_DIR


def make_job_id() -> str:
    base = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = base
    suffix = 1
    while get_job_dir(candidate).exists():
        candidate = f"{base}-{suffix:02d}"
        suffix += 1
    return candidate


def get_job_dir(job_id: str) -> Path:
    return ensure_local_jobs_dir() / job_id


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _base_job_evaluation(job_id: str) -> dict:
    payload = {
        "job_id": job_id,
        "rubric_version": EVALUATION_RUBRIC_VERSION,
        "score_min": EVALUATION_SCORE_MIN,
        "score_max": EVALUATION_SCORE_MAX,
        "updated_at": None,
        "notes": "",
    }
    for field_name in EVALUATION_SCORE_FIELDS:
        payload[field_name] = None
    return payload


def _normalize_job_evaluation(job_id: str, payload: dict | None = None) -> dict:
    normalized = _base_job_evaluation(job_id)
    if not payload:
        return normalized

    if payload.get("updated_at"):
        normalized["updated_at"] = str(payload["updated_at"])

    notes = payload.get("notes")
    if notes is not None:
        normalized["notes"] = str(notes)

    raw_scores = payload.get("scores")
    score_map = raw_scores if isinstance(raw_scores, dict) else {}
    for field_name in EVALUATION_SCORE_FIELDS:
        if field_name in payload:
            normalized[field_name] = payload[field_name]
        elif field_name in score_map:
            normalized[field_name] = score_map[field_name]
    for alias_name, canonical_name in EVALUATION_FIELD_ALIASES.items():
        if alias_name in payload:
            normalized[canonical_name] = payload[alias_name]
        elif alias_name in score_map:
            normalized[canonical_name] = score_map[alias_name]

    return normalized


def _public_job_evaluation(payload: dict) -> dict:
    public_payload = dict(payload)
    for alias_name, canonical_name in EVALUATION_FIELD_ALIASES.items():
        public_payload[alias_name] = public_payload.get(canonical_name)
    return public_payload


def create_job(model: str, source_type: str, notes: str, params: dict | None = None, sample_id: str | None = None) -> JobRecord:
    job_id = make_job_id()
    created_at = datetime.now().isoformat(timespec="seconds")
    normalized_sample_id = sample_id.strip() if isinstance(sample_id, str) else None
    job = JobRecord(
        job_id=job_id,
        created_at=created_at,
        model=model,
        source_type=source_type,
        notes=notes.strip(),
        sample_id=normalized_sample_id or None,
        params=params or {},
        remote_runner=_default_runner_for(model),
        progress_message="本地任务已就绪。文件名没有要求，系统会自动规范化内部命名。",
    )

    job_dir = get_job_dir(job_id)
    (job_dir / "input").mkdir(parents=True, exist_ok=True)
    (job_dir / "output").mkdir(parents=True, exist_ok=True)
    (job_dir / "logs").mkdir(parents=True, exist_ok=True)
    save_job(job)
    return job


def _default_runner_for(model: str) -> str:
    try:
        return default_runner_for(model)
    except KeyError:
        return "unknown_runner.py"


def save_job(job: JobRecord) -> None:
    with _JOB_STORE_LOCK:
        job_dir = get_job_dir(job.job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        _write_json(job_dir / "job.json", job.to_dict())
        _write_json(
            job_dir / "status.json",
            {
                "status": job.status,
                "phase": job.phase,
                "error_message": job.error_message,
                "progress_message": job.progress_message,
            },
        )


def register_job_update_listener(listener: Callable[[JobRecord], None]) -> None:
    with _JOB_STORE_LOCK:
        if listener not in _JOB_UPDATE_LISTENERS:
            _JOB_UPDATE_LISTENERS.append(listener)


def _notify_job_update(job: JobRecord) -> None:
    with _JOB_STORE_LOCK:
        listeners = list(_JOB_UPDATE_LISTENERS)
    for listener in listeners:
        try:
            listener(job)
        except Exception:
            continue


def load_job(job_id: str) -> JobRecord:
    with _JOB_STORE_LOCK:
        return _load_job_record(get_job_dir(job_id) / "job.json")


def list_jobs(limit: int = 20) -> list[JobRecord]:
    return query_jobs(limit=limit)["jobs"]


def list_all_jobs() -> list[JobRecord]:
    with _JOB_STORE_LOCK:
        ensure_local_jobs_dir()
        jobs = []
        for job_json in sorted(LOCAL_JOBS_DIR.glob("*/job.json"), reverse=True):
            jobs.append(_load_job_record(job_json))
        return jobs


def query_jobs(
    *,
    limit: int = JOB_LIST_DEFAULT_LIMIT,
    offset: int = 0,
    statuses: Sequence[str] | None = None,
    models: Sequence[str] | None = None,
    source_types: Sequence[str] | None = None,
    sample_id: str | None = None,
    search: str | None = None,
    sort: str = "created_desc",
) -> dict:
    with _JOB_STORE_LOCK:
        ensure_local_jobs_dir()
        normalized_limit = min(max(int(limit), 1), JOB_LIST_MAX_LIMIT)
        normalized_offset = max(int(offset), 0)
        status_filter = _filter_set(statuses)
        model_filter = _filter_set(models)
        source_filter = _filter_set(source_types)
        normalized_sample_id = str(sample_id).strip() if sample_id is not None else ""
        normalized_search = str(search).strip().lower() if search is not None else ""
        reverse = sort != "created_asc"

        jobs: list[JobRecord] = []
        matched_total = 0
        for job_json in sorted(LOCAL_JOBS_DIR.glob("*/job.json"), reverse=reverse):
            job = _load_job_record(job_json)
            if not _job_matches_filters(
                job,
                statuses=status_filter,
                models=model_filter,
                source_types=source_filter,
                sample_id=normalized_sample_id,
                search=normalized_search,
            ):
                continue
            matched_total += 1
            if matched_total <= normalized_offset:
                continue
            if len(jobs) < normalized_limit:
                jobs.append(job)

        return {
            "jobs": jobs,
            "page": {
                "limit": normalized_limit,
                "offset": normalized_offset,
                "total": matched_total,
                "has_more": normalized_offset + len(jobs) < matched_total,
                "sort": "created_asc" if sort == "created_asc" else "created_desc",
            },
            "filters": {
                "status": sorted(status_filter),
                "model": sorted(model_filter),
                "source_type": sorted(source_filter),
                "sample_id": normalized_sample_id or None,
                "search": normalized_search or None,
            },
        }


def _load_job_record(job_json: Path) -> JobRecord:
    payload = _read_json(job_json)
    payload.setdefault("sample_id", None)
    payload.setdefault("params", {})
    payload.setdefault("input_items", [])
    return JobRecord(**payload)


def _filter_set(values: Sequence[str] | None) -> set[str]:
    if not values:
        return set()
    normalized: set[str] = set()
    for value in values:
        for part in str(value).split(","):
            item = part.strip()
            if item:
                normalized.add(item)
    return normalized


def _job_matches_filters(
    job: JobRecord,
    *,
    statuses: set[str],
    models: set[str],
    source_types: set[str],
    sample_id: str,
    search: str,
) -> bool:
    if statuses and job.status not in statuses:
        return False
    if models and job.model not in models:
        return False
    if source_types and job.source_type not in source_types:
        return False
    if sample_id and (job.sample_id or "") != sample_id:
        return False
    if search:
        haystack = " ".join(
            [
                job.job_id,
                job.model,
                job.source_type,
                job.status,
                job.phase,
                job.notes or "",
                job.sample_id or "",
                job.progress_message or "",
                job.error_message or "",
            ]
        ).lower()
        if search not in haystack:
            return False
    return True


def _normalized_suffix(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    return suffix if suffix else ".bin"


def iter_input_items(job: JobRecord) -> list[dict]:
    if job.input_items:
        return list(job.input_items)

    items = []
    for rel_path in job.input_files:
        path = Path(rel_path)
        items.append(
            {
                "original_name": path.name,
                "stored_name": path.name,
                "relative_path": rel_path,
                "size_bytes": None,
            }
        )
    return items


def save_inputs(job: JobRecord, uploaded_files: Iterable[tuple[str, bytes]]) -> JobRecord:
    uploads = list(uploaded_files)
    job_dir = get_job_dir(job.job_id)
    input_dir = job_dir / "input"
    saved_paths: list[str] = []
    saved_items: list[dict] = []

    width = max(2, len(str(max(len(uploads), 1))))

    for index, (filename, content) in enumerate(uploads, start=1):
        suffix = _normalized_suffix(filename)
        stored_name = f"input_{index:0{width}d}{suffix}"
        target = input_dir / stored_name
        target.write_bytes(content)
        relative_path = str(target.relative_to(ROOT))
        saved_paths.append(relative_path)
        saved_items.append(
            {
                "original_name": filename,
                "stored_name": stored_name,
                "relative_path": relative_path,
                "size_bytes": len(content),
            }
        )

    job.input_files = saved_paths
    job.input_items = saved_items
    save_job(job)
    return job


def duplicate_job(job_id: str) -> JobRecord:
    source = load_job(job_id)
    new_job = create_job(
        model=source.model,
        source_type=source.source_type,
        notes=source.notes,
        params=dict(source.params),
        sample_id=source.sample_id,
    )

    uploads = []
    for item in iter_input_items(source):
        local_path = ROOT / item["relative_path"]
        uploads.append((item["original_name"], local_path.read_bytes()))

    save_inputs(new_job, uploads)
    update_job(
        new_job.job_id,
        progress_message=f"已从 {job_id} 复制任务，输入文件保持一致，可以直接运行。",
    )
    return load_job(new_job.job_id)


def clear_job_runtime(job_id: str) -> JobRecord:
    job = load_job(job_id)
    job_dir = get_job_dir(job_id)

    for folder_name in ("output", "logs"):
        folder = job_dir / folder_name
        folder.mkdir(parents=True, exist_ok=True)
        for child in folder.iterdir():
            if child.is_file():
                child.unlink()
            else:
                shutil.rmtree(child)

    remote_payload = job_dir / "remote_job.json"
    if remote_payload.exists():
        remote_payload.unlink()

    job.status = "draft"
    job.phase = "local_prepared"
    job.output_files = []
    job.error_message = None
    job.progress_message = "任务已在本地重置，可以重新调度。"
    save_job(job)
    return job


def get_log_snippets(job_id: str, limit: int = 60) -> list[dict]:
    snippets: list[dict] = []
    logs_dir = get_job_dir(job_id) / "logs"
    if not logs_dir.exists():
        return snippets

    for log_path in sorted(logs_dir.glob("*.log")):
        try:
            tail = _read_tail_lines(log_path, limit)
        except OSError:
            tail = []
        snippets.append(
            {
                "name": log_path.name,
                "relative_path": str(log_path.relative_to(ROOT)),
                "tail": "\n".join(tail),
            }
        )
    return snippets


def _read_tail_lines(path: Path, limit: int) -> list[str]:
    if limit <= 0:
        return []

    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > LOG_TAIL_READ_BYTES:
            handle.seek(max(0, size - LOG_TAIL_READ_BYTES))
            handle.readline()
        data = handle.read()

    return data.decode("utf-8", errors="replace").splitlines()[-limit:]


def _render_summary_markdown(payload: dict) -> str:
    lines = [
        f"# 任务摘要：{payload.get('job_id', 'unknown')}",
        "",
        f"- 模型：{payload.get('model', 'unknown')}",
        f"- 状态：{payload.get('status_label', payload.get('status', 'unknown'))}",
        f"- 输入类型：{payload.get('source_type', 'unknown')}",
        f"- 生成时间：{payload.get('generated_at', '-')}",
        "",
    ]

    highlights = payload.get("highlights") or []
    if highlights:
        lines.extend(["## 关键结果", ""])
        lines.extend([f"- {item}" for item in highlights])
        lines.append("")

    params = payload.get("params") or {}
    if params:
        lines.extend(["## 运行参数", ""])
        lines.extend([f"- {key}: {value}" for key, value in params.items()])
        lines.append("")

    artifacts = payload.get("artifacts") or []
    if artifacts:
        lines.extend(["## 产物列表", ""])
        for item in artifacts:
            lines.append(f"- {item.get('name', 'unknown')}: {item.get('relative_path', '-')}")
        lines.append("")

    next_actions = payload.get("next_actions") or []
    if next_actions:
        lines.extend(["## 建议后续动作", ""])
        lines.extend([f"- {item}" for item in next_actions])
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def write_result_summary(job_id: str, payload: dict) -> None:
    job_dir = get_job_dir(job_id)
    _write_json(job_dir / "result_summary.json", payload)
    (job_dir / "result_summary.md").write_text(_render_summary_markdown(payload), encoding="utf-8")


def load_result_summary(job_id: str) -> dict | None:
    path = get_job_dir(job_id) / "result_summary.json"
    if not path.exists():
        return None
    return _read_json(path)


def load_job_evaluation(job_id: str) -> dict:
    path = get_job_dir(job_id) / "evaluation.json"
    if not path.exists():
        return _public_job_evaluation(_base_job_evaluation(job_id))
    return _public_job_evaluation(_normalize_job_evaluation(job_id, _read_json(path)))


def save_job_evaluation(job_id: str, payload: dict) -> dict:
    with _JOB_STORE_LOCK:
        normalized = _normalize_job_evaluation(job_id, payload)
        normalized["updated_at"] = datetime.now().isoformat(timespec="seconds")
        job_dir = get_job_dir(job_id)
        job_dir.mkdir(parents=True, exist_ok=True)
        _write_json(job_dir / "evaluation.json", normalized)
        return _public_job_evaluation(normalized)


def load_evaluation(job_id: str) -> dict:
    return load_job_evaluation(job_id)


def save_evaluation(job_id: str, payload: dict) -> dict:
    return save_job_evaluation(job_id, payload)


def update_job(
    job_id: str,
    *,
    status: str | None = None,
    phase: str | None = None,
    remote_job_dir: str | None = None,
    output_files: list[str] | None = None,
    error_message: str | None = None,
    progress_message: str | None = None,
) -> JobRecord:
    with _JOB_STORE_LOCK:
        job = load_job(job_id)
        if status is not None:
            job.status = status
        if phase is not None:
            job.phase = phase
        if remote_job_dir is not None:
            job.remote_job_dir = remote_job_dir
        if output_files is not None:
            job.output_files = output_files
        job.error_message = error_message
        if progress_message is not None:
            job.progress_message = progress_message
        save_job(job)
    _notify_job_update(job)
    return job


def recover_orphan_running_jobs() -> list[str]:
    """Mark jobs whose ``status == "running"`` as ``failed`` because no runner
    thread can be holding them across an uvicorn restart.

    Returns the list of job IDs that were rehydrated. Safe to call repeatedly;
    only jobs whose status is currently ``running`` are touched.
    """
    rehydrated: list[str] = []
    with _JOB_STORE_LOCK:
        ensure_local_jobs_dir()
        for job_json in sorted(LOCAL_JOBS_DIR.glob("*/job.json")):
            try:
                job = _load_job_record(job_json)
            except Exception:
                continue
            if job.status != "running":
                continue
            job.status = "failed"
            job.phase = "failed"
            job.error_message = (
                "本地后端在任务运行中重启或崩溃，调度线程已不存在。"
                "任务被标记为失败以避免 UI 长期假在跑；可点击重试重新调度。"
            )
            job.progress_message = "后端重启后未发现运行线程，已自动标记为失败。"
            try:
                save_job(job)
                rehydrated.append(job.job_id)
            except Exception:
                continue
    return rehydrated
