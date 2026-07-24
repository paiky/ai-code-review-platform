import pytest

from app.agent_review_spike.schema import ReviewSchemaError, validate_review_card


def _finding(**overrides):
    value = {
        "severity": "MAJOR",
        "category": "CUSTOM_PLATFORM_RISK",
        "filePath": "src/service.py",
        "startLine": 10,
        "endLine": 12,
        "title": "事务边界不完整",
        "body": "缓存更新发生在事务提交前。",
        "suggestion": "提交后再更新缓存。",
        "confidence": "HIGH",
        "contextStatus": "SUFFICIENT",
        "evidence": ["diff 第 10 行"],
        "missingContext": [],
        "contextSummary": "已检查调用方和事务实现。",
    }
    value.update(overrides)
    return value


def test_validate_review_card_keeps_existing_shape_and_deduplicates():
    card = validate_review_card(
        {
            "summary": "发现一个问题",
            "overallLevel": "high",
            "findings": [_finding(), _finding()],
        },
        ["src/service.py"],
    )

    assert card["overallLevel"] == "HIGH"
    assert len(card["findings"]) == 1
    assert card["findings"][0]["category"] == "CUSTOM_PLATFORM_RISK"


def test_validate_review_card_forces_low_for_empty_result():
    card = validate_review_card(
        {"summary": "未发现问题", "overallLevel": "CRITICAL", "findings": []},
        ["src/service.py"],
    )

    assert card["overallLevel"] == "LOW"


@pytest.mark.parametrize(
    "finding,error_fragment",
    [
        (_finding(filePath="../secret.py"), "unsafe path"),
        (_finding(filePath="src/other.py"), "outside changedFiles"),
        (_finding(startLine=0), "positive integer"),
        (_finding(startLine=12, endLine=11), ">= startLine"),
        (_finding(confidence="CERTAIN"), "unsupported"),
    ],
)
def test_validate_review_card_rejects_invalid_findings(finding, error_fragment):
    with pytest.raises(ReviewSchemaError, match=error_fragment):
        validate_review_card(
            {"summary": "x", "overallLevel": "HIGH", "findings": [finding]},
            ["src/service.py"],
        )
