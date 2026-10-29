"""Consistent error responses: ``{"error": {"code", "message", "details"}}``."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


class NotFound(AppError):
    def __init__(self, what: str = "Resource"):
        super().__init__("not_found", f"{what} not found.", 404)


class Forbidden(AppError):
    def __init__(self, message: str = "You do not have permission to perform this action."):
        super().__init__("forbidden", message, 403)


class AnalysisError(AppError):
    """Raised by statistical procedures when an analysis cannot be performed reliably."""

    def __init__(self, message: str, code: str = "analysis_not_possible", suggestion: str | None = None):
        super().__init__(code, message, 422, {"suggestion": suggestion} if suggestion else None)
        self.suggestion = suggestion


def _body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def install_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_req: Request, exc: AppError):
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_req: Request, exc: RequestValidationError):
        details = [{"loc": list(e.get("loc", [])), "msg": e.get("msg")} for e in exc.errors()]
        return JSONResponse(_body("validation_error", "The request is invalid.", details), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_req: Request, exc: StarletteHTTPException):
        code = {401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed",
                413: "payload_too_large"}.get(exc.status_code, "http_error")
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code)
