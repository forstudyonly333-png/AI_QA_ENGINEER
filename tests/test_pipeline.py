"""Automated tests for AI QA Engineer agents, workflow, and FastAPI endpoints."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

from agents.ai_reviewer import AIReviewerAgent
from agents.bug_analyzer import BugAnalyzerAgent
from agents.code_analyzer import CodeAnalyzerAgent
from agents.code_loader import CodeLoaderAgent
from agents.report_agent import ReportAgent
from agents.test_generator import TestGeneratorAgent
from app import DebugRequest, ProjectRequest, analyze, browse_directory, debug_snippet, health, home, stats
from workflow import run_workflow


def test_code_loader_requirements_and_framework(tmp_path: Path) -> None:
    (tmp_path / "requirements.txt").write_text("uvicorn==0.51.0\nfastapi==0.139.0\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")

    data = CodeLoaderAgent(str(tmp_path)).load_project()
    assert data["framework"] == "FastAPI"
    assert len(data["requirements"]) == 2
    assert data["total_files"] == 1


def test_syntax_error_does_not_crash_pipeline(tmp_path: Path) -> None:
    (tmp_path / "good.py").write_text(
        'def add(a, b):\n    """Add two numbers."""\n    return a + b\n',
        encoding="utf-8",
    )
    (tmp_path / "broken.py").write_text("def broken(x\n    return x\n", encoding="utf-8")

    with patch("workflow.AIReviewerAgent.review_structured") as mock_ai, patch("workflow._record_run_stats"):
        mock_ai.return_value = {
            "status": "unavailable",
            "summary": "AI Review unavailable in offline test.",
            "architecture_feedback": "",
            "maintainability": "",
            "security_observations": [],
            "action_items": [],
            "raw_text": "AI Review unavailable in offline test.",
            "model": "gemini-3.8-flash",
            "error": "Missing key",
        }
        result = run_workflow(str(tmp_path))

    assert result["status"] in ("success", "partial")
    assert result["analysis"]["total_files"] == 2
    assert result["analysis"]["parsed_files"] == 1
    assert result["analysis"]["failed_files"] == 1
    assert len(result["analysis"]["analysis_errors"]) == 1
    assert any(tc["function"] == "add" for tc in result["test_cases"])
    assert result["report"]["status"] == "success"


def test_empty_directory_and_invalid_path(tmp_path: Path) -> None:
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    res_empty = run_workflow(str(empty_dir))
    assert res_empty["status"] == "partial"
    assert res_empty["analysis"]["total_files"] == 0

    res_missing = run_workflow(str(tmp_path / "does_not_exist"))
    assert res_missing["status"] == "error"
    assert "does not exist" in res_missing["message"]

    res_blank = run_workflow("   ")
    assert res_blank["status"] == "error"


def test_bug_analyzer_and_test_generator_fixes(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text(
        "# TODO: refine logic\n"
        "secret_token = 'hardcoded123'\n"
        "def divide(a, b):\n"
        "    try:\n"
        "        print(a)\n"
        "        return a / b\n"
        "    except:\n"
        "        return None\n"
        "def login(user, pw):\n"
        "    return True\n",
        encoding="utf-8",
    )
    project_data = CodeLoaderAgent(str(tmp_path)).load_project()
    analyzer = CodeAnalyzerAgent(project_data)
    analysis = analyzer.analyze()
    bugs = BugAnalyzerAgent(project_data, parsed_cache=analyzer.get_parsed_cache()).analyze()
    bug_msgs = [b["bug"] for b in bugs]

    assert any("TODO" in m for m in bug_msgs)
    assert any("hardcoded secret" in m.lower() for m in bug_msgs)
    assert any("Bare except" in m for m in bug_msgs)
    assert any("Print statement" in m for m in bug_msgs)
    assert any("Missing function docstring" in m for m in bug_msgs)

    tests = TestGeneratorAgent(analysis).generate_tests()
    fn_names = {t["function"] for t in tests}
    assert {"divide", "login"}.issubset(fn_names)


def test_ai_reviewer_unavailable_without_key() -> None:
    reviewer = AIReviewerAgent(api_key="")
    res = reviewer.review_structured({"total_files": 1})
    assert res["status"] == "unavailable"
    assert "unavailable" in res["summary"].lower()


def test_report_agent_escapes_html(tmp_path: Path) -> None:
    agent = ReportAgent(
        analysis={"project": {"project_name": "<script>alert(1)</script>"}, "total_files": 1},
        bugs=[{"file": "a.py", "line": 1, "severity": "warning", "bug": "<img src=x onerror=alert(1)>"}],
        test_cases=[{"function": "f", "file": "a.py", "test_scenarios": ["<b>check</b>"]}],
        ai_review={"status": "unavailable", "raw_text": "No AI"},
        reports_dir=tmp_path,
    )
    meta = agent.generate_report()
    assert meta["status"] == "success"
    html_text = (tmp_path / "analysis_report.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html_text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_text
    json_data = json.loads((tmp_path / "analysis_report.json").read_text(encoding="utf-8"))
    assert json_data["summary"]["total_bugs"] == 1


def test_fastapi_endpoints_and_debugger(tmp_path: Path) -> None:
    r_home = home()
    assert r_home.status_code == 200
    body_text = r_home.body.decode("utf-8")
    assert "Your Intelligent AI Partner for" in body_text
    assert "Better Code." in body_text

    r_health = health()
    assert r_health["status"] == "ok"

    r_stats = stats()
    assert r_stats["analysis_agents"] == 6

    r_browse = browse_directory(None)
    assert r_browse["status"] == "success"

    r_debug_ok = asyncio.run(debug_snippet(DebugRequest(code="def ok():\n    return 1\n", language="python")))
    ok_payload = json.loads(r_debug_ok.body.decode("utf-8"))
    assert ok_payload["validation_status"] is True

    r_debug_js = asyncio.run(debug_snippet(DebugRequest(code="const x = 1;", language="javascript")))
    js_payload = json.loads(r_debug_js.body.decode("utf-8"))
    assert js_payload["status"] == "unsupported"

    r_empty_analyze = asyncio.run(analyze(ProjectRequest(project_path="")))
    assert r_empty_analyze.status_code == 400
    assert json.loads(r_empty_analyze.body.decode("utf-8"))["status"] == "error"

    (tmp_path / "calc.py").write_text('def add(x, y):\n    """Sum."""\n    return x + y\n', encoding="utf-8")
    with patch("workflow.AIReviewerAgent.review_structured") as mock_ai, patch("workflow._record_run_stats"):
        mock_ai.return_value = {
            "status": "completed",
            "summary": "Clean module.",
            "architecture_feedback": "Good.",
            "maintainability": "High.",
            "security_observations": [],
            "action_items": ["Add type hints"],
            "raw_text": "Clean module.",
            "model": "gemini-3.8-flash",
            "error": None,
        }
        r_analyze = asyncio.run(analyze(ProjectRequest(project_path=str(tmp_path))))
    payload = json.loads(r_analyze.body.decode("utf-8"))
    assert payload["status"] == "success"
    assert payload["analysis"]["total_functions"] == 1
    assert payload["ai_review_details"]["status"] == "completed"
