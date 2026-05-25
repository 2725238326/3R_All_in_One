import type { SamplesPayload } from "./types";
import {
  modelDisplayName,
  sampleStatusLabel,
  sourceTypeLabel
} from "./displayHelpers";
import type { ModelCatalogItem } from "./displayHelpers";

export type SampleMatrixJob = NonNullable<SamplesPayload["job_matrix"]>["rows"][number]["jobs_by_model"][string];
export type SampleManifestEntry = NonNullable<SamplesPayload["manifest"]["samples"]>[number];
export type SampleMatrixSortKey = "manifest" | "completion" | "score" | "attention";
export type SampleMatrixFilterKey = "all" | "attention" | "running" | "unfinished";
export type SampleMatrixReportModelScope = "all" | "required" | "with_jobs" | "finished";
export type SampleMatrixRowView = {
  sample: SampleManifestEntry;
  rowIndex: number;
  jobsByModel: Record<string, SampleMatrixJob>;
  requiredModels: string[];
  requiredModelSet: Set<string>;
  compareModels: string[];
  rowStats: ReturnType<typeof summarizeSampleMatrixRow>;
  rowScore: ReturnType<typeof summarizeMatrixRowScore>;
  rowEvidence: ReturnType<typeof summarizeMatrixRowEvidence>;
};

export function roleLabel(role: string) {
  const labels: Record<string, string> = {
    scene: "三维场景",
    trajectory: "相机轨迹",
    intrinsics: "相机内参",
    frame_preview: "彩色帧预览",
    dynamic_mask: "动态区域",
    confidence: "置信数组"
  };
  return labels[role] ?? role.replace(/_/g, " ");
}

export function summarizeScoreSnapshot(scoreSnapshot?: Record<string, number>) {
  if (!scoreSnapshot) {
    return {
      label: "评分快照：暂无",
      metricCount: 0,
      average: null as number | null,
      percent: 0,
      tone: "none" as "none" | "low" | "medium" | "high"
    };
  }
  const values = Object.values(scoreSnapshot).filter((value) => Number.isFinite(value));
  if (values.length === 0) {
    return {
      label: "评分快照：暂无",
      metricCount: 0,
      average: null as number | null,
      percent: 0,
      tone: "none" as "none" | "low" | "medium" | "high"
    };
  }
  const avg = values.reduce((sum, value) => sum + value, 0) / values.length;
  const bounded = Math.min(5, Math.max(0, avg));
  const tone: "low" | "medium" | "high" = bounded >= 4.2 ? "high" : bounded >= 3.2 ? "medium" : "low";
  return {
    label: `评分快照：${bounded.toFixed(2)}`,
    metricCount: values.length,
    average: bounded,
    percent: Math.round((bounded / 5) * 100),
    tone
  };
}

export function summarizeSampleMatrixRow(compareModels: string[], jobsByModel: Record<string, SampleMatrixJob>) {
  const stats = {
    total: compareModels.length,
    finished: 0,
    running: 0,
    attention: 0,
    pending: 0,
    missing: 0,
    completionPercent: 0
  };

  compareModels.forEach((model) => {
    const job = jobsByModel[model];
    const status = job?.status ?? "missing";
    if (status === "finished") {
      stats.finished += 1;
      return;
    }
    if (status === "running" || status === "starting") {
      stats.running += 1;
      return;
    }
    if (status === "failed" || status === "cancelled") {
      stats.attention += 1;
      return;
    }
    if (status === "missing") {
      stats.missing += 1;
      return;
    }
    stats.pending += 1;
  });

  stats.completionPercent = stats.total > 0 ? Math.round((stats.finished / stats.total) * 100) : 0;
  return stats;
}

export function summarizeMatrixRowScore(compareModels: string[], jobsByModel: Record<string, SampleMatrixJob>) {
  const digests = compareModels
    .map((model) => summarizeScoreSnapshot(jobsByModel[model]?.score_snapshot))
    .filter((digest) => typeof digest.average === "number");
  if (digests.length === 0) {
    return {
      average: null as number | null,
      percent: 0,
      metricCount: 0,
      tone: "none" as "none" | "low" | "medium" | "high"
    };
  }
  const totalAverage = digests.reduce((sum, digest) => sum + (digest.average ?? 0), 0);
  const average = totalAverage / digests.length;
  const metricCount = digests.reduce((sum, digest) => sum + digest.metricCount, 0);
  const bounded = Math.min(5, Math.max(0, average));
  return {
    average: bounded,
    percent: Math.round((bounded / 5) * 100),
    metricCount,
    tone: bounded >= 4.2 ? ("high" as const) : bounded >= 3.2 ? ("medium" as const) : ("low" as const)
  };
}

export function summarizeJobEvidence(job?: SampleMatrixJob) {
  if (!job) {
    return {
      label: "证据：无任务",
      detail: "尚无任务记录",
      countLabel: "--",
      ready: false,
      tone: "none" as "none" | "partial" | "ready"
    };
  }

  const artifacts = job.primary_artifacts ?? [];
  if (artifacts.length === 0) {
    return {
      label: "证据：待回传",
      detail: job.status === "finished" ? "核心产物暂无" : `阶段：${job.phase}`,
      countLabel: "0",
      ready: false,
      tone: "partial" as "none" | "partial" | "ready"
    };
  }

  const firstArtifact = artifacts[0];
  return {
    label: "证据：已回传",
    detail: firstArtifact.label || roleLabel(firstArtifact.role),
    countLabel: String(artifacts.length),
    ready: true,
    tone: "ready" as "none" | "partial" | "ready"
  };
}

export function summarizeMatrixRowEvidence(compareModels: string[], jobsByModel: Record<string, SampleMatrixJob>) {
  const digests = compareModels.map((model) => summarizeJobEvidence(jobsByModel[model]));
  const ready = digests.filter((digest) => digest.ready).length;
  const firstReady = digests.find((digest) => digest.ready);
  const tone: "none" | "partial" | "ready" = ready === 0 ? "none" : ready === compareModels.length ? "ready" : "partial";
  return {
    ready,
    total: compareModels.length,
    label: firstReady ? firstReady.detail : "暂无核心产物",
    tone
  };
}

export function matrixRowMatchesFilter(row: SampleMatrixRowView, filterKey: SampleMatrixFilterKey) {
  switch (filterKey) {
    case "attention":
      return row.rowStats.attention > 0;
    case "running":
      return row.rowStats.running > 0;
    case "unfinished":
      return row.rowStats.finished < row.rowStats.total;
    default:
      return true;
  }
}

export function compareSampleMatrixRows(left: SampleMatrixRowView, right: SampleMatrixRowView, sortKey: SampleMatrixSortKey) {
  switch (sortKey) {
    case "completion": {
      const byCompletion = right.rowStats.completionPercent - left.rowStats.completionPercent;
      if (byCompletion !== 0) {
        return byCompletion;
      }
      const leftScore = left.rowScore.average ?? -1;
      const rightScore = right.rowScore.average ?? -1;
      const byScore = rightScore - leftScore;
      if (byScore !== 0) {
        return byScore;
      }
      break;
    }
    case "score": {
      const leftScore = left.rowScore.average ?? -1;
      const rightScore = right.rowScore.average ?? -1;
      const byScore = rightScore - leftScore;
      if (byScore !== 0) {
        return byScore;
      }
      const byCompletion = right.rowStats.completionPercent - left.rowStats.completionPercent;
      if (byCompletion !== 0) {
        return byCompletion;
      }
      break;
    }
    case "attention": {
      const byAttention = right.rowStats.attention - left.rowStats.attention;
      if (byAttention !== 0) {
        return byAttention;
      }
      const byRunning = right.rowStats.running - left.rowStats.running;
      if (byRunning !== 0) {
        return byRunning;
      }
      const leftPending = left.rowStats.pending + left.rowStats.missing;
      const rightPending = right.rowStats.pending + right.rowStats.missing;
      const byPending = rightPending - leftPending;
      if (byPending !== 0) {
        return byPending;
      }
      break;
    }
    case "manifest":
    default: {
      const byIndex = left.rowIndex - right.rowIndex;
      if (byIndex !== 0) {
        return byIndex;
      }
      break;
    }
  }
  return left.sample.id.localeCompare(right.sample.id);
}

export function primaryArtifactHint(primaryArtifacts?: SampleMatrixJob["primary_artifacts"]) {
  if (!primaryArtifacts || primaryArtifacts.length === 0) {
    return "核心产物：暂无";
  }
  const first = primaryArtifacts[0];
  const label = first.label || roleLabel(first.role);
  return `核心产物：${label}`;
}

export function collectSampleMatrixJobIds(rows: SampleMatrixRowView[]) {
  const ids: string[] = [];
  const seen = new Set<string>();
  for (const row of rows) {
    if (row.sample.seed_job_id && !seen.has(row.sample.seed_job_id)) {
      seen.add(row.sample.seed_job_id);
      ids.push(row.sample.seed_job_id);
    }
    for (const model of row.compareModels) {
      const jobId = row.jobsByModel[model]?.job_id;
      if (jobId && !seen.has(jobId)) {
        seen.add(jobId);
        ids.push(jobId);
      }
    }
  }
  return ids;
}

export function buildSampleMatrixReport(
  rows: SampleMatrixRowView[],
  modelCatalog: ModelCatalogItem[],
  context: {
    filterKey: SampleMatrixFilterKey;
    generatedAt: string;
    manifestPurpose?: string;
    manifestUpdated?: string | null;
    modelScope: SampleMatrixReportModelScope;
    selectedRowCount: number;
    sortKey: SampleMatrixSortKey;
    visibleRowCount: number;
  }
) {
  const summary = summarizeSampleMatrixReportRows(rows, context.modelScope);
  const lines = [
    "# Sample Matrix Compare Report",
    "",
    `- Generated: ${context.generatedAt}`,
    `- Scope: ${context.selectedRowCount > 0 ? `selected ${context.selectedRowCount} rows` : `filtered ${context.visibleRowCount} rows`}`,
    `- Sort: ${sampleMatrixSortLabel(context.sortKey)}`,
    `- Filter: ${sampleMatrixFilterLabel(context.filterKey)}`,
    `- Model scope: ${sampleMatrixReportModelScopeLabel(context.modelScope)}`,
    `- Manifest updated: ${context.manifestUpdated ?? "unknown"}`,
    context.manifestPurpose ? `- Manifest purpose: ${context.manifestPurpose}` : "",
    "",
    "## Summary",
    "",
    `- Samples: ${rows.length}`,
    `- Model cells: ${summary.modelCells}`,
    `- Finished cells: ${summary.finished}`,
    `- Attention cells: ${summary.attention}`,
    `- Evidence-ready cells: ${summary.evidenceReady}`,
    `- Average score: ${summary.average !== null ? summary.average.toFixed(2) : "--"}`
  ].filter(Boolean);

  rows.forEach((row) => {
    const reportModels = sampleMatrixReportModels(row, context.modelScope);
    lines.push(
      "",
      `## ${row.sample.id}`,
      "",
      `- Status: ${sampleStatusLabel(row.sample.status)}`,
      `- Source: ${sourceTypeLabel(row.sample.source_type)} / ${sampleTargetSummary(row.sample)}`,
      `- Matrix: ${row.rowStats.finished}/${row.rowStats.total} finished, ${row.rowStats.attention} attention, ${row.rowStats.missing} missing`,
      `- Score: ${sampleMatrixReportScoreLabel(row.rowScore)}`,
      `- Evidence: ${row.rowEvidence.ready}/${row.rowEvidence.total} (${row.rowEvidence.label})`,
      `- Seed job: ${row.sample.seed_job_id ?? "--"}`,
      ""
    );

    if (row.sample.manual_criteria?.length) {
      lines.push(`- Criteria: ${row.sample.manual_criteria.join("; ")}`, "");
    }

    if (reportModels.length === 0) {
      lines.push("No model cells match the current report scope.");
      return;
    }

    lines.push("| Model | Role | Job | Status | Score | Evidence | Phase |", "| --- | --- | --- | --- | --- | --- | --- |");
    reportModels.forEach((model) => {
      const job = row.jobsByModel[model];
      const scoreDigest = summarizeScoreSnapshot(job?.score_snapshot);
      const evidenceDigest = summarizeJobEvidence(job);
      const scoreLabel = scoreDigest.average !== null ? `${scoreDigest.average.toFixed(2)} (${scoreDigest.metricCount})` : "--";
      lines.push(
        [
          modelDisplayName(model, modelCatalog),
          row.requiredModelSet.has(model) ? "Required" : "Optional",
          job?.job_id ?? "--",
          job ? job.status_label : "未跑",
          scoreLabel,
          `${evidenceDigest.countLabel} / ${evidenceDigest.detail}`,
          job?.progress_message || job?.phase || "--"
        ]
          .map(escapeMarkdownCell)
          .join(" | ")
          .replace(/^/, "| ")
          .replace(/$/, " |")
      );
    });
  });

  return {
    fileName: `sample-matrix-report-${safeFileTimestamp(context.generatedAt)}.md`,
    markdown: `${lines.join("\n")}\n`
  };
}

export function sampleMatrixReportModels(row: SampleMatrixRowView, scope: SampleMatrixReportModelScope) {
  switch (scope) {
    case "required":
      return row.compareModels.filter((model) => row.requiredModelSet.has(model));
    case "with_jobs":
      return row.compareModels.filter((model) => Boolean(row.jobsByModel[model]?.job_id));
    case "finished":
      return row.compareModels.filter((model) => row.jobsByModel[model]?.status === "finished");
    case "all":
    default:
      return row.compareModels;
  }
}

export function summarizeSampleMatrixReportRows(rows: SampleMatrixRowView[], modelScope: SampleMatrixReportModelScope) {
  const summary = {
    modelCells: 0,
    finished: 0,
    attention: 0,
    evidenceReady: 0,
    scoreCount: 0,
    scoreTotal: 0
  };

  rows.forEach((row) => {
    sampleMatrixReportModels(row, modelScope).forEach((model) => {
      const job = row.jobsByModel[model];
      const scoreDigest = summarizeScoreSnapshot(job?.score_snapshot);
      const evidenceDigest = summarizeJobEvidence(job);
      summary.modelCells += 1;
      if (job?.status === "finished") {
        summary.finished += 1;
      }
      if (job?.status === "failed" || job?.status === "cancelled") {
        summary.attention += 1;
      }
      if (evidenceDigest.ready) {
        summary.evidenceReady += 1;
      }
      if (scoreDigest.average !== null) {
        summary.scoreCount += 1;
        summary.scoreTotal += scoreDigest.average;
      }
    });
  });

  return {
    modelCells: summary.modelCells,
    finished: summary.finished,
    attention: summary.attention,
    evidenceReady: summary.evidenceReady,
    average: summary.scoreCount > 0 ? summary.scoreTotal / summary.scoreCount : null
  };
}

export function sampleMatrixReportScoreLabel(score: ReturnType<typeof summarizeMatrixRowScore>) {
  return score.average !== null ? `${score.average.toFixed(2)} (${score.metricCount} metrics)` : "--";
}

export function sampleTargetSummary(sample: SampleManifestEntry) {
  if (sample.target_file_count) {
    return `${sample.target_file_count} files`;
  }
  if (sample.target_duration_seconds) {
    return `${sample.target_duration_seconds} seconds`;
  }
  return "--";
}

export function sampleMatrixReportModelScopeLabel(scope: SampleMatrixReportModelScope) {
  switch (scope) {
    case "required":
      return "Required models";
    case "with_jobs":
      return "Models with jobs";
    case "finished":
      return "Finished model jobs";
    case "all":
    default:
      return "All model columns";
  }
}

export function sampleMatrixSortLabel(sortKey: SampleMatrixSortKey) {
  switch (sortKey) {
    case "completion":
      return "completion";
    case "score":
      return "score";
    case "attention":
      return "attention";
    case "manifest":
    default:
      return "manifest";
  }
}

export function sampleMatrixFilterLabel(filterKey: SampleMatrixFilterKey) {
  switch (filterKey) {
    case "attention":
      return "attention";
    case "running":
      return "running";
    case "unfinished":
      return "unfinished";
    case "all":
    default:
      return "all";
  }
}

function escapeMarkdownCell(value: string | number | null | undefined) {
  return String(value ?? "--").replace(/\r?\n/g, " ").replace(/\|/g, "\\|");
}

function safeFileTimestamp(value: string) {
  return value.replace(/[:.]/g, "-").replace(/[^0-9A-Za-z_-]/g, "_");
}
