import json

from fastapi.testclient import TestClient


def test_standard_model_presets_expose_backend_defaults_without_keys(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setenv("OPENAI_RESPONSES_URL", "https://gateway.example.com/v1/responses")
    monkeypatch.setenv("OPENAI_CODE_REVIEW_MODEL", "gpt-company")

    response = client.get(
        "/api/review-model-presets",
        params={"reviewType": "STANDARD"},
    )

    assert response.status_code == 200
    presets = response.json()["data"]
    assert [item["vendorCode"] for item in presets] == [
        "OPENAI",
        "ANTHROPIC",
        "DEEPSEEK",
        "XIAOMIMO",
        "GLM",
        "CUSTOM",
    ]
    openai = presets[0]
    assert openai == {
        "presetCode": "STANDARD_OPENAI",
        "reviewType": "STANDARD",
        "vendorCode": "OPENAI",
        "vendorName": "OpenAI",
        "custom": False,
        "variants": [
            {
                "protocol": "OPENAI_RESPONSES",
                "baseUrl": "https://gateway.example.com/v1/responses",
                "models": ["gpt-company"],
                "defaultModel": "gpt-company",
                "reasoningEfforts": ["low", "medium", "high"],
                "defaultReasoningEffort": "high",
            }
        ],
    }
    assert presets[-1]["custom"] is True
    assert presets[-1]["variants"] == []
    serialized = json.dumps(response.json(), ensure_ascii=False).casefold()
    assert "apikey" not in serialized
    assert "secret" not in serialized


def test_agent_model_presets_include_production_runner_variants(
    client: TestClient,
) -> None:
    response = client.get(
        "/api/review-model-presets",
        params={"reviewType": "AGENT"},
    )

    assert response.status_code == 200
    presets = response.json()["data"]
    assert [item["presetCode"] for item in presets] == [
        "AGENT_CLAUDE_CODE_DEEPSEEK",
        "AGENT_OPENAI",
        "AGENT_ANTHROPIC",
        "AGENT_CUSTOM",
    ]
    deepseek = presets[0]["variants"][0]
    assert deepseek["protocol"] == "ANTHROPIC_COMPATIBLE"
    assert deepseek["baseUrl"] == "https://api.deepseek.com/anthropic"
    assert deepseek["defaultModel"] == "deepseek-v4-pro[1m]"

    openai_variants = presets[1]["variants"]
    assert [item["protocol"] for item in openai_variants] == [
        "OPENAI_RESPONSES",
        "OPENAI_CHAT_COMPLETIONS",
    ]
    assert openai_variants[0]["baseUrl"] == "https://api.openai.com/v1/responses"
    assert openai_variants[1]["baseUrl"] == "https://api.openai.com/v1/chat/completions"
    assert presets[2]["variants"][0]["protocol"] == "ANTHROPIC_MESSAGES"


def test_model_presets_require_supported_review_type(client: TestClient) -> None:
    missing = client.get("/api/review-model-presets")
    invalid = client.get(
        "/api/review-model-presets",
        params={"reviewType": "OTHER"},
    )

    assert missing.status_code == 400
    assert invalid.status_code == 400
