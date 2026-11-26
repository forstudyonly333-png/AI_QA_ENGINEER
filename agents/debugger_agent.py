"""DebuggerAgent: AST-based Python snippet validator with optional Gemini auto-fix."""

from __future__ import annotations

import ast
import difflib
import json
import re
from typing import Any

from config import GEMINI_API_KEY, GEMINI_MODEL
from utils.gemini_client import generate_gemini_content


def clean_llm_code(code_str: str) -> str:
    """Strip markdown code fences from LLM output."""
    if not code_str:
        return ""
    cleaned = code_str.strip()
    cleaned = re.sub(r"^```(?:json|python)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def validate_python_code(code: str) -> tuple[bool, str | None]:
    """Validate Python syntax safely via ast.parse without executing code."""
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as exc:
        location = f"Line {exc.lineno}: " if exc.lineno else ""
        return False, f"{location}{exc.msg}"
    except Exception as exc:
        return False, str(exc)


def generate_diff(old_code: str, new_code: str) -> str:
    """Return unified diff between original and fixed code."""
    return "".join(
        difflib.unified_diff(
            old_code.splitlines(keepends=True),
            new_code.splitlines(keepends=True),
            fromfile="Original",
            tofile="Fixed",
            n=2,
        )
    )


def debug_and_fix_code(raw_code: str, language: str = "python") -> dict[str, Any]:
    """Validate Python code via AST and optionally generate an AST-validated AI fix."""
    lang = (language or "python").strip().lower()
    if lang != "python":
        return {
            "status": "unsupported",
            "language": lang,
            "has_error": False,
            "error_type": None,
            "error_message": f"Language '{lang}' analyzer is planned and not yet implemented.",
            "explanation": f"Only Python AST debugging is currently supported. '{lang}' is on the roadmap.",
            "fixed_code": raw_code,
            "validation_status": False,
            "validation_error": "Unsupported language",
            "diff": "",
            "ai_status": "unavailable",
        }

    if not raw_code or not raw_code.strip():
        return {
            "status": "error",
            "language": "python",
            "has_error": True,
            "error_type": "ValidationError",
            "error_message": "Code input cannot be empty.",
            "explanation": "Please provide a Python code snippet to analyze.",
            "fixed_code": "",
            "validation_status": False,
            "validation_error": "Empty code input",
            "diff": "",
            "ai_status": "unavailable",
        }

    is_valid, syntax_error = validate_python_code(raw_code)
    if is_valid:
        return {
            "status": "success",
            "language": "python",
            "has_error": False,
            "error_type": None,
            "error_message": None,
            "explanation": "Code passed Python AST validation cleanly with zero syntax errors.",
            "fixed_code": raw_code,
            "validation_status": True,
            "validation_error": None,
            "diff": "",
            "ai_status": "not_needed",
        }

    if not GEMINI_API_KEY:
        return {
            "status": "partial",
            "language": "python",
            "has_error": True,
            "error_type": "SyntaxError",
            "error_message": syntax_error,
            "explanation": f"Python AST detected a syntax error ({syntax_error}). Configure GEMINI_API_KEY in .env to enable AI auto-fix suggestions.",
            "fixed_code": raw_code,
            "validation_status": False,
            "validation_error": syntax_error,
            "diff": "",
            "ai_status": "unavailable",
        }

    prompt = f"""You are an expert Python QA and Auto-Fix engine.
Fix the syntax and indentation errors in this Python code so it parses cleanly with ast.parse().
Respond ONLY with a valid JSON object matching this schema:
{{
  "explanation": "concise explanation of what was fixed",
  "fixed_code": "pure corrected python code without markdown fences"
}}

Original Code:
```python
{raw_code}
```
"""

    fixed_code = raw_code
    explanation = f"Syntax error detected: {syntax_error}"
    ai_result = generate_gemini_content(
        prompt,
        api_key=GEMINI_API_KEY,
        model=GEMINI_MODEL,
        temperature=0.1,
        max_output_tokens=1200,
    )

    ai_status = ai_result["status"]
    if ai_result["ok"] and ai_result["text"]:
        cleaned = clean_llm_code(ai_result["text"])
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                data = json.loads(match.group(0))
                candidate = clean_llm_code(str(data.get("fixed_code", raw_code)))
                if candidate:
                    fixed_code = candidate
                explanation = str(data.get("explanation") or "Syntax error resolved.")
            except ValueError:
                explanation = f"AI returned non-JSON fix output. Original error: {syntax_error}"
                ai_status = "failed"
    else:
        explanation = f"AI fix attempt {ai_status} ({ai_result.get('error')}). Original error: {syntax_error}"

    valid_fix, fix_err = validate_python_code(fixed_code)
    diff = generate_diff(raw_code, fixed_code)

    return {
        "status": "success" if valid_fix else "partial",
        "language": "python",
        "has_error": True,
        "error_type": "SyntaxError",
        "error_message": syntax_error,
        "explanation": explanation,
        "fixed_code": fixed_code,
        "validation_status": valid_fix,
        "validation_error": fix_err,
        "diff": diff,
        "ai_status": ai_status,
    }
