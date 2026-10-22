"""Pytest configuration for PMS Backend test suite.

Ensures that default test environment variables are set before any test
modules are imported, preventing collection errors and ensuring isolation.
"""

from __future__ import annotations

import os

# Safe anonymous test defaults (matches CI environment)
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "")
os.environ.setdefault("JWT_SECRET", "ci-only-anonymous-test-secret-never-production")
os.environ.setdefault("PMS_AUTO_SEED", "false")
os.environ.setdefault("PMS_SEED_DEMO_LEVELS", "false")
os.environ.setdefault("PMS_SEED_PERMISSIONS_ON_STARTUP", "false")
