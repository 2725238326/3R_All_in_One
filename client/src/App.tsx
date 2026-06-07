import { FormEvent, KeyboardEvent as ReactKeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useAppStore } from "./store/appStore";
import type {
  AdvisorConfig,
  AdvisorDiagnostics,
  AdvisorProvider,
  AdvisorStatus,
  AppState,
  BackendStatusPayload,
  BatchCompareResponse,
  BatchJobsResponse,
  ComparePacket,
  DeploymentStatusPayload,
  DevelopmentLaneItem,
  EvaluationPayload,
  InspectionPacket,
  JobPayload,
  JobsListPayload,
  ModelContract,
  ResultContract,
  SamplesPayload,
  ValidationCreateResponse
} from "./types";
import { API_BASE } from "./appConfig";
import { uploadWithProgress } from "./uploadProgress";
import type { UploadProgress } from "./uploadProgress";
import {
  backendStatusText,
  delay,
  formatDateTime,
  formatParamLabel,
  friendlyError,
  modelDisplayName,
  runnerStatusLabel,
  serviceStatusLabel,
  sourceTypeLabel,
  statusLabel,
  statusModelLabel
} from "./displayHelpers";
import type { ModelCatalogItem } from "./displayHelpers";
import {
  buildDeploymentComponentRows,
  buildModelActionRows,
  formatDeploymentCacheStatus,
  formatDeploymentDirectoryStatus,
  formatDeploymentEnvSummary
} from "./deploymentHelpers";
import {
  formatFileSize,
  isImageLikeFile,
  isVideoLikeFile,
  pendingFileRoleLabel
} from "./fileHelpers";
import {
  batchActionLabel,
  buildActionMessage,
  buildAdvisorChecklist,
  buildCaptureChecklist,
  buildSystemChecklist,
  canDispatchJobStatus,
  isAdvisorSuggested,
  matchesJobQuery
} from "./workflowHelpers";
import type { BatchJobAction, JobListItem } from "./workflowHelpers";
import { ResourceMonitor } from "./ResourceMonitor";
import {
  MessageBanner,
  ModelSemanticChips,
  PanelTitle,
  StatusBadge,
  SummaryStat,
  MiniStat
} from "./uiPrimitives";
import { ModelRoadmapPanel } from "./ModelRoadmapPanel";
import { SampleMatrixPanel } from "./SampleMatrixPanel";
import { AdvisorWorkbench } from "./AdvisorWorkbench";
import { JobDetail } from "./JobDetail";
import type { PreviewAsset } from "./JobDetail";
import { currentStepLabel } from "./jobInspectorHelpers";
import { DevelopmentCyclePanel } from "./DevelopmentCyclePanel";
import { ResearchAccelerationPanel } from "./ResearchAccelerationPanel";
import { DynamicParamForm } from "./DynamicParamForm";
import { Sidebar } from "./Sidebar";
import { CommandBar } from "./CommandBar";
import { QueueWorkspace } from "./QueueWorkspace";
import { InspectWorkspace } from "./InspectWorkspace";
import { CompareBoard, CompareBoardInline } from "./CompareBoard";
import { filterRunnableModels, modelCompatibilityHint } from "./compareHelpers";
import { PointCloudViewer } from "./PointCloudViewer";
import { StoragePanel } from "./StoragePanel";
import { DashboardPanel } from "./DashboardPanel";
import { AgentWorkbench } from "./AgentWorkbench";

export type ServiceState = "starting" | "ready" | "degraded";
export type JobFilter = "all" | "running" | "attention" | "finished";
export type WorkspaceTab = "queue" | "create" | "inspect" | "samples" | "compare" | "development" | "agent" | "system" | "storage" | "dashboard";
export type CreateMode = "single" | "batch";

type JobSocketEvent =
  | { type: "jobs.snapshot"; jobs: JobListItem[] }
  | { type: "job.updated"; job_id: string; list_item: JobListItem; inspection?: InspectionPacket }
  | { type: "job.error"; job_id?: string; detail: string };

function jobSocketUrl(jobId: string) {
  return `${API_BASE.replace(/^http/i, "ws")}/ws/jobs/${encodeURIComponent(jobId)}`;
}

function applyJobListItem(current: JobListItem[], next: JobListItem) {
  const index = current.findIndex((item) => item.job.job_id === next.job.job_id);
  if (index === -1) {
    return [next, ...current];
  }
  const updated = [...current];
  updated[index] = next;
  return updated;
}

function App() {
  // Zustand store
  const {
    // 服务状态
    serviceState,
    serviceMessage,
    backendStatus,
    appState,
    // 任务状态
    jobs,
    selectedJobId,
    selectedInspection,
    // UI 状态
    activeWorkspace,
    submitting,
    actionKey,
    batchActionKey,
    batchSubmitting,
    errorMessage,
    infoMessage,
    previewAsset,
    uploadProgress,
    savingEvaluation,
    // 表单状态
    formState,
    files,
    createMode,
    selectedModels,
    batchAutoDispatch,
    // 数据面板
    samplesPayload,
    samplesError,
    developmentLanes,
    deploymentStatus,
    deploymentError,
    // 对比面板
    compareSampleId,
    comparePacket,
    compareLoading,
    compareError,
    // 顾问状态
    advisorModalOpen,
    advisorProviders,
    advisorDiagnostics,
    advisorForm,
    advisorConfigLoading,
    advisorConfigSaving,
    validationResponse,
    recommendModalOpen,
    recommendResult,
    diagnoseModalOpen,
    diagnoseResult,
    // Actions
    setServiceState,
    setServiceMessage,
    setBackendStatus,
    setAppState,
    setJobs,
    updateJobInList,
    setSelectedJobId,
    setSelectedInspection,
    setActiveWorkspace,
    setSubmitting,
    setActionKey,
    setBatchActionKey,
    setBatchSubmitting,
    setErrorMessage,
    setInfoMessage,
    setPreviewAsset,
    setUploadProgress,
    setSavingEvaluation,
    setFormState,
    resetFormState,
    setFiles,
    addFiles,
    clearFiles,
    setCreateMode,
    setSelectedModels,
    toggleModelSelection,
    setBatchAutoDispatch,
    setSamplesPayload,
    setSamplesError,
    setDevelopmentLanes,
    setDeploymentStatus,
    setCompareSampleId,
    setComparePacket,
    setCompareLoading,
    setCompareError,
    setAdvisorModalOpen,
    setAdvisorProviders,
    setAdvisorDiagnostics,
    setAdvisorForm,
    setAdvisorConfigLoading,
    setAdvisorConfigSaving,
    setValidationResponse,
    setRecommendModalOpen,
    setRecommendResult,
    setDiagnoseModalOpen,
    setDiagnoseResult,
  } = useAppStore();

  // 本地状态（尚未迁移到 store）
  const [deploymentLoading, setDeploymentLoading] = useState(false);
  const selectedJobIdRef = useRef<string | null>(null);

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

  const runnableModelCatalog = useMemo(() => modelCatalog.filter((item) => item.runnable), [modelCatalog]);
  const catalogOnlyModelCatalog = useMemo(() => modelCatalog.filter((item) => !item.runnable), [modelCatalog]);

  const selectedModelCatalog = useMemo(() => modelCatalog.find((item) => item.value === formState.model) ?? null, [formState.model, modelCatalog]);
  const selectedModelContract = useMemo(() => modelContracts[formState.model] ?? null, [formState.model, modelContracts]);
  const selectedModelSourceTypes = useMemo(() => selectedModelContract?.allowedSourceTypes ?? selectedModelCatalog?.source_types ?? [], [selectedModelCatalog, selectedModelContract]);
  const selectedModelLaunchBlocker = useMemo(() => selectedModelContract?.launchBlocker ?? selectedModelCatalog?.launch_blocker ?? null, [selectedModelCatalog, selectedModelContract]);

  const summary = useMemo(() => ({
    total: jobs.length,
    running: jobs.filter((item) => item.job.status === "running").length,
    finished: jobs.filter((item) => item.job.status === "finished").length,
    failed: jobs.filter((item) => item.job.status === "failed").length,
    cancelled: jobs.filter((item) => item.job.status === "cancelled").length
  }), [jobs]);

  const pendingImageCount = useMemo(() => files.filter((file) => isImageLikeFile(file)).length, [files]);
  const pendingVideoCount = useMemo(() => files.filter((file) => isVideoLikeFile(file)).length, [files]);
  const pendingTotalSize = useMemo(() => files.reduce((total, file) => total + file.size, 0), [files]);
  const pendingTypeSummary = useMemo(() => [
    pendingImageCount > 0 ? `图片 ${pendingImageCount}` : null,
    pendingVideoCount > 0 ? `视频 ${pendingVideoCount}` : null,
  ].filter(Boolean).join(" / ") || "暂无", [pendingImageCount, pendingVideoCount]);

  const batchCompatibleModels = useMemo(() => 
    filterRunnableModels(modelCatalog, formState.source_type),
    [modelCatalog, formState.source_type]
  );

  const batchModelHints = useMemo(() => {
    const hints: Record<string, string | null> = {};
    for (const m of selectedModels) {
      hints[m] = modelCompatibilityHint(m, formState.source_type, modelCatalog);
    }
    return hints;
  }, [selectedModels, formState.source_type, modelCatalog]);

  const batchHasBlockers = useMemo(() => 
    selectedModels.some((m) => batchModelHints[m] !== null),
    [selectedModels, batchModelHints]
  );

  async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${path}`, init);
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.detail || `请求失败：${response.status}`);
    }
    return response.json();
  }

  async function refreshAppState() {
    try {
      const state = await fetchJson<AppState>("/api/app/state");
      setAppState(state);
      if (state.developmentLanes) setDevelopmentLanes(state.developmentLanes);
      return state;
    } catch (e) {
      console.error("Failed to refresh app state", e);
    }
  }

  async function loadJobs(showError = true) {
    try {
      const payload = await fetchJson<JobsListPayload>("/api/jobs");
      setJobs(payload.jobs);
      setServiceState("ready");
      setServiceMessage("本地服务已就绪");
    } catch (error) {
      if (showError) setErrorMessage(friendlyError(error, "加载任务列表失败。"));
      setServiceState("degraded");
      setServiceMessage("本地服务连接异常");
    }
  }

  async function loadSamples(showError = true) {
    try {
      const payload = await fetchJson<SamplesPayload>("/api/samples");
      setSamplesPayload(payload);
    } catch (error) {
      if (showError) console.error("Samples API error", error);
    }
  }

  async function loadDeploymentStatus(showError = true, refresh = false) {
    setDeploymentLoading(true);
    try {
      const payload = await fetchJson<DeploymentStatusPayload>(`/api/deployment/status${refresh ? "?refresh=true" : ""}`);
      setDeploymentStatus(payload);
    } catch (error) {
      if (showError) setErrorMessage(friendlyError(error, "远端部署状态读取失败。"));
    } finally {
      setDeploymentLoading(false);
    }
  }

  async function loadDesktopBackendStatus() {
    try {
      const status = await invoke<BackendStatusPayload>("backend_status");
      setBackendStatus(status);
    } catch {
      setBackendStatus(null);
    }
  }

  useEffect(() => {
    selectedJobIdRef.current = selectedJobId;
  }, [selectedJobId]);

  useEffect(() => {
    loadDesktopBackendStatus();
    refreshAppState();
    loadJobs();
    loadSamples();

    const statusInterval = setInterval(() => {
      loadDesktopBackendStatus();
    }, 8000);
    return () => clearInterval(statusInterval);
  }, []);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let closed = false;

    function connect() {
      socket = new WebSocket(jobSocketUrl("__all__"));
      socket.onopen = () => {
        setServiceState("ready");
        setServiceMessage("本地服务已就绪");
      };
      socket.onmessage = (event) => {
        const payload = JSON.parse(event.data) as JobSocketEvent;
        if (payload.type === "jobs.snapshot") {
          setJobs(payload.jobs);
          return;
        }
        if (payload.type === "job.updated") {
          setJobs(applyJobListItem(jobs, payload.list_item));
          if (payload.inspection && selectedJobIdRef.current === payload.job_id) {
            setSelectedInspection(payload.inspection);
          }
          return;
        }
        if (payload.type === "job.error") {
          console.warn("Job websocket error", payload.detail);
        }
      };
      socket.onclose = () => {
        if (!closed) {
          reconnectTimer = window.setTimeout(connect, 3000);
        }
      };
    }

    connect();
    return () => {
      closed = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, []);

  useEffect(() => {
    if (selectedJobId && activeWorkspace === "inspect") loadInspection(selectedJobId);
  }, [selectedJobId, activeWorkspace]);

  useEffect(() => {
    if (activeWorkspace === "create" && formState.model) validateLaunch();
  }, [activeWorkspace, formState.model, files.length]);

  async function validateLaunch() {
    try {
      const res = await fetchJson<ValidationCreateResponse>(`/api/models/${formState.model}/validate-create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sourceType: formState.source_type, fileCount: files.length })
      });
      setValidationResponse(res);
    } catch {
      setValidationResponse(null);
    }
  }

  function handleWorkspaceChange(tab: WorkspaceTab) {
    setActiveWorkspace(tab);
    setErrorMessage(null);
    setInfoMessage(null);
  }

  async function handleInspectJob(jobId: string) {
    setSelectedJobId(jobId);
    setActiveWorkspace("inspect");
    await loadInspection(jobId);
  }

  async function loadInspection(jobId: string, showError = true) {
    try {
      const packet = await fetchJson<InspectionPacket>(`/api/jobs/${jobId}/inspection`);
      setSelectedInspection(packet);
    } catch (error) {
      if (showError) setErrorMessage(friendlyError(error, "加载任务检视数据失败。"));
    }
  }

  async function loadComparePacket(sampleId: string, showError = true) {
    setCompareLoading(true);
    setCompareError(null);
    try {
      const packet = await fetchJson<ComparePacket>(`/api/compare/samples/${encodeURIComponent(sampleId)}`);
      setComparePacket(packet);
    } catch (error) {
      if (showError) setCompareError(friendlyError(error, "加载对比数据失败。"));
    } finally {
      setCompareLoading(false);
    }
  }

  async function handleBatchCompare(autoDispatch: boolean) {
    if (selectedModels.length < 1) {
      setErrorMessage("请至少选择一个模型。");
      return;
    }
    if (files.length === 0) {
      setErrorMessage("请先上传输入文件。");
      return;
    }
    if (batchHasBlockers) {
      setErrorMessage("部分模型不兼容当前输入类型。");
      return;
    }

    setBatchSubmitting(true);
    const formData = new FormData();
    formData.append("models", JSON.stringify(selectedModels));
    formData.append("source_type", formState.source_type);
    formData.append("notes", formState.notes);
    formData.append("auto_dispatch", autoDispatch ? "true" : "false");
    formData.append("params", JSON.stringify(formState.params));
    files.forEach(f => formData.append("files", f, f.name));

    try {
      const result = await fetchJson<BatchCompareResponse>("/api/compare/batches", {
        method: "POST",
        body: formData
      });
      setFiles([]);
      setSelectedModels([]);
      setCompareSampleId(result.sampleId);
      setComparePacket(result.compare);
      setActiveWorkspace("compare");
      setInfoMessage(`批量对比已创建：${result.models.length} 个任务，sample_id: ${result.sampleId}`);
      loadJobs(false);
    } catch (e) {
      setErrorMessage(friendlyError(e, "批量对比创建失败"));
    } finally {
      setBatchSubmitting(false);
    }
  }

  function toggleBatchModel(model: string) {
    toggleModelSelection(model);
  }

  function openCompareBoard(sampleId: string) {
    setCompareSampleId(sampleId);
    loadComparePacket(sampleId);
    setActiveWorkspace("compare");
  }

  const workspaceTitle = useMemo(() => {
    switch (activeWorkspace) {
      case "queue": return "任务队列";
      case "create": return createMode === "batch" ? "批量对比" : "新建任务";
      case "inspect": return `检视：${selectedJobId || "尚未选择"}`;
      case "samples": return "样例矩阵";
      case "compare": return `对比面板：${compareSampleId || "--"}`;
      case "development": return "研发加速";
      case "agent": return "Agent 编排";
      case "system": return "系统配置";
    }
  }, [activeWorkspace, selectedJobId, createMode, compareSampleId]);

  async function openAdvisorSettings() {
    setAdvisorConfigLoading(true);
    try {
      const [config, providers, diagnostics] = await Promise.all([
        fetchJson<AdvisorConfig>("/api/advisor/config"),
        fetchJson<AdvisorProvider[]>("/api/advisor/providers"),
        fetchJson<AdvisorDiagnostics>("/api/advisor/diagnostics")
      ]);
      setAdvisorForm(config);
      setAdvisorProviders(providers);
      setAdvisorDiagnostics(diagnostics);
      setAdvisorModalOpen(true);
    } catch (e) {
      setErrorMessage("无法读取 Advisor 配置");
    } finally {
      setAdvisorConfigLoading(false);
    }
  }

  async function saveAdvisorSettings(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setAdvisorConfigSaving(true);
    try {
      await fetchJson("/api/advisor/config", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(advisorForm),
      });
      await refreshAppState();
      setAdvisorModalOpen(false);
      setInfoMessage("Advisor 配置已更新");
    } catch (e) {
      setErrorMessage("保存配置失败");
    } finally {
      setAdvisorConfigSaving(false);
    }
  }

  async function handleCommandAction(action: string) {
    if (action === "submit") handleCreateJob();
    if (action === "clear") {
      setFiles([]);
      setFormState({ notes: "", params: {} });
    }
    if (action === "dispatch" && selectedJobId) postJobAction(`/api/jobs/${selectedJobId}/dispatch`, "dispatch");
    if (action === "retry" && selectedJobId) postJobAction(`/api/jobs/${selectedJobId}/retry`, "retry");
    if (action === "cancel" && selectedJobId) postJobAction(`/api/jobs/${selectedJobId}/cancel`, "cancel");
    if (action === "advisor" && selectedJobId) postJobAction(`/api/jobs/${selectedJobId}/advisor/evaluate`, "advisor");
    if (action === "diagnostics") loadDeploymentStatus(true, true);
    if (action === "test_advisor") {
      try {
        await fetchJson("/api/advisor/test", { method: "POST" });
        setInfoMessage("AI 助手连接测试成功");
      } catch (e) {
        setErrorMessage("AI 连接测试失败");
      }
    }
  }

  async function postJobAction(path: string, key: string) {
    setActionKey(key);
    try {
      const payload = await fetchJson<JobPayload>(path, { method: "POST" });
      setInfoMessage(buildActionMessage(key, payload.job.job_id));
      setJobs(applyJobListItem(jobs, { job: payload.job, phase_display: payload.phase_display }));
      if (selectedJobId === payload.job.job_id) {
        loadInspection(selectedJobId, false);
      }
    } catch (e) {
      setErrorMessage("执行操作失败");
    } finally {
      setActionKey(null);
    }
  }

  async function postBatchJobAction(action: BatchJobAction, jobIds: string[]) {
    if (jobIds.length === 0) return;
    setBatchActionKey(action);
    const path = action === "cancel" ? "/api/jobs/batch-cancel" : "/api/jobs/batch-dispatch";
    try {
      const payload = await fetchJson<BatchJobsResponse>(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_ids: jobIds }),
      });
      const successful = payload.results.filter((item) => item.success);
      if (action === "dispatch") {
        setInfoMessage(`已派发 ${successful.length} 个任务`);
      } else if (action === "cancel") {
        setInfoMessage(`已取消 ${successful.length} 个任务`);
      }
      loadJobs();
    } catch (e: any) {
      setErrorMessage(e?.message || "执行批量操作失败");
    } finally {
      setBatchActionKey(null);
    }
  }

  async function handleBatchDelete(jobIds: string[]) {
    if (jobIds.length === 0) return;
    setBatchActionKey("delete");
    try {
      const payload = await fetchJson<BatchJobsResponse>("/api/jobs/batch-delete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_ids: jobIds }),
      });
      const successful = payload.results.filter((item) => item.success);
      setInfoMessage(`已删除 ${successful.length} 个任务`);
      loadJobs();
    } catch (e: any) {
      setErrorMessage(e?.message || "批量删除失败");
    } finally {
      setBatchActionKey(null);
    }
  }

  async function handleRecommendParams(jobId: string) {
    try {
      const res = await fetch(`${API_BASE}/api/advisor/jobs/${jobId}/recommend`);
      if (!res.ok) throw new Error("参数推荐失败");
      const data = await res.json();
      setRecommendResult(data);
      setRecommendModalOpen(true);
    } catch (e: any) {
      setErrorMessage(e?.message || "参数推荐失败");
    }
  }

  async function handleDiagnoseFailure(jobId: string) {
    try {
      const res = await fetch(`${API_BASE}/api/advisor/jobs/${jobId}/diagnose`);
      if (!res.ok) throw new Error("故障诊断失败");
      const data = await res.json();
      setDiagnoseResult(data);
      setDiagnoseModalOpen(true);
    } catch (e: any) {
      setErrorMessage(e?.message || "故障诊断失败");
    }
  }

  async function handleCreateJob() {
    if (selectedModelLaunchBlocker) {
      setErrorMessage(selectedModelLaunchBlocker);
      return;
    }
    if (validationResponse && !validationResponse.ok) {
      setErrorMessage(validationResponse.errors.join("；"));
      return;
    }

    setSubmitting(true);
    setUploadProgress(0);
    const formData = new FormData();
    formData.append("model", formState.model);
    formData.append("source_type", formState.source_type);
    formData.append("notes", formState.notes);
    formData.append("params", JSON.stringify(formState.params));
    files.forEach(f => formData.append("files", f, f.name));

    try {
      const payload = await uploadWithProgress<JobPayload>({
        url: "/api/jobs",
        formData,
        onProgress: (p: UploadProgress) => setUploadProgress(p.percent),
      });
      setFiles([]);
      handleInspectJob(payload.job.job_id);
      setInfoMessage(`任务 ${payload.job.job_id} 已创建。`);
    } catch (e) {
      setErrorMessage(friendlyError(e, "创建任务失败"));
    } finally {
      setSubmitting(false);
      setUploadProgress(null);
    }
  }

  function updateFormField(key: string, value: any) {
    if (key === "model" || key === "source_type" || key === "notes") {
      setFormState({ [key]: value });
    } else {
      setFormState({
        params: { ...formState.params, [key]: value }
      });
    }
  }

  async function updateModel(value: string) {
    setFormState({ model: value, params: {} });
    if (!modelContracts[value]) {
      try {
        const contract = await fetchJson<ModelContract>(`/api/models/${value}/contract`);
        const sourceTypes = contract.allowedSourceTypes || (contract as any).sourceTypes || [];
        const fields = contract.paramSchema?.fields || [];
        setAppState(appState ? { ...appState, modelContracts: { ...appState.modelContracts, [value]: contract } } : null);
        setFormState({
          source_type: sourceTypes[0] || "images",
          params: fields.reduce((acc, f) => ({ ...acc, [f.key]: f.default }), {})
        });
      } catch (e) {
        setErrorMessage("加载模型契约失败");
      }
    }
  }

  return (
    <div className="app-shell">
      <Sidebar activeWorkspace={activeWorkspace} onWorkspaceChange={handleWorkspaceChange} summary={summary} />
      
      <div className="main-view">
        <CommandBar 
          activeWorkspace={activeWorkspace} 
          serviceState={serviceState} 
          serviceStatusLabel={serviceStatusLabel(serviceState)}
          onRefresh={() => { loadJobs(); refreshAppState(); }}
          onCreateJob={() => handleWorkspaceChange("create")}
          onAction={handleCommandAction}
          title={workspaceTitle || ""}
        />

        <main className="workspace-content">
          {infoMessage && <MessageBanner kind="info" message={infoMessage} />}
          {errorMessage && <MessageBanner kind="error" message={errorMessage} />}

          {activeWorkspace === "queue" && (
            <QueueWorkspace 
              jobs={jobs} 
              modelCatalog={modelCatalog} 
              selectedJobId={selectedJobId} 
              onSelectJob={setSelectedJobId} 
              onInspectJob={handleInspectJob}
              onDispatchJob={(id) => void postJobAction(`/api/jobs/${id}/dispatch`, "dispatch")}
              onCancelJob={(id) => void postJobAction(`/api/jobs/${id}/cancel`, "cancel")}
              onBatchDispatch={(ids) => void postBatchJobAction("dispatch", ids)}
              onBatchCancel={(ids) => void postBatchJobAction("cancel", ids)}
              onBatchDelete={handleBatchDelete}
              batchActionBusy={batchActionKey}
            />
          )}

          {activeWorkspace === "create" && (
            <div className="create-workspace">
              {/* Step 1: Mode & Model Selection */}
              <div className="create-section">
                <div className="create-section-header">
                  <span className="create-step-num">1</span>
                  <span className="create-section-title">选择模式</span>
                </div>
                <div className="create-mode-toggle">
                  <button
                    type="button"
                    className={`mode-toggle-btn ${createMode === "single" ? "active" : ""}`}
                    onClick={() => setCreateMode("single")}
                  >
                    单任务创建
                  </button>
                  <button
                    type="button"
                    className={`mode-toggle-btn ${createMode === "batch" ? "active" : ""}`}
                    onClick={() => setCreateMode("batch")}
                  >
                    多模型对比
                  </button>
                </div>
              </div>

              <div className="create-main-grid">
                {/* Left: Model Config */}
                <div className="create-left-panel">
                  <div className="create-section">
                    <div className="create-section-header">
                      <span className="create-step-num">2</span>
                      <span className="create-section-title">{createMode === "single" ? "选择模型" : "选择对比模型"}</span>
                    </div>
                    {createMode === "single" ? (
                      <div className="model-selector-grid">
                        {runnableModelCatalog.map((m) => (
                          <div
                            key={m.value}
                            className={`model-selector-card ${formState.model === m.value ? "selected" : ""}`}
                            onClick={() => updateModel(m.value)}
                          >
                            <div className="model-selector-header">
                              <strong>{m.label}</strong>
                              {formState.model === m.value && <span className="model-selected-badge">已选</span>}
                            </div>
                            <p className="model-selector-desc">{m.description}</p>
                            <div className="model-selector-meta">
                              <span>{m.source_types?.join(" / ") || "images"}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="batch-model-grid">
                        {batchCompatibleModels.map((m) => {
                          const hint = batchModelHints[m.value];
                          const selected = selectedModels.includes(m.value);
                          return (
                            <div
                              key={m.value}
                              className={`model-selector-card compact ${selected ? "selected" : ""} ${hint ? "blocked" : ""}`}
                              onClick={() => !hint && toggleBatchModel(m.value)}
                            >
                              <div className="model-selector-header">
                                <input
                                  type="checkbox"
                                  checked={selected}
                                  onChange={() => toggleBatchModel(m.value)}
                                  disabled={!!hint && !selected}
                                  onClick={(e) => e.stopPropagation()}
                                />
                                <strong>{m.label}</strong>
                              </div>
                              {hint && <small className="model-blocker-hint">{hint}</small>}
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>

                  {createMode === "single" && (
                    <div className="create-section">
                      <div className="create-section-header">
                        <span className="create-step-num">3</span>
                        <span className="create-section-title">参数配置</span>
                      </div>
                      <div className="create-config-form">
                        <label className="field compact">
                          <span>输入类型</span>
                          <select value={formState.source_type} onChange={(e) => updateFormField("source_type", e.target.value)}>
                            {appState?.sourceTypes.filter(st => selectedModelSourceTypes.includes(st.value)).map((st) => (
                              <option key={st.value} value={st.value}>{st.label}</option>
                            ))}
                          </select>
                        </label>
                        {selectedModelContract && selectedModelContract.paramSchema.fields.length > 0 && (
                          <DynamicParamForm fields={selectedModelContract.paramSchema.fields} values={formState.params} onChange={updateFormField} />
                        )}
                      </div>
                    </div>
                  )}

                  {createMode === "batch" && (
                    <div className="create-section">
                      <div className="create-section-header">
                        <span className="create-step-num">3</span>
                        <span className="create-section-title">输入配置</span>
                      </div>
                      <label className="field compact">
                        <span>输入类型</span>
                        <select value={formState.source_type} onChange={(e) => updateFormField("source_type", e.target.value)}>
                          {appState?.sourceTypes.map((st) => (
                            <option key={st.value} value={st.value}>{st.label}</option>
                          ))}
                        </select>
                      </label>
                    </div>
                  )}
                </div>

                {/* Right: File Upload & Submit */}
                <div className="create-right-panel">
                  <div className="create-section">
                    <div className="create-section-header">
                      <span className="create-step-num">{createMode === "single" ? "4" : "4"}</span>
                      <span className="create-section-title">上传文件</span>
                      {files.length > 0 && <span className="create-file-count">{files.length} 个文件</span>}
                    </div>
                    <label className="dropzone-pro">
                      <input type="file" multiple onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
                      <div className="dropzone-content">
                        <div className="dropzone-icon">📁</div>
                        <strong>点击选择文件或拖拽到此处</strong>
                        <span>支持图片、视频等格式</span>
                      </div>
                    </label>
                    {files.length > 0 && (
                      <div className="file-list">
                        {files.slice(0, 6).map((file) => (
                          <div className="file-item" key={`${file.name}-${file.size}`}>
                            <span className="file-name">{file.name}</span>
                            <span className="file-size">{formatFileSize(file.size)}</span>
                            <button className="file-remove" type="button" onClick={() => setFiles(files.filter(f => f !== file))}>×</button>
                          </div>
                        ))}
                        {files.length > 6 && <div className="file-item more">+{files.length - 6} 个文件</div>}
                      </div>
                    )}
                  </div>

                  <div className="create-section">
                    <label className="field compact">
                      <span>备注（可选）</span>
                      <input 
                        type="text" 
                        value={formState.notes} 
                        onChange={(e) => updateFormField("notes", e.target.value)} 
                        placeholder="实验目的或说明..."
                      />
                    </label>
                  </div>

                  <div className="create-submit-section">
                    {uploadProgress !== null && (
                      <div className="upload-progress-bar">
                        <div className="upload-progress-fill" style={{ width: `${uploadProgress}%` }} />
                        <span className="upload-progress-text">上传中 {uploadProgress}%</span>
                      </div>
                    )}
                    {createMode === "single" ? (
                      <button
                        className="create-submit-btn primary"
                        type="button"
                        onClick={() => handleCreateJob()}
                        disabled={submitting || !!selectedModelLaunchBlocker || files.length === 0}
                      >
                        {submitting ? (uploadProgress !== null ? `上传 ${uploadProgress}%` : "创建中...") : "创建任务"}
                      </button>
                    ) : (
                      <div className="create-submit-group">
                        <button
                          className="create-submit-btn"
                          type="button"
                          onClick={() => handleBatchCompare(false)}
                          disabled={batchSubmitting || selectedModels.length < 1 || files.length === 0 || batchHasBlockers}
                        >
                          {batchSubmitting ? "创建中..." : "仅创建"}
                        </button>
                        <button
                          className="create-submit-btn primary"
                          type="button"
                          onClick={() => handleBatchCompare(true)}
                          disabled={batchSubmitting || selectedModels.length < 1 || files.length === 0 || batchHasBlockers}
                        >
                          {batchSubmitting ? "创建中..." : "创建并派发"}
                        </button>
                      </div>
                    )}
                    {selectedModelLaunchBlocker && (
                      <p className="create-blocker-msg">{selectedModelLaunchBlocker}</p>
                    )}
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeWorkspace === "inspect" && selectedInspection && (
            <InspectWorkspace
              inspection={selectedInspection}
              advisorState={advisorState}
              savingEvaluation={savingEvaluation}
              onSaveEvaluation={async (id, p) => { 
                setSavingEvaluation(true); 
                try { 
                  await fetchJson(`/api/jobs/${id}/evaluation`, { method: "POST", body: JSON.stringify(p) }); 
                  loadInspection(id); 
                } finally { 
                  setSavingEvaluation(false); 
                } 
              }}
              onConfigureAdvisor={openAdvisorSettings}
              onAction={postJobAction}
              onPreviewAsset={setPreviewAsset}
              onOpenOutput={async (p) => { 
                const f = new FormData(); 
                f.append("relative_path", p); 
                await fetchJson(`/api/jobs/${selectedInspection.job.job_id}/open-output`, { method: "POST", body: f }); 
              }}
              assetUrl={(p) => `${API_BASE}${p.startsWith("/") ? "" : "/"}${p}`}
              modelCatalog={modelCatalog}
            />
          )}

          {activeWorkspace === "samples" && (
            <SampleMatrixPanel
              samplesPayload={samplesPayload}
              errorMessage={samplesError}
              modelCatalog={modelCatalog}
              onLocateJob={handleInspectJob}
              onCopy={async (v, l) => { await navigator.clipboard.writeText(v); setInfoMessage(`${l}已复制`); }}
            />
          )}

          {activeWorkspace === "compare" && (
            <CompareBoard
              sampleId={compareSampleId}
              packet={comparePacket}
              loading={compareLoading}
              error={compareError}
              modelCatalog={modelCatalog}
              apiBase={API_BASE}
              onInspectJob={handleInspectJob}
              onRefresh={() => compareSampleId && loadComparePacket(compareSampleId)}
              onPreviewAsset={(asset) => setPreviewAsset(asset as PreviewAsset)}
            />
          )}

          {activeWorkspace === "development" && (
            <section className="overview-development-grid">
              <DevelopmentCyclePanel items={developmentLanes} />
              <ResearchAccelerationPanel items={developmentLanes} />
            </section>
          )}

          {activeWorkspace === "agent" && (
            <AgentWorkbench />
          )}

          {activeWorkspace === "system" && (
            <SystemWorkbench
              backendStatus={backendStatus}
              serviceState={serviceState}
              serviceMessage={serviceMessage}
              advisorState={advisorState}
              advisorReady={advisorReady}
              deploymentStatus={deploymentStatus}
              modelCatalog={modelCatalog}
              openAdvisorSettings={openAdvisorSettings}
              loadDeploymentStatus={loadDeploymentStatus}
              selectedJobId={selectedJobId}
              onRecommendParams={handleRecommendParams}
              onDiagnoseFailure={handleDiagnoseFailure}
            />
          )}

          {activeWorkspace === "storage" && (
            <StoragePanel />
          )}

          {activeWorkspace === "dashboard" && (
            <DashboardPanel />
          )}
        </main>
      </div>

      {advisorModalOpen && (
        <div className="settings-modal-backdrop" onClick={() => setAdvisorModalOpen(false)}>
          <div className="settings-modal" onClick={e => e.stopPropagation()}>
            <div className="preview-modal-head">
              <strong>Advisor 配置</strong>
              <button className="ghost-button small" onClick={() => setAdvisorModalOpen(false)}>关闭</button>
            </div>
            <form className="form-stack settings-form" onSubmit={saveAdvisorSettings}>
              <label className="field"><span>启用</span><input type="checkbox" checked={advisorForm.enabled} onChange={e => setAdvisorForm({ enabled: e.target.checked })} /></label>
              <label className="field"><span>Provider</span><select value={advisorForm.model} onChange={e => setAdvisorForm({ model: e.target.value })}>{advisorProviders.map(p => <optgroup key={p.id} label={p.label}>{p.models.map(m => <option key={m} value={m}>{m}</option>)}</optgroup>)}</select></label>
              <label className="field"><span>Base URL</span><input value={advisorForm.baseUrl} onChange={e => setAdvisorForm({ baseUrl: e.target.value })} /></label>
              <label className="field"><span>API Key</span><input type="password" value={advisorForm.apiKey} onChange={e => setAdvisorForm({ apiKey: e.target.value })} placeholder={advisorForm.hasApiKey ? "已保存" : "输入 Key"} /></label>
              <div className="settings-modal-actions"><button className="primary-button" type="submit">保存</button></div>
            </form>
          </div>
        </div>
      )}

      {recommendModalOpen && recommendResult && (
        <div className="settings-modal-backdrop" onClick={() => setRecommendModalOpen(false)}>
          <div className="settings-modal" onClick={e => e.stopPropagation()}>
            <div className="preview-modal-head">
              <strong>参数推荐</strong>
              <button className="ghost-button small" onClick={() => setRecommendModalOpen(false)}>关闭</button>
            </div>
            <div style={{ padding: "16px" }}>
              <p className="dense-text">{recommendResult.message}</p>
              {recommendResult.has_recommendations && recommendResult.recommended_params && (
                <div style={{ marginTop: "12px" }}>
                  <strong>推荐参数：</strong>
                  <pre style={{ background: "var(--surface-soft, #fafafa)", padding: "12px", borderRadius: "6px", marginTop: "8px", fontSize: "12px" }}>
                    {JSON.stringify(recommendResult.recommended_params, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {diagnoseModalOpen && diagnoseResult && (
        <div className="settings-modal-backdrop" onClick={() => setDiagnoseModalOpen(false)}>
          <div className="settings-modal" onClick={e => e.stopPropagation()}>
            <div className="preview-modal-head">
              <strong>故障诊断</strong>
              <button className="ghost-button small" onClick={() => setDiagnoseModalOpen(false)}>关闭</button>
            </div>
            <div style={{ padding: "16px" }}>
              <div style={{ marginBottom: "12px" }}>
                <strong>诊断结果：</strong>
                <ul style={{ marginTop: "8px", paddingLeft: "20px" }}>
                  {diagnoseResult.diagnosis.map((d: string, i: number) => <li key={i}>{d}</li>)}
                </ul>
              </div>
              <div>
                <strong>建议：</strong>
                <ul style={{ marginTop: "8px", paddingLeft: "20px" }}>
                  {diagnoseResult.suggestions.map((s: string, i: number) => <li key={i}>{s}</li>)}
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}

      {previewAsset && (
        previewAsset.kind === "pointcloud" ? (
          <div className="pointcloud-modal" onClick={() => setPreviewAsset(null)}>
            <div className="pointcloud-modal-content" onClick={e => e.stopPropagation()}>
              <div className="pointcloud-modal-header">
                <span className="pointcloud-modal-title">{previewAsset.name}</span>
                <button className="pointcloud-modal-close" onClick={() => setPreviewAsset(null)}>×</button>
              </div>
              <div className="pointcloud-modal-body">
                <PointCloudViewer
                  url={previewAsset.url}
                  height="100%"
                  onError={(e) => console.error("PointCloud load error:", e)}
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="preview-modal-backdrop" onClick={() => setPreviewAsset(null)}>
            <div className="preview-modal" onClick={e => e.stopPropagation()}>
              <div className="preview-modal-head">
                <strong>{previewAsset.name}</strong>
                <button className="ghost-button small" onClick={() => setPreviewAsset(null)}>关闭</button>
              </div>
              <div className="preview-modal-body">
                {previewAsset.kind === "image" ? <img src={previewAsset.url} alt={previewAsset.name} /> : <video src={previewAsset.url} controls autoPlay />}
              </div>
            </div>
          </div>
        )
      )}
    </div>
  );
}

function SystemWorkbench(props: any) {
  const deploymentRows = buildDeploymentComponentRows(props.deploymentStatus, props.modelCatalog);
  return (
    <div className="system-workspace">
      <div className="system-top-row">
        <div className="section-card">
          <div className="section-card-header">
            <h3 className="section-card-title">本地服务</h3>
            <span className={`section-card-badge ${props.backendStatus === "ready" ? "success" : ""}`}>
              {props.backendStatus === "ready" ? "运行中" : "检查中"}
            </span>
          </div>
          <div className="kv-row">
            <span className="kv-label">服务状态</span>
            <span className={`kv-value ${props.backendStatus === "ready" ? "success" : ""}`}>{props.serviceMessage}</span>
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
          <div style={{ marginTop: "12px" }}>
            <button className="ghost-button small" onClick={props.openAdvisorSettings}>打开配置</button>
          </div>
        </div>
      </div>

      <div className="section-card">
        <div className="section-card-header">
          <h3 className="section-card-title">模型部署状态</h3>
          <button className="ghost-button small" onClick={() => props.loadDeploymentStatus(true, true)}>刷新</button>
        </div>
        <div className="deployment-table">
          <div className="deployment-table-head">
            <span>模型</span><span>目录</span><span>环境</span><span>文件</span><span>权重</span>
          </div>
          {deploymentRows.map((row: any) => (
            <div className={`deployment-table-row ${row.tone}`} key={row.component}>
              <span className="deployment-model-name">{modelDisplayName(row.component, props.modelCatalog)}</span>
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

export default App;
