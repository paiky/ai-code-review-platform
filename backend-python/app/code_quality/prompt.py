from __future__ import annotations

from typing import Any


def render_instructions(request: dict[str, Any]) -> str:
    base = (
        "你是资深后端代码质量审核助手。只审查用户提供的 diff，必须返回严格 JSON，不要 Markdown。\n"
        "JSON 字段名和枚举值保持英文；summary、title、body、suggestion 必须使用简体中文。\n"
        "必须返回这个 JSON 结构："
        '{"summary": string, "overallLevel": "LOW|MEDIUM|HIGH|CRITICAL", '
        '"findings": [{"severity": "MINOR|MAJOR|CRITICAL", '
        '"category": "CODE_QUALITY|CORRECTNESS|SECURITY|TRANSACTION|SQL_PERFORMANCE|CACHE_CONSISTENCY|MQ_CONSISTENCY|EXCEPTION_HANDLING|TEST_GAP", '
        '"filePath": string, "startLine": integer, "endLine": integer, '
        '"title": string, "body": string, "suggestion": string, "confidence": "LOW|MEDIUM|HIGH"}]}。\n'
        "不要使用 type、file_path、line_range、path、line 等替代字段；没有准确行号时使用最接近的 diff 新增或修改行号。\n"
        "只报告本次变更引入的、可执行的代码质量问题，不报告历史存量问题。\n"
        "重点关注正确性、数据一致性、安全、事务边界、SQL 性能、缓存一致性、MQ 一致性、异常处理、可观测性和关键测试缺口。\n"
        "不报告纯代码风格、命名偏好、格式、注释或主观重构建议。\n"
        "不要编造输入中不存在的文件或行号；缺少证据时不要报告，除非潜在影响很高且必须人工确认。\n"
        "你可以参考上下文，但最终只能报告由 changed files 白名单中的 diff 引入的问题。"
    )
    instructions = request.get("instructions")
    if instructions:
        return f"{base}\n\n用户自定义审核规则：\n{instructions}"
    return base


def render_input(request: dict[str, Any]) -> str:
    return (
        f"Review mode: {request.get('mode') or '-'}\n"
        f"Base ref: {request.get('baseRef') or '-'}\n"
        f"Commit sha: {request.get('commitSha') or '-'}\n"
        f"Title: {request.get('title') or '-'}\n"
        f"Changed files: {request.get('changedFiles') or []}\n\n"
        f"Diff:\n{request.get('diffText') or '-'}"
    )


def openai_responses_request(model: str, request: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": model,
        "instructions": render_instructions(request),
        "input": render_input(request),
        "text": {"format": json_schema_format()},
        "store": False,
    }


def anthropic_messages_request(model: str, request: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": 4096,
        "system": render_instructions(request),
        "messages": [{"role": "user", "content": render_input(request)}],
    }


def openai_chat_compatible_request(model: str, request: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": render_instructions(request)},
            {"role": "user", "content": render_input(request)},
        ],
    }


def json_schema_format() -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": "code_quality_review_card",
        "strict": True,
        "schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["summary", "overallLevel", "findings"],
            "properties": {
                "summary": {"type": "string"},
                "overallLevel": {
                    "type": "string",
                    "enum": ["LOW", "MEDIUM", "HIGH", "CRITICAL"],
                },
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "severity",
                            "category",
                            "filePath",
                            "startLine",
                            "endLine",
                            "title",
                            "body",
                            "suggestion",
                            "confidence",
                        ],
                        "properties": {
                            "severity": {
                                "type": "string",
                                "enum": ["MINOR", "MAJOR", "CRITICAL"],
                            },
                            "category": {"type": "string"},
                            "filePath": {"type": "string"},
                            "startLine": {"type": "integer"},
                            "endLine": {"type": "integer"},
                            "title": {"type": "string"},
                            "body": {"type": "string"},
                            "suggestion": {"type": "string"},
                            "confidence": {
                                "type": "string",
                                "enum": ["LOW", "MEDIUM", "HIGH"],
                            },
                        },
                    },
                },
            },
        },
    }
