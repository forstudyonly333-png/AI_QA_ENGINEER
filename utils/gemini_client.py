"""Shared Gemini API client using official REST endpoint with timeouts and safe error handling."""

from __future__ import annotations

import logging
import os
import ssl
import time
from typing import Any

import certifi
import requests
from requests.adapters import HTTPAdapter

from config import GEMINI_API_KEY, GEMINI_MODEL, GEMINI_TIMEOUT_SECONDS

logger = logging.getLogger("ai_qa_engineer.gemini")

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def _build_verified_ssl_context() -> ssl.SSLContext:
    """Create a strict TLS context combining certifi with Windows OS trusted roots."""
    ctx = ssl.create_default_context(cafile=certifi.where())
    if os.name == "nt" and hasattr(ssl, "enum_certificates"):
        pem_certs: list[str] = []
        for store in ("ROOT", "CA"):
            try:
                for cert_bytes, encoding, _trust in ssl.enum_certificates(store):
                    if encoding == "x509_asn":
                        pem_certs.append(ssl.DER_cert_to_PEM_cert(cert_bytes))
            except Exception:
                continue
        if pem_certs:
            try:
                ctx.load_verify_locations(cadata="\n".join(pem_certs))
            except Exception as exc:
                logger.debug("Could not load Windows OS certificates: %s", exc)
    return ctx


class _VerifiedTLSAdapter(HTTPAdapter):
    def __init__(self, ssl_context: ssl.SSLContext) -> None:
        self._ssl_context = ssl_context
        super().__init__()

    def init_poolmanager(self, *args: Any, **kwargs: Any) -> Any:
        kwargs["ssl_context"] = self._ssl_context
        return super().init_poolmanager(*args, **kwargs)


_SESSION: requests.Session | None = None


def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        session = requests.Session()
        session.mount("https://", _VerifiedTLSAdapter(_build_verified_ssl_context()))
        _SESSION = session
    return _SESSION


def _normalize_model_name(model_name: str) -> str:
    cleaned = (model_name or GEMINI_MODEL).strip()
    if cleaned.startswith("models/"):
        cleaned = cleaned[len("models/") :]
    return cleaned or "gemini-3.8-flash"


def _sanitize_error(message: str, api_key: str) -> str:
    if not message:
        return "Unknown Gemini API error."
    if api_key and api_key in message:
        return message.replace(api_key, "[REDACTED]")
    return message


def generate_gemini_content(
    prompt: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    timeout_seconds: int | None = None,
    temperature: float = 0.2,
    max_output_tokens: int = 1500,
) -> dict[str, Any]:
    """Call Gemini generateContent without slow model discovery or hardcoded keys."""
    resolved_key = (api_key if api_key is not None else GEMINI_API_KEY).strip()
    resolved_model = _normalize_model_name(model or GEMINI_MODEL)
    timeout = timeout_seconds or GEMINI_TIMEOUT_SECONDS

    if not resolved_key:
        return {
            "ok": False,
            "status": "unavailable",
            "text": "",
            "model": resolved_model,
            "error": "GEMINI_API_KEY is not configured in environment variables.",
        }

    url = f"{GEMINI_API_BASE}/{resolved_model}:generateContent"
    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": resolved_key,
    }
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }

    response = None
    for attempt in range(2):
        try:
            response = _get_session().post(
                url,
                headers=headers,
                json=payload,
                timeout=(5, timeout),
            )
            if response.status_code == 503 and attempt == 0:
                time.sleep(1.0)
                continue
            break
        except requests.Timeout:
            logger.warning("Gemini API request timed out after %ss (model=%s)", timeout, resolved_model)
            return {
                "ok": False,
                "status": "failed",
                "text": "",
                "model": resolved_model,
                "error": f"Gemini API request timed out after {timeout} seconds.",
            }
        except requests.RequestException as exc:
            safe_err = _sanitize_error(str(exc), resolved_key)
            logger.warning("Gemini API network error (model=%s): %s", resolved_model, safe_err)
            return {
                "ok": False,
                "status": "failed",
                "text": "",
                "model": resolved_model,
                "error": f"Network error reaching Gemini API: {safe_err}",
            }

    assert response is not None

    if response.status_code != 200:
        err_detail = f"HTTP {response.status_code}"
        try:
            err_json = response.json()
            err_msg = err_json.get("error", {}).get("message")
            if err_msg:
                err_detail = f"{err_detail}: {err_msg}"
        except ValueError:
            pass
        err_detail = _sanitize_error(err_detail, resolved_key)
        logger.warning("Gemini API returned error (%s) for model=%s", err_detail, resolved_model)
        return {
            "ok": False,
            "status": "failed",
            "text": "",
            "model": resolved_model,
            "error": err_detail,
        }

    try:
        data = response.json()
    except ValueError:
        return {
            "ok": False,
            "status": "failed",
            "text": "",
            "model": resolved_model,
            "error": "Invalid JSON returned by Gemini API.",
        }

    candidates = data.get("candidates") or []
    parts_text: list[str] = []
    if candidates and isinstance(candidates, list):
        content = candidates[0].get("content") or {}
        for part in content.get("parts") or []:
            text_piece = part.get("text")
            if text_piece:
                parts_text.append(text_piece)

    final_text = "\n".join(parts_text).strip()
    if not final_text:
        return {
            "ok": False,
            "status": "failed",
            "text": "",
            "model": resolved_model,
            "error": "Gemini returned an empty response.",
        }

    return {
        "ok": True,
        "status": "completed",
        "text": final_text,
        "model": resolved_model,
        "error": None,
    }
