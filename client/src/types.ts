export type JobRecord = {
  job_id: string;
  created_at: string;
  model: string;
  source_type: string;
  notes: string;
  sample_id?: string | null;
  params: Record<string, unknown>;
  status: string;
  phase: string;
  input_files: string[];
  input_items: Array<{
    original_name: string;
    stored_name: string;
    relative_path: string;
    size_bytes: number | null;
  }>;
  output_files: string[];
  remote_job_dir?: string | null;
  remote_runner?: string | null;
  error_message?: string | null;
  progress_message?: string | null;
};

export type PhaseDisplay = {
  label: string;
  description: string;
  percent: number;
  stageProgress?: {
    percent?: number | null;
    ratio?: number | null;
    count?: {
      done: number;
      total: number;
    } | null;
  } | null;
  stage_progress?: {
    percent?: number | null;
    ratio?: number | null;
    count?: {
      done: number;
      total: number;
    } | null;
  } | null;
  steps: Array<{
    code: string;
    label: string;
    hint: string;
    state: "todo" | "current" | "done";
  }>;
};

export type ParamFieldSchema = {
  key: string;
  label: string;
  type: "string" | "number" | "boolean" | "select";
  default: any;
  choices?: Array<{ value: string; label: string }>;
  description?: string;
  optional?: boolean;
};

export type ModelContract = {
  model: string;
  paramSchema: {
    fields: ParamFieldSchema[];
    presets?: Record<string, Record<string, any>>;
  };
  runner: string;
  resultContract: ResultContract;
  allowedSourceTypes: string[];
  launchBlocker: string | null;
};

export type ResultArtifact = {
  role: string;
  label: string;
  name: string;
  relativePath: string;
  kind: "image" | "video" | "pointcloud" | "model3d" | "log" | "data";
  note?: string;
};

export type ResultContract = {
  primaryRole?: string;
  groups: Array<{
    key: string;
    label: string;
    description?: string;
  }>;
  artifacts: ResultArtifact[];
};

export type ResultSummary = {
  job_id: string;
  model: string;
  status: string;
  status_label: string;
  source_type: string;
  created_at: string;
  generated_at: string;
  duration_seconds?: number | null;
  inputs?: {
    count?: number;
    names?: string[];
  } | null;
  artifacts?: Array<{
    name: string;
    relative_path: string;
  }> | null;
  artifact_groups?: Array<{
    key: string;
    label: string;
    count: number;
    description?: string;
  }> | null;
  primary_artifacts?: Array<{
    role: string;
    label?: string;
    name: string;
    relative_path: string;
    note?: string;
  }> | null;
  params?: Record<string, unknown> | null;
  scene_meta?: Record<string, unknown> | null;
  highlights?: string[] | null;
  next_actions?: string[] | null;
};

export type AdvisorReport = {
  evaluated_at: string;
  job_id: string;
  overall_score: number;
  readiness: string;
  summary: string;
  issues: string[];
  next_actions: string[];
  teacher_talk: string;
  advisor_model: string;
};

export type AdvisorStatus = {
  enabled: boolean;
  configured: boolean;
  base_url: string;
  model: string;
  has_api_key?: boolean;
  message: string;
};

export type AdvisorConfig = {
  enabled: boolean;
  provider?: string;
  baseUrl: string;
  apiKey: string;
  model: string;
  temperature?: number;
  maxTokens: number;
  systemPrompt: string;
  structuredOutput: "auto" | "json_schema" | "json_object" | "prompt_only";
  timeoutSeconds: number;
  hasApiKey?: boolean; // compatibility/info
};

export type AdvisorProvider = {
  id?: string;
  value?: string;
  label: string;
  description?: string;
  notes?: string;
  baseUrl?: string;
  base_url?: string;
  models?: string[];
  structuredOutput?: "auto" | "json_schema" | "json_object" | "prompt_only";
  structured_output?: "auto" | "json_schema" | "json_object" | "prompt_only";
  supportsStructuredOutput?: boolean;
};

export type AdvisorDiagnostics = {
  state: "ready" | "unconfigured" | "error";
  checks: Array<{
    name: string;
    passed: boolean;
    message: string;
    detail?: string;
  }>;
  latencyMs?: number;
};

export type JobPayload = {
  job: JobRecord;
  phase_display: PhaseDisplay;
  outputs: Array<{
    relative_path: string;
    display_name: string;
    url: string;
    is_image: boolean;
    is_pointcloud: boolean;
    is_model3d: boolean;
    is_video: boolean;
    is_log: boolean;
  }>;
  previews: Array<{
    relative_path: string;
    display_name: string;
    stored_name: string;
    url: string;
    is_image: boolean;
  }>;
  logs: Array<{
    name: string;
    relative_path: string;
    tail: string;
  }>;
  result_summary: ResultSummary | null;
  evaluation?: EvaluationPayload | null;
  advisor_report?: AdvisorReport | null;
  contract?: ResultContract; // New
};

export type EvaluationPayload = {
  job_id: string;
  rubric_version?: number;
  score_min?: number;
  score_max?: number;
  updated_at?: string | null;
  structure_completeness?: number | null;
  trajectory_stability?: number | null;
  noise?: number | null;
  dynamic_handling?: number | null;
  depth_continuity?: number | null;
  presentation_usability?: number | null;
  noise_control?: number | null;
  depth_consistency?: number | null;
  notes?: string;
};

export type ModelCatalogItem = {
  value: string;
  label: string;
  description: string;
  family: string;
  param_family: string;
  source_types: string[];
  runner_status: string;
  research_priority: number;
  active_track: boolean;
  runnable: boolean;
  launch_blocker?: string | null;
};

export type BootstrapPayload = {
  summary: {
    total: number;
    running: number;
    finished: number;
    failed: number;
    cancelled: number;
  };
  delivery_gaps: Array<{
    title: string;
    detail: string;
  }>;
  server: {
    alias: string;
    host: string;
    user: string;
    port: number;
    remote_root: string;
  };
  models: any[]; // legacy
  model_catalog?: ModelCatalogItem[];
  source_types: Array<{
    value: string;
    label: string;
  }>;
  advisor?: AdvisorStatus;
};

export type AppState = {
  modelCatalog: ModelCatalogItem[];
  modelContracts: Record<string, ModelContract>;
  sourceTypes: Array<{ value: string; label: string }>;
  developmentLanes: DevelopmentLaneItem[];
  deliveryGaps: Array<{ title: string; detail: string }>;
  advisor: AdvisorStatus;
  summary: BootstrapPayload["summary"];
};

export type SampleManifestItem = {
  id: string;
  source_type: string;
  status: string;
  purpose: string;
  required_models?: string[];
  optional_models?: string[];
  target_file_count?: string;
  target_duration_seconds?: string;
  seed_job_id?: string;
  manual_criteria?: string[];
};

export type SamplesPayload = {
  manifest: {
    last_updated?: string | null;
    purpose?: string;
    active_models?: string[];
    deferred_models?: string[];
    samples?: SampleManifestItem[];
    scoring?: Record<string, string[]>;
  };
  summary: {
    sample_count: number;
    status_counts: Record<string, number>;
    source_counts: Record<string, number>;
    required_model_counts: Record<string, number>;
  };
  model_catalog: ModelCatalogItem[];
  job_matrix?: {
    rows: Array<{
      sample_id: string;
      jobs_by_model: Record<
        string,
        {
          job_id: string;
          model: string;
          status: string;
          status_label: string;
          phase: string;
          progress_message?: string | null;
          created_at: string;
          sample_id?: string | null;
          score_snapshot?: Record<string, number>;
          primary_artifacts?: Array<{
            role: string;
            label?: string;
            name: string;
            relative_path: string;
            note?: string;
          }>;
        }
      >;
    }>;
    unassigned_jobs: Array<{
      job_id: string;
      model: string;
      status: string;
      status_label: string;
      phase: string;
      progress_message?: string | null;
      created_at: string;
      sample_id?: string | null;
      score_snapshot?: Record<string, number>;
      primary_artifacts?: Array<{
        role: string;
        label?: string;
        name: string;
        relative_path: string;
        note?: string;
      }>;
    }>;
  };
};

export type DeploymentStatusPayload = {
  host?: string | null;
  root: string;
  fetched_at?: string;
  source?: string;
  stale?: boolean;
  cache?: {
    state?: string;
    hit?: boolean;
    age_seconds?: number;
    ttl_seconds?: number;
    stale_ttl_seconds?: number;
    timeout_seconds?: number;
    expires_at?: string;
    script_path?: string;
    ssh_alias?: string;
    last_error?: string;
  };
  directories: Array<{
    name: string;
    path: string;
    state: string;
    exists: boolean;
    readme_setup: boolean;
    size_bytes?: number | null;
  }>;
  conda_envs: Array<{
    component: string;
    env: string;
    exists: boolean;
    path?: string | null;
  }>;
  known_files: Array<{
    component: string;
    kind: string;
    need: string;
    relative_path: string;
    path: string;
    exists: boolean;
    size_bytes?: number | null;
  }>;
  checkpoints?: Array<{
    component: string;
    relative_path: string;
    size_bytes?: number | null;
  }>;
  summary: {
    missing_directories: number;
    missing_conda_envs: number;
    missing_required_files: number;
    warnings: number;
    ok: boolean;
  };
};

export type PageInfo = {
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
};

export type JobsListPayload = {
  jobs: Array<{
    job: JobRecord;
    phase_display: PhaseDisplay;
  }>;
  summary: BootstrapPayload["summary"];
  page_info?: PageInfo;
};

export type BatchJobsResponse = {
  ok: boolean;
  results: Array<{
    job_id: string;
    success: boolean;
    status_code?: number;
    error?: string;
    job?: JobPayload;
    list_item?: JobsListPayload["jobs"][number];
  }>;
};

export type StatsOverviewPayload = {
  total: number;
  total_jobs: number;
  by_status: Record<string, number>;
  by_model: Record<string, {
    count: number;
    finished: number;
    failed: number;
    cancelled: number;
    success_rate: number;
    avg_duration_sec: number | null;
  }>;
  recent_24h: {
    created: number;
    finished: number;
  };
};

export type DevelopmentLaneItem = {
  id: string;
  title: string;
  category: "paper_reproduction" | "model_runner" | "prototype" | "evaluation" | "ui_workflow";
  status: "draft" | "scoped" | "reproducing" | "prototype" | "smoke_ready" | "validated" | "merged" | "deferred";
  priority: "P0" | "P1" | "P2" | "P3";
  targetModel?: string;
  nextAction: string;
  blockers: string[];
  mergeTarget?: "runner" | "sample_matrix" | "advisor" | "report" | "deferred_research";
  createdAt?: string;
  updatedAt?: string;
  metadata?: Record<string, unknown>;
};

export type BackendStatusPayload = {
  running: boolean;
  managed_by_tauri: boolean;
  message: string;
  backend_root: string | null;
  log_path: string | null;
};

export type InspectionPacket = {
  job: JobRecord;
  phaseDisplay: PhaseDisplay;
  result_summary?: ResultSummary | null;
  contract?: ModelContract | null;
  inspection: {
    attention: Array<{
      kind?: "warning" | "error" | "missing_output";
      level?: string;
      label?: string;
      title?: string;
      detail: string;
    }>;
    recommendedActions: Array<string | {
      key: string;
      label: string;
      target: string;
      primary: boolean;
    }>;
    viserSupported?: boolean;
  };
  artifactIndex: {
    groups: Array<{
      key: string;
      label: string;
      description?: string;
      artifacts: ResultArtifact[];
    }>;
    primaryArtifacts: ResultArtifact[];
  };
  logs: Array<{
    name: string;
    relative_path: string;
    tail: string;
  }>;
  evaluation?: EvaluationPayload | null;
  advisorReport?: AdvisorReport | null;
};

export type ValidationCreateResponse = {
  ok: boolean;
  errors: string[];
};

// ──────────────────────────────────────────────────────────────
// Batch Compare Types
// ──────────────────────────────────────────────────────────────

export type CompareSummary = {
  jobCount: number;
  job_count: number;
  finished: number;
  running: number;
  attention: number;
  visualCount: number;
  visual_count: number;
  averageScore: number | null;
  average_score: number | null;
  statusCounts: Record<string, number>;
  status_counts: Record<string, number>;
};

export type CompareVisual = {
  role: string;
  label: string;
  kind: string;
  name: string;
  relativePath: string;
  relative_path: string;
  url: string;
  primary: boolean;
};

export type CompareModelCell = {
  model: string;
  jobId: string;
  job_id: string;
  status: string;
  statusLabel: string;
  status_label: string;
  phase: string;
  progressMessage: string | null;
  progress_message: string | null;
  createdAt: string;
  created_at: string;
  scoreSnapshot: Record<string, number>;
  score_snapshot: Record<string, number>;
  primaryArtifacts: Array<{
    role: string;
    label?: string;
    name: string;
    relative_path: string;
    relativePath?: string;
    note?: string;
    kind?: string;
  }>;
  primary_artifacts: Array<{
    role: string;
    label?: string;
    name: string;
    relative_path: string;
    note?: string;
  }>;
  visuals: CompareVisual[];
  outputs: Array<{
    relative_path: string;
    display_name: string;
    url: string;
    role: string;
    label: string;
    kind: string;
    is_image: boolean;
    is_pointcloud: boolean;
    is_model3d: boolean;
    is_video: boolean;
    is_log: boolean;
  }>;
  previews: Array<{
    relative_path: string;
    display_name: string;
    stored_name: string;
    url: string;
    is_image: boolean;
  }>;
};

export type ComparePacket = {
  sampleId: string;
  sample_id: string;
  summary: CompareSummary;
  modelCells: CompareModelCell[];
  model_cells: CompareModelCell[];
  reportMarkdown: string;
  report_markdown: string;
};

export type BatchCompareResponse = {
  ok: boolean;
  sampleId: string;
  sample_id: string;
  models: string[];
  createdJobs: JobPayload[];
  created_jobs: JobPayload[];
  dispatchResults: Array<{
    job_id: string;
    model: string;
    dispatched: boolean;
  }>;
  dispatch_results: Array<{
    job_id: string;
    model: string;
    dispatched: boolean;
  }>;
  compare: ComparePacket;
};

// ══════════════════════════════════════════════════════════════════
// P1/P2: Scheduler, Resources, Metrics
// ══════════════════════════════════════════════════════════════════

export type SchedulerStatus = {
  running: boolean;
  max_concurrent: number;
  queue_length: number;
  running_count: number;
  queued_jobs: Array<{
    job_id: string;
    priority: "high" | "normal" | "low";
    retry_count: number;
    score: number;
  }>;
  running_jobs: Array<{
    job_id: string;
    priority: "high" | "normal" | "low";
    started_at: number | null;
  }>;
};

export type SystemResources = {
  cpu_percent: number;
  memory: {
    used_mb: number;
    total_mb: number;
    free_mb: number;
    used_percent: number;
  };
  disk: {
    used_gb: number;
    total_gb: number;
    free_gb: number;
    used_percent: number;
  };
  gpus: Array<{
    index: number;
    name: string;
    memory_used_mb: number;
    memory_total_mb: number;
    memory_free_mb: number;
    memory_used_percent: number;
    utilization_percent: number;
    temperature_c: number | null;
  }>;
  gpu_count: number;
  timestamp: number;
};

export type JobMetrics = {
  job_id: string;
  metrics: {
    depth?: {
      file: string;
      shape: number[];
      min: number;
      max: number;
      metrics: {
        rmse: number;
        abs_rel: number;
        sq_rel: number;
        delta_1: number;
        delta_2: number;
        delta_3: number;
        valid_ratio: number;
      };
    };
    pointcloud?: {
      file: string;
      metrics: {
        point_count: number;
        density: number;
        coverage_ratio: number;
        bbox: { min: number[]; max: number[] };
        centroid: number[];
      };
    };
    trajectory?: {
      file: string;
      metrics: {
        file: string;
        metrics: {
          path_length: number;
          average_speed: number;
          smoothness: number;
          drift: number;
        };
      };
    };
  };
};

// ──────────────────────────────────────────────────────────────
// Storage Management Types
// ──────────────────────────────────────────────────────────────

export type StorageStats = {
  totalBytes: number;
  usedBytes: number;
  freeBytes: number;
  usagePercent: number;
  jobCount: number;
  byModel: Record<string, number>;
  byStatus: Record<string, number>;
  largestJobs: Array<{ jobId: string; bytes: number }>;
};

export type CleanupCondition = {
  type: "age_days" | "score_below" | "manual";
  value: number;
  statusFilter: string[];
};

export type CleanupRule = {
  name: string;
  enabled: boolean;
  priority: number;
  condition: CleanupCondition | null;
  action: "delete" | "archive";
};

export type AutoCleanConfig = {
  enabled: boolean;
  checkIntervalHours: number;
  thresholdPercent: number;
};

export type StorageConfig = {
  quotaBytes: number;
  rules: CleanupRule[];
  protectedSampleIds: string[];
  autoClean: AutoCleanConfig;
};

export type CleanupCandidate = {
  jobId: string;
  reason: string;
  sizeBytes: number;
  ruleName: string;
};

export type CleanupResult = {
  deletedCount: number;
  freedBytes: number;
  candidates: CleanupCandidate[];
  errors: string[];
  dryRun: boolean;
};
