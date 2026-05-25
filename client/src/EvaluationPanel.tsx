import { useEffect, useState } from "react";
import type { EvaluationPayload } from "./types";
import { formatDateTime } from "./displayHelpers";

export function EvaluationPanel(props: {
  evaluation: EvaluationPayload | null;
  jobId: string;
  saving: boolean;
  onSave: (jobId: string, payload: EvaluationPayload) => Promise<void>;
}) {
  const [draft, setDraft] = useState<EvaluationPayload>({ job_id: props.jobId, notes: "" });

  useEffect(() => {
    setDraft({
      job_id: props.jobId,
      structure_completeness: props.evaluation?.structure_completeness ?? null,
      trajectory_stability: props.evaluation?.trajectory_stability ?? null,
      noise: props.evaluation?.noise ?? props.evaluation?.noise_control ?? null,
      dynamic_handling: props.evaluation?.dynamic_handling ?? null,
      depth_continuity: props.evaluation?.depth_continuity ?? props.evaluation?.depth_consistency ?? null,
      presentation_usability: props.evaluation?.presentation_usability ?? null,
      notes: props.evaluation?.notes ?? ""
    });
  }, [props.evaluation, props.jobId]);

  const fields: Array<{ key: keyof EvaluationPayload; label: string }> = [
    { key: "structure_completeness", label: "结构完整性" },
    { key: "trajectory_stability", label: "轨迹稳定性" },
    { key: "noise", label: "噪声控制" },
    { key: "dynamic_handling", label: "动态处理" },
    { key: "depth_continuity", label: "深度连续性" },
    { key: "presentation_usability", label: "展示可用性" }
  ];

  return (
    <form
      className="evaluation-form"
      onSubmit={(event) => {
        event.preventDefault();
        void props.onSave(props.jobId, draft);
      }}
    >
      <div className="evaluation-grid">
        {fields.map((field) => (
          <label className="field" key={String(field.key)}>
            <span>{field.label}</span>
            <select
              value={draft[field.key] == null ? "" : String(draft[field.key])}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  [field.key]: event.target.value ? Number(event.target.value) : null
                }))
              }
            >
              <option value="">未评分</option>
              <option value="1">1</option>
              <option value="2">2</option>
              <option value="3">3</option>
              <option value="4">4</option>
              <option value="5">5</option>
            </select>
          </label>
        ))}
      </div>
      <label className="field">
        <span>备注</span>
        <textarea
          rows={4}
          value={draft.notes ?? ""}
          onChange={(event) => setDraft((current) => ({ ...current, notes: event.target.value }))}
          placeholder="记录结构问题、轨迹漂移、动态区域表现、适不适合展示。"
        />
      </label>
      <div className="evaluation-actions">
        <span className="muted-text">
          {props.evaluation?.updated_at ? `上次保存：${formatDateTime(props.evaluation.updated_at)}` : "尚未保存人工评分。"}
        </span>
        <button className="ghost-button small" disabled={props.saving} type="submit">
          {props.saving ? "保存中..." : "保存评分"}
        </button>
      </div>
    </form>
  );
}
