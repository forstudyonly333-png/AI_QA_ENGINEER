"""BugAnalyzerAgent: detects code quality issues and potential bugs without crashing on syntax errors."""

from __future__ import annotations

import ast
import logging
import os
import re
from typing import Any

from config import LONG_FUNCTION_THRESHOLD

logger = logging.getLogger("ai_qa_engineer.bug_analyzer")


class BugAnalyzerAgent:
    """Inspects Python files for code-quality smells, security risks, and structural issues."""

    SECRET_KEYWORDS = ("password", "passwd", "secret", "api_key", "apikey", "token")
    SAFE_PLACEHOLDERS = {"", "none", "null", "changeme", "your_api_key", "replace_me", "<redacted>"}

    def __init__(
        self,
        project_data: dict[str, Any],
        parsed_cache: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.project_data = project_data or {}
        self._parsed_cache = parsed_cache
        self.errors: list[dict[str, Any]] = []

    def _get_files(self) -> dict[str, dict[str, Any]]:
        if self._parsed_cache is not None:
            return self._parsed_cache

        cache: dict[str, dict[str, Any]] = {}
        for file_path in self.project_data.get("python_files", []):
            code: str | None = None
            for encoding in ("utf-8", "utf-8-sig", "latin-1"):
                try:
                    with open(file_path, "r", encoding=encoding) as file:
                        code = file.read()
                    break
                except UnicodeDecodeError:
                    continue
                except OSError as exc:
                    self.errors.append({"file": file_path, "error": f"File read error: {exc}"})
                    break

            if code is None:
                cache[file_path] = {"code": None, "lines": [], "tree": None, "status": "read_error"}
                continue

            tree: ast.AST | None = None
            try:
                tree = ast.parse(code, filename=file_path)
            except SyntaxError as exc:
                self.errors.append({
                    "file": file_path,
                    "line": exc.lineno,
                    "error": f"SyntaxError: {exc.msg}",
                })
            except Exception as exc:
                self.errors.append({"file": file_path, "error": str(exc)})

            cache[file_path] = {
                "code": code,
                "lines": code.splitlines(),
                "tree": tree,
                "status": "parsed" if tree is not None else "syntax_error",
            }

        self._parsed_cache = cache
        return self._parsed_cache

    def analyze(self) -> list[dict[str, Any]]:
        """Run all bug & code-quality checks across cached files."""
        files = self._get_files()
        bugs: list[dict[str, Any]] = []

        for file_path, entry in files.items():
            code = entry.get("code")
            lines = entry.get("lines") or []
            tree = entry.get("tree")
            if code is None:
                continue

            file_name = os.path.basename(file_path)

            # 1. TODO / FIXME comments (line-level)
            for line_no, line in enumerate(lines, start=1):
                if re.search(r"#.*\b(TODO|FIXME)\b", line):
                    bugs.append({
                        "file": file_path,
                        "file_name": file_name,
                        "line": line_no,
                        "severity": "info",
                        "category": "maintenance",
                        "bug": "TODO/FIXME comment found",
                    })

            # 2. Hardcoded secrets (AST-based when parsed, conservative regex fallback otherwise)
            if tree is not None:
                bugs.extend(self._check_secrets_ast(tree, file_path, file_name))
            else:
                bugs.extend(self._check_secrets_text(lines, file_path, file_name))

            if tree is None:
                continue

            # 3-6. AST checks (bare except, print calls, long functions, missing docstrings)
            for node in ast.walk(tree):
                if isinstance(node, ast.Try):
                    for handler in node.handlers:
                        if handler.type is None:
                            bugs.append({
                                "file": file_path,
                                "file_name": file_name,
                                "line": handler.lineno,
                                "severity": "critical",
                                "category": "exception_handling",
                                "bug": "Bare except statement found",
                            })

                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name) and node.func.id == "print":
                        bugs.append({
                            "file": file_path,
                            "file_name": file_name,
                            "line": node.lineno,
                            "severity": "warning",
                            "category": "code_hygiene",
                            "bug": "Print statement found (consider logging)",
                        })

                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    end_line = getattr(node, "end_lineno", node.lineno) or node.lineno
                    func_length = end_line - node.lineno + 1
                    if func_length > LONG_FUNCTION_THRESHOLD:
                        bugs.append({
                            "file": file_path,
                            "file_name": file_name,
                            "function": node.name,
                            "line": node.lineno,
                            "severity": "warning",
                            "category": "complexity",
                            "bug": f"Function too long ({func_length} lines, threshold {LONG_FUNCTION_THRESHOLD})",
                        })

                    if ast.get_docstring(node) is None:
                        bugs.append({
                            "file": file_path,
                            "file_name": file_name,
                            "function": node.name,
                            "line": node.lineno,
                            "severity": "info",
                            "category": "documentation",
                            "bug": "Missing function docstring",
                        })

        logger.info("BugAnalyzer finished: %d finding(s), %d file error(s)", len(bugs), len(self.errors))
        return bugs

    def _is_secret_identifier(self, name: str) -> str | None:
        lower = name.lower()
        for kw in self.SECRET_KEYWORDS:
            if kw in lower:
                return kw
        return None

    def _is_nonempty_literal_secret(self, value_node: ast.AST | None) -> bool:
        if isinstance(value_node, ast.Constant) and isinstance(value_node.value, str):
            val = value_node.value.strip()
            return bool(val) and val.lower() not in self.SAFE_PLACEHOLDERS
        return False

    def _check_secrets_ast(self, tree: ast.AST, file_path: str, file_name: str) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            targets: list[ast.AST] = []
            value_node: ast.AST | None = None
            if isinstance(node, ast.Assign):
                targets = node.targets
                value_node = node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets = [node.target]
                value_node = node.value
            else:
                continue

            if not self._is_nonempty_literal_secret(value_node):
                continue

            for target in targets:
                target_name = ""
                if isinstance(target, ast.Name):
                    target_name = target.id
                elif isinstance(target, ast.Attribute):
                    target_name = target.attr
                kw = self._is_secret_identifier(target_name) if target_name else None
                if kw:
                    findings.append({
                        "file": file_path,
                        "file_name": file_name,
                        "line": node.lineno,
                        "severity": "critical",
                        "category": "security",
                        "bug": f"Possible hardcoded secret assigned to '{target_name}'",
                    })
        return findings

    def _check_secrets_text(self, lines: list[str], file_path: str, file_name: str) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        pattern = re.compile(
            r"""\b([A-Za-z0-9_]*(?:password|passwd|secret|api_key|apikey|token)[A-Za-z0-9_]*)\s*=\s*(['"])([^'"]+)\2""",
            re.IGNORECASE,
        )
        for line_no, line in enumerate(lines, start=1):
            match = pattern.search(line)
            if match:
                val = match.group(3).strip().lower()
                if val not in self.SAFE_PLACEHOLDERS:
                    findings.append({
                        "file": file_path,
                        "file_name": file_name,
                        "line": line_no,
                        "severity": "critical",
                        "category": "security",
                        "bug": f"Possible hardcoded secret assigned to '{match.group(1)}'",
                    })
        return findings

    # Preserve method names for direct callers
    def check_todo_comments(self) -> list[dict[str, Any]]:
        return [b for b in self.analyze() if b.get("category") == "maintenance"]

    def check_hardcoded_secrets(self) -> list[dict[str, Any]]:
        return [b for b in self.analyze() if b.get("category") == "security"]

    def check_bare_except(self) -> list[dict[str, Any]]:
        return [b for b in self.analyze() if b.get("category") == "exception_handling"]

    def check_print_statements(self) -> list[dict[str, Any]]:
        return [b for b in self.analyze() if b.get("category") == "code_hygiene"]

    def check_long_functions(self) -> list[dict[str, Any]]:
        return [b for b in self.analyze() if b.get("category") == "complexity"]

    def check_missing_docstrings(self) -> list[dict[str, Any]]:
        return [b for b in self.analyze() if b.get("category") == "documentation"]
