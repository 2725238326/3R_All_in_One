import type { BootstrapPayload } from "./types";

export const API_BASE = (import.meta.env.VITE_API_BASE || "http://127.0.0.1:8765").replace(/\/$/, "");

export const DEFAULT_BOOTSTRAP: BootstrapPayload = {
  summary: { total: 0, running: 0, finished: 0, failed: 0, cancelled: 0 },
  delivery_gaps: [],
  server: {
    alias: "KYKT-UI",
    host: "172.17.140.97",
    user: "kykt26",
    port: 22,
    remote_root: "/hdd3/kykt26"
  },
  models: [
    {
      value: "dust3r",
      label: "DUSt3R",
      description: "图片对 / 多图三维重建",
      param_family: "image_collection"
    },
    {
      value: "mast3r",
      label: "MASt3R",
      description: "更强的静态多图匹配与三维重建",
      param_family: "image_collection"
    },
    {
      value: "monst3r",
      label: "MonST3R",
      description: "视频 / 帧序列动态三维重建",
      param_family: "video_sequence"
    },
    {
      value: "spann3r",
      label: "Spann3R",
      description: "Spatial memory 全局点图重建",
      param_family: "spann3r_sequence"
    },
    {
      value: "fast3r",
      label: "Fast3R",
      description: "长图集快速前馈三维重建",
      param_family: "fast3r_collection"
    }
  ],
  source_types: [
    { value: "images", label: "图片" },
    { value: "frames", label: "帧序列" },
    { value: "video", label: "视频" }
  ]
};

export const defaultDust3rParams = {
  image_size: "512",
  scene_graph: "complete",
  niter: "300",
  lr: "0.01",
  batch_size: "1",
  max_points: "250000",
  match_viz_count: "50"
};

export const defaultMonst3rParams = {
  image_size: "512",
  batch_size: "1",
  fps: "0",
  num_frames: "48",
  not_batchify: "true",
  real_time: "false",
  window_wise: "false",
  window_size: "24",
  window_overlap_ratio: "0.5"
};

export const defaultFast3rParams = {
  image_size: "512",
  max_points: "250000"
};

export type ParamChoice = {
  value: string;
  label: string;
  note: string;
};

export type PresetKey = "quick" | "standard" | "enhanced";

type PresetDescriptor = {
  key: PresetKey;
  label: string;
  note: string;
};

export const dust3rParamChoices: Record<keyof typeof defaultDust3rParams, ParamChoice[]> = {
  image_size: [
    { value: "512", label: "512（标准推荐）", note: "标准档" },
    { value: "384", label: "384（中速）", note: "中速档" },
    { value: "224", label: "224（快速摸底）", note: "快速档" }
  ],
  scene_graph: [
    { value: "complete", label: "complete（2 到 6 张推荐）", note: "完整配对" },
    { value: "swin-5", label: "swin-5（6 张以上推荐）", note: "滑窗配对" }
  ],
  niter: [
    { value: "150", label: "150（快速）", note: "快速档" },
    { value: "300", label: "300（基线推荐）", note: "基线档" },
    { value: "500", label: "500（精细）", note: "精细档" }
  ],
  lr: [
    { value: "0.005", label: "0.005（更稳）", note: "保守档" },
    { value: "0.01", label: "0.01（标准推荐）", note: "标准档" },
    { value: "0.02", label: "0.02（更激进）", note: "快速收敛档" }
  ],
  batch_size: [
    { value: "1", label: "1（稳妥推荐）", note: "低显存档" },
    { value: "2", label: "2（显存充足）", note: "提速档" }
  ],
  max_points: [
    { value: "100000", label: "100000（快速）", note: "轻量档" },
    { value: "250000", label: "250000（基线推荐）", note: "基线档" },
    { value: "500000", label: "500000（细节优先）", note: "细节档" }
  ],
  match_viz_count: [
    { value: "0", label: "0（不画匹配线）", note: "关闭" },
    { value: "20", label: "20（简洁）", note: "简洁档" },
    { value: "50", label: "50（基线推荐）", note: "基线档" },
    { value: "100", label: "100（更密）", note: "密集档" }
  ]
};

export const monst3rParamChoices: Record<keyof typeof defaultMonst3rParams, ParamChoice[]> = {
  image_size: [
    { value: "512", label: "512（正式样例推荐）", note: "标准档" },
    { value: "224", label: "224（快速验链路）", note: "快速档" }
  ],
  batch_size: [
    { value: "1", label: "1（稳妥推荐）", note: "低显存档" },
    { value: "2", label: "2（显存足够再试）", note: "提速档" }
  ],
  fps: [
    { value: "0", label: "0（自动/原节奏推荐）", note: "自动档" },
    { value: "2", label: "2（更省）", note: "低采样档" },
    { value: "4", label: "4（常规抽帧）", note: "常规档" },
    { value: "8", label: "8（高动作场景）", note: "高采样档" }
  ],
  num_frames: [
    { value: "24", label: "24（快速验链路）", note: "快速档" },
    { value: "48", label: "48（基线推荐）", note: "基线档" },
    { value: "72", label: "72（增强）", note: "增强档" },
    { value: "96", label: "96（长序列）", note: "长序列档" }
  ],
  not_batchify: [
    { value: "true", label: "开启（稳妥推荐）", note: "低显存档" },
    { value: "false", label: "关闭（速度优先）", note: "速度档" }
  ],
  real_time: [
    { value: "false", label: "关闭（离线质量推荐）", note: "离线档" },
    { value: "true", label: "开启（演示模式）", note: "演示档" }
  ],
  window_wise: [
    { value: "false", label: "关闭（短视频推荐）", note: "短序列档" },
    { value: "true", label: "开启（长序列推荐）", note: "长序列档" }
  ],
  window_size: [
    { value: "16", label: "16（更轻）", note: "轻量档" },
    { value: "24", label: "24（基线推荐）", note: "基线档" },
    { value: "32", label: "32（更长序列）", note: "长窗口档" }
  ],
  window_overlap_ratio: [
    { value: "0.25", label: "0.25（更快）", note: "低重叠档" },
    { value: "0.5", label: "0.5（基线推荐）", note: "基线档" },
    { value: "0.75", label: "0.75（更稳）", note: "高重叠档" }
  ]
};

export const fast3rParamChoices: Record<keyof typeof defaultFast3rParams, ParamChoice[]> = {
  image_size: [
    { value: "512", label: "512（标准推荐）", note: "标准档" },
    { value: "224", label: "224（快速摸底）", note: "快速档" }
  ],
  max_points: [
    { value: "100000", label: "100000（快速）", note: "轻量档" },
    { value: "250000", label: "250000（标准推荐）", note: "标准档" },
    { value: "500000", label: "500000（细节优先）", note: "细节档" }
  ]
};

export const presetDescriptors: PresetDescriptor[] = [
  { key: "quick", label: "快速", note: "先验链路、快速出结果" },
  { key: "standard", label: "标准", note: "正式样例首选基线" },
  { key: "enhanced", label: "增强", note: "重点样例，质量优先" }
];
