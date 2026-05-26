/**
 * useJobs — 任务管理 Hook
 * 提取自 App.tsx，管理任务列表、选中状态、轮询
 */
import { useState, useCallback, useRef, useEffect } from "react";
import type { JobsListPayload, InspectionPacket } from "../types";
import type { JobListItem } from "../workflowHelpers";
import { API_BASE } from "../appConfig";
import { friendlyError } from "../displayHelpers";

export interface UseJobsOptions {
  onError?: (message: string) => void;
  onServiceStateChange?: (state: "starting" | "ready" | "degraded") => void;
}

export interface UseJobsReturn {
  jobs: JobListItem[];
  selectedJobId: string | null;
  selectedInspection: InspectionPacket | null;
  loading: boolean;
  setSelectedJobId: (id: string | null) => void;
  setSelectedInspection: (inspection: InspectionPacket | null) => void;
  loadJobs: (showError?: boolean) => Promise<void>;
  refreshJob: (jobId: string) => Promise<void>;
  updateJobInList: (jobItem: JobListItem) => void;
}

export function useJobs(options: UseJobsOptions = {}): UseJobsReturn {
  const { onError, onServiceStateChange } = options;
  
  const [jobs, setJobs] = useState<JobListItem[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedInspection, setSelectedInspection] = useState<InspectionPacket | null>(null);
  const [loading, setLoading] = useState(false);
  
  const selectedJobIdRef = useRef<string | null>(null);
  
  // 同步 ref
  useEffect(() => {
    selectedJobIdRef.current = selectedJobId;
  }, [selectedJobId]);

  const loadJobs = useCallback(async (showError = true) => {
    setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/api/jobs`);
      if (!response.ok) {
        throw new Error(`请求失败：${response.status}`);
      }
      const payload: JobsListPayload = await response.json();
      setJobs(payload.jobs);
      onServiceStateChange?.("ready");
    } catch (error) {
      if (showError) {
        onError?.(friendlyError(error, "加载任务列表失败。"));
      }
      onServiceStateChange?.("degraded");
    } finally {
      setLoading(false);
    }
  }, [onError, onServiceStateChange]);

  const refreshJob = useCallback(async (jobId: string) => {
    try {
      const response = await fetch(`${API_BASE}/api/jobs/${encodeURIComponent(jobId)}`);
      if (!response.ok) return;
      const jobItem: JobListItem = await response.json();
      updateJobInList(jobItem);
    } catch (error) {
      console.error("Failed to refresh job", jobId, error);
    }
  }, []);

  const updateJobInList = useCallback((jobItem: JobListItem) => {
    setJobs((current) => {
      const index = current.findIndex((item) => item.job.job_id === jobItem.job.job_id);
      if (index === -1) {
        return [jobItem, ...current];
      }
      const updated = [...current];
      updated[index] = jobItem;
      return updated;
    });
  }, []);

  return {
    jobs,
    selectedJobId,
    selectedInspection,
    loading,
    setSelectedJobId,
    setSelectedInspection,
    loadJobs,
    refreshJob,
    updateJobInList,
  };
}
