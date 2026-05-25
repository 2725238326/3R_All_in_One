import type { AdvisorReport, AdvisorStatus, JobPayload } from "./types";
import { sourceTypeLabel, statusLabel, statusModelLabel } from "./displayHelpers";
import { isAdvisorSuggested } from "./workflowHelpers";
import { SummaryStat } from "./uiPrimitives";

export function AdvisorPanel(props: { report: AdvisorReport | null }) {
  if (!props.report) {
    return <span className="muted-text">暂无自动评估。</span>;
  }

  return (
    <div className="advisor-panel">
      <div className="summary-strip">
        <SummaryStat label="评分" value={String(props.report.overall_score || "-")} />
        <SummaryStat label="结论" value={props.report.readiness || "-"} />
        <SummaryStat label="模型" value={props.report.advisor_model || "-"} />
      </div>
      <p className="advisor-summary">{props.report.summary}</p>
      {props.report.issues.length > 0 ? (
        <div>
          <strong>主要问题</strong>
          <ul>
            {props.report.issues.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {props.report.next_actions.length > 0 ? (
        <div>
          <strong>下一步</strong>
          <ul>
            {props.report.next_actions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {props.report.teacher_talk ? (
        <div className="advisor-quote">
          <strong>可直接汇报</strong>
          <p>{props.report.teacher_talk}</p>
        </div>
      ) : null}
    </div>
  );
}

export function AdvisorWorkbench(props: {
  job: JobPayload | null;
  advisorState: AdvisorStatus;
  actionKey: string | null;
  onEvaluate: (jobId: string) => void;
  onConfigure: () => void;
  onCopy: (value: string, label: string) => Promise<void>;
  compact?: boolean;
}) {
  if (!props.advisorState.enabled || !props.advisorState.configured) {
    return (
      <div className={`advisor-workbench ${props.compact ? "compact" : ""}`}>
        <div className="advisor-config-note">
          <strong>辅助评估未就绪</strong>
          <p>{props.advisorState.message}</p>
          <div className="advisor-workbench-actions">
            <button onClick={props.onConfigure} type="button">
              配置
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!props.job) {
    return (
      <div className={`advisor-workbench ${props.compact ? "compact" : ""}`}>
        <div className="empty-state">先选中一条任务。</div>
      </div>
    );
  }

  const job = props.job;
  const report = job.advisor_report ?? null;
  const suggested = isAdvisorSuggested(job.job.status);

  return (
    <div className={`advisor-workbench ${props.compact ? "compact" : ""}`}>
      <div className="advisor-workbench-head">
        <div>
          <strong>{job.job.job_id}</strong>
          <p>
            {statusModelLabel(job.job.model)} · {statusLabel(job.job.status)} · {sourceTypeLabel(job.job.source_type)}
          </p>
        </div>
        <div className="advisor-workbench-actions">
          {report?.teacher_talk ? (
            <button onClick={() => void props.onCopy(report.teacher_talk, "汇报话术")} type="button">
              复制汇报话术
            </button>
          ) : null}
          <button
            disabled={!suggested || props.actionKey === "advisor"}
            onClick={() => props.onEvaluate(job.job.job_id)}
            type="button"
          >
            {props.actionKey === "advisor" ? "生成中..." : report ? "重新生成" : "生成草稿"}
          </button>
        </div>
      </div>

      {!report ? (
        <div className="advisor-config-note">
          <strong>{suggested ? "可生成评估草稿" : "等待任务结束"}</strong>
          <p>{suggested ? "会读取参数、摘要和日志。" : "完成、失败或取消后再生成。"}</p>
        </div>
      ) : (
        <>
          <AdvisorPanel report={report} />
          {props.compact ? null : (
            <div className="advisor-copy-row">
              <button onClick={() => void props.onCopy(report.summary, "评估摘要")} type="button">
                复制摘要
              </button>
              {report.teacher_talk ? (
                <button onClick={() => void props.onCopy(report.teacher_talk, "汇报话术")} type="button">
                  复制汇报话术
                </button>
              ) : null}
            </div>
          )}
        </>
      )}
    </div>
  );
}
