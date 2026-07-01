from __future__ import annotations

from typing import Any


def render_instructions(request: dict[str, Any]) -> str:
    protocol = (
        "平台统一输出协议：只审查用户提供的 diff，必须返回严格 JSON，不要 Markdown。\n"
        "JSON 字段名和枚举值保持英文；summary、title、body、suggestion 必须使用简体中文。\n"
        "必须返回这个 JSON 结构："
        '{"summary": string, "overallLevel": "LOW|MEDIUM|HIGH|CRITICAL", '
        '"findings": [{"severity": "MINOR|MAJOR|CRITICAL", '
        '"category": "CODE_QUALITY|CORRECTNESS|SECURITY|TRANSACTION|SQL_PERFORMANCE|CACHE_CONSISTENCY|MQ_CONSISTENCY|EXCEPTION_HANDLING|TEST_GAP", '
        '"filePath": string, "startLine": integer, "endLine": integer, '
        '"title": string, "body": string, "suggestion": string, "confidence": "LOW|MEDIUM|HIGH", '
        '"contextStatus": "SUFFICIENT|PARTIAL|INSUFFICIENT", '
        '"evidence": string[], "missingContext": string[], "contextSummary": string}]}。\n'
        "不要使用 type、file_path、line_range、path、line 等替代字段；没有准确行号时使用最接近的 diff 新增或修改行号。\n"
        "只报告本次变更引入的、可执行的代码质量问题，不报告历史存量问题。\n"
        "重点关注正确性、数据一致性、安全、事务边界、SQL 性能、缓存一致性、MQ 一致性、异常处理、可观测性和关键测试缺口。\n"
        "不报告纯代码风格、命名偏好、格式、注释或主观重构建议。\n"
        "不要编造输入中不存在的文件或行号；缺少证据时不要报告，除非潜在影响很高且必须人工确认。\n"
        "每个 finding 都必须填写上下文字段：contextStatus 表示证据是否充分，evidence 写本次判断依赖的 diff 或上下文依据，missingContext 写仍缺少的上下文类型，contextSummary 用一句中文概括已看到的上下文。\n"
        "如果只能基于 diff 推断且缺少调用方、引用关系、同文件上下文、配置、表结构或测试结果，应使用 PARTIAL 或 INSUFFICIENT，并将 confidence 设为 LOW 或 MEDIUM。\n"
        "上下文不足时不要武断输出高风险或紧急；除非属于明确的安全、数据一致性或线上正确性硬风险，否则应把 severity 控制为 MINOR，并在 body 中说明“需要确认”。\n"
        "删除方法、修改方法签名、删除字段或修改 DTO/VO 字段时，不要仅凭变更动作判定风险；必须结合调用方、字段引用、序列化/反序列化、Mapper、前端或外部调用迁移证据，缺少这些证据时输出需要确认。\n"
        "Context Pack / reviewContext 只是辅助证据，用于说明本次可见上下文、不可用上下文和历史上下文不足反馈；"
        "它不能覆盖或削弱明确的安全、数据一致性、事务一致性或线上正确性硬风险。\n"
        "本地引用证据只表示在当前 task worktree 中检索到的有限引用片段；字段引用和 DB / Mapper / Entity snippets 也只是有限证据，DB 证据仅来自源码、Mapper、Entity 和迁移脚本，不代表运行期生产 schema。不能仅凭未命中引用、引用 snippets 未注入或 requested context 不可用判定无风险，也不能覆盖硬风险。\n"
        "Context Pack 中的 notInjectedEvidence / BUDGET_CUT 表示本地已命中或已请求的证据因预算、能力或环境原因未进入模型；这不是“没有引用”或“没有风险”的证明。\n"
        "当 DB_SQL_MAPPER_CHANGED、DTO_FIELD_CHANGED、FIELD_DELETED、METHOD_SIGNATURE_CHANGED、METHOD_DELETED 相关的关键字段引用、调用方、Mapper、Entity、迁移脚本、配置读取点或表结构证据被预算裁剪、未注入或不可用时，除非 diff 本身足以证明安全、数据一致性或线上正确性硬风险，否则 finding 必须使用 PARTIAL 或 INSUFFICIENT，并将 confidence 设为 LOW 或 MEDIUM，不能输出 HIGH confidence。\n"
        "Context Planner 只提示本次可能缺少的证据和 requestedContexts；它不能作为自动忽略、自动降级或覆盖硬风险的依据。\n"
        "你可以参考上下文，但最终只能报告由 changed files 白名单中的 diff 引入的问题。"
    )
    instructions = str(request.get("instructions") or "").strip()
    policy_text = str(request.get("projectReviewPoliciesText") or "").strip()
    parts = [item for item in (instructions, policy_text, protocol) if item]
    return "\n\n".join(parts)


def render_input(request: dict[str, Any]) -> str:
    return (
        f"Review mode: {request.get('mode') or '-'}\n"
        f"Base ref: {request.get('baseRef') or '-'}\n"
        f"Commit sha: {request.get('commitSha') or '-'}\n"
        f"Title: {request.get('title') or '-'}\n"
        f"Changed files: {request.get('changedFiles') or []}\n\n"
        f"Review Context Pack:\n{request.get('reviewContextText') or '-'}\n\n"
        f"Diff:\n{request.get('diffText') or '-'}"
    )


def render_fix_instructions(request: dict[str, Any]) -> str:
    return (
        "你是资深代码修复助手。你只为一个 AI Review finding 生成修复预览 patch。\n"
        "必须只返回 unified diff 文本，不要 Markdown，不要代码围栏，不要解释文字。\n"
        "patch 必须以 diff --git 开头，并包含 ---、+++、@@ hunk。\n"
        "只允许修改当前 finding 对应文件和相关行附近代码；不要修改其他文件。\n"
        "不得引入 diff 外无法确认的新依赖、配置或大范围重构。\n"
        "如果上下文不足以安全修复，返回一个最小 patch，并在注释或代码附近保留最小必要保护逻辑；不要编造不存在的业务 API。\n"
        f"目标文件：{request.get('filePath') or '-'}"
    )


def render_fix_input(request: dict[str, Any]) -> str:
    finding = request.get("finding") or {}
    return (
        f"Review mode: FIX_PREVIEW\n"
        f"File path: {request.get('filePath') or '-'}\n"
        f"Finding title: {finding.get('title') or '-'}\n"
        f"Finding category: {finding.get('category') or '-'}\n"
        f"Finding severity: {finding.get('severity') or '-'}\n"
        f"Finding line: {finding.get('startLine') or '-'}-{finding.get('endLine') or finding.get('startLine') or '-'}\n"
        f"Finding body: {finding.get('body') or '-'}\n"
        f"Finding suggestion: {finding.get('suggestion') or '-'}\n\n"
        f"Original file diff:\n{request.get('diffText') or '-'}"
    )


def openai_responses_request(model: str, request: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": model,
        "instructions": render_instructions(request),
        "input": render_input(request),
        "text": {"format": json_schema_format()},
        "store": False,
    }


def openai_responses_fix_request(model: str, request: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": model,
        "instructions": render_fix_instructions(request),
        "input": render_fix_input(request),
        "store": False,
    }


def anthropic_messages_request(model: str, request: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": 4096,
        "system": render_instructions(request),
        "messages": [{"role": "user", "content": render_input(request)}],
    }


def anthropic_messages_fix_request(model: str, request: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": 4096,
        "system": render_fix_instructions(request),
        "messages": [{"role": "user", "content": render_fix_input(request)}],
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


def openai_chat_compatible_fix_request(model: str, request: dict[str, Any]) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": render_fix_instructions(request)},
            {"role": "user", "content": render_fix_input(request)},
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
                            "contextStatus",
                            "evidence",
                            "missingContext",
                            "contextSummary",
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
                            "contextStatus": {
                                "type": "string",
                                "enum": ["SUFFICIENT", "PARTIAL", "INSUFFICIENT"],
                            },
                            "evidence": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "missingContext": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "contextSummary": {"type": "string"},
                        },
                    },
                },
            },
        },
    }
