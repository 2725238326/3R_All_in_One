/**
 * useAppState — 应用状态管理 Hook
 * 管理后端连接状态、模型目录、服务状态
 */
import { useState, useCallback, useMemo, useEffect } from "react";
import { invoke } from "@tauri-apps/api/core";
import type {
  AppState,
  BackendStatusPayload,
  DeploymentStatusPayload,
  DevelopmentLaneItem,
} from "../types";
import { API_BASE } from "../appConfig";
import { delay } from "../displayHelpers";

export type ServiceState = "starting" | "ready" | "degraded";

export interface UseAppStateReturn {
  appState: AppState | null;
  backendStatus: BackendStatusPayload | null;
  deploymentStatus: DeploymentStatusPayload | null;
  developmentLanes: DevelopmentLaneItem[];
  serviceState: ServiceState;
  serviceMessage: string;
  serviceReady: boolean;
  modelCatalog: AppState["modelCatalog"];
  modelContracts: AppState["modelContracts"];
  advisorState: AppState["advisor"];
  advisorReady: boolean;
  refreshAppState: () => Promise<AppState | undefined>;
  setServiceState: (state: ServiceState) => void;
  setServiceMessage: (message: string) => void;
  initializeBackend: () => Promise<void>;
  loadDeploymentStatus: (showError?: boolean) => Promise<void>;
}

export function useAppState(): UseAppStateReturn {
  const [appState, setAppState] = useState<AppState | null>(null);
  const [backendStatus, setBackendStatus] = useState<BackendStatusPayload | null>(null);
  const [deploymentStatus, setDeploymentStatus] = useState<DeploymentStatusPayload | null>(null);
  const [developmentLanes, setDevelopmentLanes] = useState<DevelopmentLaneItem[]>([]);
  const [serviceState, setServiceState] = useState<ServiceState>("starting");
  const [serviceMessage, setServiceMessage] = useState("正在准备本地服务...");

  const modelCatalog = useMemo(() => appState?.modelCatalog ?? [], [appState]);
  const modelContracts = useMemo(() => appState?.modelContracts ?? {}, [appState]);
  const advisorState = useMemo(() => appState?.advisor ?? {
    enabled: false,
    configured: false,
    base_url: "",
    model: "",
    has_api_key: false,
    message: "辅助评估尚未配置。"
  }, [appState]);

  const serviceReady = serviceState === "ready";
  const advisorReady = advisorState.enabled && advisorState.configured;

  const refreshAppState = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/api/app/state`);
      if (!response.ok) throw new Error(`请求失败：${response.status}`);
      const state: AppState = await response.json();
      setAppState(state);
      if (state.developmentLanes) setDevelopmentLanes(state.developmentLanes);
      return state;
    } catch (e) {
      console.error("Failed to refresh app state", e);
    }
  }, []);

  const loadDeploymentStatus = useCallback(async (showError = true) => {
    try {
      const response = await fetch(`${API_BASE}/api/deployment/status`);
      if (!response.ok) throw new Error(`请求失败：${response.status}`);
      const payload: DeploymentStatusPayload = await response.json();
      setDeploymentStatus(payload);
    } catch (error) {
      console.error("Failed to load deployment status", error);
    }
  }, []);

  const initializeBackend = useCallback(async () => {
    setServiceMessage("正在启动后端服务...");
    try {
      const status = await invoke<BackendStatusPayload>("ensure_backend");
      setBackendStatus(status);
      if (status.running) {
        setServiceMessage("后端已启动，正在加载数据...");
        // 等待后端完全就绪
        for (let i = 0; i < 10; i++) {
          try {
            const response = await fetch(`${API_BASE}/api/health`);
            if (response.ok) break;
          } catch {
            await delay(500);
          }
        }
      } else {
        setServiceState("degraded");
        setServiceMessage(status.message || "后端启动失败");
      }
    } catch (error) {
      console.error("Failed to initialize backend", error);
      setServiceState("degraded");
      setServiceMessage("后端初始化失败");
    }
  }, []);

  return {
    appState,
    backendStatus,
    deploymentStatus,
    developmentLanes,
    serviceState,
    serviceMessage,
    serviceReady,
    modelCatalog,
    modelContracts,
    advisorState,
    advisorReady,
    refreshAppState,
    setServiceState,
    setServiceMessage,
    initializeBackend,
    loadDeploymentStatus,
  };
}
