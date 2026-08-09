"""Error Handling Middleware
Intercepts all unhandled exceptions, records them in the database,
and maps them to standard JSON error responses.
"""

import uuid
import logging
import time
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import (
    HTTPException as FastAPIHTTPException,
    RequestValidationError,
)
from config.database import SessionLocal
from services.error_tracker import ErrorTracker
from config.logging_config import request_id_ctx

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _message_from_detail(detail, fallback: str) -> str:
    if isinstance(detail, str) and detail.strip():
        return detail
    if isinstance(detail, dict):
        message = detail.get("message")
        if isinstance(message, str) and message.strip():
            return message
    return fallback


async def canonical_http_exception_handler(
    request: Request,
    exc: FastAPIHTTPException,
) -> JSONResponse:
    """Add canonical fields while retaining FastAPI's existing `detail` contract."""
    return JSONResponse(
        status_code=exc.status_code,
        headers=exc.headers,
        content=jsonable_encoder({
            "success": False,
            "message": _message_from_detail(exc.detail, "Request failed"),
            "detail": exc.detail,
            "request_id": _request_id(request),
        }),
    )


async def canonical_validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Retain validation details and expose the same additive error envelope."""
    detail = exc.errors()
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder({
            "success": False,
            "message": "Request validation failed",
            "detail": detail,
            "request_id": _request_id(request),
        }),
    )


def install_api_error_handlers(application) -> None:
    application.add_exception_handler(
        FastAPIHTTPException,
        canonical_http_exception_handler,
    )
    application.add_exception_handler(
        RequestValidationError,
        canonical_validation_exception_handler,
    )


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Intercepts and records exceptions, returning clean JSON responses"""

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        started_at = time.perf_counter()
        response = None
        exception_error_registered = False
        normalized_path = request.url.path.rstrip("/")
        is_health_request = (
            normalized_path == "/health"
            or normalized_path.startswith("/health/")
            or normalized_path == "/api/health"
            or normalized_path.startswith("/api/health/")
        )

        try:
            if not is_health_request:
                ErrorTracker.register_request()

            try:
                response = await call_next(request)
            except Exception as exc:
                status_code = 500
                is_critical = True

                if isinstance(exc, (FastAPIHTTPException, StarletteHTTPException)):
                    status_code = exc.status_code
                    is_critical = status_code >= 500
                elif isinstance(exc, ValueError):
                    status_code = 400
                    is_critical = False

                if is_health_request:
                    is_critical = False

                if status_code >= 500 or is_critical:
                    try:
                        with SessionLocal() as db:
                            ErrorTracker.log_error(db, request, exc, request_id)
                            exception_error_registered = True
                    except Exception:
                        logger.exception("Error handling middleware failed to write to database")

                route = request.scope.get("route")
                route_path = getattr(route, "path", None) or "unmatched"
                logger.exception("Unhandled exception on %s %s", request.method, route_path)

                error_message = "An internal server error occurred."
                error_detail = error_message
                if isinstance(exc, (FastAPIHTTPException, StarletteHTTPException)):
                    error_detail = exc.detail
                    error_message = _message_from_detail(exc.detail, "Request failed")
                elif isinstance(exc, ValueError):
                    error_message = str(exc)
                    error_detail = error_message

                response = JSONResponse(
                    status_code=status_code,
                    content={
                        "success": False,
                        "message": error_message,
                        "detail": error_detail,
                        "request_id": request_id,
                    },
                )

            if (
                response.status_code >= 500
                and not is_health_request
                and not exception_error_registered
            ):
                ErrorTracker.register_error()

            duration_ms = (time.perf_counter() - started_at) * 1000.0
            response.headers["X-Request-ID"] = request_id
            response.headers["Server-Timing"] = f"app;dur={duration_ms:.2f}"
            response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"

            route = request.scope.get("route")
            route_path = getattr(route, "path", None) or "unmatched"
            content_length = response.headers.get("content-length")
            logger.info(
                "request completed method=%s route=%s status=%s duration_ms=%.2f response_bytes=%s",
                request.method,
                route_path,
                response.status_code,
                duration_ms,
                content_length or "unknown",
                extra={
                    "path": route_path,
                    "method": request.method,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "response_bytes": (
                        int(content_length)
                        if content_length and content_length.isdigit()
                        else None
                    ),
                },
            )
            return response
        finally:
            request_id_ctx.reset(token)
