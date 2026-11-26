"""AIReviewerAgent: provides structured Gemini-powered code review with safe fallbacks."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from config import GEMINI_API_KEY, GEMINI_MODEL
from utils.gemini_client import generate_gemini_content

logger = logging.getLogger("ai_qa_engineer.ai_reviewer")


class AIReviewerAgent:
    """Integrates with Google Gemini to summarize architecture, maintainability, and action items."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = (api_key if api_key is not None else GEMINI_API_KEY).strip()
        self.model = (model or GEMINI_MODEL).strip() or "gemini-3.8-flash"

    def review_structured(self, context_data: str | dict[str, Any]) -> dict[str, Any]:
        """Generate a structured AI review payload without raising on API failure."""
        if not self.api_key:
            return {
                "status": "unavailable",
                "summary": "AI Review unavailable: GEMINI_API_KEY is not configured in environment variables.",
                "architecture_feedback": "",
                "maintainability": "",
                "security_observations": [],
                "action_items": [],
                "raw_text": "AI Review unavailable: configure GEMINI_API_KEY in .env to enable Gemini code review.",
                "model": self.model,
                "error": "Missing GEMINI_API_KEY",
            }

        context_str = (
            json.dumps(context_data, indent=2, default=str)
            if isinstance(context_data, dict)
            else str(context_data or "")
        ).strip()

        if not context_str:
            return {
                "status": "failed",
                "summary": "No analysis data available to review.",
                "architecture_feedback": "",
                "maintainability": "",
                "security_observations": [],
                "action_items": [],
                "raw_text": "No analysis data available to review.",
                "model": self.model,
                "error": "Empty analysis context",
            }

        # Cap prompt context size so requests stay fast and within limits
        truncated_context = context_str[:12000]

        prompt = f"""You are a Principal Software QA Engineer reviewing static analysis metrics and findings.
Respond ONLY with valid JSON matching this schema (no markdown fences):
{{
  "summary": "2-3 sentence developer-friendly executive summary",
  "architecture_feedback": "concise architectural health observations",
  "maintainability": "concise maintainability and modularity feedback",
  "security_observations": ["potential bug or security pattern observation (clearly framed as AI observation)"],
  "action_items": ["Action 1", "Action 2", "Action 3"]
}}

Analysis Context:
{truncated_context}
"""

        result = generate_gemini_content(
            prompt,
            api_key=self.api_key,
            model=self.model,
            temperature=0.2,
            max_output_tokens=1200,
        )

        if not result["ok"]:
            err = result.get("error") or "Gemini request failed."
            return {
                "status": result["status"],
                "summary": f"AI Review {result['status']}: {err}",
                "architecture_feedback": "",
                "maintainability": "",
                "security_observations": [],
                "action_items": [],
                "raw_text": f"AI Review {result['status']}: {err}",
                "model": result["model"],
                "error": err,
            }

        raw_text = result["text"]
        parsed = self._parse_review_json(raw_text)
        if parsed:
            action_items = [str(item) for item in (parsed.get("action_items") or [])[:5]]
            sec_obs = [str(item) for item in (parsed.get("security_observations") or [])[:6]]
            formatted = self._format_text_summary(
                summary=str(parsed.get("summary", "")),
                architecture=str(parsed.get("architecture_feedback", "")),
                maintainability=str(parsed.get("maintainability", "")),
                security_observations=sec_obs,
                action_items=action_items,
            )
            return {
                "status": "completed",
                "summary": str(parsed.get("summary", "")),
                "architecture_feedback": str(parsed.get("architecture_feedback", "")),
                "maintainability": str(parsed.get("maintainability", "")),
                "security_observations": sec_obs,
                "action_items": action_items,
                "raw_text": formatted,
                "model": result["model"],
                "error": None,
            }

        return {
            "status": "completed",
            "summary": raw_text.splitlines()[0] if raw_text else "AI Review completed.",
            "architecture_feedback": raw_text,
            "maintainability": "",
            "security_observations": [],
            "action_items": [],
            "raw_text": raw_text,
            "model": result["model"],
            "error": None,
        }

    def review(self, context_data: str | dict[str, Any]) -> str:
        """Return human-readable review string for backward compatibility."""
        structured = self.review_structured(context_data)
        return str(structured.get("raw_text") or structured.get("summary") or "")

    @staticmethod
    def _parse_review_json(text: str) -> dict[str, Any] | None:
        cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else None
        except ValueError:
            return None

    @staticmethod
    def _format_text_summary(
        *,
        summary: str,
        architecture: str,
        maintainability: str,
        security_observations: list[str],
        action_items: list[str],
    ) -> str:
        lines = []
        if summary:
            lines.append(f"Summary:\n{summary}")
        if architecture:
            lines.append(f"\nArchitecture Health:\n{architecture}")
        if maintainability:
            lines.append(f"\nMaintainability:\n{maintainability}")
        if security_observations:
            lines.append("\nPotential Bug & Security Observations (AI-Suggested):")
            lines.extend(f"- {obs}" for obs in security_observations)
        if action_items:
            lines.append("\nTop Recommended Action Items:")
            lines.extend(f"{idx}. {act}" for idx, act in enumerate(action_items, start=1))
        return "\n".join(lines).strip()
