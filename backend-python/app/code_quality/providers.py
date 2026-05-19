from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Callable

import httpx
from sqlalchemy.orm import Session

from app.code_quality import prompt
from app.code_quality.models import CodeQualityModelProvider
from app.code_quality.repository import append_progress, scrub_sensitive
from app.core.config import get_settings
from app.core.errors import AppError


def run_provider(
    db: Session,
    task_id: int,
    provider: CodeQualityModelProvider,
    review_request: dict[str, Any],
) -> dict[str, Any]:
    append_progress(
        db,
        task_id,
        "PROVIDER_SELECTED",
        "INFO",
        "已选择代码质量 Review Provider",
        f"provider={provider.provider_code}, type={provider.provider_type}, enabled={provider.enabled}",
    )
    db.commit()
    if not provider.enabled:
        _validation_failed(
            db,
            task_id,
            f"{provider.provider_code} model provider is disabled",
        )
        raise AppError("BAD_REQUEST", f"{provider.provider_code} model provider is disabled", 400)
    if provider.provider_type == "OPENAI_RESPONSES":
        return _run_openai_responses(db, task_id, provider, review_request)
    if provider.provider_type == "ANTHROPIC_MESSAGES":
        return _run_anthropic_messages(db, task_id, provider, review_request)
    if provider.provider_type == "OPENAI_CHAT_COMPATIBLE":
        return _run_openai_compatible(db, task_id, provider, review_request)
    _validation_failed(db, task_id, f"Unsupported provider type: {provider.provider_type}")
    raise AppError("BAD_REQUEST", f"Unsupported provider type: {provider.provider_type}", 400)


def _run_openai_responses(
    db: Session,
    task_id: int,
    provider: CodeQualityModelProvider,
    review_request: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()
    api_key = provider.api_key or settings.openai_api_key
    endpoint = provider.endpoint_url or settings.openai_responses_url
    model = review_request.get("model") or provider.model_name or settings.openai_code_review_model
    validation_error = _validation_error(
        api_key,
        review_request.get("diffText"),
        endpoint,
        model,
        api_key_message="OPENAI_API_KEY is required for OpenAI API code quality review",
        diff_message="diffText is required for OpenAI API code quality review",
    )
    if validation_error:
        _validation_failed(db, task_id, validation_error)
        raise AppError("BAD_REQUEST", validation_error, 400)
    _validation_passed(db, task_id, provider.provider_code, endpoint, model, review_request)

    body = prompt.openai_responses_request(model, review_request)
    return _run_json_http_provider(
        db,
        task_id,
        source="OPENAI",
        request_message="准备调用 OpenAI Responses API",
        response_message="OpenAI API 已返回响应",
        endpoint=endpoint,
        model=model,
        body=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout_seconds=settings.openai_code_review_timeout_seconds,
        output_extractor=_extract_openai_output,
        review_request=review_request,
    )


def _run_anthropic_messages(
    db: Session,
    task_id: int,
    provider: CodeQualityModelProvider,
    review_request: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()
    api_key = provider.api_key or settings.anthropic_api_key
    endpoint = provider.endpoint_url or settings.anthropic_messages_url
    model = review_request.get("model") or provider.model_name or settings.anthropic_code_review_model
    validation_error = _validation_error(
        api_key,
        review_request.get("diffText"),
        endpoint,
        model,
        api_key_message="ANTHROPIC_API_KEY is required for Anthropic API code quality review",
        diff_message="diffText is required for Anthropic API code quality review",
    )
    if validation_error:
        _validation_failed(db, task_id, validation_error)
        raise AppError("BAD_REQUEST", validation_error, 400)
    _validation_passed(db, task_id, provider.provider_code, endpoint, model, review_request)

    body = prompt.anthropic_messages_request(model, review_request)
    return _run_json_http_provider(
        db,
        task_id,
        source="ANTHROPIC",
        request_message="准备调用 Anthropic Messages API",
        response_message="Anthropic API 已返回响应",
        endpoint=endpoint,
        model=model,
        body=body,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        timeout_seconds=settings.anthropic_code_review_timeout_seconds,
        output_extractor=_extract_anthropic_output,
        review_request=review_request,
    )


def _run_openai_compatible(
    db: Session,
    task_id: int,
    provider: CodeQualityModelProvider,
    review_request: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()
    api_key = provider.api_key or (settings.deepseek_api_key if provider.provider_code == "DEEPSEEK" else "")
    endpoint_base = provider.endpoint_url
    model = review_request.get("model") or provider.model_name
    validation_error = _validation_error(
        api_key,
        review_request.get("diffText"),
        endpoint_base,
        model,
        api_key_message=f"{provider.provider_code} API key is required for code quality review",
        diff_message="diffText is required for code quality review",
        endpoint_message=f"{provider.provider_code} endpointUrl is required for code quality review",
        model_message=f"{provider.provider_code} modelName is required for code quality review",
    )
    if validation_error:
        _validation_failed(db, task_id, validation_error)
        raise AppError("BAD_REQUEST", validation_error, 400)

    endpoint = _chat_completions_url(endpoint_base)
    _validation_passed(db, task_id, provider.provider_code, endpoint, model, review_request)
    body = prompt.openai_chat_compatible_request(model, review_request)
    return _run_json_http_provider(
        db,
        task_id,
        source=provider.provider_code,
        request_message="准备调用 OpenAI-compatible Chat Completions API",
        response_message=f"{provider.provider_code} API 已返回响应",
        endpoint=endpoint,
        model=model,
        body=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout_seconds=settings.openai_code_review_timeout_seconds,
        output_extractor=_extract_openai_compatible_output,
        review_request=review_request,
    )


def _run_json_http_provider(
    db: Session,
    task_id: int,
    *,
    source: str,
    request_message: str,
    response_message: str,
    endpoint: str,
    model: str,
    body: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: int,
    output_extractor: Callable[[str], str],
    review_request: dict[str, Any],
) -> dict[str, Any]:
    request_json = json.dumps(body, ensure_ascii=False)
    started_at = datetime.now()
    try:
        append_progress(db, task_id, f"{source}_REQUEST", "INFO", request_message, f"url={endpoint}, model={model}")
        append_progress(
            db,
            task_id,
            f"{source}_REQUEST_DEBUG",
            "DEBUG",
            f"{source} 请求摘要",
            _request_debug_detail(review_request, request_json, endpoint, model),
        )
        append_progress(
            db,
            task_id,
            f"{source}_REQUEST_PREVIEW",
            "DEBUG",
            f"{source} 请求预览",
            _abbreviate(request_json, 3000),
        )
        append_progress(
            db,
            task_id,
            "HTTP_REQUEST_START",
            "INFO",
            "已发起 Provider HTTP 请求",
            f"provider={source}, url={endpoint}, model={model}, timeoutSeconds={timeout_seconds}",
        )
        db.commit()

        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(endpoint, json=body, headers=headers)
        raw = response.text
        append_progress(
            db,
            task_id,
            "HTTP_RESPONSE_HEADERS",
            "ERROR" if response.is_error else "INFO",
            "Provider HTTP 响应头已返回",
            _response_summary(response, raw),
        )
        if response.is_error:
            append_progress(
                db,
                task_id,
                "HTTP_RESPONSE_BODY_PREVIEW",
                "ERROR",
                "Provider 返回 HTTP 错误响应",
                _abbreviate(raw, 3000),
            )
            db.commit()
            response.raise_for_status()

        append_progress(db, task_id, f"{source}_RESPONSE", "INFO", response_message, f"responseBytes={len(raw)}")
        append_progress(db, task_id, f"{source}_RESPONSE_DEBUG", "DEBUG", f"{source} 响应摘要", f"responseBytes={len(raw)}")
        append_progress(db, task_id, f"{source}_RESPONSE_RAW", "DEBUG", f"{source} 原始响应预览", _abbreviate(raw, 3000))
        db.commit()

        try:
            output_text = output_extractor(raw)
        except json.JSONDecodeError as exception:
            append_progress(
                db,
                task_id,
                "HTTP_RESPONSE_BODY_PREVIEW",
                "ERROR",
                "Provider 返回非 JSON 响应",
                _abbreviate(raw, 3000),
            )
            raise ValueError(f"protocol_error: Provider returned non-JSON response: {exception}") from exception
        except ValueError as exception:
            append_progress(
                db,
                task_id,
                "OUTPUT_EXTRACTED",
                "ERROR",
                "Provider 响应文本提取失败",
                str(exception),
            )
            raise

        append_progress(
            db,
            task_id,
            "OUTPUT_EXTRACTED",
            "INFO",
            "Provider 输出文本已提取",
            f"provider={source}, outputBytes={len(output_text.encode('utf-8'))}",
        )
        append_progress(
            db,
            task_id,
            f"{source}_PARSED",
            "INFO",
            f"{source} API 响应文本已提取",
            f"outputBytes={len(output_text.encode('utf-8'))}",
        )
        append_progress(db, task_id, f"{source}_OUTPUT_TEXT", "DEBUG", f"{source} 输出文本预览", _abbreviate(output_text, 3000))
        append_progress(db, task_id, "JSON_PARSE_START", "INFO", "开始解析模型结构化 JSON 输出", f"provider={source}")
        db.commit()

        try:
            result = _success_result(source, output_text, raw, started_at)
        except json.JSONDecodeError as exception:
            append_progress(
                db,
                task_id,
                "JSON_PARSE_FAILED",
                "ERROR",
                "模型输出不是合法 Review JSON",
                _abbreviate(output_text, 3000),
            )
            raise ValueError(f"parse_error: Model output is not valid review JSON: {exception}") from exception

        append_progress(
            db,
            task_id,
            f"{source}_PARSE_RESULT",
            "INFO",
            f"{source} 解析结果",
            f"findingCount={len(result.get('findings') or [])}, overallLevel={result.get('overallLevel') or '-'}",
        )
        db.commit()
        return result
    except Exception as exception:
        error_message = _provider_error_message(exception, timeout_seconds)
        append_progress(db, task_id, f"{source}_FAILED", "ERROR", f"{source} API Review 执行失败", error_message)
        db.commit()
        return _failed_result(source, error_message, started_at)


def _success_result(
    source: str,
    output_text: str,
    raw_output: str,
    started_at: datetime,
) -> dict[str, Any]:
    card = json.loads(_strip_json_fence(output_text))
    findings = []
    for finding in card.get("findings") or []:
        item = {
            "severity": finding.get("severity"),
            "category": finding.get("category"),
            "filePath": finding.get("filePath"),
            "startLine": finding.get("startLine"),
            "endLine": finding.get("endLine"),
            "title": finding.get("title"),
            "body": finding.get("body"),
            "suggestion": finding.get("suggestion"),
            "confidence": finding.get("confidence"),
            "source": source,
        }
        findings.append(item)
    return {
        "status": "SUCCESS",
        "provider": source,
        "overallLevel": card.get("overallLevel"),
        "summary": card.get("summary") or f"{source} review completed",
        "findings": findings,
        "rawOutput": scrub_sensitive(raw_output),
        "exitCode": None,
        "errorMessage": None,
        "startedAt": started_at,
        "finishedAt": datetime.now(),
    }


def _failed_result(provider: str, error_message: str | None, started_at: datetime) -> dict[str, Any]:
    return {
        "status": "FAILED",
        "provider": provider,
        "overallLevel": None,
        "summary": None,
        "findings": [],
        "rawOutput": None,
        "exitCode": None,
        "errorMessage": error_message or "Code quality review failed",
        "startedAt": started_at,
        "finishedAt": datetime.now(),
    }


def _extract_openai_output(response_body: str) -> str:
    root = json.loads(response_body)
    if root.get("output_text"):
        return str(root["output_text"])
    for output in root.get("output") or []:
        for content in output.get("content") or []:
            if content.get("text"):
                return str(content["text"])
    raise ValueError("OpenAI response does not contain output text")


def _extract_anthropic_output(response_body: str) -> str:
    root = json.loads(response_body)
    parts = [
        str(content.get("text"))
        for content in root.get("content") or []
        if content.get("type") == "text" and content.get("text")
    ]
    if not parts:
        raise ValueError("Anthropic response does not contain text content")
    return "".join(parts)


def _extract_openai_compatible_output(response_body: str) -> str:
    root = json.loads(response_body)
    content = (((root.get("choices") or [{}])[0].get("message") or {}).get("content"))
    if not content:
        raise ValueError("OpenAI-compatible response does not contain choices[0].message.content")
    return str(content)


def _validation_error(
    api_key: str | None,
    diff_text: str | None,
    endpoint_url: str | None,
    model: str | None,
    *,
    api_key_message: str,
    diff_message: str,
    endpoint_message: str = "Provider endpointUrl is required for code quality review",
    model_message: str = "Provider modelName is required for code quality review",
) -> str | None:
    if not api_key:
        return api_key_message
    if not endpoint_url:
        return endpoint_message
    if not model:
        return model_message
    if not diff_text:
        return diff_message
    return None


def _validation_passed(
    db: Session,
    task_id: int,
    provider_code: str,
    endpoint: str,
    model: str,
    request: dict[str, Any],
) -> None:
    append_progress(
        db,
        task_id,
        "REQUEST_VALIDATED",
        "INFO",
        "Provider 请求参数校验通过",
        (
            f"provider={provider_code}, url={endpoint}, model={model}, "
            f"mode={request.get('mode')}, changedFiles={len(request.get('changedFiles') or [])}"
        ),
    )
    db.commit()


def _validation_failed(db: Session, task_id: int, message: str) -> None:
    append_progress(
        db,
        task_id,
        "REQUEST_VALIDATED",
        "ERROR",
        "Provider 请求参数校验失败",
        scrub_sensitive(message),
    )
    db.commit()


def _provider_error_message(exception: Exception, timeout_seconds: int) -> str:
    if isinstance(exception, TimeoutError):
        return scrub_sensitive(str(exception))
    if isinstance(exception, httpx.ConnectTimeout):
        return f"connect_timeout: Provider connection timed out after {timeout_seconds} seconds"
    if isinstance(exception, httpx.ReadTimeout):
        return f"read_timeout: Provider response timed out after {timeout_seconds} seconds"
    if isinstance(exception, httpx.TimeoutException):
        return f"request_timeout: Provider request timed out after {timeout_seconds} seconds"
    if isinstance(exception, httpx.ConnectError):
        return f"connect_error: {scrub_sensitive(str(exception))}"
    if isinstance(exception, httpx.HTTPStatusError):
        response = exception.response
        return scrub_sensitive(
            f"http_status_error: status={response.status_code}, body={_abbreviate(response.text, 1000)}"
        )
    return scrub_sensitive(str(exception))


def _response_summary(response: httpx.Response, raw: str) -> str:
    content_type = response.headers.get("content-type", "-")
    return (
        f"status={response.status_code}, contentType={content_type}, "
        f"responseBytes={len(raw.encode('utf-8'))}"
    )


def _strip_json_fence(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").strip()
        text = text.removesuffix("```").strip()
    return text


def _chat_completions_url(endpoint_url: str) -> str:
    trimmed = endpoint_url.rstrip("/")
    if trimmed.endswith("/chat/completions"):
        return trimmed
    return f"{trimmed}/chat/completions"


def _request_debug_detail(request: dict[str, Any], request_json: str, endpoint_url: str, model: str) -> str:
    diff = request.get("diffText") or ""
    changed_files = request.get("changedFiles") or []
    return (
        f"url={endpoint_url}, model={model}, mode={request.get('mode')}, "
        f"baseRef={request.get('baseRef') or '-'}, changedFiles={len(changed_files)}, "
        f"diffBytes={len(diff.encode('utf-8'))}, requestBytes={len(request_json.encode('utf-8'))}"
    )


def _abbreviate(value: str | None, max_length: int) -> str:
    if not value:
        return ""
    text = scrub_sensitive(value)
    if len(text) <= max_length:
        return text
    return f"{text[:max_length]}\n... truncated, totalChars={len(text)}"
