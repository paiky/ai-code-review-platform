from app.code_quality import prompt
from app.code_quality.providers import _normalize_finding
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
    assert '"contextStatus": "SUFFICIENT|PARTIAL|INSUFFICIENT"' in system
    assert "上下文不足时不要武断输出高风险或紧急" in system
    assert "Context Planner 只提示本次可能缺少的证据" in system
    assert "本地引用证据只表示" in system
    assert "字段引用 snippets 也只是有限证据" in system
    assert "关键字段引用" in system
    assert "notInjectedEvidence / BUDGET_CUT" in system
    assert "DTO_FIELD_CHANGED、FIELD_DELETED、METHOD_SIGNATURE_CHANGED、METHOD_DELETED" in system
    assert "不能输出 HIGH confidence" in system


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


def test_json_schema_requires_context_status_fields() -> None:
    schema = prompt.json_schema_format()["schema"]
    finding_schema = schema["properties"]["findings"]["items"]

    assert "contextStatus" in finding_schema["required"]
    assert "evidence" in finding_schema["required"]
    assert "missingContext" in finding_schema["required"]
    assert "contextSummary" in finding_schema["required"]
    assert finding_schema["properties"]["contextStatus"]["enum"] == [
        "SUFFICIENT",
        "PARTIAL",
        "INSUFFICIENT",
    ]


def test_normalize_finding_keeps_context_aware_fields() -> None:
    finding = _normalize_finding(
        {
            "severity": "major",
            "category": "correctness",
            "filePath": "src/OrderService.java",
            "startLine": 12,
            "endLine": 12,
            "title": "删除方法需要确认",
            "body": "当前只看到 diff 删除动作。",
            "suggestion": "补充引用搜索后再判断。",
            "confidence": "low",
            "contextStatus": "insufficient",
            "evidence": ["diff 删除了 cancelOrder 方法"],
            "missingContext": ["REFERENCE_SEARCH", {"type": "SAME_CLASS_METHODS"}],
            "contextSummary": "仅基于 diff，缺少引用关系。",
        },
        "DEEPSEEK",
        "HIGH",
    )

    assert finding["contextStatus"] == "INSUFFICIENT"
    assert finding["confidence"] == "LOW"
    assert finding["evidence"] == ["diff 删除了 cancelOrder 方法"]
    assert finding["missingContext"] == ["REFERENCE_SEARCH", "SAME_CLASS_METHODS"]
    assert finding["contextSummary"] == "仅基于 diff，缺少引用关系。"


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
