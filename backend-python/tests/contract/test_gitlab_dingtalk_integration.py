from datetime import datetime
import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.rule_template.models import RuleTemplate


def seed_template(db_session: Session) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add(
        RuleTemplate(
            template_code="backend-default",
            template_name="后端默认审查模板",
            target_type="BACKEND",
            version=1,
            enabled_rule_codes=json.dumps(
                [
                    "DB_SQL_CHANGE_CHECK",
                    "CACHE_INVALIDATION_CHANGE_CHECK",
                    "MQ_PRODUCER_CHANGE_CHECK",
                    "CONFIG_RELEASE_CHECK",
                ]
            ),
            config_json=json.dumps(
                {
                    "focusChangeTypes": ["DB_SQL", "CACHE_INVALIDATION", "MQ_PRODUCER", "CONFIG"],
                    "recommendedChecks": ["确认变更影响范围。"],
                }
            ),
            status="ENABLED",
            description="stage3b",
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


def save_dingtalk_webhooks(client: TestClient, items: list[dict]) -> None:
    response = client.put("/api/code-quality-reviews/settings", json={"dingtalkWebhooks": items})
    assert response.status_code == 200


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
    assert result["changeAnalysis"]["changeTypes"] == ["DB", "DB_SQL"]
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
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
        router.post("https://dingtalk.example.test/robot/send").mock(
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
            enabled_rule_codes=json.dumps(["DB_SQL_CHANGE_CHECK", "CONFIG_RELEASE_CHECK"]),
            config_json=json.dumps(
                {
                    "focusChangeTypes": ["DB_SQL"],
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
                "ref": "refs/heads/feature/push",
                "before": "before-sha",
                "after": "after-sha",
                "user_name": "Alice",
                "user_username": "alice",
                "commits": [{"modified": ["src/main/resources/mapper/OrderMapper.xml"]}],
            },
            headers={"X-Gitlab-Event": "Push Hook"},
        )

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    result = client.get(f"/api/review-tasks/{task_id}/result").json()["data"]
    assert result["changeAnalysis"]["changeTypes"] == ["DB", "DB_SQL"]
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    assert detail["changedFilesSummary"]["source"] == "gitlab_compare_api"


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
                "ref": "refs/heads/feature/push",
                "before": "before-sha",
                "after": "after-sha",
                "user_name": "Alice",
                "user_username": "alice",
                "changedFiles": [
                    {
                        "path": "docs/readme.md",
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
    assert notifications[0]["target"] == "DINGTALK_PUSH_REVIEW_SUMMARY"


def test_push_with_reminders_uses_colored_type_tags(
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

    with respx.mock(assert_all_called=True) as router:
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
                "ref": "refs/heads/feature/push",
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
    body = json.loads(route.calls[0].request.content)
    markdown = body["markdown"]["text"]
    assert "配置变更（规则扫描）" in markdown
    assert '* <font color="#64748b">DB</font>' in markdown
    assert "数据库变更：请确认脚本是否需要准备" not in markdown


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
                        "path": "docs/readme.md",
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
    assert "MR 作者：Alice(@alice)" in markdown
    assert "GITLAB_MR_WEBHOOK" not in markdown
    assert "暂无需要特别维护的变更。" in markdown
    assert "未发现需要修复的问题。" in markdown
    assert f"详情：http://example.com/app/?taskId={task_id}" in markdown
