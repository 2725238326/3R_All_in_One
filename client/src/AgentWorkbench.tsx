import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Hammer,
  Package,
  RefreshCw,
  Server,
  ShieldCheck,
  Stethoscope,
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
  smoke_test: { script?: string; expected?: string };
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

type AgentValidationIssue = {
  level: string;
  field: string;
  message: string;
  suggestion: string;
};

type AgentValidationResult = {
  model: string;
  path: string;
  valid: boolean;
  errors: AgentValidationIssue[];
  warnings: AgentValidationIssue[];
  issues: AgentValidationIssue[];
  errorCount: number;
  warningCount: number;
};

type AgentValidationPayload = {
  ok: boolean;
  summary: {
    total: number;
    valid: number;
    errors: number;
    warnings: number;
  };
  results: AgentValidationResult[];
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

type SmokeResult = {
  model: string;
  ready: boolean;
  env_exists: boolean;
  checkpoints_ok: boolean;
  missing_checkpoints: string[];
  smoke_ok: boolean;
  smoke_output: string;
  error: string;
  duration_sec: number;
};

type HealthCheckResult = {
  step: string;
  success: boolean;
  error: string;
  output: string;
  duration_sec: number;
};

type DiagnosisItem = {
  symptom: string;
  cause: string;
  solution: string;
  confidence: number;
  related_issue_id: string;
  fix_command: string;
};

type HealthResult = {
  checks: HealthCheckResult[];
  all_passed: boolean;
  diagnosis: {
    model: string;
    overall_status: string;
    has_fixes: boolean;
    items: DiagnosisItem[];
  };
};

type BatchResult = {
  total: number;
  ready: number;
  not_ready: number;
  ready_models: string[];
  blocked_models: Array<{ model: string; reason: string }>;
};

type AgentCheckBase = {
  taskId: string;
  label: string;
  status: "queued" | "running" | "finished" | "failed";
  created_at: string;
  updated_at: string;
  error: string | null;
};

type AgentCheckTask =
  | (AgentCheckBase & { kind: "smoke"; result: SmokeResult | null })
  | (AgentCheckBase & { kind: "health"; result: HealthResult | null })
  | (AgentCheckBase & { kind: "smoke-batch"; result: BatchResult | null });

async function fetchAgentJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(data?.detail || data?.message || `HTTP ${response.status}`);
  }
  return data as T;
}

function postAgentAction<T>(path: string): Promise<T> {
  return fetchAgentJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
}

function agentStatusLabel(status: string) {
  if (status === "integrated") return "已集成";
  if (status === "env_ready") return "环境就绪";
  if (status === "planned") return "计划中";
  if (status === "deprecated") return "已弃用";
  return status || "未知";
}

function checkStatusLabel(status: string) {
  if (status === "queued") return "排队中";
  if (status === "running") return "执行中";
  if (status === "finished") return "完成";
  if (status === "failed") return "失败";
  return status;
}

function checkKindLabel(kind: string) {
  if (kind === "smoke") return "Smoke";
  if (kind === "health") return "健康检查";
  if (kind === "smoke-batch") return "批量 Smoke";
  return kind;
}

function badgeStateForCheck(status: string) {
  if (status === "finished") return "ready";
  if (status === "failed") return "degraded";
  return "running";
}

function diagnosisBadgeState(status: string) {
  if (status === "healthy") return "ready";
  if (status === "fixable") return "starting";
  if (status === "critical") return "degraded";
  return "running";
}

export function AgentWorkbench() {
  const [registry, setRegistry] = useState<AgentRegistryPayload | null>(null);
  const [validation, setValidation] = useState<AgentValidationPayload | null>(null);
  const [tasks, setTasks] = useState<AgentBuildTask[]>([]);
  const [checks, setChecks] = useState<AgentCheckTask[]>([]);
  const [selectedKey, setSelectedKey] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [actionKey, setActionKey] = useState<string | null>(null);
  const [batchRunning, setBatchRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  const selectedModel = useMemo(
    () => registry?.models.find((model) => model.key === selectedKey) ?? registry?.models[0] ?? null,
    [registry, selectedKey]
  );

  const selectedValidation = useMemo(() => {
    if (!validation || !selectedModel) return null;
    return (
      validation.results.find(
        (result) =>
          result.model.toLowerCase() === selectedModel.key ||
          result.model.toLowerCase() === selectedModel.name.toLowerCase()
      ) ?? null
    );
  }, [validation, selectedModel]);

  const runningTasks = useMemo(
    () => tasks.filter((task) => task.status === "queued" || task.status === "running"),
    [tasks]
  );

  const runningChecks = useMemo(
    () => checks.filter((task) => task.status === "queued" || task.status === "running"),
    [checks]
  );

  const latestCheck = (kind: "smoke" | "health") => {
    if (!selectedModel) return null;
    return (
      checks.find((task) => task.kind === kind && task.label === selectedModel.key) ?? null
    );
  };

  const latestSmoke = latestCheck("smoke");
  const latestHealth = latestCheck("health");
  const latestBatch = useMemo(
    () => checks.find((task) => task.kind === "smoke-batch") ?? null,
    [checks]
  );

  async function loadAgentState(showInfo = false) {
    setLoading(true);
    setError(null);
    try {
      const [registryPayload, validationPayload, buildsPayload, checksPayload] = await Promise.all([
        fetchAgentJson<AgentRegistryPayload>("/api/agent/registry"),
        fetchAgentJson<AgentValidationPayload>("/api/agent/validate"),
        fetchAgentJson<{ tasks: AgentBuildTask[] }>("/api/agent/builds"),
        fetchAgentJson<{ tasks: AgentCheckTask[] }>("/api/agent/checks"),
      ]);
      setRegistry(registryPayload);
      setValidation(validationPayload);
      setTasks(buildsPayload.tasks);
      setChecks(checksPayload.tasks);
      setSelectedKey((current) => current || registryPayload.models[0]?.key || "");
      if (showInfo) setInfo("Agent 状态已刷新");
    } catch (err: any) {
      setError(err?.message || "Agent 状态读取失败");
    } finally {
      setLoading(false);
    }
  }

  async function startBuild(modelKey: string) {
    setActionKey(`build:${modelKey}`);
    setError(null);
    setInfo(null);
    try {
      const task = await postAgentAction<AgentBuildTask>(`/api/agent/build/${encodeURIComponent(modelKey)}`);
      setTasks((current) => [task, ...current.filter((item) => item.taskId !== task.taskId)]);
      setInfo(`${task.modelName} 环境构建已进入后台队列`);
    } catch (err: any) {
      setError(err?.message || "Agent 构建启动失败");
    } finally {
      setActionKey(null);
    }
  }

  async function startCheck(kind: "smoke" | "health", modelKey: string) {
    setActionKey(`${kind}:${modelKey}`);
    setError(null);
    setInfo(null);
    try {
      const task = await postAgentAction<AgentCheckTask>(`/api/agent/${kind}/${encodeURIComponent(modelKey)}`);
      setChecks((current) => [task, ...current.filter((item) => item.taskId !== task.taskId)]);
      setInfo(`${modelKey} ${checkKindLabel(kind)} 已进入后台队列`);
    } catch (err: any) {
      setError(err?.message || `Agent ${checkKindLabel(kind)} 启动失败`);
    } finally {
      setActionKey(null);
    }
  }

  async function startBatchSmoke() {
    setBatchRunning(true);
    setError(null);
    setInfo(null);
    try {
      const task = await postAgentAction<AgentCheckTask>("/api/agent/smoke-batch");
      setChecks((current) => [task, ...current.filter((item) => item.taskId !== task.taskId)]);
      setInfo("批量 Smoke 已进入后台队列");
    } catch (err: any) {
      setError(err?.message || "批量 Smoke 启动失败");
    } finally {
      setBatchRunning(false);
    }
  }

  useEffect(() => {
    loadAgentState();
  }, []);

  useEffect(() => {
    if (runningTasks.length === 0 && runningChecks.length === 0) return;
    const timer = window.setInterval(() => {
      loadAgentState(false);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [runningTasks.length, runningChecks.length]);

  const isBusy = actionKey !== null;

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
            {runningChecks.length > 0 && <span>{runningChecks.length} 项检查执行中</span>}
          </div>
        </div>
        <div className="agent-head-actions">
          <button className="ghost-button small" type="button" onClick={startBatchSmoke} disabled={batchRunning}>
            <Activity size={14} />
            {batchRunning ? "启动中" : "批量 Smoke"}
          </button>
          <button className="ghost-button small" type="button" onClick={() => loadAgentState(true)} disabled={loading}>
            <RefreshCw size={14} />
            {loading ? "刷新中" : "刷新"}
          </button>
        </div>
      </div>

      <div className="agent-summary-grid">
        <MiniStat label="蓝图总数" value={registry?.summary.total ?? 0} />
        <MiniStat label="已集成" value={registry?.summary.integrated ?? 0} />
        <MiniStat label="待处理问题" value={registry?.summary.with_issues ?? 0} />
        <MiniStat label="校验通过" value={validation ? `${validation.summary.valid}/${validation.summary.total}` : "--"} />
        <MiniStat label="校验警告" value={validation?.summary.warnings ?? 0} />
      </div>

      {latestBatch && latestBatch.kind === "smoke-batch" && (
        <div className="panel agent-batch-panel">
          <div className="agent-panel-head">
            <PanelTitle eyebrow="Batch Smoke" title="批量就绪检查结果" />
            <StatusBadge state={badgeStateForCheck(latestBatch.status)} label={checkStatusLabel(latestBatch.status)} />
          </div>
          {latestBatch.status === "finished" && latestBatch.result ? (
            <div className="agent-batch-body">
              <div className="model-semantic-chips compact">
                <span>就绪 {latestBatch.result.ready}/{latestBatch.result.total}</span>
                <span>未就绪 {latestBatch.result.not_ready}</span>
              </div>
              {latestBatch.result.blocked_models.length > 0 && (
                <div className="agent-issue-list">
                  {latestBatch.result.blocked_models.map((blocked) => (
                    <div className="critical-log-banner" key={blocked.model}>
                      <strong>{blocked.model}</strong>
                      <span>{blocked.reason || "未就绪"}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="empty-state">{latestBatch.error || "批量 Smoke 执行中..."}</div>
          )}
        </div>
      )}

      <div className="agent-grid">
        <div className="panel agent-model-panel">
          <div className="agent-panel-head">
            <PanelTitle eyebrow="Registry" title="模型蓝图" />
            <StatusBadge
              state={validation?.ok ? "ready" : "degraded"}
              label={validation ? `${validation.summary.valid}/${validation.summary.total} valid` : "--"}
            />
          </div>
          <div className="agent-model-list">
            {(registry?.models ?? []).map((model) => {
              const modelValidation = validation?.results.find(
                (result) =>
                  result.model.toLowerCase() === model.key ||
                  result.model.toLowerCase() === model.name.toLowerCase()
              );
              return (
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
                    <StatusBadge
                      state={modelValidation ? (modelValidation.valid ? "ready" : "degraded") : "starting"}
                      label={
                        modelValidation
                          ? modelValidation.valid
                            ? modelValidation.warningCount > 0
                              ? `${modelValidation.warningCount} warn`
                              : "valid"
                            : `${modelValidation.errorCount} err`
                          : agentStatusLabel(model.status)
                      }
                    />
                    <small>{model.gpu_memory_gb} GB</small>
                  </span>
                </button>
              );
            })}
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
                <div className="agent-detail-actions">
                  <button
                    className="ghost-button small"
                    type="button"
                    onClick={() => startCheck("smoke", selectedModel.key)}
                    disabled={isBusy}
                  >
                    <Activity size={14} />
                    {actionKey === `smoke:${selectedModel.key}` ? "启动中" : "Smoke"}
                  </button>
                  <button
                    className="ghost-button small"
                    type="button"
                    onClick={() => startCheck("health", selectedModel.key)}
                    disabled={isBusy}
                  >
                    <Stethoscope size={14} />
                    {actionKey === `health:${selectedModel.key}` ? "启动中" : "健康检查"}
                  </button>
                  <button
                    className="primary-button small"
                    type="button"
                    onClick={() => startBuild(selectedModel.key)}
                    disabled={isBusy}
                  >
                    <Hammer size={14} />
                    {actionKey === `build:${selectedModel.key}` ? "启动中" : "构建环境"}
                  </button>
                </div>
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
                  <span>健康检查项</span>
                  <strong>{selectedModel.health_checks.length}</strong>
                </div>
                <div className="meta-card">
                  {selectedModel.unresolved_issues > 0 ? <AlertTriangle size={16} /> : <CheckCircle2 size={16} />}
                  <span>未解决问题</span>
                  <strong>{selectedModel.unresolved_issues}</strong>
                </div>
              </div>

              {selectedValidation && selectedValidation.issues.length > 0 && (
                <div className="agent-validation-block">
                  <div className="agent-subhead">
                    <Package size={14} />
                    <span>蓝图校验明细</span>
                    <StatusBadge
                      state={selectedValidation.valid ? "ready" : "degraded"}
                      label={`${selectedValidation.errorCount} 错误 / ${selectedValidation.warningCount} 警告`}
                    />
                  </div>
                  <div className="agent-issue-list">
                    {selectedValidation.issues.map((issue, index) => (
                      <div className={`agent-issue-row ${issue.level}`} key={`${issue.field}-${index}`}>
                        <span className="agent-issue-level">{issue.level.toUpperCase()}</span>
                        <div className="agent-issue-body">
                          <strong>{issue.field}</strong>
                          <span>{issue.message}</span>
                          {issue.suggestion && <small>建议：{issue.suggestion}</small>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {latestSmoke && (
                <div className="agent-check-result">
                  <div className="agent-subhead">
                    <Activity size={14} />
                    <span>最近一次 Smoke</span>
                    <StatusBadge state={badgeStateForCheck(latestSmoke.status)} label={checkStatusLabel(latestSmoke.status)} />
                  </div>
                  {latestSmoke.kind === "smoke" && latestSmoke.status === "finished" && latestSmoke.result ? (
                    <div className="model-semantic-chips compact">
                      <span>{latestSmoke.result.ready ? "就绪" : "未就绪"}</span>
                      <span>env：{latestSmoke.result.env_exists ? "存在" : "缺失"}</span>
                      <span>权重：{latestSmoke.result.checkpoints_ok ? "完整" : "缺失"}</span>
                      {latestSmoke.result.error && <span>{latestSmoke.result.error}</span>}
                    </div>
                  ) : (
                    <div className="empty-state">{latestSmoke.error || "执行中..."}</div>
                  )}
                </div>
              )}

              {latestHealth && latestHealth.kind === "health" && latestHealth.status === "finished" && latestHealth.result && (
                <div className="agent-check-result">
                  <div className="agent-subhead">
                    <Stethoscope size={14} />
                    <span>健康诊断</span>
                    <StatusBadge
                      state={diagnosisBadgeState(latestHealth.result.diagnosis.overall_status)}
                      label={latestHealth.result.diagnosis.overall_status}
                    />
                  </div>
                  {latestHealth.result.diagnosis.items.length === 0 ? (
                    <div className="model-semantic-chips compact">
                      <span>{latestHealth.result.all_passed ? "全部健康检查通过" : "无诊断项"}</span>
                    </div>
                  ) : (
                    <div className="agent-issue-list">
                      {latestHealth.result.diagnosis.items.map((item, index) => (
                        <div className="agent-diagnosis-row" key={`${item.symptom}-${index}`}>
                          <strong>{item.symptom}</strong>
                          <span>{item.cause}</span>
                          <small>建议：{item.solution}</small>
                          {item.fix_command && <code>{item.fix_command}</code>}
                          <em>置信度 {Math.round(item.confidence * 100)}%</em>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

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

      <div className="agent-grid">
        <div className="panel agent-build-panel">
          <div className="agent-panel-head">
            <PanelTitle eyebrow="Builds" title="环境构建任务" />
            <StatusBadge state={runningTasks.length > 0 ? "running" : "ready"} label={`${runningTasks.length} running`} />
          </div>
          {tasks.length === 0 ? (
            <div className="empty-state">暂无构建任务</div>
          ) : (
            <div className="agent-build-list">
              {tasks.slice(0, 6).map((task) => (
                <div className={`agent-build-row ${task.status}`} key={task.taskId}>
                  <div>
                    <strong>{task.modelName}</strong>
                    <span>{task.taskId}</span>
                  </div>
                  <StatusBadge
                    state={badgeStateForCheck(task.status)}
                    label={checkStatusLabel(task.status)}
                  />
                  <span>{task.report ? `${task.report.steps.length} steps / ${task.report.total_duration_sec}s` : task.error || "等待执行"}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="panel agent-build-panel">
          <div className="agent-panel-head">
            <PanelTitle eyebrow="Checks" title="Smoke / 健康检查任务" />
            <StatusBadge state={runningChecks.length > 0 ? "running" : "ready"} label={`${runningChecks.length} running`} />
          </div>
          {checks.length === 0 ? (
            <div className="empty-state">暂无检查任务</div>
          ) : (
            <div className="agent-build-list">
              {checks.slice(0, 8).map((task) => (
                <div className={`agent-build-row ${task.status}`} key={task.taskId}>
                  <div>
                    <strong>{checkKindLabel(task.kind)} · {task.label}</strong>
                    <span>{task.taskId}</span>
                  </div>
                  <StatusBadge state={badgeStateForCheck(task.status)} label={checkStatusLabel(task.status)} />
                  <span>{summarizeCheckTask(task)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function summarizeCheckTask(task: AgentCheckTask): string {
  if (task.status !== "finished") {
    return task.error || "等待执行";
  }
  if (task.kind === "smoke") {
    return task.result ? (task.result.ready ? "就绪" : task.result.error || "未就绪") : "完成";
  }
  if (task.kind === "health") {
    return task.result ? `诊断：${task.result.diagnosis.overall_status}` : "完成";
  }
  if (task.kind === "smoke-batch") {
    return task.result ? `就绪 ${task.result.ready}/${task.result.total}` : "完成";
  }
  return "完成";
}
