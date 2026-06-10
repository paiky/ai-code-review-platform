from datetime import datetime
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityReviewResult
from app.project_integration.models import Project
from app.review_record.models import ReviewResult, ReviewTask


def seed_feedback_task(db_session: Session) -> None:
    now = datetime(2026, 6, 9, 10, 0, 0)
    db_session.add(
        Project(
            id=1,
            name="feedback-demo-service",
            git_provider="GITLAB",
            git_project_id="feedback-1001",
            repository_url="https://gitlab.example.com/demo/feedback",
            default_template_code="backend-default",
            default_code_quality_profile_code="backend-default-ai-review",
            status="ENABLED",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        ReviewTask(
            id=10001,
            project_id=1,
            trigger_type="GITLAB_MR_WEBHOOK",
            external_source_id="88",
            external_url="https://gitlab.example.com/demo/feedback/-/merge_requests/88",
            source_branch="feature/feedback",
            target_branch="main",
            author_name="Alice",
            author_username="alice",
            template_code="backend-default",
            status="SUCCESS",
            review_status="MAJOR",
            risk_level="HIGH",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        ReviewResult(
            id=20001,
            task_id=10001,
            project_id=1,
            template_code="backend-default",
            risk_level="HIGH",
            risk_item_count=1,
            change_analysis_json=json.dumps({"changeTypes": ["DB_DATA_WRITE"], "changedFileCount": 1}),
            risk_card_json=json.dumps(
                {
                    "cardId": "risk-card-feedback-demo",
                    "riskLevel": "HIGH",
                    "summary": "DB change",
                    "riskItems": [
                        {
                            "riskId": "DB_DATA_WRITE_CHANGE_CHECK-001",
                            "ruleCode": "DB_DATA_WRITE_CHANGE_CHECK",
                            "category": "DB_DATA_WRITE",
                            "riskLevel": "HIGH",
                            "title": "DB 写入、表结构或映射变更需要确认",
                            "evidences": [{"filePath": "src/main/resources/db/V1.sql", "lineStart": 12}],
                        }
                    ],
                    "focusIndicators": [],
                },
                ensure_ascii=False,
            ),
            summary="DB change",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.add(
        CodeQualityReviewResult(
            id=30001,
            task_id=10001,
            review_key="deepseek-main",
            project_id=1,
            profile_code="backend-default-ai-review",
            provider="DEEPSEEK",
            model="deepseek-chat",
            display_name="DeepSeek",
            sort_order=10,
            status="SUCCESS",
            overall_level="HIGH",
            summary="发现 1 个问题",
            finding_count=1,
            findings_json=json.dumps(
                [
                    {
                        "severity": "MAJOR",
                        "category": "TRANSACTION",
                        "filePath": "src/main/java/com/demo/OrderService.java",
                        "startLine": 42,
                        "endLine": 48,
                        "title": "订单创建缺少事务边界",
                        "body": "同时写订单和流水。",
                        "suggestion": "增加事务。",
                        "confidence": "HIGH",
                        "source": "DEEPSEEK",
                    }
                ],
                ensure_ascii=False,
            ),
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()


def test_rule_reminder_feedback_roundtrip(client: TestClient, db_session: Session) -> None:
    seed_feedback_task(db_session)

    result_response = client.get("/api/review-tasks/10001/result")

    assert result_response.status_code == 200
    risk_item = result_response.json()["data"]["riskCard"]["riskItems"][0]
    assert risk_item["feedbackKey"]
    assert risk_item["feedback"] is None

    feedback_response = client.post(
        "/api/review-tasks/10001/feedback",
        json={
            "sourceType": "RULE_REMINDER",
            "itemFingerprint": risk_item["feedbackKey"],
            "feedbackType": "FALSE_POSITIVE",
            "reasonType": "PROJECT_ALLOWED",
            "reasonText": "该项目允许本类维护 SQL 由 DBA 单独执行。",
            "suggestAsProjectRule": True,
        },
    )

    assert feedback_response.status_code == 200
    feedback = feedback_response.json()["data"]
    assert feedback["sourceType"] == "RULE_REMINDER"
    assert feedback["feedbackType"] == "FALSE_POSITIVE"
    assert feedback["status"] == "PENDING"

    refreshed = client.get("/api/review-tasks/10001/result").json()["data"]["riskCard"]["riskItems"][0]
    assert refreshed["feedback"]["feedbackType"] == "FALSE_POSITIVE"
    assert refreshed["feedback"]["suggestAsProjectRule"] is True


def test_ai_finding_feedback_pool_and_status_flow(client: TestClient, db_session: Session) -> None:
    seed_feedback_task(db_session)

    quality_response = client.get("/api/review-tasks/10001/code-quality-results")

    assert quality_response.status_code == 200
    finding = quality_response.json()["data"][0]["findings"][0]
    assert finding["fingerprint"]
    assert finding["feedback"] is None

    feedback_response = client.post(
        "/api/review-tasks/10001/feedback",
        json={
            "sourceType": "AI_FINDING",
            "itemFingerprint": finding["fingerprint"],
            "feedbackType": "LEVEL_TOO_HIGH",
            "reasonType": "LEVEL_TOO_HIGH",
            "reasonText": "这里有事务保护，但提示仍有参考价值。",
        },
    )

    assert feedback_response.status_code == 200
    feedback = feedback_response.json()["data"]
    assert feedback["reviewKey"] == "deepseek-main"
    assert feedback["findingIndex"] == 0

    refreshed_finding = client.get("/api/review-tasks/10001/code-quality-results").json()["data"][0]["findings"][0]
    assert refreshed_finding["feedback"]["feedbackType"] == "LEVEL_TOO_HIGH"

    pool_response = client.get("/api/risk-feedback", params={"sourceType": "AI_FINDING"})
    assert pool_response.status_code == 200
    pool = pool_response.json()["data"]
    assert pool["total"] == 1
    assert pool["items"][0]["riskTitle"] == "订单创建缺少事务边界"

    status_response = client.put(
        f"/api/risk-feedback/{feedback['id']}/status",
        json={"status": "VALID", "adminComment": "可作为后续项目规则候选。"},
    )

    assert status_response.status_code == 200
    updated = status_response.json()["data"]
    assert updated["status"] == "VALID"
    assert updated["adminComment"] == "可作为后续项目规则候选。"
