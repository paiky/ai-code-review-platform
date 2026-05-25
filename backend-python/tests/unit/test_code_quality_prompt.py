from app.code_quality import prompt
from app.code_quality.repository import APP_ANDROID_REVIEW_INSTRUCTIONS, DEFAULT_REVIEW_INSTRUCTIONS
from app.code_quality.service import _build_review_request


class _Profile:
    def __init__(self, instructions: str | None, model: str | None = None) -> None:
        self.review_instructions = instructions
        self.model = model


def _system_message(body: dict) -> str:
    return body["messages"][0]["content"]


def test_chat_prompt_uses_android_profile_as_review_role() -> None:
    body = prompt.openai_chat_compatible_request(
        "deepseek-test",
        {
            "mode": "DIFF_TEXT",
            "instructions": APP_ANDROID_REVIEW_INSTRUCTIONS,
            "diffText": "+ fun render() {}",
            "changedFiles": ["app/src/main/java/MainActivity.kt"],
        },
    )

    system = _system_message(body)

    assert system.startswith(APP_ANDROID_REVIEW_INSTRUCTIONS)
    assert "资深 Android 代码质量审核助手" in system
    assert "资深后端代码质量审核助手" not in system
    assert "平台统一输出协议" in system
    assert '"overallLevel": "LOW|MEDIUM|HIGH|CRITICAL"' in system


def test_chat_prompt_keeps_backend_role_when_profile_is_backend() -> None:
    body = prompt.openai_chat_compatible_request(
        "deepseek-test",
        {
            "mode": "DIFF_TEXT",
            "instructions": DEFAULT_REVIEW_INSTRUCTIONS,
            "diffText": "+ order.setStatus(null);",
            "changedFiles": ["src/main/java/OrderService.java"],
        },
    )

    system = _system_message(body)

    assert system.startswith(DEFAULT_REVIEW_INSTRUCTIONS)
    assert "资深后端代码质量审核助手" in system
    assert "平台统一输出协议" in system


def test_chat_prompt_without_profile_still_contains_json_contract() -> None:
    body = prompt.openai_chat_compatible_request(
        "deepseek-test",
        {
            "mode": "DIFF_TEXT",
            "diffText": "+ fun render() {}",
            "changedFiles": ["app/src/main/java/MainActivity.kt"],
        },
    )

    system = _system_message(body)

    assert system.startswith("平台统一输出协议")
    assert "必须返回这个 JSON 结构" in system
    assert "资深后端代码质量审核助手" not in system


def test_build_review_request_reads_android_profile_instructions() -> None:
    request = _build_review_request(
        _Profile(APP_ANDROID_REVIEW_INSTRUCTIONS),
        {
            "mode": "DIFF_TEXT",
            "diffText": "+ fun render() {}",
            "changedFiles": ["app/src/main/java/MainActivity.kt"],
        },
    )

    assert request["instructions"] == APP_ANDROID_REVIEW_INSTRUCTIONS
    assert "资深 Android 代码质量审核助手" in request["instructions"]
    assert "资深后端代码质量审核助手" not in request["instructions"]
