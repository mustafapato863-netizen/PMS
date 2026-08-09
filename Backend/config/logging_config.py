"""Structured Logging Configuration
Configures JSON formatting for rotating files and console outputs,
leveraging contextvars to track request IDs automatically.
"""

import os
import sys
import json
import logging
import time
import contextvars
from logging.handlers import TimedRotatingFileHandler

# Central request ID tracking context variable
request_id_ctx = contextvars.ContextVar("request_id", default=None)


class RequestIDFilter(logging.Filter):
    """Injects the current request_id context variable into logging records"""

    def filter(self, record):
        record.request_id = request_id_ctx.get()
        return True


class JSONFormatter(logging.Formatter):
    """Formats log records as structured JSON strings"""

    def format(self, record):
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None)
        }
        for field in (
            "method",
            "path",
            "status_code",
            "duration_ms",
            "response_bytes",
        ):
            value = getattr(record, field, None)
            if value is not None:
                log_entry[field] = value
        
        # Capture error/exception trace if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
            
        return json.dumps(log_entry)


def setup_logging():
    """Initialize structured logging across the application"""
    # Serverless function bundles are read-only. Vercel captures stdout, so a
    # rotating file handler is unnecessary there and would crash imports.
    file_logging_enabled = os.getenv(
        "ENABLE_FILE_LOGGING",
        "false" if os.getenv("VERCEL") else "true",
    ).strip().lower() == "true"

    # Get root logger
    root_logger = logging.getLogger()
    # Remove existing handlers to prevent duplicate logs
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # Configure log level from environment
    log_level_str = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_str, logging.INFO)
    root_logger.setLevel(log_level)

    # 1. Console Handler (for readable stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s] [ReqID: %(request_id)s] %(message)s"
    )
    console_handler.setFormatter(console_formatter)
    console_handler.addFilter(RequestIDFilter())
    root_logger.addHandler(console_handler)

    if file_logging_enabled:
        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        logs_dir = os.path.join(backend_dir, "logs")
        os.makedirs(logs_dir, exist_ok=True)
        log_filepath = os.path.join(logs_dir, "pms_app.log")
        file_handler = TimedRotatingFileHandler(
            log_filepath,
            when="D",
            interval=1,
            backupCount=30,
            encoding="utf-8"
        )
        file_handler.setLevel(log_level)
        file_formatter = JSONFormatter()
        file_handler.setFormatter(file_formatter)
        file_handler.addFilter(RequestIDFilter())
        root_logger.addHandler(file_handler)
        logging.info("Structured logging initialized. File: %s", log_filepath)
    else:
        logging.info("Structured console logging initialized.")
