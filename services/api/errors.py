"""Structured error types and exception handlers for the API.

All error responses follow a consistent JSON shape::

    {"error": {"code": "...", "message": "...", "detail": {...}}}

Internal stack traces are never exposed to clients.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Base exception for API errors with structured responses."""

    __slots__ = ("status_code", "error_code", "message", "detail")

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        detail: Optional[dict[str, Any]] = None,
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.detail = detail or {}
        super().__init__(message)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach structured error handlers to *app*."""

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        body: dict[str, Any] = {
            "error": {
                "code": exc.error_code,
                "message": exc.message,
            }
        }
        if exc.detail:
            body["error"]["detail"] = exc.detail
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
        )
