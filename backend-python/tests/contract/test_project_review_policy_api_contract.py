from datetime import datetime
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.project_integration.models import Project
from app.review_record.models import ReviewResult, ReviewTask


def seed_policy_task(db_session: Session) -> None:
    now = datetime(2026, 6, 10, 9, 30, 0)
    db_session.add_all(
        [
            Project(
                id=1,
                name="policy-demo-service",
                git_provider="GITLAB",
                git_project_id="policy-1001",
                repository_url="https://gitlab.example.com/demo/policy",
                default_template_code="backend-default",
                default_code_quality_profile_code="backend-default-ai-review",
                status="ENABLED",
                created_at=now,
                updated_at=now,
            ),
            Project(
                id=2,
                name="other-service",
                git_provider="GITLAB",
                git_project_id="policy-1002",
                repository_url="https://gitlab.example.com/demo/other",
                default_template_code="backend-default",
                default_code_quality_profile_code="backend-default-ai-review",
                status="ENABLED",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.add(
        ReviewTask(
            id=11001,
            project_id=1,
            trigger_type="GITLAB_MR_WEBHOOK",
            external_source_id="108",
            external_url="https://gitlab.example.com/demo/policy/-/merge_requests/108",
            source_branch="feature/policy",
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
            id=21001,
            task_id=11001,
            project_id=1,
            template_code="backend-default",
            risk_level="HIGH",
            risk_item_count=1,
            change_analysis_json=json.dumps({"changeTypes": ["DB_DATA_WRITE"], "changedFileCount": 1}),
            risk_card_json=json.dumps(
                {
                    "cardId": "risk-card-policy-demo",
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
    db_session.commit()


def submit_rule_feedback(
    client: TestClient,
    *,
    suggest: bool,
    reason_type: str = "PROJECT_ALLOWED",
    reason_text: str = "该项目允许本类维护 SQL 由 DBA 单独执行。",
) -> dict:
    risk_item = client.get("/api/review-tasks/11001/result").json()["data"]["riskCard"]["riskItems"][0]
    response = client.post(
        "/api/review-tasks/11001/feedback",
        json={
            "sourceType": "RULE_REMINDER",
            "itemFingerprint": risk_item["feedbackKey"],
            "feedbackType": "FALSE_POSITIVE",
            "reasonType": reason_type,
            "reasonText": reason_text,
            "suggestAsProjectRule": suggest,
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def test_suggested_feedback_can_convert_to_project_policy_and_is_project_scoped(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_policy_task(db_session)
    feedback = submit_rule_feedback(client, suggest=True)

    response = client.post(
        f"/api/risk-feedback/{feedback['id']}/convert-to-policy",
        json={
            "policyType": "PROJECT_RULE",
            "riskType": "DB_DATA_WRITE",
            "title": "本项目 DB 维护 SQL 由 DBA 单独执行",
            "content": "DB 维护 SQL 已由 DBA 发布流程承接，不应仅凭 SQL 文件变更判定为阻塞风险。",
            "enabled": True,
            "createdBy": "alice",
        },
    )

    assert response.status_code == 200
    policy = response.json()["data"]
    assert policy["projectId"] == 1
    assert policy["policyType"] == "PROJECT_RULE"
    assert policy["riskType"] == "DB_DATA_WRITE"
    assert policy["sourceFeedbackId"] == feedback["id"]
    assert policy["enabled"] is True
    assert policy["version"] == 1

    converted_pool = client.get("/api/risk-feedback", params={"status": "CONVERTED"}).json()["data"]
    assert converted_pool["total"] == 1
    assert converted_pool["items"][0]["id"] == feedback["id"]

    project_policies = client.get("/api/projects/1/review-policies").json()["data"]
    assert [item["id"] for item in project_policies] == [policy["id"]]
    other_project_policies = client.get("/api/projects/2/review-policies").json()["data"]
    assert other_project_policies == []


def test_project_policy_can_update_and_toggle_enabled(client: TestClient, db_session: Session) -> None:
    seed_policy_task(db_session)
    feedback = submit_rule_feedback(client, suggest=True)
    policy = client.post(
        f"/api/risk-feedback/{feedback['id']}/convert-to-policy",
        json={
            "policyType": "PROJECT_RULE",
            "title": "初始项目规则",
            "content": "初始内容",
        },
    ).json()["data"]

    update_response = client.put(
        f"/api/project-review-policies/{policy['id']}",
        json={
            "policyType": "CONTEXT_FACT",
            "riskType": "TRANSACTION",
            "title": "统一事务边界由框架注入",
            "content": "本项目部分事务由框架切面注入，Review 时需结合上下文判断。",
            "enabled": False,
        },
    )

    assert update_response.status_code == 200
    updated = update_response.json()["data"]
    assert updated["policyType"] == "CONTEXT_FACT"
    assert updated["riskType"] == "TRANSACTION"
    assert updated["enabled"] is False
    assert updated["version"] == 2

    disabled_policies = client.get("/api/projects/1/review-policies", params={"enabled": "false"}).json()["data"]
    assert [item["id"] for item in disabled_policies] == [policy["id"]]

    toggle_response = client.put(f"/api/project-review-policies/{policy['id']}/enabled", json={"enabled": True})
    assert toggle_response.status_code == 200
    assert toggle_response.json()["data"]["enabled"] is True


def test_pending_feedback_must_be_suggested_or_valid_before_conversion(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_policy_task(db_session)
    feedback = submit_rule_feedback(client, suggest=False)

    rejected = client.post(f"/api/risk-feedback/{feedback['id']}/convert-to-policy", json={})
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "VALIDATION_ERROR"

    status_response = client.put(
        f"/api/risk-feedback/{feedback['id']}/status",
        json={"status": "VALID", "adminComment": "确认可沉淀。"},
    )
    assert status_response.status_code == 200

    converted = client.post(f"/api/risk-feedback/{feedback['id']}/convert-to-policy", json={})
    assert converted.status_code == 200
    assert converted.json()["data"]["policyType"] == "PROJECT_RULE"


def test_context_missing_and_non_injectable_policy_type_are_rejected(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_policy_task(db_session)
    feedback = submit_rule_feedback(
        client,
        suggest=True,
        reason_type="CONTEXT_MISSING",
        reason_text="缺少调用方和引用搜索结果。",
    )

    rejected_context = client.post(f"/api/risk-feedback/{feedback['id']}/convert-to-policy", json={})
    assert rejected_context.status_code == 400
    assert "CONTEXT_MISSING" in rejected_context.json()["message"]

    valid_feedback = submit_rule_feedback(client, suggest=True, reason_type="PROJECT_ALLOWED")
    rejected_policy_type = client.post(
        f"/api/risk-feedback/{valid_feedback['id']}/convert-to-policy",
        json={"policyType": "IGNORE_RULE"},
    )
    assert rejected_policy_type.status_code == 400
    assert rejected_policy_type.json()["code"] == "VALIDATION_ERROR"
