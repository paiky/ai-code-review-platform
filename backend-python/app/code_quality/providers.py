from __future__ import annotations

import json
from datetime import datetime
from time import perf_counter
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


def run_fix_provider(
    db: Session,
    task_id: int,
    provider: CodeQualityModelProvider,
    fix_request: dict[str, Any],
) -> dict[str, Any]:
    append_progress(
        db,
        task_id,
        "FIX_PROVIDER_SELECTED",
        "INFO",
        "已选择修复预览 Provider",
        f"provider={provider.provider_code}, type={provider.provider_type}, enabled={provider.enabled}",
    )
    db.commit()
    if not provider.enabled:
        _validation_failed(db, task_id, f"{provider.provider_code} model provider is disabled")
        raise AppError("BAD_REQUEST", f"{provider.provider_code} model provider is disabled", 400)
    if provider.provider_type == "OPENAI_RESPONSES":
        return _run_openai_responses_fix(db, task_id, provider, fix_request)
    if provider.provider_type == "ANTHROPIC_MESSAGES":
        return _run_anthropic_messages_fix(db, task_id, provider, fix_request)
    if provider.provider_type == "OPENAI_CHAT_COMPATIBLE":
        return _run_openai_compatible_fix(db, task_id, provider, fix_request)
    _validation_failed(db, task_id, f"Unsupported provider type: {provider.provider_type}")
    raise AppError("BAD_REQUEST", f"Unsupported provider type: {provider.provider_type}", 400)


def test_provider_connection(
    provider: CodeQualityModelProvider,
    request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request = request or {}
    started_at = datetime.now()
    try:
        prepared = _provider_connection_request(provider, request)
        started = perf_counter()
        with _provider_http_client(prepared["timeout_seconds"]) as client:
            response = client.post(
                prepared["endpoint"],
                json=prepared["body"],
                headers=prepared["headers"],
            )
        latency_ms = int((perf_counter() - started) * 1000)
        raw = response.text
        if response.is_error:
            error_message = (
                f"http_status_error: status={response.status_code}, "
                f"body={_abbreviate(raw, 1000)}"
            )
            return _provider_connection_result(
                provider,
                prepared,
                "FAILED",
                latency_ms,
                error_message=error_message,
                response_preview=raw,
                started_at=started_at,
            )
        output_text = prepared["output_extractor"](raw)
        return _provider_connection_result(
            provider,
            prepared,
            "SUCCESS",
            latency_ms,
            response_preview=output_text,
            started_at=started_at,
        )
    except Exception as exception:
        prepared = {
            "endpoint": _blank_to_none(request.get("endpointUrl")) or provider.endpoint_url,
            "model": _blank_to_none(request.get("modelName")) or provider.model_name,
        }
        return _provider_connection_result(
            provider,
            prepared,
            "FAILED",
            None,
            error_message=_provider_error_message(exception, 30),
            started_at=started_at,
        )


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
        timeout_seconds=_provider_timeout_seconds(
            provider,
            settings.openai_code_review_timeout_seconds,
        ),
        output_extractor=_extract_openai_output,
        review_request=review_request,
    )


def _run_openai_responses_fix(
    db: Session,
    task_id: int,
    provider: CodeQualityModelProvider,
    fix_request: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()
    api_key = provider.api_key or settings.openai_api_key
    endpoint = provider.endpoint_url or settings.openai_responses_url
    model = fix_request.get("model") or provider.model_name or settings.openai_code_review_model
    validation_error = _validation_error(
        api_key,
        fix_request.get("diffText"),
        endpoint,
        model,
        api_key_message="OPENAI_API_KEY is required for OpenAI API fix preview",
        diff_message="diffText is required for OpenAI API fix preview",
    )
    if validation_error:
        _validation_failed(db, task_id, validation_error)
        raise AppError("BAD_REQUEST", validation_error, 400)
    _validation_passed(db, task_id, provider.provider_code, endpoint, model, fix_request)
    return _run_text_http_provider(
        db,
        task_id,
        source="OPENAI",
        request_message="准备调用 OpenAI Responses API 生成修复预览",
        response_message="OpenAI API 已返回修复预览响应",
        endpoint=endpoint,
        model=model,
        body=prompt.openai_responses_fix_request(model, fix_request),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout_seconds=_provider_timeout_seconds(
            provider,
            settings.openai_code_review_timeout_seconds,
        ),
        output_extractor=_extract_openai_output,
        request=fix_request,
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
        timeout_seconds=_provider_timeout_seconds(
            provider,
            settings.anthropic_code_review_timeout_seconds,
        ),
        output_extractor=_extract_anthropic_output,
        review_request=review_request,
    )


def _run_anthropic_messages_fix(
    db: Session,
    task_id: int,
    provider: CodeQualityModelProvider,
    fix_request: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()
    api_key = provider.api_key or settings.anthropic_api_key
    endpoint = provider.endpoint_url or settings.anthropic_messages_url
    model = fix_request.get("model") or provider.model_name or settings.anthropic_code_review_model
    validation_error = _validation_error(
        api_key,
        fix_request.get("diffText"),
        endpoint,
        model,
        api_key_message="ANTHROPIC_API_KEY is required for Anthropic API fix preview",
        diff_message="diffText is required for Anthropic API fix preview",
    )
    if validation_error:
        _validation_failed(db, task_id, validation_error)
        raise AppError("BAD_REQUEST", validation_error, 400)
    _validation_passed(db, task_id, provider.provider_code, endpoint, model, fix_request)
    return _run_text_http_provider(
        db,
        task_id,
        source="ANTHROPIC",
        request_message="准备调用 Anthropic Messages API 生成修复预览",
        response_message="Anthropic API 已返回修复预览响应",
        endpoint=endpoint,
        model=model,
        body=prompt.anthropic_messages_fix_request(model, fix_request),
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
        timeout_seconds=_provider_timeout_seconds(
            provider,
            settings.anthropic_code_review_timeout_seconds,
        ),
        output_extractor=_extract_anthropic_output,
        request=fix_request,
    )


def _run_openai_compatible(
    db: Session,
    task_id: int,
    provider: CodeQualityModelProvider,
    review_request: dict[str, Any],
) -> dict[str, Any]:
    api_key = provider.api_key or _openai_compatible_env_api_key(provider.provider_code)
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
        timeout_seconds=_openai_compatible_timeout_seconds(provider),
        output_extractor=_extract_openai_compatible_output,
        review_request=review_request,
    )


def _run_openai_compatible_fix(
    db: Session,
    task_id: int,
    provider: CodeQualityModelProvider,
    fix_request: dict[str, Any],
) -> dict[str, Any]:
    api_key = provider.api_key or _openai_compatible_env_api_key(provider.provider_code)
    endpoint_base = provider.endpoint_url
    model = fix_request.get("model") or provider.model_name
    validation_error = _validation_error(
        api_key,
        fix_request.get("diffText"),
        endpoint_base,
        model,
        api_key_message=f"{provider.provider_code} API key is required for fix preview",
        diff_message="diffText is required for fix preview",
        endpoint_message=f"{provider.provider_code} endpointUrl is required for fix preview",
        model_message=f"{provider.provider_code} modelName is required for fix preview",
    )
    if validation_error:
        _validation_failed(db, task_id, validation_error)
        raise AppError("BAD_REQUEST", validation_error, 400)
    endpoint = _chat_completions_url(endpoint_base)
    _validation_passed(db, task_id, provider.provider_code, endpoint, model, fix_request)
    return _run_text_http_provider(
        db,
        task_id,
        source=provider.provider_code,
        request_message="准备调用 OpenAI-compatible Chat Completions API 生成修复预览",
        response_message=f"{provider.provider_code} API 已返回修复预览响应",
        endpoint=endpoint,
        model=model,
        body=prompt.openai_chat_compatible_fix_request(model, fix_request),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        timeout_seconds=_openai_compatible_timeout_seconds(provider),
        output_extractor=_extract_openai_compatible_output,
        request=fix_request,
    )


def _openai_compatible_env_api_key(provider_code: str) -> str:
    settings = get_settings()
    if provider_code == "DEEPSEEK":
        return settings.deepseek_api_key
    if provider_code == "XIAOMIMO":
        return settings.xiaomimo_api_key
    if provider_code == "GLM":
        return settings.glm_api_key
    return ""


def _openai_compatible_timeout_seconds(provider: CodeQualityModelProvider) -> int:
    settings = get_settings()
    provider_code = provider.provider_code
    if provider_code == "DEEPSEEK":
        return _provider_timeout_seconds(provider, settings.deepseek_code_review_timeout_seconds)
    if provider_code == "XIAOMIMO":
        return _provider_timeout_seconds(provider, settings.xiaomimo_code_review_timeout_seconds)
    if provider_code == "GLM":
        return _provider_timeout_seconds(provider, settings.glm_code_review_timeout_seconds)
    return _provider_timeout_seconds(provider, settings.openai_code_review_timeout_seconds)


def _provider_timeout_seconds(provider: CodeQualityModelProvider, default_timeout: int) -> int:
    timeout = provider.timeout_seconds if provider.timeout_seconds is not None else default_timeout
    return max(int(timeout or 1000), 1)


def _provider_connection_request(
    provider: CodeQualityModelProvider,
    request: dict[str, Any],
) -> dict[str, Any]:
    settings = get_settings()
    provider_type = provider.provider_type
    if provider_type == "OPENAI_RESPONSES":
        endpoint = _request_value(
            request,
            "endpointUrl",
            provider.endpoint_url or settings.openai_responses_url,
        )
        model = _request_value(
            request,
            "modelName",
            provider.model_name or settings.openai_code_review_model,
        )
        api_key = _request_value(request, "apiKey", provider.api_key or settings.openai_api_key)
        validation_error = _connection_validation_error(
            provider.provider_code,
            api_key,
            endpoint,
            model,
        )
        if validation_error:
            raise ValueError(validation_error)
        return {
            "endpoint": endpoint,
            "model": model,
            "timeout_seconds": _connection_timeout_seconds(
                request,
                _provider_timeout_seconds(provider, settings.openai_code_review_timeout_seconds),
            ),
            "body": {"model": model, "input": "Reply with the single word pong.", "store": False},
            "headers": {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            "output_extractor": _extract_openai_output,
        }
    if provider_type == "ANTHROPIC_MESSAGES":
        endpoint = _request_value(
            request,
            "endpointUrl",
            provider.endpoint_url or settings.anthropic_messages_url,
        )
        model = _request_value(
            request,
            "modelName",
            provider.model_name or settings.anthropic_code_review_model,
        )
        api_key = _request_value(request, "apiKey", provider.api_key or settings.anthropic_api_key)
        validation_error = _connection_validation_error(
            provider.provider_code,
            api_key,
            endpoint,
            model,
        )
        if validation_error:
            raise ValueError(validation_error)
        return {
            "endpoint": endpoint,
            "model": model,
            "timeout_seconds": _connection_timeout_seconds(
                request,
                _provider_timeout_seconds(provider, settings.anthropic_code_review_timeout_seconds),
            ),
            "body": {
                "model": model,
                "max_tokens": 32,
                "messages": [{"role": "user", "content": "Reply with the single word pong."}],
            },
            "headers": {
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            "output_extractor": _extract_anthropic_output,
        }
    if provider_type == "OPENAI_CHAT_COMPATIBLE":
        endpoint_base = _request_value(request, "endpointUrl", provider.endpoint_url)
        endpoint = _chat_completions_url(endpoint_base) if endpoint_base else None
        model = _request_value(request, "modelName", provider.model_name)
        api_key = _request_value(
            request,
            "apiKey",
            provider.api_key or _openai_compatible_env_api_key(provider.provider_code),
        )
        validation_error = _connection_validation_error(
            provider.provider_code,
            api_key,
            endpoint_base,
            model,
        )
        if validation_error:
            raise ValueError(validation_error)
        return {
            "endpoint": endpoint,
            "model": model,
            "timeout_seconds": _connection_timeout_seconds(
                request,
                _openai_compatible_timeout_seconds(provider),
            ),
            "body": {
                "model": model,
                "messages": [{"role": "user", "content": "Reply with the single word pong."}],
            },
            "headers": {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            "output_extractor": _extract_openai_compatible_output,
        }
    raise ValueError(f"Unsupported provider type: {provider_type}")


def _connection_validation_error(
    provider_code: str,
    api_key: str | None,
    endpoint_url: str | None,
    model: str | None,
) -> str | None:
    if not api_key:
        return f"{provider_code} API key is required for provider connectivity test"
    if not endpoint_url:
        return f"{provider_code} endpointUrl is required for provider connectivity test"
    if not model:
        return f"{provider_code} modelName is required for provider connectivity test"
    return None


def _request_value(request: dict[str, Any], key: str, fallback: str | None) -> str | None:
    if key in request:
        return _blank_to_none(request.get(key))
    return _blank_to_none(fallback)


def _blank_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _connection_timeout_seconds(request: dict[str, Any], default_timeout: int) -> int:
    raw = request.get("timeoutSeconds")
    if raw is not None:
        try:
            return min(max(int(raw), 1), 120)
        except (TypeError, ValueError):
            return 30
    return min(max(int(default_timeout or 30), 1), 30)


def _provider_connection_result(
    provider: CodeQualityModelProvider,
    prepared: dict[str, Any],
    status: str,
    latency_ms: int | None,
    *,
    error_message: str | None = None,
    response_preview: str | None = None,
    started_at: datetime,
) -> dict[str, Any]:
    return {
        "providerCode": provider.provider_code,
        "providerType": provider.provider_type,
        "endpointUrl": prepared.get("endpoint"),
        "modelName": prepared.get("model"),
        "status": status,
        "success": status == "SUCCESS",
        "latencyMs": latency_ms,
        "message": (
            "Provider connectivity test succeeded"
            if status == "SUCCESS"
            else "Provider connectivity test failed"
        ),
        "responsePreview": _abbreviate(response_preview, 500),
        "errorMessage": scrub_sensitive(error_message),
        "startedAt": started_at.isoformat(),
        "finishedAt": datetime.now().isoformat(),
    }


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

        with _provider_http_client(timeout_seconds) as client:
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


def _run_text_http_provider(
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
    request: dict[str, Any],
) -> dict[str, Any]:
    request_json = json.dumps(body, ensure_ascii=False)
    started_at = datetime.now()
    try:
        append_progress(db, task_id, f"{source}_FIX_REQUEST", "INFO", request_message, f"url={endpoint}, model={model}")
        append_progress(
            db,
            task_id,
            f"{source}_FIX_REQUEST_DEBUG",
            "DEBUG",
            f"{source} 修复预览请求摘要",
            _request_debug_detail(request, request_json, endpoint, model),
        )
        append_progress(db, task_id, "FIX_HTTP_REQUEST_START", "INFO", "已发起修复预览 Provider HTTP 请求", f"provider={source}, url={endpoint}, model={model}, timeoutSeconds={timeout_seconds}")
        db.commit()
        with _provider_http_client(timeout_seconds) as client:
            response = client.post(endpoint, json=body, headers=headers)
        raw = response.text
        append_progress(
            db,
            task_id,
            "FIX_HTTP_RESPONSE_HEADERS",
            "ERROR" if response.is_error else "INFO",
            "修复预览 Provider HTTP 响应头已返回",
            _response_summary(response, raw),
        )
        if response.is_error:
            append_progress(db, task_id, "FIX_HTTP_RESPONSE_BODY_PREVIEW", "ERROR", "Provider 返回 HTTP 错误响应", _abbreviate(raw, 3000))
            db.commit()
            response.raise_for_status()
        append_progress(db, task_id, f"{source}_FIX_RESPONSE", "INFO", response_message, f"responseBytes={len(raw)}")
        append_progress(db, task_id, f"{source}_FIX_RESPONSE_RAW", "DEBUG", f"{source} 修复预览原始响应预览", _abbreviate(raw, 3000))
        db.commit()
        output_text = output_extractor(raw)
        patch_text = _strip_patch_fence(output_text)
        if not _looks_like_unified_diff(patch_text):
            append_progress(db, task_id, "FIX_PATCH_PARSE_FAILED", "ERROR", "模型输出不是合法 unified diff", _abbreviate(patch_text, 3000))
            return _failed_fix_result(source, "parse_error: Model output is not a unified diff patch", started_at)
        append_progress(
            db,
            task_id,
            "FIX_PATCH_EXTRACTED",
            "INFO",
            "修复预览 patch 已提取",
            f"provider={source}, patchBytes={len(patch_text.encode('utf-8'))}",
        )
        db.commit()
        return {
            "status": "SUCCESS",
            "provider": source,
            "summary": "AI 修复预览已生成",
            "patchText": patch_text,
            "warnings": [],
            "rawOutput": scrub_sensitive(raw),
            "errorMessage": None,
            "startedAt": started_at,
            "finishedAt": datetime.now(),
        }
    except Exception as exception:
        error_message = _provider_error_message(exception, timeout_seconds)
        append_progress(db, task_id, f"{source}_FIX_FAILED", "ERROR", f"{source} 修复预览执行失败", error_message)
        db.commit()
        return _failed_fix_result(source, error_message, started_at)


def _success_result(
    source: str,
    output_text: str,
    raw_output: str,
    started_at: datetime,
) -> dict[str, Any]:
    card = json.loads(_strip_json_fence(output_text))
    findings = []
    for finding in card.get("findings") or []:
        findings.append(_normalize_finding(finding, source, card.get("overallLevel")))
    overall_level = _normalize_overall_level(card.get("overallLevel")) or _overall_level_from_findings(findings)
    return {
        "status": "SUCCESS",
        "provider": source,
        "overallLevel": overall_level,
        "summary": card.get("summary") or f"{source} review completed",
        "findings": findings,
        "rawOutput": scrub_sensitive(raw_output),
        "exitCode": None,
        "errorMessage": None,
        "startedAt": started_at,
        "finishedAt": datetime.now(),
    }


def _failed_fix_result(provider: str, error_message: str | None, started_at: datetime) -> dict[str, Any]:
    return {
        "status": "FAILED",
        "provider": provider,
        "summary": None,
        "patchText": None,
        "warnings": [],
        "rawOutput": None,
        "errorMessage": error_message or "Fix preview failed",
        "startedAt": started_at,
        "finishedAt": datetime.now(),
    }


def _normalize_finding(finding: dict[str, Any], source: str, overall_level: Any) -> dict[str, Any]:
    line_range = finding.get("line_range") or finding.get("lineRange") or finding.get("lines")
    start_line = _first_present(
        finding,
        "startLine",
        "start_line",
        "line",
        "lineNumber",
        "line_number",
    )
    end_line = _first_present(finding, "endLine", "end_line")
    if isinstance(line_range, list) and line_range:
        start_line = start_line if start_line is not None else line_range[0]
        end_line = end_line if end_line is not None else (line_range[1] if len(line_range) > 1 else line_range[0])
    location = finding.get("location") if isinstance(finding.get("location"), dict) else {}
    if location:
        start_line = start_line if start_line is not None else _first_present(location, "startLine", "start_line", "line")
        end_line = end_line if end_line is not None else _first_present(location, "endLine", "end_line", "line")

    category = _normalize_category(
        _first_present(finding, "category", "type", "kind", "issueType", "issue_type")
    )
    severity = _normalize_severity(
        _first_present(finding, "severity", "riskLevel", "risk_level", "level", "priority")
    ) or _severity_from_overall(overall_level)
    return {
        "severity": severity,
        "category": category,
        "filePath": _first_present(finding, "filePath", "file_path", "path", "file") or location.get("filePath") or location.get("file"),
        "startLine": _to_int(start_line),
        "endLine": _to_int(end_line if end_line is not None else start_line),
        "title": finding.get("title"),
        "body": finding.get("body") or finding.get("description"),
        "suggestion": finding.get("suggestion") or finding.get("recommendation"),
        "confidence": _normalize_confidence(finding.get("confidence")) or "MEDIUM",
        "contextStatus": _normalize_context_status(_first_present(finding, "contextStatus", "context_status")) or "PARTIAL",
        "evidence": _normalize_string_list(_first_present(finding, "evidence", "evidences")),
        "missingContext": _normalize_string_list(_first_present(finding, "missingContext", "missing_context")),
        "contextSummary": _first_present(finding, "contextSummary", "context_summary"),
        "source": source,
    }


def _first_present(mapping: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def _normalize_category(value: Any) -> str:
    normalized = str(value or "").strip().upper().replace("-", "_")
    return {
        "BUG": "CORRECTNESS",
        "CORRECTNESS": "CORRECTNESS",
        "SECURITY": "SECURITY",
        "PERFORMANCE": "SQL_PERFORMANCE",
        "SQL_PERFORMANCE": "SQL_PERFORMANCE",
        "CONSISTENCY": "CORRECTNESS",
        "DATA_CONSISTENCY": "CORRECTNESS",
        "TRANSACTION": "TRANSACTION",
        "TEST": "TEST_GAP",
        "TEST_COVERAGE": "TEST_GAP",
        "TEST_GAP": "TEST_GAP",
        "EXCEPTION": "EXCEPTION_HANDLING",
        "EXCEPTION_HANDLING": "EXCEPTION_HANDLING",
        "CACHE": "CACHE_CONSISTENCY",
        "CACHE_CONSISTENCY": "CACHE_CONSISTENCY",
        "MQ": "MQ_CONSISTENCY",
        "MQ_CONSISTENCY": "MQ_CONSISTENCY",
        "OTHER": "CODE_QUALITY",
        "CODE_QUALITY": "CODE_QUALITY",
    }.get(normalized, normalized or "CODE_QUALITY")


def _normalize_severity(value: Any) -> str | None:
    normalized = str(value or "").strip().upper().replace("-", "_")
    return {
        "BLOCKER": "CRITICAL",
        "CRITICAL": "CRITICAL",
        "HIGH": "MAJOR",
        "MAJOR": "MAJOR",
        "MEDIUM": "MINOR",
        "MINOR": "MINOR",
        "LOW": "MINOR",
    }.get(normalized)


def _severity_from_overall(value: Any) -> str:
    normalized = str(value or "").strip().upper()
    if normalized == "CRITICAL":
        return "CRITICAL"
    if normalized == "HIGH":
        return "MAJOR"
    return "MINOR"


def _normalize_overall_level(value: Any) -> str | None:
    normalized = str(value or "").strip().upper()
    return normalized if normalized in {"LOW", "MEDIUM", "HIGH", "CRITICAL"} else None


def _overall_level_from_findings(findings: list[dict[str, Any]]) -> str:
    severities = {finding.get("severity") for finding in findings}
    if "CRITICAL" in severities:
        return "CRITICAL"
    if "MAJOR" in severities:
        return "HIGH"
    if "MINOR" in severities:
        return "MEDIUM"
    return "LOW"


def _normalize_confidence(value: Any) -> str | None:
    normalized = str(value or "").strip().upper()
    return normalized if normalized in {"LOW", "MEDIUM", "HIGH"} else None


def _normalize_context_status(value: Any) -> str | None:
    normalized = str(value or "").strip().upper()
    return normalized if normalized in {"SUFFICIENT", "PARTIAL", "INSUFFICIENT"} else None


def _normalize_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    normalized: list[str] = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, dict):
            text = item.get("text") or item.get("summary") or item.get("snippet") or item.get("type")
        else:
            text = item
        compact = " ".join(str(text or "").split())
        if compact:
            normalized.append(compact[:500])
    return normalized[:12]


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


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


def _provider_http_client(timeout_seconds: int) -> httpx.Client:
    proxy = get_settings().code_quality_review_proxy or None
    return httpx.Client(timeout=timeout_seconds, proxy=proxy, trust_env=False)


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


def _strip_patch_fence(value: str) -> str:
    text = (value or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    diff_index = text.find("diff --git ")
    if diff_index > 0:
        text = text[diff_index:].strip()
    return text


def _looks_like_unified_diff(value: str | None) -> bool:
    text = (value or "").strip()
    return text.startswith("diff --git ") and "\n--- " in text and "\n+++ " in text and "\n@@" in text


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
