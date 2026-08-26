import json
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.notification.models import (
    NotificationWebhook,
    ProjectNotificationWebhook,
)
from app.project_integration.models import (
    Project,
    ProjectAiReviewModel,
    ProjectReviewSettings,
    ProjectTargetConfig,
)


def create_project(
    client: TestClient,
    name: str,
    git_project_id: str,
    target_type: str,
) -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "gitProvider": "GITLAB",
            "gitProjectId": git_project_id,
            "repositoryUrl": f"https://gitlab.example.com/demo/{name}",
            "targetType": target_type,
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def create_webhook(client: TestClient, name: str) -> dict:
    response = client.post(
        "/api/notification-webhooks",
        json={
            "name": name,
            "webhookUrl": (
                "https://oapi.dingtalk.com/robot/send?access_token="
                f"stage5-prerequisite-{name}"
            ),
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def associate_webhooks(
    client: TestClient,
    project_ids: list[int],
    webhook_ids: list[int],
) -> None:
    response = client.put(
        "/api/projects/notification-webhooks/batch",
        json={
            "projectIds": project_ids,
            "webhookIds": webhook_ids,
            "mode": "REPLACE",
        },
    )
    assert response.status_code == 200


def test_project_center_list_filters_pages_and_returns_status_summaries(
    client: TestClient,
    db_session: Session,
) -> None:
    alpha = create_project(client, "alpha-backend", "501-alpha", "BACKEND")
    beta = create_project(client, "beta-general", "502-beta", "GENERAL")
    gamma = create_project(client, "gamma-android", "503-gamma", "APP_ANDROID")

    failed_webhook = create_webhook(client, "alpha-failed-health")
    associate_webhooks(client, [alpha["id"]], [failed_webhook["id"]])
    failed_record = db_session.get(NotificationWebhook, failed_webhook["id"])
    failed_record.last_test_status = "FAILED"
    failed_record.last_test_message = "safe contract fixture"
    failed_record.last_test_at = datetime(2026, 8, 25, 12, 0, 0)

    disabled_webhook = create_webhook(client, "gamma-disabled")
    disabled_response = client.put(
        f"/api/notification-webhooks/{disabled_webhook['id']}",
        json={"enabled": False},
    )
    assert disabled_response.status_code == 200
    associate_webhooks(client, [gamma["id"]], [disabled_webhook["id"]])
    db_session.commit()

    page_response = client.get(
        "/api/projects",
        params={"pageNo": 1, "pageSize": 2},
    )
    assert page_response.status_code == 200
    page = page_response.json()["data"]
    assert page["pageNo"] == 1
    assert page["pageSize"] == 2
    assert page["total"] == 3
    assert [item["id"] for item in page["items"]] == [
        gamma["id"],
        beta["id"],
    ]

    alpha_response = client.get(
        "/api/projects",
        params={
            "keyword": "501-alpha",
            "targetType": "BACKEND",
            "pageNo": 1,
            "pageSize": 20,
        },
    )
    assert alpha_response.status_code == 200
    alpha_item = alpha_response.json()["data"]["items"][0]
    assert alpha_item["reviewProfileCode"] == "backend-default-ai-review"
    assert alpha_item["reviewModelNames"]
    assert alpha_item["reviewStatus"] == "CONFIGURED"
    assert alpha_item["triggerOnMr"] is True
    assert alpha_item["triggerOnPush"] is False
    assert alpha_item["notificationStatus"] == "CONFIGURED"
    assert alpha_item["healthWarning"] is True
    assert alpha_item["webhooks"][0]["lastTestStatus"] == "FAILED"
    assert "stage5-prerequisite" not in alpha_item["webhooks"][0]["webhookMasked"]

    configured = client.get(
        "/api/projects",
        params={"notificationStatus": "CONFIGURED", "pageNo": 1, "pageSize": 20},
    ).json()["data"]
    assert [item["id"] for item in configured["items"]] == [alpha["id"]]

    warning = client.get(
        "/api/projects",
        params={"notificationStatus": "HEALTH_WARNING", "pageNo": 1, "pageSize": 20},
    ).json()["data"]
    assert [item["id"] for item in warning["items"]] == [alpha["id"]]

    abnormal = client.get(
        "/api/projects",
        params={"notificationStatus": "ABNORMAL", "pageNo": 1, "pageSize": 20},
    ).json()["data"]
    assert [item["id"] for item in abnormal["items"]] == [gamma["id"]]

    unconfigured_review = client.get(
        "/api/projects",
        params={"reviewStatus": "UNCONFIGURED", "pageNo": 1, "pageSize": 20},
    ).json()["data"]
    assert [item["id"] for item in unconfigured_review["items"]] == [beta["id"]]


def test_project_configuration_defaults_cover_all_target_types(
    client: TestClient,
) -> None:
    expected = {
        "BACKEND": ("backend-default", "backend-default-ai-review", True),
        "WEB_PC": ("frontend-default", "web-pc-default-ai-review", False),
        "APP_IOS": ("frontend-default", "app-ios-default-ai-review", False),
        "APP_ANDROID": (
            "frontend-default",
            "app-android-default-ai-review",
            False,
        ),
        "APP_CROSS_PLATFORM": (
            "frontend-default",
            "app-cross-platform-default-ai-review",
            False,
        ),
        "GENERAL": ("general-default", None, False),
    }

    for target_type, (
        template_code,
        profile_code,
        reminder_enabled,
    ) in expected.items():
        response = client.get(
            "/api/projects/configuration-defaults",
            params={"targetType": target_type},
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["targetType"] == target_type
        config = data["targetConfig"]
        assert config["targetType"] == target_type
        assert config["templateCode"] == template_code
        assert config["codeQualityProfileCode"] == profile_code
        assert config["providerCode"] is None
        assert config["pathPatterns"]
        assert config["reminderCardEnabled"] is reminder_enabled

    invalid = client.get(
        "/api/projects/configuration-defaults",
        params={"targetType": "UNKNOWN"},
    )
    assert invalid.status_code == 400


def test_restore_auto_detection_previews_and_applies_without_touching_relations(
    client: TestClient,
    db_session: Session,
) -> None:
    project = create_project(
        client,
        "restore-detection",
        "504-restore",
        "BACKEND",
    )
    project_id = int(project["id"])
    project_record = db_session.get(Project, project_id)
    project_record.detected_target_types = '["WEB_PC", "BACKEND"]'
    project_record.target_detection_json = json.dumps(
        {
            "targetTypes": ["WEB_PC", "BACKEND"],
            "evidences": [
                {
                    "targetType": "WEB_PC",
                    "source": "PATH_MAPPING",
                    "value": "frontend/src/App.jsx",
                    "pattern": "frontend/**",
                    "reason": "frontend/src/App.jsx matches frontend/**",
                },
                {
                    "targetType": "BACKEND",
                    "source": "PATH_MAPPING",
                    "value": "backend-python/app/main.py",
                    "pattern": "backend-python/**",
                    "reason": "backend-python/app/main.py matches backend-python/**",
                },
            ],
            "updatedAt": "2026-08-25T12:00:00",
        },
        ensure_ascii=False,
    )
    db_session.add(
        ProjectAiReviewModel(
            project_id=project_id,
            review_key="preserved-model",
            provider_code="DEEPSEEK",
            model_name="deepseek-preserved",
            display_name="Preserved model",
            enabled=True,
            sort_order=10,
            created_at=datetime(2026, 8, 25, 12, 0, 0),
            updated_at=datetime(2026, 8, 25, 12, 0, 0),
        )
    )
    review_settings = db_session.get(ProjectReviewSettings, project_id)
    review_settings.trigger_on_push = True
    db_session.commit()

    webhook = create_webhook(client, "restore-preserved")
    associate_webhooks(client, [project_id], [webhook["id"]])
    before_relation_count = len(
        db_session.scalars(
            select(ProjectNotificationWebhook).where(
                ProjectNotificationWebhook.project_id == project_id
            )
        ).all()
    )

    preview_response = client.get(
        f"/api/projects/{project_id}/target-type-auto-detection/preview"
    )
    assert preview_response.status_code == 200
    preview = preview_response.json()["data"]
    assert preview["currentTargetType"] == "BACKEND"
    assert preview["detectedTargetType"] == "WEB_PC"
    assert preview["detectedTargetTypes"] == ["WEB_PC", "BACKEND"]
    assert len(preview["evidenceVersion"]) == 64
    assert preview["targetConfig"]["templateCode"] == "frontend-default"
    changed_fields = {item["field"] for item in preview["changes"]}
    assert {
        "targetType",
        "templateCode",
        "codeQualityProfileCode",
        "reminderCardEnabled",
    }.issubset(changed_fields)
    assert db_session.get(Project, project_id).target_type == "BACKEND"

    mismatched = client.put(
        f"/api/projects/{project_id}/target-type-auto-detection",
        json={
            "targetType": "APP_ANDROID",
            "evidenceVersion": preview["evidenceVersion"],
        },
    )
    assert mismatched.status_code == 409
    assert mismatched.json()["code"] == "PROJECT_TARGET_DETECTION_STALE"

    apply_response = client.put(
        f"/api/projects/{project_id}/target-type-auto-detection",
        json={
            "targetType": preview["detectedTargetType"],
            "evidenceVersion": preview["evidenceVersion"],
        },
    )
    assert apply_response.status_code == 200
    applied = apply_response.json()["data"]
    assert applied["appliedTargetType"] == "WEB_PC"
    assert applied["configuration"]["targetType"] == "WEB_PC"
    assert applied["configuration"]["targetConfig"]["providerCode"] is None

    db_session.expire_all()
    restored_project = db_session.get(Project, project_id)
    assert restored_project.target_type == "WEB_PC"
    configs = db_session.scalars(
        select(ProjectTargetConfig).where(
            ProjectTargetConfig.project_id == project_id
        )
    ).all()
    enabled_configs = [config for config in configs if config.enabled]
    assert len(enabled_configs) == 1
    assert enabled_configs[0].target_type == "WEB_PC"
    assert enabled_configs[0].description == "恢复自动识别的端类型配置"
    assert db_session.get(ProjectReviewSettings, project_id).trigger_on_push is True
    assert [
        model.review_key
        for model in db_session.scalars(
            select(ProjectAiReviewModel).where(
                ProjectAiReviewModel.project_id == project_id
            )
        ).all()
    ] == ["preserved-model"]
    assert len(
        db_session.scalars(
            select(ProjectNotificationWebhook).where(
                ProjectNotificationWebhook.project_id == project_id
            )
        ).all()
    ) == before_relation_count

    repeated = client.put(
        f"/api/projects/{project_id}/target-type-auto-detection",
        json={
            "targetType": preview["detectedTargetType"],
            "evidenceVersion": preview["evidenceVersion"],
        },
    )
    assert repeated.status_code == 200
    assert repeated.json()["data"]["configuration"]["targetType"] == "WEB_PC"

    current_preview = client.get(
        f"/api/projects/{project_id}/target-type-auto-detection/preview"
    ).json()["data"]
    restored_project.target_detection_json = restored_project.target_detection_json.replace(
        "2026-08-25T12:00:00",
        "2026-08-25T12:05:00",
    )
    db_session.commit()
    stale = client.put(
        f"/api/projects/{project_id}/target-type-auto-detection",
        json={
            "targetType": current_preview["detectedTargetType"],
            "evidenceVersion": current_preview["evidenceVersion"],
        },
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "PROJECT_TARGET_DETECTION_STALE"


def test_restore_auto_detection_rejects_missing_evidence(
    client: TestClient,
) -> None:
    project = create_project(
        client,
        "manual-without-evidence",
        "505-no-evidence",
        "BACKEND",
    )

    response = client.get(
        f"/api/projects/{project['id']}/target-type-auto-detection/preview"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "PROJECT_TARGET_DETECTION_UNAVAILABLE"

