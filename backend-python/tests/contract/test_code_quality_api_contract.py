from datetime import datetime, timedelta
import json

import httpx
import respx
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.code_quality.models import CodeQualityReviewResult, CodeQualitySchedulerJob
from app.project_integration.models import GitLabMergeRequestEvent, Project
from app.review_record.models import ReviewTask
from app.rule_template.models import RuleTemplate


def seed_project(db_session: Session, provider_code: str | None = None) -> None:
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
            default_code_quality_provider_code=provider_code,
            dingtalk_webhook_id=None,
            status="ENABLED",
            description=None,
            created_at=now,
            updated_at=now,
        )
    )
    db_session.commit()


def seed_template(db_session: Session) -> None:
    now = datetime(2026, 5, 18, 10, 0, 0)
    db_session.add_all(
        [
            RuleTemplate(
                template_code="backend-default",
                template_name="后端默认审查模板",
                target_type="BACKEND",
                version=1,
                enabled_rule_codes=json.dumps(["DB_DATA_WRITE_CHANGE_CHECK"]),
                config_json=json.dumps(
                    {
                        "focusChangeTypes": ["DB_DATA_WRITE"],
                        "focusRuleCodes": ["DB_DATA_WRITE_CHANGE_CHECK"],
                        "recommendedChecks": [],
                    }
                ),
                status="ENABLED",
                description="stage4",
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
                description="stage4",
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()


def manual_request() -> dict:
    return {
        "projectId": 1,
        "profileCode": "backend-default-ai-review",
        "mode": "DIFF_TEXT",
        "title": "Manual AI review",
        "diffText": "diff --git a/src/OrderService.java b/src/OrderService.java\n+ order.setStatus(null);",
        "changedFiles": ["src/OrderService.java"],
    }


def push_payload(branch: str = "feature/push-ai", changed_files: list[dict] | None = None) -> dict:
    return {
        "object_kind": "push",
        "project": {
            "id": 1001,
            "name": "demo-service",
            "path_with_namespace": "demo/service",
            "web_url": "https://gitlab.example.com/demo/service",
        },
        "ref": f"refs/heads/{branch}",
        "before": "1111111111111111111111111111111111111111",
        "after": "2222222222222222222222222222222222222222",
        "user_name": "Alice",
        "user_username": "alice",
        "commits": [
            {
                "id": "2222222222222222222222222222222222222222",
                "added": [],
                "modified": ["src/OrderService.java"],
                "removed": [],
            }
        ],
        "changedFiles": changed_files
        if changed_files is not None
        else [
            {
                "path": "src/OrderService.java",
                "diffText": "+ public void touch() {}",
            }
        ],
    }


def review_card_json(summary: str = "发现一个问题", severity: str = "MAJOR") -> str:
    return json.dumps(
        {
            "summary": summary,
            "overallLevel": "HIGH",
            "findings": [
                {
                    "severity": severity,
                    "category": "CORRECTNESS",
                    "filePath": "src/OrderService.java",
                    "startLine": 12,
                    "endLine": 12,
                    "title": "空状态可能导致后续流程异常",
                    "body": "新增代码把订单状态设置为空，后续状态机可能无法处理。",
                    "suggestion": "保持明确状态值，并补充异常路径测试。",
                    "confidence": "HIGH",
                }
            ],
        },
        ensure_ascii=False,
    )


def legacy_review_card_json() -> str:
    return json.dumps(
        {
            "summary": "兼容旧字段",
            "findings": [
                {
                    "title": "默认配置变更需要确认",
                    "type": "other",
                    "body": "默认值变更可能影响过滤范围。",
                    "suggestion": "确认配置中心已有显式配置。",
                    "file_path": "src/main/java/com/demo/Config.java",
                    "line_range": [53, 53],
                }
            ],
        },
        ensure_ascii=False,
    )


def fix_patch_text() -> str:
    return (
        "diff --git a/src/OrderService.java b/src/OrderService.java\n"
        "--- a/src/OrderService.java\n"
        "+++ b/src/OrderService.java\n"
        "@@ -9,4 +9,4 @@ public void create(Order order) {\n"
        "-        order.setStatus(null);\n"
        "+        order.setStatus(OrderStatus.CREATED);\n"
        "     }\n"
    )


def test_manual_review_disabled_returns_clear_error(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_project(db_session, "DEEPSEEK")

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    assert response.status_code == 400
    assert response.json()["message"] == "Code quality review is disabled"


def test_provider_update_masks_api_key(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")

    response = client.put(
        "/api/code-quality-review-providers/OPENAI",
        json={"apiKey": "sk-test-secret-123456", "modelName": "gpt-test", "timeoutSeconds": 900},
    )

    assert response.status_code == 200
    openai = next(item for item in response.json()["data"] if item["providerCode"] == "OPENAI")
    assert openai["apiKeyConfigured"] is True
    assert openai["apiKeyMasked"] == "sk-t...3456"
    assert openai["timeoutSeconds"] == 900
    assert "sk-test-secret-123456" not in json.dumps(response.json(), ensure_ascii=False)


def test_xiaomimo_provider_update_masks_api_key(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")

    response = client.put(
        "/api/code-quality-review-providers/XIAOMIMO",
        json={"apiKey": "mimo-secret-123456", "modelName": "mimo-v2.5-pro"},
    )

    assert response.status_code == 200
    xiaomimo = next(item for item in response.json()["data"] if item["providerCode"] == "XIAOMIMO")
    assert xiaomimo["apiKeyConfigured"] is True
    assert xiaomimo["apiKeyMasked"] == "mimo...3456"
    assert "mimo-secret-123456" not in json.dumps(response.json(), ensure_ascii=False)


def test_provider_list_exposes_basic_provider_config(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")

    response = client.get("/api/code-quality-review-providers")

    assert response.status_code == 200
    providers = {item["providerCode"]: item for item in response.json()["data"]}
    assert set(providers) == {"OPENAI", "ANTHROPIC", "DEEPSEEK", "XIAOMIMO", "CUSTOM"}
    assert providers["OPENAI"]["providerType"] == "OPENAI_RESPONSES"
    assert providers["DEEPSEEK"]["providerType"] == "OPENAI_CHAT_COMPATIBLE"
    assert providers["XIAOMIMO"]["providerType"] == "OPENAI_CHAT_COMPATIBLE"
    assert providers["XIAOMIMO"]["endpointUrl"] == "https://api.xiaomimimo.com/v1"
    assert providers["XIAOMIMO"]["modelName"] == "mimo-v2.5-pro"
    assert providers["DEEPSEEK"]["timeoutSeconds"] is None
    assert "capabilities" not in providers["OPENAI"]
    assert "streamingConfig" not in providers["OPENAI"]


@respx.mock
def test_provider_connectivity_uses_unsaved_xiaomimo_draft(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    route = respx.post("https://draft-xiaomimo.example.com/v1/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": "pong"}}]})
    )

    response = client.post(
        "/api/code-quality-review-providers/XIAOMIMO/test",
        json={
            "endpointUrl": "https://draft-xiaomimo.example.com/v1",
            "modelName": "draft-mimo-model",
            "apiKey": "draft-xiaomimo-secret",
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "SUCCESS"
    assert data["success"] is True
    assert data["endpointUrl"] == "https://draft-xiaomimo.example.com/v1/chat/completions"
    assert data["modelName"] == "draft-mimo-model"
    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer draft-xiaomimo-secret"
    assert json.loads(request.content.decode("utf-8"))["model"] == "draft-mimo-model"
    assert "draft-xiaomimo-secret" not in json.dumps(response.json(), ensure_ascii=False)


def test_provider_connectivity_missing_key_returns_failed_result(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")

    response = client.post(
        "/api/code-quality-review-providers/XIAOMIMO/test",
        json={"endpointUrl": "https://api.xiaomimimo.com/v1", "modelName": "mimo-v2.5-pro"},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "FAILED"
    assert data["success"] is False
    assert "API key is required" in data["errorMessage"]


@respx.mock
def test_xiaomimo_provider_uses_openai_compatible_request(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("XIAOMIMO_API_KEY", "xiaomimo-secret")
    seed_project(db_session, "XIAOMIMO")
    route = respx.post("https://api.xiaomimimo.com/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={"choices": [{"message": {"content": review_card_json("XiaoMIMO 完成")}}]},
        )
    )

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "SUCCESS"
    assert data["provider"] == "XIAOMIMO"
    request_body = json.loads(route.calls[0].request.content.decode("utf-8"))
    assert request_body["model"] == "mimo-v2.5-pro"
    result = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-result").json()["data"]
    assert result["model"] == "mimo-v2.5-pro"
    assert result["findings"][0]["source"] == "XIAOMIMO"
    progress = client.get(
        f"/api/review-tasks/{data['taskId']}/code-quality-progress"
    ).json()["data"]
    phases = [event["phase"] for event in progress]
    request_start = next(event for event in progress if event["phase"] == "HTTP_REQUEST_START")
    assert "timeoutSeconds=1000" in request_start["detail"]
    assert "XIAOMIMO_REQUEST" in phases
    assert "XIAOMIMO_RESPONSE" in phases
    assert "XIAOMIMO_PARSE_RESULT" in phases
    assert "xiaomimo-secret" not in json.dumps(progress, ensure_ascii=False)


def test_config_endpoints_repair_legacy_code_quality_schema(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    db_session.execute(text("DROP TABLE IF EXISTS code_quality_model_providers"))
    db_session.execute(text("DROP TABLE IF EXISTS code_quality_review_profiles"))
    db_session.execute(text("DROP TABLE IF EXISTS code_quality_review_settings"))
    db_session.execute(
        text(
            """
            CREATE TABLE code_quality_review_settings (
              id INTEGER PRIMARY KEY,
              mr_auto_review_enabled BOOLEAN NOT NULL DEFAULT 1,
              created_at DATETIME NULL,
              updated_at DATETIME NULL
            )
            """
        )
    )
    db_session.execute(
        text(
            """
            CREATE TABLE code_quality_review_profiles (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              profile_code VARCHAR(64) NOT NULL UNIQUE,
              profile_name VARCHAR(128) NOT NULL,
              enabled BOOLEAN NOT NULL DEFAULT 1,
              provider VARCHAR(32) NOT NULL DEFAULT 'CODEX_CLI',
              model VARCHAR(128) NULL,
              trigger_on_manual BOOLEAN NOT NULL DEFAULT 1,
              trigger_on_mr BOOLEAN NOT NULL DEFAULT 1,
              trigger_on_push BOOLEAN NOT NULL DEFAULT 0,
              severity_threshold VARCHAR(32) NOT NULL DEFAULT 'MAJOR',
              block_on_severities TEXT NOT NULL,
              enabled_categories TEXT NOT NULL,
              ignored_paths TEXT NOT NULL,
              push_branch_patterns TEXT NOT NULL,
              push_max_changed_files INTEGER NULL,
              push_max_diff_bytes INTEGER NULL,
              push_debounce_seconds INTEGER NULL,
              trigger_only_when_risk_matched BOOLEAN NOT NULL DEFAULT 1,
              codex_prompt TEXT NULL,
              openai_instructions TEXT NULL,
              status VARCHAR(32) NOT NULL DEFAULT 'ENABLED',
              description VARCHAR(512) NULL,
              created_at DATETIME NULL,
              updated_at DATETIME NULL
            )
            """
        )
    )
    db_session.commit()

    settings = client.get("/api/code-quality-reviews/settings")
    profiles = client.get("/api/code-quality-review-profiles")
    providers = client.get("/api/code-quality-review-providers")

    assert settings.status_code == 200
    assert "defaultProviderCode" in settings.json()["data"]
    assert profiles.status_code == 200
    assert profiles.json()["data"]["items"][0]["profileCode"] == "backend-default-ai-review"
    assert providers.status_code == 200
    assert {item["providerCode"] for item in providers.json()["data"]} == {
        "OPENAI",
        "ANTHROPIC",
        "DEEPSEEK",
        "XIAOMIMO",
        "CUSTOM",
    }
    inspector = inspect(db_session.get_bind())
    setting_columns = {column["name"] for column in inspector.get_columns("code_quality_review_settings")}
    profile_columns = {column["name"] for column in inspector.get_columns("code_quality_review_profiles")}
    assert "review_enabled" in setting_columns
    assert "default_provider_code" in setting_columns
    assert "auto_fix_preview_enabled" in setting_columns
    assert "auto_fix_preview_severities" in setting_columns
    assert "provider_code" in profile_columns
    assert "review_instructions" in profile_columns


def test_rendered_prompt_uses_java_stronger_default(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")

    response = client.get("/api/code-quality-review-profiles/backend-default-ai-review/rendered-prompt")

    assert response.status_code == 200
    prompt = response.json()["data"]["prompt"]
    assert "审查原则" in prompt
    assert "事务与一致性" in prompt
    assert "每个 finding 都必须说明" in prompt


def test_default_push_hard_limits_are_unlimited(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")

    response = client.get("/api/code-quality-review-profiles/backend-default-ai-review")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["pushMaxChangedFiles"] == -1
    assert data["pushMaxDiffBytes"] == -1


def test_reset_default_prompt_uses_selected_profile_default(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    changed = client.put(
        "/api/code-quality-review-profiles/web-pc-default-ai-review",
        json={"reviewInstructions": "临时改成一段自定义 PC Prompt"},
    )
    assert changed.status_code == 200

    reset = client.post("/api/code-quality-review-profiles/web-pc-default-ai-review/reset-default-prompt")

    assert reset.status_code == 200
    data = reset.json()["data"]
    assert data["profileCode"] == "web-pc-default-ai-review"
    assert "资深 PC Web / H5" in data["reviewInstructions"]
    assert "资深后端" not in data["reviewInstructions"]


def test_loading_profiles_repairs_pc_profile_overwritten_by_backend_default(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    backend = client.get("/api/code-quality-review-profiles/backend-default-ai-review").json()["data"]
    overwritten = client.put(
        "/api/code-quality-review-profiles/web-pc-default-ai-review",
        json={"reviewInstructions": backend["reviewInstructions"]},
    )
    assert overwritten.status_code == 200

    profiles = client.get("/api/code-quality-review-profiles")

    assert profiles.status_code == 200
    pc_profile = next(
        item for item in profiles.json()["data"]["items"] if item["profileCode"] == "web-pc-default-ai-review"
    )
    assert "资深 PC Web / H5" in pc_profile["reviewInstructions"]
    assert "资深后端" not in pc_profile["reviewInstructions"]


def test_settings_returns_empty_dingtalk_webhook_list(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")

    response = client.get("/api/code-quality-reviews/settings")

    assert response.status_code == 200
    assert response.json()["data"]["reviewEnabled"] is True
    assert response.json()["data"]["autoFixPreviewEnabled"] is False
    assert response.json()["data"]["autoFixPreviewSeverities"] == ["CRITICAL"]
    assert response.json()["data"]["dingtalkWebhooks"] == []


def test_settings_filters_auto_fix_preview_severities(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")

    response = client.put(
        "/api/code-quality-reviews/settings",
        json={
            "autoFixPreviewEnabled": True,
            "autoFixPreviewSeverities": ["MAJOR", "bad", "CRITICAL", "MAJOR"],
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["autoFixPreviewEnabled"] is True
    assert response.json()["data"]["autoFixPreviewSeverities"] == ["MAJOR", "CRITICAL"]

    empty = client.put(
        "/api/code-quality-reviews/settings",
        json={"autoFixPreviewSeverities": []},
    )

    assert empty.status_code == 200
    assert empty.json()["data"]["autoFixPreviewSeverities"] == ["CRITICAL"]


@respx.mock
def test_settings_review_enabled_can_turn_on_ai_review_without_env_flag(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "false")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "settings-review-enabled-secret")
    seed_project(db_session, "DEEPSEEK")
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": review_card_json()}}]})
    )

    settings = client.put("/api/code-quality-reviews/settings", json={"reviewEnabled": True})
    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    assert settings.status_code == 200
    assert settings.json()["data"]["reviewEnabled"] is True
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "SUCCESS"


def test_settings_can_save_multiple_dingtalk_webhooks(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")

    saved = client.put(
        "/api/code-quality-reviews/settings",
        json={
            "dingtalkNotificationEnabled": True,
            "dingtalkWebhooks": [
                {
                    "name": "研发群",
                    "channel": "DINGTALK",
                    "webhookUrl": "https://dingtalk.example.test/robot/send?access_token=one",
                    "enabled": True,
                },
                {
                    "name": "测试群",
                    "channel": "DINGTALK",
                    "webhookUrl": "https://dingtalk.example.test/robot/send?access_token=two",
                    "enabled": False,
                },
            ],
        },
    )

    assert saved.status_code == 200
    items = saved.json()["data"]["dingtalkWebhooks"]
    assert len(items) == 2
    assert items[0]["name"] == "研发群"
    assert items[0]["enabled"] is True
    assert items[1]["enabled"] is False

    fetched = client.get("/api/code-quality-reviews/settings")
    assert fetched.status_code == 200
    assert len(fetched.json()["data"]["dingtalkWebhooks"]) == 2


@respx.mock
def test_settings_does_not_send_test_notification_for_new_webhook(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    route = respx.post("https://dingtalk.example.test/robot/send?access_token=test-new").mock(
        return_value=Response(200, json={"errcode": 0, "errmsg": "ok"})
    )

    saved = client.put(
        "/api/code-quality-reviews/settings",
        json={
            "dingtalkWebhooks": [
                {
                    "name": "测试群",
                    "channel": "DINGTALK",
                    "webhookUrl": "https://dingtalk.example.test/robot/send?access_token=test-new",
                    "enabled": True,
                }
            ],
        },
    )

    assert saved.status_code == 200
    assert not route.called
    assert "webhookTestResults" not in saved.json()["data"]


def test_settings_update_disables_omitted_webhook(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    created = client.put(
        "/api/code-quality-reviews/settings",
        json={
            "dingtalkWebhooks": [
                {
                    "name": "研发群",
                    "channel": "DINGTALK",
                    "webhookUrl": "https://dingtalk.example.test/robot/send?access_token=one",
                    "enabled": True,
                },
                {
                    "name": "测试群",
                    "channel": "DINGTALK",
                    "webhookUrl": "https://dingtalk.example.test/robot/send?access_token=two",
                    "enabled": True,
                },
            ]
        },
    ).json()["data"]["dingtalkWebhooks"]

    updated = client.put(
        "/api/code-quality-reviews/settings",
        json={
            "dingtalkWebhooks": [
                {
                    "id": created[0]["id"],
                    "name": "研发群-新",
                    "channel": "DINGTALK",
                    "webhookUrl": "https://dingtalk.example.test/robot/send?access_token=one-new",
                    "enabled": True,
                }
            ]
        },
    )

    assert updated.status_code == 200
    items = updated.json()["data"]["dingtalkWebhooks"]
    assert len(items) == 1
    assert items[0]["name"] == "研发群-新"
    assert items[0]["enabled"] is True


@respx.mock
def test_settings_does_not_send_test_notification_when_reenabling_existing_webhook(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    created = client.put(
        "/api/code-quality-reviews/settings",
        json={
            "dingtalkWebhooks": [
                {
                    "name": "测试群",
                    "channel": "DINGTALK",
                    "webhookUrl": "https://dingtalk.example.test/robot/send?access_token=reenable",
                    "enabled": False,
                }
            ]
        },
    )
    assert created.status_code == 200
    webhook = created.json()["data"]["dingtalkWebhooks"][0]
    route = respx.post("https://dingtalk.example.test/robot/send?access_token=reenable").mock(
        return_value=Response(200, json={"errcode": 0, "errmsg": "ok"})
    )

    updated = client.put(
        "/api/code-quality-reviews/settings",
        json={
            "dingtalkWebhooks": [
                {
                    "id": webhook["id"],
                    "name": "测试群",
                    "channel": "DINGTALK",
                    "webhookUrl": "https://dingtalk.example.test/robot/send?access_token=reenable",
                    "enabled": True,
                }
            ]
        },
    )

    assert updated.status_code == 200
    assert not route.called
    assert "webhookTestResults" not in updated.json()["data"]


def test_settings_rejects_invalid_or_duplicate_dingtalk_webhooks(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")

    invalid = client.put(
        "/api/code-quality-reviews/settings",
        json={
            "dingtalkWebhooks": [
                {
                    "name": "",
                    "channel": "DINGTALK",
                    "webhookUrl": "ftp://invalid.example.test",
                    "enabled": True,
                }
            ]
        },
    )
    assert invalid.status_code == 400

    duplicate = client.put(
        "/api/code-quality-reviews/settings",
        json={
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
            ]
        },
    )
    assert duplicate.status_code == 400


@respx.mock
def test_deepseek_manual_review_saves_result_and_progress(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    seed_project(db_session, "DEEPSEEK")
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": review_card_json()}}]})
    )

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "SUCCESS"
    assert data["provider"] == "DEEPSEEK"
    result = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-result").json()["data"]
    assert result["overallLevel"] == "HIGH"
    assert result["findings"][0]["source"] == "DEEPSEEK"
    progress = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-progress").json()["data"]
    phases = [event["phase"] for event in progress]
    request_start = next(event for event in progress if event["phase"] == "HTTP_REQUEST_START")
    assert "timeoutSeconds=1000" in request_start["detail"]
    assert "DEEPSEEK_REQUEST_DEBUG" in phases
    assert "DEEPSEEK_RESPONSE_RAW" in phases
    assert "DEEPSEEK_PARSE_RESULT" in phases
    assert "deepseek-secret" not in json.dumps(progress, ensure_ascii=False)


@respx.mock
def test_project_group_multi_model_manual_review_saves_result_list(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    monkeypatch.setenv("XIAOMIMO_API_KEY", "mimo-secret")
    seed_project(db_session, None)

    default_group = next(
        item for item in client.get("/api/project-groups").json()["data"]["items"]
        if item["groupCode"] == "default"
    )
    bind = client.put("/api/projects/1/group", json={"groupId": default_group["id"]})
    assert bind.status_code == 200
    update_group = client.put(
        f"/api/project-groups/{default_group['id']}",
        json={
            "groupName": default_group["groupName"],
            "groupCode": default_group["groupCode"],
            "defaultCodeQualityProfileCode": "backend-default-ai-review",
            "aiReviewModels": [
                {"providerCode": "DEEPSEEK", "modelName": "deepseek-v4-pro", "displayName": "DeepSeek 主审", "sortOrder": 10},
                {"providerCode": "XIAOMIMO", "modelName": "mimo-v2.5-pro", "displayName": "MiMo 复审", "sortOrder": 20},
            ],
        },
    )
    assert update_group.status_code == 200
    deepseek_route = respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": review_card_json("DeepSeek 完成")}}]})
    )
    mimo_route = respx.post("https://api.xiaomimimo.com/v1/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": review_card_json("MiMo 完成")}}]})
    )

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    assert response.status_code == 200
    task_id = response.json()["data"]["taskId"]
    results_response = client.get(f"/api/review-tasks/{task_id}/code-quality-results")
    assert results_response.status_code == 200
    results = results_response.json()["data"]
    assert [item["provider"] for item in results] == ["DEEPSEEK", "XIAOMIMO"]
    assert [item["displayName"] for item in results] == ["DeepSeek 主审", "MiMo 复审"]
    assert all(item["status"] == "SUCCESS" for item in results)
    assert deepseek_route.called
    assert mimo_route.called


@respx.mock
def test_provider_timeout_config_overrides_deepseek_default(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    seed_project(db_session, "DEEPSEEK")
    update_response = client.put(
        "/api/code-quality-review-providers/DEEPSEEK",
        json={"timeoutSeconds": 333},
    )
    assert update_response.status_code == 200
    assert next(
        item for item in update_response.json()["data"] if item["providerCode"] == "DEEPSEEK"
    )["timeoutSeconds"] == 333
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": review_card_json()}}]})
    )

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    assert response.status_code == 200
    data = response.json()["data"]
    progress = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-progress").json()["data"]
    request_start = next(event for event in progress if event["phase"] == "HTTP_REQUEST_START")
    assert "timeoutSeconds=333" in request_start["detail"]


@respx.mock
def test_fix_preview_generates_and_caches_patch(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("CODE_QUALITY_FIX_PREVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fix-preview-secret")
    calls = []

    def provider_response(request: httpx.Request) -> Response:
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return Response(200, json={"choices": [{"message": {"content": review_card_json()}}]})
        return Response(200, json={"choices": [{"message": {"content": fix_patch_text()}}]})

    respx.post("https://api.deepseek.com/chat/completions").mock(side_effect=provider_response)
    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {
                "id": 1001,
                "name": "demo-service",
                "web_url": "https://gitlab.example.com/demo/service",
            },
            "object_attributes": {
                "iid": 21,
                "action": "open",
                "source_branch": "feature/fix-preview",
                "target_branch": "main",
            },
            "changedFiles": [
                {
                    "path": "src/OrderService.java",
                    "diffText": (
                        "@@ -9,4 +9,4 @@ public void create(Order order) {\n"
                        "+        order.setStatus(null);\n"
                        "     }"
                    ),
                }
            ],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )
    task_id = created.json()["data"]["taskId"]

    generated = client.post(
        f"/api/review-tasks/{task_id}/code-quality-fix-preview",
        json={"findingIndex": 0},
    )
    cached = client.post(
        f"/api/review-tasks/{task_id}/code-quality-fix-preview",
        json={"findingIndex": 0},
    )

    assert generated.status_code == 200
    data = generated.json()["data"]
    assert data["status"] == "SUCCESS"
    assert data["filePath"] == "src/OrderService.java"
    assert data["patchText"].startswith("diff --git ")
    assert "OrderStatus.CREATED" in data["patchText"]
    assert cached.json()["data"]["patchText"] == data["patchText"]
    assert len(calls) == 2
    progress = client.get(f"/api/review-tasks/{task_id}/code-quality-progress").json()["data"]
    assert "FIX_PREVIEW_SAVED" in [event["phase"] for event in progress]
    assert "fix-preview-secret" not in json.dumps(progress, ensure_ascii=False)


@respx.mock
def test_ai_review_auto_generates_fix_previews_after_success(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("CODE_QUALITY_FIX_PREVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "auto-fix-secret")
    enabled = update_default_push_policy(client, autoFixPreviewEnabled=True)
    assert enabled["autoFixPreviewEnabled"] is True
    calls = []

    def provider_response(request: httpx.Request) -> Response:
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return Response(200, json={"choices": [{"message": {"content": review_card_json("需要修复", "CRITICAL")}}]})
        return Response(200, json={"choices": [{"message": {"content": fix_patch_text()}}]})

    respx.post("https://api.deepseek.com/chat/completions").mock(side_effect=provider_response)

    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {"id": 1001, "name": "demo-service", "web_url": "https://gitlab.example.com/demo/service"},
            "object_attributes": {"iid": 24, "action": "open", "source_branch": "feature/auto-fix", "target_branch": "main"},
            "changedFiles": [
                {
                    "path": "src/OrderService.java",
                    "diffText": "@@ -9,4 +9,4 @@ public void create(Order order) {\n+        order.setStatus(null);",
                }
            ],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )
    task_id = created.json()["data"]["taskId"]

    result = client.get(f"/api/review-tasks/{task_id}/code-quality-result").json()["data"]
    previews = client.get(f"/api/review-tasks/{task_id}/code-quality-fix-previews").json()["data"]

    assert result["status"] == "SUCCESS"
    assert len(previews) == 1
    assert previews[0]["status"] == "SUCCESS"
    assert "OrderStatus.CREATED" in previews[0]["patchText"]
    assert len(calls) == 2
    progress = client.get(f"/api/review-tasks/{task_id}/code-quality-progress").json()["data"]
    phases = [event["phase"] for event in progress]
    assert "FIX_PREVIEW_AUTO_QUEUED" in phases
    assert "FIX_PREVIEW_SAVED" in phases
    assert "auto-fix-secret" not in json.dumps(progress, ensure_ascii=False)


@respx.mock
def test_auto_review_uses_project_group_profile_before_target_type_profile(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    seed_project(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "group-profile-secret")
    group = client.post(
        "/api/project-groups",
        json={
            "groupName": "PC 业务组",
            "groupCode": "pc",
            "defaultCodeQualityProfileCode": "web-pc-default-ai-review",
        },
    ).json()["data"]
    bind = client.put("/api/projects/1/group", json={"groupId": group["id"]})
    assert bind.status_code == 200

    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": review_card_json("组模板优先", "MAJOR")}}]})
    )

    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {"id": 1001, "name": "demo-service", "web_url": "https://gitlab.example.com/demo/service"},
            "object_attributes": {"iid": 34, "action": "open", "source_branch": "feature/group-profile", "target_branch": "main"},
            "changedFiles": [
                {
                    "path": "src/main/java/com/demo/OrderService.java",
                    "diffText": "@@ -9,4 +9,4 @@ public void create(Order order) {\n+        order.setStatus(null);",
                }
            ],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )
    task_id = created.json()["data"]["taskId"]

    result = client.get(f"/api/review-tasks/{task_id}/code-quality-result").json()["data"]
    assert result["status"] == "SUCCESS"
    assert result["profileCode"] == "web-pc-default-ai-review"
    progress = client.get(f"/api/review-tasks/{task_id}/code-quality-progress").json()["data"]
    assert "group-profile-secret" not in json.dumps(progress, ensure_ascii=False)


@respx.mock
def test_project_target_provider_override_wins_over_global_default_for_auto_mr_review(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    seed_project(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("XIAOMIMO_API_KEY", "xiaomimo-secret")
    settings = client.put("/api/code-quality-reviews/settings", json={"defaultProviderCode": "DEEPSEEK"})
    assert settings.status_code == 200
    target_config = client.put(
        "/api/projects/1/target-configs/BACKEND",
        json={"providerCode": "XIAOMIMO"},
    )
    assert target_config.status_code == 200

    xiaomimo = respx.post("https://api.xiaomimimo.com/v1/chat/completions").mock(
        return_value=Response(
            200,
            json={"choices": [{"message": {"content": review_card_json("XiaomiMIMO 完成", "MAJOR")}}]},
        )
    )

    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {"id": 1001, "name": "demo-service", "web_url": "https://gitlab.example.com/demo/service"},
            "object_attributes": {"iid": 36, "action": "open", "source_branch": "feature/xiaomi-provider", "target_branch": "main"},
            "changedFiles": [
                {
                    "path": "src/main/java/com/demo/OrderService.java",
                    "diffText": "@@ -9,4 +9,4 @@ public void create(Order order) {\n+        order.setStatus(null);",
                }
            ],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )

    assert created.status_code == 200
    task_id = created.json()["data"]["taskId"]
    result = client.get(f"/api/review-tasks/{task_id}/code-quality-result").json()["data"]
    progress = client.get(f"/api/review-tasks/{task_id}/code-quality-progress").json()["data"]
    assert result["status"] == "SUCCESS"
    assert result["provider"] == "XIAOMIMO"
    assert xiaomimo.called
    assert "xiaomimo-secret" not in json.dumps(progress, ensure_ascii=False)


def test_non_default_project_group_without_profile_records_ai_review_failure(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    seed_project(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    group = client.post(
        "/api/project-groups",
        json={"groupName": "未配置模板组", "groupCode": "without-profile"},
    ).json()["data"]
    bind = client.put("/api/projects/1/group", json={"groupId": group["id"]})
    assert bind.status_code == 200

    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {"id": 1001, "name": "demo-service", "web_url": "https://gitlab.example.com/demo/service"},
            "object_attributes": {"iid": 35, "action": "open", "source_branch": "feature/no-group-profile", "target_branch": "main"},
            "changedFiles": [
                {
                    "path": "src/main/java/com/demo/OrderService.java",
                    "diffText": "@@ -9,4 +9,4 @@ public void create(Order order) {\n+        order.setStatus(null);",
                }
            ],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )
    task_id = created.json()["data"]["taskId"]

    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    assert detail["status"] == "SUCCESS"
    assert detail["codeQualityProfileCode"] is None
    result = client.get(f"/api/review-tasks/{task_id}/code-quality-result").json()["data"]
    assert result["status"] == "SKIPPED"
    assert "项目所属项目组未设置 AI Review 模板" in result["errorMessage"]


@respx.mock
def test_ai_review_does_not_auto_generate_fix_previews_for_non_critical_findings(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("CODE_QUALITY_FIX_PREVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "auto-fix-non-critical-secret")
    enabled = update_default_push_policy(client, autoFixPreviewEnabled=True)
    assert enabled["autoFixPreviewEnabled"] is True
    calls = []

    def provider_response(request: httpx.Request) -> Response:
        calls.append(json.loads(request.content))
        return Response(200, json={"choices": [{"message": {"content": review_card_json("非紧急问题", "MAJOR")}}]})

    respx.post("https://api.deepseek.com/chat/completions").mock(side_effect=provider_response)

    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {"id": 1001, "name": "demo-service", "web_url": "https://gitlab.example.com/demo/service"},
            "object_attributes": {"iid": 26, "action": "open", "source_branch": "feature/non-critical-fix", "target_branch": "main"},
            "changedFiles": [
                {
                    "path": "src/OrderService.java",
                    "diffText": "@@ -9,4 +9,4 @@ public void create(Order order) {\n+        order.setStatus(null);",
                }
            ],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )
    task_id = created.json()["data"]["taskId"]

    result = client.get(f"/api/review-tasks/{task_id}/code-quality-result").json()["data"]
    previews = client.get(f"/api/review-tasks/{task_id}/code-quality-fix-previews").json()["data"]

    assert result["status"] == "SUCCESS"
    assert result["findings"][0]["severity"] == "MAJOR"
    assert previews == []
    assert len(calls) == 1
    progress = client.get(f"/api/review-tasks/{task_id}/code-quality-progress").json()["data"]
    phases = [event["phase"] for event in progress]
    assert "FIX_PREVIEW_AUTO_QUEUED" not in phases


@respx.mock
def test_ai_review_auto_generates_fix_previews_for_configured_major_findings(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("CODE_QUALITY_FIX_PREVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "auto-fix-major-secret")
    enabled = update_default_push_policy(
        client,
        autoFixPreviewEnabled=True,
        autoFixPreviewSeverities=["CRITICAL", "MAJOR"],
    )
    assert enabled["autoFixPreviewSeverities"] == ["CRITICAL", "MAJOR"]
    calls = []

    def provider_response(request: httpx.Request) -> Response:
        calls.append(json.loads(request.content))
        if len(calls) == 1:
            return Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": review_card_json("高风险也需要修复", "MAJOR")}}
                    ]
                },
            )
        return Response(200, json={"choices": [{"message": {"content": fix_patch_text()}}]})

    respx.post("https://api.deepseek.com/chat/completions").mock(side_effect=provider_response)

    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {"id": 1001, "name": "demo-service", "web_url": "https://gitlab.example.com/demo/service"},
            "object_attributes": {
                "iid": 27,
                "action": "open",
                "source_branch": "feature/major-auto-fix",
                "target_branch": "main",
            },
            "changedFiles": [
                {
                    "path": "src/OrderService.java",
                    "diffText": "@@ -9,4 +9,4 @@ public void create(Order order) {\n+        order.setStatus(null);",
                }
            ],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )
    task_id = created.json()["data"]["taskId"]

    result = client.get(f"/api/review-tasks/{task_id}/code-quality-result").json()["data"]
    previews = client.get(f"/api/review-tasks/{task_id}/code-quality-fix-previews").json()["data"]

    assert result["status"] == "SUCCESS"
    assert result["findings"][0]["severity"] == "MAJOR"
    assert len(previews) == 1
    assert previews[0]["status"] == "SUCCESS"
    assert len(calls) == 2
    progress = client.get(f"/api/review-tasks/{task_id}/code-quality-progress").json()["data"]
    phases = [event["phase"] for event in progress]
    assert "FIX_PREVIEW_AUTO_QUEUED" in phases
    assert "FIX_PREVIEW_SAVED" in phases
    assert "auto-fix-major-secret" not in json.dumps(progress, ensure_ascii=False)


@respx.mock
def test_ai_review_does_not_auto_generate_fix_previews_when_disabled(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("CODE_QUALITY_FIX_PREVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "auto-fix-disabled-secret")
    calls = []

    def provider_response(request: httpx.Request) -> Response:
        calls.append(json.loads(request.content))
        return Response(200, json={"choices": [{"message": {"content": review_card_json("需要手动修复预览")}}]})

    respx.post("https://api.deepseek.com/chat/completions").mock(side_effect=provider_response)

    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {"id": 1001, "name": "demo-service", "web_url": "https://gitlab.example.com/demo/service"},
            "object_attributes": {"iid": 25, "action": "open", "source_branch": "feature/manual-fix", "target_branch": "main"},
            "changedFiles": [
                {
                    "path": "src/OrderService.java",
                    "diffText": "@@ -9,4 +9,4 @@ public void create(Order order) {\n+        order.setStatus(null);",
                }
            ],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )
    task_id = created.json()["data"]["taskId"]

    result = client.get(f"/api/review-tasks/{task_id}/code-quality-result").json()["data"]
    previews = client.get(f"/api/review-tasks/{task_id}/code-quality-fix-previews").json()["data"]

    assert result["status"] == "SUCCESS"
    assert previews == []
    assert len(calls) == 1
    progress = client.get(f"/api/review-tasks/{task_id}/code-quality-progress").json()["data"]
    phases = [event["phase"] for event in progress]
    assert "FIX_PREVIEW_AUTO_QUEUED" not in phases


@respx.mock
def test_fix_preview_queues_without_running_provider_immediately(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    from app.code_quality import service

    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.delenv("CODE_QUALITY_FIX_PREVIEW_INLINE", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fix-preview-secret")
    submitted: list[dict] = []
    monkeypatch.setattr(
        service._executor,
        "submit",
        lambda fn, *args, **kwargs: submitted.append({"fn": fn.__name__, "args": args, "kwargs": kwargs}),
    )
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": review_card_json()}}]})
    )
    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {"id": 1001, "name": "demo-service", "web_url": "https://gitlab.example.com/demo/service"},
            "object_attributes": {"iid": 25, "action": "open", "source_branch": "feature/queued-fix", "target_branch": "main"},
            "changedFiles": [
                {
                    "path": "src/OrderService.java",
                    "diffText": "@@ -9,4 +9,4 @@ public void create(Order order) {\n+        order.setStatus(null);",
                }
            ],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )
    task_id = created.json()["data"]["taskId"]

    response = client.post(f"/api/review-tasks/{task_id}/code-quality-fix-preview", json={"findingIndex": 0})

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "QUEUED"
    assert submitted[0]["fn"] == "run_auto_fix_preview_job"
    assert submitted[0]["kwargs"]["priority"] == service.FIX_PREVIEW_JOB_PRIORITY
    queue = client.get("/api/code-quality-reviews/job-queue").json()["data"]
    assert queue["activeCount"] == 1
    assert queue["groups"][0]["fixPreviewJobs"][0]["status"] == "QUEUED"


def test_job_queue_keeps_active_jobs_and_recently_updated_finished_jobs(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime.now()
    old = now - timedelta(days=3)
    within_queue_window = now - timedelta(hours=12)
    db_session.add_all(
        [
            CodeQualitySchedulerJob(
                id=91001,
                job_type="AI_REVIEW",
                task_id=91001,
                project_id=1,
                finding_index=None,
                status="QUEUED",
                priority=10,
                label="old active",
                file_path=None,
                error_message=None,
                queued_at=old,
                started_at=None,
                finished_at=None,
                created_at=old,
                updated_at=old,
            ),
            CodeQualitySchedulerJob(
                id=91002,
                job_type="FIX_PREVIEW",
                task_id=91002,
                project_id=1,
                finding_index=0,
                status="SUCCESS",
                priority=20,
                label="recently finished",
                file_path="src/OrderService.java",
                error_message=None,
                queued_at=old,
                started_at=old,
                finished_at=within_queue_window,
                created_at=old,
                updated_at=within_queue_window,
            ),
            CodeQualitySchedulerJob(
                id=91003,
                job_type="FIX_PREVIEW",
                task_id=91003,
                project_id=1,
                finding_index=1,
                status="SUCCESS",
                priority=20,
                label="old finished",
                file_path="src/Old.java",
                error_message=None,
                queued_at=old,
                started_at=old,
                finished_at=old,
                created_at=old,
                updated_at=old,
            ),
        ]
    )
    db_session.commit()

    queue = client.get("/api/code-quality-reviews/job-queue").json()["data"]

    task_ids = {group["taskId"] for group in queue["groups"]}
    assert 91001 in task_ids
    assert 91002 in task_ids
    assert 91003 not in task_ids
    assert [group["taskId"] for group in queue["groups"][:2]] == [91002, 91001]


def test_job_queue_schema_adds_scheduler_indexes(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.get("/api/code-quality-reviews/job-queue")

    assert response.status_code == 200
    inspector = inspect(db_session.get_bind())
    indexes = {index["name"] for index in inspector.get_indexes("code_quality_scheduler_jobs")}
    assert "idx_code_quality_scheduler_jobs_status_priority" in indexes
    assert "idx_code_quality_scheduler_jobs_task" in indexes
    assert "idx_code_quality_scheduler_jobs_status_updated" in indexes
    assert "idx_code_quality_scheduler_jobs_status_queue" in indexes


def test_job_queue_limits_loaded_active_jobs_but_reports_total_active_count(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime.now()
    db_session.add_all(
        [
            CodeQualitySchedulerJob(
                id=92000 + index,
                job_type="AI_REVIEW",
                task_id=92000 + index,
                project_id=1,
                finding_index=None,
                status="QUEUED",
                priority=10,
                label=f"active {index}",
                file_path=None,
                error_message=None,
                queued_at=now - timedelta(seconds=index),
                started_at=None,
                finished_at=None,
                created_at=now - timedelta(seconds=index),
                updated_at=now - timedelta(seconds=index),
            )
            for index in range(150)
        ]
    )
    db_session.commit()

    queue = client.get("/api/code-quality-reviews/job-queue").json()["data"]

    assert queue["activeCount"] == 150
    assert len(queue["groups"]) == 100


@respx.mock
def test_fix_preview_rejects_missing_file_diff(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fix-preview-secret")
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": review_card_json()}}]})
    )
    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {"id": 1001, "name": "demo-service", "web_url": "https://gitlab.example.com/demo/service"},
            "object_attributes": {"iid": 22, "action": "open", "source_branch": "feature/no-diff", "target_branch": "main"},
            "changedFiles": [{"path": "src/OrderService.java", "diffText": "+        order.setStatus(null);"}],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )
    task_id = created.json()["data"]["taskId"]
    event = db_session.query(GitLabMergeRequestEvent).filter_by(task_id=task_id).one()
    event.changed_files_summary = json.dumps(
        {"count": 1, "source": "payload", "files": [{"path": "src/OrderService.java"}]},
        ensure_ascii=False,
    )
    db_session.commit()

    response = client.post(
        f"/api/review-tasks/{task_id}/code-quality-fix-preview",
        json={"findingIndex": 0},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "SKIPPED"
    assert data["errorMessage"] == "Current task did not save diff text for this file"
    previews = client.get(f"/api/review-tasks/{task_id}/code-quality-fix-previews").json()["data"]
    assert previews[0]["status"] == "SKIPPED"


@respx.mock
def test_fix_preview_saves_failed_when_provider_returns_non_diff(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("CODE_QUALITY_FIX_PREVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "fix-preview-secret")
    calls = []

    def provider_response(request: httpx.Request) -> Response:
        calls.append(json.loads(request.content))
        content = review_card_json() if len(calls) == 1 else "建议把状态改成 CREATED。"
        return Response(200, json={"choices": [{"message": {"content": content}}]})

    respx.post("https://api.deepseek.com/chat/completions").mock(side_effect=provider_response)
    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {"id": 1001, "name": "demo-service", "web_url": "https://gitlab.example.com/demo/service"},
            "object_attributes": {"iid": 23, "action": "open", "source_branch": "feature/bad-patch", "target_branch": "main"},
            "changedFiles": [
                {
                    "path": "src/OrderService.java",
                    "diffText": "@@ -9,4 +9,4 @@ public void create(Order order) {\n+        order.setStatus(null);",
                }
            ],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )
    task_id = created.json()["data"]["taskId"]

    response = client.post(
        f"/api/review-tasks/{task_id}/code-quality-fix-preview",
        json={"findingIndex": 0},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "FAILED"
    assert data["patchText"] is None
    assert "unified diff" in data["errorMessage"]
    result = client.get(f"/api/review-tasks/{task_id}/code-quality-result").json()["data"]
    assert result["status"] == "SUCCESS"


@respx.mock
def test_provider_legacy_finding_fields_are_normalized(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-secret")
    seed_project(db_session, "DEEPSEEK")
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": legacy_review_card_json()}}]})
    )

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    assert response.status_code == 200
    data = response.json()["data"]
    result = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-result").json()["data"]
    finding = result["findings"][0]
    assert finding["filePath"] == "src/main/java/com/demo/Config.java"
    assert finding["startLine"] == 53
    assert finding["endLine"] == 53
    assert finding["category"] == "CODE_QUALITY"
    assert finding["severity"] == "MINOR"
    assert result["overallLevel"] == "MEDIUM"


@respx.mock
def test_custom_provider_uses_non_stream_request(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    seed_project(db_session, "CUSTOM")
    client.put(
        "/api/code-quality-review-providers/CUSTOM",
        json={
            "enabled": True,
            "endpointUrl": "https://custom.example.com/v1",
            "modelName": "custom-model",
            "apiKey": "custom-secret",
        },
    )
    non_stream_route = respx.post("https://custom.example.com/v1/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": review_card_json("Custom 非流式")}}]})
    )

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    assert response.status_code == 200
    data = response.json()["data"]
    progress = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-progress").json()["data"]
    assert "STREAM_START" not in [event["phase"] for event in progress]
    assert non_stream_route.called


def test_deepseek_missing_api_key_saves_failed_with_validation_phase(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    seed_project(db_session, "DEEPSEEK")

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "FAILED"
    result = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-result").json()["data"]
    assert result["status"] == "FAILED"
    assert "API key is required" in result["errorMessage"]
    progress = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-progress").json()["data"]
    phases = [event["phase"] for event in progress]
    assert "PROVIDER_SELECTED" in phases
    assert "REQUEST_VALIDATED" in phases
    assert progress[phases.index("REQUEST_VALIDATED")]["level"] == "ERROR"
    assert "RESULT_SAVED" in phases
    detail = client.get(f"/api/review-tasks/{data['taskId']}").json()["data"]
    assert detail["status"] == "FAILED"


def test_failure_notifications_return_recent_ai_review_failures_only(
    client: TestClient,
    db_session: Session,
) -> None:
    seed_project(db_session, "DEEPSEEK")
    now = datetime.now()
    db_session.add_all(
        [
            ReviewTask(
                id=101,
                project_id=1,
                trigger_type="GITLAB_MR_WEBHOOK",
                external_source_id="!101",
                external_url=None,
                source_branch="feature/recent-b",
                target_branch="main",
                commit_sha=None,
                before_sha=None,
                after_sha=None,
                author_name=None,
                author_username=None,
                template_code="backend-default",
                target_type="BACKEND",
                target_types_json=json.dumps(["BACKEND"]),
                code_quality_profile_code="backend-default-ai-review",
                status="FAILED",
                risk_level="LOW",
                error_message="recent b",
                started_at=now,
                finished_at=now,
                created_at=now,
                updated_at=now,
            ),
            ReviewTask(
                id=102,
                project_id=1,
                trigger_type="GITLAB_PUSH_WEBHOOK",
                external_source_id=None,
                external_url=None,
                source_branch="feature/recent-a",
                target_branch=None,
                commit_sha=None,
                before_sha=None,
                after_sha=None,
                author_name=None,
                author_username=None,
                template_code="backend-default",
                target_type="BACKEND",
                target_types_json=json.dumps(["BACKEND"]),
                code_quality_profile_code="backend-default-ai-review",
                status="FAILED",
                risk_level="LOW",
                error_message="recent a",
                started_at=now,
                finished_at=now,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.add_all(
        [
            CodeQualityReviewResult(
                task_id=101,
                project_id=1,
                profile_code="backend-default-ai-review",
                provider="DEEPSEEK",
                model="deepseek-test",
                status="FAILED",
                overall_level=None,
                summary=None,
                finding_count=0,
                findings_json="[]",
                raw_output=None,
                exit_code=None,
                error_message="recent b failed",
                started_at=now,
                finished_at=now,
                created_at=now,
                updated_at=now,
            ),
            CodeQualityReviewResult(
                task_id=102,
                project_id=1,
                profile_code="backend-default-ai-review",
                provider="OPENAI",
                model="gpt-test",
                status="FAILED",
                overall_level=None,
                summary=None,
                finding_count=0,
                findings_json="[]",
                raw_output=None,
                exit_code=None,
                error_message="recent a failed",
                started_at=now,
                finished_at=now,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.add_all(
        [
            CodeQualitySchedulerJob(
                job_type="AI_REVIEW",
                task_id=101,
                project_id=1,
                finding_index=None,
                status="FAILED",
                priority=10,
                label="recent b",
                file_path=None,
                error_message="job recent b failed",
                queued_at=now - timedelta(minutes=4),
                started_at=now - timedelta(minutes=3),
                finished_at=now - timedelta(minutes=2),
                created_at=now - timedelta(minutes=2),
                updated_at=now - timedelta(minutes=2),
            ),
            CodeQualitySchedulerJob(
                job_type="AI_REVIEW",
                task_id=102,
                project_id=1,
                finding_index=None,
                status="FAILED",
                priority=10,
                label="recent a",
                file_path=None,
                error_message=None,
                queued_at=now - timedelta(minutes=12),
                started_at=now - timedelta(minutes=11),
                finished_at=now - timedelta(minutes=10),
                created_at=now - timedelta(minutes=10),
                updated_at=now - timedelta(minutes=10),
            ),
            CodeQualitySchedulerJob(
                job_type="AI_REVIEW",
                task_id=101,
                project_id=1,
                finding_index=None,
                status="FAILED",
                priority=10,
                label="old",
                file_path=None,
                error_message="old failed",
                queued_at=now - timedelta(hours=25),
                started_at=now - timedelta(hours=25),
                finished_at=now - timedelta(hours=25),
                created_at=now - timedelta(hours=25),
                updated_at=now - timedelta(hours=25),
            ),
            CodeQualitySchedulerJob(
                job_type="FIX_PREVIEW",
                task_id=101,
                project_id=1,
                finding_index=0,
                status="FAILED",
                priority=50,
                label="fix failed",
                file_path="src/OrderService.java",
                error_message="fix failed",
                queued_at=now,
                started_at=now,
                finished_at=now,
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db_session.commit()

    response = client.get("/api/code-quality-reviews/failure-notifications")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["failureCount"] == 2
    assert [item["taskId"] for item in data["items"]] == [101, 102]
    assert data["items"][0]["provider"] == "DEEPSEEK"
    assert data["items"][0]["errorMessage"] == "job recent b failed"
    assert data["items"][1]["provider"] == "OPENAI"
    assert data["items"][1]["errorMessage"] == "recent a failed"


@respx.mock
def test_deepseek_http_failure_has_diagnostic_phases_and_masks_key(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-http-secret")
    seed_project(db_session, "DEEPSEEK")
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(401, json={"error": {"message": "invalid api key"}})
    )

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    data = response.json()["data"]
    assert data["status"] == "FAILED"
    result = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-result").json()["data"]
    assert result["status"] == "FAILED"
    assert "http_status_error" in result["errorMessage"]
    progress = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-progress").json()["data"]
    phases = [event["phase"] for event in progress]
    assert "HTTP_REQUEST_START" in phases
    assert "HTTP_RESPONSE_HEADERS" in phases
    assert "HTTP_RESPONSE_BODY_PREVIEW" in phases
    assert "DEEPSEEK_FAILED" in phases
    assert "deepseek-http-secret" not in json.dumps(progress, ensure_ascii=False)


@respx.mock
def test_deepseek_non_json_http_body_is_protocol_error(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-protocol-secret")
    seed_project(db_session, "DEEPSEEK")
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(200, text="<html>bad gateway</html>")
    )

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    data = response.json()["data"]
    assert data["status"] == "FAILED"
    result = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-result").json()["data"]
    assert "protocol_error" in result["errorMessage"]
    progress = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-progress").json()["data"]
    phases = [event["phase"] for event in progress]
    assert "HTTP_RESPONSE_HEADERS" in phases
    assert "HTTP_RESPONSE_BODY_PREVIEW" in phases
    assert "OUTPUT_EXTRACTED" not in phases


@respx.mock
def test_deepseek_invalid_model_output_has_json_parse_failed_phase(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-parse-secret")
    seed_project(db_session, "DEEPSEEK")
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": "not-json"}}]})
    )

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    data = response.json()["data"]
    assert data["status"] == "FAILED"
    result = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-result").json()["data"]
    assert "parse_error" in result["errorMessage"]
    progress = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-progress").json()["data"]
    phases = [event["phase"] for event in progress]
    assert "OUTPUT_EXTRACTED" in phases
    assert "JSON_PARSE_START" in phases
    assert "JSON_PARSE_FAILED" in phases


@respx.mock
def test_deepseek_timeout_saves_failed_result(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-timeout-secret")
    seed_project(db_session, "DEEPSEEK")
    respx.post("https://api.deepseek.com/chat/completions").mock(
        side_effect=httpx.ReadTimeout("timed out")
    )

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    data = response.json()["data"]
    assert data["status"] == "FAILED"
    result = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-result").json()["data"]
    assert result["status"] == "FAILED"
    assert "read_timeout" in result["errorMessage"]
    assert "1000 seconds" in result["errorMessage"]
    progress = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-progress").json()["data"]
    phases = [event["phase"] for event in progress]
    assert "HTTP_REQUEST_START" in phases
    assert "DEEPSEEK_FAILED" in phases
    assert "FINISHED" in phases


@respx.mock
def test_openai_http_failure_has_standard_diagnostics(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-http-secret")
    seed_project(db_session, "OPENAI")
    respx.post("https://api.openai.com/v1/responses").mock(
        return_value=Response(500, json={"error": {"message": "upstream unavailable"}})
    )

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    data = response.json()["data"]
    assert data["provider"] == "OPENAI"
    assert data["status"] == "FAILED"
    progress = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-progress").json()["data"]
    phases = [event["phase"] for event in progress]
    assert "PROVIDER_SELECTED" in phases
    assert "REQUEST_VALIDATED" in phases
    assert "HTTP_REQUEST_START" in phases
    assert "HTTP_RESPONSE_HEADERS" in phases
    assert "OPENAI_FAILED" in phases
    assert "openai-http-secret" not in json.dumps(progress, ensure_ascii=False)


@respx.mock
def test_mr_auto_review_sends_combined_review_summary(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "auto-secret")
    legacy_mr_switch = client.put(
        "/api/code-quality-review-profiles/backend-default-ai-review",
        json={"triggerOnMr": False},
    )
    assert legacy_mr_switch.status_code == 200
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": review_card_json()}}]})
    )

    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {
                "id": 1001,
                "name": "demo-service",
                "web_url": "https://gitlab.example.com/demo/service",
            },
            "object_attributes": {
                "iid": 14,
                "action": "open",
                "source_branch": "feature/auto-ai",
                "target_branch": "main",
            },
            "changedFiles": [
                {
                    "path": "src/main/resources/mapper/OrderMapper.xml",
                    "diffText": "+ update orders set status = #{status} where id = #{id}",
                }
            ],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    )

    assert created.status_code == 200
    task_id = created.json()["data"]["taskId"]
    result = client.get(f"/api/review-tasks/{task_id}/code-quality-result").json()["data"]
    assert result["status"] == "SUCCESS"
    notifications = client.get(f"/api/review-tasks/{task_id}/notifications").json()["data"]
    assert len(notifications) == 1
    assert "变更审查结果" in notifications[0]["requestDigest"]
    assert "代码质量 Review" in notifications[0]["requestDigest"]
    assert "auto-secret" not in json.dumps(notifications, ensure_ascii=False)


@respx.mock
def test_openai_and_anthropic_provider_mocks(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    seed_project(db_session, "OPENAI")
    respx.post("https://api.openai.com/v1/responses").mock(
        return_value=Response(200, json={"output_text": review_card_json("OpenAI 完成")})
    )

    openai = client.post("/api/code-quality-reviews/manual", json=manual_request())

    assert openai.status_code == 200
    assert openai.json()["data"]["provider"] == "OPENAI"

    project = db_session.get(Project, 1)
    project.default_code_quality_provider_code = "ANTHROPIC"
    db_session.commit()
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(
            200,
            json={"content": [{"type": "text", "text": review_card_json("Anthropic 完成")}]},
        )
    )

    anthropic = client.post("/api/code-quality-reviews/manual", json=manual_request())

    assert anthropic.status_code == 200
    assert anthropic.json()["data"]["provider"] == "ANTHROPIC"


@respx.mock
def test_anthropic_provider_uses_non_stream_request(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-secret")
    seed_project(db_session, "ANTHROPIC")
    respx.post("https://api.anthropic.com/v1/messages").mock(
        return_value=Response(
            200,
            json={"content": [{"type": "text", "text": review_card_json("Anthropic 非流式完成")}]},
        )
    )

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    data = response.json()["data"]
    assert data["status"] == "SUCCESS"
    result = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-result").json()["data"]
    assert result["summary"] == "Anthropic 非流式完成"
    progress = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-progress").json()["data"]
    phases = [event["phase"] for event in progress]
    assert "STREAM_START" not in phases
    assert "ANTHROPIC_PARSE_RESULT" in phases
    assert "anthropic-secret" not in json.dumps(progress, ensure_ascii=False)


@respx.mock
def test_retry_gitlab_mr_ai_review_uses_saved_changed_files(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "false")
    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {
                "id": 1001,
                "name": "demo-service",
                "web_url": "https://gitlab.example.com/demo/service",
            },
            "object_attributes": {
                "iid": 12,
                "action": "open",
                "source_branch": "feature/ai",
                "target_branch": "main",
            },
            "changedFiles": [
                {
                    "path": "src/OrderService.java",
                    "diffText": "+ order.setStatus(null);",
                }
            ],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    ).json()["data"]
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_RETRY_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "retry-secret")
    enabled = client.put("/api/code-quality-reviews/settings", json={"reviewEnabled": True})
    assert enabled.status_code == 200
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": review_card_json()}}]})
    )

    retry = client.post(f"/api/code-quality-reviews/tasks/{created['taskId']}/retry")

    assert retry.status_code == 200
    assert retry.json()["data"]["status"] == "SUCCESS"
    result = client.get(f"/api/review-tasks/{created['taskId']}/code-quality-result").json()["data"]
    assert result["findingCount"] == 1


@respx.mock
def test_retry_failure_marks_existing_success_task_failed(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "false")
    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {
                "id": 1001,
                "name": "demo-service",
                "web_url": "https://gitlab.example.com/demo/service",
            },
            "object_attributes": {
                "iid": 16,
                "action": "open",
                "source_branch": "feature/retry-failure",
                "target_branch": "main",
            },
            "changedFiles": [
                {
                    "path": "src/OrderService.java",
                    "diffText": "+ order.setStatus(null);",
                }
            ],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    ).json()["data"]
    task_id = created["taskId"]
    assert client.get(f"/api/review-tasks/{task_id}").json()["data"]["status"] == "SUCCESS"

    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_RETRY_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "retry-failure-secret")
    enabled = client.put("/api/code-quality-reviews/settings", json={"reviewEnabled": True})
    assert enabled.status_code == 200
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(500, json={"error": {"message": "upstream unavailable"}})
    )

    retry = client.post(f"/api/code-quality-reviews/tasks/{task_id}/retry")

    assert retry.status_code == 200
    assert retry.json()["data"]["status"] == "FAILED"
    result = client.get(f"/api/review-tasks/{task_id}/code-quality-result").json()["data"]
    assert result["status"] == "FAILED"
    detail = client.get(f"/api/review-tasks/{task_id}").json()["data"]
    assert detail["status"] == "FAILED"
    assert "http_status_error" in detail["errorMessage"]


def test_retry_returns_running_without_waiting_for_provider(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    from app.code_quality import service

    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "false")
    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {
                "id": 1001,
                "name": "demo-service",
                "web_url": "https://gitlab.example.com/demo/service",
            },
            "object_attributes": {
                "iid": 13,
                "action": "open",
                "source_branch": "feature/async-ai",
                "target_branch": "main",
            },
            "changedFiles": [
                {
                    "path": "src/OrderService.java",
                    "diffText": "+ order.setStatus(null);",
                }
            ],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    ).json()["data"]
    submitted: list[int] = []
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.delenv("CODE_QUALITY_RETRY_INLINE", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "retry-secret")
    monkeypatch.setattr(service._executor, "submit", lambda _fn, task_id: submitted.append(task_id))
    enabled = client.put("/api/code-quality-reviews/settings", json={"reviewEnabled": True})
    assert enabled.status_code == 200

    retry = client.post(f"/api/code-quality-reviews/tasks/{created['taskId']}/retry")

    assert retry.status_code == 200
    assert retry.json()["data"]["status"] == "RUNNING"
    assert submitted == [created["taskId"]]
    result = client.get(f"/api/review-tasks/{created['taskId']}/code-quality-result").json()["data"]
    assert result["status"] == "RUNNING"


def test_manual_review_returns_running_without_waiting_for_provider(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    from app.code_quality import service

    seed_project(db_session, "DEEPSEEK")
    submitted: list[dict] = []
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.delenv("CODE_QUALITY_REVIEW_INLINE", raising=False)
    monkeypatch.delenv("CODE_QUALITY_RETRY_INLINE", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "manual-secret")
    monkeypatch.setattr(
        service._executor,
        "submit",
        lambda fn, *args, **kwargs: submitted.append({"fn": fn.__name__, "args": args, "kwargs": kwargs}),
    )

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "RUNNING"
    assert data["provider"] == "DEEPSEEK"
    assert submitted
    assert submitted[0]["kwargs"]["priority"] == service.REVIEW_JOB_PRIORITY
    assert service.REVIEW_JOB_PRIORITY < service.FIX_PREVIEW_JOB_PRIORITY
    assert service._executor.max_workers == 10
    result = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-result").json()["data"]
    assert result["status"] == "RUNNING"
    progress = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-progress").json()["data"]
    assert progress[0]["phase"] == "QUEUED"


def enable_push_profile(client: TestClient) -> None:
    update_default_push_policy(
        client,
        aiReviewEnabled=True,
        triggerOnPush=True,
        triggerOnlyWhenRiskMatched=False,
        pushBranchPatterns=["feature/*", "bugfix/*", "hotfix/*"],
    )


def update_default_push_policy(client: TestClient, **overrides) -> dict:
    groups_response = client.get("/api/project-groups")
    assert groups_response.status_code == 200
    default_group = next(item for item in groups_response.json()["data"]["items"] if item["groupCode"] == "default")
    payload = {
        "pushBranchPatterns": default_group["pushBranchPatterns"],
        "pushMinChangedFiles": default_group["pushMinChangedFiles"],
        "pushMinDiffBytes": default_group["pushMinDiffBytes"],
        "pushMinCommitCount": default_group["pushMinCommitCount"],
        "pushMaxChangedFiles": default_group["pushMaxChangedFiles"],
        "pushMaxDiffBytes": default_group["pushMaxDiffBytes"],
        "pushDebounceSeconds": default_group["pushDebounceSeconds"],
        "aiReviewEnabled": default_group["aiReviewEnabled"],
        "triggerOnManual": default_group["triggerOnManual"],
        "triggerOnMr": default_group["triggerOnMr"],
        "triggerOnPush": default_group["triggerOnPush"],
        "triggerOnlyWhenRiskMatched": default_group["triggerOnlyWhenRiskMatched"],
        "autoFixPreviewEnabled": default_group["autoFixPreviewEnabled"],
        "autoFixPreviewSeverities": default_group["autoFixPreviewSeverities"],
        **overrides,
    }
    response = client.put(f"/api/project-groups/{default_group['id']}", json=payload)
    assert response.status_code == 200
    return response.json()["data"]


def test_push_gate_returns_stable_empty_response_for_non_evaluated_task(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "false")
    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json={
            "object_kind": "merge_request",
            "project": {"id": 1001, "name": "demo-service"},
            "object_attributes": {"iid": 15, "action": "open", "source_branch": "feature/a", "target_branch": "main"},
            "changedFiles": [{"path": "src/OrderService.java", "diffText": "+ public void touch() {}"}],
        },
        headers={"X-Gitlab-Event": "Merge Request Hook"},
    ).json()["data"]

    response = client.get(f"/api/review-tasks/{created['taskId']}/code-quality-gate")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["decision"] == "NOT_EVALUATED"
    assert data["aiReviewScheduled"] is False


def test_push_gate_rejects_small_push_as_not_significant(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    enable_push_profile(client)

    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=push_payload(changed_files=[{"path": "src/OrderService.java", "diffText": "+ typo"}]),
        headers={"X-Gitlab-Event": "Push Hook"},
    ).json()["data"]
    gate = client.get(f"/api/review-tasks/{created['taskId']}/code-quality-gate").json()["data"]

    assert gate["decision"] == "REJECTED"
    assert gate["reasonCode"] == "NOT_SIGNIFICANT"
    assert gate["aiReviewScheduled"] is False
    assert gate["metrics"]["changedFileCount"] == 1
    result = client.get(f"/api/review-tasks/{created['taskId']}/code-quality-result")
    assert result.status_code == 200
    assert result.json()["data"] is None


@respx.mock
def test_push_gate_allows_risk_matched_push_and_runs_ai_review(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "push-risk-secret")
    enable_push_profile(client)
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": review_card_json("Push AI Review 完成")}}]})
    )

    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=push_payload(
            branch="feature/push-risk",
            changed_files=[
                {
                    "path": "src/main/resources/mapper/OrderMapper.xml",
                    "diffText": "+ update orders set status = #{status} where id = #{id}",
                }
            ],
        ),
        headers={"X-Gitlab-Event": "Push Hook"},
    ).json()["data"]
    gate = client.get(f"/api/review-tasks/{created['taskId']}/code-quality-gate").json()["data"]
    result = client.get(f"/api/review-tasks/{created['taskId']}/code-quality-result").json()["data"]

    assert gate["decision"] == "ALLOWED"
    assert gate["reasonCode"] == "RISK_MATCHED"
    assert gate["aiReviewScheduled"] is True
    assert gate["metrics"]["focusRiskItemCount"] == 1
    assert result["status"] == "SUCCESS"
    assert "push-risk-secret" not in json.dumps(gate, ensure_ascii=False)


@respx.mock
def test_push_gate_allows_large_push_without_risk_match(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "push-large-secret")
    enable_push_profile(client)
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": review_card_json("Large Push 完成")}}]})
    )
    files = [
        {"path": f"src/Change{index}.java", "diffText": "+ documentation update"}
        for index in range(10)
    ]

    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=push_payload(branch="feature/large-push", changed_files=files),
        headers={"X-Gitlab-Event": "Push Hook"},
    ).json()["data"]
    gate = client.get(f"/api/review-tasks/{created['taskId']}/code-quality-gate").json()["data"]

    assert gate["decision"] == "ALLOWED"
    assert gate["reasonCode"] == "LARGE_CHANGE"
    assert gate["metrics"]["changedFileCount"] == 10


@respx.mock
def test_push_gate_ignores_legacy_risk_only_switch_when_large_change_matches(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.setenv("CODE_QUALITY_REVIEW_INLINE", "true")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "push-risk-only-legacy-secret")
    update_default_push_policy(
        client,
        aiReviewEnabled=True,
        triggerOnPush=True,
        triggerOnlyWhenRiskMatched=True,
        pushBranchPatterns=["feature/*"],
        pushMinChangedFiles=1,
        pushMinDiffBytes=1,
        pushMinCommitCount=1,
    )
    respx.post("https://api.deepseek.com/chat/completions").mock(
        return_value=Response(200, json={"choices": [{"message": {"content": review_card_json("Large Push 完成")}}]})
    )

    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=push_payload(
            branch="feature/risk-required",
            changed_files=[{"path": "src/Readme.java", "diffText": "+ documentation update"}],
        ),
        headers={"X-Gitlab-Event": "Push Hook"},
    ).json()["data"]
    gate = client.get(f"/api/review-tasks/{created['taskId']}/code-quality-gate").json()["data"]

    assert gate["decision"] == "ALLOWED"
    assert gate["reasonCode"] == "LARGE_CHANGE"
    assert gate["metrics"]["riskLevel"] == "LOW"
    assert gate["metrics"]["focusRiskItemCount"] == 0
    assert any(rule["code"] == "largeChange" and rule["matched"] for rule in gate["matchedRules"])


def test_push_gate_rejects_branch_no_diff_and_too_large(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    enable_push_profile(client)

    main_response = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=push_payload(branch="main"),
        headers={"X-Gitlab-Event": "Push Hook"},
    ).json()["data"]
    no_diff_task = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=push_payload(branch="feature/no-diff", changed_files=[{"path": "src/OrderService.java"}]),
        headers={"X-Gitlab-Event": "Push Hook"},
    ).json()["data"]["taskId"]
    update_default_push_policy(client, pushMaxDiffBytes=3)
    too_large_task = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=push_payload(branch="feature/too-large", changed_files=[{"path": "docs/a.md", "diffText": "+ too large"}]),
        headers={"X-Gitlab-Event": "Push Hook"},
    ).json()["data"]["taskId"]

    assert main_response["status"] == "SKIPPED"
    assert main_response["taskId"] is None
    assert main_response["reasonCode"] == "PUSH_BRANCH_NOT_ALLOWED"
    assert client.get(f"/api/review-tasks/{no_diff_task}/code-quality-gate").json()["data"]["reasonCode"] == "NO_DIFF_TEXT"
    assert client.get(f"/api/review-tasks/{too_large_task}/code-quality-gate").json()["data"]["reasonCode"] == "DIFF_TOO_LARGE"


def test_push_branch_filter_uses_project_group_policy(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    enable_push_profile(client)
    update_default_push_policy(client, pushBranchPatterns=["release/*"])

    skipped = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=push_payload(branch="feature/group-policy", changed_files=[{"path": "docs/a.md", "diffText": "+ update"}]),
        headers={"X-Gitlab-Event": "Push Hook"},
    ).json()["data"]
    created = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=push_payload(branch="release/1.0", changed_files=[{"path": "docs/a.md", "diffText": "+ update"}]),
        headers={"X-Gitlab-Event": "Push Hook"},
    ).json()["data"]

    assert skipped["status"] == "SKIPPED"
    assert skipped["reasonCode"] == "PUSH_BRANCH_NOT_ALLOWED"
    assert skipped["pushBranchPatterns"] == ["release/*"]
    assert created["taskId"] is not None


def test_push_gate_debounces_recent_allowed_push(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    from app.code_quality import service

    seed_template(db_session)
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.delenv("CODE_QUALITY_REVIEW_INLINE", raising=False)
    monkeypatch.setattr(service._executor, "submit", lambda *args: None)
    enable_push_profile(client)
    files = [{"path": f"src/Change{index}.java", "diffText": "+ documentation update"} for index in range(10)]

    first = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=push_payload(branch="feature/debounce", changed_files=files),
        headers={"X-Gitlab-Event": "Push Hook"},
    ).json()["data"]["taskId"]
    second = client.post(
        "/api/webhooks/gitlab/merge-request",
        json=push_payload(branch="feature/debounce", changed_files=files),
        headers={"X-Gitlab-Event": "Push Hook"},
    ).json()["data"]["taskId"]

    first_gate = client.get(f"/api/review-tasks/{first}/code-quality-gate").json()["data"]
    second_gate = client.get(f"/api/review-tasks/{second}/code-quality-gate").json()["data"]
    assert first_gate["decision"] == "ALLOWED"
    assert second_gate["decision"] == "REJECTED"
    assert second_gate["reasonCode"] == "DEBOUNCED"
