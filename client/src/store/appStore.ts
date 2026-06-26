/**
 * appStore — 全局应用状态（Zustand）
 * 替代 App.tsx 中的大量 useState
 */
import { create } from "zustand";
import { devtools } from "zustand/middleware";
import type {
  AppState,
  BackendStatusPayload,
  DeploymentStatusPayload,
  DevelopmentLaneItem,
  InspectionPacket,
  SamplesPayload,
  AdvisorConfig,
  AdvisorProvider,
  AdvisorDiagnostics,
  ComparePacket,
  ValidationCreateResponse,
} from "../types";
import type { JobListItem, BatchJobAction } from "../workflowHelpers";
import type { PreviewAsset } from "../JobDetail";
import type { WorkspaceTab } from "../workspaceTypes";

export type ServiceState = "starting" | "ready" | "degraded";
export type CreateMode = "single" | "batch";

interface AppStore {
  // ─────────────── 服务状态 ───────────────
  serviceState: ServiceState;
  serviceMessage: string;
  backendStatus: BackendStatusPayload | null;
  appState: AppState | null;
  
  // ─────────────── 任务状态 ───────────────
  jobs: JobListItem[];
  selectedJobId: string | null;
  selectedInspection: InspectionPacket | null;
  
  // ─────────────── UI 状态 ───────────────
  activeWorkspace: WorkspaceTab;
  submitting: boolean;
  actionKey: string | null;
  batchActionKey: BatchJobAction | null;
  batchSubmitting: boolean;
  errorMessage: string | null;
  infoMessage: string | null;
  previewAsset: PreviewAsset | null;
  uploadProgress: number | null;
  savingEvaluation: boolean;
  
  // ─────────────── 表单状态 ───────────────
  formState: {
    model: string;
    source_type: string;
    notes: string;
    params: Record<string, any>;
  };
  files: File[];
  createMode: CreateMode;
  selectedModels: string[];
  batchAutoDispatch: boolean;
  
  // ─────────────── 数据面板 ───────────────
  samplesPayload: SamplesPayload | null;
  samplesError: string | null;
  developmentLanes: DevelopmentLaneItem[];
  deploymentStatus: DeploymentStatusPayload | null;
  deploymentError: string | null;
  
  // ─────────────── 对比面板 ───────────────
  compareSampleId: string | null;
  comparePacket: ComparePacket | null;
  compareLoading: boolean;
  compareError: string | null;
  
  // ─────────────── 顾问状态 ───────────────
  advisorModalOpen: boolean;
  advisorProviders: AdvisorProvider[];
  advisorDiagnostics: AdvisorDiagnostics | null;
  advisorForm: AdvisorConfig;
  advisorConfigLoading: boolean;
  advisorConfigSaving: boolean;
  validationResponse: ValidationCreateResponse | null;
  recommendModalOpen: boolean;
  recommendResult: any;
  diagnoseModalOpen: boolean;
  diagnoseResult: any;
  
  // ─────────────── Actions ───────────────
  setServiceState: (state: ServiceState) => void;
  setServiceMessage: (message: string) => void;
  setBackendStatus: (status: BackendStatusPayload | null) => void;
  setAppState: (state: AppState | null) => void;
  
  setJobs: (jobs: JobListItem[]) => void;
  updateJobInList: (job: JobListItem) => void;
  setSelectedJobId: (id: string | null) => void;
  setSelectedInspection: (inspection: InspectionPacket | null) => void;
  
  setActiveWorkspace: (tab: WorkspaceTab) => void;
  setSubmitting: (submitting: boolean) => void;
  setActionKey: (key: string | null) => void;
  setBatchActionKey: (key: BatchJobAction | null) => void;
  setBatchSubmitting: (submitting: boolean) => void;
  setErrorMessage: (message: string | null) => void;
  setInfoMessage: (message: string | null) => void;
  setPreviewAsset: (asset: PreviewAsset | null) => void;
  setUploadProgress: (progress: number | null) => void;
  setSavingEvaluation: (saving: boolean) => void;
  
  setFormState: (state: Partial<AppStore["formState"]>) => void;
  resetFormState: () => void;
  setFiles: (files: File[]) => void;
  addFiles: (files: File[]) => void;
  clearFiles: () => void;
  setCreateMode: (mode: CreateMode) => void;
  setSelectedModels: (models: string[]) => void;
  toggleModelSelection: (model: string) => void;
  setBatchAutoDispatch: (auto: boolean) => void;
  
  setSamplesPayload: (payload: SamplesPayload | null) => void;
  setSamplesError: (error: string | null) => void;
  setDevelopmentLanes: (lanes: DevelopmentLaneItem[]) => void;
  setDeploymentStatus: (status: DeploymentStatusPayload | null) => void;
  
  setCompareSampleId: (id: string | null) => void;
  setComparePacket: (packet: ComparePacket | null) => void;
  setCompareLoading: (loading: boolean) => void;
  setCompareError: (error: string | null) => void;
  
  setAdvisorModalOpen: (open: boolean) => void;
  setAdvisorProviders: (providers: AdvisorProvider[]) => void;
  setAdvisorDiagnostics: (diagnostics: AdvisorDiagnostics | null) => void;
  setAdvisorForm: (form: Partial<AdvisorConfig>) => void;
  setAdvisorConfigLoading: (loading: boolean) => void;
  setAdvisorConfigSaving: (saving: boolean) => void;
  setValidationResponse: (response: ValidationCreateResponse | null) => void;
  setRecommendModalOpen: (open: boolean) => void;
  setRecommendResult: (result: any) => void;
  setDiagnoseModalOpen: (open: boolean) => void;
  setDiagnoseResult: (result: any) => void;
}

const initialFormState = {
  model: "dust3r",
  source_type: "images",
  notes: "",
  params: {},
};

const initialAdvisorForm: AdvisorConfig = {
  enabled: false,
  provider: "custom_openai_compatible",
  baseUrl: "",
  apiKey: "",
  model: "gpt-4o-mini",
  temperature: 0.2,
  maxTokens: 1200,
  systemPrompt: "",
  structuredOutput: "auto",
  timeoutSeconds: 90,
};

export const useAppStore = create<AppStore>()(
  devtools(
    (set) => ({
      // ─────────────── 初始状态 ───────────────
      serviceState: "starting",
      serviceMessage: "正在准备本地服务...",
      backendStatus: null,
      appState: null,
      
      jobs: [],
      selectedJobId: null,
      selectedInspection: null,
      
      activeWorkspace: "queue",
      submitting: false,
      actionKey: null,
      batchActionKey: null,
      batchSubmitting: false,
      errorMessage: null,
      infoMessage: null,
      previewAsset: null,
      uploadProgress: null,
      savingEvaluation: false,
      
      formState: initialFormState,
      files: [],
      createMode: "single",
      selectedModels: [],
      batchAutoDispatch: false,
      
      samplesPayload: null,
      samplesError: null,
      developmentLanes: [],
      deploymentStatus: null,
      deploymentError: null,
      
      compareSampleId: null,
      comparePacket: null,
      compareLoading: false,
      compareError: null,
      
      advisorModalOpen: false,
      advisorProviders: [],
      advisorDiagnostics: null,
      advisorForm: initialAdvisorForm,
      advisorConfigLoading: false,
      advisorConfigSaving: false,
      validationResponse: null,
      recommendModalOpen: false,
      recommendResult: null,
      diagnoseModalOpen: false,
      diagnoseResult: null,
      
      // ─────────────── Actions ───────────────
      setServiceState: (state) => set({ serviceState: state }),
      setServiceMessage: (message) => set({ serviceMessage: message }),
      setBackendStatus: (status) => set({ backendStatus: status }),
      setAppState: (state) => set({ appState: state }),
      
      setJobs: (jobs) => set({ jobs }),
      updateJobInList: (job) => set((state) => {
        const index = state.jobs.findIndex((j) => j.job.job_id === job.job.job_id);
        if (index === -1) return { jobs: [job, ...state.jobs] };
        const updated = [...state.jobs];
        updated[index] = job;
        return { jobs: updated };
      }),
      setSelectedJobId: (id) => set({ selectedJobId: id }),
      setSelectedInspection: (inspection) => set({ selectedInspection: inspection }),
      
      setActiveWorkspace: (tab) => set({ activeWorkspace: tab }),
      setSubmitting: (submitting) => set({ submitting }),
      setActionKey: (key) => set({ actionKey: key }),
      setBatchActionKey: (key) => set({ batchActionKey: key }),
      setBatchSubmitting: (submitting) => set({ batchSubmitting: submitting }),
      setErrorMessage: (message) => set({ errorMessage: message }),
      setInfoMessage: (message) => set({ infoMessage: message }),
      setPreviewAsset: (asset) => set({ previewAsset: asset }),
      setUploadProgress: (progress) => set({ uploadProgress: progress }),
      setSavingEvaluation: (saving) => set({ savingEvaluation: saving }),
      
      setFormState: (partial) => set((state) => ({
        formState: { ...state.formState, ...partial },
      })),
      resetFormState: () => set({ formState: initialFormState }),
      setFiles: (files) => set({ files }),
      addFiles: (newFiles) => set((state) => ({
        files: [...state.files, ...newFiles],
      })),
      clearFiles: () => set({ files: [] }),
      setCreateMode: (mode) => set({ createMode: mode }),
      setSelectedModels: (models) => set({ selectedModels: models }),
      toggleModelSelection: (model) => set((state) => {
        const selected = state.selectedModels.includes(model)
          ? state.selectedModels.filter((m) => m !== model)
          : [...state.selectedModels, model];
        return { selectedModels: selected };
      }),
      setBatchAutoDispatch: (auto) => set({ batchAutoDispatch: auto }),
      
      setSamplesPayload: (payload) => set({ samplesPayload: payload }),
      setSamplesError: (error) => set({ samplesError: error }),
      setDevelopmentLanes: (lanes) => set({ developmentLanes: lanes }),
      setDeploymentStatus: (status) => set({ deploymentStatus: status }),
      
      setCompareSampleId: (id) => set({ compareSampleId: id }),
      setComparePacket: (packet) => set({ comparePacket: packet }),
      setCompareLoading: (loading) => set({ compareLoading: loading }),
      setCompareError: (error) => set({ compareError: error }),
      
      setAdvisorModalOpen: (open) => set({ advisorModalOpen: open }),
      setAdvisorProviders: (providers) => set({ advisorProviders: providers }),
      setAdvisorDiagnostics: (diagnostics) => set({ advisorDiagnostics: diagnostics }),
      setAdvisorForm: (partial) => set((state) => ({
        advisorForm: { ...state.advisorForm, ...partial },
      })),
      setAdvisorConfigLoading: (loading) => set({ advisorConfigLoading: loading }),
      setAdvisorConfigSaving: (saving) => set({ advisorConfigSaving: saving }),
      setValidationResponse: (response) => set({ validationResponse: response }),
      setRecommendModalOpen: (open) => set({ recommendModalOpen: open }),
      setRecommendResult: (result) => set({ recommendResult: result }),
      setDiagnoseModalOpen: (open) => set({ diagnoseModalOpen: open }),
      setDiagnoseResult: (result) => set({ diagnoseResult: result }),
    }),
    { name: "3R-AppStore" }
  )
);

// ─────────────── 派生状态 (Selectors) ───────────────

export const selectServiceReady = (state: AppStore) => state.serviceState === "ready";

export const selectModelCatalog = (state: AppStore) => state.appState?.modelCatalog ?? [];

export const selectModelContracts = (state: AppStore) => state.appState?.modelContracts ?? {};

export const selectAdvisorState = (state: AppStore) => state.appState?.advisor ?? {
  enabled: false,
  configured: false,
  base_url: "",
  model: "",
  has_api_key: false,
  message: "辅助评估尚未配置。",
};

export const selectAdvisorReady = (state: AppStore) => {
  const advisor = selectAdvisorState(state);
  return advisor.enabled && advisor.configured;
};

export const selectJobSummary = (state: AppStore) => ({
  total: state.jobs.length,
  running: state.jobs.filter((item) => item.job.status === "running").length,
  finished: state.jobs.filter((item) => item.job.status === "finished").length,
  failed: state.jobs.filter((item) => item.job.status === "failed").length,
  cancelled: state.jobs.filter((item) => item.job.status === "cancelled").length,
});
