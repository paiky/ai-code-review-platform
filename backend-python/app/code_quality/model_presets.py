from __future__ import annotations

from app.agent_review.runtime import CUSTOM_DEFAULT_MODEL, DEFAULT_MODEL
from app.code_quality.schemas import ReviewModelPreset
from app.core.config import get_settings


REASONING_EFFORTS = ["low", "medium", "high"]


def list_review_model_presets(review_type: str) -> list[dict]:
    settings = get_settings()
    normalized_type = review_type.strip().upper()
    if normalized_type == "AGENT":
        presets = [
            _preset(
                "AGENT_CLAUDE_CODE_DEEPSEEK",
                "AGENT",
                "DEEPSEEK",
                "Claude Code + DeepSeek",
                [
                    _variant(
                        "ANTHROPIC_COMPATIBLE",
                        "https://api.deepseek.com/anthropic",
                        DEFAULT_MODEL,
                        reasoning_efforts=REASONING_EFFORTS,
                        default_reasoning_effort="high",
                    )
                ],
            ),
            _preset(
                "AGENT_OPENAI",
                "AGENT",
                "OPENAI",
                "OpenAI",
                [
                    _variant(
                        "OPENAI_RESPONSES",
                        _remove_endpoint_suffix(
                            settings.openai_responses_url,
                            "/responses",
                        ),
                        CUSTOM_DEFAULT_MODEL,
                        reasoning_efforts=REASONING_EFFORTS,
                        default_reasoning_effort="high",
                    ),
                    _variant(
                        "OPENAI_CHAT_COMPLETIONS",
                        _remove_endpoint_suffix(
                            settings.openai_responses_url,
                            "/responses",
                        ),
                        CUSTOM_DEFAULT_MODEL,
                    ),
                ],
            ),
            _preset(
                "AGENT_ANTHROPIC",
                "AGENT",
                "ANTHROPIC",
                "Anthropic / Claude",
                [
                    _variant(
                        "ANTHROPIC_MESSAGES",
                        _remove_endpoint_suffix(
                            settings.anthropic_messages_url,
                            "/messages",
                        ),
                        settings.anthropic_code_review_model,
                    )
                ],
            ),
            _preset("AGENT_CUSTOM", "AGENT", "CUSTOM", "自定义", [], custom=True),
        ]
    else:
        presets = [
            _preset(
                "STANDARD_OPENAI",
                "STANDARD",
                "OPENAI",
                "OpenAI",
                [
                    _variant(
                        "OPENAI_RESPONSES",
                        settings.openai_responses_url,
                        settings.openai_code_review_model,
                        reasoning_efforts=REASONING_EFFORTS,
                        default_reasoning_effort="high",
                    )
                ],
            ),
            _preset(
                "STANDARD_ANTHROPIC",
                "STANDARD",
                "ANTHROPIC",
                "Anthropic / Claude",
                [
                    _variant(
                        "ANTHROPIC_MESSAGES",
                        settings.anthropic_messages_url,
                        settings.anthropic_code_review_model,
                    )
                ],
            ),
            _preset(
                "STANDARD_DEEPSEEK",
                "STANDARD",
                "DEEPSEEK",
                "DeepSeek",
                [
                    _variant(
                        "OPENAI_CHAT_COMPATIBLE",
                        settings.deepseek_base_url,
                        settings.deepseek_code_review_model,
                    )
                ],
            ),
            _preset(
                "STANDARD_XIAOMIMO",
                "STANDARD",
                "XIAOMIMO",
                "XiaoMIMO / Xiaomi MiMo",
                [
                    _variant(
                        "OPENAI_CHAT_COMPATIBLE",
                        settings.xiaomimo_base_url,
                        settings.xiaomimo_code_review_model,
                    )
                ],
            ),
            _preset(
                "STANDARD_GLM",
                "STANDARD",
                "GLM",
                "智谱 GLM",
                [
                    _variant(
                        "OPENAI_CHAT_COMPATIBLE",
                        settings.glm_base_url,
                        settings.glm_code_review_model,
                    )
                ],
            ),
            _preset("STANDARD_CUSTOM", "STANDARD", "CUSTOM", "自定义", [], custom=True),
        ]
    return [
        ReviewModelPreset.model_validate(item).model_dump(by_alias=True)
        for item in presets
    ]


def _preset(
    preset_code: str,
    review_type: str,
    vendor_code: str,
    vendor_name: str,
    variants: list[dict],
    *,
    custom: bool = False,
) -> dict:
    return {
        "presetCode": preset_code,
        "reviewType": review_type,
        "vendorCode": vendor_code,
        "vendorName": vendor_name,
        "custom": custom,
        "variants": variants,
    }


def _variant(
    protocol: str,
    base_url: str,
    default_model: str,
    *,
    reasoning_efforts: list[str] | None = None,
    default_reasoning_effort: str | None = None,
) -> dict:
    return {
        "protocol": protocol,
        "baseUrl": base_url,
        "models": [default_model],
        "defaultModel": default_model,
        "reasoningEfforts": reasoning_efforts or [],
        "defaultReasoningEffort": default_reasoning_effort,
    }


def _remove_endpoint_suffix(value: str, suffix: str) -> str:
    normalized = value.rstrip("/")
    if normalized.endswith(suffix):
        return normalized[: -len(suffix)]
    return normalized
