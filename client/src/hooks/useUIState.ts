/**
 * useUIState — UI 状态 hooks（渐进式迁移）
 * 
 * 从这里导出的 hooks 可以逐步替换 App.tsx 中的 useState
 * 使用方式：
 *   // 旧: const [previewAsset, setPreviewAsset] = useState(null);
 *   // 新: const { previewAsset, setPreviewAsset } = usePreviewAsset();
 */

import { useAppStore } from "../store";
import type { PreviewAsset } from "../JobDetail";
import type { WorkspaceTab } from "../workspaceTypes";
import type { ServiceState } from "../store/appStore";

// ─────────────── Preview Asset ───────────────

export function usePreviewAsset() {
  const previewAsset = useAppStore((s) => s.previewAsset);
  const setPreviewAsset = useAppStore((s) => s.setPreviewAsset);
  
  return {
    previewAsset,
    setPreviewAsset,
    clearPreview: () => setPreviewAsset(null),
    showImage: (url: string, name: string) => 
      setPreviewAsset({ url, name, kind: "image" }),
    showVideo: (url: string, name: string) => 
      setPreviewAsset({ url, name, kind: "video" }),
    showPointCloud: (url: string, name: string) => 
      setPreviewAsset({ url, name, kind: "pointcloud" }),
  };
}

// ─────────────── Messages ───────────────

export function useMessages() {
  const errorMessage = useAppStore((s) => s.errorMessage);
  const infoMessage = useAppStore((s) => s.infoMessage);
  const setErrorMessage = useAppStore((s) => s.setErrorMessage);
  const setInfoMessage = useAppStore((s) => s.setInfoMessage);
  
  return {
    errorMessage,
    infoMessage,
    setErrorMessage,
    setInfoMessage,
    showError: (msg: string) => setErrorMessage(msg),
    showInfo: (msg: string) => setInfoMessage(msg),
    clearError: () => setErrorMessage(null),
    clearInfo: () => setInfoMessage(null),
    clearAll: () => {
      setErrorMessage(null);
      setInfoMessage(null);
    },
  };
}

// ─────────────── Workspace Navigation ───────────────

export function useWorkspace() {
  const activeWorkspace = useAppStore((s) => s.activeWorkspace);
  const setActiveWorkspace = useAppStore((s) => s.setActiveWorkspace);
  
  return {
    activeWorkspace,
    setActiveWorkspace,
    goToQueue: () => setActiveWorkspace("queue"),
    goToCreate: () => setActiveWorkspace("create"),
    goToInspect: () => setActiveWorkspace("inspect"),
    goToSamples: () => setActiveWorkspace("samples"),
    goToCompare: () => setActiveWorkspace("compare"),
    goToDevelopment: () => setActiveWorkspace("development"),
    goToSystem: () => setActiveWorkspace("system"),
  };
}

// ─────────────── Service State ───────────────

export function useServiceState() {
  const serviceState = useAppStore((s) => s.serviceState);
  const serviceMessage = useAppStore((s) => s.serviceMessage);
  const setServiceState = useAppStore((s) => s.setServiceState);
  const setServiceMessage = useAppStore((s) => s.setServiceMessage);
  
  return {
    serviceState,
    serviceMessage,
    setServiceState,
    setServiceMessage,
    isReady: serviceState === "ready",
    isStarting: serviceState === "starting",
    isDegraded: serviceState === "degraded",
  };
}

// ─────────────── Jobs ───────────────

export function useJobs() {
  const jobs = useAppStore((s) => s.jobs);
  const selectedJobId = useAppStore((s) => s.selectedJobId);
  const setJobs = useAppStore((s) => s.setJobs);
  const setSelectedJobId = useAppStore((s) => s.setSelectedJobId);
  const updateJobInList = useAppStore((s) => s.updateJobInList);
  
  const selectedJob = jobs.find((j) => j.job.job_id === selectedJobId) ?? null;
  
  return {
    jobs,
    selectedJobId,
    selectedJob,
    setJobs,
    setSelectedJobId,
    updateJobInList,
    jobCount: jobs.length,
    runningCount: jobs.filter((j) => j.job.status === "running").length,
    finishedCount: jobs.filter((j) => j.job.status === "finished").length,
    failedCount: jobs.filter((j) => j.job.status === "failed").length,
  };
}

// ─────────────── Create Form ───────────────

export function useCreateForm() {
  const formState = useAppStore((s) => s.formState);
  const files = useAppStore((s) => s.files);
  const createMode = useAppStore((s) => s.createMode);
  const selectedModels = useAppStore((s) => s.selectedModels);
  const batchAutoDispatch = useAppStore((s) => s.batchAutoDispatch);
  const submitting = useAppStore((s) => s.submitting);
  
  const setFormState = useAppStore((s) => s.setFormState);
  const resetFormState = useAppStore((s) => s.resetFormState);
  const setFiles = useAppStore((s) => s.setFiles);
  const addFiles = useAppStore((s) => s.addFiles);
  const clearFiles = useAppStore((s) => s.clearFiles);
  const setCreateMode = useAppStore((s) => s.setCreateMode);
  const setSelectedModels = useAppStore((s) => s.setSelectedModels);
  const toggleModelSelection = useAppStore((s) => s.toggleModelSelection);
  const setBatchAutoDispatch = useAppStore((s) => s.setBatchAutoDispatch);
  const setSubmitting = useAppStore((s) => s.setSubmitting);
  
  return {
    // State
    formState,
    files,
    createMode,
    selectedModels,
    batchAutoDispatch,
    submitting,
    
    // Actions
    setFormState,
    resetFormState,
    setFiles,
    addFiles,
    clearFiles,
    setCreateMode,
    setSelectedModels,
    toggleModelSelection,
    setBatchAutoDispatch,
    setSubmitting,
    
    // Helpers
    isBatchMode: createMode === "batch",
    hasFiles: files.length > 0,
    canSubmit: files.length > 0 && !submitting,
  };
}

// ─────────────── Advisor ───────────────

export function useAdvisor() {
  const advisorModalOpen = useAppStore((s) => s.advisorModalOpen);
  const advisorForm = useAppStore((s) => s.advisorForm);
  const validationResponse = useAppStore((s) => s.validationResponse);
  
  const setAdvisorModalOpen = useAppStore((s) => s.setAdvisorModalOpen);
  const setAdvisorForm = useAppStore((s) => s.setAdvisorForm);
  const setValidationResponse = useAppStore((s) => s.setValidationResponse);
  
  return {
    advisorModalOpen,
    advisorForm,
    validationResponse,
    setAdvisorModalOpen,
    setAdvisorForm,
    setValidationResponse,
    openModal: () => setAdvisorModalOpen(true),
    closeModal: () => setAdvisorModalOpen(false),
  };
}

// ─────────────── Compare ───────────────

export function useCompare() {
  const compareSampleId = useAppStore((s) => s.compareSampleId);
  const comparePacket = useAppStore((s) => s.comparePacket);
  const compareLoading = useAppStore((s) => s.compareLoading);
  const compareError = useAppStore((s) => s.compareError);
  
  const setCompareSampleId = useAppStore((s) => s.setCompareSampleId);
  const setComparePacket = useAppStore((s) => s.setComparePacket);
  const setCompareLoading = useAppStore((s) => s.setCompareLoading);
  const setCompareError = useAppStore((s) => s.setCompareError);
  
  return {
    compareSampleId,
    comparePacket,
    compareLoading,
    compareError,
    setCompareSampleId,
    setComparePacket,
    setCompareLoading,
    setCompareError,
    clearCompare: () => {
      setCompareSampleId(null);
      setComparePacket(null);
      setCompareError(null);
    },
  };
}
