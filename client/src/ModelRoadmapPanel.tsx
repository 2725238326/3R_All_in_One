import { ModelSemanticChips, SummaryStat } from "./uiPrimitives";
import type { ModelCatalogItem } from "./displayHelpers";

export function ModelRoadmapPanel(props: {
  activeModels: ModelCatalogItem[];
  deferredModels: ModelCatalogItem[];
  compact?: boolean;
}) {
  const runnable = props.activeModels.filter((item) => item.runnable).length;
  const planned = props.activeModels.filter((item) => !item.runnable).length;

  return (
    <article className="panel model-roadmap-panel">
      <div className="section-head">
        <div>
          <span className="mini-label">模型路线</span>
          <h4>3R 接入与测评进度</h4>
          <p>当前主线集中在 MASt3R、MonST3R、Spann3R、Align3R、Fast3R、CUT3R；Pi3X、ZipMap、LingBot-Map 暂缓。</p>
        </div>
        <div className="model-roadmap-stats">
          <SummaryStat label="可运行" value={String(runnable)} />
          <SummaryStat label="待接入" value={String(planned)} />
        </div>
      </div>

      <div className="model-roadmap-list">
        {props.activeModels.map((item) => (
          <article className={`model-roadmap-item ${item.runnable ? "ready" : "planned"}`} key={item.value}>
            <div>
              <strong>{item.label}</strong>
              <p>{item.description}</p>
            </div>
            <ModelSemanticChips className="model-roadmap-meta" compact item={item} />
          </article>
        ))}
      </div>

      {!props.compact && props.deferredModels.length > 0 ? (
        <div className="deferred-model-strip">
          <span className="mini-label">暂缓预研</span>
          <p>{props.deferredModels.map((item) => item.label).join(" / ")}</p>
        </div>
      ) : null}
    </article>
  );
}
