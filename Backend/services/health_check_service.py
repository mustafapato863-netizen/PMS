"""Health Check Service
Probes database and cache connectivity and measures latencies.
"""

import time
import logging
from typing import Dict, Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from services.cache_service import redis_client

logger = logging.getLogger(__name__)


class HealthCheckService:
    """Service to perform system component health checks"""

    @staticmethod
    def check_health(db: Session) -> Dict[str, Any]:
        """
        Check database and Redis health and returns detailed status with latencies.
        """
        status = "healthy"
        health_details = {}

        # 1. Probe Database
        db_start = time.perf_counter()
        db_status = "up"
        db_latency = 0.0
        db_error = None
        try:
            db.execute(text("SELECT 1"))
            db_latency = (time.perf_counter() - db_start) * 1000.0  # in ms
        except Exception as e:
            db_status = "down"
            db_error = str(e)
            status = "unhealthy"
            logger.error(f"Health check database error: {e}")

        health_details["database"] = {
            "status": db_status,
            "latency_ms": round(db_latency, 2) if db_status == "up" else None,
            "error": db_error
        }

        # 2. Probe Redis
        redis_status = "disabled"
        redis_latency = 0.0
        redis_error = None
        
        if redis_client is not None:
            redis_start = time.perf_counter()
            try:
                # ping() raises ConnectionError if Redis is down
                if redis_client.ping():
                    redis_status = "up"
                    redis_latency = (time.perf_counter() - redis_start) * 1000.0
                else:
                    redis_status = "down"
            except Exception as e:
                redis_status = "down"
                redis_error = str(e)
                logger.warning(f"Health check Redis error: {e}")
        
        health_details["redis"] = {
            "status": redis_status,
            "latency_ms": round(redis_latency, 2) if redis_status == "up" else None,
            "error": redis_error
        }

        return {
            "status": status,
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "details": health_details
        }
