/**
 * SystemWorkbench — 系统面板组件
 * 显示本地服务状态、AI 助手配置、模型部署状态
 */
import type {
  BackendStatusPayload,
  DeploymentStatusPayload,
  AdvisorStatus,
} from "./types";
import type { ModelCatalogItem } from "./displayHelpers";
import { backendStatusText, modelDisplayName } from "./displayHelpers";
import { buildDeploymentComponentRows } from "./deploymentHelpers";
import { ResourceMonitor } from "./ResourceMonitor";

export interface SystemWorkbenchProps {
  backendStatus: BackendStatusPayload | null;
  serviceState: "starting" | "ready" | "degraded";
  serviceMessage: string;
  advisorState: AdvisorStatus;
  advisorReady: boolean;
  deploymentStatus: DeploymentStatusPayload | null;
  modelCatalog: ModelCatalogItem[];
  openAdvisorSettings: () => void;
  loadDeploymentStatus: (showError?: boolean, forceRefresh?: boolean) => void;
  selectedJobId: string | null;
  onRecommendParams?: (jobId: string) => void;
  onDiagnoseFailure?: (jobId: string) => void;
}

export function SystemWorkbench(props: SystemWorkbenchProps) {
  const deploymentRows = buildDeploymentComponentRows(props.deploymentStatus, props.modelCatalog);
  
  return (
    <div className="system-workspace">
      <div className="system-top-row">
        <div className="section-card">
          <div className="section-card-header">
            <h3 className="section-card-title">本地服务</h3>
            <span className={`section-card-badge ${props.serviceState === "ready" ? "success" : ""}`}>
              {props.serviceState === "ready" ? "运行中" : "检查中"}
            </span>
          </div>
          <div className="kv-row">
            <span className="kv-label">服务状态</span>
            <span className={`kv-value ${props.serviceState === "ready" ? "success" : ""}`}>
              {props.serviceMessage}
            </span>
          </div>
          <div className="kv-row">
            <span className="kv-label">后端进程</span>
            <span className="kv-value">{backendStatusText(props.backendStatus)}</span>
          </div>
        </div>

        <div className="section-card">
          <div className="section-card-header">
            <h3 className="section-card-title">AI 助手</h3>
            <span className={`section-card-badge ${props.advisorReady ? "success" : ""}`}>
              {props.advisorReady ? "已配置" : "未配置"}
            </span>
          </div>
          <div className="kv-row">
            <span className="kv-label">状态</span>
            <span className={`kv-value ${props.advisorReady ? "success" : "muted"}`}>
              {props.advisorReady ? `就绪 · ${props.advisorState.model}` : "未配置"}
            </span>
          </div>
          <div style={{ marginTop: "12px", display: "flex", gap: "8px", flexWrap: "wrap" }}>
            <button className="ghost-button small" onClick={props.openAdvisorSettings}>
              打开配置
            </button>
            {props.selectedJobId && props.advisorReady && (
              <>
                <button
                  className="ghost-button small"
                  onClick={() => props.selectedJobId && props.onRecommendParams?.(props.selectedJobId)}
                >
                  参数推荐
                </button>
                <button
                  className="ghost-button small"
                  onClick={() => props.selectedJobId && props.onDiagnoseFailure?.(props.selectedJobId)}
                >
                  故障诊断
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      <div className="section-card">
        <div className="section-card-header">
          <h3 className="section-card-title">模型部署状态</h3>
          <button 
            className="ghost-button small" 
            onClick={() => props.loadDeploymentStatus(true, true)}
          >
            刷新
          </button>
        </div>
        <div className="deployment-table">
          <div className="deployment-table-head">
            <span>模型</span>
            <span>目录</span>
            <span>环境</span>
            <span>文件</span>
            <span>权重</span>
          </div>
          {deploymentRows.map((row: any) => (
            <div className={`deployment-table-row ${row.tone}`} key={row.component}>
              <span className="deployment-model-name">
                {modelDisplayName(row.component, props.modelCatalog)}
              </span>
              <span>{row.directory}</span>
              <span>{row.env}</span>
              <span>{row.files}</span>
              <span>{row.checkpoints}</span>
            </div>
          ))}
        </div>
      </div>
      
      <ResourceMonitor />
    </div>
  );
}
