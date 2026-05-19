from typing import Any

from app.core.tracing import get_trace_id


def api_response(
    *,
    success: bool,
    code: str,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    return {
        "success": success,
        "code": code,
        "message": message,
        "data": data,
        "traceId": get_trace_id(),
    }


def ok(data: Any) -> dict[str, Any]:
    return api_response(success=True, code="OK", message="success", data=data)


def fail(code: str, message: str) -> dict[str, Any]:
    return api_response(success=False, code=code, message=message, data=None)

