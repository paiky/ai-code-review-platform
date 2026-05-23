from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.project_integration.models import Project


def test_projects_api_returns_enabled_projects_page(client: TestClient, db_session: Session) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add_all(
        [
            Project(
                id=1,
                name="disabled-service",
                git_provider="GITLAB",
                git_project_id="900",
                repository_url="https://gitlab.example.com/demo/disabled",
                default_template_code="backend-default",
                default_code_quality_profile_code="backend-default-ai-review",
                default_code_quality_provider_code=None,
                dingtalk_webhook_id=None,
                status="DISABLED",
                description=None,
                created_at=now,
                updated_at=now,
            ),
            Project(
                id=2,
                name="demo-service",
                git_provider="GITLAB",
                git_project_id="1001",
                repository_url="https://gitlab.example.com/demo/service",
                default_template_code="backend-default",
                default_code_quality_profile_code="backend-default-ai-review",
                default_code_quality_provider_code="DEEPSEEK",
                dingtalk_webhook_id=None,
                status="ENABLED",
                description=None,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/projects")

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] == 1
    assert body["data"]["pageNo"] == 1
    assert body["data"]["pageSize"] == 1
    assert body["data"]["items"] == [
        {
            "id": 2,
            "groupId": 1,
            "groupName": "默认项目组",
            "name": "demo-service",
            "gitProvider": "GITLAB",
            "gitProjectId": "1001",
            "repositoryUrl": "https://gitlab.example.com/demo/service",
            "supportedTargetTypes": ["BACKEND"],
            "defaultTemplateCode": "backend-default",
            "defaultCodeQualityProfileCode": "backend-default-ai-review",
            "defaultCodeQualityProviderCode": "DEEPSEEK",
            "status": "ENABLED",
        }
    ]


def test_project_groups_and_target_configs_can_be_managed(client: TestClient, db_session: Session) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add(
        Project(
            id=10,
            name="multi-client",
            git_provider="GITLAB",
            git_project_id="2001",
            repository_url="https://gitlab.example.com/demo/multi-client",
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

    group_response = client.post(
        "/api/project-groups",
        json={"groupName": "移动业务组", "groupCode": "mobile"},
    )
    assert group_response.status_code == 200
    group = group_response.json()["data"]

    bind_response = client.put("/api/projects/10/group", json={"groupId": group["id"]})
    assert bind_response.status_code == 200
    assert bind_response.json()["data"]["groupName"] == "移动业务组"

    update_response = client.put(
        "/api/projects/10/target-configs/WEB_PC",
        json={
            "templateCode": "frontend-default",
            "codeQualityProfileCode": "web-pc-default-ai-review",
            "pathPatterns": ["frontend/**"],
            "reminderCardEnabled": False,
            "enabled": True,
        },
    )
    assert update_response.status_code == 200
    config = update_response.json()["data"]
    assert config["targetType"] == "WEB_PC"
    assert config["codeQualityProfileCode"] == "web-pc-default-ai-review"
    assert config["pathPatterns"] == ["frontend/**"]
    assert config["reminderCardEnabled"] is False

    configs_response = client.get("/api/projects/10/target-configs")
    assert configs_response.status_code == 200
    target_types = {item["targetType"] for item in configs_response.json()["data"]}
    assert {"BACKEND", "WEB_PC"}.issubset(target_types)
