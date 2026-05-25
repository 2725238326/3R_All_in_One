import type { DeploymentStatusPayload } from "./types";
import { findModelCatalogItem, modelDisplayName } from "./displayHelpers";
import type { ModelCatalogItem } from "./displayHelpers";

const ACTIVE_DEPLOYMENT_TARGETS = ["mast3r", "monst3r", "spann3r", "align3r", "fast3r", "cut3r"];

export function formatDeploymentEnvSummary(payload: DeploymentStatusPayload) {
  return payload.conda_envs
    .filter((item) => ACTIVE_DEPLOYMENT_TARGETS.includes(item.component))
    .map((item) => `${item.component}:${item.exists ? "OK" : "缺失"}${item.path ? ` (${item.path})` : ""}`)
    .join(" / ");
}

export function formatDeploymentCacheStatus(payload: DeploymentStatusPayload | null) {
  if (!payload?.cache) {
    return "暂无缓存信息";
  }
  const state = payload.cache.state ?? payload.source ?? "unknown";
  const age = typeof payload.cache.age_seconds === "number" ? `${payload.cache.age_seconds.toFixed(1)}s` : "-";
  const fetched = payload.fetched_at ?? "-";
  return `${state} / age ${age} / fetched ${fetched}`;
}

export function formatDeploymentDirectoryStatus(payload: DeploymentStatusPayload | null) {
  if (!payload?.directories?.length) {
    return "暂无目录状态";
  }
  return payload.directories
    .filter((item) => ACTIVE_DEPLOYMENT_TARGETS.includes(item.name))
    .map((item) => `${item.name}:${item.state}${item.readme_setup ? "" : "/README缺失"}`)
    .join(" / ");
}

export function buildDeploymentComponentRows(payload: DeploymentStatusPayload | null, catalog: ModelCatalogItem[] = []) {
  if (!payload) {
    return [];
  }
  return ACTIVE_DEPLOYMENT_TARGETS.map((component) => {
    const modelItem = findModelCatalogItem(component, catalog);
    const directory = payload.directories.find((item) => item.name === component);
    const env = payload.conda_envs.find((item) => item.component === component);
    const files = payload.known_files.filter((item) => item.component === component);
    const missingRequiredFiles = files.filter((item) => /required/i.test(item.need) && !item.exists).length;
    const checkpointCount = payload.checkpoints?.filter((item) => item.component === component).length ?? 0;
    const blocked = !directory?.exists || !env?.exists || missingRequiredFiles > 0;
    const tone = blocked ? "blocked" : checkpointCount > 0 ? "ready" : "partial";

    return {
      component,
      tone,
      modelItem,
      nextAction: buildDeploymentNextAction(modelItem, directory?.exists ?? false, env?.exists ?? false, missingRequiredFiles, checkpointCount),
      constraints: buildModelConstraintTags(modelItem, directory?.exists ?? false, env?.exists ?? false, missingRequiredFiles, checkpointCount),
      directory: directory?.exists ? (directory.readme_setup ? "OK" : "README 待补") : "缺失",
      env: env?.exists ? "OK" : "缺失",
      files: files.length > 0 ? `${files.length - missingRequiredFiles}/${files.length}` : "未登记",
      checkpoints: checkpointCount > 0 ? `${checkpointCount} 个` : "待确认"
    };
  });
}

export function buildModelActionRows(payload: DeploymentStatusPayload | null, catalog: ModelCatalogItem[]) {
  if (!payload) {
    return [];
  }
  return buildDeploymentComponentRows(payload, catalog)
    .map((row) => {
      const item = row.modelItem;
      const stateLabel = !item?.runnable
        ? "目录模型"
        : row.tone === "ready"
          ? "可创建"
          : row.tone === "partial"
            ? "需确认"
            : "阻塞";
      return {
        value: row.component,
        label: modelDisplayName(row.component, catalog),
        tone: !item?.runnable ? "blocked" : row.tone,
        stateLabel,
        nextAction: row.nextAction,
        constraints: row.constraints
      };
    })
    .sort((left, right) => modelActionSortRank(left.tone) - modelActionSortRank(right.tone) || left.label.localeCompare(right.label));
}

function modelActionSortRank(tone: string) {
  if (tone === "blocked") {
    return 0;
  }
  if (tone === "partial") {
    return 1;
  }
  return 2;
}

function buildDeploymentNextAction(
  item: ModelCatalogItem | null,
  hasDirectory: boolean,
  hasEnv: boolean,
  missingRequiredFiles: number,
  checkpointCount: number
) {
  if (!item) {
    return "先把该模型补进 model registry，再绑定部署检查结果。";
  }
  if (!item.runnable) {
    return item.launch_blocker ?? "先完成 runner、输出合同和 smoke run，再开放 Create 创建入口。";
  }
  if (!hasDirectory) {
    return "先确认远端代码目录是否存在，必要时按上传计划解压 repo。";
  }
  if (!hasEnv) {
    return "先补齐独立 conda env，再跑官方 demo smoke。";
  }
  if (missingRequiredFiles > 0) {
    return `先补齐 ${missingRequiredFiles} 个必需文件，再刷新部署状态。`;
  }
  if (item.runner_status === "smoke_ready_attention_fallback" || item.runner_status === "validated_smoke_attention_fallback") {
    return "可从 Create 创建，但先用小样例确认 attention fallback 的速度和显存。";
  }
  if (checkpointCount === 0) {
    return "部署基本可见，下一步确认权重/checkpoint 是否已登记。";
  }
  return "可从 Create 发起任务；建议用样例矩阵做同输入横向对比。";
}

function buildModelConstraintTags(
  item: ModelCatalogItem | null,
  hasDirectory: boolean,
  hasEnv: boolean,
  missingRequiredFiles: number,
  checkpointCount: number
) {
  const tags: string[] = [];
  if (!item?.runnable) {
    tags.push("catalog-only");
  }
  if (!hasDirectory) {
    tags.push("code-dir missing");
  }
  if (!hasEnv) {
    tags.push("env missing");
  }
  if (missingRequiredFiles > 0) {
    tags.push(`files missing ${missingRequiredFiles}`);
  }
  if (checkpointCount === 0) {
    tags.push("checkpoint pending");
  }
  if (item?.runner_status === "smoke_ready_attention_fallback" || item?.runner_status === "validated_smoke_attention_fallback") {
    tags.push("attention fallback");
  }
  if (item?.runner_status === "env_blocked_curope") {
    tags.push("curope blocked");
  }
  if (item?.runner_status === "runner_pending_smoke") {
    tags.push("runner pending");
  }
  return tags;
}
