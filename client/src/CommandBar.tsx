import { WorkspaceTab } from "./App";
import { StatusBadge } from "./uiPrimitives";

interface CommandBarProps {
  activeWorkspace: WorkspaceTab;
  serviceState: string;
  serviceStatusLabel: string;
  onRefresh: () => void;
  onCreateJob?: () => void;
  onAction?: (action: string) => void;
  title: string;
}

export function CommandBar({ activeWorkspace, serviceState, serviceStatusLabel, onRefresh, onCreateJob, onAction, title }: CommandBarProps) {
  return (
    <header className="command-bar">
      <div className="command-bar-left">
        <h2 style={{ fontSize: '18px', fontWeight: 600 }}>{title}</h2>
        <StatusBadge state={serviceState} label={serviceStatusLabel} />
      </div>
      <div className="command-bar-right">
        {activeWorkspace === "queue" && (
          <>
            <button className="primary-button small" onClick={onCreateJob}>新建任务</button>
            <button className="ghost-button small" onClick={onRefresh}>刷新</button>
          </>
        )}
        {activeWorkspace === "create" && (
          <>
            <button className="primary-button small" onClick={() => onAction?.("submit")}>启动任务</button>
            <button className="ghost-button small" onClick={() => onAction?.("clear")}>重置</button>
          </>
        )}
        {activeWorkspace === "inspect" && (
          <>
            <button className="ghost-button small" onClick={() => onAction?.("dispatch")}>运行</button>
            <button className="ghost-button small" onClick={() => onAction?.("retry")}>重试</button>
            <button className="ghost-button small danger" onClick={() => onAction?.("cancel")}>取消</button>
            <button className="ghost-button small" onClick={() => onAction?.("advisor")}>生成评估</button>
          </>
        )}
        {activeWorkspace === "samples" && (
          <>
            <button className="ghost-button small" onClick={() => onAction?.("export")}>导出报告</button>
            <button className="ghost-button small" onClick={onRefresh}>刷新</button>
          </>
        )}
        {activeWorkspace === "development" && (
          <>
            <button className="primary-button small" onClick={() => onAction?.("new_item")}>新增项</button>
          </>
        )}
        {activeWorkspace === "system" && (
          <>
            <button className="ghost-button small" onClick={() => onAction?.("diagnostics")}>刷新诊断</button>
            <button className="ghost-button small" onClick={() => onAction?.("test_advisor")}>测试 AI</button>
          </>
        )}
      </div>
    </header>
  );
}
