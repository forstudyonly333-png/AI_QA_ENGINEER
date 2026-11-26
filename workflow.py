"""Workflow orchestrator for the 6-agent AI QA Engineer analysis pipeline."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.ai_reviewer import AIReviewerAgent
from agents.bug_analyzer import BugAnalyzerAgent
from agents.code_analyzer import CodeAnalyzerAgent
from agents.code_loader import CodeLoaderAgent
from agents.report_agent import ReportAgent
from agents.test_generator import TestGeneratorAgent
from config import HISTORY_FILE, REPORTS_DIR, WORKFLOW_TIMEOUT_SECONDS

logger = logging.getLogger("ai_qa_engineer.workflow")

STAGE_DEFINITIONS = [
    ("code_loader", "Code Loader Agent", "Scans directory, discovers Python files, and extracts metadata"),
    ("code_analyzer", "Code Analyzer Agent", "Parses AST structure, functions, classes, and imports"),
    ("bug_analyzer", "Bug Analyzer Agent", "Detects code smells, bare excepts, prints, and hardcoded secrets"),
    ("test_generator", "Test Generator Agent", "Generates suggested test-case scenarios and pytest skeletons"),
    ("report_agent", "Report Agent", "Builds structured JSON and styled HTML quality reports"),
    ("ai_reviewer", "AI Reviewer Agent", "Synthesizes executive code review via Google Gemini"),
]

_PROGRESS_LOCK = threading.Lock()
_JOB_PROGRESS: dict[str, dict[str, Any]] = {}


def _init_stages() -> list[dict[str, Any]]:
    return [
        {
            "id": stage_id,
            "name": name,
            "description": desc,
            "status": "pending",
            "duration_ms": 0,
            "detail": "Waiting...",
        }
        for stage_id, name, desc in STAGE_DEFINITIONS
    ]


def _update_stage(
    job_id: str | None,
    stages: list[dict[str, Any]],
    stage_id: str,
    status: str,
    detail: str,
    duration_ms: int = 0,
) -> None:
    for st in stages:
        if st["id"] == stage_id:
            st["status"] = status
            st["detail"] = detail
            st["duration_ms"] = duration_ms
            break
    if job_id:
        with _PROGRESS_LOCK:
            _JOB_PROGRESS[job_id] = {
                "job_id": job_id,
                "current_stage": stage_id,
                "stages": [dict(s) for s in stages],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }


def get_job_progress(job_id: str) -> dict[str, Any] | None:
    """Return latest recorded stage snapshot for a running or finished job."""
    with _PROGRESS_LOCK:
        snap = _JOB_PROGRESS.get(job_id)
        return dict(snap) if snap else None


def _record_run_stats(
    project_name: str,
    project_path: str,
    status: str,
    bugs_count: int,
    tests_count: int,
    score: int,
) -> None:
    """Persist real analysis run counters for dashboard statistics."""
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        history: dict[str, Any] = {
            "projects_analyzed": 0,
            "issues_detected": 0,
            "test_cases_generated": 0,
            "recent_runs": [],
        }
        if HISTORY_FILE.is_file():
            with open(HISTORY_FILE, "r", encoding="utf-8") as file:
                loaded = json.load(file)
                if isinstance(loaded, dict):
                    history.update(loaded)

        history["projects_analyzed"] = int(history.get("projects_analyzed", 0)) + 1
        history["issues_detected"] = int(history.get("issues_detected", 0)) + bugs_count
        history["test_cases_generated"] = int(history.get("test_cases_generated", 0)) + tests_count
        recent = list(history.get("recent_runs") or [])
        recent.insert(
            0,
            {
                "project_name": project_name,
                "project_path": project_path,
                "status": status,
                "bugs_count": bugs_count,
                "tests_count": tests_count,
                "quality_score": score,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        history["recent_runs"] = recent[:10]

        with open(HISTORY_FILE, "w", encoding="utf-8") as file:
            json.dump(history, file, indent=2)
    except Exception as exc:
        logger.warning("Could not update analysis history stats: %s", exc)


def get_stats_summary() -> dict[str, Any]:
    """Return real persisted stats without inventing mock metrics."""
    if HISTORY_FILE.is_file():
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as file:
                data = json.load(file)
                if isinstance(data, dict):
                    return {
                        "has_data": int(data.get("projects_analyzed", 0)) > 0,
                        "projects_analyzed": int(data.get("projects_analyzed", 0)),
                        "issues_detected": int(data.get("issues_detected", 0)),
                        "test_cases_generated": int(data.get("test_cases_generated", 0)),
                        "analysis_agents": len(STAGE_DEFINITIONS),
                        "recent_runs": data.get("recent_runs", []),
                    }
        except Exception:
            pass

    return {
        "has_data": False,
        "projects_analyzed": 0,
        "issues_detected": 0,
        "test_cases_generated": 0,
        "analysis_agents": len(STAGE_DEFINITIONS),
        "recent_runs": [],
    }


def _build_error_response(message: str, project_path: str, errors: list[dict[str, Any]], stages: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "error",
        "message": message,
        "project_path": project_path,
        "duration_ms": 0,
        "stages": stages,
        "analysis": {},
        "bug": [],
        "test_cases": [],
        "report": {},
        "ai_review": "",
        "ai_review_details": {
            "status": "unavailable",
            "summary": message,
            "architecture_feedback": "",
            "maintainability": "",
            "security_observations": [],
            "action_items": [],
            "raw_text": "",
        },
        "errors": errors,
    }


def run_workflow(project_path: str, job_id: str | None = None) -> dict[str, Any]:
    """Execute the full multi-agent analysis pipeline and always return a valid dict."""
    started_at = time.perf_counter()
    stages = _init_stages()
    errors: list[dict[str, Any]] = []

    raw_input = (project_path or "").strip().strip('"').strip("'")
    if not raw_input:
        msg = "Project path cannot be empty."
        errors.append({"stage": "validation", "error": msg})
        return _build_error_response(msg, "", errors, stages)

    try:
        clean_path = str(Path(raw_input).expanduser().resolve())
    except OSError as exc:
        msg = f"Invalid project path '{raw_input}': {exc}"
        errors.append({"stage": "validation", "error": msg})
        return _build_error_response(msg, raw_input, errors, stages)

    if not os.path.exists(clean_path):
        msg = f"Project directory does not exist: {clean_path}"
        errors.append({"stage": "validation", "error": msg})
        return _build_error_response(msg, clean_path, errors, stages)

    if not os.path.isdir(clean_path):
        msg = f"Path is not a directory: {clean_path}"
        errors.append({"stage": "validation", "error": msg})
        return _build_error_response(msg, clean_path, errors, stages)

    # Step 1: Code Loader Agent
    project_data: dict[str, Any] = {}
    t0 = time.perf_counter()
    _update_stage(job_id, stages, "code_loader", "running", "Scanning directory for Python files...")
    try:
        loader = CodeLoaderAgent(clean_path)
        project_data = loader.load_project()
        if project_data.get("errors"):
            errors.extend(project_data["errors"])
        file_count = project_data.get("total_files", 0)
        _update_stage(
            job_id,
            stages,
            "code_loader",
            "completed",
            f"Discovered {file_count} Python file(s) ({project_data.get('framework', 'None')} framework)",
            int((time.perf_counter() - t0) * 1000),
        )
    except Exception as exc:
        logger.exception("CodeLoaderAgent failed")
        err_msg = f"CodeLoaderAgent failed: {exc}"
        errors.append({"stage": "code_loader", "error": err_msg})
        _update_stage(job_id, stages, "code_loader", "failed", err_msg, int((time.perf_counter() - t0) * 1000))
        return _build_error_response(err_msg, clean_path, errors, stages)

    # Handle empty Python project gracefully
    if project_data.get("total_files", 0) == 0:
        empty_analysis = {
            "status": "Partial",
            "message": "No Python (.py) files found in the selected directory.",
            "project": project_data,
            "total_files": 0,
            "parsed_files": 0,
            "failed_files": 0,
            "total_lines": 0,
            "total_functions": 0,
            "total_classes": 0,
            "total_imports": 0,
            "total_comments": 0,
            "total_blank_lines": 0,
            "functions": [],
            "classes": [],
            "imports": [],
            "large_functions": [],
            "files_summary": [],
            "analysis_errors": [],
        }
        for s_id in ("code_analyzer", "bug_analyzer", "test_generator", "report_agent", "ai_reviewer"):
            _update_stage(job_id, stages, s_id, "skipped", "Skipped (no Python files in directory)")
        total_ms = int((time.perf_counter() - started_at) * 1000)
        errors.append({"stage": "code_loader", "error": "No Python (.py) files found in directory."})
        return {
            "status": "partial",
            "message": "Directory scanned successfully, but no Python (.py) files were found.",
            "project_path": clean_path,
            "duration_ms": total_ms,
            "stages": stages,
            "analysis": empty_analysis,
            "bug": [],
            "test_cases": [],
            "report": {},
            "ai_review": "AI Review skipped because no Python source files were found.",
            "ai_review_details": {
                "status": "unavailable",
                "summary": "No Python source files found to review.",
                "architecture_feedback": "",
                "maintainability": "",
                "security_observations": [],
                "action_items": [],
                "raw_text": "No Python source files found to review.",
            },
            "errors": errors,
        }

    # Step 2: Code Analyzer Agent (single-pass AST parse + cache)
    analysis: dict[str, Any] = {}
    parsed_cache: dict[str, dict[str, Any]] | None = None
    t0 = time.perf_counter()
    _update_stage(job_id, stages, "code_analyzer", "running", "Parsing Python ASTs and computing metrics...")
    try:
        analyzer = CodeAnalyzerAgent(project_data)
        analysis = analyzer.analyze()
        parsed_cache = analyzer.get_parsed_cache()
        for err in analysis.get("analysis_errors", []):
            errors.append({"stage": "code_analyzer", **err})
        _update_stage(
            job_id,
            stages,
            "code_analyzer",
            "completed",
            f"Parsed {analysis.get('parsed_files', 0)}/{analysis.get('total_files', 0)} files "
            f"({analysis.get('total_functions', 0)} functions, {analysis.get('total_classes', 0)} classes)",
            int((time.perf_counter() - t0) * 1000),
        )
    except Exception as exc:
        logger.exception("CodeAnalyzerAgent failed")
        err_msg = f"CodeAnalyzerAgent failed: {exc}"
        errors.append({"stage": "code_analyzer", "error": err_msg})
        analysis = {
            "status": "Error",
            "message": err_msg,
            "project": project_data,
            "total_files": project_data.get("total_files", 0),
            "parsed_files": 0,
            "failed_files": project_data.get("total_files", 0),
            "total_lines": 0,
            "total_functions": 0,
            "total_classes": 0,
            "total_imports": 0,
            "total_comments": 0,
            "total_blank_lines": 0,
            "functions": [],
            "classes": [],
            "imports": [],
            "large_functions": [],
            "files_summary": [],
            "analysis_errors": [],
        }
        _update_stage(job_id, stages, "code_analyzer", "failed", err_msg, int((time.perf_counter() - t0) * 1000))

    # Step 3: Bug Analyzer Agent (reuses parsed_cache)
    bugs: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    _update_stage(job_id, stages, "bug_analyzer", "running", "Scanning for bugs, code smells, and secret patterns...")
    try:
        bug_agent = BugAnalyzerAgent(project_data, parsed_cache=parsed_cache)
        bugs = bug_agent.analyze()
        for err in bug_agent.errors:
            errors.append({"stage": "bug_analyzer", **err})
        _update_stage(
            job_id,
            stages,
            "bug_analyzer",
            "completed",
            f"Identified {len(bugs)} static finding(s)",
            int((time.perf_counter() - t0) * 1000),
        )
    except Exception as exc:
        logger.exception("BugAnalyzerAgent failed")
        err_msg = f"BugAnalyzerAgent failed: {exc}"
        errors.append({"stage": "bug_analyzer", "error": err_msg})
        _update_stage(job_id, stages, "bug_analyzer", "failed", err_msg, int((time.perf_counter() - t0) * 1000))

    # Step 4: Test Generator Agent
    test_cases: list[dict[str, Any]] = []
    t0 = time.perf_counter()
    _update_stage(job_id, stages, "test_generator", "running", "Generating suggested test scenarios...")
    try:
        test_agent = TestGeneratorAgent(analysis)
        test_cases = test_agent.generate_tests()
        _update_stage(
            job_id,
            stages,
            "test_generator",
            "completed",
            f"Generated {len(test_cases)} suggested test case(s)",
            int((time.perf_counter() - t0) * 1000),
        )
    except Exception as exc:
        logger.exception("TestGeneratorAgent failed")
        err_msg = f"TestGeneratorAgent failed: {exc}"
        errors.append({"stage": "test_generator", "error": err_msg})
        _update_stage(job_id, stages, "test_generator", "failed", err_msg, int((time.perf_counter() - t0) * 1000))

    # Step 5: AI Reviewer Agent (executed before final report so report includes AI review)
    ai_review_details: dict[str, Any] = {
        "status": "unavailable",
        "summary": "AI Review not run.",
        "architecture_feedback": "",
        "maintainability": "",
        "security_observations": [],
        "action_items": [],
        "raw_text": "",
    }
    elapsed_so_far = time.perf_counter() - started_at
    t0 = time.perf_counter()
    if elapsed_so_far > max(10, WORKFLOW_TIMEOUT_SECONDS - 10):
        msg = "AI Review skipped to stay within workflow execution timeout."
        ai_review_details = {
            **ai_review_details,
            "status": "failed",
            "summary": msg,
            "raw_text": msg,
            "error": msg,
        }
        errors.append({"stage": "ai_reviewer", "error": msg})
        _update_stage(job_id, stages, "ai_reviewer", "skipped", msg, 0)
    else:
        _update_stage(job_id, stages, "ai_reviewer", "running", "Requesting Gemini architectural code review...")
        try:
            review_context = {
                "project_name": project_data.get("project_name"),
                "framework": project_data.get("framework"),
                "requirements_count": len(project_data.get("requirements") or []),
                "metrics": {
                    "total_files": analysis.get("total_files", 0),
                    "parsed_files": analysis.get("parsed_files", 0),
                    "failed_files": analysis.get("failed_files", 0),
                    "total_lines": analysis.get("total_lines", 0),
                    "total_functions": analysis.get("total_functions", 0),
                    "total_classes": analysis.get("total_classes", 0),
                    "total_imports": analysis.get("total_imports", 0),
                    "large_functions": (analysis.get("large_functions") or [])[:10],
                },
                "bugs_sample": bugs[:25],
                "total_bugs": len(bugs),
                "analysis_errors": analysis.get("analysis_errors", [])[:10],
            }
            reviewer = AIReviewerAgent()
            ai_review_details = reviewer.review_structured(review_context)
            ai_status = ai_review_details.get("status", "failed")
            if ai_status == "completed":
                _update_stage(
                    job_id,
                    stages,
                    "ai_reviewer",
                    "completed",
                    f"AI review completed via {ai_review_details.get('model', 'Gemini')}",
                    int((time.perf_counter() - t0) * 1000),
                )
            elif ai_status == "unavailable":
                _update_stage(
                    job_id,
                    stages,
                    "ai_reviewer",
                    "skipped",
                    "AI review unavailable (missing API key)",
                    int((time.perf_counter() - t0) * 1000),
                )
            else:
                err_txt = ai_review_details.get("error") or "AI review failed"
                errors.append({"stage": "ai_reviewer", "error": err_txt})
                _update_stage(
                    job_id,
                    stages,
                    "ai_reviewer",
                    "failed",
                    f"AI review unavailable ({err_txt})",
                    int((time.perf_counter() - t0) * 1000),
                )
        except Exception as exc:
            logger.exception("AIReviewerAgent failed")
            err_msg = f"AIReviewerAgent failed: {exc}"
            errors.append({"stage": "ai_reviewer", "error": err_msg})
            ai_review_details = {
                **ai_review_details,
                "status": "failed",
                "summary": err_msg,
                "raw_text": err_msg,
                "error": err_msg,
            }
            _update_stage(job_id, stages, "ai_reviewer", "failed", err_msg, int((time.perf_counter() - t0) * 1000))

    # Step 6: Report Agent
    report: dict[str, Any] = {}
    t0 = time.perf_counter()
    _update_stage(job_id, stages, "report_agent", "running", "Generating JSON and HTML reports...")
    try:
        report_agent = ReportAgent(
            analysis=analysis,
            bugs=bugs,
            test_cases=test_cases,
            ai_review=ai_review_details,
        )
        report = report_agent.generate_report()
        _update_stage(
            job_id,
            stages,
            "report_agent",
            "completed",
            f"Generated JSON & HTML reports (Score: {report.get('quality_score', 0)}/100)",
            int((time.perf_counter() - t0) * 1000),
        )
    except Exception as exc:
        logger.exception("ReportAgent failed")
        err_msg = f"ReportAgent failed: {exc}"
        errors.append({"stage": "report_agent", "error": err_msg})
        report = {"status": "error", "message": err_msg}
        _update_stage(job_id, stages, "report_agent", "failed", err_msg, int((time.perf_counter() - t0) * 1000))

    has_non_ai_errors = any(e.get("stage") != "ai_reviewer" for e in errors)
    overall_status = "partial" if (has_non_ai_errors or ai_review_details.get("status") == "failed") else "success"
    overall_message = (
        "Analysis completed successfully."
        if overall_status == "success"
        else "Analysis completed with warnings or partial stage results."
    )

    _record_run_stats(
        project_name=project_data.get("project_name", "Project"),
        project_path=clean_path,
        status=overall_status,
        bugs_count=len(bugs),
        tests_count=len(test_cases),
        score=int(report.get("quality_score", 0)) if isinstance(report, dict) else 0,
    )

    total_ms = int((time.perf_counter() - started_at) * 1000)
    logger.info("Workflow finished in %dms (status=%s, bugs=%d, tests=%d)", total_ms, overall_status, len(bugs), len(test_cases))

    return {
        "status": overall_status,
        "message": overall_message,
        "project_path": clean_path,
        "duration_ms": total_ms,
        "stages": stages,
        "analysis": analysis,
        "bug": bugs,
        "test_cases": test_cases,
        "report": report,
        "ai_review": ai_review_details.get("raw_text") or ai_review_details.get("summary") or "",
        "ai_review_details": ai_review_details,
        "errors": errors,
    }
