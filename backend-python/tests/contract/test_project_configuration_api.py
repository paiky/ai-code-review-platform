from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.notification.models import ProjectNotificationWebhook
from app.project_integration.models import (
    Project,
    ProjectAiReviewModel,
    ProjectReviewSettings,
    ProjectTargetConfig,
)
from app.rule_template.models import RuleTemplate


def create_project(client: TestClient, git_project_id: str = "stage4-project") -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": f"project-{git_project_id}",
            "gitProvider": "GITLAB",
            "gitProjectId": git_project_id,
            "repositoryUrl": f"https://gitlab.example.com/demo/{git_project_id}",
            "targetType": "BACKEND",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def seed_template(db_session: Session, template_code: str, target_type: str) -> None:
    now = datetime(2026, 8, 25, 10, 0, 0)
    db_session.add(
        RuleTemplate(
            template_code=template_code,
            template_name=template_code,
            target_type=target_type,
            version=1,
            enabled_rule_codes="[]",
            config_json=(
                '{"focusChangeTypes":[],"focusRuleCodes":[],"recommendedChecks":[]}'
            ),
            status="ENABLED",
            description="stage4 configuration contract",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()


def create_webhook(client: TestClient, name: str) -> int:
    response = client.post(
        "/api/notification-webhooks",
        json={
            "name": name,
            "webhookUrl": (
                "https://oapi.dingtalk.com/robot/send?access_token="
                f"stage4-{name}"
            ),
        },
    )
    assert response.status_code == 200
    return int(response.json()["data"]["id"])


def configuration_payload(webhook_ids: list[int]) -> dict:
    return {
        "targetType": "WEB_PC",
        "targetConfig": {
            "templateCode": "frontend-default",
            "codeQualityProfileCode": "web-pc-default-ai-review",
            "providerCode": None,
            "pathPatterns": ["**/*"],
            "reminderCardEnabled": False,
        },
        "aiReviewModels": [
            {
                "reviewKey": "deepseek-main",
                "providerCode": "DEEPSEEK",
                "modelName": "deepseek-v4-pro",
                "displayName": "DeepSeek primary",
                "enabled": True,
                "sortOrder": 10,
            },
            {
                "reviewKey": "mimo-secondary",
                "providerCode": "XIAOMIMO",
                "modelName": "mimo-v2.5-pro",
                "displayName": "MiMo secondary",
                "enabled": True,
                "sortOrder": 20,
            },
        ],
        "reviewSettings": {
            "triggerOnMr": True,
            "triggerOnPush": True,
            "triggerOnlyWhenRiskMatched": True,
            "autoFixPreviewEnabled": True,
            "autoFixPreviewSeverities": ["CRITICAL", "MAJOR"],
            "pushBranchPatterns": ["main", "release/*"],
            "pushMinChangedFiles": 2,
            "pushMinDiffBytes": 1024,
            "pushMinCommitCount": 1,
            "pushMaxChangedFiles": 80,
            "pushMaxDiffBytes": 500000,
            "pushDebounceSeconds": 60,
        },
        "webhookIds": webhook_ids,
    }


def test_project_configuration_get_returns_single_target_defaults(
    client: TestClient,
) -> None:
    project = create_project(client)

    response = client.get(f"/api/projects/{project['id']}/configuration")

    assert response.status_code == 200
    configuration = response.json()["data"]
    assert configuration["targetType"] == "BACKEND"
    assert configuration["targetTypes"] == ["BACKEND"]
    assert configuration["targetConfig"]["targetType"] == "BACKEND"
    assert configuration["targetConfig"]["enabled"] is True
    assert configuration["aiReviewModels"] == []
    assert configuration["reviewSettings"]["source"] == "PROJECT"
    assert configuration["webhookIds"] == []


def test_project_configuration_put_saves_all_domains_in_one_transaction(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_template(db_session, "frontend-default", "FRONTEND")
    assert client.get("/api/code-quality-review-profiles").status_code == 200
    project = create_project(client, "stage4-save")
    webhook_ids = [
        create_webhook(client, "frontend-primary"),
        create_webhook(client, "frontend-backup"),
    ]

    response = client.put(
        f"/api/projects/{project['id']}/configuration",
        json=configuration_payload(webhook_ids),
    )

    assert response.status_code == 200
    configuration = response.json()["data"]
    assert configuration["targetType"] == "WEB_PC"
    assert configuration["targetTypes"] == ["WEB_PC"]
    assert configuration["targetConfig"]["codeQualityProfileCode"] == (
        "web-pc-default-ai-review"
    )
    assert [item["reviewKey"] for item in configuration["aiReviewModels"]] == [
        "deepseek-main",
        "mimo-secondary",
    ]
    assert configuration["reviewSettings"]["triggerOnPush"] is True
    assert configuration["webhookIds"] == webhook_ids
    filtered = client.get("/api/projects?targetType=WEB_PC").json()["data"]
    assert filtered["total"] == 1
    assert filtered["items"][0]["id"] == project["id"]
    assert client.get("/api/projects?targetType=BACKEND").json()["data"]["total"] == 0

    stored_project = db_session.get(Project, project["id"])
    assert stored_project is not None
    assert stored_project.target_type == "WEB_PC"
    assert stored_project.supported_target_types == '["WEB_PC"]'
    configs = db_session.scalars(
        select(ProjectTargetConfig).where(
            ProjectTargetConfig.project_id == project["id"]
        )
    ).all()
    assert sum(bool(item.enabled) for item in configs) == 1
    assert next(item for item in configs if item.enabled).target_type == "WEB_PC"
    assert len(
        db_session.scalars(
            select(ProjectAiReviewModel).where(
                ProjectAiReviewModel.project_id == project["id"]
            )
        ).all()
    ) == 2
    assert db_session.get(ProjectReviewSettings, project["id"]).trigger_on_push is True
    relations = db_session.scalars(
        select(ProjectNotificationWebhook).where(
            ProjectNotificationWebhook.project_id == project["id"]
        )
    ).all()
    assert [int(item.webhook_id) for item in relations] == webhook_ids


def test_project_configuration_failure_rolls_back_and_fixed_target_drives_tasks(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_template(db_session, "frontend-default", "FRONTEND")
    seed_template(db_session, "backend-default", "BACKEND")
    assert client.get("/api/code-quality-review-profiles").status_code == 200
    project = create_project(client, "stage4-fixed-target")
    saved = client.put(
        f"/api/projects/{project['id']}/configuration",
        json=configuration_payload([]),
    )
    assert saved.status_code == 200

    invalid = configuration_payload([])
    invalid["targetType"] = "BACKEND"
    invalid["targetConfig"] = {
        "templateCode": "backend-default",
        "codeQualityProfileCode": "backend-default-ai-review",
        "providerCode": None,
        "pathPatterns": ["**/*"],
        "reminderCardEnabled": True,
    }
    invalid["aiReviewModels"] = [
        {
            "reviewKey": "duplicate-a",
            "providerCode": "DEEPSEEK",
            "modelName": "same-model",
            "enabled": True,
            "sortOrder": 10,
        },
        {
            "reviewKey": "duplicate-b",
            "providerCode": "DEEPSEEK",
            "modelName": "same-model",
            "enabled": True,
            "sortOrder": 20,
        },
    ]

    rejected = client.put(
        f"/api/projects/{project['id']}/configuration",
        json=invalid,
    )

    assert rejected.status_code == 400
    after_rejection = client.get(
        f"/api/projects/{project['id']}/configuration"
    ).json()["data"]
    assert after_rejection["targetType"] == "WEB_PC"
    assert [item["reviewKey"] for item in after_rejection["aiReviewModels"]] == [
        "deepseek-main",
        "mimo-secondary",
    ]

    manual = client.post(
        "/api/review-tasks/manual",
        json={
            "projectId": project["id"],
            "targetType": "BACKEND",
            "targetTypes": ["BACKEND", "APP_ANDROID"],
            "changedFiles": [
                {
                    "path": "src/main/java/com/demo/OrderService.java",
                    "diffText": "+ class OrderService {}",
                }
            ],
        },
    )
    assert manual.status_code == 200
    task_id = manual.json()["data"]["taskId"]
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    assert detail["targetType"] == "WEB_PC"
    assert detail["targetTypes"] == ["WEB_PC"]
    assert detail["codeQualityProfileCode"] == "web-pc-default-ai-review"

def test_project_creation_rejects_multiple_target_types(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/projects",
        json={
            "name": "invalid-multi-target",
            "gitProvider": "GITLAB",
            "gitProjectId": "stage4-invalid-multi",
            "targetTypes": ["BACKEND", "WEB_PC"],
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
