import { useEffect, useMemo, useState } from "react";
import type { AdvisorStatus, EvaluationPayload, JobPayload } from "./types";
import {
  describeOutput,
  fileExtensionLabel,
  formatDateTime,
  modelDisplayName,
  sourceTypeLabel,
  statusLabel
} from "./displayHelpers";
import type { ModelCatalogItem } from "./displayHelpers";
import { isAdvisorSuggested } from "./workflowHelpers";
import { ModelSemanticChips, StatusBadge } from "./uiPrimitives";
import { SummaryPanel } from "./SummaryPanel";
import { EvaluationPanel } from "./EvaluationPanel";
import { AdvisorPanel } from "./AdvisorWorkbench";
import {
  buildAdvisorCompactStatus,
  buildAttentionJobMessage,
  buildInspectorRhythm,
  buildOutputSections,
  countLogKeywordHits,
  countLogLines,
  currentStepLabel,
  getCriticalLogLine,
  getLatestLogLine,
  HighlightedLogTail
} from "./jobInspectorHelpers";

export type PreviewAsset = {
  url: string;
  name: string;
  kind: "image" | "video" | "pointcloud";
  note?: string;
};

type SceneMetaPayload = {
  jobId: string;
  model: string;
  sceneMeta: Record<string, unknown>;
};

type ContractCheckPayload = {
  jobId: string;
  contractCheck: {
    model: string;
    ok: boolean;
    download_mode?: string | null;
    required_files: string[];
    satisfied_files: string[];
    missing_files: string[];
    optional_present: string[];
    scene_meta_present: boolean;
    output_file_count: number;
  };
};

type ResultEvidenceState = {
  loading: boolean;
  error: string | null;
  sceneMeta: SceneMetaPayload | null;
  contractCheck: ContractCheckPayload | null;
};

export function JobDetail(props: {
  selectedJob: JobPayload;
  advisorState: AdvisorStatus;
  actionKey: string | null;
  savingEvaluation: boolean;
  canDispatch: boolean;
  running: boolean;
  assetUrl: (path: string) => string;
  onAction: (path: string, key: string) => Promise<void>;
  onSaveEvaluation: (jobId: string, payload: EvaluationPayload) => Promise<void>;
  onConfigureAdvisor: () => void;
  onOpenOutput: (relativePath: string) => Promise<void>;
  onPreviewAsset: (asset: PreviewAsset) => void;
  onCopy: (value: string, label: string) => Promise<void>;
  modelCatalog: ModelCatalogItem[];
}) {
  const job = props.selectedJob.job;
  const summary = props.selectedJob.result_summary;
  const latestLogLine = getLatestLogLine(props.selectedJob.logs);
  const criticalLogLine = getCriticalLogLine(props.selectedJob.logs);
  const [logQuery, setLogQuery] = useState("");
  const normalizedLogQuery = logQuery.trim().toLowerCase();
  const filteredLogs = useMemo(() => {
    if (!normalizedLogQuery) {
      return props.selectedJob.logs;
    }
    return props.selectedJob.logs.filter((log) => {
      const haystack = [log.name, log.relative_path, log.tail || ""].join("\n").toLowerCase();
      return haystack.includes(normalizedLogQuery);
    });
  }, [normalizedLogQuery, props.selectedJob.logs]);
  const totalLogLines = useMemo(() => countLogLines(props.selectedJob.logs), [props.selectedJob.logs]);
  const logKeywordHits = useMemo(
    () => countLogKeywordHits(props.selectedJob.logs, normalizedLogQuery),
    [normalizedLogQuery, props.selectedJob.logs]
  );
  const outputSections = useMemo(
    () => buildOutputSections(props.selectedJob.outputs, job.model, props.selectedJob.contract),
    [props.selectedJob.outputs, job.model, props.selectedJob.contract]
  );
  const progress = props.selectedJob.phase_display;
  const advisorSuggested = isAdvisorSuggested(job.status);
  const advisorReport = props.selectedJob.advisor_report ?? null;
  const attentionJob = job.status === "failed" || job.status === "cancelled";
  const batchActionBusy = props.actionKey?.startsWith("batch:") ?? false;
  const inspectorRhythm = buildInspectorRhythm(props.selectedJob, latestLogLine, criticalLogLine, advisorReport);
  const [evidence, setEvidence] = useState<ResultEvidenceState>({
    loading: false,
    error: null,
    sceneMeta: null,
    contractCheck: null
  });

  useEffect(() => {
    let cancelled = false;
    setEvidence((current) => ({ ...current, loading: true, error: null }));
    Promise.all([
      fetch(props.assetUrl(`/api/jobs/${job.job_id}/scene-meta`)),
      fetch(props.assetUrl(`/api/jobs/${job.job_id}/contract-check`))
    ])
      .then(async ([sceneResponse, contractResponse]) => {
        if (!sceneResponse.ok) throw new Error(`scene_meta 读取失败 (${sceneResponse.status})`);
        if (!contractResponse.ok) throw new Error(`输出合同检查失败 (${contractResponse.status})`);
        const [sceneMeta, contractCheck] = await Promise.all([
          sceneResponse.json() as Promise<SceneMetaPayload>,
          contractResponse.json() as Promise<ContractCheckPayload>
        ]);
        if (!cancelled) {
          setEvidence({ loading: false, error: null, sceneMeta, contractCheck });
        }
      })
      .catch((err: any) => {
        if (!cancelled) {
          setEvidence({ loading: false, error: err?.message || "结果证据读取失败", sceneMeta: null, contractCheck: null });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [job.job_id, props.assetUrl]);

  useEffect(() => {
    setLogQuery("");
  }, [job.job_id]);

  function scrollToInspectorSection(sectionId: string) {
    const target = document.getElementById(sectionId);
    if (!target) {
      return;
    }
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  return (
    <div className="detail-stack">
      <div className={`detail-hero ${job.status}`}>
        <div className="detail-hero-head">
          <div className="hero-copy">
            <div className="hero-badges">
              <StatusBadge state={job.status} label={statusLabel(job.status)} />
              <span className="hero-tag">{modelDisplayName(job.model, props.modelCatalog)}</span>
              <span className="hero-tag">{sourceTypeLabel(job.source_type)}</span>
            </div>
            <ModelSemanticChips
              catalog={props.modelCatalog}
              className="detail-model-semantics"
              compact
              model={job.model}
            />
            <h3>{progress.label}</h3>
            <p>{job.progress_message || progress.description}</p>
          </div>
          <div className="detail-score-block">
            <div className="detail-score">{progress.percent}%</div>
            <span>{currentStepLabel(progress.steps)}</span>
          </div>
        </div>

        <div className="hero-progress">
          <div className="hero-progress-track">
            <div className="hero-progress-fill" style={{ width: `${progress.percent}%` }} />
          </div>
          <div className="hero-progress-labels">
            <span>当前阶段：{progress.label}</span>
            <span>{job.job_id}</span>
          </div>
        </div>

        <div className="step-grid">
          {progress.steps.map((step, index) => (
            <article className={`step-card ${step.state}`} key={step.code}>
              <span className="step-index">{index + 1}</span>
              <strong>{step.label}</strong>
              <p>{step.hint}</p>
            </article>
          ))}
        </div>
      </div>

      <article className={`advisor-recommendation compact ${advisorSuggested ? "active" : ""}`}>
        <div>
          <span className="mini-label">辅助评估</span>
          <strong>{buildAdvisorCompactStatus(props.advisorState, advisorReport, advisorSuggested)}</strong>
        </div>
        <div className="advisor-workbench-actions">
          {!props.advisorState.enabled || !props.advisorState.configured ? (
            <button onClick={props.onConfigureAdvisor} type="button">
              配置
            </button>
          ) : null}
          {advisorReport?.teacher_talk ? (
            <button onClick={() => void props.onCopy(advisorReport.teacher_talk, "汇报话术")} type="button">
              复制汇报话术
            </button>
          ) : null}
          <button
            disabled={!props.advisorState.enabled || !props.advisorState.configured || !advisorSuggested || props.actionKey === "advisor"}
            onClick={() => props.onAction(`/api/jobs/${job.job_id}/advisor/evaluate`, "advisor")}
            type="button"
          >
            {props.actionKey === "advisor" ? "生成中..." : "生成草稿"}
          </button>
        </div>
      </article>

      <div className="action-row">
        <button
          disabled={!props.canDispatch || props.actionKey === "dispatch" || batchActionBusy}
          onClick={() => props.onAction(`/api/jobs/${job.job_id}/dispatch`, "dispatch")}
          type="button"
        >
          运行
        </button>
        <button
          disabled={props.running || props.actionKey === "retry" || batchActionBusy}
          onClick={() => props.onAction(`/api/jobs/${job.job_id}/retry`, "retry")}
          type="button"
        >
          重试
        </button>
        <button
          disabled={props.actionKey === "duplicate" || batchActionBusy}
          onClick={() => props.onAction(`/api/jobs/${job.job_id}/duplicate`, "duplicate")}
          type="button"
        >
          复制
        </button>
        <button
          className="danger"
          disabled={!props.running || props.actionKey === "cancel" || batchActionBusy}
          onClick={() => props.onAction(`/api/jobs/${job.job_id}/cancel`, "cancel")}
          type="button"
        >
          取消
        </button>
        <a className="ghost-button" download href={props.assetUrl(`/api/jobs/${job.job_id}/bundle`)}>
          导出包
        </a>
        <a className="ghost-button" download href={props.assetUrl(`/api/agent/experiment-record/${job.job_id}/download`)}>
          实验记录包
        </a>
      </div>

      {attentionJob ? (
        <article className={`attention-inspector ${job.status}`}>
          <div>
            <span className="mini-label">Attention</span>
            <strong>{job.status === "failed" ? "失败任务优先排查" : "已取消任务复查"}</strong>
            <p>{buildAttentionJobMessage(job.status, job.error_message, criticalLogLine, latestLogLine)}</p>
          </div>
          <div className="attention-inspector-actions">
            {job.error_message ? (
              <button className="ghost-button small" onClick={() => void props.onCopy(job.error_message ?? "", "错误原因")} type="button">
                复制错误
              </button>
            ) : null}
            {criticalLogLine ? (
              <button className="ghost-button small" onClick={() => void props.onCopy(criticalLogLine, "可疑日志")} type="button">
                复制可疑行
              </button>
            ) : null}
            {latestLogLine ? (
              <button className="ghost-button small" onClick={() => void props.onCopy(latestLogLine, "最新日志")} type="button">
                复制最新日志
              </button>
            ) : null}
            <button
              className="ghost-button small"
              disabled={props.running || props.actionKey === "retry" || batchActionBusy}
              onClick={() => props.onAction(`/api/jobs/${job.job_id}/retry`, "retry")}
              type="button"
            >
              {props.actionKey === "retry" ? "重试中..." : "重试任务"}
            </button>
          </div>
        </article>
      ) : null}

      <div className="inspector-nav-strip">
        <span className="mini-label">检查器导航</span>
        <div className="inspector-nav-actions">
          <button className="ghost-button small" type="button" onClick={() => scrollToInspectorSection("job-summary-panel")}>
            摘要
          </button>
          <button className="ghost-button small" type="button" onClick={() => scrollToInspectorSection("job-evidence-panel")}>
            证据链
          </button>
          <button className="ghost-button small" type="button" onClick={() => scrollToInspectorSection("job-outputs-panel")}>
            输出
          </button>
          <button className="ghost-button small" type="button" onClick={() => scrollToInspectorSection("job-logs-panel")}>
            日志
          </button>
          <button className="ghost-button small" type="button" onClick={() => scrollToInspectorSection("job-evaluation-panel")}>
            人工评分
          </button>
          <button className="ghost-button small" type="button" onClick={() => scrollToInspectorSection("job-ai-panel")}>
            辅助评估
          </button>
          <button className="ghost-button small" type="button" onClick={() => scrollToInspectorSection("job-inputs-panel")}>
            输入
          </button>
        </div>
      </div>

      {job.error_message ? (
        <article className="soft-panel error-panel">
          <h4>错误原因</h4>
          <p>{job.error_message}</p>
        </article>
      ) : null}

      <div className="detail-inspector-grid">
        <section className="detail-inspector-main">
          <article className="soft-panel inspector-panel" id="job-summary-panel">
            <div className="section-head">
              <div>
                <h4>结果摘要</h4>
              </div>
            </div>
            <SummaryPanel summary={props.selectedJob.result_summary} />
          </article>

          <article className="soft-panel inspector-panel" id="job-evidence-panel">
            <ResultEvidencePanel evidence={evidence} summary={summary} />
          </article>

          <article className="soft-panel inspector-panel" id="job-outputs-panel">
            <div className="section-head">
              <div>
                <h4>输出结果</h4>
              </div>
              <span className="section-pill">{props.selectedJob.outputs.length} 个文件</span>
            </div>
            {outputSections.length > 1 ? (
              <div className="output-anchor-strip">
                {outputSections.map((section) => (
                  <button
                    className="ghost-button small"
                    key={section.key}
                    onClick={() => scrollToInspectorSection(`job-output-group-${section.key}`)}
                    type="button"
                  >
                    {section.title}
                  </button>
                ))}
                <button className="ghost-button small" onClick={() => scrollToInspectorSection("job-logs-panel")} type="button">
                  跳到日志
                </button>
              </div>
            ) : null}
            {outputSections.length > 0 ? (
              <div className="output-section-list">
                {outputSections.map((section) => (
                  <details className={`output-section ${section.accent}`} id={`job-output-group-${section.key}`} key={section.key} open={section.defaultOpen}>
                    <summary>
                      <div>
                        <strong>{section.title}</strong>
                        <p>{section.description}</p>
                      </div>
                      <span className="section-pill">{section.items.length}</span>
                    </summary>
                    <div className="output-grid">
                      {section.items.map((output) => (
                        <article className="output-card" key={output.relative_path}>
                          {output.is_image ? (
                            <button
                              className="output-preview-button"
                              type="button"
                              onClick={() =>
                                props.onPreviewAsset({
                                  url: props.assetUrl(output.url),
                                  name: output.display_name,
                                  kind: "image",
                                  note: section.key === "masks" ? "动态掩膜" : undefined
                                })
                              }
                            >
                              <img className="output-preview" src={props.assetUrl(output.url)} alt={output.display_name} />
                            </button>
                          ) : output.is_video ? (
                            <button
                              className="output-preview-button"
                              type="button"
                              onClick={() =>
                                props.onPreviewAsset({
                                  url: props.assetUrl(output.url),
                                  name: output.display_name,
                                  kind: "video"
                                })
                              }
                            >
                              <div className="output-preview placeholder">VIDEO</div>
                            </button>
                          ) : output.is_pointcloud ? (
                            <button
                              className="output-preview-button"
                              type="button"
                              onClick={() =>
                                props.onPreviewAsset({
                                  url: props.assetUrl(output.url),
                                  name: output.display_name,
                                  kind: "pointcloud"
                                })
                              }
                            >
                              <div className="output-preview placeholder pointcloud">
                                <span className="pointcloud-icon">⬡</span>
                                <span>PLY</span>
                              </div>
                            </button>
                          ) : (
                            <div className="output-preview placeholder">
                              {output.is_model3d ? "GLB" : fileExtensionLabel(output.display_name)}
                            </div>
                          )}
                          <div>
                            <strong>{output.display_name}</strong>
                            <p>{describeOutput(output.display_name)}</p>
                            <div className="output-actions">
                              {output.is_image || output.is_video ? (
                                <button
                                  onClick={() =>
                                    props.onPreviewAsset({
                                      url: props.assetUrl(output.url),
                                      name: output.display_name,
                                      kind: output.is_video ? "video" : "image",
                                      note: section.key === "masks" ? "动态掩膜" : undefined
                                    })
                                  }
                                  type="button"
                                >
                                  预览
                                </button>
                              ) : output.is_pointcloud ? (
                                <button
                                  onClick={() =>
                                    props.onPreviewAsset({
                                      url: props.assetUrl(output.url),
                                      name: output.display_name,
                                      kind: "pointcloud"
                                    })
                                  }
                                  type="button"
                                >
                                  3D 预览
                                </button>
                              ) : null}
                              <a href={props.assetUrl(output.url)} download>
                                下载
                              </a>
                              <button onClick={() => props.onOpenOutput(output.relative_path)} type="button">
                                本地打开
                              </button>
                            </div>
                          </div>
                        </article>
                      ))}
                    </div>
                  </details>
                ))}
              </div>
            ) : (
              <span className="muted-text">结果回传后会出现在这里。</span>
            )}
          </article>

          <article className="soft-panel inspector-panel" id="job-logs-panel">
            <div className="section-head">
              <div>
                <h4>日志</h4>
              </div>
              <div className="logs-head-actions">
                <span className="section-pill">
                  {normalizedLogQuery
                    ? `命中 ${logKeywordHits}/${totalLogLines} 行 · ${filteredLogs.length}/${props.selectedJob.logs.length} 份`
                    : `${props.selectedJob.logs.length} 份`}
                </span>
                {latestLogLine ? (
                  <button className="ghost-button small" onClick={() => void props.onCopy(latestLogLine, "最新日志")} type="button">
                    复制最新
                  </button>
                ) : null}
                {criticalLogLine ? (
                  <button className="ghost-button small" onClick={() => void props.onCopy(criticalLogLine, "可疑日志")} type="button">
                    复制可疑行
                  </button>
                ) : null}
              </div>
            </div>
            {latestLogLine ? <div className="latest-log-banner">{latestLogLine}</div> : null}
            {criticalLogLine ? <div className="critical-log-banner">可疑日志：{criticalLogLine}</div> : null}
            <div className="log-filter-strip">
              <label className="field compact log-filter-field">
                <span>关键词</span>
                <input
                  type="search"
                  value={logQuery}
                  onChange={(event) => setLogQuery(event.target.value)}
                  placeholder="例如 error / timeout / cuda / oom"
                />
              </label>
              {normalizedLogQuery ? (
                <button className="ghost-button small" onClick={() => setLogQuery("")} type="button">
                  清除
                </button>
              ) : null}
            </div>
            {filteredLogs.length > 0 ? (
              <div className="log-list">
                {filteredLogs.map((log) => (
                  <div className="log-card" key={log.relative_path}>
                    <strong>{log.name}</strong>
                    <pre>
                      <HighlightedLogTail query={normalizedLogQuery} text={log.tail || "暂无日志。"} />
                    </pre>
                  </div>
                ))}
              </div>
            ) : props.selectedJob.logs.length > 0 ? (
              <div className="empty-state">没有匹配“{logQuery.trim()}”的日志。</div>
            ) : (
              <span className="muted-text">还没有日志。</span>
            )}
          </article>
        </section>

        <aside className="detail-inspector-rail">
          <article className="soft-panel inspector-panel inspector-rhythm-panel">
            <div className="section-head">
              <div>
                <h4>检查顺序</h4>
              </div>
            </div>
            <div className="inspector-rhythm-list">
              {inspectorRhythm.map((item) => (
                <button
                  className={`inspector-rhythm-card ${item.tone}`}
                  key={item.id}
                  onClick={() => scrollToInspectorSection(item.id)}
                  type="button"
                >
                  <div>
                    <span>{item.label}</span>
                    <strong>{item.status}</strong>
                  </div>
                  <p>{item.detail}</p>
                </button>
              ))}
            </div>
          </article>

          <article className="soft-panel inspector-panel">
            <div className="section-head">
              <div>
                <h4>检查器快照</h4>
              </div>
            </div>
            <div className="meta-grid inspector-meta-grid">
              <MetaCard label="创建时间" value={formatDateTime(job.created_at)} />
              <MetaCard label="输入数量" value={String(summary?.inputs?.count ?? job.input_items.length ?? 0)} />
              <MetaCard label="回传产物" value={String(summary?.artifacts?.length ?? props.selectedJob.outputs.length)} />
              <MetaCard label="最新日志" value={latestLogLine || "尚无有效日志"} compact />
            </div>
          </article>

          <article className="soft-panel inspector-panel" id="job-evaluation-panel">
            <h4>人工评分</h4>
            <EvaluationPanel
              evaluation={props.selectedJob.evaluation ?? null}
              jobId={job.job_id}
              saving={props.savingEvaluation}
              onSave={props.onSaveEvaluation}
            />
          </article>

          <article className="soft-panel inspector-panel" id="job-ai-panel">
            <h4>辅助评估</h4>
            <AdvisorPanel report={advisorReport} />
          </article>

          <article className="soft-panel inspector-panel" id="job-inputs-panel">
            <h4>输入</h4>
            <div className="preview-grid">
              {props.selectedJob.previews.length > 0 ? (
                props.selectedJob.previews.map((preview) => (
                  <button
                    key={preview.relative_path}
                    className="preview-card"
                    type="button"
                    onClick={() =>
                      props.onPreviewAsset({
                        url: props.assetUrl(preview.url),
                        name: preview.display_name,
                        kind: "image"
                      })
                    }
                  >
                    {preview.is_image ? <img src={props.assetUrl(preview.url)} alt={preview.display_name} /> : null}
                    <span>{preview.display_name}</span>
                  </button>
                ))
              ) : (
                <span className="muted-text">暂无输入预览。</span>
              )}
            </div>
          </article>
        </aside>
      </div>
    </div>
  );
}

function MetaCard(props: { label: string; value: string; compact?: boolean }) {
  return (
    <article className={`meta-card ${props.compact ? "compact" : ""}`}>
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </article>
  );
}

function ResultEvidencePanel(props: { evidence: ResultEvidenceState; summary: JobPayload["result_summary"] }) {
  const sceneMeta = props.evidence.sceneMeta?.sceneMeta ?? props.summary?.scene_meta ?? null;
  const contract = props.evidence.contractCheck?.contractCheck ?? null;
  const keyStats = buildSceneMetaStats(sceneMeta);
  const artifactCount = typeof sceneMeta?.["artifact_count"] === "number" ? sceneMeta["artifact_count"] : props.summary?.artifacts?.length ?? 0;
  const warnings = Array.isArray(sceneMeta?.["warnings"]) ? sceneMeta["warnings"] as unknown[] : [];

  return (
    <div className="result-evidence-panel">
      <div className="section-head">
        <div>
          <h4>结果证据链</h4>
          <p className="dense-text">scene_meta 归一化、输出合同检查和可复现实验记录共同说明本次任务产物是否完整。</p>
        </div>
        {props.evidence.loading ? (
          <span className="section-pill">读取中</span>
        ) : contract ? (
          <StatusBadge state={contract.ok ? "ready" : "degraded"} label={contract.ok ? "合同通过" : "合同缺失"} />
        ) : (
          <span className="section-pill">待检查</span>
        )}
      </div>

      {props.evidence.error ? <div className="critical-log-banner">{props.evidence.error}</div> : null}

      <div className="evidence-kpi-grid">
        <MetaCard label="合同状态" value={contract ? (contract.ok ? "PASS" : "MISSING") : "--"} />
        <MetaCard label="必需产物" value={contract ? `${contract.satisfied_files.length}/${contract.required_files.length}` : "--"} />
        <MetaCard label="scene_meta" value={contract ? (contract.scene_meta_present ? "已归档" : "缺失") : sceneMeta ? "已归档" : "--"} />
        <MetaCard label="输出文件" value={String(contract?.output_file_count ?? artifactCount)} />
      </div>

      {keyStats.length > 0 ? (
        <div className="evidence-stat-strip">
          {keyStats.map((item) => (
            <MetaCard key={item.label} label={item.label} value={item.value} />
          ))}
        </div>
      ) : null}

      <div className="evidence-two-col">
        <div className="evidence-block">
          <span className="mini-label">Required Outputs</span>
          {contract && contract.required_files.length > 0 ? (
            <div className="contract-file-list">
              {contract.required_files.map((file) => {
                const ok = contract.satisfied_files.includes(file);
                return (
                  <div className={`contract-file-row ${ok ? "ok" : "missing"}`} key={file}>
                    <span>{ok ? "OK" : "MISS"}</span>
                    <strong>{file}</strong>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="dense-text muted-text">该模型没有登记强制下载文件。</p>
          )}
        </div>

        <div className="evidence-block">
          <span className="mini-label">Scene Meta</span>
          {sceneMeta ? (
            <div className="scene-meta-list">
              {buildSceneMetaRows(sceneMeta).map((item) => (
                <div key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </div>
              ))}
            </div>
          ) : (
            <p className="dense-text muted-text">暂无 scene_meta，可在结果回传后自动生成。</p>
          )}
        </div>
      </div>

      {warnings.length > 0 ? (
        <div className="evidence-warning-list">
          <span className="mini-label">Warnings</span>
          {warnings.slice(0, 4).map((warning, index) => (
            <div className="overview-callout warning" key={`${String(warning)}-${index}`}>
              <p className="dense-text">{String(warning)}</p>
            </div>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function buildSceneMetaStats(sceneMeta: Record<string, unknown> | null) {
  if (!sceneMeta) return [];
  return [
    statFromSceneMeta(sceneMeta, "input_count", "输入"),
    statFromSceneMeta(sceneMeta, "artifact_count", "产物"),
    statFromSceneMeta(sceneMeta, "glb_count", "GLB"),
    statFromSceneMeta(sceneMeta, "image_count", "图像"),
    statFromSceneMeta(sceneMeta, "n_points", "点数"),
    statFromSceneMeta(sceneMeta, "point_count", "点数")
  ].filter(Boolean).slice(0, 5) as Array<{ label: string; value: string }>;
}

function statFromSceneMeta(sceneMeta: Record<string, unknown>, key: string, label: string) {
  const value = sceneMeta[key];
  return typeof value === "number" || typeof value === "string" ? { label, value: String(value) } : null;
}

function buildSceneMetaRows(sceneMeta: Record<string, unknown>) {
  const rows = [
    { key: "model", label: "模型" },
    { key: "source_type", label: "输入类型" },
    { key: "input_mode", label: "输入模式" },
    { key: "seq_name", label: "序列" },
    { key: "weights", label: "权重" },
    { key: "demo_output_dir", label: "远端输出" }
  ];
  return rows
    .map((row) => {
      const value = sceneMeta[row.key];
      if (value === undefined || value === null || value === "") return null;
      return { label: row.label, value: formatEvidenceValue(value) };
    })
    .filter(Boolean) as Array<{ label: string; value: string }>;
}

function formatEvidenceValue(value: unknown) {
  if (Array.isArray(value)) return value.map((item) => String(item)).join(" / ");
  if (typeof value === "object" && value !== null) return JSON.stringify(value);
  return String(value);
}