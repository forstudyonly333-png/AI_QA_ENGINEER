"""TestGeneratorAgent: generates test-case suggestions from AST function metadata."""

from __future__ import annotations

import logging
from typing import Any

from utils.qa_rules import ADD_RULES, DIVIDE_RULES, LOGIN_RULES, REGISTER_RULES

logger = logging.getLogger("ai_qa_engineer.test_generator")


class TestGeneratorAgent:
    """Produces structured test-case suggestions (does not execute tests)."""

    __test__ = False

    RULE_MATCHERS = (
        ("add", "ADD_RULES", ADD_RULES),
        ("divide", "DIVIDE_RULES", DIVIDE_RULES),
        ("login", "LOGIN_RULES", LOGIN_RULES),
        ("register", "REGISTER_RULES", REGISTER_RULES),
    )

    def __init__(self, analysis: dict[str, Any]) -> None:
        self.analysis = analysis if isinstance(analysis, dict) else {}

    def generate(self) -> list[dict[str, Any]]:
        """Generate suggested test cases for discovered functions."""
        functions = self.analysis.get("functions", [])
        if not isinstance(functions, list):
            return []

        test_cases: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str, int]] = set()

        for func in functions:
            if not isinstance(func, dict):
                continue
            raw_name = func.get("name", "unknown")
            func_lower = raw_name.lower()
            params = func.get("parameters") or []
            file_path = func.get("file", "")
            file_name = func.get("file_name") or file_path
            line = int(func.get("line") or 0)

            key = (file_path, raw_name, line)
            if key in seen_keys:
                continue
            seen_keys.add(key)

            # Skip private/dunder helpers unless they match explicit QA rules
            matched_rules_key = None
            matched_rules: list[str] = []
            for keyword, rules_label, rules_list in self.RULE_MATCHERS:
                if keyword in func_lower:
                    matched_rules_key = rules_label
                    matched_rules = list(rules_list)
                    break

            if raw_name.startswith("_") and matched_rules_key is None:
                continue

            scenarios = self._build_scenarios(raw_name, params, matched_rules)
            arg_placeholders = ", ".join(
                "None" if p in ("self", "cls") else f"sample_{p}"
                for p in params
                if p not in ("self", "cls")
            )
            sample_pytest = (
                f"def test_{raw_name}_basic():\n"
                f"    # Suggested test skeleton (not executed automatically)\n"
                f"    result = {raw_name}({arg_placeholders})\n"
                f"    assert result is not None"
            )

            entry: dict[str, Any] = {
                "function": raw_name,
                "file": file_name,
                "line": line,
                "parameters": params,
                "test_scenarios": scenarios,
                "sample_pytest": sample_pytest,
                "executed": False,
                "note": "Suggested test case only — not executed by the static analyzer.",
            }
            if matched_rules_key:
                entry[matched_rules_key] = matched_rules

            test_cases.append(entry)

        logger.info("TestGenerator produced %d suggested test case(s)", len(test_cases))
        return test_cases

    def generate_tests(self) -> list[dict[str, Any]]:
        """Alias preserved for workflow compatibility."""
        return self.generate()

    @staticmethod
    def _build_scenarios(name: str, params: list[str], matched_rules: list[str]) -> list[str]:
        if matched_rules:
            return list(matched_rules)
        non_self_params = [p for p in params if p not in ("self", "cls")]
        if not non_self_params:
            return [
                f"Verify {name}() returns expected output with default state",
                f"Verify {name}() handles unexpected exceptions cleanly",
            ]
        return [
            f"Valid input values for ({', '.join(non_self_params)})",
            f"Boundary / empty / None values for ({', '.join(non_self_params)})",
            f"Invalid type or error-handling path in {name}()",
        ]
