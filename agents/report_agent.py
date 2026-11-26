"""ReportAgent: generates escaped, well-structured JSON and HTML analysis reports."""

from __future__ import annotations

import html
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import REPORTS_DIR

logger = logging.getLogger("ai_qa_engineer.report_agent")


class ReportAgent:
    """Generates JSON and HTML reports from static analysis, bugs, tests, and AI review."""

    def __init__(
        self,
        analysis: dict[str, Any] | None = None,
        bugs: list[dict[str, Any]] | None = None,
        test_cases: list[dict[str, Any]] | None = None,
        ai_review: dict[str, Any] | str | None = None,
        reports_dir: Path | str | None = None,
    ) -> None:
        self.analysis = analysis if isinstance(analysis, dict) else {}
        self.bugs = bugs if isinstance(bugs, list) else []
        self.test_cases = test_cases if isinstance(test_cases, list) else []
        self.ai_review = ai_review
        self.reports_dir = Path(reports_dir) if reports_dir else REPORTS_DIR

    def calculate_score(self) -> int:
        """Compute deterministic code quality score (0-100) weighted by bug severity."""
        penalty = 0
        for bug in self.bugs:
            if not isinstance(bug, dict):
                penalty += 2
                continue
            severity = str(bug.get("severity", "warning")).lower()
            if severity == "critical":
                penalty += 6
            elif severity == "warning":
                penalty += 2
            else:
                penalty += 1

        # Cap minor informational penalties so large clean repos aren't forced to 0 unfairly
        score = max(0, 100 - min(penalty, 100))
        return score

    def _build_report_payload(self) -> dict[str, Any]:
        generated_at = datetime.now(timezone.utc).isoformat()
        return {
            "generated_at": generated_at,
            "project": self.analysis.get("project", {}),
            "quality_score": self.calculate_score(),
            "summary": {
                "total_files": self.analysis.get("total_files", 0),
                "parsed_files": self.analysis.get("parsed_files", 0),
                "failed_files": self.analysis.get("failed_files", 0),
                "total_lines": self.analysis.get("total_lines", 0),
                "total_functions": self.analysis.get("total_functions", 0),
                "total_classes": self.analysis.get("total_classes", 0),
                "total_imports": self.analysis.get("total_imports", 0),
                "total_comments": self.analysis.get("total_comments", 0),
                "total_blank_lines": self.analysis.get("total_blank_lines", 0),
                "total_bugs": len(self.bugs),
                "total_test_cases": len(self.test_cases),
            },
            "bugs": self.bugs,
            "test_cases": self.test_cases,
            "ai_review": self.ai_review,
        }

    def generate_json_report(self) -> str:
        """Write structured JSON report to reports/analysis_report.json."""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        payload = self._build_report_payload()
        json_path = self.reports_dir / "analysis_report.json"
        with open(json_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, default=str)
        return str(json_path)

    def generate_html_report(self) -> str:
        """Write HTML-escaped styled report to reports/analysis_report.html."""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        payload = self._build_report_payload()
        project = payload.get("project") or {}
        summary = payload.get("summary") or {}
        score = payload.get("quality_score", 0)
        project_name = html.escape(str(project.get("project_name", "Python Project")))
        framework = html.escape(str(project.get("framework", "None")))
        generated_at = html.escape(str(payload.get("generated_at", "")))

        bug_rows = []
        for bug in self.bugs:
            if isinstance(bug, dict):
                sev = html.escape(str(bug.get("severity", "info")).upper())
                msg = html.escape(str(bug.get("bug", "")))
                f_name = html.escape(os.path.basename(str(bug.get("file", ""))))
                line = html.escape(str(bug.get("line", "-")))
                bug_rows.append(
                    f"<tr><td><span class='badge badge-{sev.lower()}'>{sev}</span></td>"
                    f"<td>{f_name}</td><td>{line}</td><td>{msg}</td></tr>"
                )
        bugs_html = (
            "\n".join(bug_rows)
            if bug_rows
            else "<tr><td colspan='4'>No static bug findings reported.</td></tr>"
        )

        test_rows = []
        for tc in self.test_cases:
            if isinstance(tc, dict):
                fn = html.escape(str(tc.get("function", "")))
                f_name = html.escape(str(tc.get("file", "")))
                scenarios = "; ".join(str(s) for s in tc.get("test_scenarios", []))
                test_rows.append(
                    f"<tr><td><code>{fn}</code></td><td>{f_name}</td>"
                    f"<td>{html.escape(scenarios)}</td></tr>"
                )
        tests_html = (
            "\n".join(test_rows)
            if test_rows
            else "<tr><td colspan='3'>No test case suggestions generated.</td></tr>"
        )

        ai_text = ""
        if isinstance(self.ai_review, dict):
            ai_text = str(self.ai_review.get("raw_text") or self.ai_review.get("summary") or "")
        elif isinstance(self.ai_review, str):
            ai_text = self.ai_review
        ai_html = html.escape(ai_text) if ai_text.strip() else "AI review not available for this run."

        doc = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI QA Engineer Report - {project_name}</title>
  <style>
    body {{ font-family: 'Inter', system-ui, sans-serif; background: #FFF9FC; color: #252238; margin: 0; padding: 32px; }}
    .wrap {{ max-width: 1080px; margin: 0 auto; }}
    .hero {{ background: linear-gradient(135deg, #FCE7F3, #F3E8FF); border: 1px solid #F5D0FE; border-radius: 20px; padding: 28px; margin-bottom: 24px; }}
    h1 {{ margin: 0 0 8px; color: #6D28D9; font-size: 28px; }}
    .meta {{ color: #777187; font-size: 14px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 14px; margin-bottom: 24px; }}
    .card {{ background: #FFFFFF; border: 1px solid #F3E8FF; border-radius: 16px; padding: 18px; box-shadow: 0 6px 20px rgba(109, 40, 217, 0.06); }}
    .metric-val {{ font-size: 26px; font-weight: 700; color: #EC4899; }}
    .metric-lbl {{ font-size: 12px; color: #777187; text-transform: uppercase; letter-spacing: 0.04em; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 14px; }}
    th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid #F3E8FF; vertical-align: top; }}
    th {{ color: #6D28D9; font-weight: 600; background: #FDF4FF; }}
    .badge {{ display: inline-block; padding: 3px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }}
    .badge-critical {{ background: #FEE2E2; color: #DC2626; }}
    .badge-warning {{ background: #FEF3C7; color: #D97706; }}
    .badge-info {{ background: #F3E8FF; color: #6D28D9; }}
    pre {{ white-space: pre-wrap; background: #FAF5FF; padding: 16px; border-radius: 12px; border: 1px solid #F3E8FF; font-size: 13px; line-height: 1.55; }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <h1>AI QA Engineer — Quality Report</h1>
      <div class="meta">Project: <strong>{project_name}</strong> · Framework: <strong>{framework}</strong> · Generated: {generated_at}</div>
    </div>
    <div class="grid">
      <div class="card"><div class="metric-val">{score}/100</div><div class="metric-lbl">Quality Score</div></div>
      <div class="card"><div class="metric-val">{summary.get("total_files", 0)}</div><div class="metric-lbl">Python Files</div></div>
      <div class="card"><div class="metric-val">{summary.get("total_lines", 0)}</div><div class="metric-lbl">Total Lines</div></div>
      <div class="card"><div class="metric-val">{summary.get("total_functions", 0)}</div><div class="metric-lbl">Functions</div></div>
      <div class="card"><div class="metric-val">{summary.get("total_classes", 0)}</div><div class="metric-lbl">Classes</div></div>
      <div class="card"><div class="metric-val">{summary.get("total_bugs", 0)}</div><div class="metric-lbl">Bug Findings</div></div>
    </div>
    <div class="card" style="margin-bottom: 24px;">
      <h2 style="margin-top:0; color:#252238;">Bug &amp; Quality Findings</h2>
      <table><thead><tr><th>Severity</th><th>File</th><th>Line</th><th>Description</th></tr></thead><tbody>{bugs_html}</tbody></table>
    </div>
    <div class="card" style="margin-bottom: 24px;">
      <h2 style="margin-top:0; color:#252238;">Suggested Test Cases (Not Executed)</h2>
      <table><thead><tr><th>Function</th><th>File</th><th>Scenarios</th></tr></thead><tbody>{tests_html}</tbody></table>
    </div>
    <div class="card">
      <h2 style="margin-top:0; color:#252238;">AI Code Review Observations</h2>
      <pre>{ai_html}</pre>
    </div>
  </div>
</body>
</html>"""

        html_path = self.reports_dir / "analysis_report.html"
        with open(html_path, "w", encoding="utf-8") as file:
            file.write(doc)
        return str(html_path)

    def generate_report(self) -> dict[str, Any]:
        """Generate both JSON and HTML reports and return metadata."""
        json_path = self.generate_json_report()
        html_path = self.generate_html_report()
        score = self.calculate_score()

        logger.info("Reports generated at %s and %s (score=%d)", json_path, html_path, score)
        return {
            "status": "success",
            "quality_score": score,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "json_path": json_path,
            "html_path": html_path,
            "json_url": "/reports/latest",
            "html_url": "/reports/html",
            "download_json_url": "/reports/download/json",
            "download_html_url": "/reports/download/html",
        }
