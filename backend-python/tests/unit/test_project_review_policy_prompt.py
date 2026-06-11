from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.project_review_policy.models import ProjectReviewPolicy
from app.project_review_policy.service import (
    PROMPT_POLICY_MAX_CONTENT_CHARS,
    PROMPT_POLICY_MAX_COUNT,
    PROMPT_POLICY_MAX_TOTAL_CHARS,
    build_project_review_policy_prompt_context,
)


def add_policy(
    db_session: Session,
    *,
    project_id: int = 1,
    policy_type: str = "PROJECT_RULE",
    title: str,
    content: str = "策略内容",
    risk_type: str | None = "TRANSACTION",
    enabled: bool = True,
    updated_at: datetime | None = None,
) -> None:
    now = updated_at or datetime(2026, 6, 10, 10, 0, 0)
    db_session.add(
        ProjectReviewPolicy(
            project_id=project_id,
            policy_type=policy_type,
            risk_type=risk_type,
            title=title,
            content=content,
            source_feedback_id=None,
            enabled=enabled,
            version=1,
            created_by="test",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()


def test_prompt_context_injects_only_enabled_project_rule_and_context_fact(db_session: Session) -> None:
    add_policy(db_session, title="项目规则", policy_type="PROJECT_RULE")
    add_policy(db_session, title="项目事实", policy_type="CONTEXT_FACT")
    add_policy(db_session, title="停用规则", policy_type="PROJECT_RULE", enabled=False)
    add_policy(db_session, title="忽略规则", policy_type="IGNORE_RULE")
    add_policy(db_session, title="其它项目规则", project_id=2)

    context = build_project_review_policy_prompt_context(db_session, 1)

    assert [item["title"] for item in context["items"]] == ["项目事实", "项目规则"]
    assert "项目规则" in context["promptText"]
    assert "项目事实" in context["promptText"]
    assert "停用规则" not in context["promptText"]
    assert "忽略规则" not in context["promptText"]
    assert context["meta"]["injectedCount"] == 2


def test_prompt_context_orders_by_updated_at_desc(db_session: Session) -> None:
    base = datetime(2026, 6, 10, 10, 0, 0)
    add_policy(db_session, title="旧策略", updated_at=base)
    add_policy(db_session, title="新策略", updated_at=base + timedelta(minutes=1))

    context = build_project_review_policy_prompt_context(db_session, 1)

    assert [item["title"] for item in context["items"]] == ["新策略", "旧策略"]


def test_prompt_context_limits_policy_count(db_session: Session) -> None:
    for index in range(PROMPT_POLICY_MAX_COUNT + 5):
        add_policy(db_session, title=f"策略 {index}", content="短内容")

    context = build_project_review_policy_prompt_context(db_session, 1)

    assert context["meta"]["totalAvailable"] == PROMPT_POLICY_MAX_COUNT + 5
    assert context["meta"]["injectedCount"] == PROMPT_POLICY_MAX_COUNT
    assert len(context["items"]) == PROMPT_POLICY_MAX_COUNT
    assert context["meta"]["truncated"] is True


def test_prompt_context_limits_single_content_and_total_text(db_session: Session) -> None:
    huge_content = "x" * (PROMPT_POLICY_MAX_CONTENT_CHARS + 500)
    for index in range(12):
        add_policy(db_session, title=f"长策略 {index}", content=huge_content)

    context = build_project_review_policy_prompt_context(db_session, 1)

    assert context["meta"]["promptLength"] <= PROMPT_POLICY_MAX_TOTAL_CHARS
    assert len(context["promptText"]) <= PROMPT_POLICY_MAX_TOTAL_CHARS
    assert context["meta"]["contentTruncatedCount"] == context["meta"]["injectedCount"]
    assert context["meta"]["truncated"] is True
    assert all(len(item["content"]) <= PROMPT_POLICY_MAX_CONTENT_CHARS for item in context["items"])
