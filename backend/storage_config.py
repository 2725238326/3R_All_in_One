"""存储配额与清理策略配置管理。

配置文件位置：``ROOT / "settings" / "storage_config.json"``

配置结构：
```json
{
  "quotaBytes": 107374182400,  // 100GB
  "rules": [
    {
      "name": "old_unfinished",
      "enabled": true,
      "priority": 1,
      "condition": {
        "type": "age_days",
        "value": 30,
        "status_filter": ["draft", "failed", "cancelled"]
      },
      "action": "delete"
    },
    {
      "name": "low_score_finished",
      "enabled": true,
      "priority": 2,
      "condition": {
        "type": "score_below",
        "value": 3,
        "status_filter": ["finished"]
      },
      "action": "delete"
    },
    {
      "name": "old_finished",
      "enabled": true,
      "priority": 3,
      "condition": {
        "type": "age_days",
        "value": 90,
        "status_filter": ["finished"]
      },
      "action": "delete"
    }
  ],
  "protectedSampleIds": ["sample_001", "sample_002"],  // 样例标记保护
  "autoClean": {
    "enabled": true,
    "checkIntervalHours": 24,
    "thresholdPercent": 85  // 使用率超过 85% 时触发自动清理
  }
}
```
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from runtime_paths import data_root

DEFAULT_QUOTA_BYTES = 100 * 1024 * 1024 * 1024  # 100GB


@dataclass
class CleanupCondition:
    type: Literal["age_days", "score_below", "manual"]
    value: int | float
    status_filter: list[str] = field(default_factory=list)


@dataclass
class CleanupRule:
    name: str
    enabled: bool = True
    priority: int = 1
    condition: CleanupCondition | None = None
    action: Literal["delete", "archive"] = "delete"


@dataclass
class AutoCleanConfig:
    enabled: bool = True
    check_interval_hours: int = 24
    threshold_percent: int = 85


@dataclass
class StorageConfig:
    quota_bytes: int = DEFAULT_QUOTA_BYTES
    rules: list[CleanupRule] = field(default_factory=list)
    protected_sample_ids: list[str] = field(default_factory=list)
    auto_clean: AutoCleanConfig = field(default_factory=AutoCleanConfig)

    def to_dict(self) -> dict:
        return {
            "quotaBytes": self.quota_bytes,
            "rules": [
                {
                    "name": r.name,
                    "enabled": r.enabled,
                    "priority": r.priority,
                    "condition": {
                        "type": r.condition.type,
                        "value": r.condition.value,
                        "statusFilter": r.condition.status_filter,
                    } if r.condition else None,
                    "action": r.action,
                }
                for r in self.rules
            ],
            "protectedSampleIds": self.protected_sample_ids,
            "autoClean": {
                "enabled": self.auto_clean.enabled,
                "checkIntervalHours": self.auto_clean.check_interval_hours,
                "thresholdPercent": self.auto_clean.threshold_percent,
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StorageConfig":
        rules = []
        for r_data in data.get("rules", []):
            cond_data = r_data.get("condition")
            condition = (
                CleanupCondition(
                    type=cond_data["type"],
                    value=cond_data["value"],
                    status_filter=cond_data.get("statusFilter", []),
                )
                if cond_data
                else None
            )
            rules.append(
                CleanupRule(
                    name=r_data["name"],
                    enabled=r_data.get("enabled", True),
                    priority=r_data.get("priority", 1),
                    condition=condition,
                    action=r_data.get("action", "delete"),
                )
            )
        auto_data = data.get("autoClean", {})
        return cls(
            quota_bytes=data.get("quotaBytes", DEFAULT_QUOTA_BYTES),
            rules=rules,
            protected_sample_ids=data.get("protectedSampleIds", []),
            auto_clean=AutoCleanConfig(
                enabled=auto_data.get("enabled", True),
                check_interval_hours=auto_data.get("checkIntervalHours", 24),
                threshold_percent=auto_data.get("thresholdPercent", 85),
            ),
        )


def get_default_rules() -> list[CleanupRule]:
    """默认清理规则：优先级从高到低"""
    return [
        CleanupRule(
            name="old_unfinished",
            enabled=True,
            priority=1,
            condition=CleanupCondition(
                type="age_days", value=30, status_filter=["draft", "failed", "cancelled"]
            ),
            action="delete",
        ),
        CleanupRule(
            name="low_score_finished",
            enabled=True,
            priority=2,
            condition=CleanupCondition(
                type="score_below", value=3, status_filter=["finished"]
            ),
            action="delete",
        ),
        CleanupRule(
            name="old_finished",
            enabled=True,
            priority=3,
            condition=CleanupCondition(
                type="age_days", value=90, status_filter=["finished"]
            ),
            action="delete",
        ),
    ]


def get_config_path() -> Path:
    """配置文件路径"""
    return data_root() / "settings" / "storage_config.json"


def load_config() -> StorageConfig:
    """加载配置，不存在则返回默认配置"""
    path = get_config_path()
    if not path.exists():
        return StorageConfig(rules=get_default_rules())
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return StorageConfig.from_dict(data)
    except Exception:
        # 配置损坏时返回默认配置
        return StorageConfig(rules=get_default_rules())


def save_config(config: StorageConfig) -> None:
    """保存配置"""
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
