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
            "name": "demo-service",
            "gitProvider": "GITLAB",
            "gitProjectId": "1001",
            "repositoryUrl": "https://gitlab.example.com/demo/service",
            "defaultTemplateCode": "backend-default",
            "defaultCodeQualityProfileCode": "backend-default-ai-review",
            "defaultCodeQualityProviderCode": "DEEPSEEK",
            "status": "ENABLED",
        }
    ]

