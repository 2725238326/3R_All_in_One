// ═══════════════════════════════════════════════════════════════
// 带进度条的文件上传工具
// ═══════════════════════════════════════════════════════════════

import { API_BASE } from "./appConfig";

export type UploadProgress = {
  loaded: number;
  total: number;
  percent: number;
};

export type UploadOptions = {
  url: string;
  formData: FormData;
  onProgress?: (progress: UploadProgress) => void;
  signal?: AbortSignal;
};

export function uploadWithProgress<T = any>({
  url,
  formData,
  onProgress,
  signal,
}: UploadOptions): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const fullUrl = url.startsWith("http") ? url : `${API_BASE}${url}`;

    xhr.open("POST", fullUrl);

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && onProgress) {
        onProgress({
          loaded: event.loaded,
          total: event.total,
          percent: Math.round((event.loaded / event.total) * 100),
        });
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          resolve(xhr.responseText as any);
        }
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || `上传失败：${xhr.status}`));
        } catch {
          reject(new Error(`上传失败：${xhr.status}`));
        }
      }
    };

    xhr.onerror = () => reject(new Error("网络错误"));
    xhr.ontimeout = () => reject(new Error("上传超时"));

    if (signal) {
      signal.addEventListener("abort", () => {
        xhr.abort();
        reject(new Error("上传已取消"));
      });
    }

    xhr.send(formData);
  });
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}
