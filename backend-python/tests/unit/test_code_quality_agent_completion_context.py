from app.code_quality.service import _build_agent_completion_context


def test_auto_review_builds_reference_only_completion_context_v2() -> None:
    context = _build_agent_completion_context(
        rule_result_id=1270,
        focus_change_types=["CACHE"],
        focus_rule_codes=["CACHE_WRITE_DELETE_CHANGED"],
        notification_context={"title": "GITLAB_MR_WEBHOOK 432"},
        reminder_card_enabled=True,
    )

    assert context == {
        "schemaVersion": "agent-completion-context-v2",
        "autoNotification": True,
        "ruleResultId": 1270,
        "focusChangeTypes": ["CACHE"],
        "focusRuleCodes": ["CACHE_WRITE_DELETE_CHANGED"],
        "notificationContext": {"title": "GITLAB_MR_WEBHOOK 432"},
        "reminderCardEnabled": True,
    }
    assert "riskCard" not in context
