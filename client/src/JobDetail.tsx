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
