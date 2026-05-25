import { useCallback, useEffect, useState } from "react";
import type { CompareModelCell, ComparePacket } from "./types";
import type { ModelCatalogItem } from "./displayHelpers";
import { modelDisplayName } from "./displayHelpers";
import {
  compareCellStatusLabel,
  compareCellTone,
  compareSummaryText,
  primaryArtifactLabel,
  primaryArtifactUrl,
  scoreSnapshotDisplay,
  visualCountLabel,
  buildCompareReportFilename,
} from "./compareHelpers";
import { downloadTextFile } from "./fileHelpers";
import { StatusBadge, SummaryStat } from "./uiPrimitives";

export type CompareBoardProps = {
  sampleId: string | null;
  packet: ComparePacket | null;
  loading: boolean;
  error: string | null;
  modelCatalog: ModelCatalogItem[];
  apiBase: string;
  onInspectJob: (jobId: string) => void;
  onRefresh: () => void;
  onPreviewAsset?: (asset: { name: string; url: string; kind: string }) => void;
};

export function CompareBoard({
  sampleId,
  packet,
  loading,
  error,
  modelCatalog,
  apiBase,
  onInspectJob,
  onRefresh,
  onPreviewAsset,
}: CompareBoardProps) {
  const [reportCopied, setReportCopied] = useState(false);

  const handleCopyReport = useCallback(async () => {
    if (!packet?.reportMarkdown) return;
    try {
      await navigator.clipboard.writeText(packet.reportMarkdown);
      setReportCopied(true);
      setTimeout(() => setReportCopied(false), 2000);
    } catch {
      // ignore
    }
  }, [packet]);

  const handleDownloadReport = useCallback(() => {
    if (!packet?.reportMarkdown || !sampleId) return;
    const filename = buildCompareReportFilename(sampleId);
    downloadTextFile(filename, packet.reportMarkdown, "text/markdown;charset=utf-8");
  }, [packet, sampleId]);

  if (!sampleId) {
    return (
      <article className="panel compare-board-panel">
        <div className="compare-board-empty">
          <span className="mini-label">Compare Board</span>
          <strong>尚未选择对比样例</strong>
          <p>通过 Batch Compare 创建任务后，或从样例矩阵选择一个 sample_id 进入对比面板。</p>
        </div>
      </article>
    );
  }

  return (
    <article className="panel compare-board-panel">
      <div className="compare-board-head">
        <div className="compare-board-title">
          <span className="mini-label">Compare Board</span>
          <strong>{sampleId}</strong>
        </div>
        <div className="compare-board-actions">
          <button className="ghost-button small" onClick={onRefresh} disabled={loading}>
            {loading ? "加载中…" : "刷新"}
          </button>
          <button
            className="ghost-button small"
            onClick={handleCopyReport}
            disabled={!packet?.reportMarkdown}
          >
            {reportCopied ? "已复制" : "复制报告"}
          </button>
          <button
            className="ghost-button small"
            onClick={handleDownloadReport}
            disabled={!packet?.reportMarkdown}
          >
            下载报告
          </button>
        </div>
      </div>

      {error && <div className="compare-board-error">{error}</div>}

      {loading && !packet && (
        <div className="compare-board-loading">正在加载对比数据…</div>
      )}

      {packet && (
        <>
          <div className="compare-board-summary">
            <SummaryStat label="任务数" value={String(packet.summary.jobCount)} />
            <SummaryStat label="已完成" value={String(packet.summary.finished)} />
            <SummaryStat label="运行中" value={String(packet.summary.running)} />
            <SummaryStat label="待处理" value={String(packet.summary.attention)} />
            <SummaryStat label="视觉产物" value={String(packet.summary.visualCount)} />
            <SummaryStat
              label="均分"
              value={
                packet.summary.averageScore !== null
                  ? packet.summary.averageScore.toFixed(2)
                  : "--"
              }
            />
          </div>

          <div className="compare-board-summary-text">
            {compareSummaryText(packet.summary)}
          </div>

          {packet.modelCells.length === 0 ? (
            <div className="compare-board-empty-cells">
              <p>当前 sample_id 下没有任务记录。</p>
            </div>
          ) : (
            <div className="compare-board-grid">
              {packet.modelCells.map((cell) => (
                <ModelCellCard
                  key={cell.jobId || cell.job_id}
                  cell={cell}
                  modelCatalog={modelCatalog}
                  apiBase={apiBase}
                  onInspectJob={onInspectJob}
                  onPreviewAsset={onPreviewAsset}
                />
              ))}
            </div>
          )}
        </>
      )}
    </article>
  );
}

type ModelCellCardProps = {
  cell: CompareModelCell;
  modelCatalog: ModelCatalogItem[];
  apiBase: string;
  onInspectJob: (jobId: string) => void;
  onPreviewAsset?: (asset: { name: string; url: string; kind: string }) => void;
};

function ModelCellCard({
  cell,
  modelCatalog,
  apiBase,
  onInspectJob,
  onPreviewAsset,
}: ModelCellCardProps) {
  const jobId = cell.jobId || cell.job_id;
  const tone = compareCellTone(cell.status);
  const statusLabel = compareCellStatusLabel(cell.status);
  const modelLabel = modelDisplayName(cell.model, modelCatalog);
  const primaryLabel = primaryArtifactLabel(cell);
  const primaryUrl = primaryArtifactUrl(cell, apiBase);
  const visuals = cell.visuals || [];
  const scoreDisplay = scoreSnapshotDisplay(cell.scoreSnapshot || cell.score_snapshot);

  const previewableVisuals = visuals.filter(
    (v) => v.kind === "image" || v.kind === "video"
  );

  const handlePreview = (v: { name: string; url: string; kind: string }) => {
    if (onPreviewAsset) {
      const fullUrl = v.url.startsWith("http") ? v.url : `${apiBase}/${v.url.replace(/^\//, "")}`;
      onPreviewAsset({ name: v.name, url: fullUrl, kind: v.kind });
    }
  };

  return (
    <article className={`compare-cell-card ${tone}`}>
      <div className="compare-cell-head">
        <strong>{modelLabel}</strong>
        <StatusBadge state={cell.status} label={statusLabel} />
      </div>

      <div className="compare-cell-meta">
        <span>任务 {jobId}</span>
        <span>{cell.phase}</span>
      </div>

      {cell.progressMessage || cell.progress_message ? (
        <p className="compare-cell-progress">
          {cell.progressMessage || cell.progress_message}
        </p>
      ) : null}

      <div className="compare-cell-primary">
        <span className="mini-label">核心产物</span>
        <strong>{primaryLabel}</strong>
        {primaryUrl && (
          <div className="compare-cell-primary-thumb">
            {(cell.primaryArtifacts?.[0] as any)?.kind === "image" ||
            (cell.visuals?.[0]?.kind === "image") ? (
              <img
                src={primaryUrl}
                alt={primaryLabel}
                onClick={() =>
                  handlePreview({ name: primaryLabel, url: primaryUrl, kind: "image" })
                }
              />
            ) : (
              <div className="compare-cell-placeholder">
                {(cell.primaryArtifacts?.[0] as any)?.kind || cell.visuals?.[0]?.kind || "data"}
              </div>
            )}
          </div>
        )}
      </div>

      {previewableVisuals.length > 0 && (
        <div className="compare-cell-visuals">
          <span className="mini-label">{visualCountLabel(visuals.length)}</span>
          <div className="compare-cell-visual-strip">
            {previewableVisuals.slice(0, 4).map((v, idx) => (
              <div
                key={idx}
                className="compare-cell-visual-thumb"
                onClick={() => handlePreview(v)}
              >
                {v.kind === "image" ? (
                  <img
                    src={v.url.startsWith("http") ? v.url : `${apiBase}/${v.url.replace(/^\//, "")}`}
                    alt={v.name}
                  />
                ) : (
                  <div className="compare-cell-placeholder video">{v.kind}</div>
                )}
              </div>
            ))}
            {previewableVisuals.length > 4 && (
              <span className="compare-cell-visual-more">
                +{previewableVisuals.length - 4}
              </span>
            )}
          </div>
        </div>
      )}

      <div className="compare-cell-score">
        <span className="mini-label">评分</span>
        <strong>{scoreDisplay}</strong>
      </div>

      <div className="compare-cell-actions">
        <button
          className="ghost-button small"
          onClick={() => onInspectJob(jobId)}
        >
          检视任务
        </button>
      </div>
    </article>
  );
}

export type CompareBoardInlineProps = {
  sampleId: string;
  apiBase: string;
  modelCatalog: ModelCatalogItem[];
  onInspectJob: (jobId: string) => void;
  onPreviewAsset?: (asset: { name: string; url: string; kind: string }) => void;
  onClose?: () => void;
};

export function CompareBoardInline({
  sampleId,
  apiBase,
  modelCatalog,
  onInspectJob,
  onPreviewAsset,
  onClose,
}: CompareBoardInlineProps) {
  const [packet, setPacket] = useState<ComparePacket | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPacket = useCallback(async () => {
    if (!sampleId) return;
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(`${apiBase}/api/compare/samples/${encodeURIComponent(sampleId)}`);
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || `请求失败：${response.status}`);
      }
      const data: ComparePacket = await response.json();
      setPacket(data);
    } catch (e: any) {
      setError(e.message || "加载失败");
    } finally {
      setLoading(false);
    }
  }, [apiBase, sampleId]);

  useEffect(() => {
    fetchPacket();
  }, [fetchPacket]);

  useEffect(() => {
    if (!sampleId) return;
    const interval = setInterval(fetchPacket, 10000);
    return () => clearInterval(interval);
  }, [fetchPacket, sampleId]);

  return (
    <div className="compare-board-inline">
      {onClose && (
        <div className="compare-board-inline-close">
          <button className="ghost-button small" onClick={onClose}>
            关闭对比面板
          </button>
        </div>
      )}
      <CompareBoard
        sampleId={sampleId}
        packet={packet}
        loading={loading}
        error={error}
        modelCatalog={modelCatalog}
        apiBase={apiBase}
        onInspectJob={onInspectJob}
        onRefresh={fetchPacket}
        onPreviewAsset={onPreviewAsset}
      />
    </div>
  );
}
