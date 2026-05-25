import {
  findModelCatalogItem,
  formatSourceTypeList,
  modelFamilyLabel,
  paramFamilyLabel,
  runnerStatusLabel
} from "./displayHelpers";
import type { ModelCatalogItem } from "./displayHelpers";

export function PanelTitle(props: { eyebrow: string; title: string }) {
  return (
    <div className="panel-title">
      <span>{props.eyebrow}</span>
      <h2>{props.title}</h2>
    </div>
  );
}

export function MiniStat(props: { label: string; value: number | string }) {
  return (
    <div className="mini-stat">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </div>
  );
}

export function FilterPill(props: {
  active: boolean;
  count: number;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      className={`filter-pill ${props.active ? "active" : ""}`}
      onClick={props.onClick}
      type="button"
    >
      {props.label}
      <span>{props.count}</span>
    </button>
  );
}

export function MessageBanner(props: { kind: "info" | "error"; message: string }) {
  return (
    <section className={`message-banner ${props.kind}`}>
      <strong>{props.kind === "info" ? "状态" : "需要处理"}</strong>
      <span>{props.message}</span>
    </section>
  );
}

export function StatusBadge(props: { state: string; label: string }) {
  return (
    <span className={`status-badge ${props.state}`}>
      <span className="status-dot" />
      {props.label}
    </span>
  );
}

export function ModelSemanticChips(props: {
  catalog?: ModelCatalogItem[];
  className?: string;
  compact?: boolean;
  item?: ModelCatalogItem | null;
  model?: string;
  showParamFamily?: boolean;
}) {
  const item = props.item ?? (props.model && props.catalog ? findModelCatalogItem(props.model, props.catalog) : null);
  if (!item) {
    return (
      <div className={`model-semantic-chips ${props.compact ? "compact" : ""} ${props.className ?? ""}`}>
        <span>目录未登记</span>
      </div>
    );
  }
  return (
    <div className={`model-semantic-chips ${props.compact ? "compact" : ""} ${props.className ?? ""}`}>
      <span>{modelFamilyLabel(item.family)}</span>
      {props.showParamFamily ? <span>参数族：{paramFamilyLabel(item.param_family)}</span> : null}
      <span>输入：{formatSourceTypeList(item.source_types)}</span>
      <span>{runnerStatusLabel(item.runner_status)}</span>
      <span className={item.runnable ? "runnable" : "catalog"}>{item.runnable ? "可创建" : "目录模型"}</span>
    </div>
  );
}

export function SummaryStat(props: { label: string; value: string }) {
  return (
    <div className="summary-stat">
      <span>{props.label}</span>
      <strong>{props.value}</strong>
    </div>
  );
}
