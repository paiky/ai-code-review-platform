from datetime import datetime
import json

import httpx
import respx
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.project_integration.models import Project
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
    db_session.add(
        RuleTemplate(
            template_code="backend-default",
            template_name="后端默认审查模板",
            target_type="BACKEND",
            version=1,
            enabled_rule_codes=json.dumps(["DB_SQL_CHANGE_CHECK"]),
            config_json=json.dumps({"focusChangeTypes": ["DB_SQL"], "recommendedChecks": []}),
            status="ENABLED",
            description="stage4",
            created_at=now,
            updated_at=now,
        )
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


def review_card_json(summary: str = "发现一个问题") -> str:
    return json.dumps(
        {
            "summary": summary,
            "overallLevel": "HIGH",
            "findings": [
                {
                    "severity": "MAJOR",
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
        json={"apiKey": "sk-test-secret-123456", "modelName": "gpt-test"},
    )

    assert response.status_code == 200
    openai = next(item for item in response.json()["data"] if item["providerCode"] == "OPENAI")
    assert openai["apiKeyConfigured"] is True
    assert openai["apiKeyMasked"] == "sk-t...3456"
    assert "sk-test-secret-123456" not in json.dumps(response.json(), ensure_ascii=False)


def test_provider_list_exposes_basic_provider_config(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")

    response = client.get("/api/code-quality-review-providers")

    assert response.status_code == 200
    providers = {item["providerCode"]: item for item in response.json()["data"]}
    assert set(providers) == {"OPENAI", "ANTHROPIC", "DEEPSEEK", "CUSTOM"}
    assert providers["OPENAI"]["providerType"] == "OPENAI_RESPONSES"
    assert providers["DEEPSEEK"]["providerType"] == "OPENAI_CHAT_COMPATIBLE"
    assert "capabilities" not in providers["OPENAI"]
    assert "streamingConfig" not in providers["OPENAI"]


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
        "CUSTOM",
    }
    inspector = inspect(db_session.get_bind())
    setting_columns = {column["name"] for column in inspector.get_columns("code_quality_review_settings")}
    profile_columns = {column["name"] for column in inspector.get_columns("code_quality_review_profiles")}
    assert "review_enabled" in setting_columns
    assert "default_provider_code" in setting_columns
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


def test_settings_returns_empty_dingtalk_webhook_list(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")

    response = client.get("/api/code-quality-reviews/settings")

    assert response.status_code == 200
    assert response.json()["data"]["reviewEnabled"] is True
    assert response.json()["data"]["dingtalkWebhooks"] == []


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
def test_settings_sends_test_notification_for_new_webhook(
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
    assert route.called
    test_results = saved.json()["data"]["webhookTestResults"]
    assert len(test_results) == 1
    assert test_results[0]["status"] == "SUCCESS"


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
def test_settings_sends_test_notification_when_reenabling_existing_webhook(
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
    assert route.called
    assert updated.json()["data"]["webhookTestResults"][0]["status"] == "SUCCESS"


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
    assert "DEEPSEEK_REQUEST_DEBUG" in phases
    assert "DEEPSEEK_RESPONSE_RAW" in phases
    assert "DEEPSEEK_PARSE_RESULT" in phases
    assert "deepseek-secret" not in json.dumps(progress, ensure_ascii=False)


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
                    "diffText": "+ select id, status from orders where id = #{id}",
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
    submitted: list[tuple] = []
    monkeypatch.setenv("CODE_QUALITY_REVIEW_ENABLED", "true")
    monkeypatch.delenv("CODE_QUALITY_REVIEW_INLINE", raising=False)
    monkeypatch.delenv("CODE_QUALITY_RETRY_INLINE", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "manual-secret")
    monkeypatch.setattr(service._executor, "submit", lambda *args: submitted.append(args))

    response = client.post("/api/code-quality-reviews/manual", json=manual_request())

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "RUNNING"
    assert data["provider"] == "DEEPSEEK"
    assert submitted
    result = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-result").json()["data"]
    assert result["status"] == "RUNNING"
    progress = client.get(f"/api/review-tasks/{data['taskId']}/code-quality-progress").json()["data"]
    assert progress[0]["phase"] == "QUEUED"


def enable_push_profile(client: TestClient) -> None:
    response = client.put(
        "/api/code-quality-review-profiles/backend-default-ai-review",
        json={
            "triggerOnPush": True,
            "triggerOnlyWhenRiskMatched": False,
            "pushBranchPatterns": ["feature/*", "bugfix/*", "hotfix/*"],
            "pushMinChangedFiles": 10,
            "pushMinDiffBytes": 30000,
            "pushMinCommitCount": 3,
            "pushMaxChangedFiles": 80,
            "pushMaxDiffBytes": 300000,
            "pushDebounceSeconds": 300,
        },
    )
    assert response.status_code == 200


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
        json=push_payload(changed_files=[{"path": "docs/readme.md", "diffText": "+ typo"}]),
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
                    "diffText": "+ select id, status from orders where id = #{id}",
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
        {"path": f"docs/change-{index}.md", "diffText": "+ documentation update"}
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
    client.put(
        "/api/code-quality-review-profiles/backend-default-ai-review",
        json={"pushMaxDiffBytes": 3},
    )
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
    files = [{"path": f"docs/change-{index}.md", "diffText": "+ documentation update"} for index in range(10)]

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
