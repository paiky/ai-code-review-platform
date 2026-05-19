from contextvars import ContextVar
from uuid import uuid4

from fastapi import Request


TRACE_ID_HEADER = "X-Trace-Id"

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    trace_id = _trace_id.get()
    if trace_id:
        return trace_id
    trace_id = uuid4().hex
    _trace_id.set(trace_id)
    return trace_id


async def trace_id_middleware(request: Request, call_next):
    trace_id = request.headers.get(TRACE_ID_HEADER) or uuid4().hex
    token = _trace_id.set(trace_id)
    try:
        response = await call_next(request)
        response.headers[TRACE_ID_HEADER] = trace_id
        return response
    finally:
        _trace_id.reset(token)

