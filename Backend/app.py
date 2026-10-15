"""
FastAPI backend server for PMS Dashboard.
Provides clean endpoints for PMS Dashboard following Clean Architecture.

Run with:  cd Backend && uvicorn app:app --reload --port 8000
"""
import sys
import os
import io
import logging

# Force UTF-8 encoding for console output (Windows compatibility, skip on Vercel)
if sys.stdout and hasattr(sys.stdout, 'buffer') and not os.environ.get("VERCEL"):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware
from contextlib import asynccontextmanager

# Ensure Backend directory is on the import path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.routers import router as api_router
from config.socket_config import SOCKETIO_ENABLED, sio
from api.middleware.auth_middleware import AuthMiddleware
from api.middleware.error_handling_middleware import (
    ErrorHandlingMiddleware,
    install_api_error_handlers,
)
from api.middleware.rate_limit_middleware import (
    RateLimitPostAuthMiddleware,
    RateLimitPreAuthMiddleware,
)
from services.rate_limit.enforcement import (
    RATE_LIMIT_HEADERS,
    RateLimitExceeded,
    rate_limit_exception_handler,
)
from config.database import SessionLocal
from config.logging_config import setup_logging
from config import settings

# Initialize structured logging
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    from services.obsolete_json_data import warn_obsolete_json_files
    warn_obsolete_json_files(settings.DATA_DIR)
    if not os.environ.get("VERCEL"):
        try:
            from services.seeding_service import DatabaseSeeder
            from services.permission_seed import seed_role_permissions

            seed_demo_levels = settings.PMS_SEED_DEMO_LEVELS
            seeder = DatabaseSeeder() if seed_demo_levels else None
            if seed_demo_levels and seeder is not None:
                seeder.seed_demo_performance_levels()
            
            if settings.PMS_SEED_PERMISSIONS_ON_STARTUP:
                db = SessionLocal()
                try:
                    seed_role_permissions(db)
                finally:
                    db.close()
        except Exception as e:
            logger.warning("Lifespan startup seeding skipped or failed: %s", e)
        
    yield

app = FastAPI(
    title="PMS Dashboard API",
    description="Backend Clean Architecture API for Saudi German Hospital Performance Management System",
    version="2.0.0",
    lifespan=lifespan
)
install_api_error_handlers(app)
app.add_exception_handler(RateLimitExceeded, rate_limit_exception_handler)

# Per-user rate limits run after AuthMiddleware. Added before the security-header
# middleware, so the 429 responses it produces still carry the baseline headers.
app.add_middleware(RateLimitPostAuthMiddleware)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    """Apply baseline browser protections to every API response."""

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if settings.APP_ENV in {"production", "staging"}:
        response.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
    return response

# Register AuthMiddleware
app.add_middleware(AuthMiddleware)

# Address rate limits run before authentication, so unauthenticated requests still count.
app.add_middleware(RateLimitPreAuthMiddleware)

# Register ErrorHandlingMiddleware (to catch database/internal exceptions and set request_id)
app.add_middleware(ErrorHandlingMiddleware)

# Compress JSON responses large enough to benefit from it. CORS remains the
# outermost middleware so compressed errors and preflight responses keep the
# same cross-origin behavior.
app.add_middleware(GZipMiddleware, minimum_size=1000)

# CORS Middleware — allow frontend dev servers (outermost to wrap errors and auth responses)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Server-Timing", "X-Response-Time-Ms", *RATE_LIMIT_HEADERS],
)


# Mount Routers
app.include_router(api_router, prefix="/api")

@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "online",
        "api": "PMS Dashboard API - Clean Architecture",
        "version": "2.0.0",
    }

# Wrap FastAPI with Socket.IO when the optional real-time runtime is available.
# This enables polling fallback on serverless environments like Vercel.
if SOCKETIO_ENABLED:
    try:
        from socketio import ASGIApp
        app = ASGIApp(sio, app)
    except Exception as e:
        logger.warning(f"Failed to mount Socket.IO: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=settings.PORT, reload=True)

# ========== Cloudflare Workers Compatibility Layer ==========
# Export FastAPI app for Workers compatibility
handler = app

try:
    from workers import WorkerEntrypoint
    import asgi

    class Default(WorkerEntrypoint):
        async def fetch(self, request):
            return await asgi.fetch(app, request, self.env)
            
    # Make the entrypoint class available as default export
    default = Default
except ImportError:
    # Local execution or non-worker environment
    pass
