"""Tracking-only indicators declared by a team configuration.

One rule for every Insights builder: a declared tracking indicator is never a
scored KPI. Its stored row (weight 0) stays on the record for evidence, but no
score list, count, driver, trend or on-track status may use it.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from config.loader import ConfigurationError, find_team_config_by_db_name, load_team_config, resolve_team_config


@lru_cache(maxsize=64)
def _resolved_config(team: str) -> dict[str, Any] | None:
    try:
        try:
            base = load_team_config(team)
        except ConfigurationError:
            base = find_team_config_by_db_name(team)
            if not base:
                return None
        return resolve_team_config(base, "Employee", None)
    except ConfigurationError:
        return None


def tracking_definitions(team: str) -> list[dict[str, Any]]:
    """The team's tracking indicator definitions, in configuration order. Empty when it declares none."""
    config = _resolved_config(str(team or ""))
    if not config:
        return []
    return [
        dict(item)
        for item in config.get("tracking_indicators") or []
        if isinstance(item, dict) and item.get("key")
    ]


def tracking_indicator_keys(team: str) -> frozenset[str]:
    """Keys a builder must never score for this team."""
    return frozenset(str(item["key"]) for item in tracking_definitions(team))
