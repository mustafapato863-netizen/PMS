"""Optional pool settings: env overrides, defaults and invalid values."""
import pytest

from config import database


@pytest.mark.parametrize(("raw", "expected"), [(None, 7), ("", 7), ("12", 12), ("abc", 7), ("-3", 7)])
def test_int_setting(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("PMS_TEST_POOL_SETTING", raising=False)
    else:
        monkeypatch.setenv("PMS_TEST_POOL_SETTING", raw)
    assert database._int_setting("PMS_TEST_POOL_SETTING", 7, minimum=0) == expected


@pytest.mark.parametrize(("raw", "expected"), [(None, True), ("false", False), ("0", False), ("yes", True)])
def test_bool_setting(monkeypatch, raw, expected):
    if raw is None:
        monkeypatch.delenv("PMS_TEST_POOL_FLAG", raising=False)
    else:
        monkeypatch.setenv("PMS_TEST_POOL_FLAG", raw)
    assert database._bool_setting("PMS_TEST_POOL_FLAG", True) is expected


def test_engine_pre_pings():
    assert database.engine_kwargs["pool_pre_ping"] is True
    assert database.pool_timeout >= 1
