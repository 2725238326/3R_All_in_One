// ═══════════════════════════════════════════════════════════════
// StoragePanel — 存储配额管理与清理规则配置
//   显示存储使用情况、配额设置、清理规则，支持手动触发清理
// ═══════════════════════════════════════════════════════════════
import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "./appConfig";
import type { StorageStats, StorageConfig, CleanupResult } from "./types";

export function StoragePanel() {
  const [stats, setStats] = useState<StorageStats | null>(null);
  const [config, setConfig] = useState<StorageConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [dryRunResult, setDryRunResult] = useState<CleanupResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [trashItems, setTrashItems] = useState<any[]>([]);
  const [showTrash, setShowTrash] = useState(false);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/storage/stats`);
      if (!res.ok) throw new Error("获取存储统计失败");
      const data = await res.json();
      setStats(data);
    } catch (e: any) {
      setError(e?.message || "获取存储统计失败");
    }
  }, []);

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/storage/config`);
      if (!res.ok) throw new Error("获取配置失败");
      const data = await res.json();
      setConfig(data);
    } catch (e: any) {
      setError(e?.message || "获取配置失败");
    }
  }, []);

  const fetchTrash = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/storage/trash`);
      if (!res.ok) throw new Error("获取回收站失败");
      const data = await res.json();
      setTrashItems(data.items || []);
    } catch (e: any) {
      setError(e?.message || "获取回收站失败");
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchStats(), fetchConfig()]).finally(() => setLoading(false));
  }, [fetchStats, fetchConfig]);

  useEffect(() => {
    if (showTrash) {
      fetchTrash();
    }
  }, [showTrash, fetchTrash]);

  async function handleSaveConfig() {
    if (!config) return;
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/storage/config`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!res.ok) throw new Error("保存配置失败");
      await fetchConfig();
    } catch (e: any) {
      setError(e?.message || "保存配置失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleDryRun() {
    setCleaning(true);
    setError(null);
    setDryRunResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/storage/clean?dry_run=true`, { method: "POST" });
      if (!res.ok) throw new Error("执行清理失败");
      const data = await res.json();
      setDryRunResult(data);
    } catch (e: any) {
      setError(e?.message || "执行清理失败");
    } finally {
      setCleaning(false);
    }
  }

  async function handleExecuteClean() {
    if (!dryRunResult || dryRunResult.candidates.length === 0) return;
    if (!confirm(`确认删除 ${dryRunResult.candidates.length} 个任务？此操作不可撤销。`)) return;
    setCleaning(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/storage/clean?dry_run=false`, { method: "POST" });
      if (!res.ok) throw new Error("执行清理失败");
      const data = await res.json();
      setDryRunResult(data);
      await fetchStats();
    } catch (e: any) {
      setError(e?.message || "执行清理失败");
    } finally {
      setCleaning(false);
    }
  }

  async function handleRestoreItem(jobId: string) {
    try {
      const res = await fetch(`${API_BASE}/api/storage/trash/${jobId}/restore`, { method: "POST" });
      if (!res.ok) throw new Error("恢复失败");
      await fetchTrash();
      await fetchStats();
    } catch (e: any) {
      setError(e?.message || "恢复失败");
    }
  }

  async function handleEmptyTrash() {
    if (!confirm("确认清空回收站？此操作不可撤销。")) return;
    try {
      const res = await fetch(`${API_BASE}/api/storage/trash/empty`, { method: "POST" });
      if (!res.ok) throw new Error("清空失败");
      await fetchTrash();
      await fetchStats();
    } catch (e: any) {
      setError(e?.message || "清空失败");
    }
  }

  function formatBytes(bytes: number): string {
    for (const unit of ["B", "KB", "MB", "GB", "TB"]) {
      if (bytes < 1024) return `${bytes.toFixed(1)} ${unit}`;
      bytes /= 1024;
    }
    return `${bytes.toFixed(1)} PB`;
  }

  if (loading) return <div className="dense-text">加载中...</div>;

  if (!stats || !config) return <div className="dense-text">数据加载失败</div>;

  const usagePercent = stats.usagePercent;
  const isWarning = usagePercent >= 80;
  const isCritical = usagePercent >= 95;

  return (
    <div className="storage-panel" style={{ padding: "16px" }}>
      {error && (
        <div className="overview-callout danger" style={{ marginBottom: "12px", padding: "8px" }}>
          <strong>错误：</strong> {error}
        </div>
      )}

      {/* 存储使用概览 */}
      <section style={{ marginBottom: "24px" }}>
        <h3 style={{ margin: "0 0 12px", fontSize: "16px" }}>存储使用概览</h3>
        <div style={{
          background: isCritical ? "#fee2e2" : isWarning ? "#fef3c7" : "#d1fae5",
          padding: "16px",
          borderRadius: "8px",
          marginBottom: "12px",
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
            <strong style={{ fontSize: "18px" }}>{usagePercent.toFixed(1)}%</strong>
            <span className="dense-text" style={{ fontSize: "12px" }}>
              {formatBytes(stats.usedBytes)} / {formatBytes(stats.totalBytes)}
            </span>
          </div>
          <div style={{
            height: "8px",
            background: "rgba(0,0,0,0.1)",
            borderRadius: "4px",
            overflow: "hidden",
          }}>
            <div style={{
              height: "100%",
              width: `${usagePercent}%`,
              background: isCritical ? "#ef4444" : isWarning ? "#f59e0b" : "#10b981",
              transition: "width 0.3s",
            }} />
          </div>
          <p className="dense-text" style={{ margin: "8px 0 0", fontSize: "12px" }}>
            {isCritical ? "存储空间严重不足，请立即清理" : isWarning ? "存储空间紧张，建议清理" : "存储空间充足"}
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "12px" }}>
          <div style={{ background: "var(--surface-soft, #fafafa)", padding: "12px", borderRadius: "8px" }}>
            <div className="dense-text" style={{ fontSize: "12px", color: "var(--text-soft, #6b7280)" }}>任务总数</div>
            <div style={{ fontSize: "20px", fontWeight: 600 }}>{stats.jobCount}</div>
          </div>
          <div style={{ background: "var(--surface-soft, #fafafa)", padding: "12px", borderRadius: "8px" }}>
            <div className="dense-text" style={{ fontSize: "12px", color: "var(--text-soft, #6b7280)" }}>可用空间</div>
            <div style={{ fontSize: "20px", fontWeight: 600 }}>{formatBytes(stats.freeBytes)}</div>
          </div>
        </div>
      </section>

      {/* 配额设置 */}
      <section style={{ marginBottom: "24px" }}>
        <h3 style={{ margin: "0 0 12px", fontSize: "16px" }}>配额设置</h3>
        <div style={{ background: "var(--surface-soft, #fafafa)", padding: "16px", borderRadius: "8px" }}>
          <label className="dense-text" style={{ display: "block", marginBottom: "8px", fontSize: "13px" }}>
            全局配额（GB）
          </label>
          <input
            type="number"
            value={(config.quotaBytes / (1024 ** 3)).toFixed(0)}
            onChange={(e) => {
              const gb = parseInt(e.target.value) || 100;
              setConfig({ ...config, quotaBytes: gb * 1024 ** 3 });
            }}
            style={{ width: "120px", padding: "6px", borderRadius: "4px", border: "1px solid var(--border-soft, #e5e7eb)" }}
          />
          <button
            className="primary-button small"
            onClick={handleSaveConfig}
            disabled={saving}
            style={{ marginLeft: "8px" }}
          >
            {saving ? "保存中..." : "保存"}
          </button>
        </div>
      </section>

      {/* 清理规则 */}
      <section style={{ marginBottom: "24px" }}>
        <h3 style={{ margin: "0 0 12px", fontSize: "16px" }}>清理规则</h3>
        <div style={{ background: "var(--surface-soft, #fafafa)", padding: "16px", borderRadius: "8px" }}>
          {config.rules.map((rule, idx) => (
            <div key={rule.name} style={{
              padding: "12px",
              background: "white",
              borderRadius: "6px",
              marginBottom: "8px",
              border: "1px solid var(--border-soft, #e5e7eb)",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "8px" }}>
                <strong style={{ fontSize: "14px" }}>{rule.name}</strong>
                <label style={{ fontSize: "12px", display: "flex", alignItems: "center", gap: "4px" }}>
                  <input
                    type="checkbox"
                    checked={rule.enabled}
                    onChange={(e) => {
                      const newRules = [...config.rules];
                      newRules[idx] = { ...rule, enabled: e.target.checked };
                      setConfig({ ...config, rules: newRules });
                    }}
                  />
                  启用
                </label>
              </div>
              {rule.condition && (
                <p className="dense-text" style={{ margin: "0", fontSize: "12px", color: "var(--text-soft, #6b7280)" }}>
                  {rule.condition.type === "age_days" && `超过 ${rule.condition.value} 天 (${rule.condition.statusFilter.join(", ")})`}
                  {rule.condition.type === "score_below" && `评分低于 ${rule.condition.value} (${rule.condition.statusFilter.join(", ")})`}
                </p>
              )}
            </div>
          ))}
          <button
            className="primary-button small"
            onClick={handleSaveConfig}
            disabled={saving}
            style={{ marginTop: "8px" }}
          >
            {saving ? "保存中..." : "保存规则"}
          </button>
        </div>
      </section>

      {/* 自动清理 */}
      <section style={{ marginBottom: "24px" }}>
        <h3 style={{ margin: "0 0 12px", fontSize: "16px" }}>自动清理</h3>
        <div style={{ background: "var(--surface-soft, #fafafa)", padding: "16px", borderRadius: "8px" }}>
          <label style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px" }}>
            <input
              type="checkbox"
              checked={config.autoClean.enabled}
              onChange={(e) => {
                setConfig({
                  ...config,
                  autoClean: { ...config.autoClean, enabled: e.target.checked },
                });
              }}
            />
            <span className="dense-text" style={{ fontSize: "13px" }}>启用自动清理</span>
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: "12px" }}>
            <div>
              <label className="dense-text" style={{ display: "block", marginBottom: "4px", fontSize: "12px" }}>
                检查间隔（小时）
              </label>
              <input
                type="number"
                value={config.autoClean.checkIntervalHours}
                onChange={(e) => {
                  setConfig({
                    ...config,
                    autoClean: { ...config.autoClean, checkIntervalHours: parseInt(e.target.value) || 24 },
                  });
                }}
                style={{ width: "100%", padding: "6px", borderRadius: "4px", border: "1px solid var(--border-soft, #e5e7eb)" }}
              />
            </div>
            <div>
              <label className="dense-text" style={{ display: "block", marginBottom: "4px", fontSize: "12px" }}>
                触发阈值（%）
              </label>
              <input
                type="number"
                value={config.autoClean.thresholdPercent}
                onChange={(e) => {
                  setConfig({
                    ...config,
                    autoClean: { ...config.autoClean, thresholdPercent: parseInt(e.target.value) || 85 },
                  });
                }}
                style={{ width: "100%", padding: "6px", borderRadius: "4px", border: "1px solid var(--border-soft, #e5e7eb)" }}
              />
            </div>
          </div>
          <button
            className="primary-button small"
            onClick={handleSaveConfig}
            disabled={saving}
            style={{ marginTop: "12px" }}
          >
            {saving ? "保存中..." : "保存"}
          </button>
        </div>
      </section>

      {/* 手动清理 */}
      <section>
        <h3 style={{ margin: "0 0 12px", fontSize: "16px" }}>手动清理</h3>
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            className="primary-button small"
            onClick={handleDryRun}
            disabled={cleaning}
          >
            {cleaning ? "评估中..." : "评估可清理任务"}
          </button>
          {dryRunResult && dryRunResult.candidates.length > 0 && (
            <button
              className="ghost-button small"
              onClick={handleExecuteClean}
              disabled={cleaning}
              style={{ borderColor: "#ef4444", color: "#ef4444" }}
            >
              {cleaning ? "清理中..." : `执行清理 (${dryRunResult.candidates.length} 个)`}
            </button>
          )}
        </div>

        {dryRunResult && (
          <div style={{ marginTop: "12px" }}>
            <p className="dense-text" style={{ margin: "0 0 8px", fontSize: "13px" }}>
              {dryRunResult.dryRun ? "评估结果（预览）" : "清理结果"}
            </p>
            {dryRunResult.candidates.length === 0 ? (
              <p className="dense-text" style={{ color: "var(--text-soft, #6b7280)" }}>没有匹配的任务</p>
            ) : (
              <div style={{
                maxHeight: "200px",
                overflowY: "auto",
                background: "var(--surface-soft, #fafafa)",
                borderRadius: "6px",
                border: "1px solid var(--border-soft, #e5e7eb)",
              }}>
                {dryRunResult.candidates.map((cand) => (
                  <div key={cand.jobId} style={{
                    padding: "8px",
                    borderBottom: "1px solid var(--border-soft, #e5e7eb)",
                    fontSize: "12px",
                  }}>
                    <div style={{ display: "flex", justifyContent: "space-between" }}>
                      <strong>{cand.jobId}</strong>
                      <span>{formatBytes(cand.sizeBytes)}</span>
                    </div>
                    <p className="dense-text" style={{ margin: "4px 0 0", color: "var(--text-soft, #6b7280)" }}>
                      {cand.reason} · {cand.ruleName}
                    </p>
                  </div>
                ))}
              </div>
            )}
            {dryRunResult.errors.length > 0 && (
              <div className="overview-callout danger" style={{ marginTop: "8px", padding: "8px", fontSize: "12px" }}>
                <strong>错误：</strong>
                {dryRunResult.errors.map((e, i) => <div key={i}>{e}</div>)}
              </div>
            )}
          </div>
        )}
      </section>

      {/* 回收站 */}
      <section>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <h3 style={{ margin: 0, fontSize: "16px" }}>回收站</h3>
          <button
            className="ghost-button small"
            onClick={() => setShowTrash(!showTrash)}
          >
            {showTrash ? "隐藏" : "显示"}
          </button>
        </div>

        {showTrash && (
          <>
            {trashItems.length === 0 ? (
              <p className="dense-text" style={{ color: "var(--text-soft, #6b7280)" }}>回收站为空</p>
            ) : (
              <>
                <div style={{
                  maxHeight: "200px",
                  overflowY: "auto",
                  background: "var(--surface-soft, #fafafa)",
                  borderRadius: "6px",
                  border: "1px solid var(--border-soft, #e5e7eb)",
                  marginBottom: "8px",
                }}>
                  {trashItems.map((item) => (
                    <div key={item.jobId} style={{
                      padding: "8px",
                      borderBottom: "1px solid var(--border-soft, #e5e7eb)",
                      fontSize: "12px",
                    }}>
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <strong>{item.jobId}</strong>
                        <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                          <span>{formatBytes(item.sizeBytes)}</span>
                          <button
                            className="ghost-button small"
                            onClick={() => handleRestoreItem(item.jobId)}
                            style={{ padding: "2px 6px", fontSize: "11px" }}
                          >
                            恢复
                          </button>
                        </div>
                      </div>
                      <p className="dense-text" style={{ margin: "4px 0 0", color: "var(--text-soft, #6b7280)" }}>
                        删除于 {new Date(item.deleted_at).toLocaleString()}
                      </p>
                    </div>
                  ))}
                </div>
                <button
                  className="ghost-button small"
                  onClick={handleEmptyTrash}
                  style={{ borderColor: "#ef4444", color: "#ef4444" }}
                >
                  清空回收站
                </button>
              </>
            )}
          </>
        )}
      </section>
    </div>
  );
}
