"""Health Check Router
Provides public health check endpoints for container and service monitoring.
"""

import logging
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from config.database import get_db
from services.health_check_service import HealthCheckService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", status_code=status.HTTP_200_OK)
async def check_health(response: Response, db: Session = Depends(get_db)):
    """
    Service health check endpoint.
    Returns details on database and Redis cache health.
    Returns HTTP 503 if critical systems (e.g., Database) are offline.
    """
    try:
        report = HealthCheckService.check_health(db)
        if report["status"] != "healthy":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return report
    except Exception as e:
        logger.error(f"Error during health check execution: {e}")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "error": "Health check failed"
        }


@router.get("/liveness", status_code=status.HTTP_200_OK)
async def check_liveness():
    """
    Liveness probe for host/container health checking.
    Returns HTTP 200 immediately.
    """
    return {"status": "alive"}


@router.get("/readiness", status_code=status.HTTP_200_OK)
async def check_readiness(response: Response, db: Session = Depends(get_db)):
    """
    Readiness probe for full system dependencies check.
    Checks database and Redis cache connectivity.
    """
    try:
        report = HealthCheckService.check_health(db)
        if report["status"] != "healthy":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return report
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unhealthy",
            "error": "Readiness check failed"
        }

