/**
 * DashboardPanel - 自定义仪表板组件
 * 展示系统概览、任务统计、资源使用等可视化数据
 */
import { useEffect, useState } from "react";
import { API_BASE } from "./appConfig";

interface DashboardStats {
  totalJobs: number;
  runningJobs: number;
  finishedJobs: number;
  failedJobs: number;
  totalStorage: number;
  usedStorage: number;
  modelUsage: Record<string, number>;
}

export function DashboardPanel() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboardStats();
  }, []);

  async function loadDashboardStats() {
    try {
      const res = await fetch(`${API_BASE}/api/jobs`);
      const data = await res.json();
      const jobs = data.jobs || [];
      
      const storageRes = await fetch(`${API_BASE}/api/storage/stats`);
      const storageData = await storageRes.json();
      
      const modelUsage: Record<string, number> = {};
      jobs.forEach((job: any) => {
        const model = job.job.model;
        modelUsage[model] = (modelUsage[model] || 0) + 1;
      });

      setStats({
        totalJobs: jobs.length,
        runningJobs: jobs.filter((j: any) => j.job.status === "running").length,
        finishedJobs: jobs.filter((j: any) => j.job.status === "finished").length,
        failedJobs: jobs.filter((j: any) => j.job.status === "failed").length,
        totalStorage: storageData.quotaBytes || 0,
        usedStorage: storageData.usedBytes || 0,
        modelUsage,
      });
    } catch (e) {
      console.error("加载仪表板数据失败", e);
    } finally {
      setLoading(false);
    }
  }

  function formatBytes(bytes: number): string {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round((bytes / Math.pow(k, i)) * 100) / 100 + " " + sizes[i];
  }

  function formatPercentage(value: number, total: number): string {
    if (total === 0) return "0%";
    return Math.round((value / total) * 100) + "%";
  }

  if (loading) {
    return <div className="loading">加载中...</div>;
  }

  if (!stats) {
    return <div className="error">加载数据失败</div>;
  }

  const storagePercentage = stats.totalStorage > 0 
    ? (stats.usedStorage / stats.totalStorage) * 100 
    : 0;

  return (
    <div className="dashboard-panel">
      <h2>仪表板</h2>
      
      {/* 任务统计卡片 */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">总任务数</div>
          <div className="stat-value">{stats.totalJobs}</div>
        </div>
        <div className="stat-card running">
          <div className="stat-label">运行中</div>
          <div className="stat-value">{stats.runningJobs}</div>
        </div>
        <div className="stat-card finished">
          <div className="stat-label">已完成</div>
          <div className="stat-value">{stats.finishedJobs}</div>
        </div>
        <div className="stat-card failed">
          <div className="stat-label">失败</div>
          <div className="stat-value">{stats.failedJobs}</div>
        </div>
      </div>

      {/* 存储使用情况 */}
      <div className="storage-section">
        <h3>存储使用</h3>
        <div className="storage-bar">
          <div 
            className="storage-fill" 
            style={{ width: `${Math.min(storagePercentage, 100)}%` }}
          />
        </div>
        <div className="storage-info">
          <span>{formatBytes(stats.usedStorage)} / {formatBytes(stats.totalStorage)}</span>
          <span>{formatPercentage(stats.usedStorage, stats.totalStorage)}</span>
        </div>
      </div>

      {/* 模型使用分布 */}
      <div className="model-usage-section">
        <h3>模型使用分布</h3>
        <div className="model-bars">
          {Object.entries(stats.modelUsage).map(([model, count]) => (
            <div key={model} className="model-bar-item">
              <div className="model-label">{model}</div>
              <div className="model-bar">
                <div 
                  className="model-bar-fill" 
                  style={{ width: `${formatPercentage(count, stats.totalJobs)}` }}
                />
              </div>
              <div className="model-count">{count}</div>
            </div>
          ))}
        </div>
      </div>

      {/* 快捷操作 */}
      <div className="quick-actions">
        <h3>快捷操作</h3>
        <div className="action-buttons">
          <button className="action-button">创建新任务</button>
          <button className="action-button">查看所有任务</button>
          <button className="action-button">系统设置</button>
          <button className="action-button">存储管理</button>
        </div>
      </div>
    </div>
  );
}
