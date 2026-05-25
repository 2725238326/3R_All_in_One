import { useEffect, useState } from "react";
import type { SystemResources, SchedulerStatus } from "./types";
import { API_BASE } from "./appConfig";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`Failed to fetch ${path}`);
  return res.json();
}

function ProgressBar({ value, max, color = "var(--accent)" }: { value: number; max: number; color?: string }) {
  const percent = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div className="progress-bar-container">
      <div className="progress-bar-fill" style={{ width: `${percent}%`, backgroundColor: color }} />
    </div>
  );
}

function formatBytes(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb.toFixed(0)} MB`;
}

export function ResourceMonitor() {
  const [resources, setResources] = useState<SystemResources | null>(null);
  const [scheduler, setScheduler] = useState<SchedulerStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    async function poll() {
      try {
        const [res, sched] = await Promise.all([
          fetchJson<SystemResources>("/api/system/resources"),
          fetchJson<SchedulerStatus>("/api/scheduler/status"),
        ]);
        if (mounted) {
          setResources(res);
          setScheduler(sched);
          setError(null);
        }
      } catch (e) {
        if (mounted) setError("无法获取资源状态");
      }
    }

    poll();
    const interval = setInterval(poll, 5000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, []);

  if (error) {
    return <div className="resource-monitor-error">{error}</div>;
  }

  if (!resources) {
    return <div className="resource-monitor-loading">加载中...</div>;
  }

  const cpuColor = resources.cpu_percent > 80 ? "#dc2626" : resources.cpu_percent > 50 ? "#d97706" : "#059669";
  const memColor = resources.memory.used_percent > 80 ? "#dc2626" : resources.memory.used_percent > 50 ? "#d97706" : "#059669";
  const diskColor = resources.disk.used_percent > 90 ? "#dc2626" : resources.disk.used_percent > 70 ? "#d97706" : "#059669";

  return (
    <div className="resource-monitor">
      <div className="section-card">
        <div className="section-card-header">
          <h3 className="section-card-title">系统资源</h3>
          <span className="section-card-badge success">实时</span>
        </div>

        <div className="resource-grid">
          <div className="resource-item">
            <div className="resource-label">CPU</div>
            <ProgressBar value={resources.cpu_percent} max={100} color={cpuColor} />
            <div className="resource-value">{resources.cpu_percent.toFixed(1)}%</div>
          </div>

          <div className="resource-item">
            <div className="resource-label">内存</div>
            <ProgressBar value={resources.memory.used_mb} max={resources.memory.total_mb} color={memColor} />
            <div className="resource-value">
              {formatBytes(resources.memory.used_mb)} / {formatBytes(resources.memory.total_mb)}
            </div>
          </div>

          <div className="resource-item">
            <div className="resource-label">磁盘</div>
            <ProgressBar value={resources.disk.used_gb} max={resources.disk.total_gb} color={diskColor} />
            <div className="resource-value">
              {resources.disk.used_gb.toFixed(1)} GB / {resources.disk.total_gb.toFixed(1)} GB
            </div>
          </div>
        </div>

        {resources.gpus.length > 0 && (
          <div className="gpu-section">
            <div className="resource-label" style={{ marginTop: "12px", marginBottom: "8px" }}>GPU</div>
            {resources.gpus.map((gpu) => {
              const gpuMemColor = gpu.memory_used_percent > 80 ? "#dc2626" : gpu.memory_used_percent > 50 ? "#d97706" : "#059669";
              return (
                <div key={gpu.index} className="gpu-item">
                  <div className="gpu-name">{gpu.name}</div>
                  <div className="gpu-stats">
                    <span>显存: {formatBytes(gpu.memory_used_mb)} / {formatBytes(gpu.memory_total_mb)}</span>
                    <span>利用率: {gpu.utilization_percent}%</span>
                    {gpu.temperature_c && <span>温度: {gpu.temperature_c}°C</span>}
                  </div>
                  <ProgressBar value={gpu.memory_used_mb} max={gpu.memory_total_mb} color={gpuMemColor} />
                </div>
              );
            })}
          </div>
        )}
      </div>

      {scheduler && (
        <div className="section-card" style={{ marginTop: "16px" }}>
          <div className="section-card-header">
            <h3 className="section-card-title">任务调度器</h3>
            <span className={`section-card-badge ${scheduler.running ? "success" : ""}`}>
              {scheduler.running ? "运行中" : "已停止"}
            </span>
          </div>

          <div className="kv-row">
            <span className="kv-label">并发限制</span>
            <span className="kv-value">{scheduler.max_concurrent}</span>
          </div>
          <div className="kv-row">
            <span className="kv-label">队列长度</span>
            <span className="kv-value">{scheduler.queue_length}</span>
          </div>
          <div className="kv-row">
            <span className="kv-label">运行中</span>
            <span className="kv-value">{scheduler.running_count}</span>
          </div>

          {scheduler.running_jobs.length > 0 && (
            <div className="scheduler-jobs">
              <div className="resource-label" style={{ marginTop: "12px" }}>正在运行</div>
              {scheduler.running_jobs.map((job) => (
                <div key={job.job_id} className="scheduler-job-item">
                  <span className="job-id">{job.job_id.slice(0, 8)}</span>
                  <span className={`job-priority ${job.priority}`}>{job.priority}</span>
                </div>
              ))}
            </div>
          )}

          {scheduler.queued_jobs.length > 0 && (
            <div className="scheduler-jobs">
              <div className="resource-label" style={{ marginTop: "12px" }}>等待队列</div>
              {scheduler.queued_jobs.slice(0, 5).map((job) => (
                <div key={job.job_id} className="scheduler-job-item">
                  <span className="job-id">{job.job_id.slice(0, 8)}</span>
                  <span className={`job-priority ${job.priority}`}>{job.priority}</span>
                  {job.retry_count > 0 && <span className="retry-badge">重试 {job.retry_count}</span>}
                </div>
              ))}
              {scheduler.queued_jobs.length > 5 && (
                <div className="more-jobs">...还有 {scheduler.queued_jobs.length - 5} 个任务</div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ResourceMonitor;
