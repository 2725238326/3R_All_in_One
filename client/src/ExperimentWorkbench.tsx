import { useEffect, useMemo, useState } from "react";
import { FlaskConical, Play, Plus, RefreshCw, Trash2 } from "lucide-react";
import { API_BASE } from "./appConfig";
import { MessageBanner, MiniStat, PanelTitle, StatusBadge } from "./uiPrimitives";

type ExperimentTemplate = {
  id: string;
  name: string;
  description: string;
  model: string;
  source_type: string;
  base_params: Record<string, unknown>;
  param_grid: Record<string, unknown[]>;
  createdAt?: string;
  updatedAt?: string;
};

type ExperimentRunSummaryJob = {
  job_id: string;
  status: string;
  model: string;
  params: Record<string, unknown>;
};

type ExperimentRunSummary = {
  total: number;
  pending?: number;
  running?: number;
  finished?: number;
  failed?: number;
  cancelled?: number;
  jobs: ExperimentRunSummaryJob[];
};

type ExperimentRun = {
  id: string;
  templateId: string;
  name: string;
  status: string;
  jobIds: string[];
  createdAt?: string;
  startedAt?: string;
  completedAt?: string;
  metadata?: Record<string, unknown>;
  summary?: ExperimentRunSummary;
};

type CatalogModel = {
  value: string;
  label: string;
  runnable: boolean;
  source_types: string[];
};

type JobListItem = {
  job: {
    job_id: string;
    model: string;
    status: string;
    notes: string;
    source_type: string;
  };
};

async function fetchExpJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init);
  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new Error(data?.detail || data?.message || `HTTP ${response.status}`);
  }
  return data as T;
}

function postJson<T>(path: string, body: unknown): Promise<T> {
  return fetchExpJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function coerceValue(raw: string): unknown {
  const value = raw.trim();
  if (value === "true") return true;
  if (value === "false") return false;
  if (value === "") return "";
  const num = Number(value);
  return Number.isNaN(num) ? value : num;
}

// "niter: 100, 300" per line -> { niter: [100, 300] }
function parseGrid(text: string): Record<string, unknown[]> {
  const grid: Record<string, unknown[]> = {};
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    const sep = trimmed.indexOf(":");
    if (sep <= 0) continue;
    const key = trimmed.slice(0, sep).trim();
    const values = trimmed
      .slice(sep + 1)
      .split(",")
      .map((item) => coerceValue(item))
      .filter((item) => item !== "");
    if (key && values.length) grid[key] = values;
  }
  return grid;
}

// "image_size: 512" per line -> { image_size: 512 }
function parseParams(text: string): Record<string, unknown> {
  const params: Record<string, unknown> = {};
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    const sep = trimmed.indexOf(":");
    if (sep <= 0) continue;
    const key = trimmed.slice(0, sep).trim();
    if (key) params[key] = coerceValue(trimmed.slice(sep + 1));
  }
  return params;
}

function combinationCount(grid: Record<string, unknown[]>): number {
  const values = Object.values(grid);
  if (values.length === 0) return 1;
  return values.reduce((acc, list) => acc * (list.length || 1), 1);
}

function runStatusBadge(status: string): string {
  if (status === "running") return "running";
  if (status === "pending") return "starting";
  return "ready";
}

export function ExperimentWorkbench() {
  const [templates, setTemplates] = useState<ExperimentTemplate[]>([]);
  const [runs, setRuns] = useState<ExperimentRun[]>([]);
  const [catalog, setCatalog] = useState<CatalogModel[]>([]);
  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [selectedRun, setSelectedRun] = useState<ExperimentRun | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);

  // Create-template form
  const [formName, setFormName] = useState("");
  const [formModel, setFormModel] = useState("");
  const [formSourceType, setFormSourceType] = useState("images");
  const [formGrid, setFormGrid] = useState("niter: 100, 300");
  const [formBase, setFormBase] = useState("");

  // Run form
  const [selectedTemplateId, setSelectedTemplateId] = useState("");
  const [runName, setRunName] = useState("");
  const [sourceJobId, setSourceJobId] = useState("");
  const [autoDispatch, setAutoDispatch] = useState(false);

  const runnableModels = useMemo(() => catalog.filter((model) => model.runnable), [catalog]);
  const selectedTemplate = useMemo(
    () => templates.find((template) => template.id === selectedTemplateId) ?? null,
    [templates, selectedTemplateId]
  );

  async function loadAll(showInfo = false) {
    setLoading(true);
    setError(null);
    try {
      const [templatesPayload, runsPayload, catalogPayload, jobsPayload] = await Promise.all([
        fetchExpJson<{ templates: ExperimentTemplate[] }>("/api/experiments/templates"),
        fetchExpJson<{ runs: ExperimentRun[] }>("/api/experiments/runs"),
        fetchExpJson<{ models: CatalogModel[] }>("/api/models/catalog"),
        fetchExpJson<{ jobs: JobListItem[] }>("/api/jobs?limit=50"),
      ]);
      setTemplates(templatesPayload.templates);
      setRuns(runsPayload.runs);
      setCatalog(catalogPayload.models);
      setJobs(jobsPayload.jobs);
      setFormModel((current) => current || catalogPayload.models.find((m) => m.runnable)?.value || "");
      setSelectedTemplateId((current) => current || templatesPayload.templates[0]?.id || "");
      if (showInfo) setInfo("实验编排状态已刷新");
    } catch (err: any) {
      setError(err?.message || "实验编排状态读取失败");
    } finally {
      setLoading(false);
    }
  }

  async function createTemplate() {
    if (!formName.trim() || !formModel) {
      setError("请填写模板名称并选择模型");
      return;
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const template = await postJson<ExperimentTemplate>("/api/experiments/templates", {
        name: formName.trim(),
        description: "",
        model: formModel,
        source_type: formSourceType,
        base_params: parseParams(formBase),
        param_grid: parseGrid(formGrid),
      });
      setTemplates((current) => [template, ...current.filter((item) => item.id !== template.id)]);
      setSelectedTemplateId(template.id);
      setFormName("");
      setInfo(`模板「${template.name}」已创建（${combinationCount(template.param_grid)} 组参数）`);
    } catch (err: any) {
      setError(err?.message || "创建模板失败");
    } finally {
      setBusy(false);
    }
  }

  async function deleteTemplate(templateId: string) {
    setBusy(true);
    setError(null);
    try {
      await fetchExpJson(`/api/experiments/templates/${encodeURIComponent(templateId)}`, { method: "DELETE" });
      setTemplates((current) => current.filter((item) => item.id !== templateId));
      setInfo("模板已删除");
    } catch (err: any) {
      setError(err?.message || "删除模板失败");
    } finally {
      setBusy(false);
    }
  }

  async function runTemplate() {
    if (!selectedTemplateId) {
      setError("请选择要运行的模板");
      return;
    }
    if (!sourceJobId) {
      setError("请选择一个来源任务以复用其输入文件");
      return;
    }
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const run = await postJson<ExperimentRun>(
        `/api/experiments/templates/${encodeURIComponent(selectedTemplateId)}/run`,
        {
          run_name: runName.trim() || `run-${selectedTemplate?.name ?? selectedTemplateId}`,
          source_job_id: sourceJobId,
          auto_dispatch: autoDispatch,
        }
      );
      setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)]);
      setSelectedRun(run);
      setInfo(
        `实验「${run.name}」已生成 ${run.jobIds.length} 个任务` +
          (autoDispatch ? `，已派发 ${String((run.metadata?.dispatched as number) ?? 0)} 个` : "（未派发，可在队列中手动运行）")
      );
    } catch (err: any) {
      setError(err?.message || "运行实验失败");
    } finally {
      setBusy(false);
    }
  }

  async function loadRunSummary(runId: string) {
    setError(null);
    try {
      const run = await fetchExpJson<ExperimentRun>(`/api/experiments/runs/${encodeURIComponent(runId)}`);
      setSelectedRun(run);
      setRuns((current) => current.map((item) => (item.id === run.id ? run : item)));
    } catch (err: any) {
      setError(err?.message || "读取实验汇总失败");
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  return (
    <section className="agent-workbench">
      {info && <MessageBanner kind="info" message={info} />}
      {error && <MessageBanner kind="error" message={error} />}

      <div className="agent-head-strip">
        <div>
          <PanelTitle eyebrow="Experiments" title="实验编排" />
          <div className="model-semantic-chips compact">
            <span>参数网格批量实验</span>
            <span>{templates.length} 个模板</span>
            <span>{runs.length} 次运行</span>
          </div>
        </div>
        <button className="ghost-button small" type="button" onClick={() => loadAll(true)} disabled={loading}>
          <RefreshCw size={14} />
          {loading ? "刷新中" : "刷新"}
        </button>
      </div>

      <div className="agent-summary-grid">
        <MiniStat label="模板" value={templates.length} />
        <MiniStat label="运行记录" value={runs.length} />
        <MiniStat label="可运行模型" value={runnableModels.length} />
        <MiniStat label="可选来源任务" value={jobs.length} />
        <MiniStat
          label="选中模板组合"
          value={selectedTemplate ? combinationCount(selectedTemplate.param_grid) : "--"}
        />
      </div>

      <div className="agent-grid">
        {/* Create template */}
        <div className="panel agent-model-panel">
          <div className="agent-panel-head">
            <PanelTitle eyebrow="New" title="创建实验模板" />
          </div>
          <div className="exp-form">
            <label className="exp-field">
              <span>模板名称</span>
              <input value={formName} onChange={(e) => setFormName(e.target.value)} placeholder="例如：niter 扫描" />
            </label>
            <label className="exp-field">
              <span>模型</span>
              <select value={formModel} onChange={(e) => setFormModel(e.target.value)}>
                {runnableModels.map((model) => (
                  <option key={model.value} value={model.value}>
                    {model.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="exp-field">
              <span>输入类型</span>
              <select value={formSourceType} onChange={(e) => setFormSourceType(e.target.value)}>
                <option value="images">图片</option>
                <option value="video">视频</option>
                <option value="frames">帧序列</option>
              </select>
            </label>
            <label className="exp-field">
              <span>参数网格（每行 key: v1, v2）</span>
              <textarea value={formGrid} onChange={(e) => setFormGrid(e.target.value)} rows={3} />
            </label>
            <label className="exp-field">
              <span>基础参数（每行 key: value，可空）</span>
              <textarea value={formBase} onChange={(e) => setFormBase(e.target.value)} rows={2} />
            </label>
            <div className="model-semantic-chips compact">
              <span>预计 {combinationCount(parseGrid(formGrid))} 组任务</span>
            </div>
            <button className="primary-button small" type="button" onClick={createTemplate} disabled={busy}>
              <Plus size={14} />
              创建模板
            </button>
          </div>
        </div>

        {/* Run template */}
        <div className="panel agent-detail-panel">
          <div className="agent-panel-head">
            <PanelTitle eyebrow="Run" title="运行实验" />
          </div>
          {templates.length === 0 ? (
            <div className="empty-state">先创建一个实验模板</div>
          ) : (
            <div className="exp-form">
              <label className="exp-field">
                <span>模板</span>
                <select value={selectedTemplateId} onChange={(e) => setSelectedTemplateId(e.target.value)}>
                  {templates.map((template) => (
                    <option key={template.id} value={template.id}>
                      {template.name} · {template.model} · {combinationCount(template.param_grid)} 组
                    </option>
                  ))}
                </select>
              </label>
              <label className="exp-field">
                <span>来源任务（复用其输入文件）</span>
                <select value={sourceJobId} onChange={(e) => setSourceJobId(e.target.value)}>
                  <option value="">— 选择一个已有任务 —</option>
                  {jobs
                    .filter((item) => !selectedTemplate || item.job.source_type === selectedTemplate.source_type)
                    .map((item) => (
                      <option key={item.job.job_id} value={item.job.job_id}>
                        {item.job.job_id} · {item.job.model} · {item.job.status}
                      </option>
                    ))}
                </select>
              </label>
              <label className="exp-field">
                <span>运行名称</span>
                <input value={runName} onChange={(e) => setRunName(e.target.value)} placeholder="可空，自动生成" />
              </label>
              <label className="exp-checkbox">
                <input type="checkbox" checked={autoDispatch} onChange={(e) => setAutoDispatch(e.target.checked)} />
                <span>创建后立即派发到远端（否则留在队列待手动运行）</span>
              </label>
              <button className="primary-button small" type="button" onClick={runTemplate} disabled={busy}>
                <Play size={14} />
                运行实验
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="agent-grid">
        {/* Templates list */}
        <div className="panel agent-model-panel">
          <div className="agent-panel-head">
            <PanelTitle eyebrow="Templates" title="实验模板" />
            <StatusBadge state="ready" label={`${templates.length}`} />
          </div>
          {templates.length === 0 ? (
            <div className="empty-state">暂无模板</div>
          ) : (
            <div className="agent-model-list">
              {templates.map((template) => (
                <div
                  key={template.id}
                  className={`agent-model-row ${selectedTemplateId === template.id ? "active" : ""}`}
                >
                  <span className="agent-model-main">
                    <strong>{template.name}</strong>
                    <small>
                      {template.model} · {template.source_type} · {combinationCount(template.param_grid)} 组 ·{" "}
                      {Object.keys(template.param_grid).join(", ") || "无网格"}
                    </small>
                  </span>
                  <span className="agent-model-meta">
                    <button className="ghost-button small" type="button" onClick={() => setSelectedTemplateId(template.id)}>
                      <FlaskConical size={13} />
                      选用
                    </button>
                    <button className="ghost-button small" type="button" onClick={() => deleteTemplate(template.id)} disabled={busy}>
                      <Trash2 size={13} />
                    </button>
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Runs list + summary */}
        <div className="panel agent-detail-panel">
          <div className="agent-panel-head">
            <PanelTitle eyebrow="Runs" title="运行记录" />
            <StatusBadge state="ready" label={`${runs.length}`} />
          </div>
          {runs.length === 0 ? (
            <div className="empty-state">暂无运行记录</div>
          ) : (
            <div className="agent-build-list">
              {runs.slice(0, 8).map((run) => (
                <div
                  className={`agent-build-row ${run.status}`}
                  key={run.id}
                  onClick={() => loadRunSummary(run.id)}
                  style={{ cursor: "pointer" }}
                >
                  <div>
                    <strong>{run.name}</strong>
                    <span>{run.id} · {run.jobIds.length} 任务</span>
                  </div>
                  <StatusBadge state={runStatusBadge(run.status)} label={run.status} />
                  <span>
                    {String((run.metadata?.dispatched as number) ?? 0)} 已派发 · {String((run.metadata?.input_count as number) ?? 0)} 输入
                  </span>
                </div>
              ))}
            </div>
          )}

          {selectedRun && selectedRun.summary && (
            <div className="agent-check-result">
              <div className="agent-subhead">
                <span>汇总：{selectedRun.name}</span>
                <StatusBadge state="ready" label={`${selectedRun.summary.finished ?? 0}/${selectedRun.summary.total} 完成`} />
              </div>
              <div className="model-semantic-chips compact">
                <span>待派发 {selectedRun.summary.pending ?? 0}</span>
                <span>运行中 {selectedRun.summary.running ?? 0}</span>
                <span>完成 {selectedRun.summary.finished ?? 0}</span>
                <span>失败 {selectedRun.summary.failed ?? 0}</span>
              </div>
              <div className="agent-issue-list">
                {selectedRun.summary.jobs.map((job) => (
                  <div className="agent-issue-row" key={job.job_id}>
                    <span className="agent-issue-level">{job.status}</span>
                    <div className="agent-issue-body">
                      <strong>{job.job_id}</strong>
                      <small>{Object.entries(job.params).map(([k, v]) => `${k}=${String(v)}`).join(", ")}</small>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
