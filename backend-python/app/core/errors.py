from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.response import fail

import logging


log = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exception: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exception.status_code,
            content=fail(exception.code, exception.message),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exception: RequestValidationError
    ) -> JSONResponse:
        messages = []
        for error in exception.errors():
            location = ".".join(str(part) for part in error.get("loc", ()))
            messages.append(f"{location} {error.get('msg', 'is invalid')}".strip())
        return JSONResponse(
            status_code=400,
            content=fail("VALIDATION_ERROR", "; ".join(messages) or "Validation failed"),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_error(
        _request: Request, exception: StarletteHTTPException
    ) -> JSONResponse:
        if exception.status_code == 404:
            return JSONResponse(
                status_code=404,
                content=fail("RESOURCE_NOT_FOUND", "Resource not found"),
            )
        return JSONResponse(
            status_code=exception.status_code,
            content=fail("BAD_REQUEST", str(exception.detail or "Bad request")),
        )

    @app.exception_handler(Exception)
    async def handle_unhandled_error(_request: Request, exception: Exception) -> JSONResponse:
        log.exception("Unhandled exception", exc_info=exception)
        return JSONResponse(
            status_code=500,
            content=fail("INTERNAL_ERROR", "Internal server error"),
        )
