import type { AdvisorReport, AdvisorStatus, JobPayload, ResultContract } from "./types";

type OutputItem = JobPayload["outputs"][number];

export type OutputSection = {
  key: string;
  title: string;
  description: string;
  accent: "blue" | "green" | "gold" | "slate";
  defaultOpen: boolean;
  items: OutputItem[];
};

export function buildOutputSections(outputs: OutputItem[], model: string, contract?: ResultContract): OutputSection[] {
  if (contract) {
    const sections: OutputSection[] = contract.groups.map((g) => ({
      key: g.key,
      title: g.label,
      description: g.description || "",
      accent: "blue",
      defaultOpen: true,
      items: []
    }));

    const otherSection: OutputSection = {
      key: "other",
      title: "其他产物",
      description: "契约之外的产物。",
      accent: "slate",
      defaultOpen: false,
      items: []
    };

    outputs.forEach((out) => {
      const artifact = contract.artifacts.find(
        (a) => a.name === out.display_name || out.relative_path.endsWith(a.relativePath)
      );
      if (artifact) {
        const section = sections.find((s) => s.key === artifact.role);
        if (section) {
          section.items.push(out);
          return;
        }
      }
      otherSection.items.push(out);
    });

    return [...sections, otherSection].filter((s) => s.items.length > 0);
  }

  const buckets: Record<string, OutputSection> = {
    main: {
      key: "main",
      title: "核心成果",
      description: model === "monst3r" ? "三维场景、点云、主要导出。" : "点云与主要可视化。",
      accent: "blue",
      defaultOpen: true,
      items: []
    },
    camera: {
      key: "camera",
      title: "相机与轨迹",
      description: "相机内参、位姿、轨迹等文本产物。",
      accent: "slate",
      defaultOpen: true,
      items: []
    },
    masks: {
      key: "masks",
      title: "掩膜与动态区域",
      description: "动态 mask 与扩张 mask。",
      accent: "gold",
      defaultOpen: false,
      items: []
    },
    confidence: {
      key: "confidence",
      title: "置信度与数组",
      description: "置信图、深度数组和中间数值文件。",
      accent: "slate",
      defaultOpen: false,
      items: []
    },
    visuals: {
      key: "visuals",
      title: "图像可视化",
      description: "可直接浏览的 PNG/JPG 结果图。",
      accent: "green",
      defaultOpen: true,
      items: []
    },
    other: {
      key: "other",
      title: "其他产物",
      description: "未归类文件。",
      accent: "slate",
      defaultOpen: false,
      items: []
    }
  };

  outputs.forEach((output) => {
    const name = output.display_name.toLowerCase();
    if (output.is_model3d || output.is_pointcloud || /scene\.glb|pointcloud|matches\./i.test(name)) {
      buckets.main.items.push(output);
      return;
    }
    if (/traj|intrinsics|poses?|focal|camera/i.test(name) || name.endsWith(".txt")) {
      buckets.camera.items.push(output);
      return;
    }
    if (/mask/i.test(name)) {
      buckets.masks.items.push(output);
      return;
    }
    if (/conf|depth|frame_.*\.npy|\.npy$/i.test(name)) {
      buckets.confidence.items.push(output);
      return;
    }
    if (output.is_image) {
      buckets.visuals.items.push(output);
      return;
    }
    buckets.other.items.push(output);
  });

  const orderedKeys = ["main", "visuals", "camera", "masks", "confidence", "other"];

  return orderedKeys
    .map((key) => buckets[key])
    .filter((section) => section && section.items.length > 0);
}

export function buildInspectorRhythm(
  selectedJob: JobPayload,
  latestLogLine: string,
  criticalLogLine: string,
  advisorReport: AdvisorReport | null
) {
  const summary = selectedJob.result_summary;
  const evaluation = selectedJob.evaluation;
  const outputCount = selectedJob.outputs.length;
  const primaryCount = summary?.primary_artifacts?.length ?? 0;
  const logCount = selectedJob.logs.length;

  return [
    {
      id: "job-summary-panel",
      label: "摘要",
      status: summary ? "已生成" : "等待结果",
      detail: summary?.next_actions?.length ? `下一步 ${summary.next_actions.length} 条` : summary ? "有结果摘要可复查" : "结果回传后生成摘要",
      tone: summary ? "ready" : "pending"
    },
    {
      id: "job-outputs-panel",
      label: "证据",
      status: outputCount > 0 ? `${outputCount} 个产物` : "无产物",
      detail: primaryCount > 0 ? `核心检查对象 ${primaryCount} 个` : outputCount > 0 ? "按用途分组查看" : "等待远端输出下载",
      tone: outputCount > 0 ? "ready" : "pending"
    },
    {
      id: "job-logs-panel",
      label: "日志",
      status: criticalLogLine ? "待排查" : logCount > 0 ? "可追踪" : "暂无日志",
      detail: criticalLogLine || latestLogLine || "运行开始后会显示日志尾部",
      tone: criticalLogLine ? "attention" : logCount > 0 ? "ready" : "pending"
    },
    {
      id: "job-evaluation-panel",
      label: "评分",
      status: evaluation ? "人工已评" : advisorReport ? "自动已评" : "待评估",
      detail: evaluation
        ? "人工评分"
        : advisorReport
          ? `结论：${advisorReport.readiness}`
          : "等待评分",
      tone: evaluation || advisorReport ? "ready" : "pending"
    }
  ];
}

export function buildAdvisorCompactStatus(state: AdvisorStatus, report: AdvisorReport | null, suggested: boolean) {
  if (!state.enabled) {
    return "未启用";
  }
  if (!state.configured) {
    return "未配置";
  }
  if (report) {
    return "已有草稿";
  }
  return suggested ? "可生成草稿" : "等待结果";
}

export function currentStepLabel(steps: JobPayload["phase_display"]["steps"]) {
  const currentIndex = steps.findIndex((step) => step.state === "current");
  if (currentIndex >= 0) {
    return `第 ${currentIndex + 1} / ${steps.length} 阶段`;
  }
  if (steps.every((step) => step.state === "done")) {
    return "全部阶段完成";
  }
  return `共 ${steps.length} 个阶段`;
}

export function HighlightedLogTail(props: { text: string; query: string }) {
  if (!props.query) {
    return <>{props.text}</>;
  }
  const pattern = new RegExp(`(${escapeRegExp(props.query)})`, "gi");
  const parts = props.text.split(pattern);
  return (
    <>
      {parts.map((part, index) =>
        part.toLowerCase() === props.query.toLowerCase() ? (
          <mark className="log-hit" key={`${part}-${index}`}>
            {part}
          </mark>
        ) : (
          <span key={`${part}-${index}`}>{part}</span>
        )
      )}
    </>
  );
}

function escapeRegExp(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function countLogLines(logs: JobPayload["logs"]) {
  return logs.reduce((total, log) => {
    const lines = (log.tail || "").split(/\r?\n/).filter((line) => line.trim().length > 0);
    return total + lines.length;
  }, 0);
}

export function countLogKeywordHits(logs: JobPayload["logs"], query: string) {
  if (!query) {
    return 0;
  }
  const needle = query.toLowerCase();
  return logs.reduce((total, log) => {
    const lines = (log.tail || "").split(/\r?\n/).filter((line) => line.trim().length > 0);
    return total + lines.filter((line) => line.toLowerCase().includes(needle)).length;
  }, 0);
}

export function buildAttentionJobMessage(status: string, errorMessage: string | null | undefined, criticalLogLine: string, latestLogLine: string) {
  if (errorMessage) {
    return errorMessage;
  }
  if (criticalLogLine) {
    return `优先查看可疑日志：${criticalLogLine}`;
  }
  if (latestLogLine) {
    return `没有明确错误行，先从最新日志判断是否需要重试：${latestLogLine}`;
  }
  return status === "cancelled" ? "任务已取消，先确认是否需要清理远端残留或复制任务重跑。" : "任务失败但没有回传明确日志，先检查远端状态和 dispatch 日志。";
}

export function getLatestLogLine(logs: JobPayload["logs"]) {
  for (const log of logs) {
    const lines = (log.tail || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    for (let index = lines.length - 1; index >= 0; index -= 1) {
      const line = lines[index];
      if (!/futurewarning|warning, cannot find cuda-compiled version of rope2d/i.test(line)) {
        return line;
      }
    }
  }
  return "";
}

export function getCriticalLogLine(logs: JobPayload["logs"]) {
  const criticalPattern = /traceback|exception|fatal|runtimeerror|oom|cuda out of memory|failed|error/i;
  const ignoredPattern = /futurewarning|warning, cannot find cuda-compiled version of rope2d/i;
  for (const log of logs) {
    const lines = (log.tail || "")
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean);
    for (let index = lines.length - 1; index >= 0; index -= 1) {
      const line = lines[index];
      if (ignoredPattern.test(line)) {
        continue;
      }
      if (criticalPattern.test(line)) {
        return line;
      }
    }
  }
  return "";
}
