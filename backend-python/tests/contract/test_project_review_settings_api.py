from datetime import datetime
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityReviewResult
from app.project_integration.models import ProjectReviewSettings
from app.rule_template.models import RuleTemplate


def create_project(client: TestClient, git_project_id: str = "stage3-project") -> dict:
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


def seed_backend_template(db_session: Session) -> None:
    now = datetime(2026, 8, 25, 10, 0, 0)
    db_session.add(
        RuleTemplate(
            template_code="backend-default",
            template_name="Backend default",
            target_type="BACKEND",
            version=1,
            enabled_rule_codes="[]",
            config_json=json.dumps(
                {
                    "focusChangeTypes": [],
                    "focusRuleCodes": [],
                    "recommendedChecks": [],
                }
            ),
            status="ENABLED",
            description="stage3 project review settings contract",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()


def mr_payload(git_project_id: str) -> dict:
    return {
        "object_kind": "merge_request",
        "project": {
            "id": git_project_id,
            "name": f"project-{git_project_id}",
            "path_with_namespace": f"demo/{git_project_id}",
            "web_url": f"https://gitlab.example.com/demo/{git_project_id}",
        },
        "object_attributes": {
            "iid": 25,
            "action": "open",
            "source_branch": "feature/stage3",
            "target_branch": "main",
            "last_commit": {"id": "abcdef123456"},
        },
        "changedFiles": [
            {
                "path": "src/main/java/com/demo/OrderService.java",
                "diffText": "+ public void review() {}",
            }
        ],
    }


def test_project_creation_persists_default_review_settings(
    client: TestClient,
    db_session: Session,
) -> None:
    project = create_project(client)

    response = client.get(f"/api/projects/{project['id']}/review-settings")

    assert response.status_code == 200
    settings = response.json()["data"]
    assert settings == {
        "projectId": project["id"],
        "source": "PROJECT",
        "triggerOnMr": True,
        "triggerOnPush": False,
        "triggerOnlyWhenRiskMatched": False,
        "autoFixPreviewEnabled": False,
        "autoFixPreviewSeverities": ["MAJOR"],
        "pushBranchPatterns": ["master"],
        "pushMinChangedFiles": 10,
        "pushMinDiffBytes": 30000,
        "pushMinCommitCount": 3,
        "pushMaxChangedFiles": -1,
        "pushMaxDiffBytes": -1,
        "pushDebounceSeconds": 300,
    }
    stored = db_session.get(ProjectReviewSettings, project["id"])
    assert stored is not None
    assert stored.created_at is not None
    assert stored.updated_at is not None


def test_project_review_settings_support_partial_updates_and_validation(client: TestClient) -> None:
    project = create_project(client, "stage3-update")

    updated = client.put(
        f"/api/projects/{project['id']}/review-settings",
        json={
            "triggerOnMr": False,
            "triggerOnPush": True,
            "triggerOnlyWhenRiskMatched": True,
            "autoFixPreviewEnabled": True,
            "autoFixPreviewSeverities": ["CRITICAL", "MINOR"],
            "pushBranchPatterns": ["release/*", "hotfix/*"],
            "pushMinChangedFiles": 2,
            "pushMinDiffBytes": 1024,
            "pushMinCommitCount": 1,
            "pushMaxChangedFiles": 80,
            "pushMaxDiffBytes": 500000,
            "pushDebounceSeconds": 60,
        },
    )

    assert updated.status_code == 200
    settings = updated.json()["data"]
    assert settings["source"] == "PROJECT"
    assert settings["triggerOnMr"] is False
    assert settings["triggerOnPush"] is True
    assert settings["triggerOnlyWhenRiskMatched"] is True
    assert settings["autoFixPreviewSeverities"] == ["CRITICAL", "MINOR"]
    assert settings["pushBranchPatterns"] == ["release/*", "hotfix/*"]
    assert settings["pushMinChangedFiles"] == 2
    assert settings["pushDebounceSeconds"] == 60

    unknown = client.put(
        f"/api/projects/{project['id']}/review-settings",
        json={"unsupportedField": True},
    )
    invalid_limit = client.put(
        f"/api/projects/{project['id']}/review-settings",
        json={"pushMaxChangedFiles": -2},
    )
    blank_patterns = client.put(
        f"/api/projects/{project['id']}/review-settings",
        json={"pushBranchPatterns": ["  "]},
    )
    assert unknown.status_code == 400
    assert invalid_limit.status_code == 400
    assert blank_patterns.status_code == 400


@pytest.mark.parametrize(
    ("trigger_on_mr", "trigger_on_push"),
    [(True, False), (False, True), (True, True), (False, False)],
)
def test_project_review_settings_preserve_all_trigger_combinations(
    client: TestClient,
    trigger_on_mr: bool,
    trigger_on_push: bool,
) -> None:
    project = create_project(client, f"combination-{int(trigger_on_mr)}-{int(trigger_on_push)}")

    response = client.put(
        f"/api/projects/{project['id']}/review-settings",
        json={
            "triggerOnMr": trigger_on_mr,
            "triggerOnPush": trigger_on_push,
        },
    )

    assert response.status_code == 200
    settings = response.json()["data"]
    assert settings["triggerOnMr"] is trigger_on_mr
    assert settings["triggerOnPush"] is trigger_on_push


def test_webhook_created_project_gets_defaults_and_mr_switch_controls_auto_review(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_backend_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    project = create_project(client, "stage3-mr-disabled")
    disabled = client.put(
        f"/api/projects/{project['id']}/review-settings",
        json={"triggerOnMr": False},
    )
    assert disabled.status_code == 200

    response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mr_payload("stage3-mr-disabled"),
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    assert db_session.scalar(
        select(CodeQualityReviewResult).where(CodeQualityReviewResult.task_id == task_id)
    ) is None
    stored = db_session.get(ProjectReviewSettings, project["id"])
    assert stored is not None
    assert stored.trigger_on_mr is False

def test_gitlab_webhook_auto_created_project_persists_default_review_settings(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_backend_template(db_session)

    response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mr_payload("stage3-webhook-auto"),
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )

    assert response.status_code == 200
    projects = client.get("/api/projects").json()["data"]["items"]
    project = next(item for item in projects if item["gitProjectId"] == "stage3-webhook-auto")
    stored = db_session.get(ProjectReviewSettings, project["id"])
    assert stored is not None
    assert stored.trigger_on_mr is True
    assert stored.trigger_on_push is False
    assert json.loads(stored.push_branch_patterns) == ["master"]
