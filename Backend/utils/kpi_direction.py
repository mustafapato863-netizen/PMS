"""Single source of truth for KPI optimisation direction.

Every page that interprets a KPI (Insights, dashboards, scorecards, reports,
exports) resolves ``higher_better`` / ``lower_better`` through
:func:`resolve_kpi_direction` so a stale or defaulted direction stored on a
record is corrected at read time.

Precedence (highest first):

1. ``config``        - the record's own resolved KPI definition (plus the
   documented legacy source variants in ``LEGACY_VARIANT_DIRECTIONS``)
2. ``team_config``   - the same KPI anywhere in the team's file config (all
   levels/positions); merged/logical teams fall back to their source teams via
   ``utils.report_scope._team_keys``; ambiguous matches are ignored
3. ``persisted``     - a valid direction stored on the KPI row
4. ``global_config`` - a single unambiguous key/label match across all team
   configs. Identities configured with different directions in different
   teams (e.g. ``TAT``: Coding lower vs Re-Submission higher; ``Other``:
   Inbound abandon lower vs Outbound reachability higher) are excluded, so
   they only ever resolve by team.
5. ``default``       - ``higher_better``; logged once as a warning and returned
   with ``direction_source == "default"`` so callers can flag it.

Configuration beats the persisted value because older readers wrote
``higher_better`` whenever their exact-key config lookup missed. A valid
persisted value is still preferred over the cross-team (global) match because
it was written from the record's own config at upload time.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from functools import lru_cache
from typing import Any, Iterable

from config.loader import (
    ConfigurationError,
    find_team_config_by_db_name,
    load_all_team_configs,
    load_team_config,
)
from utils.report_scope import _team_keys


logger = logging.getLogger(__name__)

VALID_DIRECTIONS = frozenset({"higher_better", "lower_better"})
DEFAULT_DIRECTION = "higher_better"
DIRECTION_SOURCES = ("config", "team_config", "persisted", "global_config", "default")

_DIRECTION_ALIASES = {
    "higher_better": "higher_better",
    "higher_is_better": "higher_better",
    "higher": "higher_better",
    "high": "higher_better",
    "increase": "higher_better",
    "max": "higher_better",
    "maximize": "higher_better",
    "up": "higher_better",
    "asc": "higher_better",
    "lower_better": "lower_better",
    "lower_is_better": "lower_better",
    "lower": "lower_better",
    "low": "lower_better",
    "decrease": "lower_better",
    "min": "lower_better",
    "minimize": "lower_better",
    "down": "lower_better",
    "desc": "lower_better",
    "inverse": "lower_better",
}


# Documented legacy source variants (docs/KPI_CONFIGURATION_REFERENCE.md,
# Inbound "Legacy source note"): when the source row carries ``A.UTZ%`` the
# legacy evidence builder presents ``Other`` as Utilization, which is
# higher-is-better although the JSON ``Other`` definition is Abandon Rate.
LEGACY_VARIANT_DIRECTIONS: dict[tuple[str, str], str] = {
    ("other", "utilization"): "higher_better",
}

_WARNED_DEFAULTS: set[tuple[str, tuple[str, ...]]] = set()


def _get(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def normalize_direction(value: Any) -> str | None:
    """Map stored direction spellings onto ``higher_better`` / ``lower_better``."""
    if value is None:
        return None
    normalized = "_".join(str(value).strip().casefold().replace("-", " ").split())
    return _DIRECTION_ALIASES.get(normalized)


def _collect_kpi_definitions(node: Any, sink: list[dict[str, Any]]) -> None:
    if isinstance(node, dict):
        for key, child in node.items():
            if key == "kpis" and isinstance(child, list):
                sink.extend(item for item in child if isinstance(item, dict))
            else:
                _collect_kpi_definitions(child, sink)
    elif isinstance(node, list):
        for child in node:
            _collect_kpi_definitions(child, sink)


def _identities(definition: dict[str, Any], *, aliases: bool = False) -> list[str]:
    values = [definition.get("key"), definition.get("label")]
    if aliases:
        values.extend(definition.get("aliases") or [])
    return [str(value).strip().casefold() for value in values if value]


def _direction_index(configs: Iterable[dict[str, Any]]) -> dict[str, str]:
    """Identity (casefolded key/label) -> direction, unambiguous entries only."""
    seen: dict[str, set[str]] = defaultdict(set)
    for config in configs:
        definitions: list[dict[str, Any]] = []
        _collect_kpi_definitions(config, definitions)
        for definition in definitions:
            direction = normalize_direction(definition.get("direction"))
            if not direction:
                continue
            for identity in _identities(definition):
                seen[identity].add(direction)
    return {identity: next(iter(directions)) for identity, directions in seen.items() if len(directions) == 1}


def _load_config(name: str) -> dict[str, Any] | None:
    try:
        return load_team_config(name)
    except ConfigurationError:
        return find_team_config_by_db_name(name)


@lru_cache(maxsize=128)
def team_direction_index(team: str) -> dict[str, str]:
    """Every KPI direction configured for a team, across all levels/positions."""
    configs: list[dict[str, Any]] = []
    for name in [team, *sorted(_team_keys(team))]:
        if not name:
            continue
        config = _load_config(name)
        if config and config not in configs:
            configs.append(config)
    return _direction_index(configs)


@lru_cache(maxsize=1)
def global_direction_index() -> dict[str, str]:
    try:
        return _direction_index(load_all_team_configs())
    except ConfigurationError:
        return {}


def clear_kpi_direction_cache() -> None:
    team_direction_index.cache_clear()
    global_direction_index.cache_clear()
    _WARNED_DEFAULTS.clear()


def _warn_default(team: Any, identities: list[str]) -> None:
    marker = (str(team or ""), tuple(identities))
    if marker in _WARNED_DEFAULTS:
        return
    _WARNED_DEFAULTS.add(marker)
    logger.warning(
        "KPI direction unresolved for team=%r kpi=%r; defaulting to %s (direction_source=default)",
        team,
        identities[0] if identities else None,
        DEFAULT_DIRECTION,
    )


def find_kpi_definition(config: dict[str, Any] | None, key: Any = None, label: Any = None) -> dict[str, Any] | None:
    """Find a KPI definition in a resolved config by key, then key/label/alias (casefolded)."""
    kpis = [kpi for kpi in ((config or {}).get("kpis") or []) if isinstance(kpi, dict)]
    if not kpis:
        return None
    if key is not None:
        exact = next((kpi for kpi in kpis if str(kpi.get("key")) == str(key)), None)
        if exact is not None:
            return exact
    wanted = [str(value).strip().casefold() for value in (key, label) if value]
    for identity in wanted:
        match = next((kpi for kpi in kpis if identity in _identities(kpi, aliases=True)), None)
        if match is not None:
            return match
    return None


def resolve_kpi_direction(
    team: Any,
    value: Any,
    definition: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Return ``(direction, source)`` for one KPI row (see module docstring)."""
    variant_key = str(_get(value, "kpi_key") or _get(value, "key") or "").strip().casefold()
    variant_label = str(_get(value, "label") or "").strip().casefold()
    variant = LEGACY_VARIANT_DIRECTIONS.get((variant_key, variant_label))
    if variant:
        return variant, "config"
    configured = normalize_direction((definition or {}).get("direction"))
    if configured:
        return configured, "config"
    identities = [
        str(identity).strip().casefold()
        for identity in (_get(value, "kpi_key"), _get(value, "label"), _get(value, "key"))
        if identity
    ]
    team_index = team_direction_index(str(team or ""))
    for identity in identities:
        if identity in team_index:
            return team_index[identity], "team_config"
    persisted = normalize_direction(_get(value, "direction"))
    if persisted:
        return persisted, "persisted"
    global_index = global_direction_index()
    for identity in identities:
        if identity in global_index:
            return global_index[identity], "global_config"
    _warn_default(team, identities)
    return DEFAULT_DIRECTION, "default"


def kpi_direction(team: Any, value: Any, definition: dict[str, Any] | None = None) -> str:
    """Convenience wrapper returning only the resolved direction."""
    return resolve_kpi_direction(team, value, definition)[0]


def apply_kpi_direction(item: dict[str, Any], team: Any, definition: dict[str, Any] | None = None) -> dict[str, Any]:
    """Set ``direction`` and ``direction_source`` on a KPI row dict in place."""
    direction, source = resolve_kpi_direction(team, item, definition)
    item["direction"] = direction
    item["direction_source"] = source
    return item


def target_ratio_achievement(actual: Any, target: Any, direction: str | None) -> float | None:
    """Uncapped target-ratio achievement for ``direction`` (None when not computable)."""
    try:
        actual_value = float(actual)
        target_value = float(target)
    except (TypeError, ValueError):
        return None
    if target_value != target_value or actual_value != actual_value or target_value <= 0:
        return None
    if direction == "lower_better":
        return target_value / actual_value if actual_value > 0 else 1.0
    return max(actual_value / target_value, 0.0)


def opposite_direction(direction: str) -> str:
    return "higher_better" if direction == "lower_better" else "lower_better"


# Contributions are persisted with 4 decimal places; allow for that rounding.
FLIP_TOLERANCE = 0.0005


def flipped_contribution_fix(
    actual: Any,
    target: Any,
    weight: float,
    contribution: float,
    resolved_direction: str,
    persisted_direction: Any,
    *,
    tolerance: float = FLIP_TOLERANCE,
) -> float | None:
    """Corrected contribution when a KPI was saved under the opposite direction.

    Returns ``None`` unless there is positive evidence of a flip: the row was
    persisted with a valid direction that disagrees with the resolved one, and
    the stored contribution equals the opposite-direction score (not the
    correct one). Exception-driven contributions (full credit, zero weight)
    therefore never change. Applying the fix twice is a no-op. ``weight`` and
    ``contribution`` share one scale (0-1 or 0-100); scale ``tolerance`` with it.
    """
    persisted = normalize_direction(persisted_direction)
    if not persisted or persisted == resolved_direction or weight <= 0:
        return None
    correct = target_ratio_achievement(actual, target, resolved_direction)
    opposite = target_ratio_achievement(actual, target, persisted)
    if correct is None or opposite is None:
        return None
    correct_contribution = min(max(correct, 0.0), 1.0) * weight
    opposite_contribution = min(max(opposite, 0.0), 1.0) * weight
    if abs(correct_contribution - opposite_contribution) <= tolerance:
        return None
    if abs(contribution - opposite_contribution) > tolerance:
        return None
    return correct_contribution
