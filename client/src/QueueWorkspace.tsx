import { useEffect, useMemo, useState } from "react";
import { canDispatchJobStatus, JobListItem, matchesJobQuery } from "./workflowHelpers";
import { formatDateTime, modelDisplayName, sourceTypeLabel, statusLabel } from "./displayHelpers";
import { StatusBadge } from "./uiPrimitives";
import { ModelCatalogItem } from "./types";
import {
  Play,
  Clock,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Square,
  CheckSquare,
  XCircle,
  Trash2
} from "lucide-react";

interface QueueWorkspaceProps {
  jobs: JobListItem[];
  modelCatalog: ModelCatalogItem[];
  selectedJobId: string | null;
  onSelectJob: (jobId: string) => void;
  onInspectJob: (jobId: string) => void;
  onDispatchJob?: (jobId: string) => void;
  onRetryJob?: (jobId: string) => void;
  onCancelJob?: (jobId: string) => void;
  onBatchDispatch?: (jobIds: string[]) => void;
  onBatchCancel?: (jobIds: string[]) => void;
  onBatchDelete?: (jobIds: string[]) => void;
  batchActionBusy?: "dispatch" | "retry" | "cancel" | "delete" | null;
}

export function QueueWorkspace({
  jobs,
  modelCatalog,
  selectedJobId,
  onSelectJob,
  onInspectJob,
  onDispatchJob,
  onRetryJob,
  onCancelJob,
  onBatchDispatch,
  onBatchCancel,
  onBatchDelete,
  batchActionBusy
}: QueueWorkspaceProps) {
  const [selectedBatchIds, setSelectedBatchIds] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const filteredJobs = useMemo(() => {
    let result = jobs;
    if (statusFilter !== "all") {
      result = result.filter(j => {
        if (statusFilter === "failed") return j.job.status === "failed" || j.job.status === "cancelled";
        if (statusFilter === "pending") return canDispatchJobStatus(j.job.status);
        return j.job.status === statusFilter;
      });
    }
    if (searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      result = result.filter(j => matchesJobQuery(j, q));
    }
    return result;
  }, [jobs, statusFilter, searchQuery]);

  const stats = useMemo(() => {
    const created = jobs.filter(j => canDispatchJobStatus(j.job.status)).length;
    const running = jobs.filter(j => j.job.status === "running").length;
    const finished = jobs.filter(j => j.job.status === "finished").length;
    const failed = jobs.filter(j => j.job.status === "failed" || j.job.status === "cancelled").length;
    return { total: jobs.length, created, running, finished, failed };
  }, [jobs]);

  const runningJobs = useMemo(() => jobs.filter(j => j.job.status === "running"), [jobs]);
  const pendingJobs = useMemo(() => jobs.filter(j => canDispatchJobStatus(j.job.status)), [jobs]);
  const recentJobs = useMemo(() => filteredJobs.slice(0, 50), [filteredJobs]);
  const selectedBatchSet = useMemo(() => new Set(selectedBatchIds), [selectedBatchIds]);
  const selectedBatchItems = useMemo(
    () => jobs.filter((item) => selectedBatchSet.has(item.job.job_id)),
    [jobs, selectedBatchSet]
  );
  const dispatchableBatchIds = useMemo(
    () => selectedBatchItems.filter((item) => canDispatchJobStatus(item.job.status)).map((item) => item.job.job_id),
    [selectedBatchItems]
  );
  const cancellableBatchIds = useMemo(
    () => selectedBatchItems.filter((item) => item.job.status === "running").map((item) => item.job.job_id),
    [selectedBatchItems]
  );
  const deletableBatchIds = useMemo(
    () => selectedBatchItems.filter((item) => item.job.status !== "running").map((item) => item.job.job_id),
    [selectedBatchItems]
  );
  const visibleJobIds = useMemo(() => recentJobs.map((item) => item.job.job_id), [recentJobs]);
  const allVisibleSelected = visibleJobIds.length > 0 && visibleJobIds.every((id) => selectedBatchSet.has(id));

  useEffect(() => {
    const availableIds = new Set(jobs.map((item) => item.job.job_id));
    setSelectedBatchIds((current) => current.filter((id) => availableIds.has(id)));
  }, [jobs]);

  function toggleBatchJob(jobId: string) {
    setSelectedBatchIds((current) =>
      current.includes(jobId) ? current.filter((id) => id !== jobId) : [...current, jobId]
    );
  }

  function toggleVisibleJobs() {
    setSelectedBatchIds((current) => {
      const currentSet = new Set(current);
      if (allVisibleSelected) {
        return current.filter((id) => !visibleJobIds.includes(id));
      }
      for (const id of visibleJobIds) {
        currentSet.add(id);
      }
      return Array.from(currentSet);
    });
  }

  return (
    <div className="queue-workspace">
      {/* Stats Bar */}
      <div className="queue-stats-bar">
        <div className="queue-stat">
          <Clock size={14} />
          <span className="queue-stat-value">{stats.created}</span>
          <span className="queue-stat-label">待派发</span>
        </div>
        <div className="queue-stat running">
          <Loader2 size={14} className="spin" />
          <span className="queue-stat-value">{stats.running}</span>
          <span className="queue-stat-label">运行中</span>
        </div>
        <div className="queue-stat success">
          <CheckCircle2 size={14} />
          <span className="queue-stat-value">{stats.finished}</span>
          <span className="queue-stat-label">已完成</span>
        </div>
        <div className="queue-stat danger">
          <AlertCircle size={14} />
          <span className="queue-stat-value">{stats.failed}</span>
          <span className="queue-stat-label">需处理</span>
        </div>
      </div>

      {selectedBatchIds.length > 0 && (
        <div className="queue-batch-strip">
          <div className="queue-batch-summary">
            <strong>已选择 {selectedBatchIds.length} 个任务</strong>
            <span>{dispatchableBatchIds.length} 个可派发，{cancellableBatchIds.length} 个可取消，{deletableBatchIds.length} 个可删除</span>
          </div>
          <div className="queue-batch-actions">
            <button
              className="icon-btn primary"
              disabled={!onBatchDispatch || dispatchableBatchIds.length === 0 || !!batchActionBusy}
              onClick={() => onBatchDispatch?.(dispatchableBatchIds)}
              type="button"
            >
              <Play size={12} /> 批量派发
            </button>
            <button
              className="icon-btn danger"
              disabled={!onBatchCancel || cancellableBatchIds.length === 0 || !!batchActionBusy}
              onClick={() => onBatchCancel?.(cancellableBatchIds)}
              type="button"
            >
              <XCircle size={12} /> 批量取消
            </button>
            <button
              className="icon-btn danger"
              disabled={!onBatchDelete || deletableBatchIds.length === 0 || !!batchActionBusy}
              onClick={() => {
                if (confirm(`确认删除 ${deletableBatchIds.length} 个任务？此操作不可撤销。`)) {
                  onBatchDelete?.(deletableBatchIds);
                }
              }}
              type="button"
            >
              <Trash2 size={12} /> 批量删除
            </button>
            <button className="icon-btn" onClick={() => setSelectedBatchIds([])} type="button">
              清空
            </button>
          </div>
        </div>
      )}

      <div className="queue-main-grid">
        {/* Left: Running & Pending */}
        <div className="queue-lanes">
          {/* Running Jobs */}
          <div className="queue-lane">
            <div className="queue-lane-header">
              <span className="queue-lane-title">运行中</span>
              <span className="queue-lane-count">{runningJobs.length}</span>
            </div>
            <div className="queue-lane-list">
              {runningJobs.length > 0 ? runningJobs.map(item => (
                <div 
                  key={item.job.job_id} 
                  className={`queue-job-card running ${selectedJobId === item.job.job_id ? "selected" : ""}`}
                  onClick={() => onSelectJob(item.job.job_id)}
                >
                  <div className="queue-job-header">
                    <strong>{modelDisplayName(item.job.model, modelCatalog)}</strong>
                    <span className="queue-job-progress">{item.phase_display.percent}%</span>
                  </div>
                  <div className="queue-job-meta">
                    <code>{item.job.job_id.slice(0, 8)}</code>
                    <span>{item.phase_display.label}</span>
                  </div>
                  {item.job.progress_message && (
                    <div className="queue-job-live-msg">{item.job.progress_message}</div>
                  )}
                  <div className="queue-job-progress-bar">
                    <div className="queue-job-progress-fill" style={{ width: `${item.phase_display.percent}%` }} />
                  </div>
                  <div className="queue-job-actions">
                    <button className="icon-btn" title="检视" onClick={(e) => { e.stopPropagation(); onInspectJob(item.job.job_id); }}>
                      检视
                    </button>
                    {onCancelJob && (
                      <button className="icon-btn danger" title="取消" onClick={(e) => { e.stopPropagation(); onCancelJob(item.job.job_id); }}>
                        取消
                      </button>
                    )}
                  </div>
                </div>
              )) : (
                <div className="queue-lane-empty">无运行中任务</div>
              )}
            </div>
          </div>

          {/* Pending Jobs */}
          <div className="queue-lane">
            <div className="queue-lane-header">
              <span className="queue-lane-title">待派发</span>
              <span className="queue-lane-count">{pendingJobs.length}</span>
            </div>
            <div className="queue-lane-list">
              {pendingJobs.length > 0 ? pendingJobs.map(item => (
                <div 
                  key={item.job.job_id} 
                  className={`queue-job-card pending ${selectedJobId === item.job.job_id ? "selected" : ""}`}
                  onClick={() => onSelectJob(item.job.job_id)}
                >
                  <div className="queue-job-header">
                    <strong>{modelDisplayName(item.job.model, modelCatalog)}</strong>
                    <StatusBadge state={item.job.status} label={statusLabel(item.job.status)} />
                  </div>
                  <div className="queue-job-meta">
                    <code>{item.job.job_id.slice(0, 8)}</code>
                    <span>{sourceTypeLabel(item.job.source_type)}</span>
                  </div>
                  <div className="queue-job-actions">
                    {onDispatchJob && (
                      <button className="icon-btn primary" title="派发" onClick={(e) => { e.stopPropagation(); onDispatchJob(item.job.job_id); }}>
                        <Play size={12} /> 派发
                      </button>
                    )}
                    <button className="icon-btn" title="检视" onClick={(e) => { e.stopPropagation(); onInspectJob(item.job.job_id); }}>
                      检视
                    </button>
                  </div>
                </div>
              )) : (
                <div className="queue-lane-empty">无待派发任务</div>
              )}
            </div>
          </div>
        </div>

        {/* Right: All Jobs Table */}
        <div className="queue-table-section">
          <div className="queue-table-header">
            <span className="queue-table-title">全部任务</span>
            <span className="queue-table-count">{filteredJobs.length}/{jobs.length} 条</span>
          </div>
          <div className="queue-search-bar">
            <input
              type="text"
              className="queue-search-input"
              placeholder="搜索任务 ID、模型、备注..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <select
              className="queue-status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="all">全部状态</option>
              <option value="running">运行中</option>
              <option value="pending">待派发</option>
              <option value="finished">已完成</option>
              <option value="failed">失败/取消</option>
            </select>
          </div>
          <div className="workbench-table-container compact">
            <table className="workbench-table">
              <thead>
                <tr>
                  <th style={{width: "42px"}}>
                    <button className="icon-btn square" onClick={toggleVisibleJobs} title="选择当前列表" type="button">
                      {allVisibleSelected ? <CheckSquare size={13} /> : <Square size={13} />}
                    </button>
                  </th>
                  <th style={{width: "70px"}}>状态</th>
                  <th style={{width: "90px"}}>ID</th>
                  <th>模型</th>
                  <th style={{width: "70px"}}>来源</th>
                  <th style={{width: "100px"}}>时间</th>
                  <th style={{width: "80px"}}>进度</th>
                  <th style={{width: "60px"}}></th>
                </tr>
              </thead>
              <tbody>
                {recentJobs.length > 0 ? recentJobs.map((item) => (
                  <tr 
                    key={item.job.job_id} 
                    className={selectedJobId === item.job.job_id ? "selected" : ""}
                    onClick={() => onSelectJob(item.job.job_id)}
                  >
                    <td>
                      <input
                        type="checkbox"
                        checked={selectedBatchSet.has(item.job.job_id)}
                        onChange={() => toggleBatchJob(item.job.job_id)}
                        onClick={(e) => e.stopPropagation()}
                        title="加入批量操作"
                      />
                    </td>
                    <td>
                      <StatusBadge state={item.job.status} label={statusLabel(item.job.status)} />
                    </td>
                    <td><code className="job-id-cell">{item.job.job_id.slice(0, 8)}</code></td>
                    <td><strong className="model-cell">{modelDisplayName(item.job.model, modelCatalog)}</strong></td>
                    <td>{sourceTypeLabel(item.job.source_type)}</td>
                    <td className="time-cell">{formatDateTime(item.job.created_at)}</td>
                    <td>
                      {(item.job.status === "failed" || item.job.status === "cancelled") && item.job.error_message ? (
                        <span className="error-hint" title={item.job.error_message}>
                          {item.job.error_message.length > 28 ? item.job.error_message.slice(0, 28) + "\u2026" : item.job.error_message}
                        </span>
                      ) : (
                        <span className="progress-cell">{item.phase_display.percent}%</span>
                      )}
                    </td>
                    <td>
                      <button className="icon-btn" onClick={(e) => { e.stopPropagation(); onInspectJob(item.job.job_id); }}>
                        →
                      </button>
                    </td>
                  </tr>
                )) : (
                  <tr>
                    <td colSpan={8}>
                      <div className="queue-table-empty">暂无任务记录</div>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
