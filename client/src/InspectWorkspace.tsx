import { useMemo, useState } from "react";
import type { InspectionPacket, AdvisorStatus, EvaluationPayload, ResultArtifact } from "./types";
import { formatDateTime, modelDisplayName, sourceTypeLabel, statusLabel } from "./displayHelpers";
import { StatusBadge, ModelSemanticChips, MiniStat } from "./uiPrimitives";
import { SummaryPanel } from "./SummaryPanel";
import { EvaluationPanel } from "./EvaluationPanel";
import { AdvisorPanel } from "./AdvisorWorkbench";
import { HighlightedLogTail } from "./jobInspectorHelpers";

interface InspectWorkspaceProps {
  inspection: InspectionPacket;
  advisorState: AdvisorStatus;
  savingEvaluation: boolean;
  onSaveEvaluation: (jobId: string, payload: EvaluationPayload) => Promise<void>;
  onConfigureAdvisor: () => void;
  onAction: (path: string, key: string) => Promise<void>;
  onPreviewAsset: (asset: { url: string; name: string; kind: "image" | "video" }) => void;
  onOpenOutput: (path: string) => Promise<void>;
  assetUrl: (path: string) => string;
  modelCatalog: any[];
}

export function InspectWorkspace({ 
  inspection, 
  advisorState, 
  savingEvaluation, 
  onSaveEvaluation, 
  onConfigureAdvisor,
  onAction,
  onPreviewAsset,
  onOpenOutput,
  assetUrl,
  modelCatalog
}: InspectWorkspaceProps) {
  const { job, phaseDisplay, inspection: details, artifactIndex, logs, evaluation, advisorReport } = inspection;
  const [logQuery, setLogQuery] = useState("");
  const normalizedLogQuery = logQuery.trim().toLowerCase();

  const filteredLogs = useMemo(() => {
    if (!normalizedLogQuery) return logs;
    return logs.filter(l => (l.name + l.tail).toLowerCase().includes(normalizedLogQuery));
  }, [logs, normalizedLogQuery]);

  return (
    <div className="inspect-layout">
      {/* Column 1: Job Facts */}
      <aside className="inspect-pane facts-pane">
        <div className="sticky-header">
          <PanelTitle eyebrow="Job Facts" title={job.job_id} />
          <div className="badge-group" style={{ margin: '12px 0' }}>
            <StatusBadge state={job.status} label={statusLabel(job.status)} />
            <span className="hero-tag">{modelDisplayName(job.model, modelCatalog)}</span>
          </div>
          <ModelSemanticChips catalog={modelCatalog} model={job.model} compact />
        </div>

        <div className="facts-content" style={{ marginTop: '24px' }}>
          <div className="inspector-meta-grid">
            <MiniStat label="创建时间" value={formatDateTime(job.created_at)} />
            <MiniStat label="输入来源" value={sourceTypeLabel(job.source_type)} />
            <MiniStat label="输入数量" value={String(job.input_files.length)} />
            <MiniStat label="进度" value={`${phaseDisplay.percent}%`} />
          </div>

          {details.attention.length > 0 && (
            <section className="attention-list" style={{ marginTop: '24px' }}>
              <span className="mini-label">需要关注</span>
              {details.attention.map((item, i) => {
                const kind = item.kind || (item.level === 'error' ? 'error' : 'warning');
                const label = item.label || item.title || (kind === 'error' ? '错误' : '警告');
                return (
                  <div key={i} className={`overview-callout ${kind === 'error' ? 'danger' : 'warning'}`} style={{ marginTop: '8px' }}>
                    <strong>{label}</strong>
                    <p className="dense-text">{item.detail}</p>
                  </div>
                );
              })}
            </section>
          )}

          <section className="actions-list" style={{ marginTop: '24px' }}>
            <span className="mini-label">推荐行动</span>
            <div className="support-checklist" style={{ marginTop: '8px' }}>
              {details.recommendedActions.map((action, i) => {
                if (typeof action === 'string') {
                  return (
                    <div key={i} className="overview-callout info" style={{ marginBottom: '8px', padding: '8px', borderLeft: '3px solid var(--brand-accent)' }}>
                      <p className="dense-text">{action}</p>
                    </div>
                  );
                }
                return (
                  <button 
                    key={action.key} 
                    className={action.primary ? "primary-button small" : "ghost-button small"}
                    onClick={() => onAction(action.target, action.key)}
                    style={{ width: '100%', justifyContent: 'center', marginBottom: '8px' }}
                  >
                    {action.label}
                  </button>
                );
              })}
            </div>
          </section>
        </div>
      </aside>

      {/* Column 2: Artifacts & Results */}
      <section className="inspect-pane center artifacts-pane">
        <PanelTitle eyebrow="Artifacts" title="产物与分组" />
        
        <div className="primary-artifacts-strip" style={{ display: 'flex', gap: '12px', overflowX: 'auto', padding: '12px 0' }}>
          {artifactIndex.primaryArtifacts.map((art) => {
            const isImageOrVideo = art.kind === 'image' || art.kind === 'video';
            return (
              <div 
                key={art.relativePath} 
                className={`primary-art-card ${isImageOrVideo ? 'clickable' : ''}`} 
                onClick={() => {
                  if (art.kind === 'image' || art.kind === 'video') {
                    onPreviewAsset({ url: assetUrl(art.relativePath), name: art.label, kind: art.kind });
                  }
                }}
              >
                {art.kind === 'image' && <img src={assetUrl(art.relativePath)} alt={art.label} style={{ width: '120px', height: '80px', objectFit: 'cover', borderRadius: '8px' }} />}
                <div className="dense-text">
                  <strong>{art.label}</strong>
                  {!isImageOrVideo && (
                    <div style={{ marginTop: '4px' }}>
                      <button className="ghost-button small" onClick={(e) => { e.stopPropagation(); onOpenOutput(art.relativePath); }}>打开</button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        <div className="artifact-groups" style={{ marginTop: '24px' }}>
          {artifactIndex.groups.map((group) => (
            <details key={group.key} className="output-section blue" open>
              <summary>
                <div>
                  <strong>{group.label}</strong>
                  <p className="dense-text">{group.description}</p>
                </div>
                <span className="section-pill">{group.artifacts.length}</span>
              </summary>
              <div className="output-grid">
                {group.artifacts.map((art) => (
                  <div key={art.relativePath} className="output-card">
                    <div className="dense-text">
                      <strong>{art.name}</strong>
                      <p>{art.note || art.role}</p>
                      <div className="output-actions">
                        {(art.kind === 'image' || art.kind === 'video') && (
                          <button onClick={() => {
                            if (art.kind === 'image' || art.kind === 'video') {
                              onPreviewAsset({ url: assetUrl(art.relativePath), name: art.name, kind: art.kind });
                            }
                          }}>预览</button>
                        )}
                        <button onClick={() => onOpenOutput(art.relativePath)}>打开</button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </details>
          ))}
        </div>
      </section>

      {/* Column 3: Analysis & Logs */}
      <section className="inspect-pane analysis-pane">
        <PanelTitle eyebrow="Analysis" title="日志与评估" />
        
        <details className="advanced-panel" open>
          <summary>辅助评估 (Advisor)</summary>
          <div style={{ padding: '12px' }}>
            <AdvisorPanel report={advisorReport ?? null} />
            <div className="advisor-workbench-actions" style={{ marginTop: '12px' }}>
              <button className="ghost-button small" onClick={onConfigureAdvisor}>配置</button>
              <button className="primary-button small" onClick={() => onAction(`/api/jobs/${job.job_id}/advisor/evaluate`, 'advisor')}>重新评估</button>
            </div>
          </div>
        </details>

        <details className="advanced-panel" style={{ marginTop: '16px' }} open>
          <summary>人工评分 (Evaluation)</summary>
          <div style={{ padding: '12px' }}>
            <EvaluationPanel 
              evaluation={evaluation ?? null} 
              jobId={job.job_id} 
              saving={savingEvaluation} 
              onSave={onSaveEvaluation} 
            />
          </div>
        </details>

        <div className="logs-section" style={{ marginTop: '24px' }}>
          <div className="section-head">
            <strong>日志回传</strong>
            <input 
              type="search" 
              placeholder="搜索日志..." 
              value={logQuery} 
              onChange={e => setLogQuery(e.target.value)}
              className="dense-text"
              style={{ padding: '4px 8px', borderRadius: '4px', border: '1px solid var(--line-default)' }}
            />
          </div>
          <div className="log-list" style={{ marginTop: '12px', maxHeight: '400px', overflowY: 'auto' }}>
            {filteredLogs.map((log) => (
              <div key={log.relative_path} className="log-card">
                <small>{log.name}</small>
                <pre className="dense-text">
                  <HighlightedLogTail query={normalizedLogQuery} text={log.tail} />
                </pre>
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  );
}

function PanelTitle({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="panel-title">
      <span className="mini-label">{eyebrow}</span>
      <h2 style={{ fontSize: '20px', fontWeight: 700, margin: '4px 0' }}>{title}</h2>
    </div>
  );
}
