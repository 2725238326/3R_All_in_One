import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Hammer,
  RefreshCw,
  Server,
  ShieldCheck,
  Wrench
} from "lucide-react";
import { API_BASE } from "./appConfig";
import { MessageBanner, MiniStat, PanelTitle, StatusBadge } from "./uiPrimitives";

type AgentModel = {
  name: string;
  key: string;
  type: string;
  paradigm: string;
  status: string;
  env: string;
  needs_curope: boolean;
  gpu_memory_gb: number;
  unresolved_issues: number;
  family: string;
  version: string;
  repo: {
    url?: string;
    branch?: string;
    server_path?: string;
  };
  environment: {
    conda_env?: string;
    python?: string;
    torch?: string;
    create_strategy?: string;
    clone_source?: string;
  };
  resources: Record<string, number | string | null>;
  health_checks: Array<{ name?: string; type?: string; critical?: boolean }>;
  runner: {
    script?: string;
    conda_env?: string;
  };
  unresolved_issue_items: Array<{
    id?: string;
    description?: string;
    workaround?: string;
  }>;
  param_tiers: Record<string, Record<string, unknown>>;
  last_verified?: string;
};

type AgentRegistryPayload = {
  summary: {
    total: number;
    integrated: number;
    env_ready: number;
    with_issues: number;
    by_status: Record<string, number>;
  };
  models: AgentModel[];
  specs_dir: string;
};

type AgentValidationPayload = {
  ok: boolean;
  summary: {
    total: number;
    valid: number;
    errors: number;
    warnings: number;
  };
  results: Array<{
    model: string;
    valid: boolean;
    errorCount: number;
    warningCount: number;
  }>;
};

type AgentBuildTask = {
  taskId: string;
  model: string;
  modelName: string;
  status: "queued" | "running" | "finished" | "failed";
  created_at: string;
  updated_at: string;
  error: string | null;
  report: null | {
    success: boolean;
    total_duration_sec: number;
    steps: Array<{
      step: string;
      success: boolean;
      error: string;
      duration_sec: number;
    }>;
  };
};

async function fetchAgentJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(data?.detail || data?.message || `HTTP ${response.status}`);
  }
  return data as T;
}

function agentStatusLabel(status: string) {
  if (status === "integrated") return "已集成";
  if (status === "env_ready") return "环境就绪";
  if (status === "planned") return "计划中";
  if (status === "deprecated") return "已弃用";
  return status || "未知";
}

function buildStatusLabel(status: string) {
  if (status === "queued") return "排队中";
  if (status === "running") return "构建中";
  if (status === "finished") return "完成";
  if (status === "failed") return "失败";
  return status;
}

export function AgentWorkbench() {
  const [registry, setRegistry] = useState<AgentRegistryPayload | null>(null);
  const [validation, setValidation] = useState<AgentValidationPayload | null>(null);
  const [tasks, setTasks] = useState<AgentBuildTask[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [buildingKey, setBuildingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const selectedModel = useMemo(
    () => registry?.models.find((model) => model.key === selectedKey) ?? registry?.models[0] ?? null,
    [registry, selectedKey]
  );

  const runningTasks = useMemo(
    () => tasks.filter((task) => task.status === "queued" || task.status === "running"),
    [tasks]
  );

  async function loadAgentState(showInfo = false) {
    setLoading(true);
    setError(null);
    try {
      const [registryPayload, validationPayload, buildsPayload] = await Promise.all([
        fetchAgentJson<AgentRegistryPayload>("/api/agent/registry"),
        fetchAgentJson<AgentValidationPayload>("/api/agent/validate"),
        fetchAgentJson<{ tasks: AgentBuildTask[] }>("/api/agent/builds"),
      ]);
      setRegistry(registryPayload);
      setValidation(validationPayload);
      setTasks(buildsPayload.tasks);
      setSelectedKey((current) => current || registryPayload.models[0]?.key || "");
      if (showInfo) setInfo("Agent 状态已刷新");
    } catch (err: any) {
      setError(err?.message || "Agent 状态读取失败");
    } finally {
      setLoading(false);
    }
  }

  async function startBuild(modelKey: string) {
    setBuildingKey(modelKey);
    setError(null);
    setInfo(null);
    try {
      const task = await fetchAgentJson<AgentBuildTask>(`/api/agent/build/${encodeURIComponent(modelKey)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      setTasks((current) => [task, ...current.filter((item) => item.taskId !== task.taskId)]);
      setInfo(`${task.modelName} 环境构建已进入后台队列`);
    } catch (err: any) {
      setError(err?.message || "Agent 构建启动失败");
    } finally {
      setBuildingKey(null);
    }
  }

  useEffect(() => {
    loadAgentState();
  }, []);

  useEffect(() => {
    if (runningTasks.length === 0) return;
    const timer = window.setInterval(() => {
      loadAgentState(false);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [runningTasks.length]);

  return (
    <section className="agent-workbench">
      {info && <MessageBanner kind="info" message={info} />}
      {error && <MessageBanner kind="error" message={error} />}

      <div className="agent-head-strip">
        <div>
          <PanelTitle eyebrow="Agent" title="模型蓝图与环境编排" />
          <div className="model-semantic-chips compact">
            <span>{registry?.specs_dir || "agent/model_specs"}</span>
            <span>{validation?.ok ? "蓝图校验通过" : "蓝图需要处理"}</span>
          </div>
        </div>
        <button className="ghost-button small" type="button" onClick={() => loadAgentState(true)} disabled={loading}>
          <RefreshCw size={14} />
          {loading ? "刷新中" : "刷新"}
        </button>
      </div>

      <div className="agent-summary-grid">
        <MiniStat label="蓝图总数" value={registry?.summary.total ?? 0} />
        <MiniStat label="已集成" value={registry?.summary.integrated ?? 0} />
        <MiniStat label="环境就绪" value={registry?.summary.env_ready ?? 0} />
        <MiniStat label="待处理问题" value={registry?.summary.with_issues ?? 0} />
        <MiniStat label="校验通过" value={validation ? `${validation.summary.valid}/${validation.summary.total}` : "--"} />
      </div>

      <div className="agent-grid">
        <div className="panel agent-model-panel">
          <div className="agent-panel-head">
            <PanelTitle eyebrow="Registry" title="模型蓝图" />
            <StatusBadge
              state={validation?.ok ? "ready" : "degraded"}
              label={validation?.ok ? "7/7 valid" : `${validation?.summary.errors ?? 0} errors`}
            />
          </div>
          <div className="agent-model-list">
            {(registry?.models ?? []).map((model) => (
              <button
                key={model.key}
                className={`agent-model-row ${selectedModel?.key === model.key ? "active" : ""}`}
                type="button"
                onClick={() => setSelectedKey(model.key)}
              >
                <span className="agent-model-main">
                  <strong>{model.name}</strong>
                  <small>{model.type} / {model.paradigm}</small>
                </span>
                <span className="agent-model-meta">
                  <StatusBadge state={model.status === "integrated" ? "ready" : "starting"} label={agentStatusLabel(model.status)} />
                  <small>{model.gpu_memory_gb} GB</small>
                </span>
              </button>
            ))}
          </div>
        </div>

        <div className="panel agent-detail-panel">
          {selectedModel ? (
            <>
              <div className="agent-detail-head">
                <div>
                  <PanelTitle eyebrow={selectedModel.key} title={selectedModel.name} />
                  <div className="model-semantic-chips compact">
                    <span>{selectedModel.family}</span>
                    <span>{selectedModel.environment.conda_env}</span>
                    <span>{selectedModel.needs_curope ? "需要 curope" : "无需 curope"}</span>
                  </div>
                </div>
                <button
                  className="primary-button small"
                  type="button"
                  onClick={() => startBuild(selectedModel.key)}
                  disabled={buildingKey !== null}
                >
                  <Hammer size={14} />
                  {buildingKey === selectedModel.key ? "启动中" : "构建环境"}
                </button>
              </div>

              <div className="agent-detail-grid">
                <div className="meta-card">
                  <Server size={16} />
                  <span>远程路径</span>
                  <strong>{selectedModel.repo.server_path || "--"}</strong>
                </div>
                <div className="meta-card">
                  <Wrench size={16} />
                  <span>Runner</span>
                  <strong>{selectedModel.runner.script || "--"}</strong>
                </div>
                <div className="meta-card">
                  <ShieldCheck size={16} />
                  <span>健康检查</span>
                  <strong>{selectedModel.health_checks.length}</strong>
                </div>
                <div className="meta-card">
                  {selectedModel.unresolved_issues > 0 ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
                  <span>未解决问题</span>
                  <strong>{selectedModel.unresolved_issues}</strong>
                </div>
              </div>

              {selectedModel.unresolved_issue_items.length > 0 && (
                <div className="agent-issue-list">
                  {selectedModel.unresolved_issue_items.map((issue) => (
                    <div className="critical-log-banner" key={issue.id || issue.description}>
                      <strong>{issue.id || "issue"}</strong>
                      <span>{issue.description}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : (
            <div className="empty-state">暂无 Agent 蓝图</div>
          )}
        </div>
      </div>

      <div className="panel agent-build-panel">
        <div className="agent-panel-head">
          <PanelTitle eyebrow="Builds" title="环境构建任务" />
          <StatusBadge state={runningTasks.length > 0 ? "running" : "ready"} label={`${runningTasks.length} running`} />
        </div>
        {tasks.length === 0 ? (
          <div className="empty-state">暂无构建任务</div>
        ) : (
          <div className="agent-build-list">
            {tasks.slice(0, 8).map((task) => (
              <div className={`agent-build-row ${task.status}`} key={task.taskId}>
                <div>
                  <strong>{task.modelName}</strong>
                  <span>{task.taskId}</span>
                </div>
                <StatusBadge
                  state={task.status === "finished" ? "ready" : task.status === "failed" ? "degraded" : "running"}
                  label={buildStatusLabel(task.status)}
                />
                <span>{task.report ? `${task.report.steps.length} steps / ${task.report.total_duration_sec}s` : task.error || "等待执行"}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
