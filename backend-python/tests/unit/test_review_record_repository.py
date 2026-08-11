from __future__ import annotations

from datetime import datetime
import json

from sqlalchemy.orm import Session

from app.review_record.models import ReviewResult
from app.review_record.repository import (
    find_review_result_for_notification,
    parse_agent_completion_context,
    resolve_agent_completion_notification,
)


def _review_result(
    *,
    result_id: int,
    task_id: int,
    risk_card_json: str,
    reminder_card_enabled: bool = True,
) -> ReviewResult:
    now = datetime.now()
    return ReviewResult(
        id=result_id,
        task_id=task_id,
        project_id=100,
        template_code="backend-default",
        target_type="BACKEND",
        reminder_card_enabled=reminder_card_enabled,
        risk_level="HIGH",
        risk_item_count=1,
        change_analysis_json="{}",
        risk_card_json=risk_card_json,
        summary="规则风险",
        created_at=now,
        updated_at=now,
    )


def test_notification_reference_requires_matching_result_and_task(
    db_session: Session,
) -> None:
    risk_card = {"riskLevel": "HIGH", "riskItems": [{"ruleCode": "CACHE_CHANGED"}]}
    db_session.add(
        _review_result(
            result_id=1270,
            task_id=432,
            risk_card_json=json.dumps(risk_card, ensure_ascii=False),
            reminder_card_enabled=False,
        )
    )
    db_session.flush()

    assert find_review_result_for_notification(db_session, 1270, 432) == {
        "riskCard": risk_card,
        "reminderCardEnabled": False,
    }
    assert find_review_result_for_notification(db_session, 1270, 433) is None


def test_completion_context_parser_safely_rejects_invalid_or_non_object_json(
    caplog,
) -> None:
    assert parse_agent_completion_context("{damaged", task_id=432) == {}
    assert parse_agent_completion_context("[]", task_id=433) == {}
    assert "taskId=432" in caplog.text
    assert "taskId=433" in caplog.text


def test_notification_reference_rejects_damaged_risk_card_json(
    db_session: Session,
) -> None:
    db_session.add(
        _review_result(
            result_id=1271,
            task_id=434,
            risk_card_json="{damaged",
        )
    )
    db_session.flush()

    assert find_review_result_for_notification(db_session, 1271, 434) is None


def test_completion_notification_prefers_legacy_v1_embedded_risk_card(
    db_session: Session,
) -> None:
    legacy_card = {"riskLevel": "MEDIUM", "riskItems": []}

    resolved = resolve_agent_completion_notification(
        db_session,
        task_id=435,
        context={
            "ruleResultId": 9999,
            "riskCard": legacy_card,
            "reminderCardEnabled": False,
        },
    )

    assert resolved == (9999, legacy_card, False)


def test_completion_notification_v2_reads_risk_card_by_task_scoped_reference(
    db_session: Session,
) -> None:
    risk_card = {"riskLevel": "LOW", "riskItems": []}
    db_session.add(
        _review_result(
            result_id=1272,
            task_id=436,
            risk_card_json=json.dumps(risk_card, ensure_ascii=False),
        )
    )
    db_session.flush()

    resolved = resolve_agent_completion_notification(
        db_session,
        task_id=436,
        context={
            "schemaVersion": "agent-completion-context-v2",
            "ruleResultId": 1272,
        },
    )

    assert resolved == (1272, risk_card, True)
