import type { CompareModelCell, ComparePacket, CompareSummary, CompareVisual } from "./types";
import type { ModelCatalogItem } from "./displayHelpers";

export type CompareCellTone = "ready" | "running" | "attention" | "missing" | "neutral";

export function compareCellTone(status: string | undefined): CompareCellTone {
  if (!status) return "missing";
  if (status === "finished") return "ready";
  if (status === "running") return "running";
  if (status === "failed" || status === "cancelled") return "attention";
  return "neutral";
}

export function compareCellStatusLabel(status: string | undefined): string {
  if (!status) return "未创建";
  const labels: Record<string, string> = {
    created: "已创建",
    ready: "就绪",
    running: "运行中",
    finished: "已完成",
    failed: "失败",
    cancelled: "已取消",
  };
  return labels[status] || status;
}

export function scoreSnapshotAverage(snapshot: Record<string, number> | undefined): number | null {
  if (!snapshot) return null;
  const values = Object.values(snapshot).filter((v) => typeof v === "number");
  if (values.length === 0) return null;
  return values.reduce((sum, v) => sum + v, 0) / values.length;
}

export function scoreSnapshotDisplay(snapshot: Record<string, number> | undefined): string {
  const avg = scoreSnapshotAverage(snapshot);
  if (avg === null) return "--";
  return avg.toFixed(1);
}

export function visualCountLabel(count: number): string {
  if (count === 0) return "无视觉产物";
  if (count === 1) return "1 个产物";
  return `${count} 个产物`;
}

export function primaryArtifactLabel(cell: CompareModelCell): string {
  const arts = cell.primaryArtifacts || cell.primary_artifacts || [];
  if (arts.length === 0) return "无核心产物";
  return arts[0].label || arts[0].name || arts[0].relative_path;
}

export function primaryArtifactUrl(cell: CompareModelCell, apiBase: string): string | null {
  const arts = cell.primaryArtifacts || cell.primary_artifacts || [];
  if (arts.length === 0) return null;
  const first = arts[0];
  const path = first.relativePath || first.relative_path;
  if (!path) return null;
  return `${apiBase}/${path.replace(/\\/g, "/")}`;
}

export function firstPreviewableVisual(cell: CompareModelCell): CompareVisual | null {
  const visuals = cell.visuals || [];
  return visuals.find((v) => v.kind === "image" || v.kind === "video") || null;
}

export function compareSummaryText(summary: CompareSummary): string {
  const parts: string[] = [];
  parts.push(`共 ${summary.jobCount} 个任务`);
  if (summary.finished > 0) parts.push(`${summary.finished} 完成`);
  if (summary.running > 0) parts.push(`${summary.running} 运行中`);
  if (summary.attention > 0) parts.push(`${summary.attention} 待处理`);
  return parts.join("，");
}

export function isModelCompatibleWithSourceType(
  model: string,
  sourceType: string,
  catalog: ModelCatalogItem[]
): boolean {
  const item = catalog.find((m) => m.value === model);
  if (!item) return false;
  return item.source_types.includes(sourceType);
}

export function filterRunnableModels(
  catalog: ModelCatalogItem[],
  sourceType?: string
): ModelCatalogItem[] {
  let filtered = catalog.filter((m) => m.runnable);
  if (sourceType) {
    filtered = filtered.filter((m) => m.source_types.includes(sourceType));
  }
  return filtered;
}

export function modelCompatibilityHint(
  model: string,
  sourceType: string,
  catalog: ModelCatalogItem[]
): string | null {
  const item = catalog.find((m) => m.value === model);
  if (!item) return "未知模型";
  if (!item.runnable) return item.launch_blocker || "模型尚未部署";
  if (!item.source_types.includes(sourceType)) {
    return `不支持 ${sourceType}，仅支持 ${item.source_types.join("/")}`;
  }
  return null;
}

export function buildCompareReportFilename(sampleId: string): string {
  const timestamp = new Date().toISOString().slice(0, 10);
  return `compare-report-${sampleId}-${timestamp}.md`;
}
