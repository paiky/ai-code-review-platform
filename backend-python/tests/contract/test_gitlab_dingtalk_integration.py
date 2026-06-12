from datetime import datetime
import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.notification.models import NotificationWebhook
from app.notification.repository import default_project_group_id, list_enabled_webhooks, list_webhooks
from app.project_integration.models import Project
from app.project_integration.service import _build_gitlab_changed_files_summary, _parse_time
from app.review_record.models import ReviewTask
from app.rule_template.models import RuleTemplate


def seed_template(db_session: Session) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add_all(
        [
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
                        "focusChangeTypes": ["DB_DATA_WRITE", "CACHE_WRITE_DELETE", "MQ_CONFIG", "CONFIG"],
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
                description="stage3b",
                created_at=now,
                updated_at=now,
            ),
            RuleTemplate(
                template_code="general-default",
                template_name="通用默认审查模板",
                target_type="GENERAL",
                version=1,
                enabled_rule_codes=json.dumps([]),
                config_json=json.dumps(
                    {
                        "focusChangeTypes": [],
                        "focusRuleCodes": [],
                        "recommendedChecks": [],
                    }
                ),
                status="ENABLED",
                description="stage3b",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()


def test_gitlab_event_time_with_timezone_is_converted_to_local_time() -> None:
    raw_value = "2026-05-28T08:21:03.692Z"
    expected = datetime.fromisoformat(raw_value.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)

    assert _parse_time(raw_value) == expected


def seed_frontend_template(db_session: Session) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add(
        RuleTemplate(
            template_code="frontend-default",
            template_name="前端默认审查模板",
            target_type="WEB_PC",
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


def mr_payload_without_changed_files() -> dict:
    return {
        "object_kind": "merge_request",
        "project": {"id": 1001, "name": "demo-service"},
        "object_attributes": {
            "iid": 12,
            "action": "open",
            "source_branch": "feature/gitlab-api",
            "target_branch": "main",
            "last_commit": {"id": "abcdef"},
        },
        "user": {"name": "Alice", "username": "alice"},
    }


def no_findings_review_card_json() -> str:
    return json.dumps(
        {
            "summary": "未发现需要修复的问题",
            "overallLevel": "LOW",
            "findings": [],
        },
        ensure_ascii=False,
    )


def review_card_with_finding_json() -> str:
    return json.dumps(
        {
            "summary": "发现一个问题",
            "overallLevel": "HIGH",
            "findings": [
                {
                    "severity": "HIGH",
                    "category": "CORRECTNESS",
                    "filePath": "src/OrderService.java",
                    "startLine": 12,
                    "endLine": 12,
                    "title": "空状态可能导致后续流程异常",
                    "body": "新增代码把订单状态设置为空，后续状态机可能无法处理。",
                    "suggestion": "保持明确状态值。",
                    "confidence": "HIGH",
                }
            ],
        },
        ensure_ascii=False,
    )


def save_dingtalk_webhooks(client: TestClient, items: list[dict]) -> None:
    response = client.put("/api/code-quality-reviews/settings", json={"dingtalkWebhooks": items})
    assert response.status_code == 200


def default_group(client: TestClient) -> dict:
    response = client.get("/api/project-groups")
    assert response.status_code == 200
    return next(item for item in response.json()["data"]["items"] if item["groupCode"] == "default")


def update_group_webhooks(client: TestClient, group: dict, webhooks: list[dict]) -> dict:
    response = client.put(
        f"/api/project-groups/{group['id']}",
        json={
            "groupName": group["groupName"],
            "groupCode": group["groupCode"],
            "defaultProviderCode": group.get("defaultProviderCode"),
            "description": group.get("description"),
            "status": group.get("status") or "ENABLED",
            "dingtalkWebhooks": webhooks,
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def create_project_group(client: TestClient, group_name: str, group_code: str, webhooks: list[dict] | None = None) -> dict:
    response = client.post(
        "/api/project-groups",
        json={
            "groupName": group_name,
            "groupCode": group_code,
            "dingtalkWebhooks": webhooks or [],
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def create_project(client: TestClient, git_project_id: int, name: str, group_id: int) -> dict:
    response = client.post(
        "/api/projects",
        json={
            "name": name,
            "gitProjectId": str(git_project_id),
            "repositoryUrl": f"https://gitlab.example.com/{name}",
            "groupId": group_id,
            "targetType": "BACKEND",
        },
    )
    assert response.status_code == 200
    return response.json()["data"]


def mr_payload_for_project(project_id: int, project_name: str, diff_text: str | None = None) -> dict:
    payload = mr_payload_without_changed_files()
    payload["project"]["id"] = project_id
    payload["project"]["name"] = project_name
    if diff_text is not None:
        payload["changedFiles"] = [
            {
                "old_path": "src/main/resources/mapper/OrderMapper.xml",
                "new_path": "src/main/resources/mapper/OrderMapper.xml",
                "diffText": diff_text,
            }
        ]
    return payload


def test_mr_without_changed_files_fetches_gitlab_diffs(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("GITLAB_API_ENABLED", "true")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.example.test")
    monkeypatch.setenv("GITLAB_TOKEN", "unit-token")

    with respx.mock(assert_all_called=True) as router:
        router.get("https://gitlab.example.test/api/v4/projects/1001").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 1001,
                    "name": "demo-service",
                    "path_with_namespace": "demo/service",
                    "web_url": "https://gitlab.example.test/demo/service",
                },
            )
        )
        router.get("https://gitlab.example.test/api/v4/projects/1001/merge_requests/12").mock(
            return_value=httpx.Response(
                200,
                json={
                    "iid": 12,
                    "web_url": "https://gitlab.example.test/demo/service/-/merge_requests/12",
                    "source_branch": "feature/gitlab-api",
                    "target_branch": "main",
                    "sha": "abcdef",
                    "diff_refs": {
                        "base_sha": "base-abcdef",
                        "head_sha": "abcdef",
                        "start_sha": "start-abcdef",
                    },
                    "author": {"name": "Alice", "username": "alice"},
                },
            )
        )
        router.get(
            "https://gitlab.example.test/api/v4/projects/1001/merge_requests/12/diffs",
            params={"page": "1", "per_page": "100"},
        ).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "old_path": "src/main/resources/mapper/OrderMapper.xml",
                        "new_path": "src/main/resources/mapper/OrderMapper.xml",
                        "diff": "+ update orders set status = 'DONE' where id = #{id}",
                    }
                ],
            )
        )

        response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json=mr_payload_without_changed_files(),
            headers={"X-Gitlab-Event": "Merge Request Hook"},
        )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    result = client.get(f"/api/review-tasks/{task_id}/result").json()["data"]
    assert result["changeAnalysis"]["changeTypes"] == ["DB", "DB_DATA_WRITE"]
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    assert detail["changedFilesSummary"]["source"] == "gitlab_api"
    assert detail["beforeSha"] == "base-abcdef"
    assert detail["afterSha"] == "abcdef"


def test_closed_mr_event_is_skipped_without_creating_review_task(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_template(db_session)

    response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            **mr_payload_without_changed_files(),
            "object_attributes": {
                **mr_payload_without_changed_files()["object_attributes"],
                "state": "opened",
                "action": "close",
            },
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "SKIPPED"
    assert response.json()["data"]["taskId"] is None
    assert client.get("/api/review-tasks").json()["data"]["items"] == []


def test_gitlab_web_urls_use_configured_public_base_url(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("GITLAB_BASE_URL", "http://192.168.100.88:19523")

    response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            **mr_payload_without_changed_files(),
            "project": {
                "id": 1001,
                "name": "demo-service",
                "web_url": "http://dc8191653c5a/demo/service",
            },
            "object_attributes": {
                **mr_payload_without_changed_files()["object_attributes"],
                "url": "http://dc8191653c5a/demo/service/-/merge_requests/12",
            },
            "changedFiles": [
                {
                    "path": "src/main/resources/mapper/OrderMapper.xml",
                    "diffText": "+ update orders set status = 'DONE' where id = #{id}",
                }
            ],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    projects = client.get("/api/projects").json()["data"]["items"]
    assert detail["externalUrl"] == "http://192.168.100.88:19523/demo/service/-/merge_requests/12"
    assert projects[0]["repositoryUrl"] == "http://192.168.100.88:19523/demo/service"


def test_gitlab_push_repository_url_uses_configured_public_base_url(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("GITLAB_BASE_URL", "http://192.168.100.88:19523")

    response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "push",
            "project": {
                "id": 1001,
                "name": "demo-service",
                "web_url": "http://dc8191653c5a/demo/service",
            },
            "ref": "refs/heads/master",
            "before": "before-sha",
            "after": "after-sha",
            "user_name": "Alice",
            "user_username": "alice",
            "total_commits_count": 1,
            "changedFiles": [
                {
                    "path": "src/main/resources/mapper/OrderMapper.xml",
                    "diffText": "+ update orders set status = 'PUSHED' where id = #{id}",
                }
            ],
        },
        headers={"X-Gitlab-Event": "Push Hook"},
    )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    projects = client.get("/api/projects").json()["data"]["items"]
    assert detail["externalUrl"] == "http://192.168.100.88:19523/demo/service/-/commit/after-sha"
    assert projects[0]["repositoryUrl"] == "http://192.168.100.88:19523/demo/service"


def test_web_mr_without_payload_changed_files_creates_task_after_gitlab_diff_detection(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_template(db_session)
    seed_frontend_template(db_session)
    monkeypatch.setenv("GITLAB_API_ENABLED", "true")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.example.test")
    monkeypatch.setenv("GITLAB_TOKEN", "unit-token")

    with respx.mock(assert_all_called=True) as router:
        router.get("https://gitlab.example.test/api/v4/projects/160").mock(
            return_value=httpx.Response(
                200,
                json={
                    "id": 160,
                    "name": "Here PetSafe Admin",
                    "path_with_namespace": "consumer-web-frontend/consumer-petsafe-admin",
                    "web_url": "https://gitlab.example.test/consumer-web-frontend/consumer-petsafe-admin",
                },
            )
        )
        router.get("https://gitlab.example.test/api/v4/projects/160/merge_requests/116").mock(
            return_value=httpx.Response(
                200,
                json={
                    "iid": 116,
                    "web_url": "https://gitlab.example.test/consumer-web-frontend/consumer-petsafe-admin/-/merge_requests/116",
                    "source_branch": "coolpet-main-internal",
                    "target_branch": "coolpet-main",
                    "sha": "8a106dc17ef43903c926aa7070e3585273db0590",
                    "author": {"name": "Lin Pei", "username": "linpei"},
                },
            )
        )
        router.get("https://gitlab.example.test/api/v4/projects/160/merge_requests/116/versions").mock(
            return_value=httpx.Response(200, json=[])
        )
        router.get(
            "https://gitlab.example.test/api/v4/projects/160/merge_requests/116/diffs",
            params={"page": "1", "per_page": "100"},
        ).mock(
            return_value=httpx.Response(
                200,
                json=[
                    {
                        "old_path": "src/pages/DealerEditor.vue",
                        "new_path": "src/pages/DealerEditor.vue",
                        "diff": "+ const minProportionFloor = props.existing ? 10 : 0",
                    },
                    {
                        "old_path": "package.json",
                        "new_path": "package.json",
                        "diff": "+ \"@vitejs/plugin-vue\": \"latest\"",
                    },
                ],
            )
        )

        response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json={
                "object_kind": "merge_request",
                "project": {
                    "id": 160,
                    "name": "Here PetSafe Admin",
                    "web_url": "https://gitlab.example.test/consumer-web-frontend/consumer-petsafe-admin",
                },
                "object_attributes": {
                    "iid": 116,
                    "action": "open",
                    "state": "opened",
                    "source_branch": "coolpet-main-internal",
                    "target_branch": "coolpet-main",
                    "last_commit": {"id": "8a106dc17ef43903c926aa7070e3585273db0590"},
                },
                "user": {"name": "Lin Pei", "username": "linpei"},
            },
            headers={"X-Gitlab-Event": "Merge Request Hook"},
        )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    assert detail["status"] == "SUCCESS"
    assert detail["targetType"] == "WEB_PC"
    assert detail["codeQualityProfileCode"] == "web-pc-default-ai-review"
    assert detail["changedFilesSummary"]["source"] == "gitlab_api"


def test_gitlab_diffs_404_falls_back_to_changes(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("GITLAB_API_ENABLED", "true")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.example.test")
    monkeypatch.setenv("GITLAB_TOKEN", "unit-token")

    with respx.mock(assert_all_called=True) as router:
        router.get("https://gitlab.example.test/api/v4/projects/1001").mock(
            return_value=httpx.Response(200, json={"id": 1001, "name": "demo-service"})
        )
        router.get("https://gitlab.example.test/api/v4/projects/1001/merge_requests/12").mock(
            return_value=httpx.Response(200, json={"iid": 12})
        )
        router.get("https://gitlab.example.test/api/v4/projects/1001/merge_requests/12/versions").mock(
            return_value=httpx.Response(200, json=[])
        )
        router.get(
            "https://gitlab.example.test/api/v4/projects/1001/merge_requests/12/diffs",
            params={"page": "1", "per_page": "100"},
        ).mock(return_value=httpx.Response(404, json={"message": "404"}))
        router.get("https://gitlab.example.test/api/v4/projects/1001/merge_requests/12/changes").mock(
            return_value=httpx.Response(
                200,
                json={
                    "changes": [
                        {
                            "old_path": "src/main/resources/application.yml",
                            "new_path": "src/main/resources/application.yml",
                            "diff": "+ order:\n+   enabled: true",
                        }
                    ]
                },
            )
        )

        response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json=mr_payload_without_changed_files(),
            headers={"X-Gitlab-Event": "Merge Request Hook"},
        )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    result = client.get(f"/api/review-tasks/{task_id}/result").json()["data"]
    assert "CONFIG" in result["changeAnalysis"]["changeTypes"]


def test_gitlab_api_failure_marks_task_failed(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("GITLAB_API_ENABLED", "true")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.example.test")
    monkeypatch.setenv("GITLAB_TOKEN", "unit-token")

    with respx.mock(assert_all_called=False) as router:
        router.get("https://gitlab.example.test/api/v4/projects/1001").mock(
            return_value=httpx.Response(200, json={"id": 1001, "name": "demo-service"})
        )
        router.get("https://gitlab.example.test/api/v4/projects/1001/merge_requests/12").mock(
            return_value=httpx.Response(200, json={"iid": 12})
        )
        router.get("https://gitlab.example.test/api/v4/projects/1001/merge_requests/12/versions").mock(
            return_value=httpx.Response(200, json=[])
        )
        router.get(
            "https://gitlab.example.test/api/v4/projects/1001/merge_requests/12/diffs",
            params={"page": "1", "per_page": "100"},
        ).mock(return_value=httpx.Response(500, json={"message": "boom"}))

        response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json=mr_payload_without_changed_files(),
            headers={"X-Gitlab-Event": "Merge Request Hook"},
        )

    assert response.status_code == 500
    tasks = client.get("/api/review-tasks").json()["data"]["items"]
    assert tasks[0]["status"] == "FAILED"


def test_dingtalk_success_is_recorded(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_template(db_session)
    save_dingtalk_webhooks(
        client,
        [
            {
                "name": "研发群",
                "channel": "DINGTALK",
                "webhookUrl": "https://dingtalk.example.test/robot/send",
                "enabled": True,
            }
        ],
    )

    with respx.mock(assert_all_called=True) as router:
        route = router.post("https://dingtalk.example.test/robot/send").mock(
            return_value=httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
        )
        response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json={
                **mr_payload_without_changed_files(),
                "changedFiles": [
                    {
                        "old_path": "src/main/resources/mapper/OrderMapper.xml",
                        "new_path": "src/main/resources/mapper/OrderMapper.xml",
                        "diffText": "+ update orders set status = 'DONE' where id = #{id}",
                    }
                ],
            },
            headers={"X-Gitlab-Event": "Merge Request Hook"},
        )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    notifications = client.get(f"/api/review-tasks/{task_id}/notifications").json()["data"]
    assert notifications[0]["status"] == "SUCCESS"
    assert notifications[0]["responseBody"] == '{"errcode":0,"errmsg":"ok"}'
    body = json.loads(route.calls[0].request.content)
    assert "项目：demo-service" in body["markdown"]["text"]
    assert "分支：feature/gitlab-api -> main" in body["markdown"]["text"]


def test_dingtalk_filter_prefers_focus_rule_codes_for_value_config(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add(
        RuleTemplate(
            template_code="backend-default",
            template_name="后端默认审查模板",
            target_type="BACKEND",
            version=1,
            enabled_rule_codes=json.dumps(["DB_DATA_WRITE_CHANGE_CHECK", "CONFIG_RELEASE_CHECK"]),
            config_json=json.dumps(
                {
                    "focusChangeTypes": ["DB_DATA_WRITE"],
                    "focusRuleCodes": ["CONFIG_RELEASE_CHECK"],
                    "recommendedChecks": ["确认配置发布窗口。"],
                }
            ),
            status="ENABLED",
            description="focus rule codes",
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()
    save_dingtalk_webhooks(
        client,
        [
            {
                "name": "配置群",
                "channel": "DINGTALK",
                "webhookUrl": "https://dingtalk.example.test/robot/send",
                "enabled": True,
            }
        ],
    )

    with respx.mock(assert_all_called=True) as router:
        router.post("https://dingtalk.example.test/robot/send").mock(
            return_value=httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
        )
        response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json={
                **mr_payload_without_changed_files(),
                "changedFiles": [
                    {
                        "old_path": "src/main/java/com/demo/OrderProperties.java",
                        "new_path": "src/main/java/com/demo/OrderProperties.java",
                        "diffText": (
                            "+ @Value(\"${order.confirm.enabled:false}\")\n"
                            "+ private boolean confirmEnabled;"
                        ),
                    }
                ],
            },
            headers={"X-Gitlab-Event": "Merge Request Hook"},
        )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    notifications = client.get(f"/api/review-tasks/{task_id}/notifications").json()["data"]
    assert notifications[0]["status"] == "SUCCESS"
    assert "配置变更（规则扫描）" in notifications[0]["requestDigest"]
    assert '<font color="#2563eb">Nacos</font>' in notifications[0]["requestDigest"]
    assert "本次没有命中需推送的重点提醒" not in notifications[0]["requestDigest"]


def test_dingtalk_multiple_webhooks_record_partial_failure(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_template(db_session)
    save_dingtalk_webhooks(
        client,
        [
            {
                "name": "研发群",
                "channel": "DINGTALK",
                "webhookUrl": "https://dingtalk.example.test/robot/send?group=dev",
                "enabled": True,
            },
            {
                "name": "测试群",
                "channel": "DINGTALK",
                "webhookUrl": "https://dingtalk.example.test/robot/send?group=qa",
                "enabled": True,
            },
        ],
    )

    with respx.mock(assert_all_called=True) as router:
        router.post("https://dingtalk.example.test/robot/send?group=dev").mock(
            return_value=httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
        )
        router.post("https://dingtalk.example.test/robot/send?group=qa").mock(
            return_value=httpx.Response(500, json={"errcode": 500, "errmsg": "boom"})
        )
        response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json={
                **mr_payload_without_changed_files(),
                "changedFiles": [
                    {
                        "old_path": "src/main/resources/mapper/OrderMapper.xml",
                        "new_path": "src/main/resources/mapper/OrderMapper.xml",
                        "diffText": "+ update orders set status = 'DONE' where id = #{id}",
                    }
                ],
            },
            headers={"X-Gitlab-Event": "Merge Request Hook"},
        )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    notifications = client.get(f"/api/review-tasks/{task_id}/notifications").json()["data"]
    assert len(notifications) == 2
    assert {item["status"] for item in notifications} == {"SUCCESS", "FAILED"}


def test_dingtalk_delivery_uses_project_group_webhooks(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_template(db_session)
    mobile_group = create_project_group(
        client,
        "移动业务组",
        "mobile",
        [
            {
                "name": "移动群",
                "channel": "DINGTALK",
                "webhookUrl": "https://dingtalk.example.test/robot/send?group=mobile",
                "enabled": True,
            }
        ],
    )
    web_group = create_project_group(
        client,
        "前端业务组",
        "web",
        [
            {
                "name": "前端群",
                "channel": "DINGTALK",
                "webhookUrl": "https://dingtalk.example.test/robot/send?group=web",
                "enabled": True,
            }
        ],
    )
    create_project(client, 1001, "mobile-service", mobile_group["id"])
    create_project(client, 1002, "web-service", web_group["id"])

    with respx.mock(assert_all_called=True) as router:
        mobile_route = router.post("https://dingtalk.example.test/robot/send?group=mobile").mock(
            return_value=httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
        )
        web_route = router.post("https://dingtalk.example.test/robot/send?group=web").mock(
            return_value=httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
        )
        mobile_response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json=mr_payload_for_project(1001, "mobile-service", "+ update orders set status = 'DONE' where id = #{id}"),
            headers={"X-Gitlab-Event": "Merge Request Hook"},
        )
        web_response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json=mr_payload_for_project(1002, "web-service", "+ update orders set status = 'DONE' where id = #{id}"),
            headers={"X-Gitlab-Event": "Merge Request Hook"},
        )

    assert mobile_response.status_code == 200
    assert web_response.status_code == 200
    assert mobile_route.call_count == 1
    assert web_route.call_count == 1
    mobile_notifications = client.get(f"/api/review-tasks/{mobile_response.json()['data']['taskId']}/notifications").json()["data"]
    web_notifications = client.get(f"/api/review-tasks/{web_response.json()['data']['taskId']}/notifications").json()["data"]
    assert mobile_notifications[0]["target"].endswith("group=mobile")
    assert web_notifications[0]["target"].endswith("group=web")


def test_dingtalk_delivery_skips_when_project_group_has_no_webhooks(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_template(db_session)
    default = update_group_webhooks(
        client,
        default_group(client),
        [
            {
                "name": "默认群",
                "channel": "DINGTALK",
                "webhookUrl": "https://dingtalk.example.test/robot/send?group=default",
                "enabled": True,
            }
        ],
    )
    empty_group = create_project_group(client, "空机器人组", "empty")
    create_project(client, 1001, "empty-service", empty_group["id"])
    assert default["enabledDingtalkWebhookCount"] == 1

    with respx.mock(assert_all_called=False) as router:
        route = router.post("https://dingtalk.example.test/robot/send?group=default").mock(
            return_value=httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
        )
        response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json=mr_payload_for_project(1001, "empty-service", "+ update orders set status = 'DONE' where id = #{id}"),
            headers={"X-Gitlab-Event": "Merge Request Hook"},
        )

    assert response.status_code == 200
    assert route.called is False
    notifications = client.get(f"/api/review-tasks/{response.json()['data']['taskId']}/notifications").json()["data"]
    assert notifications[0]["status"] == "SKIPPED"
    assert notifications[0]["target"] == "DINGTALK_WEBHOOKS_EMPTY"
    assert notifications[0]["errorMessage"] == "DingTalk webhook is not configured for the project group"


def test_dingtalk_allows_same_enabled_url_in_different_groups(client: TestClient) -> None:
    webhook = {
        "name": "公共群",
        "channel": "DINGTALK",
        "webhookUrl": "https://dingtalk.example.test/robot/send?access_token=same",
        "enabled": True,
    }

    first = create_project_group(client, "一组", "team-a", [webhook])
    second = create_project_group(client, "二组", "team-b", [webhook])

    assert first["enabledDingtalkWebhookCount"] == 1
    assert second["enabledDingtalkWebhookCount"] == 1


def test_dingtalk_rejects_duplicate_enabled_url_in_same_group(client: TestClient) -> None:
    response = client.post(
        "/api/project-groups",
        json={
            "groupName": "重复组",
            "groupCode": "dup-group",
            "dingtalkWebhooks": [
                {
                    "name": "A",
                    "channel": "DINGTALK",
                    "webhookUrl": "https://dingtalk.example.test/robot/send?access_token=same",
                    "enabled": True,
                },
                {
                    "name": "B",
                    "channel": "DINGTALK",
                    "webhookUrl": "https://dingtalk.example.test/robot/send?access_token=same",
                    "enabled": True,
                },
            ],
        },
    )

    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_legacy_null_project_group_webhooks_are_read_as_default_group(db_session: Session) -> None:
    group_id = default_project_group_id(db_session)
    now = datetime(2026, 5, 18, 10, 0, 0)
    webhook = NotificationWebhook(
        project_group_id=None,
        name="历史全局群",
        channel="DINGTALK",
        webhook_url="https://dingtalk.example.test/robot/send?access_token=legacy",
        secret_ref=None,
        status="ENABLED",
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    db_session.add(webhook)
    db_session.commit()

    default_webhooks = list_webhooks(db_session, group_id)
    enabled_webhooks = list_enabled_webhooks(db_session, group_id)

    assert [item.id for item in default_webhooks] == [webhook.id]
    assert [item.id for item in enabled_webhooks] == [webhook.id]
    db_session.refresh(webhook)
    assert webhook.project_group_id is None


def test_push_without_payload_diff_uses_compare_api(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("GITLAB_API_ENABLED", "true")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.example.test")
    monkeypatch.setenv("GITLAB_TOKEN", "unit-token")

    with respx.mock(assert_all_called=True) as router:
        router.get("https://gitlab.example.test/api/v4/projects/1001/repository/compare").mock(
            return_value=httpx.Response(
                200,
                json={
                    "diffs": [
                        {
                            "old_path": "src/main/resources/mapper/OrderMapper.xml",
                            "new_path": "src/main/resources/mapper/OrderMapper.xml",
                            "diff": "+ update orders set status = 'PUSHED' where id = #{id}",
                        }
                    ]
                },
            )
        )
        response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json={
                "object_kind": "push",
                "project": {
                    "id": 1001,
                    "name": "demo-service",
                    "web_url": "https://gitlab.example.test/demo/service",
                },
                "ref": "refs/heads/master",
                "before": "before-sha",
                "after": "after-sha",
                "user_name": "Alice",
                "user_username": "alice",
                "total_commits_count": 1,
                "commits": [{"modified": ["src/main/resources/mapper/OrderMapper.xml"]}],
            },
            headers={"X-Gitlab-Event": "Push Hook"},
        )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    result = client.get(f"/api/review-tasks/{task_id}/result").json()["data"]
    assert result["changeAnalysis"]["changeTypes"] == ["DB", "DB_DATA_WRITE"]
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    assert detail["changedFilesSummary"]["source"] == "gitlab_compare_api"
    assert detail["changedFilesSummary"]["commitCount"] == 1
    assert detail["changedFilesSummary"]["files"][0]["commitCount"] == 1


def test_gitlab_diff_summary_preserves_file_side_flags() -> None:
    summary = _build_gitlab_changed_files_summary(
        [
            {"path": "src/New.java", "newPath": "src/New.java", "newFile": True},
            {"path": "src/Old.java", "oldPath": "src/Old.java", "deletedFile": True},
            {
                "path": "src/NewName.java",
                "oldPath": "src/OldName.java",
                "newPath": "src/NewName.java",
                "renamedFile": True,
            },
        ],
        "gitlab_compare_api",
    )

    assert summary["files"][0]["newFile"] is True
    assert summary["files"][1]["deletedFile"] is True
    assert summary["files"][2]["renamedFile"] is True


def test_new_branch_push_with_zero_before_sha_without_diff_skips_task_creation(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("GITLAB_API_ENABLED", "true")
    monkeypatch.setenv("GITLAB_BASE_URL", "https://gitlab.example.test")
    monkeypatch.setenv("GITLAB_TOKEN", "unit-token")

    with respx.mock(assert_all_called=False) as router:
        compare_route = router.get("https://gitlab.example.test/api/v4/projects/1001/repository/compare").mock(
            return_value=httpx.Response(404, json={"message": "404 Not found"})
        )
        response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json={
                "object_kind": "push",
                "project": {
                    "id": 1001,
                    "name": "demo-service",
                    "web_url": "https://gitlab.example.test/demo/service",
                },
                "ref": "refs/heads/master",
                "before": "0000000000000000000000000000000000000000",
                "after": "after-sha",
                "user_name": "Alice",
                "user_username": "alice",
                "total_commits_count": 1,
                "commits": [{"modified": ["src/main/resources/mapper/OrderMapper.xml"]}],
            },
            headers={"X-Gitlab-Event": "Push Hook"},
        )

    assert response.status_code == 200
    assert compare_route.called is False
    data = response.json()["data"]
    assert data["status"] == "SKIPPED"
    assert data["taskId"] is None
    assert data["reasonCode"] == "NEW_BRANCH_PUSH_DIFF_UNAVAILABLE"
    assert db_session.query(ReviewTask).count() == 0
    project = db_session.query(Project).filter(Project.git_project_id == "1001").one()
    assert json.loads(project.supported_target_types) == ["GENERAL"]


def test_push_without_reminders_skips_dingtalk_delivery(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_template(db_session)
    save_dingtalk_webhooks(
        client,
        [
            {
                "name": "研发群",
                "channel": "DINGTALK",
                "webhookUrl": "https://dingtalk.example.test/robot/send",
                "enabled": True,
            }
        ],
    )

    with respx.mock(assert_all_called=False) as router:
        route = router.post("https://dingtalk.example.test/robot/send").mock(
            return_value=httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
        )
        response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json={
                "object_kind": "push",
                "project": {
                    "id": 1001,
                    "name": "demo-service",
                    "web_url": "https://gitlab.example.test/demo/service",
                },
                "ref": "refs/heads/master",
                "before": "before-sha",
                "after": "after-sha",
                "user_name": "Alice",
                "user_username": "alice",
                "changedFiles": [
                    {
                        "path": "src/OrderService.java",
                        "diffText": "+ update docs only",
                    }
                ],
            },
            headers={"X-Gitlab-Event": "Push Hook"},
        )

    assert response.status_code == 200
    assert route.called is False
    task_id = response.json()["data"]["taskId"]
    notifications = client.get(f"/api/review-tasks/{task_id}/notifications").json()["data"]
    assert notifications[0]["status"] == "SKIPPED"
    assert notifications[0]["target"] == "DINGTALK_REVIEW_SUMMARY"


def test_push_with_reminders_skips_dingtalk_when_ai_review_not_scheduled(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_template(db_session)
    save_dingtalk_webhooks(
        client,
        [
            {
                "name": "研发群",
                "channel": "DINGTALK",
                "webhookUrl": "https://dingtalk.example.test/robot/send",
                "enabled": True,
            }
        ],
    )

    with respx.mock(assert_all_called=False) as router:
        route = router.post("https://dingtalk.example.test/robot/send").mock(
            return_value=httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
        )
        response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json={
                "object_kind": "push",
                "project": {
                    "id": 1001,
                    "name": "demo-service",
                    "web_url": "https://gitlab.example.test/demo/service",
                },
                "ref": "refs/heads/master",
                "before": "before-sha",
                "after": "after-sha",
                "user_name": "Alice",
                "user_username": "alice",
                "changedFiles": [
                    {
                        "path": "src/main/resources/mapper/OrderMapper.xml",
                        "diffText": "+ update orders set status = 'DONE' where id = #{id}",
                    }
                ],
            },
            headers={"X-Gitlab-Event": "Push Hook"},
        )

    assert response.status_code == 200
    assert route.called is False
    notifications = client.get(f"/api/review-tasks/{response.json()['data']['taskId']}/notifications").json()["data"]
    assert notifications[0]["status"] == "SKIPPED"
    assert notifications[0]["target"] == "DINGTALK_REVIEW_SUMMARY"


def test_mr_summary_without_findings_still_sends_and_uses_platform_base_url(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    monkeypatch.setenv("PLATFORM_BASE_URL", "http://example.com/app")
    save_dingtalk_webhooks(
        client,
        [
            {
                "name": "研发群",
                "channel": "DINGTALK",
                "webhookUrl": "https://dingtalk.example.test/robot/send",
                "enabled": True,
            }
        ],
    )

    with respx.mock(assert_all_called=True) as router:
        router.post("https://api.deepseek.com/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={"choices": [{"message": {"content": no_findings_review_card_json()}}]},
            )
        )
        route = router.post("https://dingtalk.example.test/robot/send").mock(
            return_value=httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
        )
        response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json={
                **mr_payload_without_changed_files(),
                "changedFiles": [
                    {
                        "path": "src/OrderService.java",
                        "diffText": "+ update docs only",
                    }
                ],
            },
            headers={"X-Gitlab-Event": "Merge Request Hook"},
        )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    body = json.loads(route.calls[0].request.content)
    markdown = body["markdown"]["text"]
    assert "项目：demo-service" in markdown
    assert "分支：feature/gitlab-api -> main" in markdown
    assert "AI 模型：DeepSeek" in markdown
    assert "MR 作者：Alice(@alice)" in markdown
    assert "GITLAB_MR_WEBHOOK" not in markdown
    assert "配置变更（规则扫描）" not in markdown
    assert "暂无需要特别维护的变更。" not in markdown
    assert "未发现需要修复的问题。" in markdown
    assert f"详情：http://example.com/app/tasks/{task_id}" in markdown


def test_mr_summary_without_reminders_links_ai_findings_and_hides_rule_section(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    monkeypatch.setenv("PLATFORM_BASE_URL", "http://example.com/app")
    save_dingtalk_webhooks(
        client,
        [
            {
                "name": "研发群",
                "channel": "DINGTALK",
                "webhookUrl": "https://dingtalk.example.test/robot/send",
                "enabled": True,
            }
        ],
    )

    with respx.mock(assert_all_called=True) as router:
        router.post("https://api.deepseek.com/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={"choices": [{"message": {"content": review_card_with_finding_json()}}]},
            )
        )
        route = router.post("https://dingtalk.example.test/robot/send").mock(
            return_value=httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
        )
        response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json={
                **mr_payload_without_changed_files(),
                "changedFiles": [
                    {
                        "path": "src/OrderService.java",
                        "diffText": "+ update docs only",
                    }
                ],
            },
            headers={"X-Gitlab-Event": "Merge Request Hook"},
        )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    body = json.loads(route.calls[0].request.content)
    markdown = body["markdown"]["text"]
    assert "AI 模型：DeepSeek" in markdown
    assert "配置变更（规则扫描）" not in markdown
    assert (
        f"[空状态可能导致后续流程异常。]"
        f"(http://example.com/app/tasks/{task_id}?reviewKey=deepseek-deepseek-v4-pro#fix-preview-0)"
        in markdown
    )
    assert f"详情：http://example.com/app/tasks/{task_id}?reviewKey=deepseek-deepseek-v4-pro" in markdown


def test_web_project_ai_summary_hides_rule_section_when_reminder_card_disabled(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_template(db_session)
    seed_frontend_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    save_dingtalk_webhooks(
        client,
        [
            {
                "name": "前端群",
                "channel": "DINGTALK",
                "webhookUrl": "https://dingtalk.example.test/robot/send",
                "enabled": True,
            }
        ],
    )

    with respx.mock(assert_all_called=True) as router:
        router.post("https://api.deepseek.com/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json={"choices": [{"message": {"content": review_card_with_finding_json()}}]},
            )
        )
        route = router.post("https://dingtalk.example.test/robot/send").mock(
            return_value=httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})
        )
        response = client.post(
            "/api/webhooks/gitlab/merge-request",
            json={
                **mr_payload_without_changed_files(),
                "project": {
                    "id": 2002,
                    "name": "demo-web",
                    "web_url": "https://gitlab.example.test/demo/web",
                },
                "changedFiles": [
                    {
                        "path": "src/pages/Home.tsx",
                        "diffText": "+ const enabled = import.meta.env.VITE_ORDER_ENABLED;",
                    }
                ],
            },
            headers={"X-Gitlab-Event": "Merge Request Hook"},
        )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    result = client.get(f"/api/review-tasks/{task_id}/result").json()["data"]
    body = json.loads(route.calls[0].request.content)
    markdown = body["markdown"]["text"]
    assert result["targetType"] == "WEB_PC"
    assert result["reminderCardEnabled"] is False
    assert result["riskItemCount"] == 0
    assert result["changeAnalysis"]["changeTypes"] == []
    assert result["changeAnalysis"]["changedFiles"][0]["matchedChangeTypes"] == []
    assert "配置变更（规则扫描）" not in markdown
    assert "Nacos" not in markdown
