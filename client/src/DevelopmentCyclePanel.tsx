import { PanelTitle, StatusBadge } from "./uiPrimitives";
import { devLanePriorityTone, devLaneStatusLabel } from "./displayHelpers";
import type { DevelopmentLaneItem } from "./types";

interface DevelopmentCyclePanelProps {
  items: DevelopmentLaneItem[];
  errorMessage?: string | null;
}

export function DevelopmentCyclePanel({ items, errorMessage }: DevelopmentCyclePanelProps) {
  const activeItems = items.filter(item => item.status !== "merged" && item.status !== "deferred");
  
  return (
    <article className="panel development-cycle-panel">
      <PanelTitle eyebrow="Cycle" title="研发周期追踪" />
      {errorMessage ? <div className="empty-state">{errorMessage}</div> : null}
      <div className="dev-cycle-grid">
        {activeItems.length > 0 ? (
          activeItems.map((item) => (
            <div key={item.id} className="dev-cycle-item">
              <div className="dev-cycle-head">
                <StatusBadge state={devLanePriorityTone(item.priority)} label={item.priority} />
                <strong>{item.title}</strong>
              </div>
              <div className="dev-cycle-body">
                <div className="dev-cycle-meta">
                  <span className="mini-label">{devLaneStatusLabel(item.status)}</span>
                  <p>{item.nextAction}</p>
                </div>
                {item.blockers.length > 0 && (
                  <div className="dev-cycle-blockers">
                    <span className="mini-label danger">阻塞</span>
                    <p>{item.blockers.join(", ")}</p>
                  </div>
                )}
              </div>
            </div>
          ))
        ) : (
          <div className="empty-state">当前无活跃研发项目。</div>
        )}
      </div>
    </article>
  );
}
