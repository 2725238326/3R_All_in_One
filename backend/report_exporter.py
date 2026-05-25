"""
Report Exporter - PDF/HTML 格式报告导出
"""
from __future__ import annotations

import base64
import html
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

LOGGER = logging.getLogger("kykt.report")


@dataclass
class ReportSection:
    title: str
    content: str
    section_type: str = "text"  # text, table, image, code


@dataclass
class ReportData:
    title: str
    subtitle: str
    generated_at: str
    sections: list[ReportSection]
    metadata: dict
    
    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "generated_at": self.generated_at,
            "sections": [
                {"title": s.title, "content": s.content, "type": s.section_type}
                for s in self.sections
            ],
            "metadata": self.metadata,
        }


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        :root {{
            --bg: #fafafa;
            --surface: #ffffff;
            --text: #111827;
            --text-secondary: #6b7280;
            --border: #e5e7eb;
            --accent: #2563eb;
            --success: #059669;
            --warning: #d97706;
            --error: #dc2626;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 40px 20px;
        }}
        .container {{
            max-width: 900px;
            margin: 0 auto;
            background: var(--surface);
            border-radius: 12px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            padding: 40px;
        }}
        .header {{
            border-bottom: 1px solid var(--border);
            padding-bottom: 24px;
            margin-bottom: 32px;
        }}
        .header h1 {{
            font-size: 28px;
            font-weight: 600;
            margin-bottom: 8px;
        }}
        .header .subtitle {{
            color: var(--text-secondary);
            font-size: 14px;
        }}
        .meta {{
            display: flex;
            gap: 24px;
            margin-top: 16px;
            font-size: 13px;
            color: var(--text-secondary);
        }}
        .meta-item {{
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .section {{
            margin-bottom: 32px;
        }}
        .section h2 {{
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 16px;
            color: var(--text);
        }}
        .section-content {{
            font-size: 14px;
            color: var(--text-secondary);
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }}
        th, td {{
            padding: 10px 12px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{
            background: var(--bg);
            font-weight: 600;
            color: var(--text);
        }}
        tr:hover td {{
            background: var(--bg);
        }}
        .code {{
            background: #1e1e1e;
            color: #d4d4d4;
            padding: 16px;
            border-radius: 8px;
            font-family: 'Fira Code', 'Consolas', monospace;
            font-size: 12px;
            overflow-x: auto;
            white-space: pre-wrap;
        }}
        .image-container {{
            text-align: center;
            margin: 16px 0;
        }}
        .image-container img {{
            max-width: 100%;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}
        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 500;
        }}
        .badge-success {{ background: #d1fae5; color: var(--success); }}
        .badge-warning {{ background: #fef3c7; color: var(--warning); }}
        .badge-error {{ background: #fee2e2; color: var(--error); }}
        .footer {{
            margin-top: 40px;
            padding-top: 24px;
            border-top: 1px solid var(--border);
            font-size: 12px;
            color: var(--text-secondary);
            text-align: center;
        }}
        @media print {{
            body {{ padding: 0; background: white; }}
            .container {{ box-shadow: none; padding: 20px; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>{title}</h1>
            <p class="subtitle">{subtitle}</p>
            <div class="meta">
                <span class="meta-item">📅 {generated_at}</span>
                {meta_items}
            </div>
        </div>
        {sections}
        <div class="footer">
            Generated by KYKT Vision Platform
        </div>
    </div>
</body>
</html>"""


def _render_section(section: ReportSection) -> str:
    content_html = ""
    
    if section.section_type == "text":
        content_html = f'<div class="section-content">{html.escape(section.content)}</div>'
    
    elif section.section_type == "table":
        try:
            data = json.loads(section.content)
            if isinstance(data, list) and len(data) > 0:
                headers = list(data[0].keys())
                rows_html = ""
                for row in data:
                    cells = "".join(f"<td>{html.escape(str(row.get(h, '')))}</td>" for h in headers)
                    rows_html += f"<tr>{cells}</tr>"
                headers_html = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
                content_html = f'<table><thead><tr>{headers_html}</tr></thead><tbody>{rows_html}</tbody></table>'
            else:
                content_html = '<p class="section-content">No data</p>'
        except json.JSONDecodeError:
            content_html = f'<div class="section-content">{html.escape(section.content)}</div>'
    
    elif section.section_type == "code":
        content_html = f'<pre class="code">{html.escape(section.content)}</pre>'
    
    elif section.section_type == "image":
        content_html = f'<div class="image-container"><img src="{section.content}" alt="{html.escape(section.title)}"></div>'
    
    return f'<div class="section"><h2>{html.escape(section.title)}</h2>{content_html}</div>'


def export_html(report: ReportData) -> str:
    """Export report to HTML string."""
    sections_html = "".join(_render_section(s) for s in report.sections)
    
    meta_items = "".join(
        f'<span class="meta-item">• {html.escape(k)}: {html.escape(str(v))}</span>'
        for k, v in report.metadata.items()
    )
    
    return HTML_TEMPLATE.format(
        title=html.escape(report.title),
        subtitle=html.escape(report.subtitle),
        generated_at=html.escape(report.generated_at),
        meta_items=meta_items,
        sections=sections_html,
    )


def export_pdf(report: ReportData, output_path: Path) -> bool:
    """
    Export report to PDF.
    Requires weasyprint or pdfkit installed.
    """
    html_content = export_html(report)
    
    try:
        from weasyprint import HTML
        HTML(string=html_content).write_pdf(output_path)
        return True
    except ImportError:
        pass
    
    try:
        import pdfkit
        pdfkit.from_string(html_content, str(output_path))
        return True
    except ImportError:
        pass
    
    LOGGER.warning("No PDF library available (weasyprint or pdfkit)")
    html_path = output_path.with_suffix(".html")
    html_path.write_text(html_content, encoding="utf-8")
    LOGGER.info(f"Exported HTML instead: {html_path}")
    return False


def build_job_report(job: dict, metrics: Optional[dict] = None, evaluation: Optional[dict] = None) -> ReportData:
    """Build a report from job data."""
    sections = []
    
    # Basic info
    sections.append(ReportSection(
        title="任务信息",
        content=json.dumps([
            {"属性": "任务ID", "值": job.get("job_id", "")},
            {"属性": "模型", "值": job.get("model", "")},
            {"属性": "状态", "值": job.get("status", "")},
            {"属性": "创建时间", "值": job.get("created_at", "")},
            {"属性": "输入类型", "值": job.get("source_type", "")},
        ], ensure_ascii=False),
        section_type="table",
    ))
    
    # Parameters
    params = job.get("params", {})
    if params:
        sections.append(ReportSection(
            title="模型参数",
            content=json.dumps(params, indent=2, ensure_ascii=False),
            section_type="code",
        ))
    
    # Metrics
    if metrics:
        for metric_type, metric_data in metrics.items():
            if isinstance(metric_data, dict) and "metrics" in metric_data:
                rows = [{"指标": k, "值": v} for k, v in metric_data["metrics"].items()]
                sections.append(ReportSection(
                    title=f"评估指标 - {metric_type}",
                    content=json.dumps(rows, ensure_ascii=False),
                    section_type="table",
                ))
    
    # Evaluation
    if evaluation:
        scores = evaluation.get("scores", {})
        if scores:
            rows = [{"维度": k, "评分": f"{v}/5"} for k, v in scores.items()]
            sections.append(ReportSection(
                title="人工评估",
                content=json.dumps(rows, ensure_ascii=False),
                section_type="table",
            ))
        
        comment = evaluation.get("comment", "")
        if comment:
            sections.append(ReportSection(
                title="评估备注",
                content=comment,
                section_type="text",
            ))
    
    return ReportData(
        title=f"任务报告 - {job.get('job_id', 'Unknown')}",
        subtitle=f"{job.get('model', '')} | {job.get('source_type', '')}",
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        sections=sections,
        metadata={
            "model": job.get("model", ""),
            "status": job.get("status", ""),
        },
    )


def build_compare_report(sample_id: str, jobs: list[dict], summary: Optional[dict] = None) -> ReportData:
    """Build a comparison report for multiple jobs."""
    sections = []
    
    # Overview
    sections.append(ReportSection(
        title="对比概览",
        content=json.dumps([
            {"属性": "样例ID", "值": sample_id},
            {"属性": "对比任务数", "值": str(len(jobs))},
            {"属性": "涉及模型", "值": ", ".join(set(j.get("model", "") for j in jobs))},
        ], ensure_ascii=False),
        section_type="table",
    ))
    
    # Job comparison table
    job_rows = []
    for job in jobs:
        job_rows.append({
            "任务ID": job.get("job_id", ""),
            "模型": job.get("model", ""),
            "状态": job.get("status", ""),
            "阶段": job.get("phase", ""),
        })
    
    sections.append(ReportSection(
        title="任务列表",
        content=json.dumps(job_rows, ensure_ascii=False),
        section_type="table",
    ))
    
    # Summary
    if summary:
        sections.append(ReportSection(
            title="对比总结",
            content=summary.get("text", ""),
            section_type="text",
        ))
    
    return ReportData(
        title=f"模型对比报告 - {sample_id}",
        subtitle=f"包含 {len(jobs)} 个任务",
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        sections=sections,
        metadata={
            "sample_id": sample_id,
            "job_count": len(jobs),
        },
    )
