import type { JobsListPayload } from "./types";
import {
  sourceTypeLabel,
  statusLabel,
  statusModelLabel
} from "./displayHelpers";
import type { ModelCatalogItem } from "./displayHelpers";

export type BatchJobAction = "dispatch" | "retry" | "cancel" | "delete";
export type JobListItem = JobsListPayload["jobs"][number];

export function buildCaptureChecklist(model: string, sourceType: string, fileCount: number) {
  return [
    {
      title: "当前模型",
      body: statusModelLabel(model)
    },
    {
      title: "来源类型",
      body: sourceTypeLabel(sourceType)
    },
    {
      title: "输入 Staging",
      body: `已进入 ${fileCount} 个待上传项。`
    }
  ];
}

export function buildAdvisorChecklist(advisorReady: boolean) {
  return [
    {
      title: "AI 状态",
      body: advisorReady ? "已连通，可生成评估草稿。" : "未就绪，需检查 API 配置。"
    },
    {
      title: "覆盖范围",
      body: "目前支持单模型三维重建结果、日志故障、轨迹连贯性评估。"
    }
  ];
}

export function buildSystemChecklist() {
  return [
    {
      title: "核心工作流",
      body: "数据准备 -> 派发任务 -> 结果检视 -> 矩阵比较。"
    },
    {
      title: "研发加速",
      body: "利用研究车道快速复现新论文，通过 smoke test 验证后合入主线。"
    },
    {
      title: "自愈机制",
      body: "当后端连接中断，点击“强制重启”可由 Tauri 重新拉起后台服务。"
    }
  ];
}

export function buildActionMessage(action: string, jobId: string) {
  switch (action) {
    case "dispatch":
      return `任务 ${jobId} 已开始调度。`;
    case "retry":
      return `任务 ${jobId} 已重新进入调度流程。`;
    case "duplicate":
      return `已复制出新的任务 ${jobId}。`;
    case "cancel":
      return `任务 ${jobId} 已请求取消。`;
    case "advisor":
      return `任务 ${jobId} 的辅助评估已更新。`;
    default:
      return `任务 ${jobId} 已更新。`;
  }
}

export function batchActionLabel(action: BatchJobAction) {
  switch (action) {
    case "dispatch":
      return "运行";
    case "retry":
      return "重试";
    case "cancel":
      return "取消";
    default:
      return "操作";
  }
}

export function isAdvisorSuggested(status: string) {
  return status === "finished" || status === "failed" || status === "cancelled";
}

export function canDispatchJobStatus(status: string) {
  return status === "draft" || status === "created" || status === "ready" || status === "failed" || status === "cancelled";
}

export function buildMatrixModelConstraint(item: ModelCatalogItem) {
  if (!item.runnable) {
    return {
      tone: "blocked",
      label: "Catalog-only",
      detail: item.launch_blocker ?? "目录模型暂不进入创建队列。"
    };
  }
  if (item.runner_status === "smoke_ready_attention_fallback" || item.runner_status === "validated_smoke_attention_fallback") {
    return {
      tone: "partial",
      label: "Fallback",
      detail: "当前走 attention fallback，先小样例确认速度。"
    };
  }
  if (item.runner_status === "baseline") {
    return {
      tone: "partial",
      label: "Baseline",
      detail: "基座保留线，优先作为静态参考。"
    };
  }
  return null;
}

export function matchesJobQuery(item: JobListItem, normalizedQuery: string) {
  if (!normalizedQuery) {
    return true;
  }
  const haystack = [
    item.job.job_id,
    item.job.model,
    statusLabel(item.job.status),
    sourceTypeLabel(item.job.source_type),
    item.phase_display.label,
    item.job.progress_message ?? ""
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(normalizedQuery);
}
