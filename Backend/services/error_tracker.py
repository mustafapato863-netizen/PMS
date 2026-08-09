"""Error Tracking and Alerting Service
Tracks error rates in a sliding 5-minute window and alerts if rate > 1%.
"""

import os
import time
import logging
import traceback
import urllib.request
import json
from collections import deque
from threading import Lock
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import Request
from models.models import ErrorLog
from services.cache_service import redis_client
from config import settings

logger = logging.getLogger(__name__)

# Thread-safe in-memory storage for sliding window fallback
_in_memory_requests = deque()
_in_memory_errors = deque()
_in_memory_lock = Lock()
_last_alert_time = 0.0


class ErrorTracker:
    """Enterprise Error Tracking and Alerting System"""

    @staticmethod
    def register_request() -> None:
        """
        Record a request for rate calculation. Uses Redis with fallback to in-memory deque.
        """
        now = time.time()
        
        # 1. Use Redis if available
        if redis_client:
            try:
                # Use 1-minute buckets for requests
                bucket = int(now // 60)
                key = f"stats:requests:{bucket}"
                redis_client.incr(key)
                redis_client.expire(key, 600)  # 10 minute expiry
                return
            except Exception as e:
                logger.warning(f"Redis error registering request: {e}")

        # 2. In-memory fallback
        with _in_memory_lock:
            _in_memory_requests.append(now)
            # Prune records older than 5 minutes (300s)
            cutoff = now - 300
            while _in_memory_requests and _in_memory_requests[0] < cutoff:
                _in_memory_requests.popleft()

    @staticmethod
    def register_error() -> None:
        """
        Record an error for rate calculation. Uses Redis with fallback to in-memory deque.
        """
        now = time.time()

        # 1. Use Redis if available
        if redis_client:
            try:
                bucket = int(now // 60)
                key = f"stats:errors:{bucket}"
                redis_client.incr(key)
                redis_client.expire(key, 600)
                return
            except Exception as e:
                logger.warning(f"Redis error registering error: {e}")

        # 2. In-memory fallback
        with _in_memory_lock:
            _in_memory_errors.append(now)
            cutoff = now - 300
            while _in_memory_errors and _in_memory_errors[0] < cutoff:
                _in_memory_errors.popleft()

    @staticmethod
    def log_error(
        db: Session,
        request: Request,
        exception: Exception,
        request_id: Optional[str] = None
    ) -> ErrorLog:
        """
        Save the error to the database, increment the error counters, and check threshold rates.
        """
        try:
            # Increment error metrics
            ErrorTracker.register_error()

            # Extract exception info
            error_class = exception.__class__.__name__
            error_message = str(exception)
            stack_trace = "".join(traceback.format_exception(type(exception), exception, exception.__traceback__))

            # Extract request details
            route = request.scope.get("route")
            endpoint = getattr(route, "path", None) or "unmatched"
            method = request.method

            # Save to Database
            error_log = ErrorLog(
                request_id=request_id or getattr(request.state, "request_id", None),
                endpoint=endpoint,
                method=method,
                error_class=error_class,
                error_message=error_message,
                stack_trace=stack_trace
            )
            db.add(error_log)
            db.commit()
            db.refresh(error_log)

            # Check threshold and alert if exceeded
            ErrorTracker.evaluate_error_rate()

            return error_log
        except Exception as e:
            logger.error(f"Failed to record error log in database: {e}")
            # Do not raise to prevent breaking the application's fallback response
            return None

    @staticmethod
    def get_metrics_in_window() -> tuple[int, int]:
        """
        Calculate request and error totals in the last 5 minutes.
        Returns: (request_count, error_count)
        """
        now = time.time()
        
        # 1. Use Redis if available
        if redis_client:
            try:
                current_bucket = int(now // 60)
                req_keys = [f"stats:requests:{current_bucket - i}" for i in range(5)]
                err_keys = [f"stats:errors:{current_bucket - i}" for i in range(5)]
                
                req_vals = redis_client.mget(req_keys)
                err_vals = redis_client.mget(err_keys)
                
                total_reqs = sum(int(v) for v in req_vals if v is not None)
                total_errs = sum(int(v) for v in err_vals if v is not None)
                return total_reqs, total_errs
            except Exception as e:
                logger.warning(f"Redis error getting metrics: {e}")

        # 2. In-memory fallback
        with _in_memory_lock:
            cutoff = now - 300
            
            # Prune old records first
            while _in_memory_requests and _in_memory_requests[0] < cutoff:
                _in_memory_requests.popleft()
            while _in_memory_errors and _in_memory_errors[0] < cutoff:
                _in_memory_errors.popleft()
                
            return len(_in_memory_requests), len(_in_memory_errors)

    @staticmethod
    def evaluate_error_rate() -> None:
        """
        Calculate error rate and trigger alert if it exceeds 1% in the 5-minute window.
        """
        req_count, err_count = ErrorTracker.get_metrics_in_window()
        
        # We need a minimum sample size to avoid false alarms (e.g. 1 error out of 1 request)
        # Let's say at least 10 requests in 5 minutes to activate rate-based alerting
        if req_count < 10:
            return

        error_rate = err_count / req_count
        if error_rate > 0.01:
            ErrorTracker.trigger_alert(error_rate, req_count, err_count)

    @staticmethod
    def trigger_alert(error_rate: float, req_count: int, err_count: int) -> None:
        """
        Send Slack alert with a cooldown of 5 minutes (300 seconds).
        """
        global _last_alert_time
        now = time.time()
        
        # Check cooldown in Redis or in-memory
        if redis_client:
            try:
                cooldown = redis_client.get("alert:cooldown")
                if cooldown:
                    return
                # Set cooldown for 5 minutes
                redis_client.set("alert:cooldown", "active", ex=300)
            except Exception as e:
                logger.warning(f"Redis error handling alert cooldown: {e}")
                # Fall back to in-memory cooldown check
                if now - _last_alert_time < 300:
                    return
        else:
            # In-memory cooldown check
            if now - _last_alert_time < 300:
                return

        _last_alert_time = now
        
        message = (
            f"🚨 *CRITICAL ERROR RATE DETECTED* 🚨\n"
            f"*Environment:* Production Ready System\n"
            f"*Error Rate:* {error_rate:.2%}\n"
            f"*Total Requests (5m):* {req_count}\n"
            f"*Total Errors (5m):* {err_count}\n"
            f"Please inspect the system log and `error_logs` database table immediately."
        )

        slack_url = os.environ.get("SLACK_WEBHOOK_URL")
        if slack_url:
            try:
                payload = {"text": message}
                data = json.dumps(payload).encode("utf-8")
                req = urllib.request.Request(
                    slack_url,
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=5) as res:
                    if res.status != 200:
                        logger.warning(f"Slack webhook returned status {res.status}")
            except Exception as se:
                logger.error(f"Failed to send Slack alert: {se}")
        else:
            logger.error(f"SLACK_WEBHOOK_URL not configured. Alert: {message.replace('*', '')}")
