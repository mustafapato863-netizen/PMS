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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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
from config.database import SessionLocal
from config.logging_config import setup_logging
from config import settings

# Initialize structured logging
setup_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.environ.get("VERCEL"):
        try:
            from services.seeding_service import DatabaseSeeder
            from services.permission_seed import seed_role_permissions

            seed_demo_levels = settings.PMS_SEED_DEMO_LEVELS
            seeder = DatabaseSeeder() if settings.PMS_AUTO_SEED or seed_demo_levels else None
            if settings.PMS_AUTO_SEED and seeder is not None:
                seeder.seed_database()
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

# Register AuthMiddleware
app.add_middleware(AuthMiddleware)

# Register ErrorHandlingMiddleware (to catch database/internal exceptions)
app.add_middleware(ErrorHandlingMiddleware)

# CORS Middleware — allow frontend dev servers (outermost to wrap errors and auth responses)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.CORS_ORIGINS),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Server-Timing", "X-Response-Time-Ms"],
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
