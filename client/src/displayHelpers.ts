import type { BackendStatusPayload, BootstrapPayload } from "./types";

export type ModelCatalogItem = NonNullable<BootstrapPayload["model_catalog"]>[number];

export function delay(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

export function friendlyError(error: unknown, fallback: string) {
  if (error instanceof Error && error.message) {
    if (/Failed to fetch|NetworkError|fetch/i.test(error.message)) {
      return "本地服务暂时不可用，请等顶部状态变成“就绪”。";
    }
    return error.message;
  }
  return fallback;
}

export function serviceStatusLabel(state: string) {
  if (state === "ready") {
    return "就绪";
  }
  if (state === "degraded") {
    return "未连接";
  }
  return "启动中";
}

export function backendStatusText(status: BackendStatusPayload | null) {
  if (!status) {
    return "正在检查桌面后端托管状态。";
  }
  if (status.running && status.managed_by_tauri) {
    return status.log_path ? `桌面端已自动启动后端。日志：${status.log_path}` : "桌面端已自动启动后端。";
  }
  if (status.running) {
    return "检测到已有后端，当前会直接复用。";
  }
  return status.message || "后端暂未启动。";
}

export function statusLabel(status: string) {
  switch (status) {
    case "running":
      return "运行中";
    case "finished":
      return "完成";
    case "failed":
      return "失败";
    case "cancelled":
      return "取消";
    case "draft":
      return "草稿";
    case "ready":
      return "就绪";
    default:
      return status;
  }
}

export function statusModelLabel(model: string) {
  switch (model) {
    case "dust3r":
      return "DUSt3R";
    case "mast3r":
      return "MASt3R";
    case "monst3r":
      return "MonST3R";
    case "spann3r":
      return "Spann3R";
    case "align3r":
      return "Align3R";
    case "fast3r":
      return "Fast3R";
    case "cut3r":
      return "CUT3R";
    case "pi3x":
      return "Pi3X";
    case "zipmap":
      return "ZipMap";
    case "lingbot_map":
      return "LingBot-Map";
    default:
      return model;
  }
}

export function modelFamilyLabel(family: string) {
  const labels: Record<string, string> = {
    pairwise_pointmap: "Pairwise 点图",
    static_matching_reconstruction: "静态匹配重建",
    video_dynamic_reconstruction: "视频动态重建",
    memory_global_pointmap: "空间记忆",
    video_depth_consistency: "视频深度一致",
    large_image_collection: "长图集",
    streaming_state_reconstruction: "状态流式",
    general_visual_geometry: "通用视觉几何",
    stateful_linear_reconstruction: "线性状态",
    streaming_mapping: "流式建图"
  };
  return labels[family] ?? family.replace(/_/g, " ");
}

export function paramFamilyLabel(paramFamily: string) {
  const labels: Record<string, string> = {
    image_collection: "图片集合",
    video_sequence: "视频/帧序列",
    spann3r_sequence: "Spann3R 序列",
    fast3r_collection: "Fast3R 图集",
    streaming_sequence: "流式序列",
    research_catalog: "研究目录"
  };
  return labels[paramFamily] ?? paramFamily.replace(/_/g, " ");
}

export function runnerStatusLabel(status: string) {
  const labels: Record<string, string> = {
    baseline: "基座保留",
    validated_smoke: "Smoke 已过",
    validated_smoke_attention_fallback: "Smoke 已过（attention fallback）",
    validated_standard_sample: "标准样例已过",
    smoke_ready: "Smoke 已过",
    smoke_ready_attention_fallback: "Smoke 已过（需 attention fallback）",
    env_partial: "环境部分就绪",
    env_blocked_curope: "环境受 curope 阻塞",
    runner_pending_smoke: "Runner/Smoke 待补",
    planned: "待接入",
    frontier_research: "前沿预研",
    integrated: "已接入"
  };
  return labels[status] ?? status.replace(/_/g, " ");
}

export function findModelCatalogItem(value: string, catalog: ModelCatalogItem[]) {
  return catalog.find((item) => item.value === value) ?? null;
}

export function modelDisplayName(value: string, catalog: ModelCatalogItem[]) {
  return findModelCatalogItem(value, catalog)?.label ?? value.replace(/_/g, " ");
}

export function formatModelList(values: string[], catalog: ModelCatalogItem[]) {
  if (values.length === 0) {
    return "暂无";
  }
  return values.map((value) => modelDisplayName(value, catalog)).join(" / ");
}

export function formatSourceTypeList(sourceTypes: string[]) {
  if (sourceTypes.length === 0) {
    return "未登记";
  }
  return sourceTypes.map((type) => sourceTypeLabel(type)).join(" / ");
}

export function formatCountMap(values: Record<string, number> | undefined, labeler: (value: string) => string) {
  if (!values || Object.keys(values).length === 0) {
    return "暂无";
  }
  return Object.entries(values)
    .map(([key, value]) => `${labeler(key)} ${value}`)
    .join(" / ");
}

export function sampleStatusLabel(status: string) {
  const labels: Record<string, string> = {
    needs_selection: "待选样例"
  };
  if (/^seeded_from_job_/i.test(status)) {
    return "已有种子任务";
  }
  return labels[status] ?? status.replace(/_/g, " ");
}

export function scoringCategoryLabel(category: string) {
  const labels: Record<string, string> = {
    engineering: "工程成本",
    result_quality: "结果质量",
    platform: "平台交付"
  };
  return labels[category] ?? category.replace(/_/g, " ");
}

export function metricLabel(metric: string) {
  const labels: Record<string, string> = {
    setup_time: "环境准备",
    weight_download_difficulty: "权重获取",
    runtime_seconds: "运行耗时",
    peak_gpu_memory_mb: "峰值显存",
    runner_integration_difficulty: "Runner 接入",
    structure_completeness_1_to_5: "结构完整度",
    trajectory_stability_1_to_5: "轨迹稳定性",
    noise_level_1_to_5: "噪声水平",
    dynamic_handling_1_to_5: "动态处理",
    depth_temporal_consistency_1_to_5: "深度时序一致",
    presentation_usability_1_to_5: "展示可用性",
    noninteractive_runner: "非交互 Runner",
    status_json: "状态 JSON",
    scene_meta_json: "场景元数据",
    result_summary: "结果摘要",
    frontend_core_preview: "前端核心预览"
  };
  return labels[metric] ?? metric.replace(/_/g, " ");
}

export function sourceTypeLabel(sourceType: string) {
  switch (sourceType) {
    case "images":
      return "图片";
    case "video":
      return "视频";
    case "frames":
      return "帧序列";
    default:
      return sourceType;
  }
}

export function jobFilterLabel(filter: string) {
  switch (filter) {
    case "running":
      return "运行中";
    case "attention":
      return "待处理";
    case "finished":
      return "已完成";
    default:
      return "全部";
  }
}

export function formatParamLabel(key: string) {
  const labels: Record<string, string> = {
    image_size: "图像尺寸",
    scene_graph: "场景图",
    niter: "对齐迭代",
    lr: "学习率",
    batch_size: "批大小",
    max_points: "最大点数",
    match_viz_count: "匹配线数量",
    fps: "抽帧 FPS",
    num_frames: "最大帧数",
    not_batchify: "省显存模式",
    real_time: "实时模式",
    window_wise: "窗口模式",
    window_size: "窗口大小",
    window_overlap_ratio: "窗口重叠率"
  };
  return labels[key] ?? key.replace(/_/g, " ");
}

export function describeOutput(filename: string) {
  const lower = filename.toLowerCase();
  if (/dynamic_mask|enlarged_dynamic_mask/.test(lower)) {
    return "动态区域掩膜";
  }
  if (/scene\.glb/.test(lower)) {
    return "MonST3R 三维场景";
  }
  if (/pred_traj\.txt/.test(lower)) {
    return "MonST3R 相机轨迹";
  }
  if (/pred_intrinsics\.txt/.test(lower)) {
    return "MonST3R 预测相机内参";
  }
  if (/^conf_\d+\.npy$/.test(lower) || /^init_conf_\d+\.npy$/.test(lower)) {
    return "MonST3R 置信数组";
  }
  if (/^frame_\d+\.npy$/.test(lower)) {
    return "MonST3R 每帧几何数组";
  }
  if (/frame_\d+\.png/.test(lower)) {
    return "彩色帧预览";
  }
  const suffix = filename.split(".").pop()?.toLowerCase();
  switch (suffix) {
    case "png":
    case "jpg":
    case "jpeg":
    case "webp":
      return "图像预览或匹配可视化";
    case "ply":
      return "点云模型，建议用 MeshLab 打开";
    case "glb":
    case "gltf":
      return "三维场景文件";
    case "txt":
      return "轨迹或相机文本";
    case "npy":
      return "数组产物";
    case "mp4":
    case "mov":
    case "avi":
    case "mkv":
    case "webm":
      return "视频产物";
    default:
      return "任务产物";
  }
}

export function fileExtensionLabel(filename: string) {
  return filename.split(".").pop()?.toUpperCase() || "FILE";
}

export function formatDuration(value: number | null) {
  if (!value || value <= 0) {
    return "-";
  }
  const hours = Math.floor(value / 3600);
  const minutes = Math.floor((value % 3600) / 60);
  const seconds = value % 60;
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  if (minutes > 0) {
    return `${minutes}m ${seconds}s`;
  }
  return `${seconds}s`;
}

export function formatDateTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

export function devLaneCategoryLabel(category: string) {
  const labels: Record<string, string> = {
    paper_reproduction: "论文复现",
    model_runner: "模型 Runner",
    prototype: "原型开发",
    evaluation: "评测框架",
    ui_workflow: "UI 工作流"
  };
  return labels[category] ?? category.replace(/_/g, " ");
}

export function devLaneStatusLabel(status: string) {
  const labels: Record<string, string> = {
    draft: "草稿",
    scoped: "已定义",
    reproducing: "复现中",
    prototype: "原型中",
    smoke_ready: "Smoke 待过",
    validated: "已验证",
    merged: "已合入",
    deferred: "推迟"
  };
  return labels[status] ?? status.replace(/_/g, " ");
}

export function devLanePriorityTone(priority: string) {
  switch (priority) {
    case "P0":
      return "danger";
    case "P1":
      return "warning";
    case "P2":
      return "running";
    default:
      return "neutral";
  }
}
