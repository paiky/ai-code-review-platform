from datetime import datetime

import httpx
import respx
from sqlalchemy.orm import Session

from app.notification.models import NotificationWebhook, ProjectNotificationWebhook
from app.notification.repository import enabled_webhooks_for_task
from app.project_integration.models import Project
from app.review_record.models import ReviewTask


def _project(db_session: Session, project_id: int = 101) -> Project:
    project = Project(
        id=project_id,
        name=f"project-{project_id}",
        git_provider="GITLAB",
        git_project_id=str(project_id),
        repository_url=None,
        target_type="BACKEND",
        detected_target_types='["BACKEND"]',
        target_detection_json=None,
        default_template_code="backend-default",
        default_code_quality_profile_code=None,
        default_code_quality_provider_code=None,
        dingtalk_webhook_id=None,
        status="ENABLED",
        description=None,
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db_session.add(project)
    db_session.commit()
    return project


def test_notification_webhook_crud_masks_url_and_rejects_delete_when_associated(client, db_session):
    created = client.post(
        "/api/notification-webhooks",
        json={
            "name": "研发群",
            "webhookUrl": "https://dingtalk.example.test/robot/send?access_token=secret-token",
            "description": "通知群",
        },
    )
    assert created.status_code == 200
    webhook = created.json()["data"]
    assert "webhookUrl" not in webhook
    assert webhook["webhookMasked"].endswith("oken")
    webhook_id = webhook["id"]

    project = _project(db_session)
    preview = client.post(
        "/api/projects/notification-webhooks/batch/preview",
        json={"projectIds": [project.id], "webhookIds": [webhook_id], "mode": "ADD"},
    )
    assert preview.status_code == 200
    assert preview.json()["data"]["items"][0]["addedWebhookIds"] == [webhook_id]
    assert db_session.query(ProjectNotificationWebhook).count() == 0

    saved = client.put(
        "/api/projects/notification-webhooks/batch",
        json={"projectIds": [project.id], "webhookIds": [webhook_id], "mode": "ADD"},
    )
    assert saved.status_code == 200
    assert db_session.query(ProjectNotificationWebhook).count() == 1

    linked = client.get(f"/api/notification-webhooks/{webhook_id}/projects")
    assert linked.status_code == 200
    assert linked.json()["data"][0]["id"] == project.id

    rejected = client.delete(f"/api/notification-webhooks/{webhook_id}")
    assert rejected.status_code == 400
    assert rejected.json()["code"] == "VALIDATION_ERROR"

    removed = client.put(
        "/api/projects/notification-webhooks/batch",
        json={"projectIds": [project.id], "webhookIds": [webhook_id], "mode": "REMOVE"},
    )
    assert removed.status_code == 200
    deleted = client.delete(f"/api/notification-webhooks/{webhook_id}")
    assert deleted.status_code == 200


def test_notification_webhook_test_persists_success_without_returning_url(client):
    created = client.post(
        "/api/notification-webhooks",
        json={
            "name": "测试群",
            "webhookUrl": "https://dingtalk.example.test/robot/send?access_token=test-token",
        },
    )
    webhook_id = created.json()["data"]["id"]
    with respx.mock(assert_all_called=True) as router:
        route = router.post(
            "https://dingtalk.example.test/robot/send?access_token=test-token"
        ).mock(return_value=httpx.Response(200, json={"errcode": 0, "errmsg": "ok"}))
        response = client.post(f"/api/notification-webhooks/{webhook_id}/test")
    assert route.called
    assert response.status_code == 200
    assert response.json()["data"]["test"]["status"] == "SUCCESS"
    assert response.json()["data"]["webhook"]["lastTestStatus"] == "SUCCESS"
    assert "webhookUrl" not in response.json()["data"]["webhook"]


def test_task_notification_reads_project_associations(client, db_session):
    project = _project(db_session, 102)
    task = ReviewTask(
        id=9001,
        project_id=project.id,
        trigger_type="MANUAL",
        template_code="backend-default",
        status="SUCCESS",
        review_status="NOT_TRIGGERED",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    webhook = NotificationWebhook(
        name="项目群",
        channel="DINGTALK",
        webhook_url="https://dingtalk.example.test/robot/send?access_token=project-token",
        status="ENABLED",
        enabled=True,
        last_test_status="SUCCESS",
        created_at=datetime.now(),
        updated_at=datetime.now(),
    )
    db_session.add_all([task, webhook])
    db_session.flush()
    db_session.add(
        ProjectNotificationWebhook(
            project_id=project.id,
            webhook_id=webhook.id,
            enabled=True,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
    )
    db_session.commit()
    assert [item.id for item in enabled_webhooks_for_task(db_session, task.id)] == [webhook.id]
    notifications = client.get("/api/review-tasks/9001/notifications")
    assert notifications.status_code == 200

def test_notification_webhook_test_skips_without_disabling_when_dingtalk_disabled(client, db_session, monkeypatch):
    created = client.post(
        "/api/notification-webhooks",
        json={
            "name": "关闭测试群",
            "webhookUrl": "https://dingtalk.example.test/robot/send?access_token=skip-token",
        },
    )
    webhook_id = created.json()["data"]["id"]
    monkeypatch.setenv("DINGTALK_ENABLED", "false")
    response = client.post(f"/api/notification-webhooks/{webhook_id}/test")
    assert response.status_code == 200
    assert response.json()["data"]["test"]["status"] == "SKIPPED"
    saved = db_session.get(NotificationWebhook, webhook_id)
    assert saved.enabled is True
    assert saved.last_test_status == "SKIPPED"
