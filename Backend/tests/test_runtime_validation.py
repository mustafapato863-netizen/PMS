import logging
import os

import pytest

from config.environment import load_project_environment
from config.runtime_validation import (
    DEVELOPMENT_JWT_FALLBACK,
    RuntimeConfigurationError,
    resolve_database_url,
    resolve_jwt_secret,
    validate_seed_settings,
)


def test_development_defaults_remain_available():
    assert resolve_jwt_secret(None, "development") == DEVELOPMENT_JWT_FALLBACK
    assert resolve_database_url(None, "test", logger=logging.getLogger(__name__)).startswith(
        "sqlite:///"
    )


@pytest.mark.parametrize("secret", [None, "", "short", "<replace-with-a-32-byte-random-secret>"])
def test_production_rejects_missing_or_placeholder_jwt_secret(secret):
    with pytest.raises(RuntimeConfigurationError, match="JWT_SECRET"):
        resolve_jwt_secret(secret, "production")


def test_production_accepts_strong_jwt_secret():
    secret = "9f5d866f2e4c4f5f82a45389293aecfd"
    assert resolve_jwt_secret(secret, "production") == secret


@pytest.mark.parametrize("database_url", [None, "", "sqlite:///./pms.db"])
def test_production_requires_postgresql(database_url):
    with pytest.raises(RuntimeConfigurationError, match="DATABASE_URL"):
        resolve_database_url(database_url, "production")


def test_production_accepts_postgresql_url():
    url = "postgresql://user:password@db.example.test:5432/pms"
    assert resolve_database_url(url, "production") == url


def test_production_rejects_any_automatic_seed_flag():
    with pytest.raises(RuntimeConfigurationError, match="PMS_SEED_DEMO_LEVELS"):
        validate_seed_settings(
            "production",
            {
                "PMS_AUTO_SEED": False,
                "PMS_SEED_PERMISSIONS_ON_STARTUP": False,
                "PMS_SEED_DEMO_LEVELS": True,
            },
        )


def test_non_production_allows_explicit_seed_flags():
    validate_seed_settings("development", {"PMS_AUTO_SEED": True})


def test_process_environment_wins_over_dotenv_files(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("DATABASE_URL", "postgresql://external.example.test/pms")

    load_project_environment(os.path.dirname(os.path.dirname(__file__)))

    assert os.environ["APP_ENV"] == "staging"
    assert os.environ["DATABASE_URL"] == "postgresql://external.example.test/pms"
