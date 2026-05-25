import { PanelTitle } from "./uiPrimitives";
import { devLaneCategoryLabel } from "./displayHelpers";
import type { DevelopmentLaneItem } from "./types";

interface ResearchAccelerationPanelProps {
  items: DevelopmentLaneItem[];
  creating?: boolean;
  errorMessage?: string | null;
  onCreateSeed?: (category: DevelopmentLaneItem["category"]) => Promise<void> | void;
}

export function ResearchAccelerationPanel({ items, creating = false, errorMessage, onCreateSeed }: ResearchAccelerationPanelProps) {
  const researchItems = items.filter(item => 
    item.category === "paper_reproduction" || 
    item.category === "prototype" || 
    item.category === "evaluation"
  );

  return (
    <article className="panel research-acceleration-panel">
      <PanelTitle eyebrow="Acceleration" title="研究与原型加速" />
      <div className="research-acceleration-info">
        <p className="status-honest-note">
          <strong>状态提示：</strong>研发车道已接入本地持久化。论文复现、原型和评测设计会写入后端 manifest。
        </p>
      </div>
      {errorMessage ? <div className="empty-state">{errorMessage}</div> : null}
      <div className="research-lane-grid">
        {researchItems.map((item) => (
          <div key={item.id} className="research-lane-card">
            <div className="research-lane-head">
              <span className="mini-label">{devLaneCategoryLabel(item.category)}</span>
              <strong>{item.title}</strong>
            </div>
            <div className="research-lane-next">
              <span className="mini-label">Next Action</span>
              <p>{item.nextAction}</p>
            </div>
            <div className="research-lane-target">
              <span className="mini-label">合入目标</span>
              <code>{item.mergeTarget ?? "research_context"}</code>
            </div>
          </div>
        ))}
      </div>
      <div className="seed-categories-strip">
        <span className="mini-label">快速启动种子</span>
        <div className="seed-pills">
          <button className="ghost-button small" disabled={creating} onClick={() => onCreateSeed?.("paper_reproduction")} type="button">
            论文复现
          </button>
          <button className="ghost-button small" disabled={creating} onClick={() => onCreateSeed?.("model_runner")} type="button">
            新 3R 模型 Runner
          </button>
          <button className="ghost-button small" disabled={creating} onClick={() => onCreateSeed?.("prototype")} type="button">
            UI/评测流原型
          </button>
          <button className="ghost-button small" disabled={creating} onClick={() => onCreateSeed?.("evaluation")} type="button">
            研究报告/实验设计
          </button>
        </div>
      </div>
    </article>
  );
}
