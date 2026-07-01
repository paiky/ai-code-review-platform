from __future__ import annotations

from datetime import datetime, timedelta
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityReviewProgressEvent
from app.project_integration.models import Project
from app.review_feedback.models import ReviewItemFeedback
from app.review_record.models import ReviewTask


def test_rule_gap_dashboard_aggregates_context_pack_rule_gaps(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_rule_gap_records(db_session)

    response = client.get("/api/code-quality-reviews/rule-gaps?recentDays=30&limit=10")

    assert response.status_code == 200
    data = response.json()["data"]
    items = data["items"]
    dto_item = next(item for item in items if item["signal"] == "DTO_FIELD_CHANGED")
    assert dto_item["gapType"] == "UNSUPPORTED_PLANNER_SIGNAL"
    assert dto_item["requestedContext"] == "REFERENCE_SEARCH"
    assert dto_item["suggestedCapability"] == "Add DTO / VO field reference retrieval."
    assert dto_item["occurrenceCount"] == 2
    assert dto_item["projectCount"] == 2
    assert dto_item["taskCount"] == 2
    assert dto_item["reviewCount"] == 2
    assert {project["projectId"] for project in dto_item["projects"]} == {1, 2}
    assert {task["taskId"] for task in dto_item["recentTasks"]} == {101, 102}
    assert {task["reviewKey"] for task in dto_item["recentTasks"]} == {"deepseek-main", "glm-main"}
    assert dto_item["recommendation"]["recommendationStatus"] in {"RECOMMENDED", "WATCH", "NOT_NOW"}
    assert dto_item["recommendation"]["completionType"] in {
        "PLANNER",
        "RETRIEVER",
        "BUDGET",
        "PROMPT",
        "STABILITY",
        "OBSERVABILITY",
    }
    assert data["summary"]["scannedEventCount"] == 3
    assert data["summary"]["parsedEventCount"] == 3
    assert data["summary"]["eventsWithRuleGapCount"] == 3
    assert data["summary"]["parseFailedEventCount"] == 0


def test_rule_gap_dashboard_filters_by_project_gap_type_and_signal(
    client: TestClient,
    db_session: Session,
) -> None:
    _seed_rule_gap_records(db_session)

    response = client.get(
        "/api/code-quality-reviews/rule-gaps"
        "?projectId=1&gapType=UNSUPPORTED_PLANNER_SIGNAL&signal=DTO_FIELD_CHANGED&recentDays=30"
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["signal"] == "DTO_FIELD_CHANGED"
    assert items[0]["occurrenceCount"] == 1
    assert items[0]["projectCount"] == 1
    assert items[0]["projects"][0]["projectName"] == "demo-service"


def test_rule_gap_dashboard_skips_bad_json_without_breaking_response(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime.now()
    _seed_projects_and_tasks(db_session, now)
    db_session.add_all(
        [
            CodeQualityReviewProgressEvent(
                id=1,
                task_id=101,
                review_key="deepseek-main",
                phase="CONTEXT_PACK_BUILT",
                level="INFO",
                message="Context Pack 已构建",
                detail="{\"summary\":",
                created_at=now - timedelta(minutes=2),
            ),
            CodeQualityReviewProgressEvent(
                id=2,
                task_id=101,
                review_key="deepseek-main",
                phase="CONTEXT_PACK_BUILT",
                level="INFO",
                message="Context Pack 已构建",
                detail=_context_pack_detail(
                    [
                        {
                            "gapType": "UNSUPPORTED_PLANNER_SIGNAL",
                            "signal": "FIELD_DELETED",
                            "requestedContext": "REFERENCE_SEARCH",
                            "suggestedCapability": "Add field reference retrieval.",
                        }
                    ]
                ),
                created_at=now - timedelta(minutes=1),
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/code-quality-reviews/rule-gaps?recentDays=30")

    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data["items"]) == 1
    assert data["summary"]["scannedEventCount"] == 2
    assert data["summary"]["parseFailedEventCount"] == 1
    assert data["summary"]["skippedEventCount"] == 1


def test_rule_gap_dashboard_returns_recommendations_with_feedback_signals(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime.now()
    _seed_projects_and_tasks(db_session, now)
    db_session.add_all(
        [
            CodeQualityReviewProgressEvent(
                id=1,
                task_id=101,
                review_key="deepseek-main",
                phase="CONTEXT_PACK_BUILT",
                level="INFO",
                message="Context Pack 已构建",
                detail=_context_pack_detail(
                    [
                        {
                            "gapType": "UNSUPPORTED_PLANNER_SIGNAL",
                            "signal": "DB_SQL_MAPPER_CHANGED",
                            "requestedContext": "DB_SCHEMA_CONTEXT",
                            "suggestedCapability": "Add DB / Mapper / Entity relationship retrieval.",
                        }
                    ]
                ),
                created_at=now - timedelta(minutes=2),
            ),
            CodeQualityReviewProgressEvent(
                id=2,
                task_id=102,
                review_key="glm-main",
                phase="CONTEXT_PACK_BUILT",
                level="INFO",
                message="Context Pack 已构建",
                detail=_context_pack_detail(
                    [
                        {
                            "gapType": "UNSUPPORTED_PLANNER_SIGNAL",
                            "signal": "DB_SQL_MAPPER_CHANGED",
                            "requestedContext": "DB_SCHEMA_CONTEXT",
                            "suggestedCapability": "Add DB / Mapper / Entity relationship retrieval.",
                        }
                    ]
                ),
                created_at=now - timedelta(minutes=1),
            ),
            ReviewItemFeedback(
                id=1,
                project_id=1,
                task_id=101,
                source_type="AI_FINDING",
                item_fingerprint="finding-1",
                card_id=None,
                risk_id=None,
                review_key="deepseek-main",
                finding_index=0,
                risk_type="DATA_CONSISTENCY",
                risk_title="缺少表结构上下文",
                original_risk_level="MAJOR",
                feedback_type="FALSE_POSITIVE",
                reason_type="CONTEXT_MISSING",
                reason_text="需要 mapper 和 schema 证据",
                missing_context_types_json='["DB_SCHEMA_CONTEXT"]',
                suggest_as_project_rule=False,
                status="VALID",
                admin_comment=None,
                item_snapshot_json=None,
                operator_name="Alice",
                operator_username="alice",
                created_at=now - timedelta(minutes=1),
                updated_at=now - timedelta(minutes=1),
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/code-quality-reviews/rule-gaps?recentDays=30&limit=10")

    assert response.status_code == 200
    data = response.json()["data"]
    recommendations = data["recommendations"]["items"]
    db_recommendation = next(item for item in recommendations if item["signal"] == "DB_SQL_MAPPER_CHANGED")
    assert db_recommendation["recommendationStatus"] == "NOT_NOW"
    assert db_recommendation["completionType"] == "RETRIEVER"
    assert db_recommendation["suggestedNextStage"] == "已支持 signal 回归复盘：DB / Mapper / Entity 关联检索"
    assert db_recommendation["scoreBreakdown"]["resolvedCurrentSupport"] < 0
    assert any("当前代码已支持该 signal" in reason for reason in db_recommendation["reasons"])
    assert "不自动改规则" in db_recommendation["suggestedPrompt"]
    assert db_recommendation["feedbackSignals"]["contextMissingCount"] == 1
    assert db_recommendation["feedbackSignals"]["falsePositiveCount"] == 1
    assert db_recommendation["feedbackSignals"]["correlation"] == "TASK_LEVEL"
    assert db_recommendation["recentTaskSamples"][0]["taskId"] in {101, 102}
    assert data["recommendations"]["summary"]["notNowCount"] >= 1


def test_rule_gap_dashboard_does_not_leak_raw_detail_sensitive_fields(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime.now()
    _seed_projects_and_tasks(db_session, now)
    db_session.add(
        CodeQualityReviewProgressEvent(
            id=1,
            task_id=101,
            review_key="deepseek-main",
            phase="CONTEXT_PACK_BUILT",
            level="INFO",
            message="Context Pack 已构建",
            detail=_context_pack_detail(
                [
                    {
                        "gapType": "UNSUPPORTED_PLANNER_SIGNAL",
                        "signal": "DTO_FIELD_CHANGED",
                        "requestedContext": "REFERENCE_SEARCH",
                        "suggestedCapability": (
                            "Add DTO retrieval; token: super-secret; "
                            "D:\\projects\\secret\\repo\\Order.java"
                        ),
                        "sourceSnippet": "order.setStatus(secret)",
                        "localPath": "D:\\projects\\secret\\repo\\Order.java",
                        "providerRawOutput": "raw-provider-secret",
                    }
                ]
            ),
            created_at=now - timedelta(minutes=1),
        )
    )
    db_session.commit()

    response = client.get("/api/code-quality-reviews/rule-gaps?recentDays=30")

    assert response.status_code == 200
    text = json.dumps(response.json()["data"], ensure_ascii=False)
    assert "super-secret" not in text
    assert "D:\\projects" not in text
    assert "order.setStatus(secret)" not in text
    assert "raw-provider-secret" not in text
    assert "token: ****" in text


def _seed_rule_gap_records(db_session: Session) -> None:
    now = datetime.now()
    _seed_projects_and_tasks(db_session, now)
    db_session.add_all(
        [
            CodeQualityReviewProgressEvent(
                id=1,
                task_id=101,
                review_key="deepseek-main",
                phase="CONTEXT_PACK_BUILT",
                level="INFO",
                message="Context Pack 已构建",
                detail=_context_pack_detail(
                    [
                        {
                            "gapType": "UNSUPPORTED_PLANNER_SIGNAL",
                            "signal": "DTO_FIELD_CHANGED",
                            "requestedContext": "REFERENCE_SEARCH",
                            "suggestedCapability": "Add DTO / VO field reference retrieval.",
                        }
                    ]
                ),
                created_at=now - timedelta(minutes=3),
            ),
            CodeQualityReviewProgressEvent(
                id=2,
                task_id=102,
                review_key="glm-main",
                phase="CONTEXT_PACK_BUILT",
                level="INFO",
                message="Context Pack 已构建",
                detail=_context_pack_detail(
                    [
                        {
                            "gapType": "UNSUPPORTED_PLANNER_SIGNAL",
                            "signal": "DTO_FIELD_CHANGED",
                            "requestedContext": "REFERENCE_SEARCH",
                            "suggestedCapability": "Add DTO / VO field reference retrieval.",
                        }
                    ]
                ),
                created_at=now - timedelta(minutes=2),
            ),
            CodeQualityReviewProgressEvent(
                id=3,
                task_id=201,
                review_key="deepseek-main",
                phase="CONTEXT_PACK_BUILT",
                level="INFO",
                message="Context Pack 已构建",
                detail=_context_pack_detail(
                    [
                        {
                            "gapType": "BUDGET_CUT",
                            "signal": "BUDGET_CONTROLLER",
                            "requestedContext": "-",
                            "suggestedCapability": "Improve evidence ranking, summarization, or Context Pack budget allocation.",
                        }
                    ]
                ),
                created_at=now - timedelta(minutes=1),
            ),
        ]
    )
    db_session.commit()


def _seed_projects_and_tasks(db_session: Session, now: datetime) -> None:
    db_session.add_all(
        [
            Project(
                id=1,
                name="demo-service",
                git_provider="GITLAB",
                git_project_id="1001",
                repository_url="https://gitlab.example.com/demo/service",
                default_template_code="backend-default",
                default_code_quality_profile_code="backend-default-ai-review",
                default_code_quality_provider_code=None,
                dingtalk_webhook_id=None,
                status="ENABLED",
                description=None,
                created_at=now,
                updated_at=now,
            ),
            Project(
                id=2,
                name="admin-service",
                git_provider="GITLAB",
                git_project_id="1002",
                repository_url="https://gitlab.example.com/admin/service",
                default_template_code="backend-default",
                default_code_quality_profile_code="backend-default-ai-review",
                default_code_quality_provider_code=None,
                dingtalk_webhook_id=None,
                status="ENABLED",
                description=None,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.add_all(
        [
            _review_task(101, 1, now - timedelta(minutes=10)),
            _review_task(102, 2, now - timedelta(minutes=9)),
            _review_task(201, 1, now - timedelta(minutes=8)),
        ]
    )
    db_session.commit()


def _review_task(task_id: int, project_id: int, created_at: datetime) -> ReviewTask:
    return ReviewTask(
        id=task_id,
        project_id=project_id,
        trigger_type="GITLAB_MR_WEBHOOK",
        external_source_id=str(task_id),
        external_url=f"https://gitlab.example.com/demo/service/-/merge_requests/{task_id}",
        source_branch="feature/rule-gap",
        target_branch="main",
        commit_sha=f"abcdef{task_id}",
        before_sha=None,
        after_sha=None,
        author_name="Alice",
        author_username="alice",
        template_code="backend-default",
        target_type="BACKEND",
        target_types_json=None,
        code_quality_profile_code="backend-default-ai-review",
        status="SUCCESS",
        review_status="MAJOR",
        risk_level="MEDIUM",
        error_message=None,
        started_at=created_at,
        finished_at=created_at + timedelta(seconds=5),
        created_at=created_at,
        updated_at=created_at + timedelta(seconds=5),
    )


def _context_pack_detail(rule_gap_items: list[dict]) -> str:
    return json.dumps(
        {
            "meta": {"version": "context-pack-v0"},
            "summary": {
                "ruleGapItems": rule_gap_items,
                "ruleGapSummary": {"total": len(rule_gap_items)},
            },
        },
        ensure_ascii=False,
    )
