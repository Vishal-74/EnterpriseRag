"""Application errors and the JSON envelope returned to clients."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import logger, request_id_var


class AppError(Exception):
    """Expected failure with a stable client-facing code."""

    def __init__(self, message: str, *, code: str, status_code: int) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code

    def extra(self) -> dict[str, Any]:
        return {}


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, code="not_found", status_code=404)


class AuthError(AppError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message, code="unauthorized", status_code=401)


class ForbiddenError(AppError):
    def __init__(self, message: str = "You do not have access to that resource") -> None:
        super().__init__(message, code="forbidden", status_code=403)


class ConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="conflict", status_code=409)


class DuplicateDocumentError(AppError):
    def __init__(self, document_id: UUID, status: str) -> None:
        super().__init__(
            "This file has already been uploaded.",
            code="duplicate_document",
            status_code=409,
        )
        self.document_id = document_id
        self.document_status = status

    def extra(self) -> dict[str, Any]:
        return {
            "document_id": str(self.document_id),
            "document_status": self.document_status,
        }


class RateLimitError(AppError):
    def __init__(self, message: str = "Too many requests. Try again shortly.") -> None:
        super().__init__(message, code="rate_limited", status_code=429)


class ValidationFailed(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="invalid_request", status_code=400)


class ProviderFailure(AppError):
    def __init__(self, message: str = "The language model provider is unavailable.") -> None:
        super().__init__(message, code="provider_unavailable", status_code=502)


class ParseError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="parse_error", status_code=422)


def _envelope(
    code: str, message: str, *, details: Any = None, extra: dict[str, Any] | None = None
) -> dict[str, Any]:
    error: dict[str, Any] = {
        "code": code,
        "message": message,
        "request_id": request_id_var.get(),
    }
    if extra:
        error.update(extra)
    if details is not None:
        error["details"] = details
    return {"error": error}


def register_exception_handlers(app: FastAPI) -> None:
    """Attach handlers that always return the same error shape."""

    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, extra=exc.extra()),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {
                "loc": list(err.get("loc", [])),
                "msg": err.get("msg", ""),
                "type": err.get("type", ""),
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_envelope("invalid_request", "Request validation failed.", details=details),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error")
        return JSONResponse(
            status_code=500,
            content=_envelope("internal_error", "Something went wrong. Please try again."),
        )
