from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.project_integration.models import Project, ProjectTargetConfig
from app.rule_template.models import RuleTemplate


DEFAULT_PUSH_POLICY = {
    "pushBranchPatterns": ["master"],
    "pushMinChangedFiles": 10,
    "pushMinDiffBytes": 30000,
    "pushMinCommitCount": 3,
    "pushMaxChangedFiles": -1,
    "pushMaxDiffBytes": -1,
    "pushDebounceSeconds": 300,
}


def seed_template(db_session: Session, template_code: str, target_type: str) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add(
        RuleTemplate(
            template_code=template_code,
            template_name=template_code,
            target_type=target_type,
            version=1,
            enabled_rule_codes="[]",
            config_json='{"focusChangeTypes":[],"focusRuleCodes":[],"recommendedChecks":[]}',
            status="ENABLED",
            description=None,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()


def mr_payload(project_id: int, project_name: str, changed_files: list[dict]) -> dict:
    return {
        "object_kind": "merge_request",
        "event_time": "2026-05-18T10:00:00+08:00",
        "project": {
            "id": project_id,
            "name": project_name,
            "path_with_namespace": project_name,
            "web_url": f"https://gitlab.example.com/{project_name}",
        },
        "object_attributes": {
            "iid": 12,
            "action": "open",
            "source_branch": "feature/target-detect",
            "target_branch": "main",
            "url": f"https://gitlab.example.com/{project_name}/-/merge_requests/12",
            "last_commit": {"id": "abcdef123456"},
        },
        "user": {"name": "Alice", "username": "alice"},
        "changedFiles": changed_files,
    }


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
    item = body["data"]["items"][0]
    assert {
        key: item[key]
        for key in (
            "id",
            "name",
            "gitProvider",
            "gitProjectId",
            "repositoryUrl",
            "targetType",
            "supportedTargetTypes",
            "detectedTargetTypes",
            "targetDetection",
            "status",
        )
    } == {
        "id": 2,
        "name": "demo-service",
        "gitProvider": "GITLAB",
        "gitProjectId": "1001",
        "repositoryUrl": "https://gitlab.example.com/demo/service",
        "targetType": "BACKEND",
        "supportedTargetTypes": ["BACKEND"],
        "detectedTargetTypes": [],
        "targetDetection": None,
        "status": "ENABLED",
    }
    assert item["groupId"] == 1
    assert item["groupName"]
    assert item["reviewProfileCode"] == "backend-default-ai-review"
    assert item["reviewModelNames"]
    assert item["triggerOnMr"] is True
    assert item["triggerOnPush"] is False
    assert item["reviewStatus"] == "CONFIGURED"
    assert item["notificationStatus"] == "UNCONFIGURED"
    assert item["healthWarning"] is False
    assert item["webhooks"] == []

    include_disabled_response = client.get("/api/projects?includeDisabled=true")
    assert include_disabled_response.status_code == 200
    include_disabled_body = include_disabled_response.json()["data"]
    assert include_disabled_body["total"] == 2
    assert {item["name"] for item in include_disabled_body["items"]} == {"disabled-service", "demo-service"}


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
    assert group["defaultCodeQualityProfileCode"] is None
    assert {key: group[key] for key in DEFAULT_PUSH_POLICY} == DEFAULT_PUSH_POLICY

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
    configs = configs_response.json()["data"]
    target_types = {item["targetType"] for item in configs}
    assert {"BACKEND", "WEB_PC"}.issubset(target_types)
    assert sum(bool(item["enabled"]) for item in configs) == 1
    assert next(item for item in configs if item["enabled"])["targetType"] == "WEB_PC"


def test_get_project_target_configs_does_not_write_default_config(client: TestClient, db_session: Session) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add(
        Project(
            id=11,
            name="legacy-without-target-config",
            git_provider="GITLAB",
            git_project_id="2011",
            repository_url="https://gitlab.example.com/demo/legacy",
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

    response = client.get("/api/projects/11/target-configs")

    assert response.status_code == 200
    configs = response.json()["data"]
    assert configs[0]["id"] is None
    assert configs[0]["targetType"] == "BACKEND"
    assert db_session.query(ProjectTargetConfig).filter_by(project_id=11).count() == 0


def test_project_group_validation_rejects_duplicate_code_and_default_disable(client: TestClient) -> None:
    first_response = client.post(
        "/api/project-groups",
        json={"groupName": "移动业务组", "groupCode": "mobile"},
    )
    assert first_response.status_code == 200

    duplicate_response = client.post(
        "/api/project-groups",
        json={"groupName": "另一个移动组", "groupCode": "mobile"},
    )
    assert duplicate_response.status_code == 400
    assert duplicate_response.json()["code"] == "VALIDATION_ERROR"

    groups_response = client.get("/api/project-groups")
    assert groups_response.status_code == 200
    default_group = next(item for item in groups_response.json()["data"]["items"] if item["groupCode"] == "default")

    disable_default_response = client.put(
        f"/api/project-groups/{default_group['id']}",
        json={"status": "DISABLED"},
    )
    assert disable_default_response.status_code == 400
    assert disable_default_response.json()["code"] == "VALIDATION_ERROR"


def test_project_group_update_and_binding_validation(client: TestClient, db_session: Session) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add(
        Project(
            id=20,
            name="pc-admin",
            git_provider="GITLAB",
            git_project_id="3001",
            repository_url="https://gitlab.example.com/demo/pc-admin",
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
        json={"groupName": "前端业务组", "groupCode": "frontend"},
    )
    assert group_response.status_code == 200
    group = group_response.json()["data"]

    update_response = client.put(
        f"/api/project-groups/{group['id']}",
        json={
            "groupName": "PC 业务组",
            "description": "管理端项目",
            "defaultCodeQualityProfileCode": "web-pc-default-ai-review",
            "defaultProviderCode": "DEEPSEEK",
            "aiReviewModels": [
                {
                    "providerCode": "DEEPSEEK",
                    "modelName": "deepseek-v4-pro",
                    "displayName": "DeepSeek 主审",
                    "enabled": True,
                    "sortOrder": 10,
                },
                {
                    "providerCode": "XIAOMIMO",
                    "modelName": "mimo-v2.5-pro",
                    "displayName": "MiMo 复审",
                    "enabled": True,
                    "sortOrder": 20,
                },
            ],
            "pushBranchPatterns": ["release/*"],
            "pushMinChangedFiles": 2,
            "pushMinDiffBytes": 1024,
            "pushMinCommitCount": 1,
            "pushMaxChangedFiles": 20,
            "pushMaxDiffBytes": 50000,
            "pushDebounceSeconds": 60,
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()["data"]
    assert updated["groupName"] == "PC 业务组"
    assert updated["description"] == "管理端项目"
    assert updated["defaultCodeQualityProfileCode"] == "web-pc-default-ai-review"
    assert updated["defaultProviderCode"] == "DEEPSEEK"
    assert [item["providerCode"] for item in updated["aiReviewModels"]] == ["DEEPSEEK", "XIAOMIMO"]
    assert updated["aiReviewModels"][0]["displayName"] == "DeepSeek 主审"
    assert {key: updated[key] for key in DEFAULT_PUSH_POLICY} == {
        "pushBranchPatterns": ["release/*"],
        "pushMinChangedFiles": 2,
        "pushMinDiffBytes": 1024,
        "pushMinCommitCount": 1,
        "pushMaxChangedFiles": 20,
        "pushMaxDiffBytes": 50000,
        "pushDebounceSeconds": 60,
    }

    missing_group_response = client.put("/api/projects/20/group", json={"groupId": 9999})
    assert missing_group_response.status_code == 404
    assert missing_group_response.json()["code"] == "RESOURCE_NOT_FOUND"

    bind_response = client.put("/api/projects/20/group", json={"groupId": group["id"]})
    assert bind_response.status_code == 200
    assert bind_response.json()["data"]["groupName"] == "PC 业务组"


def test_project_can_be_created_before_webhook_and_reused_by_gitlab_project_id(
    client: TestClient, db_session: Session
) -> None:
    seed_template(db_session, "frontend-default", "FRONTEND")

    create_response = client.post(
        "/api/projects",
        json={
            "name": "预创建 PC 项目",
            "gitProvider": "GITLAB",
            "gitProjectId": "31001",
            "repositoryUrl": "https://gitlab.example.com/client/pc-admin",
            "targetType": "WEB_PC",
        },
    )
    assert create_response.status_code == 200
    project = create_response.json()["data"]
    assert project["gitProjectId"] == "31001"
    assert project["supportedTargetTypes"] == ["WEB_PC"]

    configs = client.get(f"/api/projects/{project['id']}/target-configs").json()["data"]
    web_config = next(item for item in configs if item["targetType"] == "WEB_PC")
    assert web_config["pathPatterns"] == ["**/*"]
    assert web_config["codeQualityProfileCode"] == "web-pc-default-ai-review"

    webhook_response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mr_payload(
            31001,
            "client/pc-admin",
            [{"path": "src/pages/Home.tsx", "diffText": "+ export function Home() {}"}],
        ),
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )
    assert webhook_response.status_code == 200
    task_id = webhook_response.json()["data"]["taskId"]
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    assert detail["projectId"] == project["id"]
    assert detail["targetType"] == "WEB_PC"
    assert detail["codeQualityProfileCode"] == "web-pc-default-ai-review"


def test_new_ios_project_webhook_auto_creates_ios_target_config(client: TestClient, db_session: Session) -> None:
    seed_template(db_session, "frontend-default", "FRONTEND")

    response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mr_payload(
            4001,
            "mobile/iphone-client",
            [{"path": "ios/AppDelegate.swift", "diffText": "+ import UIKit"}],
        ),
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    assert detail["targetType"] == "APP_IOS"
    assert detail["codeQualityProfileCode"] == "app-ios-default-ai-review"

    projects = client.get("/api/projects").json()["data"]["items"]
    project = next(item for item in projects if item["gitProjectId"] == "4001")
    assert project["supportedTargetTypes"] == ["APP_IOS"]
    assert project["detectedTargetTypes"] == ["APP_IOS"]
    assert project["targetDetection"]["evidences"][0]["source"] == "PATH_MAPPING"

    configs = client.get(f"/api/projects/{project['id']}/target-configs").json()["data"]
    ios_config = next(item for item in configs if item["targetType"] == "APP_IOS")
    assert ios_config["pathPatterns"] == ["**/*"]
    assert ios_config["reminderCardEnabled"] is False


def test_new_web_project_webhook_auto_detects_from_root_src_and_package_json(
    client: TestClient, db_session: Session
) -> None:
    seed_template(db_session, "frontend-default", "FRONTEND")

    response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mr_payload(
            4002,
            "platform/admin-web",
            [
                {"path": "src/pages/Home.tsx", "diffText": "+ export function Home() {}"},
                {"path": "package.json", "diffText": "+ \"antd\": \"6.3.6\""},
            ],
        ),
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    assert detail["targetType"] == "WEB_PC"
    assert detail["targetTypes"] == ["WEB_PC"]
    assert detail["codeQualityProfileCode"] == "web-pc-default-ai-review"


def test_existing_project_detection_does_not_overwrite_target_configs(
    client: TestClient, db_session: Session
) -> None:
    seed_template(db_session, "backend-default", "BACKEND")
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add(
        Project(
            id=30,
            name="backend-service",
            git_provider="GITLAB",
            git_project_id="4003",
            repository_url="https://gitlab.example.com/demo/backend-service",
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
    existing_configs = client.get("/api/projects/30/target-configs")
    assert existing_configs.status_code == 200
    assert {item["targetType"] for item in existing_configs.json()["data"]} == {"BACKEND"}

    response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mr_payload(
            4003,
            "demo/backend-service",
            [{"path": "src/pages/Home.tsx", "diffText": "+ export function Home() {}"}],
        ),
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )

    assert response.status_code == 200
    configs = client.get("/api/projects/30/target-configs").json()["data"]
    assert {item["targetType"] for item in configs} == {"BACKEND"}
    project = next(item for item in client.get("/api/projects").json()["data"]["items"] if item["id"] == 30)
    assert "WEB_PC" in project["detectedTargetTypes"]
    assert project["supportedTargetTypes"] == ["BACKEND"]


def test_new_project_chooses_one_target_and_keeps_all_detection_candidates(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_template(db_session, "backend-default", "BACKEND")
    seed_template(db_session, "frontend-default", "FRONTEND")

    response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mr_payload(
            4004,
            "platform/mixed-repo",
            [
                {"path": "src/main/java/com/demo/OrderService.java", "diffText": "+ class OrderService {}"},
                {"path": "web/src/App.jsx", "diffText": "+ export default App"},
            ],
        ),
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "SUCCESS"
    task_id = payload["taskId"]
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    assert detail["status"] == "SUCCESS"
    assert detail["targetType"] == "WEB_PC"
    assert detail["targetTypes"] == ["WEB_PC"]
    project = next(item for item in client.get("/api/projects").json()["data"]["items"] if item["gitProjectId"] == "4004")
    assert set(project["detectedTargetTypes"]) == {"WEB_PC", "BACKEND"}
    assert project["targetType"] == "WEB_PC"
    assert project["supportedTargetTypes"] == ["WEB_PC"]


def test_target_type_path_mapping_does_not_prefix_double_star_implicitly(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_template(db_session, "backend-default", "BACKEND")
    seed_template(db_session, "frontend-default", "FRONTEND")
    mappings = client.get("/api/target-type-path-mappings").json()["data"]
    updated = [
        {
            **item,
            "pathPatterns": (
                ["src/main/java/**"]
                if item["targetType"] == "BACKEND"
                else (["app/**/*.java"] if item["targetType"] == "APP_ANDROID" else item["pathPatterns"])
            ),
        }
        for item in mappings
    ]
    assert client.put("/api/target-type-path-mappings", json={"items": updated}).status_code == 200

    response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mr_payload(
            4005,
            "mobile/android-app",
            [{"path": "app/src/main/java/com/demo/MainActivity.java", "diffText": "+ class MainActivity {}"}],
        ),
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["status"] == "SUCCESS"
    detail = client.get(f"/api/review-tasks/{payload['taskId']}").json()["data"]
    assert detail["targetType"] == "APP_ANDROID"
    assert detail["targetTypes"] == ["APP_ANDROID"]


def test_target_type_path_mappings_can_be_updated_and_drive_new_project_detection(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_template(db_session, "frontend-default", "FRONTEND")

    mappings_response = client.get("/api/target-type-path-mappings")
    assert mappings_response.status_code == 200
    mappings = mappings_response.json()["data"]
    assert any(item["targetType"] == "WEB_PC" for item in mappings)
    assert all(item["targetType"] != "APP_CROSS_PLATFORM" for item in mappings)

    updated = [
        {
            **item,
            "pathPatterns": ["client-web/**"] if item["targetType"] == "WEB_PC" else item["pathPatterns"],
        }
        for item in mappings
    ]
    save_response = client.put("/api/target-type-path-mappings", json={"items": updated})
    assert save_response.status_code == 200

    response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mr_payload(
            4005,
            "platform/client",
            [{"path": "client-web/src/App.jsx", "diffText": "+ export default App"}],
        ),
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    assert detail["targetType"] == "WEB_PC"
    assert detail["codeQualityProfileCode"] == "web-pc-default-ai-review"

    rejected = client.put(
        "/api/target-type-path-mappings",
        json={
            "items": [
                {
                    "targetType": "APP_CROSS_PLATFORM",
                    "pathPatterns": ["flutter/**"],
                    "enabled": True,
                }
            ]
        },
    )
    assert rejected.status_code == 400


def test_disabled_path_mappings_fall_back_to_general(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_template(db_session, "general-default", "GENERAL")

    mappings_response = client.get("/api/target-type-path-mappings")
    assert mappings_response.status_code == 200
    disabled_mappings = [
        {
            **item,
            "enabled": False,
        }
        for item in mappings_response.json()["data"]
    ]
    save_response = client.put("/api/target-type-path-mappings", json={"items": disabled_mappings})
    assert save_response.status_code == 200

    response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mr_payload(
            4007,
            "platform/auto-web",
            [{"path": "src/pages/Home.tsx", "diffText": "+ export const Home = () => null"}],
        ),
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    assert detail["targetType"] == "GENERAL"
    assert detail["codeQualityProfileCode"] is None

    projects = client.get("/api/projects").json()["data"]["items"]
    project = next(item for item in projects if item["gitProjectId"] == "4007")
    assert project["detectedTargetTypes"] == ["GENERAL"]
    assert any(
        item["targetType"] == "GENERAL" and item["source"] == "FALLBACK"
        for item in project["targetDetection"]["evidences"]
    )


def test_unmatched_new_project_uses_general_and_records_ai_review_profile_failure(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session, "general-default", "GENERAL")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")

    response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=mr_payload(
            4006,
            "docs/unknown",
            [{"path": "docs/guide.md", "diffText": "+ docs only"}],
        ),
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    assert detail["status"] == "SUCCESS"
    assert detail["targetType"] == "GENERAL"
    assert detail["codeQualityProfileCode"] is None
    result = client.get(f"/api/review-tasks/{task_id}/code-quality-result").json()["data"]
    assert result["status"] == "SKIPPED"
    assert "项目未设置 AI Review 模板" in result["errorMessage"]
