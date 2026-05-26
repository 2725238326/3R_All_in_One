// ═══════════════════════════════════════════════════════════════
// RunnerSelector — 执行器选择组件
// ═══════════════════════════════════════════════════════════════
import { useState, useEffect } from "react";

export type RunnerType = "ssh" | "docker" | "online_api";

export interface RunnerOption {
  type: RunnerType;
  label: string;
  description: string;
  available: boolean;
  icon: string;
  requirements?: string[];
}

interface RunnerSelectorProps {
  value: RunnerType;
  onChange: (runner: RunnerType) => void;
  disabled?: boolean;
  compact?: boolean;
}

const RUNNER_OPTIONS: RunnerOption[] = [
  {
    type: "ssh",
    label: "SSH 远程服务器",
    description: "通过 SSH 连接到远程 GPU 服务器执行",
    available: true,
    icon: "🖥️",
    requirements: ["SSH 服务器配置", "远程 GPU"],
  },
  {
    type: "online_api",
    label: "在线 API",
    description: "使用 HuggingFace / Replicate 等在线服务，无需自备 GPU",
    available: false,
    icon: "☁️",
    requirements: ["HF_TOKEN 或 REPLICATE_API_TOKEN"],
  },
];

export function RunnerSelector({
  value,
  onChange,
  disabled = false,
  compact = false,
}: RunnerSelectorProps) {
  const [options, setOptions] = useState<RunnerOption[]>(RUNNER_OPTIONS);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // 检查各执行器可用性
    checkRunnerAvailability().then((availability) => {
      setOptions((prev) =>
        prev.map((opt) => ({
          ...opt,
          available: availability[opt.type] ?? opt.available,
        }))
      );
      setLoading(false);
    });
  }, []);

  if (compact) {
    return (
      <select
        className="runner-select"
        value={value}
        onChange={(e) => onChange(e.target.value as RunnerType)}
        disabled={disabled || loading}
      >
        {options.map((opt) => (
          <option key={opt.type} value={opt.type} disabled={!opt.available}>
            {opt.icon} {opt.label} {!opt.available && "(不可用)"}
          </option>
        ))}
      </select>
    );
  }

  return (
    <div className="runner-selector">
      <div className="runner-options">
        {options.map((opt) => (
          <button
            key={opt.type}
            type="button"
            className={`runner-option ${value === opt.type ? "selected" : ""} ${
              !opt.available ? "unavailable" : ""
            }`}
            onClick={() => opt.available && onChange(opt.type)}
            disabled={disabled || !opt.available || loading}
          >
            <span className="runner-icon">{opt.icon}</span>
            <div className="runner-info">
              <strong>{opt.label}</strong>
              <p>{opt.description}</p>
              {!opt.available && opt.requirements && (
                <span className="runner-requirements">
                  需要: {opt.requirements.join(", ")}
                </span>
              )}
            </div>
            {value === opt.type && <span className="runner-check">✓</span>}
          </button>
        ))}
      </div>
      {loading && <div className="runner-loading">检查执行器可用性...</div>}
    </div>
  );
}

async function checkRunnerAvailability(): Promise<Record<RunnerType, boolean>> {
  try {
    const response = await fetch("/api/runners/availability");
    if (response.ok) {
      return await response.json();
    }
  } catch (e) {
    console.warn("Failed to check runner availability:", e);
  }
  // 默认只有 SSH 可用
  return {
    ssh: true,
    docker: false,
    online_api: false,
  };
}

// 导出工具函数
export function getRunnerLabel(type: RunnerType): string {
  const opt = RUNNER_OPTIONS.find((o) => o.type === type);
  return opt?.label ?? type;
}

export function getRunnerIcon(type: RunnerType): string {
  const opt = RUNNER_OPTIONS.find((o) => o.type === type);
  return opt?.icon ?? "⚙️";
}
