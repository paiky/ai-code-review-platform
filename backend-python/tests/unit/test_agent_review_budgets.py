import pytest

from app.agent_review_spike.budgets import (
    AgentBudgetValidationError,
    default_agent_budgets,
    validate_agent_budgets,
)


def test_agent_budgets_keep_defaults_and_allow_bounded_partial_update() -> None:
    defaults = validate_agent_budgets({})
    assert defaults == default_agent_budgets()

    updated = validate_agent_budgets({"maxTurns": 14}, base=defaults)
    assert updated["maxTurns"] == 14
    assert updated["maxEvidenceCalls"] == 10
    assert defaults["maxTurns"] == 12


@pytest.mark.parametrize(
    ("budgets", "message"),
        [
            ({"maxTurns": True}, "maxTurns must be an integer"),
            ({"maxTurns": "14"}, "maxTurns must be an integer"),
            ({"maxTurns": 14.0}, "maxTurns must be an integer"),
            ({"maxTurns": None}, "maxTurns must be an integer"),
            ({"unknown": 1}, "unknown Agent budget field"),
        ({"maxTurns": 19}, "maxTurns must be between 6 and 18"),
        (
            {"maxEvidenceCalls": 10, "convergeAtCalls": 9},
            "convergeAtCalls must be at most maxEvidenceCalls - 2",
        ),
        (
            {"maxTurns": 12, "submitByTurn": 10},
            "submitByTurn must be at most maxTurns - 3",
        ),
            (
                {"maxToolCalls": 10, "maxEvidenceCalls": 10},
                r"maxToolCalls must be at least maxEvidenceCalls \+ 1",
            ),
    ],
)
def test_agent_budgets_reject_invalid_values(
    budgets: dict[str, object], message: str
) -> None:
    with pytest.raises(AgentBudgetValidationError, match=message):
        validate_agent_budgets(budgets)
