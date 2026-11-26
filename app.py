"""FastAPI backend for AI QA Engineer Platform."""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import string
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from config import (
    BASE_DIR,
    FRONTEND_DIR,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    REPORTS_DIR,
    WORKFLOW_TIMEOUT_SECONDS,
    logger,
)
from workflow import get_job_progress, get_stats_summary, run_workflow


class ProjectRequest(BaseModel):
    project_path: str = Field(..., description="Local directory path of the Python project to analyze.")
    job_id: str | None = Field(default=None, description="Optional client job ID for stage progress polling.")


class DebugRequest(BaseModel):
    code: str = Field(..., description="Source code snippet to validate/debug.")
    language: str = Field(default="python", description="Programming language (currently 'python').")


app = FastAPI(title="AI QA Engineer Platform", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if FRONTEND_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    """Serve the main AI QA Engineer web dashboard."""
    index_file = FRONTEND_DIR / "index.html"
    if not index_file.is_file():
        return HTMLResponse(
            content="<h1>AI QA Engineer</h1><p>Frontend index.html not found.</p>",
            status_code=500,
        )
    return HTMLResponse(content=index_file.read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict[str, Any]:
    """Return service health and AI availability without exposing credentials."""
    return {
        "status": "ok",
        "ai_configured": bool(GEMINI_API_KEY),
        "ai_model": GEMINI_MODEL,
        "workspace_path": str(BASE_DIR),
        "supported_languages": {
            "project_analyzer": ["Python"],
            "code_debugger": {
                "supported": ["python"],
                "planned": ["c", "cpp", "java", "javascript", "html", "css", "r"],
            },
        },
    }


@app.get("/api/stats")
def stats() -> dict[str, Any]:
    """Return genuine persisted analysis statistics."""
    return jsonable_encoder(get_stats_summary())


@app.get("/api/browse")
def browse_directory(path: str | None = Query(default=None)) -> dict[str, Any]:
    """Safely list subdirectories for the dashboard folder picker."""
    if not path or not path.strip():
        target = BASE_DIR
    else:
        try:
            target = Path(path.strip()).expanduser().resolve()
        except OSError as exc:
            return {"status": "error", "message": f"Invalid path: {exc}", "directories": []}

    if not target.is_dir():
        return {"status": "error", "message": f"Directory not found: {target}", "directories": []}

    directories: list[dict[str, str]] = []
    try:
        for entry in sorted(target.iterdir(), key=lambda p: p.name.lower()):
            if entry.is_dir() and not entry.name.startswith(".") and entry.name not in {"__pycache__", "node_modules", "venv", ".venv"}:
                directories.append({"name": entry.name, "path": str(entry)})
    except PermissionError:
        return {"status": "error", "message": "Permission denied reading directory.", "directories": []}
    except OSError as exc:
        return {"status": "error", "message": str(exc), "directories": []}

    parent = str(target.parent) if target.parent != target else None
    drives: list[str] = []
    if os.name == "nt":
        drives = [f"{letter}:\\" for letter in string.ascii_uppercase if os.path.exists(f"{letter}:\\")]

    return {
        "status": "success",
        "current_path": str(target),
        "parent_path": parent,
        "workspace_path": str(BASE_DIR),
        "drives": drives,
        "directories": directories[:150],
    }


@app.get("/analyze/status/{job_id}")
def analyze_status(job_id: str) -> dict[str, Any]:
    """Return real-time stage execution status for a running or recent job."""
    progress = get_job_progress(job_id)
    if not progress:
        return {"status": "pending", "job_id": job_id, "stages": []}
    return {"status": "ok", **jsonable_encoder(progress)}


@app.post("/analyze")
async def analyze(request: ProjectRequest) -> JSONResponse:
    """Run the multi-agent project analysis workflow with timeout protection."""
    clean_path = (request.project_path or "").strip()
    if not clean_path:
        return JSONResponse(
            status_code=400,
            content={
                "status": "error",
                "message": "Project path cannot be empty.",
                "analysis": {},
                "bug": [],
                "test_cases": [],
                "report": {},
                "ai_review": "",
                "errors": [{"stage": "validation", "error": "Project path cannot be empty."}],
            },
        )

    try:
        result = await asyncio.wait_for(
            run_in_threadpool(run_workflow, clean_path, request.job_id),
            timeout=WORKFLOW_TIMEOUT_SECONDS + 5,
        )
        if not isinstance(result, dict):
            logger.error("run_workflow returned unexpected non-dict type: %s", type(result))
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": "Workflow returned an invalid response structure.",
                    "analysis": {},
                    "bug": [],
                    "test_cases": [],
                    "report": {},
                    "ai_review": "",
                    "errors": [{"stage": "workflow", "error": "Workflow returned None or invalid payload."}],
                },
            )
        return JSONResponse(content=jsonable_encoder(result))
    except asyncio.TimeoutError:
        logger.error("Workflow timed out after %ss for path %s", WORKFLOW_TIMEOUT_SECONDS + 5, clean_path)
        return JSONResponse(
            status_code=504,
            content={
                "status": "error",
                "message": f"Analysis timed out after {WORKFLOW_TIMEOUT_SECONDS + 5} seconds.",
                "analysis": {},
                "bug": [],
                "test_cases": [],
                "report": {},
                "ai_review": "",
                "errors": [{"stage": "workflow", "error": "Execution timeout exceeded."}],
            },
        )
    except Exception as exc:
        logger.exception("Unhandled error in /analyze")
        return JSONResponse(
            status_code=500,
            content={
                "status": "error",
                "message": f"Analysis failed: {exc}",
                "analysis": {},
                "bug": [],
                "test_cases": [],
                "report": {},
                "ai_review": "",
                "errors": [{"stage": "server", "error": str(exc)}],
            },
        )


@app.post("/debug-snippet")
async def debug_snippet(req: DebugRequest) -> JSONResponse:
    """Validate and optionally auto-fix Python snippets without executing code."""
    try:
        debugger_agent = importlib.import_module("agents.debugger_agent")
        result = await run_in_threadpool(debugger_agent.debug_and_fix_code, req.code, req.language)
        if not isinstance(result, dict):
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": "Debugger returned an invalid response."},
            )
        return JSONResponse(content=jsonable_encoder(result))
    except ModuleNotFoundError as exc:
        if "agents.debugger_agent" in str(exc):
            return JSONResponse(
                status_code=500,
                content={
                    "status": "error",
                    "message": "The debugger agent module could not be found in agents/debugger_agent.py.",
                },
            )
        return JSONResponse(status_code=500, content={"status": "error", "message": str(exc)})
    except Exception as exc:
        logger.exception("Error in /debug-snippet")
        return JSONResponse(status_code=500, content={"status": "error", "message": str(exc)})


@app.get("/reports/latest")
def get_latest_json_report() -> JSONResponse:
    """Return latest generated JSON report if available."""
    json_path = REPORTS_DIR / "analysis_report.json"
    if not json_path.is_file():
        raise HTTPException(status_code=404, detail="No JSON report generated yet. Run an analysis first.")
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return JSONResponse(content=data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read report: {exc}") from exc


@app.get("/reports/html", response_class=HTMLResponse)
def get_latest_html_report() -> HTMLResponse:
    """Serve latest generated HTML report for viewing in browser."""
    html_path = REPORTS_DIR / "analysis_report.html"
    if not html_path.is_file():
        return HTMLResponse(
            content="<html><body style='font-family:sans-serif;padding:40px;'><h2>No HTML report generated yet</h2><p>Run a project analysis first to generate the HTML report.</p></body></html>",
            status_code=404,
        )
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/reports/download/{fmt}")
def download_report(fmt: str) -> FileResponse:
    """Download the latest JSON or HTML report."""
    cleaned = fmt.strip().lower()
    if cleaned == "json":
        target = REPORTS_DIR / "analysis_report.json"
        media_type = "application/json"
        filename = "ai_qa_analysis_report.json"
    elif cleaned == "html":
        target = REPORTS_DIR / "analysis_report.html"
        media_type = "text/html"
        filename = "ai_qa_analysis_report.html"
    else:
        raise HTTPException(status_code=400, detail="Unsupported report format. Use 'json' or 'html'.")

    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"Report file '{filename}' has not been generated yet.")

    return FileResponse(path=str(target), media_type=media_type, filename=filename)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("app:app", host="0.0.0.0", port=port)

