"""CodeAnalyzerAgent: single-pass AST & static metrics analyzer with graceful error handling."""

from __future__ import annotations

import ast
import logging
import os
from typing import Any

from config import LONG_FUNCTION_THRESHOLD

logger = logging.getLogger("ai_qa_engineer.code_analyzer")


class CodeAnalyzerAgent:
    """Analyzes Python source files once using AST and caches parsed results."""

    def __init__(self, project_data: dict[str, Any]) -> None:
        self.project_data = project_data or {}
        self.analysis_errors: list[dict[str, Any]] = []
        self._recorded_error_keys: set[tuple[str, str, int | None]] = set()
        self._file_cache: dict[str, dict[str, Any]] = {}
        self._analyzed = False

    def _add_error(self, file_path: str, error_type: str, message: str, line: int | None = None) -> None:
        key = (file_path, error_type, line)
        if key in self._recorded_error_keys:
            return
        self._recorded_error_keys.add(key)
        entry: dict[str, Any] = {
            "file": file_path,
            "error": error_type,
            "message": message,
        }
        if line is not None:
            entry["line"] = line
        self.analysis_errors.append(entry)

    def read_python_files(self, file_path: str) -> str | None:
        """Read a Python source file safely with encoding fallbacks."""
        if file_path in self._file_cache:
            return self._file_cache[file_path].get("code")

        for encoding in ("utf-8", "utf-8-sig", "latin-1"):
            try:
                with open(file_path, "r", encoding=encoding) as file:
                    return file.read()
            except UnicodeDecodeError:
                continue
            except OSError as exc:
                self._add_error(file_path, "FileReadError", f"Could not read file: {exc}")
                return None

        self._add_error(file_path, "EncodingError", "Unable to decode file with utf-8/latin-1.")
        return None

    def parse_code(self, code: str, file_path: str) -> ast.AST | None:
        """Parse Python code into an AST, recording syntax errors without crashing."""
        try:
            return ast.parse(code, filename=file_path)
        except SyntaxError as exc:
            self._add_error(
                file_path,
                "SyntaxError",
                exc.msg or "Invalid Python syntax",
                line=exc.lineno,
            )
            return None
        except Exception as exc:
            self._add_error(file_path, "ParseError", str(exc))
            return None

    def _ensure_parsed(self) -> None:
        if self._analyzed:
            return
        python_files = self.project_data.get("python_files", [])
        for file_path in python_files:
            code = self.read_python_files(file_path)
            if code is None:
                self._file_cache[file_path] = {
                    "code": None,
                    "lines": [],
                    "tree": None,
                    "status": "read_error",
                }
                continue
            tree = self.parse_code(code, file_path)
            self._file_cache[file_path] = {
                "code": code,
                "lines": code.splitlines(),
                "tree": tree,
                "status": "parsed" if tree is not None else "syntax_error",
            }
        self._analyzed = True

    def get_parsed_cache(self) -> dict[str, dict[str, Any]]:
        """Expose cached file contents and ASTs for downstream agents."""
        self._ensure_parsed()
        return self._file_cache

    def analyze(self) -> dict[str, Any]:
        """Run full single-pass AST analysis across all discovered Python files."""
        self._ensure_parsed()

        total_lines = 0
        total_comments = 0
        total_blank_lines = 0
        total_functions = 0
        total_classes = 0
        total_imports = 0
        parsed_files = 0
        failed_files = 0

        functions: list[dict[str, Any]] = []
        classes: list[dict[str, Any]] = []
        imports: list[dict[str, Any]] = []
        large_functions: list[dict[str, Any]] = []
        files_summary: list[dict[str, Any]] = []

        for file_path, cached in self._file_cache.items():
            code = cached["code"]
            lines = cached["lines"]
            tree = cached["tree"]
            rel_name = os.path.basename(file_path)

            if code is None:
                failed_files += 1
                files_summary.append({
                    "file": file_path,
                    "name": rel_name,
                    "lines": 0,
                    "functions": 0,
                    "classes": 0,
                    "imports": 0,
                    "status": "read_error",
                })
                continue

            file_line_count = len(lines)
            total_lines += file_line_count
            for line in lines:
                stripped = line.strip()
                if stripped == "":
                    total_blank_lines += 1
                elif stripped.startswith("#"):
                    total_comments += 1

            if tree is None:
                failed_files += 1
                files_summary.append({
                    "file": file_path,
                    "name": rel_name,
                    "lines": file_line_count,
                    "functions": 0,
                    "classes": 0,
                    "imports": 0,
                    "status": "syntax_error",
                })
                continue

            parsed_files += 1
            file_funcs = 0
            file_classes = 0
            file_imports = 0

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    total_functions += 1
                    file_funcs += 1
                    params = [arg.arg for arg in node.args.args]
                    end_line = getattr(node, "end_lineno", node.lineno) or node.lineno
                    func_lines = max(1, end_line - node.lineno + 1)

                    functions.append({
                        "name": node.name,
                        "parameters": params,
                        "file": file_path,
                        "file_name": rel_name,
                        "line": node.lineno,
                        "end_line": end_line,
                        "lines": func_lines,
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                        "has_docstring": ast.get_docstring(node) is not None,
                    })

                    if func_lines > LONG_FUNCTION_THRESHOLD:
                        large_functions.append({
                            "name": node.name,
                            "file": file_path,
                            "file_name": rel_name,
                            "start_line": node.lineno,
                            "end_line": end_line,
                            "lines": func_lines,
                        })

                elif isinstance(node, ast.ClassDef):
                    total_classes += 1
                    file_classes += 1
                    end_line = getattr(node, "end_lineno", node.lineno) or node.lineno
                    methods = [
                        n.name
                        for n in node.body
                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                    ]
                    bases = []
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            bases.append(base.id)
                        elif isinstance(base, ast.Attribute):
                            bases.append(base.attr)
                    classes.append({
                        "name": node.name,
                        "file": file_path,
                        "file_name": rel_name,
                        "line": node.lineno,
                        "end_line": end_line,
                        "methods": methods,
                        "method_count": len(methods),
                        "bases": bases,
                    })

                elif isinstance(node, ast.Import):
                    total_imports += 1
                    file_imports += 1
                    names = [alias.name for alias in node.names]
                    imports.append({
                        "module": ", ".join(names),
                        "names": names,
                        "file": file_path,
                        "file_name": rel_name,
                        "line": node.lineno,
                        "type": "import",
                    })

                elif isinstance(node, ast.ImportFrom):
                    total_imports += 1
                    file_imports += 1
                    module_name = node.module or ("." * (node.level or 1))
                    names = [alias.name for alias in node.names]
                    imports.append({
                        "module": module_name,
                        "names": names,
                        "file": file_path,
                        "file_name": rel_name,
                        "line": node.lineno,
                        "type": "from_import",
                    })

            files_summary.append({
                "file": file_path,
                "name": rel_name,
                "lines": file_line_count,
                "functions": file_funcs,
                "classes": file_classes,
                "imports": file_imports,
                "status": "parsed",
            })

        total_files = len(self.project_data.get("python_files", []))
        status = "Success" if failed_files == 0 else "Partial"
        message = (
            "Code Analyzer completed successfully."
            if failed_files == 0
            else f"Code Analyzer completed with {failed_files} file error(s)."
        )

        logger.info(
            "Analyzed %d files (%d parsed, %d failed): %d lines, %d functions, %d classes",
            total_files,
            parsed_files,
            failed_files,
            total_lines,
            total_functions,
            total_classes,
        )

        return {
            "status": status,
            "message": message,
            "project": self.project_data,
            "total_files": total_files,
            "parsed_files": parsed_files,
            "failed_files": failed_files,
            "total_lines": total_lines,
            "total_functions": total_functions,
            "total_classes": total_classes,
            "total_imports": total_imports,
            "total_comments": total_comments,
            "total_blank_lines": total_blank_lines,
            "functions": functions,
            "classes": classes,
            "imports": imports,
            "large_functions": large_functions,
            "files_summary": files_summary,
            "analysis_errors": self.analysis_errors,
        }

    # Backward-compatible helper methods backed by cached analysis
    def count_lines(self) -> int:
        return self.analyze()["total_lines"]

    def count_functions(self) -> int:
        return self.analyze()["total_functions"]

    def count_classes(self) -> int:
        return self.analyze()["total_classes"]

    def count_imports(self) -> int:
        return self.analyze()["total_imports"]

    def count_comments(self) -> int:
        return self.analyze()["total_comments"]

    def count_blank_lines(self) -> int:
        return self.analyze()["total_blank_lines"]

    def detect_large_functions(self) -> list[dict[str, Any]]:
        return self.analyze()["large_functions"]

    def get_functions(self) -> list[dict[str, Any]]:
        return self.analyze()["functions"]
