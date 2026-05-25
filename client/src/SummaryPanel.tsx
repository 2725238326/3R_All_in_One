import type { ResultSummary } from "./types";
import { formatDuration } from "./displayHelpers";
import { roleLabel } from "./sampleMatrixHelpers";
import { SummaryStat } from "./uiPrimitives";

export function SummaryPanel(props: { summary: ResultSummary | null }) {
  if (!props.summary) {
    return <span className="muted-text">完成后自动生成摘要。</span>;
  }

  const highlights = props.summary.highlights ?? [];
  const nextActions = props.summary.next_actions ?? [];
  const artifactGroups = props.summary.artifact_groups ?? [];
  const primaryArtifacts = props.summary.primary_artifacts ?? [];
  const sceneMeta = props.summary.scene_meta ?? {};
  const sceneStats = [
    typeof sceneMeta["artifact_count"] === "number" ? { label: "远端整理", value: String(sceneMeta["artifact_count"]) } : null,
    typeof sceneMeta["glb_count"] === "number" ? { label: "GLB", value: String(sceneMeta["glb_count"]) } : null,
    typeof sceneMeta["frame_preview_count"] === "number" ? { label: "帧预览", value: String(sceneMeta["frame_preview_count"]) } : null,
    typeof sceneMeta["dynamic_mask_count"] === "number" ? { label: "动态Mask", value: String(sceneMeta["dynamic_mask_count"]) } : null,
    typeof sceneMeta["n_points"] === "number" ? { label: "点数", value: String(sceneMeta["n_points"]) } : null,
    typeof sceneMeta["input_count"] === "number" ? { label: "输入", value: String(sceneMeta["input_count"]) } : null
  ].filter(Boolean) as Array<{ label: string; value: string }>;

  return (
    <div className="summary-panel">
      <div className="summary-strip">
        <SummaryStat label="状态" value={props.summary.status_label} />
        <SummaryStat label="耗时" value={formatDuration(props.summary.duration_seconds ?? null)} />
        <SummaryStat label="输入" value={String(props.summary.inputs?.count ?? 0)} />
        <SummaryStat label="产物" value={String(props.summary.artifacts?.length ?? 0)} />
      </div>
      {sceneStats.length > 0 ? (
        <div className="summary-strip secondary">
          {sceneStats.map((item) => (
            <SummaryStat key={item.label} label={item.label} value={item.value} />
          ))}
        </div>
      ) : null}
      {primaryArtifacts.length > 0 ? (
        <div className="summary-primary-list">
          <strong>核心检查对象</strong>
          {primaryArtifacts.map((item) => (
            <div className="summary-primary-item" key={`${item.role}-${item.relative_path}`}>
              <span>{item.label || roleLabel(item.role)}</span>
              <p>{item.name}</p>
            </div>
          ))}
        </div>
      ) : null}
      {artifactGroups.length > 0 ? (
        <div className="summary-group-grid">
          {artifactGroups.map((item) => (
            <div className="summary-group-item" key={item.key}>
              <span>{item.label}</span>
              <strong>{item.count}</strong>
            </div>
          ))}
        </div>
      ) : null}
      {highlights.length > 0 ? (
        <ul>
          {highlights.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
      {nextActions.length > 0 ? (
        <ul>
          {nextActions.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
