import { useEffect, useMemo, useState } from "react";
import type { SamplesPayload } from "./types";
import {
  findModelCatalogItem,
  formatCountMap,
  formatModelList,
  metricLabel,
  modelDisplayName,
  sampleStatusLabel,
  scoringCategoryLabel,
  sourceTypeLabel
} from "./displayHelpers";
import type { ModelCatalogItem } from "./displayHelpers";
import {
  buildSampleMatrixReport,
  collectSampleMatrixJobIds,
  compareSampleMatrixRows,
  matrixRowMatchesFilter,
  primaryArtifactHint,
  summarizeJobEvidence,
  summarizeMatrixRowEvidence,
  summarizeMatrixRowScore,
  summarizeSampleMatrixRow,
  summarizeScoreSnapshot
} from "./sampleMatrixHelpers";
import type {
  SampleMatrixFilterKey,
  SampleMatrixJob,
  SampleMatrixReportModelScope,
  SampleMatrixRowView,
  SampleMatrixSortKey
} from "./sampleMatrixHelpers";
import { downloadTextFile } from "./fileHelpers";
import { buildMatrixModelConstraint } from "./workflowHelpers";
import { ModelSemanticChips, SummaryStat } from "./uiPrimitives";

export function SampleMatrixPanel(props: {
  samplesPayload: SamplesPayload | null;
  errorMessage: string | null;
  modelCatalog: ModelCatalogItem[];
  onLocateJob?: (jobId: string) => void;
  onCopy?: (value: string, label: string) => Promise<void>;
  compact?: boolean;
}) {
  const [sortKey, setSortKey] = useState<SampleMatrixSortKey>("manifest");
  const [filterKey, setFilterKey] = useState<SampleMatrixFilterKey>("all");
  const [reportModelScope, setReportModelScope] = useState<SampleMatrixReportModelScope>("all");
  const [selectedSampleIds, setSelectedSampleIds] = useState<string[]>([]);
  const [batchLocateCursor, setBatchLocateCursor] = useState(0);
  const manifest = props.samplesPayload?.manifest ?? null;
  const summary = props.samplesPayload?.summary ?? null;
  const samples = manifest?.samples ?? [];
  const visibleSamples = props.compact ? samples.slice(0, 3) : samples;
  const scoringEntries = Object.entries(manifest?.scoring ?? {});
  const activeModels = manifest?.active_models ?? [];
  const deferredModels = manifest?.deferred_models ?? [];
  const compactScoringEntries = props.compact ? scoringEntries.slice(0, 3) : [];
  const statusCountEntries = Object.entries(summary?.status_counts ?? {}).sort(
    ([leftStatus, leftCount], [rightStatus, rightCount]) => rightCount - leftCount || leftStatus.localeCompare(rightStatus)
  );
  const jobMatrixRows = props.samplesPayload?.job_matrix?.rows ?? [];
  const unassignedJobs = props.samplesPayload?.job_matrix?.unassigned_jobs ?? [];
  const sampleRows = useMemo<SampleMatrixRowView[]>(() => {
    const matrix = new Map(jobMatrixRows.map((row) => [row.sample_id, row.jobs_by_model as Record<string, SampleMatrixJob>]));
    const rows = visibleSamples.map((sample, index) => {
      const jobsByModel = matrix.get(sample.id) ?? {};
      const requiredModels = sample.required_models ?? [];
      const requiredModelSet = new Set(requiredModels);
      const compareModels = Array.from(new Set([...(sample.required_models ?? []), ...(sample.optional_models ?? [])]));
      const rowStats = summarizeSampleMatrixRow(compareModels, jobsByModel);
      const rowScore = summarizeMatrixRowScore(compareModels, jobsByModel);
      const rowEvidence = summarizeMatrixRowEvidence(compareModels, jobsByModel);
      return {
        sample,
        rowIndex: index,
        jobsByModel,
        requiredModels,
        requiredModelSet,
        compareModels,
        rowStats,
        rowScore,
        rowEvidence
      };
    });
    const filteredRows = rows.filter((row) => matrixRowMatchesFilter(row, filterKey));
    return filteredRows.sort((left, right) => compareSampleMatrixRows(left, right, sortKey));
  }, [filterKey, jobMatrixRows, sortKey, visibleSamples]);
  const selectedSampleSet = useMemo(() => new Set(selectedSampleIds), [selectedSampleIds]);
  const selectedRows = useMemo(
    () => sampleRows.filter((row) => selectedSampleSet.has(row.sample.id)),
    [sampleRows, selectedSampleSet]
  );
  const batchTargetRows = useMemo(
    () => (selectedRows.length > 0 ? selectedRows : sampleRows),
    [sampleRows, selectedRows]
  );
  const batchTargetJobIds = useMemo(() => collectSampleMatrixJobIds(batchTargetRows), [batchTargetRows]);
  const allVisibleSelected = sampleRows.length > 0 && sampleRows.every((row) => selectedSampleSet.has(row.sample.id));
  const nextLocateIndex = batchTargetJobIds.length > 0 ? (batchLocateCursor % batchTargetJobIds.length) + 1 : 0;

  useEffect(() => {
    setSelectedSampleIds((current) => {
      const available = new Set(sampleRows.map((row) => row.sample.id));
      const next = current.filter((sampleId) => available.has(sampleId));
      return next.length === current.length ? current : next;
    });
  }, [sampleRows]);

  useEffect(() => {
    if (batchTargetJobIds.length === 0) {
      if (batchLocateCursor !== 0) {
        setBatchLocateCursor(0);
      }
      return;
    }
    if (batchLocateCursor >= batchTargetJobIds.length) {
      setBatchLocateCursor(0);
    }
  }, [batchLocateCursor, batchTargetJobIds.length]);

  function toggleSampleRowSelection(sampleId: string) {
    setSelectedSampleIds((current) =>
      current.includes(sampleId) ? current.filter((id) => id !== sampleId) : [...current, sampleId]
    );
    setBatchLocateCursor(0);
  }

  function toggleAllVisibleRows() {
    if (allVisibleSelected) {
      setSelectedSampleIds([]);
    } else {
      setSelectedSampleIds(sampleRows.map((row) => row.sample.id));
    }
    setBatchLocateCursor(0);
  }

  async function handleCopyBatchJobIds() {
    if (!props.onCopy || batchTargetJobIds.length === 0) {
      return;
    }
    const scopeLabel = selectedRows.length > 0 ? "选中样例任务ID" : "筛选样例任务ID";
    await props.onCopy(batchTargetJobIds.join("\n"), scopeLabel);
  }

  async function handleCopyCompareReport() {
    if (!props.onCopy || batchTargetRows.length === 0) {
      return;
    }
    const report = buildSampleMatrixReport(batchTargetRows, props.modelCatalog, {
      filterKey,
      generatedAt: new Date().toISOString(),
      manifestPurpose: manifest?.purpose,
      manifestUpdated: manifest?.last_updated ?? null,
      modelScope: reportModelScope,
      selectedRowCount: selectedRows.length,
      sortKey,
      visibleRowCount: sampleRows.length
    });
    await props.onCopy(report.markdown, "样例对比报告");
  }

  function handleDownloadCompareReport() {
    if (batchTargetRows.length === 0) {
      return;
    }
    const report = buildSampleMatrixReport(batchTargetRows, props.modelCatalog, {
      filterKey,
      generatedAt: new Date().toISOString(),
      manifestPurpose: manifest?.purpose,
      manifestUpdated: manifest?.last_updated ?? null,
      modelScope: reportModelScope,
      selectedRowCount: selectedRows.length,
      sortKey,
      visibleRowCount: sampleRows.length
    });
    downloadTextFile(report.fileName, report.markdown, "text/markdown;charset=utf-8");
  }

  function handleLocateNextBatchJob() {
    if (!props.onLocateJob || batchTargetJobIds.length === 0) {
      return;
    }
    const targetIndex = batchLocateCursor % batchTargetJobIds.length;
    props.onLocateJob(batchTargetJobIds[targetIndex]);
    setBatchLocateCursor((targetIndex + 1) % batchTargetJobIds.length);
  }

  return (
    <div className="samples-workspace">
      <div className="section-card">
        <div className="section-card-header">
          <div>
            <h3 className="section-card-title">样例清单与测评矩阵</h3>
            <p className="page-subtitle">{manifest?.purpose ?? "等待 API 返回共享样例计划"}</p>
          </div>
        </div>
        <div className="stats-grid" style={{ marginBottom: "16px" }}>
          <div className="stat-item">
            <span className="stat-label">样例数</span>
            <span className="stat-value">{summary?.sample_count ?? samples.length}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">活跃模型</span>
            <span className="stat-value">{activeModels.length}</span>
          </div>
          <div className="stat-item">
            <span className="stat-label">评分维度</span>
            <span className="stat-value">{scoringEntries.length}</span>
          </div>
        </div>
      </div>

      {props.errorMessage && !props.samplesPayload ? <div className="empty-state">{props.errorMessage}</div> : null}

      {manifest ? (
        <>
          <div className="sample-matrix-meta">
            <div>
              <span className="mini-label">更新时间</span>
              <strong>{manifest.last_updated ?? "未标记"}</strong>
            </div>
            <div>
              <span className="mini-label">状态分布</span>
              <p>{formatCountMap(summary?.status_counts, sampleStatusLabel)}</p>
            </div>
            <div>
              <span className="mini-label">输入类型</span>
              <p>{formatCountMap(summary?.source_counts, sourceTypeLabel)}</p>
            </div>
          </div>

          <div className="sample-model-strip">
            <div>
              <span className="mini-label">主线模型</span>
              <p>{formatModelList(activeModels, props.modelCatalog)}</p>
            </div>
            {deferredModels.length > 0 ? (
              <div>
                <span className="mini-label">暂缓模型</span>
                <p>{formatModelList(deferredModels, props.modelCatalog)}</p>
              </div>
            ) : null}
          </div>

          {compactScoringEntries.length > 0 ? (
            <div className="scoring-compact-strip" aria-label="评分维度快览">
              {compactScoringEntries.map(([key, metrics]) => (
                <div key={key}>
                  <strong>{scoringCategoryLabel(key)}</strong>
                  <span>{metrics.length} 项指标</span>
                </div>
              ))}
            </div>
          ) : null}

          {visibleSamples.length > 0 ? (
            <section className="sample-compare-section" aria-label="样例对比视图">
              <div className="sample-compare-head">
                <div>
                  <span className="mini-label">样例对比</span>
                  <strong>样例、模型、任务入口</strong>
                </div>
                <div className="sample-compare-side">
                  <div className="sample-status-strip" aria-label="当前状态计数">
                    {statusCountEntries.length > 0 ? (
                      statusCountEntries.map(([status, count]) => (
                        <div className="sample-status-pill" key={status}>
                          <span>{sampleStatusLabel(status)}</span>
                          <strong>{count}</strong>
                        </div>
                      ))
                    ) : (
                      <div className="sample-status-pill empty">
                        <span>当前状态计数</span>
                        <strong>暂无</strong>
                      </div>
                    )}
                  </div>
                  {!props.compact ? (
                    <div className="sample-compare-tools">
                      <label className="field compact">
                        <span>排序</span>
                        <select
                          value={sortKey}
                          onChange={(event) => {
                            setSortKey(event.target.value as SampleMatrixSortKey);
                            setBatchLocateCursor(0);
                          }}
                        >
                          <option value="manifest">按样例清单</option>
                          <option value="completion">按完成度</option>
                          <option value="score">按评分均值</option>
                          <option value="attention">按待处理优先</option>
                        </select>
                      </label>
                      <label className="field compact">
                        <span>筛选</span>
                        <select
                          value={filterKey}
                          onChange={(event) => {
                            setFilterKey(event.target.value as SampleMatrixFilterKey);
                            setBatchLocateCursor(0);
                          }}
                        >
                          <option value="all">全部样例</option>
                          <option value="attention">仅看待处理</option>
                          <option value="running">仅看运行中</option>
                          <option value="unfinished">仅看未完成</option>
                        </select>
                      </label>
                    </div>
                  ) : null}
                </div>
              </div>

              {!props.compact ? (
                <div className="sample-bulk-strip" aria-label="样例矩阵批量操作">
                  <div className="sample-bulk-summary">
                    <span className="mini-label">批量操作</span>
                    <strong>
                      {selectedRows.length > 0
                        ? `已选 ${selectedRows.length} 行样例`
                        : `未选择行，默认作用于当前筛选 ${sampleRows.length} 行`}
                    </strong>
                    <p>{batchTargetJobIds.length > 0 ? `可操作任务ID：${batchTargetJobIds.length}` : "当前范围还没有任务ID。"}</p>
                  </div>
                  <div className="sample-bulk-actions">
                    <label className="field compact sample-report-scope">
                      <span>报告模型</span>
                      <select value={reportModelScope} onChange={(event) => setReportModelScope(event.target.value as SampleMatrixReportModelScope)}>
                        <option value="all">全部列</option>
                        <option value="required">必跑列</option>
                        <option value="with_jobs">有任务列</option>
                        <option value="finished">已完成列</option>
                      </select>
                    </label>
                    <button className="ghost-button small" onClick={toggleAllVisibleRows} type="button">
                      {allVisibleSelected ? "取消全选" : "全选筛选行"}
                    </button>
                    <button
                      className="ghost-button small"
                      disabled={!props.onCopy || batchTargetJobIds.length === 0}
                      onClick={() => void handleCopyBatchJobIds()}
                      type="button"
                    >
                      复制任务ID
                    </button>
                    <button
                      className="ghost-button small"
                      disabled={!props.onCopy || batchTargetRows.length === 0}
                      onClick={() => void handleCopyCompareReport()}
                      type="button"
                    >
                      复制报告
                    </button>
                    <button className="ghost-button small" disabled={batchTargetRows.length === 0} onClick={handleDownloadCompareReport} type="button">
                      导出报告
                    </button>
                    <button
                      className="ghost-button small"
                      disabled={!props.onLocateJob || batchTargetJobIds.length === 0}
                      onClick={handleLocateNextBatchJob}
                      type="button"
                    >
                      定位下一条
                    </button>
                    {batchTargetJobIds.length > 0 ? (
                      <span className="sample-bulk-cursor">
                        游标 {nextLocateIndex}/{batchTargetJobIds.length}
                      </span>
                    ) : null}
                  </div>
                </div>
              ) : null}

              <div className="sample-compare-grid">
                {sampleRows.map((row) => {
                  const { sample, jobsByModel, requiredModels, requiredModelSet, compareModels, rowStats, rowScore, rowEvidence } = row;
                  return (
                    <article className="sample-compare-row" key={sample.id}>
                      <div className="sample-compare-main">
                        <span className="sample-axis-label">样例行</span>
                        <div className="sample-card-head">
                          <div className="sample-card-head-main">
                            {!props.compact ? (
                              <input
                                className="sample-row-checkbox"
                                type="checkbox"
                                checked={selectedSampleSet.has(sample.id)}
                                onChange={() => toggleSampleRowSelection(sample.id)}
                                aria-label={`选择样例 ${sample.id}`}
                              />
                            ) : null}
                            <strong>{sample.id}</strong>
                          </div>
                          <span className="status-badge">{sampleStatusLabel(sample.status)}</span>
                        </div>
                        <p>{sample.purpose}</p>
                        <div className="sample-card-meta">
                          <span>{sourceTypeLabel(sample.source_type)}</span>
                          <span>{sample.target_file_count ? `${sample.target_file_count} 个文件` : `${sample.target_duration_seconds ?? "-"} 秒`}</span>
                        </div>
                        <div className="sample-row-digest" aria-label={`${sample.id} 对比摘要`}>
                          <div className={`sample-row-digest-card ${rowScore.tone}`}>
                            <span>评分</span>
                            <strong>{rowScore.average !== null ? rowScore.average.toFixed(2) : "--"}</strong>
                            <small>{rowScore.metricCount > 0 ? `${rowScore.metricCount} 项指标` : "暂无评分"}</small>
                          </div>
                          <div className={`sample-row-digest-card ${rowEvidence.tone}`}>
                            <span>证据</span>
                            <strong>
                              {rowEvidence.ready}/{rowEvidence.total}
                            </strong>
                            <small>{rowEvidence.label}</small>
                          </div>
                          <div className="sample-row-digest-card neutral">
                            <span>模型</span>
                            <strong>
                              {requiredModels.length}/{compareModels.length}
                            </strong>
                            <small>必跑 / 总数</small>
                          </div>
                        </div>
                        <div className="sample-row-progress" aria-label={`${sample.id} 执行进度`}>
                          <div className="sample-row-progress-head">
                            <span>矩阵完成度</span>
                            <strong>
                              {rowStats.finished}/{rowStats.total}
                            </strong>
                          </div>
                          <div className="sample-row-progress-track">
                            <div className="sample-row-progress-fill" style={{ width: `${rowStats.completionPercent}%` }} />
                          </div>
                          <div className="sample-row-progress-meta">
                            <span>运行 {rowStats.running}</span>
                            <span>待处理 {rowStats.attention}</span>
                            <span>待派发 {rowStats.pending}</span>
                            <span>缺失 {rowStats.missing}</span>
                            <span>{rowScore.metricCount > 0 ? `均分 ${rowScore.average?.toFixed(2)}` : "均分 --"}</span>
                          </div>
                        </div>
                        <div className="sample-card-models sample-required-models">
                          {requiredModels.length > 0 ? (
                            requiredModels.map((model) => <span key={model}>{modelDisplayName(model, props.modelCatalog)}</span>)
                          ) : (
                            <span>未标记必跑模型</span>
                          )}
                        </div>
                        <p className="sample-compare-status-copy">
                          {sampleStatusLabel(sample.status)}
                          {sample.seed_job_id ? " · 已关联 seed 任务" : " · 尚未关联 seed 任务"}
                        </p>
                        <div className={`sample-seed-callout ${sample.seed_job_id ? "available" : "missing"}`}>
                          <span className="mini-label">任务定位</span>
                          {sample.seed_job_id ? (
                            <>
                              <strong>{sample.seed_job_id}</strong>
                              {props.onLocateJob ? (
                                <button className="ghost-button small sample-locate-button" onClick={() => props.onLocateJob?.(sample.seed_job_id!)} type="button">
                                  定位到任务中心
                                </button>
                              ) : null}
                            </>
                          ) : (
                            <p>当前还没有 seed 任务，先选样例或创建首条基准任务。</p>
                          )}
                        </div>
                      </div>

                      <div className="sample-compare-matrix">
                        <div className="sample-compare-matrix-head">
                          <div>
                            <span className="mini-label">模型列</span>
                            <p>
                              {rowStats.finished}/{rowStats.total} 完成，证据 {rowEvidence.ready}/{rowEvidence.total}
                            </p>
                          </div>
                        </div>
                        {compareModels.length > 0 ? (
                          <div className="sample-compare-matrix-stack">
                            <div className="sample-model-axis" aria-label={`${sample.id} 模型列索引`}>
                              {compareModels.map((model) => (
                                <span className={requiredModelSet.has(model) ? "required" : "optional"} key={`${sample.id}-${model}-axis`}>
                                  <strong>{modelDisplayName(model, props.modelCatalog)}</strong>
                                  <small>{requiredModelSet.has(model) ? "Required" : "Optional"}</small>
                                </span>
                              ))}
                            </div>
                            <div className="sample-compare-matrix-grid">
                              {compareModels.map((model) => {
                                const job = jobsByModel[model] as SampleMatrixJob | undefined;
                                const modelItem = findModelCatalogItem(model, props.modelCatalog);
                                const cellState = job?.status ?? "missing";
                                const scoreDigest = summarizeScoreSnapshot(job?.score_snapshot);
                                const evidenceDigest = summarizeJobEvidence(job);
                                const modelConstraint = modelItem ? buildMatrixModelConstraint(modelItem) : null;
                                return (
                                  <article className={`sample-model-cell ${cellState}`} key={`${sample.id}-${model}`}>
                                    <div className="sample-model-cell-head">
                                      <strong>{modelDisplayName(model, props.modelCatalog)}</strong>
                                      <span className={`sample-model-state ${cellState}`}>{job ? job.status_label : "未跑"}</span>
                                    </div>
                                    <ModelSemanticChips
                                      className="sample-model-semantics"
                                      compact
                                      item={modelItem}
                                      model={model}
                                    />
                                    {modelConstraint ? (
                                      <div className={`sample-model-constraint ${modelConstraint.tone}`}>
                                        <strong>{modelConstraint.label}</strong>
                                        <span>{modelConstraint.detail}</span>
                                      </div>
                                    ) : null}
                                    <p>{job?.progress_message || (job ? `阶段：${job.phase}` : "尚未创建对应任务。")}</p>
                                    <div className="sample-model-cell-meta">
                                      <span>{requiredModelSet.has(model) ? "Required" : "Optional"}</span>
                                      <span>{primaryArtifactHint(job?.primary_artifacts)}</span>
                                    </div>
                                    <div className={`sample-score-signal ${scoreDigest.tone}`}>
                                      <div>
                                        <strong>{scoreDigest.label}</strong>
                                        <span>{scoreDigest.metricCount > 0 ? `${scoreDigest.metricCount} 项指标` : "暂无评分数据"}</span>
                                      </div>
                                      <strong>{scoreDigest.percent > 0 ? `${scoreDigest.percent}%` : "--"}</strong>
                                    </div>
                                    <div className="sample-score-track" aria-hidden>
                                      <div className={`sample-score-fill ${scoreDigest.tone}`} style={{ width: `${scoreDigest.percent}%` }} />
                                    </div>
                                    <div className={`sample-evidence-signal ${evidenceDigest.tone}`}>
                                      <div>
                                        <strong>{evidenceDigest.label}</strong>
                                        <span>{evidenceDigest.detail}</span>
                                      </div>
                                      <strong>{evidenceDigest.countLabel}</strong>
                                    </div>
                                    <div className="sample-model-cell-meta">
                                      <span>{job?.job_id ? `任务：${job.job_id}` : "尚无任务记录"}</span>
                                      {job?.job_id && props.onLocateJob ? (
                                        <button className="ghost-button small sample-locate-button" onClick={() => props.onLocateJob?.(job.job_id)} type="button">
                                          定位任务
                                        </button>
                                      ) : null}
                                    </div>
                                  </article>
                                );
                              })}
                            </div>
                          </div>
                        ) : (
                          <div className="empty-state">暂无模型矩阵</div>
                        )}
                      </div>
                    </article>
                  );
                })}
              </div>
              {sampleRows.length === 0 ? <div className="empty-state">当前排序/筛选下暂无样例。</div> : null}
            </section>
          ) : (
            <div className="empty-state">样例清单还没有条目。</div>
          )}

          {!props.compact && scoringEntries.length > 0 ? (
            <div className="scoring-grid">
              {scoringEntries.map(([key, metrics]) => (
                <article className="scoring-card" key={key}>
                  <strong>{scoringCategoryLabel(key)}</strong>
                  <p>{metrics.map((metric) => metricLabel(metric)).join(" / ")}</p>
                </article>
              ))}
            </div>
          ) : null}

          {!props.compact && unassignedJobs.length > 0 ? (
            <section className="sample-unassigned-panel" aria-label="未归档任务池">
              <div className="sample-unassigned-head">
                <div>
                  <span className="mini-label">未归档任务池</span>
                  <strong>{unassignedJobs.length} 条任务还没有绑定样例</strong>
                </div>
                {props.onCopy ? (
                  <button
                    className="ghost-button small"
                    onClick={() => void props.onCopy?.(unassignedJobs.map((job) => job.job_id).join("\n"), "未归档任务ID")}
                    type="button"
                  >
                    复制ID
                  </button>
                ) : null}
              </div>
              <div className="sample-unassigned-grid">
                {unassignedJobs.slice(0, 8).map((job) => (
                  <article className={`sample-unassigned-card ${job.status}`} key={job.job_id}>
                    <div>
                      <strong>{job.job_id}</strong>
                      <span>{modelDisplayName(job.model, props.modelCatalog)} · {job.status_label}</span>
                    </div>
                    <ModelSemanticChips
                      catalog={props.modelCatalog}
                      className="sample-model-semantics"
                      compact
                      model={job.model}
                    />
                    <p>{job.progress_message || `阶段：${job.phase}`}</p>
                    {props.onLocateJob ? (
                      <button className="ghost-button small" onClick={() => props.onLocateJob?.(job.job_id)} type="button">
                        定位任务
                      </button>
                    ) : null}
                  </article>
                ))}
              </div>
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
