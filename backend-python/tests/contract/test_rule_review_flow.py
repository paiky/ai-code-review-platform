from datetime import datetime
import json

from fastapi.testclient import TestClient
import httpx
import respx
from sqlalchemy.orm import Session

from app.project_integration.models import Project
from app.review_record.models import ReviewResult
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
                    "DB_DATA_WRITE_CHANGE_CHECK",
                    "CACHE_WRITE_DELETE_CHANGE_CHECK",
                    "MQ_CONFIG_CHANGE_CHECK",
                    "CONFIG_RELEASE_CHECK",
                ]
            ),
            config_json=json.dumps(
                {
                    "focusChangeTypes": [
                        "DB_DATA_WRITE",
                        "CACHE_WRITE_DELETE",
                        "MQ_CONFIG",
                        "CONFIG",
                    ],
                    "focusRuleCodes": [
                        "DB_DATA_WRITE_CHANGE_CHECK",
                        "CACHE_WRITE_DELETE_CHANGE_CHECK",
                        "MQ_CONFIG_CHANGE_CHECK",
                        "CONFIG_RELEASE_CHECK",
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


def seed_frontend_template(db_session: Session) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add(
        RuleTemplate(
            template_code="frontend-default",
            template_name="前端默认审查模板",
            target_type="FRONTEND",
            version=1,
            enabled_rule_codes=json.dumps(["CONFIG_RELEASE_CHECK"]),
            config_json=json.dumps(
                {
                    "focusChangeTypes": ["CONFIG"],
                    "focusRuleCodes": ["CONFIG_RELEASE_CHECK"],
                    "recommendedChecks": ["确认端侧配置和接口契约。"],
                }
            ),
            status="ENABLED",
            description="frontend",
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
                "old_path": "src/main/java/com/demo/order/RabbitMqBindingConfig.java",
                "new_path": "src/main/java/com/demo/order/RabbitMqBindingConfig.java",
                "diffText": '+ return new Queue("order-confirmed-queue", true, false, false);\n+ .with("order-confirmed-route");',
            },
        ],
    }


def mock_push_payload() -> dict:
    return {
        "object_kind": "push",
        "event_time": "2026-05-18T10:00:00+08:00",
        "project": {
            "id": 1001,
            "name": "demo-service",
            "path_with_namespace": "demo/service",
            "web_url": "https://gitlab.example.com/demo/service",
        },
        "ref": "refs/heads/master",
        "before": "1111111111111111111111111111111111111111",
        "after": "2222222222222222222222222222222222222222",
        "user_name": "Alice",
        "user_username": "alice",
        "commits": [
            {
                "id": "2222222222222222222222222222222222222222",
                "added": [],
                "modified": ["src/main/resources/mapper/OrderMapper.xml"],
                "removed": [],
            }
        ],
        "changedFiles": [
            {
                "path": "src/main/resources/mapper/OrderMapper.xml",
                "diffText": "+ update orders set status = 'CONFIRMED' where id = #{id}",
            }
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
    assert {"DB_DATA_WRITE", "CACHE_WRITE_DELETE", "MQ_CONFIG"}.issubset(
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
    assert result["changeAnalysis"]["changeTypes"] == ["DB", "DB_DATA_WRITE"]
    assert result["riskCard"]["riskItems"][0]["category"] == "DB_DATA_WRITE"
    artifact = result["riskCard"]["riskItems"][0]["maintenanceArtifacts"][0]
    assert artifact["artifactType"] == "SQL"
    assert artifact["confidence"] == "EXACT"
    assert "alter table orders add column risk_level varchar(32);" in artifact["content"]


def test_manual_review_target_type_uses_frontend_profile_and_hides_card(
    client: TestClient, db_session: Session
) -> None:
    seed_backend_template(db_session)
    seed_frontend_template(db_session)
    seed_project(db_session)

    response = client.post(
        "/api/review-tasks/manual",
        json={
            "projectId": 1,
            "targetType": "WEB_PC",
            "sourceBranch": "feature/web",
            "targetBranch": "main",
            "changedFiles": [
                {
                    "path": "frontend/src/pages/OrderPage.jsx",
                    "changeType": "MODIFIED",
                    "diffText": "+ const enabled = import.meta.env.VITE_ORDER_ENABLED;",
                }
            ],
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["targetType"] == "WEB_PC"
    assert data["profileCode"] == "web-pc-default-ai-review"
    assert data["reminderCardEnabled"] is False

    detail = client.get(f"/api/review-tasks/{data['taskId']}").json()["data"]
    assert detail["targetType"] == "WEB_PC"
    assert detail["codeQualityProfileCode"] == "web-pc-default-ai-review"

    result = client.get(f"/api/review-tasks/{data['taskId']}/result").json()["data"]
    assert result["targetType"] == "WEB_PC"
    assert result["reminderCardEnabled"] is False


def test_focus_rule_codes_strictly_filter_generated_risk_card(
    client: TestClient, db_session: Session
) -> None:
    seed_backend_template(db_session)
    seed_project(db_session)
    template = db_session.query(RuleTemplate).filter_by(template_code="backend-default").first()
    template.config_json = json.dumps(
        {
            "focusRuleCodes": ["CONFIG_RELEASE_CHECK"],
            "focusChangeTypes": ["CONFIG"],
            "recommendedChecks": [],
        }
    )
    db_session.commit()

    response = client.post(
        "/api/review-tasks/manual",
        json={
            "projectId": 1,
            "sourceBranch": "feature/focus",
            "targetBranch": "main",
            "changedFiles": [
                {
                    "path": "src/main/resources/mapper/OrderMapper.xml",
                    "diffText": "+ update orders set status = #{status} where id = #{id}",
                },
                {
                    "path": "src/main/resources/application.yml",
                    "diffText": "+ order:\n+   enabled: true",
                },
            ],
        },
    )

    assert response.status_code == 200
    result = client.get(f"/api/review-tasks/{response.json()['data']['taskId']}/result").json()["data"]
    assert [item["ruleCode"] for item in result["riskCard"]["riskItems"]] == ["CONFIG_RELEASE_CHECK"]


def test_task_result_regenerates_display_card_from_stored_change_analysis(
    client: TestClient, db_session: Session
) -> None:
    seed_backend_template(db_session)
    seed_project(db_session)

    response = client.post(
        "/api/review-tasks/manual",
        json={
            "projectId": 1,
            "sourceBranch": "feature/regenerate",
            "targetBranch": "main",
            "changedFiles": [
                {
                    "path": "src/main/java/com/demo/car/entity/FenceLearningModel.java",
                    "changeType": "ADDED",
                    "diffText": (
                        '+ @TableName("client_fence_learning_model")\n'
                        '+ public class FenceLearningModel {\n'
                        '+   @TableId(value = "id", type = IdType.ASSIGN_ID)\n'
                        '+   private Long id;\n'
                        '+   @TableField(value = "create_time", fill = FieldFill.INSERT)\n'
                        '+   private Date createTime;\n'
                        "+ }"
                    ),
                }
            ],
        },
    )
    task_id = response.json()["data"]["taskId"]
    review_result = db_session.query(ReviewResult).filter_by(task_id=task_id).one()
    stale_card = json.loads(review_result.risk_card_json)
    stale_card["riskItems"][0]["maintenanceArtifacts"] = [
        {
            "artifactType": "SQL",
            "title": "可维护 SQL 片段",
            "language": "sql",
            "content": '@TableField(value = "create_time", fill = FieldFill.INSERT);',
            "confidence": "EXACT",
            "copyable": True,
            "sourceFilePath": "src/main/java/com/demo/car/entity/FenceLearningModel.java",
            "sourceChangeType": "DB_DATA_WRITE",
            "notes": "stale",
        }
    ]
    review_result.risk_card_json = json.dumps(stale_card, ensure_ascii=False)
    db_session.commit()

    result = client.get(f"/api/review-tasks/{task_id}/result").json()["data"]
    artifact = result["riskCard"]["riskItems"][0]["maintenanceArtifacts"][0]
    assert artifact["confidence"] == "INFERRED"
    assert "CREATE TABLE client_fence_learning_model" in artifact["content"]
    assert "@TableField" not in artifact["content"]


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

    detail = client.get(f"/api/review-tasks/{data['taskId']}").json()["data"]
    assert detail["createdAt"] is not None
    assert detail["updatedAt"] is not None

    notifications = client.get(f"/api/review-tasks/{data['taskId']}/notifications").json()["data"]
    assert notifications[0]["createdAt"] is not None


def test_rerun_gitlab_push_task_replays_raw_payload(client: TestClient, db_session: Session) -> None:
    seed_backend_template(db_session)
    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mock_push_payload(),
        headers={"X-Gitlab-Event": "Push Hook"},
    ).json()["data"]

    rerun = client.post(f"/api/review-tasks/{created['taskId']}/rerun")

    assert rerun.status_code == 200
    data = rerun.json()["data"]
    assert data["sourceTaskId"] == created["taskId"]
    assert data["status"] == "SUCCESS"
    assert data["triggerType"] == "GITLAB_PUSH_WEBHOOK"
    assert data["taskId"] != created["taskId"]

    detail = client.get(f"/api/review-tasks/{data['taskId']}").json()["data"]
    assert detail["triggerType"] == "GITLAB_PUSH_WEBHOOK"
    assert detail["sourceBranch"] == "master"


def test_rerun_gitlab_task_in_place_reuses_existing_task(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_backend_template(db_session)
    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mock_mr_payload(),
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    ).json()["data"]
    task_id = created["taskId"]
    original_result = db_session.query(ReviewResult).filter_by(task_id=task_id).one()
    original_result.risk_card_json = json.dumps(
        {"riskLevel": "LOW", "riskItems": [], "summary": "stale"},
        ensure_ascii=False,
    )
    db_session.commit()

    rerun = client.post(f"/api/review-tasks/{task_id}/rerun-in-place")

    assert rerun.status_code == 200
    data = rerun.json()["data"]
    assert data["sourceTaskId"] == task_id
    assert data["taskId"] == task_id
    assert data["mode"] == "IN_PLACE"
    assert db_session.query(ReviewResult).filter_by(task_id=task_id).count() == 1
    result = client.get(f"/api/review-tasks/{task_id}/result").json()["data"]
    assert result["riskCard"]["summary"] != "stale"
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    assert detail["status"] == "SUCCESS"


def test_rerun_respects_global_dingtalk_notification_switch(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_backend_template(db_session)
    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mock_mr_payload(),
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    ).json()["data"]
    monkeypatch.setenv("DINGTALK_WEBHOOK_URL", "https://dingtalk.example.test/robot/send")
    settings = client.put(
        "/api/code-quality-reviews/settings",
        json={"dingtalkNotificationEnabled": False},
    )
    assert settings.status_code == 200

    with respx.mock(assert_all_called=False) as router:
        route = router.post("https://dingtalk.example.test/robot/send").mock(
            return_value=httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
        )
        rerun = client.post(f"/api/review-tasks/{created['taskId']}/rerun")

    assert rerun.status_code == 200
    new_task_id = rerun.json()["data"]["taskId"]
    notifications = client.get(f"/api/review-tasks/{new_task_id}/notifications").json()["data"]
    assert notifications[0]["status"] == "SKIPPED"
    assert notifications[0]["target"] == "DINGTALK_NOTIFICATION_ENABLED"
    assert route.called is False
