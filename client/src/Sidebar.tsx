import type React from "react";
import { WorkspaceTab } from "./App";
import {
  ListTodo,
  Plus,
  FlaskConical,
  LayoutGrid,
  Bot,
  Rocket,
  HardDrive,
  Settings,
  Activity,
  LayoutDashboard,
  type LucideIcon
} from "lucide-react";

interface SidebarProps {
  activeWorkspace: WorkspaceTab;
  onWorkspaceChange: (tab: WorkspaceTab) => void;
  summary: {
    total: number;
    running: number;
    pending?: number;
    finished?: number;
  };
}

export function Sidebar({ activeWorkspace, onWorkspaceChange, summary }: SidebarProps) {
  const navItems: Array<{ key: WorkspaceTab; label: string; Icon: LucideIcon; badge?: () => React.ReactNode }> = [
    { 
      key: "queue", 
      label: "工作队列", 
      Icon: ListTodo,
      badge: () => summary.running > 0 ? (
        <span className="nav-badge running">{summary.running}</span>
      ) : summary.total > 0 ? (
        <span className="nav-badge">{summary.total}</span>
      ) : null
    },
    { key: "create", label: "新建任务", Icon: Plus },
    { key: "compare", label: "对比面板", Icon: FlaskConical },
    { key: "samples", label: "样例矩阵", Icon: LayoutGrid },
    { key: "development", label: "研发加速", Icon: Rocket },
    { key: "agent", label: "Agent 编排", Icon: Bot },
    { key: "experiments", label: "实验编排", Icon: FlaskConical },
    { key: "storage", label: "存储管理", Icon: HardDrive },
    { key: "system", label: "系统配置", Icon: Settings },
    { key: "dashboard", label: "仪表板", Icon: LayoutDashboard },
  ];

  return (
    <aside className="workspace-sidebar">
      <div className="sidebar-header">
        <div className="brand-mark">K</div>
        <div className="sidebar-brand">
          <strong>KYKT Vision</strong>
          <span className="sidebar-subtitle">Local Workbench</span>
        </div>
      </div>

      {/* Quick Stats */}
      {summary.running > 0 && (
        <div className="sidebar-status">
          <Activity size={12} className="status-pulse" />
          <span>{summary.running} 任务运行中</span>
        </div>
      )}

      <nav className="sidebar-nav">
        {navItems.map((item) => (
          <button
            key={item.key}
            className={`nav-item ${activeWorkspace === item.key ? "active" : ""}`}
            onClick={() => onWorkspaceChange(item.key)}
          >
            <item.Icon size={16} strokeWidth={1.75} />
            <span>{item.label}</span>
            {item.badge?.()}
          </button>
        ))}
      </nav>

      <div className="sidebar-footer">
        <span className="sidebar-version">v0.5.0</span>
      </div>
    </aside>
  );
}
