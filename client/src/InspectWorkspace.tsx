import { useEffect, useMemo, useState } from "react";
import type { InspectionPacket, AdvisorStatus, EvaluationPayload, ResultArtifact } from "./types";
import { formatDateTime, modelDisplayName, sourceTypeLabel, statusLabel } from "./displayHelpers";
import { StatusBadge, ModelSemanticChips, MiniStat, PanelTitle } from "./uiPrimitives";
import { SummaryPanel } from "./SummaryPanel";
import { EvaluationPanel } from "./EvaluationPanel";
import { AdvisorPanel } from "./AdvisorWorkbench";
import { HighlightedLogTail } from "./jobInspectorHelpers";
import { ViserPanel } from "./ViserPanel";

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
  const [evidence, setEvidence] = useState<ResultEvidenceState>({
    loading: false,
    error: null,
    sceneMeta: null,
    contractCheck: null
  });
  const normalizedLogQuery = logQuery.trim().toLowerCase();

  useEffect(() => {
    let cancelled = false;
    setEvidence((current) => ({ ...current, loading: true, error: null }));
    Promise.all([
      fetch(assetUrl(`/api/jobs/${job.job_id}/scene-meta`)),
      fetch(assetUrl(`/api/jobs/${job.job_id}/contract-check`))
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
          setEvidence({
            loading: false,
            error: err?.message || "结果证据读取失败",
            sceneMeta: null,
            contractCheck: null
          });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [assetUrl, job.job_id]);

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

      <main className="inspect-main">
        <section className="inspect-pane center artifacts-pane">
          <PanelTitle eyebrow="Artifacts" title="产物与证据" />

          {details.viserSupported && (
            <div>
              <ViserPanel jobId={job.job_id} />
            </div>
          )}

          <div className="primary-artifacts-strip">
            {(artifactIndex?.primaryArtifacts ?? []).map((art) => {
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
                  {art.kind === 'image' && <img src={assetUrl(art.relativePath)} alt={art.label} />}
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

          <ResultEvidencePanel evidence={evidence} summary={inspection.result_summary ?? null} />

          <div className="artifact-groups">
            {(artifactIndex?.groups ?? []).map((group) => {
              const groupArtifacts = group.artifacts ?? [];
              return (
              <details key={group.key} className="output-section blue" open>
                <summary>
                  <div>
                    <strong>{group.label}</strong>
                    <p className="dense-text">{group.description}</p>
                  </div>
                  <span className="section-pill">{groupArtifacts.length}</span>
                </summary>
                <div className="output-grid">
                  {groupArtifacts.map((art) => (
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
              );
            })}
          </div>
        </section>

        <section className="inspect-pane analysis-pane">
          <PanelTitle eyebrow="Analysis" title="日志与评估" />

          <div className="analysis-grid">
            <details className="advanced-panel" open>
              <summary>辅助评估 (Advisor)</summary>
              <div className="analysis-panel-body">
                <AdvisorPanel report={advisorReport ?? null} />
                <div className="advisor-workbench-actions">
                  <button className="ghost-button small" onClick={onConfigureAdvisor}>配置</button>
                  <button className="primary-button small" onClick={() => onAction(`/api/jobs/${job.job_id}/advisor/evaluate`, 'advisor')}>重新评估</button>
                </div>
              </div>
            </details>

            <details className="advanced-panel" open>
              <summary>人工评分 (Evaluation)</summary>
              <div className="analysis-panel-body">
                <EvaluationPanel
                  evaluation={evaluation ?? null}
                  jobId={job.job_id}
                  saving={savingEvaluation}
                  onSave={onSaveEvaluation}
                />
              </div>
            </details>
          </div>

          <div className="logs-section">
            <div className="section-head">
              <strong>日志回传</strong>
              <input
                type="search"
                placeholder="搜索日志..."
                value={logQuery}
                onChange={e => setLogQuery(e.target.value)}
                className="dense-text log-search"
              />
            </div>
            <div className="log-list">
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
      </main>
    </div>
  );
}

function ResultEvidencePanel(props: { evidence: ResultEvidenceState; summary?: Record<string, any> | null }) {
  const sceneMeta = props.evidence.sceneMeta?.sceneMeta ?? props.summary?.scene_meta ?? null;
  const contract = props.evidence.contractCheck?.contractCheck ?? null;
  const keyStats = buildSceneMetaStats(sceneMeta);
  const artifactCount = typeof sceneMeta?.["artifact_count"] === "number" ? sceneMeta["artifact_count"] : props.summary?.artifacts?.length ?? 0;
  const warnings = Array.isArray(sceneMeta?.["warnings"]) ? sceneMeta["warnings"] as unknown[] : [];

  return (
    <section className="result-evidence-panel inspect-evidence-panel">
      <div className="section-head">
        <div>
          <h4>结果证据链</h4>
          <p className="dense-text">scene_meta、输出合同和任务产物索引共同说明本次结果是否可审查。</p>
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
        <MiniStat label="合同状态" value={contract ? (contract.ok ? "PASS" : "MISSING") : "--"} />
        <MiniStat label="必需产物" value={contract ? `${contract.satisfied_files.length}/${contract.required_files.length}` : "--"} />
        <MiniStat label="scene_meta" value={contract ? (contract.scene_meta_present ? "已归档" : "缺失") : sceneMeta ? "已归档" : "--"} />
        <MiniStat label="输出文件" value={String(contract?.output_file_count ?? artifactCount)} />
      </div>

      {keyStats.length > 0 ? (
        <div className="evidence-stat-strip">
          {keyStats.map((item) => <MiniStat key={item.label} label={item.label} value={item.value} />)}
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
    </section>
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
