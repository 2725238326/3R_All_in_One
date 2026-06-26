// ═══════════════════════════════════════════════════════════════
// ViserPanel — 启动远端 viser 4D 可视化（MonST3R 等动态重建）
//   通过 SSH 端口转发把远端 viser web 服务器映射到本地，浏览器
//   打开后能像视频一样拖动时间轴查看每帧的 3D 几何。
// ═══════════════════════════════════════════════════════════════
import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "./appConfig";

type ViserStatus = "idle" | "starting" | "ready" | "failed" | "stopped";

interface ViserSessionPayload {
  jobId: string;
  status: ViserStatus;
  url: string | null;
  pid?: number;
  localPort?: number;
  remotePort?: number;
  remoteDataDir?: string;
  startedAt?: number;
  uptimeSeconds?: number;
  lastError?: string | null;
}

interface ViserPanelProps {
  jobId: string;
}

export function ViserPanel({ jobId }: ViserPanelProps) {
  const [session, setSession] = useState<ViserSessionPayload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const autoOpenedRef = useRef<string | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/jobs/${jobId}/viser/status`);
      if (!res.ok) return;
      const data = (await res.json()) as ViserSessionPayload;
      setSession(data);
      // 启动 ready 时自动开新标签页
      if (data.status === "ready" && data.url && autoOpenedRef.current !== data.url) {
        autoOpenedRef.current = data.url;
        window.open(data.url, "_blank", "noopener,noreferrer");
      }
    } catch (e) {
      // 忽略瞬时网络错误
    }
  }, [jobId]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // 当处于 starting/ready 状态时定时轮询
  useEffect(() => {
    const status = session?.status ?? "idle";
    if (status !== "starting" && status !== "ready") return;
    const id = window.setInterval(fetchStatus, status === "starting" ? 1500 : 5000);
    return () => window.clearInterval(id);
  }, [session?.status, fetchStatus]);

  async function handleStart() {
    setBusy(true);
    setError(null);
    autoOpenedRef.current = null;
    try {
      const res = await fetch(`${API_BASE}/api/jobs/${jobId}/viser/start`, { method: "POST" });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data?.detail || "启动失败");
      }
      setSession(data as ViserSessionPayload);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  async function handleStop() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/jobs/${jobId}/viser/stop`, { method: "POST" });
      const data = await res.json();
      setSession(data as ViserSessionPayload);
      autoOpenedRef.current = null;
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setBusy(false);
    }
  }

  const status: ViserStatus = (session?.status as ViserStatus) || "idle";
  const url = session?.url || null;
  const dependencyHint = session?.lastError?.includes("No module named 'tyro'")
    ? "远端 MonST3R 可视化环境缺少 tyro 依赖。主任务结果不受影响；需要使用 4D viewer 时，在远端环境补装后再启动。"
    : null;

  return (
    <div className="viser-panel">
      <div className="viser-panel-head">
        <div>
          <strong>4D 时序可视化（可选）</strong>
          <p className="dense-text">
            MonST3R 的动态点云预览需要远端启动 viser 服务，再通过 SSH 隧道映射到本地。它只影响交互预览，不影响任务输出和日志检查。
          </p>
        </div>
        <ViserStatusPill status={status} />
      </div>

      {error && (
        <div className="overview-callout danger" style={{ marginBottom: "8px", padding: "8px", fontSize: "12px" }}>
          <strong>失败：</strong> {error}
        </div>
      )}

      {status === "failed" && (
        <div className="viser-note">
          <strong>可视化服务没有启动成功</strong>
          <p>{dependencyHint || "通常是远端 viewer 依赖、端口或 conda 环境问题。主任务结果已经保存在任务输出中，可以先查看产物和日志。"}</p>
          {session?.lastError && (
            <details>
              <summary>查看远端启动日志</summary>
              <pre>{session.lastError}</pre>
            </details>
          )}
        </div>
      )}

      <div className="viser-actions">
        {(status === "idle" || status === "stopped" || status === "failed") && (
          <button
            type="button"
            className="primary-button small"
            disabled={busy}
            onClick={handleStart}
          >
            {busy ? "启动中..." : "启动可选预览"}
          </button>
        )}

        {status === "starting" && (
          <button type="button" className="ghost-button small" disabled>
            启动中（首次需加载远端 conda 环境，可能 30~60 秒）...
          </button>
        )}

        {status === "ready" && url && (
          <>
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="primary-button small"
              style={{ textDecoration: "none" }}
            >
              在浏览器打开 ({url})
            </a>
            <button
              type="button"
              className="ghost-button small"
              disabled={busy}
              onClick={handleStop}
            >
              停止
            </button>
          </>
        )}

        {status === "starting" && (
          <button type="button" className="ghost-button small" disabled={busy} onClick={handleStop}>
            取消启动
          </button>
        )}
      </div>

      {session && (status === "ready" || status === "starting") && (
        <p className="dense-text viser-session-meta">
          PID {session.pid} · 本地端口 {session.localPort} · 远端 {session.remoteDataDir}
        </p>
      )}
    </div>
  );
}

function ViserStatusPill({ status }: { status: ViserStatus }) {
  const config: Record<ViserStatus, { label: string; bg: string; color: string }> = {
    idle: { label: "未启动", bg: "#f3f4f6", color: "#6b7280" },
    starting: { label: "启动中", bg: "#fef3c7", color: "#92400e" },
    ready: { label: "就绪", bg: "#d1fae5", color: "#065f46" },
    failed: { label: "预览不可用", bg: "#fee2e2", color: "#991b1b" },
    stopped: { label: "已停止", bg: "#e5e7eb", color: "#374151" },
  };
  const c = config[status] || config.idle;
  return (
    <span style={{
      background: c.bg,
      color: c.color,
      padding: "2px 8px",
      borderRadius: "10px",
      fontSize: "11px",
      fontWeight: 500,
    }}>
      {c.label}
    </span>
  );
}
