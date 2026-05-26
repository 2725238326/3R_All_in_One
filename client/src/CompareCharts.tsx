// ═══════════════════════════════════════════════════════════════
// CompareCharts — 模型对比图表
// ═══════════════════════════════════════════════════════════════
import { useMemo, useState } from "react";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  Cell,
} from "recharts";
import type { CompareModelCell } from "./types";
import type { ModelCatalogItem } from "./displayHelpers";
import { modelDisplayName } from "./displayHelpers";
import { PointCloudViewer } from "./PointCloudViewer";

// ─────────────── 评分维度配置 ───────────────

const SCORE_DIMENSIONS = [
  { key: "structure_completeness", label: "结构完整度" },
  { key: "trajectory_stability", label: "轨迹稳定性" },
  { key: "noise", label: "噪声控制" },
  { key: "dynamic_handling", label: "动态处理" },
  { key: "depth_continuity", label: "深度连续性" },
  { key: "presentation_usability", label: "展示可用性" },
] as const;

// 模型颜色调色板
const MODEL_COLORS = [
  "#00ffff",  // cyan
  "#ff6b6b",  // red
  "#feca57",  // yellow
  "#48dbfb",  // light blue
  "#1dd1a1",  // green
  "#a29bfe",  // purple
  "#fd79a8",  // pink
  "#fab1a0",  // peach
];

// ─────────────── 数据转换 ───────────────

function getScore(cell: CompareModelCell, key: string): number {
  const snapshot = cell.scoreSnapshot || cell.score_snapshot || {};
  const value = snapshot[key];
  return typeof value === "number" ? value : 0;
}

function getModelLabel(cell: CompareModelCell, catalog: ModelCatalogItem[]): string {
  return modelDisplayName(cell.model, catalog);
}

// ─────────────── 雷达图 ───────────────

export function CompareRadarChart({
  cells,
  modelCatalog,
}: {
  cells: CompareModelCell[];
  modelCatalog: ModelCatalogItem[];
}) {
  const data = useMemo(() => {
    return SCORE_DIMENSIONS.map((dim) => {
      const row: any = { dimension: dim.label };
      cells.forEach((cell) => {
        const label = getModelLabel(cell, modelCatalog);
        row[label] = getScore(cell, dim.key);
      });
      return row;
    });
  }, [cells, modelCatalog]);

  const hasData = useMemo(() => {
    return cells.some((cell) => {
      const snapshot = cell.scoreSnapshot || cell.score_snapshot || {};
      return Object.keys(snapshot).length > 0;
    });
  }, [cells]);

  if (!hasData) {
    return (
      <div className="compare-chart-empty">
        <p>暂无评分数据。请先在任务详情中填写评分。</p>
      </div>
    );
  }

  return (
    <div className="compare-radar-wrapper">
      <ResponsiveContainer width="100%" height={400}>
        <RadarChart data={data}>
          <PolarGrid stroke="rgba(255,255,255,0.15)" />
          <PolarAngleAxis 
            dataKey="dimension" 
            tick={{ fill: "rgba(255,255,255,0.85)", fontSize: 12 }}
          />
          <PolarRadiusAxis 
            domain={[0, 5]} 
            tickCount={6}
            tick={{ fill: "rgba(255,255,255,0.5)", fontSize: 10 }}
          />
          {cells.map((cell, idx) => {
            const label = getModelLabel(cell, modelCatalog);
            const color = MODEL_COLORS[idx % MODEL_COLORS.length];
            return (
              <Radar
                key={cell.jobId || cell.job_id}
                name={label}
                dataKey={label}
                stroke={color}
                fill={color}
                fillOpacity={0.2}
                strokeWidth={2}
              />
            );
          })}
          <Tooltip 
            contentStyle={{
              background: "rgba(20,20,30,0.95)",
              border: "1px solid rgba(255,255,255,0.2)",
              borderRadius: 8,
              color: "#fff",
            }}
          />
          <Legend 
            wrapperStyle={{ paddingTop: 8 }}
            iconType="circle"
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─────────────── 柱状图 ───────────────

export function CompareBarChart({
  cells,
  modelCatalog,
}: {
  cells: CompareModelCell[];
  modelCatalog: ModelCatalogItem[];
}) {
  const [selectedDim, setSelectedDim] = useState<string>("structure_completeness");

  const dimension = SCORE_DIMENSIONS.find((d) => d.key === selectedDim) ?? SCORE_DIMENSIONS[0];

  const data = useMemo(() => {
    return cells.map((cell, idx) => ({
      name: getModelLabel(cell, modelCatalog),
      score: getScore(cell, selectedDim),
      jobId: cell.jobId || cell.job_id,
      color: MODEL_COLORS[idx % MODEL_COLORS.length],
    }));
  }, [cells, modelCatalog, selectedDim]);

  const hasData = data.some((d) => d.score > 0);

  return (
    <div className="compare-bar-wrapper">
      <div className="compare-bar-controls">
        <label>
          <span>选择维度：</span>
          <select
            className="compare-dim-select"
            value={selectedDim}
            onChange={(e) => setSelectedDim(e.target.value)}
          >
            {SCORE_DIMENSIONS.map((dim) => (
              <option key={dim.key} value={dim.key}>{dim.label}</option>
            ))}
          </select>
        </label>
        <span className="compare-bar-hint">
          当前指标：<strong>{dimension.label}</strong>
        </span>
      </div>

      {!hasData ? (
        <div className="compare-chart-empty">
          <p>该维度暂无评分数据。</p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={350}>
          <BarChart data={data} margin={{ top: 20, right: 20, left: 0, bottom: 20 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis 
              dataKey="name" 
              tick={{ fill: "rgba(255,255,255,0.85)", fontSize: 12 }}
            />
            <YAxis 
              domain={[0, 5]} 
              tickCount={6}
              tick={{ fill: "rgba(255,255,255,0.85)", fontSize: 12 }}
              label={{ value: "评分 (1-5)", angle: -90, position: "insideLeft", fill: "rgba(255,255,255,0.6)" }}
            />
            <Tooltip 
              contentStyle={{
                background: "rgba(20,20,30,0.95)",
                border: "1px solid rgba(255,255,255,0.2)",
                borderRadius: 8,
                color: "#fff",
              }}
              cursor={{ fill: "rgba(255,255,255,0.05)" }}
            />
            <Bar dataKey="score" radius={[4, 4, 0, 0]}>
              {data.map((entry, idx) => (
                <Cell key={idx} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      )}

      {/* 全维度小条形图概览 */}
      <div className="compare-bar-overview">
        <h4>所有维度概览</h4>
        <div className="compare-bar-overview-grid">
          {SCORE_DIMENSIONS.map((dim) => {
            const dimData = cells.map((cell, idx) => ({
              name: getModelLabel(cell, modelCatalog),
              score: getScore(cell, dim.key),
              color: MODEL_COLORS[idx % MODEL_COLORS.length],
            }));
            const dimHasData = dimData.some((d) => d.score > 0);
            return (
              <div key={dim.key} className="compare-bar-mini">
                <span className="compare-bar-mini-title">{dim.label}</span>
                {dimHasData ? (
                  <ResponsiveContainer width="100%" height={120}>
                    <BarChart data={dimData}>
                      <YAxis domain={[0, 5]} hide />
                      <Bar dataKey="score" radius={[2, 2, 0, 0]}>
                        {dimData.map((entry, idx) => (
                          <Cell key={idx} fill={entry.color} />
                        ))}
                      </Bar>
                      <Tooltip
                        contentStyle={{
                          background: "rgba(20,20,30,0.95)",
                          border: "1px solid rgba(255,255,255,0.2)",
                          borderRadius: 6,
                          fontSize: 11,
                          color: "#fff",
                        }}
                        cursor={{ fill: "rgba(255,255,255,0.05)" }}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="compare-bar-mini-empty">无数据</div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ─────────────── 并排预览 ───────────────

type AssetItem = {
  url: string;
  kind: "image" | "pointcloud" | "video" | "other";
  label: string;
};

function pickPrimaryAsset(cell: CompareModelCell, apiBase: string): AssetItem | null {
  const visuals = cell.visuals || [];
  const arts = cell.primaryArtifacts || cell.primary_artifacts || [];
  
  // 优先取核心产物
  for (const art of arts) {
    const path = (art as any).relativePath || (art as any).relative_path;
    if (!path) continue;
    const kind = (art as any).kind;
    const url = path.startsWith("http") ? path : `${apiBase}/${path.replace(/^\//, "").replace(/\\/g, "/")}`;
    if (kind === "pointcloud") {
      return { url, kind: "pointcloud", label: (art as any).label || (art as any).name || "点云" };
    }
    if (kind === "image") {
      return { url, kind: "image", label: (art as any).label || (art as any).name || "图像" };
    }
    if (kind === "video") {
      return { url, kind: "video", label: (art as any).label || (art as any).name || "视频" };
    }
  }
  
  // 退而求其次：visuals 第一个图片/视频
  for (const v of visuals) {
    if (v.kind === "image" || v.kind === "video") {
      const url = v.url.startsWith("http") ? v.url : `${apiBase}/${v.url.replace(/^\//, "")}`;
      return { url, kind: v.kind as any, label: v.name };
    }
  }
  
  // 检查 outputs 里的 ply
  const outputs = cell.outputs || [];
  for (const o of outputs) {
    if (o.is_pointcloud) {
      const url = o.url.startsWith("http") ? o.url : `${apiBase}/${o.url.replace(/^\//, "")}`;
      return { url, kind: "pointcloud", label: o.display_name };
    }
  }
  
  return null;
}

export function CompareSideBySide({
  cells,
  modelCatalog,
  apiBase,
}: {
  cells: CompareModelCell[];
  modelCatalog: ModelCatalogItem[];
  apiBase: string;
}) {
  const items = useMemo(() => {
    return cells.map((cell, idx) => ({
      cell,
      label: getModelLabel(cell, modelCatalog),
      asset: pickPrimaryAsset(cell, apiBase),
      color: MODEL_COLORS[idx % MODEL_COLORS.length],
    }));
  }, [cells, modelCatalog, apiBase]);

  if (items.length === 0) {
    return <div className="compare-chart-empty"><p>暂无任务可对比。</p></div>;
  }

  // 自适应栅格列数
  const cols = Math.min(items.length, items.length <= 2 ? 2 : items.length <= 4 ? 2 : 3);

  return (
    <div 
      className="compare-side-by-side"
      style={{ gridTemplateColumns: `repeat(${cols}, 1fr)` }}
    >
      {items.map((item) => (
        <div key={item.cell.jobId || item.cell.job_id} className="compare-sbs-cell">
          <div 
            className="compare-sbs-header"
            style={{ borderLeft: `3px solid ${item.color}` }}
          >
            <strong>{item.label}</strong>
            <span className="compare-sbs-job">{item.cell.jobId || item.cell.job_id}</span>
          </div>
          <div className="compare-sbs-content">
            {!item.asset ? (
              <div className="compare-sbs-placeholder">
                <span>无可预览产物</span>
                <small>{item.cell.statusLabel || item.cell.status_label || item.cell.status}</small>
              </div>
            ) : item.asset.kind === "pointcloud" ? (
              <PointCloudViewer url={item.asset.url} height="320px" />
            ) : item.asset.kind === "image" ? (
              <img src={item.asset.url} alt={item.asset.label} className="compare-sbs-image" />
            ) : item.asset.kind === "video" ? (
              <video src={item.asset.url} controls className="compare-sbs-video" />
            ) : (
              <div className="compare-sbs-placeholder">
                <span>{item.asset.label}</span>
              </div>
            )}
          </div>
          <div className="compare-sbs-meta">
            <span>{item.asset?.label ?? "—"}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

// ─────────────── 综合对比面板 ───────────────

export type CompareChartTab = "radar" | "bar" | "sidebyside";

export function CompareChartsPanel({
  cells,
  modelCatalog,
  apiBase,
}: {
  cells: CompareModelCell[];
  modelCatalog: ModelCatalogItem[];
  apiBase: string;
}) {
  const [tab, setTab] = useState<CompareChartTab>("radar");

  if (cells.length === 0) {
    return null;
  }

  return (
    <section className="compare-charts-panel">
      <div className="compare-charts-tabs">
        <button
          type="button"
          className={`compare-tab ${tab === "radar" ? "active" : ""}`}
          onClick={() => setTab("radar")}
        >
          雷达图
        </button>
        <button
          type="button"
          className={`compare-tab ${tab === "bar" ? "active" : ""}`}
          onClick={() => setTab("bar")}
        >
          柱状图
        </button>
        <button
          type="button"
          className={`compare-tab ${tab === "sidebyside" ? "active" : ""}`}
          onClick={() => setTab("sidebyside")}
        >
          并排预览
        </button>
      </div>

      <div className="compare-charts-body">
        {tab === "radar" && <CompareRadarChart cells={cells} modelCatalog={modelCatalog} />}
        {tab === "bar" && <CompareBarChart cells={cells} modelCatalog={modelCatalog} />}
        {tab === "sidebyside" && <CompareSideBySide cells={cells} modelCatalog={modelCatalog} apiBase={apiBase} />}
      </div>
    </section>
  );
}
