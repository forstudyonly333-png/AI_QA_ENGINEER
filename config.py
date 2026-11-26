"""Application configuration for AI QA Engineer."""

import logging
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _get_int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except ValueError:
        return default


# Security: never hardcode API keys or secrets in source files.
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip() or "gemini-3.8-flash"

GEMINI_TIMEOUT_SECONDS: int = _get_int_env("GEMINI_TIMEOUT_SECONDS", 25)
WORKFLOW_TIMEOUT_SECONDS: int = _get_int_env("WORKFLOW_TIMEOUT_SECONDS", 90)
MAX_FILES_TO_ANALYZE: int = _get_int_env("MAX_FILES_TO_ANALYZE", 500)
LONG_FUNCTION_THRESHOLD: int = _get_int_env("LONG_FUNCTION_THRESHOLD", 50)

REPORTS_DIR: Path = BASE_DIR / "reports"
FRONTEND_DIR: Path = BASE_DIR / "frontend"
HISTORY_FILE: Path = REPORTS_DIR / "analysis_history.json"


def configure_logging() -> logging.Logger:
    """Configure application-wide structured logging without leaking secrets."""
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    return logging.getLogger("ai_qa_engineer")


logger = configure_logging()
