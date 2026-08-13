"""
Team configuration loader.
Discovers and loads team configurations from /config/teams/*.json files.
Validates configurations for correctness and consistency.
"""

import json
import logging
from copy import deepcopy
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple
from utils.performance_levels import PERFORMANCE_LEVELS, normalize_performance_level

logger = logging.getLogger(__name__)

PERSPECTIVES = ("Financial", "Customer", "Internal Process", "Learning & Growth")
ROLLUPS = {"average", "sum", "latest"}
TEAM_AGGREGATIONS = {"average", "sum", "ratio", "weighted_average"}
GLOBAL_KPI_ACHIEVEMENT_CAP = 1.0


class ConfigurationError(Exception):
    """Base exception for configuration errors."""
    pass


class WeightValidationError(ConfigurationError):
    """Exception raised when KPI weights don't sum to 1.0."""
    pass


class ThresholdValidationError(ConfigurationError):
    """Exception raised when grade thresholds are not in descending order."""
    pass


def _apply_global_kpi_cap(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize every loaded KPI definition to the product-wide score rule.

    The workbook-era configuration files historically allowed individual teams
    to opt into ``uncapped`` achievement.  That made the same KPI render and
    score differently depending on the route that consumed it.  The product
    rule is now global: an achievement ratio is never greater than 1.0 (100%),
    and the weighted score is never greater than 100%.  Normalize in memory as
    a safety net for old files, uploaded configurations, and cached versions;
    the checked-in JSON files are updated separately for transparency.
    """
    normalized = deepcopy(config)

    def normalize_kpis(container: Dict[str, Any]) -> None:
        kpis = container.get("kpis")
        if not isinstance(kpis, list):
            return
        container["capping"] = "capped_at_100"
        for kpi in kpis:
            if isinstance(kpi, dict):
                kpi["cap_achievement"] = True

    normalize_kpis(normalized)
    for level_config in normalized.get("performance_levels", {}).values():
        if not isinstance(level_config, dict):
            continue
        normalize_kpis(level_config)
        positions = level_config.get("positions", {})
        if isinstance(positions, dict):
            for position_config in positions.values():
                if isinstance(position_config, dict):
                    normalize_kpis(position_config)
                    for variant in position_config.get("period_variants", []):
                        if isinstance(variant, dict):
                            normalize_kpis(variant)

    # A top-level flag keeps the final-score rule explicit even for teams whose
    # KPI list only exists under performance_levels.
    if normalized.get("kpis") or normalized.get("performance_levels"):
        normalized["capping"] = "capped_at_100"
    return normalized


def _validate_weights(kpis: List[Dict[str, Any]], context: str = "configuration") -> Tuple[bool, List[str]]:
    """
    Validate that KPI weights sum to 1.0 within 0.001 tolerance.
    
    Args:
        kpis: List of KPI definitions from config
        
    Returns:
        Tuple of (is_valid, [error_messages])
    """
    errors = []
    
    if not kpis:
        errors.append("No KPIs defined in configuration")
        return False, errors
    
    total_weight = sum(float(kpi.get('weight', 0)) for kpi in kpis)
    if total_weight > 1.001 or total_weight < 0.999:
        errors.append(
            f"KPI weights for {context} sum to {total_weight:.4f}; must sum to 1.0"
        )
        return False, errors
    
    return True, errors


def _validate_thresholds(thresholds: Dict[str, int]) -> Tuple[bool, List[str]]:
    """
    Validate that grade thresholds are in descending order (A > B > C > D).
    
    Args:
        thresholds: Grade threshold dictionary
        
    Returns:
        Tuple of (is_valid, [error_messages])
    """
    errors = []
    required_grades = ['A', 'B', 'C', 'D']
    
    # Check all required grades present
    for grade in required_grades:
        if grade not in thresholds:
            errors.append(f"Missing grade threshold for '{grade}'")
    
    if errors:
        return False, errors
    
    # Check descending order
    grades_and_values = [(grade, thresholds[grade]) for grade in required_grades]
    for i in range(len(grades_and_values) - 1):
        current_grade, current_value = grades_and_values[i]
        next_grade, next_value = grades_and_values[i + 1]
        
        if current_value <= next_value:
            errors.append(
                f"Grade thresholds not in descending order: "
                f"{current_grade}({current_value}) should be > {next_grade}({next_value})"
            )
    
    return len(errors) == 0, errors


def _validate_required_fields(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate that all required fields are present in configuration.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Tuple of (is_valid, [error_messages])
    """
    errors = []
    required_top_level = ['team', 'db_name', 'region', 'employee_id_col', 'employee_name_col', 'grade_thresholds']
    
    for field in required_top_level:
        if field not in config:
            errors.append(f"Missing required field: '{field}'")
    
    if 'kpis' not in config and 'performance_levels' not in config:
        errors.append("Missing required field: 'kpis' or 'performance_levels'")

    required_kpi_fields = ['key', 'label', 'weight', 'direction', 'unit', 'color', 'actual_col', 'target_col']
    groups = [("Employee", config.get('kpis', []), False)]
    for level, value in config.get('performance_levels', {}).items():
        groups.append((level, value.get('kpis', []), False))
        for position_name, position_config in value.get("positions", {}).items():
            groups.append((f"{level}/{position_name}", position_config.get("kpis", []), True))
            for variant_index, variant in enumerate(position_config.get("period_variants", []), start=1):
                if not isinstance(variant, dict):
                    errors.append(
                        f"{level}/{position_name} period variant {variant_index} must be an object"
                    )
                    continue
                if not variant.get("id"):
                    errors.append(
                        f"{level}/{position_name} period variant {variant_index} is missing field 'id'"
                    )
                if not variant.get("effective_from"):
                    errors.append(
                        f"{level}/{position_name} period variant {variant_index} is missing field 'effective_from'"
                    )
                groups.append(
                    (
                        f"{level}/{position_name}/period_variants[{variant_index}]",
                        variant.get("kpis", []),
                        True,
                    )
                )

    for level, kpis, position_scoped in groups:
        for idx, kpi in enumerate(kpis):
            for field in required_kpi_fields:
                if field not in kpi:
                    errors.append(f"{level} KPI {idx} ({kpi.get('key', 'unknown')}): missing field '{field}'")
            if position_scoped and "perspective" not in kpi:
                errors.append(f"{level} KPI {idx} ({kpi.get('key', 'unknown')}): missing field 'perspective'")
            aggregation = kpi.get("aggregation")
            if aggregation is not None:
                method = aggregation.get("method")
                if method not in TEAM_AGGREGATIONS:
                    errors.append(f"{level} KPI {idx} ({kpi.get('key', 'unknown')}): invalid aggregation method")
                if method == "ratio" and not all(aggregation.get(field) for field in ("numerator_col", "denominator_col")):
                    errors.append(f"{level} KPI {idx} ({kpi.get('key', 'unknown')}): ratio aggregation requires numerator_col and denominator_col")
                if method == "weighted_average" and not aggregation.get("weight_col"):
                    errors.append(f"{level} KPI {idx} ({kpi.get('key', 'unknown')}): weighted_average aggregation requires weight_col")
    
    return len(errors) == 0, errors


def _validate_balanced_scorecard(level: str, level_config: Dict[str, Any]) -> List[str]:
    bsc = level_config.get("balanced_scorecard")
    if not bsc or not bsc.get("enabled"):
        return []
    errors = []
    if level not in {"Managerial", "Corporate"}:
        return [f"Balanced Scorecard is not supported for {level}"]

    perspectives = bsc.get("perspectives", [])
    keys = [item.get("key") for item in perspectives]
    if len(keys) != len(set(keys)):
        errors.append(f"{level} Balanced Scorecard perspective keys must be unique")
    unknown = sorted(set(keys) - set(PERSPECTIVES))
    if unknown:
        errors.append(f"{level} has invalid perspectives: {', '.join(unknown)}")
    missing = [key for key in PERSPECTIVES if key not in keys]
    if missing:
        errors.append(f"{level} is missing perspectives: {', '.join(missing)}")

    configured = set(keys)
    for link in bsc.get("strategy_map_links", []):
        if link.get("from") not in configured or link.get("to") not in configured:
            errors.append(f"{level} strategy map link references an unknown perspective")

    for kpi in level_config.get("kpis", []):
        key = kpi.get("key", "unknown")
        if kpi.get("perspective") not in configured:
            errors.append(f"{level} KPI {key}: missing or invalid perspective")
        if kpi.get("rollup", "average") not in ROLLUPS:
            errors.append(f"{level} KPI {key}: invalid rollup")
    return errors


def validate_team_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validate a team configuration for correctness and consistency.
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Tuple of (is_valid, [error_messages])
    """
    all_errors = []
    
    # Check required fields
    is_valid, errors = _validate_required_fields(config)
    all_errors.extend(errors)
    
    if not is_valid:
        # Can't continue validation without required fields
        return False, all_errors
    
    if 'kpis' in config:
        _, errors = _validate_weights(config['kpis'], "Employee")
        all_errors.extend(errors)

    for raw_level, level_config in config.get('performance_levels', {}).items():
        try:
            level = normalize_performance_level(raw_level)
        except ValueError as exc:
            all_errors.append(str(exc))
            continue
        kpis = level_config.get('kpis', [])
        positions = level_config.get("positions", {})
        if kpis:
            _, errors = _validate_weights(kpis, level)
            all_errors.extend(errors)
        elif not positions:
            all_errors.append(f"No KPIs defined for {level}")

        seen_position_keys: set[str] = set()
        for position_name, position_config in positions.items():
            position_kpis = position_config.get("kpis", [])
            _, errors = _validate_weights(position_kpis, f"{level}/{position_name}")
            all_errors.extend(errors)
            keys = [str(kpi.get("key", "")).strip() for kpi in position_kpis]
            if len(keys) != len(set(keys)):
                all_errors.append(f"{level}/{position_name} KPI keys must be unique")
            duplicates = sorted(set(keys) & seen_position_keys)
            if duplicates:
                all_errors.append(
                    f"{level} KPI keys are repeated across positions: {', '.join(duplicates)}"
                )
            seen_position_keys.update(keys)
            position_sets = [("default", position_kpis)]
            for variant_index, variant in enumerate(position_config.get("period_variants", []), start=1):
                if isinstance(variant, dict):
                    variant_kpis = variant.get("kpis", [])
                    position_sets.append((f"period_variants[{variant_index}]", variant_kpis))
                    _, errors = _validate_weights(
                        variant_kpis,
                        f"{level}/{position_name}/{variant.get('id', variant_index)}",
                    )
                    all_errors.extend(errors)
                    variant_keys = [str(kpi.get("key", "")).strip() for kpi in variant_kpis]
                    if len(variant_keys) != len(set(variant_keys)):
                        all_errors.append(
                            f"{level}/{position_name}/{variant.get('id', variant_index)} KPI keys must be unique"
                        )
            for set_name, kpis in position_sets:
                for kpi in kpis:
                    if kpi.get("perspective") not in PERSPECTIVES:
                        all_errors.append(
                            f"{level}/{position_name}/{set_name} KPI {kpi.get('key', 'unknown')}: "
                            "missing or invalid perspective"
                        )
        all_errors.extend(_validate_balanced_scorecard(level, level_config))
    
    # Validate grade thresholds
    is_valid, errors = _validate_thresholds(config.get('grade_thresholds', {}))
    all_errors.extend(errors)

    for position_name, display_order, kpi in iter_employee_kpi_configs(config):
        if kpi.get("aggregation") is None:
            scope = f"Employee/{position_name}" if position_name else "Employee"
            all_errors.append(
                f"{scope} KPI {display_order} ({kpi.get('key', 'unknown')}): "
                "missing field 'aggregation'"
            )
    
    return len(all_errors) == 0, all_errors


def resolve_team_config(
    config: Dict[str, Any],
    performance_level: str = "Employee",
    position_name: str | None = None,
) -> Dict[str, Any]:
    """Return one level/position KPI config while preserving legacy flat Employee KPIs."""
    level = normalize_performance_level(performance_level)
    resolved = deepcopy(config)
    level_config = config.get("performance_levels", {}).get(level)
    if level_config:
        resolved.update(level_config)
    elif level != "Employee":
        raise ConfigurationError(f"No {level} KPI configuration for team {config.get('team', 'unknown')}")
    positions = resolved.get("positions", {})
    if positions:
        resolved["available_positions"] = list(positions)
        if position_name is None:
            resolved["kpis"] = []
        else:
            normalized_position = str(position_name).strip().casefold()
            matched_name = next(
                (name for name in positions if str(name).strip().casefold() == normalized_position),
                None,
            )
            if matched_name is None:
                raise ConfigurationError(
                    f"No {level} KPI configuration for position {position_name!r} "
                    f"in team {config.get('team', 'unknown')}"
                )
            resolved.update(deepcopy(positions[matched_name]))
            resolved["position_name"] = matched_name
    elif position_name is not None:
        resolved["position_name"] = str(position_name).strip()
    resolved["performance_level"] = level
    return resolved


def resolve_position_config(
    config: Dict[str, Any],
    performance_level: str,
    position_name: str,
) -> Dict[str, Any]:
    """Resolve a position-scoped KPI definition and require that it contains KPIs."""
    resolved = resolve_team_config(config, performance_level, position_name)
    if not resolved.get("kpis"):
        raise ConfigurationError(
            f"No {resolved['performance_level']} KPIs configured for position {position_name!r}"
        )
    return resolved


def get_configured_performance_levels(config: Dict[str, Any]) -> List[str]:
    levels = {"Employee"} if config.get("kpis") else set()
    for raw_level, level_config in config.get("performance_levels", {}).items():
        if level_config.get("kpis") or level_config.get("positions"):
            levels.add(normalize_performance_level(raw_level))
    return [level for level in PERFORMANCE_LEVELS if level in levels]


def iter_employee_kpi_configs(
    config: Dict[str, Any],
) -> Iterator[Tuple[str, int, Dict[str, Any]]]:
    """Yield ``(position_name, display_order, kpi)`` for employee-domain KPI rows."""
    level_config = config.get("performance_levels", {}).get("Employee")
    if level_config:
        for display_order, kpi in enumerate(level_config.get("kpis", [])):
            yield "", display_order, kpi
        for position_name, position_config in level_config.get("positions", {}).items():
            for display_order, kpi in enumerate(position_config.get("kpis", [])):
                yield str(position_name), display_order, kpi
        return

    for display_order, kpi in enumerate(config.get("kpis", [])):
        yield "", display_order, kpi


@lru_cache(maxsize=128)
def _load_validated_config_cached(
    config_path_value: str,
    mtime_ns: int,
    file_size: int,
) -> Dict[str, Any]:
    """Parse and validate one immutable config-file version."""
    del mtime_ns, file_size  # The values intentionally participate in the cache key.
    config_path = Path(config_path_value)
    try:
        with config_path.open("r", encoding="utf-8") as config_file:
            config = json.load(config_file)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON in {config_path}: {exc}") from exc
    except OSError as exc:
        raise ConfigurationError(f"Failed to read {config_path}: {exc}") from exc

    is_valid, errors = validate_team_config(config)
    if not is_valid:
        weight_errors = [error for error in errors if "weight" in error.lower()]
        threshold_errors = [
            error
            for error in errors
            if "threshold" in error.lower() or "grade" in error.lower()
        ]
        other_errors = [
            error
            for error in errors
            if error not in weight_errors and error not in threshold_errors
        ]
        team_name = str(config.get("team") or config_path.stem)
        if weight_errors:
            raise WeightValidationError(
                f"Weight validation failed for {team_name}:\n" + "\n".join(weight_errors)
            )
        if threshold_errors:
            raise ThresholdValidationError(
                f"Threshold validation failed for {team_name}:\n" + "\n".join(threshold_errors)
            )
        raise ConfigurationError(
            f"Configuration validation failed for {team_name}:\n" + "\n".join(other_errors)
        )

    config = _apply_global_kpi_cap(config)
    logger.info("Loaded and validated configuration file with global KPI cap: %s", config_path.name)
    return config


def _load_config_file(config_path: Path) -> Dict[str, Any]:
    stat = config_path.stat()
    return deepcopy(
        _load_validated_config_cached(
            str(config_path.resolve()),
            stat.st_mtime_ns,
            stat.st_size,
        )
    )


def clear_configuration_cache() -> None:
    """Clear parsed configuration entries after controlled in-process writes."""
    _load_validated_config_cached.cache_clear()


def load_team_config(team_name: str) -> Dict[str, Any]:
    """
    Load a single team configuration by name.
    
    Validates the configuration and raises appropriate exceptions if validation fails.
    
    Args:
        team_name: Name of the team (e.g., "Pharmacy", "Coding", "CSR")
        
    Returns:
        Dict containing validated team config
        
    Raises:
        ConfigurationError: If config file not found or invalid
        WeightValidationError: If weights don't sum to 1.0
        ThresholdValidationError: If thresholds are invalid
    """
    config_dir = Path(__file__).parent / "teams"
    
    # Normalize team name to filename (snake_case) and tolerate hyphenated names.
    filename = team_name.lower().replace(" ", "_").replace("-", "_") + ".json"
    config_path = config_dir / filename
    
    if not config_path.exists():
        for cfg_file in sorted(config_dir.glob("*.json")):
            try:
                with cfg_file.open("r", encoding="utf-8") as f:
                    cfg = json.load(f)
                if cfg.get("team", "").casefold() == team_name.casefold() or cfg.get("db_name", "").casefold() == team_name.casefold():
                    config_path = cfg_file
                    break
            except Exception:
                continue
        if not config_path.exists():
            raise ConfigurationError(f"Team configuration not found: {config_path}")

    return _load_config_file(config_path)


def load_all_team_configs() -> List[Dict[str, Any]]:
    """
    Load all team configurations from the /config/teams/ directory.
    
    Returns:
        List of validated team config dictionaries
        
    Raises:
        ConfigurationError: If config directory doesn't exist or configs are invalid
    """
    config_dir = Path(__file__).parent / "teams"
    
    if not config_dir.exists():
        raise ConfigurationError(f"Config directory not found: {config_dir}")
    
    configs = []
    json_files = sorted(config_dir.glob("*.json"))
    
    if not json_files:
        logger.warning(f"No team configs found in {config_dir}")
        return configs
    
    for config_file in json_files:
        try:
            configs.append(_load_config_file(config_file))
        except ConfigurationError as e:
            logger.error(f"Failed to load config from {config_file.name}: {e}")
            continue
    
    return configs


def get_team_names() -> List[str]:
    """
    Get list of all available team names.
    
    Returns:
        List of team names (as they appear in the config files)
    """
    configs = load_all_team_configs()
    return [config['team'] for config in configs]


def find_team_config_by_db_name(db_name: str) -> Optional[Dict[str, Any]]:
    """
    Find a team config by database name.
    Useful when you have the database name but need to find the team config.
    
    Args:
        db_name: Database name (e.g., "Pharmacy", "Coding", "CSR")
        
    Returns:
        Team config dict, or None if not found
    """
    configs = load_all_team_configs()
    for config in configs:
        if config.get('db_name') == db_name:
            return config
    return None
