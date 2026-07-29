from __future__ import annotations

from typing import Any, Mapping


DEFAULT_AGENT_BUDGETS: dict[str, int] = {
    "maxTurns": 12,
    "maxToolCalls": 40,
    "maxSourceBytes": 200_000,
    "timeoutSeconds": 600,
    "inlineDiffBytes": 200_000,
    "maxEvidenceCalls": 10,
    "convergeAtCalls": 8,
    "submitByTurn": 9,
}

AGENT_BUDGET_LIMITS: dict[str, dict[str, int]] = {
    "maxTurns": {"min": 6, "max": 18},
    "maxToolCalls": {"min": 10, "max": 60},
    "maxSourceBytes": {"min": 10_000, "max": 300_000},
    "timeoutSeconds": {"min": 60, "max": 900},
    "inlineDiffBytes": {"min": 10_000, "max": 300_000},
    "maxEvidenceCalls": {"min": 4, "max": 15},
    "convergeAtCalls": {"min": 2, "max": 13},
    "submitByTurn": {"min": 3, "max": 15},
}

AGENT_BUDGET_KEYS = frozenset(DEFAULT_AGENT_BUDGETS)


class AgentBudgetValidationError(ValueError):
    pass


def validate_agent_budgets(
    value: Any,
    *,
    base: Mapping[str, int] | None = None,
) -> dict[str, int]:
    if not isinstance(value, dict):
        raise AgentBudgetValidationError("budgets must be an object")
    unknown = sorted(set(value) - AGENT_BUDGET_KEYS)
    if unknown:
        raise AgentBudgetValidationError(f"unknown Agent budget field: {unknown[0]}")

    result = dict(DEFAULT_AGENT_BUDGETS if base is None else base)
    for key, raw in value.items():
        if isinstance(raw, bool) or not isinstance(raw, int):
            raise AgentBudgetValidationError(f"{key} must be an integer")
        limits = AGENT_BUDGET_LIMITS[key]
        if raw < limits["min"] or raw > limits["max"]:
            raise AgentBudgetValidationError(
                f"{key} must be between {limits['min']} and {limits['max']}"
            )
        result[key] = raw

    missing = sorted(AGENT_BUDGET_KEYS - set(result))
    if missing:
        raise AgentBudgetValidationError(f"missing Agent budget field: {missing[0]}")
    if result["convergeAtCalls"] > result["maxEvidenceCalls"] - 2:
        raise AgentBudgetValidationError(
            "convergeAtCalls must be at most maxEvidenceCalls - 2"
        )
    if result["submitByTurn"] > result["maxTurns"] - 3:
        raise AgentBudgetValidationError("submitByTurn must be at most maxTurns - 3")
    if result["maxToolCalls"] < result["maxEvidenceCalls"] + 1:
        raise AgentBudgetValidationError(
            "maxToolCalls must be at least maxEvidenceCalls + 1"
        )
    return result


def default_agent_budgets() -> dict[str, int]:
    return dict(DEFAULT_AGENT_BUDGETS)


def agent_budget_limits() -> dict[str, dict[str, int]]:
    return {key: dict(value) for key, value in AGENT_BUDGET_LIMITS.items()}
