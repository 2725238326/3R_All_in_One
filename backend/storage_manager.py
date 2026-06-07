"""存储管理核心逻辑：统计、清理、配额检查。"""
from __future__ import annotations

import shutil
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from job_store import get_job_dir, list_all_jobs, load_job, ROOT
from runtime_paths import local_jobs_dir
from storage_config import (
    AutoCleanConfig,
    CleanupCondition,
    CleanupRule,
    StorageConfig,
    load_config,
    save_config,
)

_LOCK = threading.RLock()
_auto_clean_thread: threading.Thread | None = None
_auto_clean_stop_event = threading.Event()
_TRASH_DIR = ROOT / "trash"


@dataclass
class StorageStats:
    total_bytes: int
    used_bytes: int
    free_bytes: int
    job_count: int
    by_model: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)
    largest_jobs: list[tuple[str, int]] = field(default_factory=list)  # (job_id, bytes)


@dataclass
class CleanupCandidate:
    job_id: str
    reason: str
    size_bytes: int
    rule_name: str


@dataclass
class CleanupResult:
    deleted_count: int
    freed_bytes: int
    candidates: list[CleanupCandidate]
    errors: list[str]


def get_storage_stats() -> StorageStats:
    """计算存储统计信息"""
    jobs_dir = local_jobs_dir()
    if not jobs_dir.exists():
        return StorageStats(
            total_bytes=0, used_bytes=0, free_bytes=0, job_count=0
        )

    total = 0
    used = 0
    job_count = 0
    by_model: dict[str, int] = defaultdict(int)
    by_status: dict[str, int] = defaultdict(int)
    job_sizes: list[tuple[str, int]] = []

    for job in list_all_jobs():
        job_dir = get_job_dir(job.job_id)
        if not job_dir.exists():
            continue
        size = _dir_size(job_dir)
        total += size
        job_count += 1
        by_model[job.model] += size
        by_status[job.status] += size
        job_sizes.append((job.job_id, size))

    # 取前 10 个最大的任务
    job_sizes.sort(key=lambda x: x[1], reverse=True)
    largest = job_sizes[:10]

    # 假设总配额为配置值，如果没有配置则默认 100GB
    config = load_config()
    quota = config.quota_bytes
    free = max(0, quota - total)

    return StorageStats(
        total_bytes=quota,
        used_bytes=total,
        free_bytes=free,
        job_count=job_count,
        by_model=dict(by_model),
        by_status=dict(by_status),
        largest_jobs=largest,
    )


def evaluate_cleanup_rules(config: StorageConfig | None = None) -> list[CleanupCandidate]:
    """根据清理规则评估可清理的任务"""
    if config is None:
        config = load_config()

    candidates: list[CleanupCandidate] = []
    now = datetime.now(timezone.utc)

    for job in list_all_jobs():
        # 跳过受保护的样例
        if job.sample_id and job.sample_id in config.protected_sample_ids:
            continue

        job_dir = get_job_dir(job.job_id)
        if not job_dir.exists():
            continue

        size = _dir_size(job_dir)
        if size == 0:
            continue

        # 按优先级评估规则
        for rule in sorted(config.rules, key=lambda r: r.priority):
            if not rule.enabled or not rule.condition:
                continue

            if _matches_rule(job, rule.condition, now):
                candidates.append(
                    CleanupCandidate(
                        job_id=job.job_id,
                        reason=_rule_description(rule),
                        size_bytes=size,
                        rule_name=rule.name,
                    )
                )
                break  # 一个任务只匹配一条规则

    return candidates


def execute_cleanup(
    candidates: list[CleanupCandidate], dry_run: bool = False, use_trash: bool = True
) -> CleanupResult:
    """执行清理操作"""
    deleted = 0
    freed = 0
    errors: list[str] = []

    if use_trash:
        _TRASH_DIR.mkdir(parents=True, exist_ok=True)

    for cand in candidates:
        job_dir = get_job_dir(cand.job_id)
        if not job_dir.exists():
            errors.append(f"任务目录不存在: {cand.job_id}")
            continue

        if dry_run:
            deleted += 1
            freed += cand.size_bytes
            continue

        try:
            if use_trash:
                # 移动到回收站而不是直接删除
                trash_path = _TRASH_DIR / cand.job_id
                if trash_path.exists():
                    shutil.rmtree(trash_path)
                shutil.move(str(job_dir), str(trash_path))
                # 记录删除日志
                _log_deletion(cand.job_id, cand.reason, cand.rule_name)
            else:
                shutil.rmtree(job_dir)
            deleted += 1
            freed += cand.size_bytes
        except Exception as e:
            errors.append(f"删除失败 {cand.job_id}: {e}")

    return CleanupResult(
        deleted_count=deleted,
        freed_bytes=freed,
        candidates=candidates,
        errors=errors,
    )


def auto_clean_if_needed() -> CleanupResult | None:
    """检查配额并在需要时触发自动清理"""
    config = load_config()
    if not config.auto_clean.enabled:
        return None

    stats = get_storage_stats()
    usage_percent = (stats.used_bytes / stats.total_bytes) * 100 if stats.total_bytes > 0 else 0

    if usage_percent < config.auto_clean.threshold_percent:
        return None

    candidates = evaluate_cleanup_rules(config)
    if not candidates:
        return None

    return execute_cleanup(candidates, dry_run=False)


def _dir_size(path: Path) -> int:
    """递归计算目录大小（字节）"""
    total = 0
    try:
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def _matches_rule(job, condition: CleanupCondition, now: datetime) -> bool:
    """判断任务是否匹配清理条件"""
    if condition.status_filter and job.status not in condition.status_filter:
        return False

    if condition.type == "age_days":
        created = datetime.fromisoformat(job.created_at).replace(tzinfo=timezone.utc)
        age = (now - created).days
        return age >= condition.value

    if condition.type == "score_below":
        # 需要加载评分数据
        from job_store import load_evaluation
        try:
            eval_data = load_evaluation(job.job_id)
            if not eval_data:
                return False
            # 计算平均分
            scores = [
                eval_data.get(k, 0)
                for k in (
                    "structure_completeness",
                    "trajectory_stability",
                    "noise",
                    "dynamic_handling",
                    "depth_continuity",
                    "presentation_usability",
                )
            ]
            avg = sum(scores) / len(scores) if scores else 0
            return avg < condition.value
        except Exception:
            return False

    if condition.type == "manual":
        return True

    return False


def _rule_description(rule: CleanupRule) -> str:
    """生成规则描述"""
    if not rule.condition:
        return "手动标记"
    cond = rule.condition
    if cond.type == "age_days":
        return f"超过 {cond.value} 天 ({', '.join(cond.status_filter)})"
    if cond.type == "score_below":
        return f"评分低于 {cond.value} ({', '.join(cond.status_filter)})"
    return "未知条件"


def format_bytes(bytes: int) -> str:
    """格式化字节数为人类可读格式"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} PB"


def _auto_clean_loop():
    """自动清理后台线程循环"""
    while not _auto_clean_stop_event.is_set():
        try:
            config = load_config()
            if config.auto_clean.enabled:
                result = auto_clean_if_needed()
                if result:
                    # 记录清理结果到日志
                    from logging_config import log
                    log.info(
                        f"自动清理完成：删除 {result.deleted_count} 个任务，释放 {format_bytes(result.freed_bytes)}"
                    )
        except Exception as e:
            from logging_config import log
            log.error(f"自动清理检查失败: {e}")

        # 等待下一个检查周期
        config = load_config()
        interval_hours = config.auto_clean.check_interval_hours
        _auto_clean_stop_event.wait(interval_hours * 3600)


def start_auto_clean():
    """启动自动清理后台线程"""
    global _auto_clean_thread
    if _auto_clean_thread is None or not _auto_clean_thread.is_alive():
        _auto_clean_stop_event.clear()
        _auto_clean_thread = threading.Thread(target=_auto_clean_loop, daemon=True, name="auto-clean")
        _auto_clean_thread.start()


def stop_auto_clean():
    """停止自动清理后台线程"""
    global _auto_clean_thread
    _auto_clean_stop_event.set()
    if _auto_clean_thread and _auto_clean_thread.is_alive():
        _auto_clean_thread.join(timeout=5)
    _auto_clean_thread = None


def _log_deletion(job_id: str, reason: str, rule_name: str) -> None:
    """记录删除日志"""
    log_file = _TRASH_DIR / "deletion_log.jsonl"
    entry = {
        "job_id": job_id,
        "deleted_at": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "rule_name": rule_name,
    }
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def list_trash_items() -> list[dict]:
    """列出回收站中的项目"""
    if not _TRASH_DIR.exists():
        return []
    items = []
    for item in _TRASH_DIR.iterdir():
        if item.is_dir() and item.name != "deletion_log.jsonl":
            size = _dir_size(item)
            items.append({
                "job_id": item.name,
                "size_bytes": size,
                "deleted_at": datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc).isoformat(),
            })
    return sorted(items, key=lambda x: x["deleted_at"], reverse=True)


def restore_from_trash(job_id: str) -> bool:
    """从回收站恢复任务"""
    trash_path = _TRASH_DIR / job_id
    if not trash_path.exists():
        return False
    target_path = get_job_dir(job_id)
    if target_path.exists():
        return False
    try:
        shutil.move(str(trash_path), str(target_path))
        return True
    except Exception:
        return False


def empty_trash() -> int:
    """清空回收站，返回删除的项目数"""
    if not _TRASH_DIR.exists():
        return 0
    count = 0
    for item in _TRASH_DIR.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
            count += 1
    log_file = _TRASH_DIR / "deletion_log.jsonl"
    if log_file.exists():
        log_file.unlink()
    return count
