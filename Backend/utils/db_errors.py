"""Classify "database temporarily unavailable" failures (pool timeout, lost
connection, server restarting) so callers answer 503 + Retry-After instead of
401/500/success:false. The frontend treats 401 as "session expired" and logs
the user out, which only adds load while the database is saturated.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import exc as sa_exc
from starlette.responses import JSONResponse

RETRY_AFTER_SECONDS = 5
UNAVAILABLE_MESSAGE = "The service is temporarily busy. Please retry shortly."

_UNAVAILABLE_TYPES: tuple[type[BaseException], ...] = (
    sa_exc.TimeoutError,  # QueuePool limit reached
    sa_exc.OperationalError,  # connection refused / dropped / server shutting down
    sa_exc.InterfaceError,
    sa_exc.DisconnectionError,
    TimeoutError,
    ConnectionError,
)


def is_db_unavailable(exc: BaseException | None) -> bool:
    """True for the exception or anything in its cause/context chain."""
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, _UNAVAILABLE_TYPES):
            return True
        if isinstance(exc, sa_exc.DBAPIError) and exc.connection_invalidated:
            return True
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return False


def retry_after_headers() -> dict[str, str]:
    return {"Retry-After": str(RETRY_AFTER_SECONDS)}


class DatabaseUnavailableError(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=503, detail=UNAVAILABLE_MESSAGE, headers=retry_after_headers())


def unavailable_response(request_id: str | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        headers=retry_after_headers(),
        content={
            "success": False,
            "code": "SERVICE_UNAVAILABLE",
            "message": UNAVAILABLE_MESSAGE,
            "detail": UNAVAILABLE_MESSAGE,
            "request_id": request_id,
        },
    )
