"""CodeLoaderAgent: scans a Python project directory safely without redundant walks."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from config import MAX_FILES_TO_ANALYZE

logger = logging.getLogger("ai_qa_engineer.code_loader")


class CodeLoaderAgent:
    """Discovers Python source files and extracts project metadata."""

    IGNORE_FOLDERS = {
        ".git",
        ".hg",
        ".svn",
        "venv",
        ".venv",
        "env",
        ".env",
        "__pycache__",
        "node_modules",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".tox",
        ".eggs",
    }

    FRAMEWORK_MAP = {
        "fastapi": "FastAPI",
        "flask": "Flask",
        "django": "Django",
        "streamlit": "Streamlit",
        "starlette": "Starlette",
        "tornado": "Tornado",
        "aiohttp": "AIOHTTP",
    }

    def __init__(self, project_path: str, max_files: int = MAX_FILES_TO_ANALYZE) -> None:
        self.project_path = project_path
        self.max_files = max_files
        self.errors: list[dict[str, str]] = []
        self._python_files: list[str] | None = None
        self._requirements: list[str] | None = None
        self._truncated = False

    def get_python_files(self) -> list[str]:
        """Walk project directory once and collect Python files while skipping ignored dirs."""
        if self._python_files is not None:
            return self._python_files

        python_files: list[str] = []
        if not os.path.isdir(self.project_path):
            self.errors.append({
                "stage": "code_loader",
                "file": self.project_path,
                "error": "Project path is not a valid directory.",
            })
            self._python_files = []
            return self._python_files

        def _on_walk_error(exc: OSError) -> None:
            self.errors.append({
                "stage": "code_loader",
                "file": getattr(exc, "filename", None) or self.project_path,
                "error": f"Directory access error: {exc}",
            })

        for root, dirs, files in os.walk(self.project_path, onerror=_on_walk_error):
            dirs[:] = sorted(d for d in dirs if d not in self.IGNORE_FOLDERS and not d.startswith("."))
            for file_name in sorted(files):
                if file_name.endswith(".py"):
                    full_path = os.path.join(root, file_name)
                    python_files.append(full_path)
                    if len(python_files) >= self.max_files:
                        self._truncated = True
                        self.errors.append({
                            "stage": "code_loader",
                            "file": self.project_path,
                            "error": f"File scan capped at {self.max_files} Python files to prevent timeout.",
                        })
                        self._python_files = python_files
                        return self._python_files

        self._python_files = python_files
        return self._python_files

    def get_requirements(self) -> list[str]:
        """Read all non-empty, non-comment lines from requirements.txt."""
        if self._requirements is not None:
            return self._requirements

        requirements: list[str] = []
        req_file = os.path.join(self.project_path, "requirements.txt")
        if os.path.isfile(req_file):
            try:
                with open(req_file, "r", encoding="utf-8", errors="replace") as file:
                    for raw_line in file:
                        line = raw_line.strip()
                        if line and not line.startswith("#"):
                            requirements.append(line)
            except OSError as exc:
                self.errors.append({
                    "stage": "code_loader",
                    "file": req_file,
                    "error": f"Could not read requirements.txt: {exc}",
                })

        self._requirements = requirements
        return self._requirements

    def get_readme(self) -> str:
        """Read README.md safely with encoding fallback."""
        readme_file = os.path.join(self.project_path, "README.md")
        if not os.path.isfile(readme_file):
            return "README not found."
        try:
            with open(readme_file, "r", encoding="utf-8", errors="replace") as file:
                content = file.read(12000)
                return content if content.strip() else "README.md is empty."
        except OSError as exc:
            self.errors.append({
                "stage": "code_loader",
                "file": readme_file,
                "error": f"Could not read README.md: {exc}",
            })
            return "README could not be read."

    def detect_framework(self) -> str:
        """Identify primary Python web/app framework from requirements."""
        requirements = self.get_requirements()
        package_names: set[str] = set()
        for req in requirements:
            pkg = re.split(r"[=<>!~;\[\s]", req.strip().lower(), maxsplit=1)[0]
            if pkg:
                package_names.add(pkg)

        for key, label in self.FRAMEWORK_MAP.items():
            if key in package_names:
                return label
        return "None"

    def load_project(self) -> dict[str, Any]:
        """Collect project metadata, Python file list, requirements, and README."""
        python_files = self.get_python_files()
        requirements = self.get_requirements()
        framework = self.detect_framework()
        readme = self.get_readme()
        project_name = os.path.basename(os.path.abspath(self.project_path)) or self.project_path

        logger.info(
            "Loaded project '%s': %d Python files, framework=%s",
            project_name,
            len(python_files),
            framework,
        )

        return {
            "project_name": project_name,
            "project_path": os.path.abspath(self.project_path),
            "language": "Python",
            "framework": framework,
            "python_files": python_files,
            "requirements": requirements,
            "readme": readme,
            "total_files": len(python_files),
            "truncated": self._truncated,
            "errors": list(self.errors),
        }
