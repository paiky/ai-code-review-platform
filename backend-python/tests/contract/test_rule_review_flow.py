from datetime import datetime
import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.project_integration.models import Project
from app.rule_template.models import RuleTemplate


def seed_backend_template(db_session: Session) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add(
        RuleTemplate(
            template_code="backend-default",
            template_name="后端默认审查模板",
            target_type="BACKEND",
            version=1,
            enabled_rule_codes=json.dumps(
                [
                    "DB_SCHEMA_CHANGE_CHECK",
                    "DB_SQL_CHANGE_CHECK",
                    "ORM_MAPPING_CHANGE_CHECK",
                    "ENTITY_MODEL_CHANGE_CHECK",
                    "DATA_MIGRATION_CHECK",
                    "DB_SCHEMA_SYNC_SUSPECT_CHECK",
                    "CACHE_KEY_CHANGE_CHECK",
                    "CACHE_TTL_CHANGE_CHECK",
                    "CACHE_INVALIDATION_CHANGE_CHECK",
                    "CACHE_READ_WRITE_CHANGE_CHECK",
                    "CACHE_SERIALIZATION_CHANGE_CHECK",
                    "MQ_PRODUCER_CHANGE_CHECK",
                    "MQ_CONSUMER_CHANGE_CHECK",
                    "MQ_MESSAGE_SCHEMA_CHANGE_CHECK",
                    "MQ_TOPIC_CONFIG_CHANGE_CHECK",
                    "MQ_RETRY_DLQ_CHANGE_CHECK",
                    "CONFIG_RELEASE_CHECK",
                ]
            ),
            config_json=json.dumps(
                {
                    "focusChangeTypes": [
                        "DB",
                        "DB_SCHEMA",
                        "DB_SQL",
                        "CACHE",
                        "CACHE_INVALIDATION",
                        "MQ",
                        "MQ_PRODUCER",
                        "CONFIG",
                    ],
                    "recommendedChecks": ["确认变更影响范围。"],
                }
            ),
            status="ENABLED",
            description="stage3",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()


def seed_project(db_session: Session) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add(
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
        )
    )
    db_session.commit()


def mock_mr_payload() -> dict:
    return {
        "object_kind": "merge_request",
        "event_time": "2026-05-18T10:00:00+08:00",
        "project": {
            "id": 1001,
            "name": "demo-service",
            "web_url": "https://gitlab.example.com/demo/service",
        },
        "object_attributes": {
            "iid": 12,
            "action": "open",
            "source_branch": "feature/risk-demo",
            "target_branch": "main",
            "url": "https://gitlab.example.com/demo/service/-/merge_requests/12",
            "last_commit": {"id": "abcdef123456"},
        },
        "user": {"name": "Alice", "username": "alice"},
        "changedFiles": [
            {
                "old_path": "src/main/resources/mapper/OrderMapper.xml",
                "new_path": "src/main/resources/mapper/OrderMapper.xml",
                "diffText": "+ update orders set status = 'CONFIRMED' where id = #{id}",
            },
            {
                "old_path": "src/main/java/com/demo/order/OrderCacheService.java",
                "new_path": "src/main/java/com/demo/order/OrderCacheService.java",
                "diffText": '+ redisTemplate.delete("order:list");',
            },
            {
                "old_path": "src/main/java/com/demo/order/OrderEventPublisher.java",
                "new_path": "src/main/java/com/demo/order/OrderEventPublisher.java",
                "diffText": '+ rabbitTemplate.convertAndSend("order.confirmed", event);',
            },
        ],
    }


def test_mock_mr_webhook_creates_success_task_result_and_notification(
    client: TestClient, db_session: Session
) -> None:
    seed_backend_template(db_session)

    response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mock_mr_payload(),
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "SUCCESS"
    task_id = data["taskId"]

    result = client.get(f"/api/review-tasks/{task_id}/result").json()["data"]
    assert result["riskLevel"] == "HIGH"
    assert {"DB_SQL", "CACHE_INVALIDATION", "MQ_PRODUCER"}.issubset(
        {item["category"] for item in result["riskCard"]["riskItems"]}
    )

    notifications = client.get(f"/api/review-tasks/{task_id}/notifications").json()["data"]
    assert notifications[0]["status"] == "SKIPPED"
    assert notifications[0]["channel"] == "DINGTALK"


def test_manual_review_flow_writes_risk_card(client: TestClient, db_session: Session) -> None:
    seed_backend_template(db_session)
    seed_project(db_session)

    response = client.post(
        "/api/review-tasks/manual",
        json={
            "projectId": 1,
            "sourceBranch": "feature/manual",
            "targetBranch": "main",
            "authorName": "Manual Tester",
            "changedFiles": [
                {
                    "path": "db/migration/V12__alter_orders.sql",
                    "changeType": "MODIFIED",
                    "diffText": "+ alter table orders add column risk_level varchar(32)",
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "SUCCESS"
    assert data["riskLevel"] == "HIGH"
    result = client.get(f"/api/review-tasks/{data['taskId']}/result").json()["data"]
    assert result["changeAnalysis"]["changeTypes"] == ["DB", "DB_SCHEMA"]
    assert result["riskCard"]["riskItems"][0]["category"] == "DB_SCHEMA"


def test_rerun_gitlab_mr_task_replays_raw_payload(client: TestClient, db_session: Session) -> None:
    seed_backend_template(db_session)
    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mock_mr_payload(),
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    ).json()["data"]

    rerun = client.post(f"/api/review-tasks/{created['taskId']}/rerun")

    assert rerun.status_code == 200
    data = rerun.json()["data"]
    assert data["sourceTaskId"] == created["taskId"]
    assert data["status"] == "SUCCESS"
    assert data["triggerType"] == "GITLAB_MR_WEBHOOK"
    assert data["taskId"] != created["taskId"]

