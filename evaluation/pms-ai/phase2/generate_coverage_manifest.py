#!/usr/bin/env python3
"""Repeatable Phase 2 PMS coverage manifest.

Reads repository catalog and configuration only. It does not open a network
connection and does not read a database unless ``--read-db`` is passed.
Outputs contain aggregate structure only: no employee names, identifiers,
emails, or individual scores.

Nothing in this manifest is marked verified. Verified requires a source-parity
check and a permission check that both exist and pass for that cell. This
generator does not execute permission checks and does not read
``performance_records`` rows by default.

Usage (from the repository root):

    python evaluation/pms-ai/phase2/generate_coverage_manifest.py
"""

from __future__ import annotations

import argparse
import ast
import csv
import hashlib
import json
import re
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any


MANIFEST_VERSION = "2.0.0"
BASELINE_COMMIT = "fabbb3d461c044bd367e6cc38a9c514fcfe300d2"
PHASE = "phase-2"

OPERATIONS = (
    "score",
    "actual/target",
    "ranking",
    "trend",
    "comparison",
    "follow-up",
    "navigation",
)

STATUSES = (
    "verified",
    "verified no data",
    "partial",
    "blocked",
    "not applicable",
    "unknown",
)

KPI_VALUE_KEY_MAX = 50
MANAGEMENT_KPI_KEY_MAX = 100
WEIGHT_TOLERANCE = Decimal("0.001")

# Volume fields on the employee record contract. They are not scored KPI keys.
RECORD_VOLUME_MEASURES = (
    {
        "key": "AbandonedCalls",
        "label": "Abandoned calls (count)",
        "teams": ("Inbound",),
        "unit": "count",
        "direction": "lower_better",
        "sources": (
            "Frontend/src/types.ts#AgentRecord.calls.abandoned",
            "Backend/services/ai/catalog.py#inbound:abandoned_calls_count",
        ),
        "note": (
            "Count of abandoned calls. Distinct from Inbound KPI Other "
            "(Abandon Rate), which is weighted and does count toward the score."
        ),
    },
    {
        "key": "AHT",
        "label": "AHT (Outbound, tracking only)",
        "teams": ("Outbound",),
        "unit": "min",
        "direction": "lower_better",
        "sources": ("Backend/services/outbound_period_basis.py#AHT_KEY",),
        "note": (
            "outbound_period_basis keeps AHT at weight 0 and out of scored lines. "
            "Outbound team JSON has no AHT KPI. Inbound AHT is a separate scored KPI."
        ),
    },
    {
        "key": "TotalBookings",
        "label": "Bookings (count)",
        "teams": ("Inbound", "Outbound"),
        "unit": "count",
        "direction": "higher_better",
        "sources": (
            "Frontend/src/types.ts#AgentRecord.geo.bookings",
            "Backend/services/ai/catalog.py#bookings_count",
        ),
        "note": "Booking count. Distinct from Booking Rate, which is the scored KPI.",
    },
    {
        "key": "HandledCalls",
        "label": "Handled calls (count)",
        "teams": ("Inbound", "Outbound"),
        "unit": "count",
        "direction": "higher_better",
        "sources": (
            "Frontend/src/types.ts#AgentRecord.calls.total_handled",
            "Backend/services/ai/catalog.py#handled_calls_count",
        ),
        "note": "Call volume. Not a weighted score KPI.",
    },
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def rel(path: Path) -> str:
    root = repo_root()
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def literal_assignment(path: Path, name: str) -> Any:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        value = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
            value = node.value
        if value is None:
            continue
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                if (
                    isinstance(value, ast.Call)
                    and isinstance(value.func, ast.Name)
                    and value.func.id == "frozenset"
                    and len(value.args) == 1
                ):
                    return frozenset(ast.literal_eval(value.args[0]))
                return ast.literal_eval(value)
    raise KeyError(f"{name} not found as a literal in {path}")


def quantize_number(value: Any) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        try:
            value = float(value)
        except ValueError:
            return None
    if not isinstance(value, (int, float)):
        return None
    quantized = Decimal(str(value)).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    if quantized == quantized.to_integral():
        return int(quantized)
    return float(quantized)


def sanitize(value: Any) -> Any:
    if isinstance(value, float):
        return quantize_number(value)
    if isinstance(value, dict):
        return {str(key): sanitize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(item) for item in value]
    return value


def norm_alias(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def alnum_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", norm_alias(value))


def function_lookup():
    """Load function membership without importing Backend.utils (that package imports pandas)."""
    source = (repo_root() / "Backend" / "utils" / "report_scope.py").read_text(encoding="utf-8")
    start = source.index("_MERGED_TEAM_KEYS")
    end = source.index("def _exact_team_keys")
    tail_start = source.index("_FUNCTION_CALL_CENTER_KEYS")
    tail_end = source.index("def functions_for_team")
    namespace: dict[str, Any] = {}
    exec(source[start:end] + "\n" + source[tail_start:tail_end], namespace)  # noqa: S102 - repository set literals only
    keys = namespace["_FUNCTION_TEAM_KEYS"]

    def functions_for_team(team_name: str) -> list[str]:
        normalized = str(team_name or "").strip()
        if not normalized:
            return []
        key = normalized.casefold()
        if key in {"support positions", "call center support positions"}:
            return ["Call Center"]
        parents = [function for function, members in keys.items() if key in members]
        return parents or [normalized]

    def function_for_team(team_name: str) -> str | None:
        functions = functions_for_team(team_name)
        return functions[0] if functions else None

    return function_for_team, functions_for_team


def sha256_files(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths, key=lambda item: rel(item)):
        digest.update(rel(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def brace_block(source: str, start: int) -> str:
    depth = 0
    begun = False
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
            begun = True
        elif char == "}":
            depth -= 1
            if begun and depth == 0:
                return source[start : index + 1]
    raise ValueError("unbalanced brace")


def extract_ts_const_strings(source: str) -> dict[str, str]:
    return dict(re.findall(r"export const ([A-Z0-9_]+) = '([^']*)'", source))


def parse_ts_string_map(source: str, const_name: str, constants: dict[str, str]) -> dict[str, str]:
    marker = f"export const {const_name}"
    start = source.find(marker)
    if start < 0:
        raise KeyError(const_name)
    body = brace_block(source, source.find("{", start))
    mapping: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.split("//", 1)[0].strip().rstrip(",")
        if not line or line in {"{", "}"}:
            continue
        computed = re.fullmatch(r"\[([A-Z0-9_]+)\]:\s*(?:'([^']*)'|([A-Z0-9_]+))", line)
        if computed:
            key = constants.get(computed.group(1), computed.group(1))
            value = computed.group(2) if computed.group(2) is not None else constants.get(computed.group(3), computed.group(3))
            mapping[key] = value
            continue
        literal = re.fullmatch(r"'([^']*)':\s*'([^']*)'", line)
        if literal:
            mapping[literal.group(1)] = literal.group(2)
    return mapping


def parse_country_aliases(source: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"business:\s*'([^']+)'\s*,\s*routeId:\s*'([^']+)'\s*,\s*sources:\s*\{\s*EGY:\s*\[([^\]]*)\]\s*,\s*UAE:\s*\[([^\]]*)\]",
        re.S,
    )
    aliases = []
    for business, route_id, egy_raw, uae_raw in pattern.findall(source):
        def names(raw: str) -> list[str]:
            return re.findall(r"'([^']+)'", raw)

        aliases.append(
            {
                "business": business,
                "route_id": route_id,
                "sources": {"EGY": names(egy_raw), "UAE": names(uae_raw)},
            }
        )
    return aliases


def function_source(source: str, name: str) -> str:
    match = re.search(rf"function {name}\s*\([^)]*\)[^{{]*\{{", source)
    if not match:
        return ""
    return brace_block(source, match.end() - 1)


def population_from_method(method: str | None) -> str:
    if method in {"ratio", "sum", "weighted_average"}:
        return "pooled"
    if method == "average":
        return "employee"
    return "unknown"


def country_from_region(region: str | None) -> str:
    token = str(region or "").strip()
    upper = token.upper()
    if upper in {"EGY", "EGYPT"}:
        return "EGY"
    if upper == "UAE":
        return "UAE"
    if upper in {"ALL", "SHARED", ""}:
        return "shared"
    return "unknown"


def ownership_for(region: str | None, rcm_group: str | None) -> dict[str, Any]:
    country = country_from_region(region)
    if rcm_group == "offshore_egy":
        scope = "EGY"
    elif rcm_group == "uae":
        scope = "UAE"
    elif country == "shared":
        scope = "shared"
    else:
        scope = country
    return {
        "scope": scope,
        "config_region": region or None,
        "rcm_group": rcm_group,
        "named_owner": None,
        "note": "Organizational scope from config region and rcm_group. Config files do not name a person owner.",
    }


class ManifestBuilder:
    def __init__(self, database_url: str | None = None) -> None:
        self.root = repo_root()
        self.database_url = database_url
        self.function_for_team, self.functions_for_team = function_lookup()
        self.team_dir = self.root / "Backend" / "config" / "teams"
        self.configs = self._load_configs()
        self.config_by_team = {cfg["team"]: cfg for cfg in self.configs}
        self.sources = self._load_sources()
        self.bindings: list[dict[str, Any]] = []
        self.conflicts: list[dict[str, Any]] = []
        self._collect_aliases()

    def _load_configs(self) -> list[dict[str, Any]]:
        loaded = []
        for path in sorted(self.team_dir.glob("*.json")):
            data = load_json(path)
            loaded.append(
                {
                    "path": rel(path),
                    "team": str(data.get("team") or "").strip(),
                    "db_name": str(data.get("db_name") or data.get("team") or "").strip(),
                    "region": str(data.get("region") or "").strip(),
                    "aliases": [str(item) for item in data.get("aliases") or []],
                    "sheet_team": data.get("sheet_team"),
                    "rcm_group": data.get("rcm_group"),
                    "rcm_domain": data.get("rcm_domain"),
                    "data": data,
                }
            )
        return loaded

    def _load_sources(self) -> dict[str, Any]:
        catalog_path = self.root / "Backend" / "services" / "ai" / "catalog.py"
        kpi_path = self.root / "Backend" / "services" / "kpi_service.py"
        outbound_path = self.root / "Backend" / "services" / "outbound_period_basis.py"
        bsc_path = self.root / "Backend" / "services" / "ai" / "corporate_bsc_catalog_data.py"
        action_path = self.root / "Backend" / "services" / "team_action_service.py"
        identity_path = self.root / "Backend" / "utils" / "team_identity.py"
        types_path = self.root / "Frontend" / "src" / "types.ts"
        country_path = self.root / "Frontend" / "src" / "features" / "team" / "countryTeamIdentity.ts"
        types_source = types_path.read_text(encoding="utf-8")
        country_source = country_path.read_text(encoding="utf-8")
        constants = extract_ts_const_strings(types_source)
        return {
            "paths": {
                "team_english_aliases": rel(catalog_path),
                "position_english_aliases": rel(catalog_path),
                "default_weights": rel(kpi_path),
                "outbound_basis": rel(outbound_path),
                "corporate_bsc": rel(bsc_path),
                "action_slugs": rel(action_path),
                "egypt_resubmission": rel(identity_path),
                "frontend_routes": rel(types_path),
                "country_aliases": rel(country_path),
                "performance_record_model": "Backend/models/models.py#PerformanceRecord",
                "kpi_value_model": "Backend/models/models.py#KPIValue",
                "team_kpi_config_model": "Backend/models/models.py#TeamKPIConfig",
                "management_kpi_config_model": "Backend/models/models.py#ManagementKPIConfig",
                "permission_functions": "Backend/utils/report_scope.py#user_can_access_team",
            },
            "team_aliases": literal_assignment(catalog_path, "TEAM_ENGLISH_ALIASES"),
            "position_aliases": literal_assignment(catalog_path, "POSITION_ENGLISH_ALIASES"),
            "default_weights": literal_assignment(kpi_path, "DEFAULT_WEIGHTS"),
            "technical_lines": literal_assignment(outbound_path, "TECHNICAL_LINES"),
            "july_lines": literal_assignment(outbound_path, "JULY_LINES"),
            "august_lines": literal_assignment(outbound_path, "AUGUST_LINES"),
            "corporate_bsc": literal_assignment(bsc_path, "CORPORATE_BSC_CATALOG_TEAMS"),
            "action_slugs": literal_assignment(action_path, "_SLUG_ALIASES"),
            "egypt_resubmission": sorted(literal_assignment(identity_path, "EGYPT_RESUBMISSION_TEAM_ALIASES")),
            "team_id_map": parse_ts_string_map(types_source, "TEAM_ID_MAP", constants),
            "team_name_map": parse_ts_string_map(types_source, "TEAM_NAME_MAP", constants),
            "team_db_map": parse_ts_string_map(types_source, "TEAM_DB_NAME_MAP", constants),
            "country_aliases": parse_country_aliases(country_source),
            "types_source": types_source,
            "country_source": country_source,
            "catalog_source": catalog_path.read_text(encoding="utf-8"),
        }

    def _add_binding(
        self,
        alias: str,
        target: str,
        source: str,
        *,
        country: str | None = None,
        kind: str = "team",
    ) -> None:
        text = str(alias or "").strip()
        destination = str(target or "").strip()
        if not text or not destination:
            return
        self.bindings.append(
            {
                "alias": text,
                "alias_key": norm_alias(text),
                "alnum_key": alnum_key(text),
                "target": destination,
                "country": country,
                "source": source,
                "kind": kind,
            }
        )

    def _collect_aliases(self) -> None:
        sources = self.sources
        for team, aliases in sources["team_aliases"].items():
            country = country_from_region((self.config_by_team.get(team) or {}).get("region"))
            for alias in aliases:
                self._add_binding(alias, team, sources["paths"]["team_english_aliases"] + "#TEAM_ENGLISH_ALIASES", country=country)
            self._add_binding(team, team, sources["paths"]["team_english_aliases"] + "#TEAM_ENGLISH_ALIASES", country=country)
        for alias, pair in sources["position_aliases"].items():
            team, position = pair
            self._add_binding(
                alias,
                f"{team} / {position}",
                sources["paths"]["position_english_aliases"] + "#POSITION_ENGLISH_ALIASES",
                kind="position",
            )
        for alias in sources["country_aliases"]:
            for country, names in alias["sources"].items():
                for name in names:
                    self._add_binding(
                        alias["business"],
                        name,
                        sources["paths"]["country_aliases"] + "#COUNTRY_ALIASES",
                        country=country,
                    )
                    self._add_binding(
                        name,
                        name,
                        sources["paths"]["country_aliases"] + "#COUNTRY_ALIASES",
                        country=country,
                    )
        for name, route_id in sources["team_id_map"].items():
            self._add_binding(name, name, sources["paths"]["frontend_routes"] + "#TEAM_ID_MAP", kind="route")
            self._add_binding(route_id, name, sources["paths"]["frontend_routes"] + "#TEAM_ID_MAP", kind="route")
        for route_id, name in sources["team_name_map"].items():
            self._add_binding(route_id, name, sources["paths"]["frontend_routes"] + "#TEAM_NAME_MAP", kind="route-display")
        for route_id, name in sources["team_db_map"].items():
            self._add_binding(route_id, name, sources["paths"]["frontend_routes"] + "#TEAM_DB_NAME_MAP", kind="route-db")
        for slug, team in sources["action_slugs"].items():
            self._add_binding(slug, team, sources["paths"]["action_slugs"] + "#_SLUG_ALIASES", kind="action-slug")
        for alias in sources["egypt_resubmission"]:
            self._add_binding(
                alias,
                "Resubmission",
                sources["paths"]["egypt_resubmission"] + "#EGYPT_RESUBMISSION_TEAM_ALIASES",
                country="EGY",
            )
        for cfg in self.configs:
            for alias in cfg["aliases"]:
                self._add_binding(alias, cfg["team"], cfg["path"] + "#aliases", country=country_from_region(cfg["region"]))
            if cfg.get("sheet_team"):
                self._add_binding(
                    str(cfg["sheet_team"]),
                    cfg["team"],
                    cfg["path"] + "#sheet_team",
                    country=country_from_region(cfg["region"]),
                    kind="sheet",
                )
        self._detect_conflicts()

    def _conflict(
        self,
        conflict_id: str,
        kind: str,
        alias: str,
        targets: list[dict[str, Any]],
        reason: str,
        sources: list[str],
    ) -> None:
        unique_targets = []
        seen = set()
        for target in targets:
            key = (target.get("target"), target.get("country"), target.get("source"))
            if key in seen:
                continue
            seen.add(key)
            unique_targets.append(target)
        unique_targets.sort(key=lambda item: (str(item.get("target")), str(item.get("country")), str(item.get("source"))))
        self.conflicts.append(
            {
                "id": conflict_id,
                "kind": kind,
                "alias": alias,
                "targets": unique_targets,
                "resolution": "unresolved",
                "reason": reason,
                "sources": sorted(set(sources)),
            }
        )

    def _detect_conflicts(self) -> None:
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for binding in self.bindings:
            grouped[(binding["kind"], binding["alias_key"])].append(binding)
        for (kind, alias_key), rows in sorted(grouped.items()):
            destinations = {(row["target"], row.get("country")) for row in rows}
            if len({item[0] for item in destinations}) <= 1 and len(destinations) <= 1:
                continue
            # Same stored team cited with and without a country is not a second team.
            target_names = {item[0] for item in destinations}
            countries = {item[1] for item in destinations if item[1]}
            if len(target_names) == 1 and len(countries) <= 1:
                continue
            self._conflict(
                conflict_id=f"{kind}:{alias_key}",
                kind="same_alias_multiple_targets" if len(target_names) > 1 else "same_alias_multiple_countries",
                alias=rows[0]["alias"],
                targets=[{"target": row["target"], "country": row.get("country"), "source": row["source"]} for row in rows],
                reason=(
                    "The same alias is attached to more than one team or country in repository tables. "
                    "No target was chosen."
                ),
                sources=[row["source"] for row in rows],
            )

        for alias in self.sources["country_aliases"]:
            egy = alias["sources"]["EGY"]
            uae = alias["sources"]["UAE"]
            self._conflict(
                conflict_id=f"cross-country:{norm_alias(alias['business'])}",
                kind="same_display_name_across_countries",
                alias=alias["business"],
                targets=(
                    [{"target": name, "country": "EGY", "source": self.sources["paths"]["country_aliases"]} for name in egy]
                    + [{"target": name, "country": "UAE", "source": self.sources["paths"]["country_aliases"]} for name in uae]
                ),
                reason=(
                    f"Business name {alias['business']} is used for both an Egypt source team and a UAE source team. "
                    "The stored teams stay separate. A bare name without a country is unresolved."
                ),
                sources=[self.sources["paths"]["country_aliases"]],
            )

        alnum_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        seen_names = {}
        for cfg in self.configs:
            seen_names[alnum_key(cfg["team"])] = cfg["team"]
        for binding in self.bindings:
            if binding["kind"] not in {"team", "route", "route-display", "route-db", "sheet", "action-slug"}:
                continue
            alnum_groups[binding["alnum_key"]].append(binding)
        for key, rows in sorted(alnum_groups.items()):
            spellings = sorted({row["alias"] for row in rows})
            targets = sorted({row["target"] for row in rows})
            if len(spellings) < 2 or len(targets) < 2:
                continue
            if key in {"", "preapprovals"}:
                continue
            self._conflict(
                conflict_id=f"spelling:{key}",
                kind="mismatched_spellings",
                alias=key,
                targets=[{"target": row["target"], "country": row.get("country"), "source": row["source"], "spelling": row["alias"]} for row in rows],
                reason=(
                    "These spellings collapse to the same letters-and-digits key but name different targets. "
                    "Frontend teamRouteKey strips punctuation, so a non-exact lookup can collide. No spelling was chosen."
                ),
                sources=[row["source"] for row in rows],
            )

        self._detect_code_collapses()
        self._detect_position_alias_gaps()
        self.conflicts.sort(key=lambda item: item["id"])

    def _detect_position_alias_gaps(self) -> None:
        positions_by_team: dict[str, set[str]] = defaultdict(set)
        for cfg in self.configs:
            for group in self._iter_groups(cfg):
                if group["position"]:
                    positions_by_team[cfg["team"]].add(group["position"])
        positions_by_team["Support Positions"] = set(positions_by_team.get("Call Center", set()))
        self._conflict(
            conflict_id="team-label:support-positions",
            kind="team_label_without_config",
            alias="Support Positions",
            targets=[
                {"target": "Support Positions", "country": "EGY", "source": "Backend/services/ai/catalog.py#POSITION_ENGLISH_ALIASES"},
                {"target": "Call Center", "country": "EGY", "source": "Backend/config/teams/call_center.json"},
            ],
            reason=(
                "Position aliases name Support Positions as the team. Those positions are stored on the Call Center config. "
                "Support Positions stays a Call Center subteam in the matrix and is not given its own config identity."
            ),
            sources=[
                "Backend/services/ai/catalog.py#POSITION_ENGLISH_ALIASES",
                "Backend/config/teams/call_center.json",
            ],
        )
        for alias, pair in sorted(self.sources["position_aliases"].items()):
            team, position = pair
            known = positions_by_team.get(team)
            if known is not None and position in known:
                continue
            catalog_positions = [str(item) for item in (self.sources["corporate_bsc"].get(team) or {}).get("positions") or []]
            in_catalog = position in catalog_positions
            self._conflict(
                conflict_id=f"position-missing:{norm_alias(alias)}",
                kind="alias_target_missing",
                alias=alias,
                targets=[
                    {
                        "target": f"{team} / {position}",
                        "country": None,
                        "source": (
                            "Backend/services/ai/corporate_bsc_catalog_data.py#positions"
                            if in_catalog
                            else "Backend/services/ai/catalog.py#POSITION_ENGLISH_ALIASES"
                        ),
                    }
                ],
                reason=(
                    "The position alias matches a Management BSC catalog position, but that position is not in the team JSON. The two sources were not merged."
                    if in_catalog
                    else "The position alias points at a team or position that is not in a team config file or the Management BSC catalog. It was not remapped."
                ),
                sources=["Backend/services/ai/catalog.py#POSITION_ENGLISH_ALIASES"],
            )

    def _detect_code_collapses(self) -> None:
        types_source = self.sources["types_source"]
        country_source = self.sources["country_source"]
        catalog_source = self.sources["catalog_source"]
        canonical = function_source(types_source, "canonicalTeamName")
        if "preapprovalsopdubai" in canonical and "preapprovalsopfinalshjajm" in canonical and "MERGED_OP_FINAL_TEAM" in canonical:
            self._conflict(
                conflict_id="collapse:pre-approvals-op-final",
                kind="distinct_teams_collapsed_by_code",
                alias="Pre-Approvals OP Final",
                targets=[
                    {"target": "Pre-Approvals OP Dubai", "country": "UAE", "source": "Frontend/src/types.ts#canonicalTeamName"},
                    {"target": "Pre-Approvals OP Final SHJAJM", "country": "UAE", "source": "Frontend/src/types.ts#canonicalTeamName"},
                    {"target": "Pre-Approvals OP Final", "country": "UAE", "source": "Frontend/src/types.ts#MERGED_OP_FINAL_TEAM"},
                ],
                reason=(
                    "canonicalTeamName returns one presentation name for OP Dubai and OP Final SHJAJM. "
                    "Those source teams have separate config files and stay separate in this manifest. "
                    "Pre-Approvals OP Final has no team JSON."
                ),
                sources=["Frontend/src/types.ts#canonicalTeamName"],
            )
        if "preapprovalsipfinaldubai" in canonical and "preapprovalsipfinalshjajm" in canonical:
            self._conflict(
                conflict_id="collapse:pre-approvals-ip-final",
                kind="distinct_teams_collapsed_by_code",
                alias="Pre-Approvals IP Final",
                targets=[
                    {"target": "Pre-Approvals IP Final Dubai", "country": "UAE", "source": "Frontend/src/types.ts#canonicalTeamName"},
                    {"target": "Pre-Approvals IP Final SHJAJM", "country": "UAE", "source": "Frontend/src/types.ts#canonicalTeamName"},
                    {"target": "Pre-Approvals IP Final", "country": "UAE", "source": "Frontend/src/types.ts#MERGED_IP_FINAL_TEAM"},
                ],
                reason=(
                    "canonicalTeamName returns one presentation name for IP Final Dubai and IP Final SHJAJM. "
                    "Those source teams have separate config files and stay separate in this manifest. "
                    "Pre-Approvals IP Final has no team JSON."
                ),
                sources=["Frontend/src/types.ts#canonicalTeamName"],
            )
        egypt_value = function_source(types_source, "egyptRcmTeamValue")
        if "Pre-Approvals IP Offshore" in egypt_value and "return 'Pre-Approvals IP'" in egypt_value:
            self._conflict(
                conflict_id="collapse:pre-approvals-ip-offshore",
                kind="distinct_teams_collapsed_by_code",
                alias="Pre-Approvals IP",
                targets=[
                    {"target": "Pre-Approvals IP", "country": "EGY", "source": "Frontend/src/types.ts#egyptRcmTeamValue"},
                    {"target": "Pre-Approvals IP Offshore", "country": "EGY", "source": "Frontend/src/types.ts#egyptRcmTeamValue"},
                ],
                reason=(
                    "egyptRcmTeamValue returns Pre-Approvals IP for both Pre-Approvals IP and Pre-Approvals IP Offshore. "
                    "countryTeamIdentity.ts says those Egypt teams are not aliases. Both config files are kept."
                ),
                sources=[
                    "Frontend/src/types.ts#egyptRcmTeamValue",
                    "Frontend/src/features/team/countryTeamIdentity.ts",
                ],
            )
        group_fn = function_source(types_source, "rcmGroupForTeam")
        if "return offshore ? 'offshore_egy' : 'uae'" in group_fn:
            self._conflict(
                conflict_id="default:rcm-group-uae",
                kind="unsafe_default",
                alias="RCM",
                targets=[
                    {"target": "RCM", "country": "shared", "source": "Backend/config/teams/rcm.json#region"},
                    {"target": "RCM", "country": "UAE", "source": "Frontend/src/types.ts#rcmGroupForTeam"},
                ],
                reason=(
                    "rcmGroupForTeam falls through to UAE when the region text is not Egypt or UAE. "
                    "The RCM config region is All, so that fallback would label the shared parent as UAE. "
                    "This manifest keeps the parent shared and does not apply the fallback."
                ),
                sources=["Frontend/src/types.ts#rcmGroupForTeam", "Backend/config/teams/rcm.json"],
            )
        shared_route = function_source(country_source, "countryForSharedRoute")
        if "?? 'UAE'" in shared_route:
            self._conflict(
                conflict_id="default:shared-route-uae",
                kind="unsafe_default",
                alias="Coding|Submission|Re-Submission",
                targets=[
                    {"target": "Coding", "country": "UAE", "source": "Frontend/src/features/team/countryTeamIdentity.ts#countryForSharedRoute"},
                    {"target": "Coding EGY", "country": "EGY", "source": "Frontend/src/features/team/countryTeamIdentity.ts#COUNTRY_ALIASES"},
                    {"target": "Submission", "country": "UAE", "source": "Frontend/src/features/team/countryTeamIdentity.ts#countryForSharedRoute"},
                    {"target": "Submission EGY", "country": "EGY", "source": "Frontend/src/features/team/countryTeamIdentity.ts#COUNTRY_ALIASES"},
                    {"target": "Re-Submission", "country": "UAE", "source": "Frontend/src/features/team/countryTeamIdentity.ts#countryForSharedRoute"},
                    {"target": "Resubmission", "country": "EGY", "source": "Frontend/src/features/team/countryTeamIdentity.ts#COUNTRY_ALIASES"},
                ],
                reason=(
                    "countryForSharedRoute defaults a shared business route with no region to UAE. "
                    "That default is not used to classify teams in this manifest."
                ),
                sources=["Frontend/src/features/team/countryTeamIdentity.ts#countryForSharedRoute"],
            )
        if 'return "Coding EGY" if eff_region == "EGY" else "Coding"' in catalog_source:
            self._conflict(
                conflict_id="region-switch:coding-submission-resubmission",
                kind="region_dependent_resolution",
                alias="coding | submission | resubmission | re-submission",
                targets=[
                    {"target": "Coding", "country": "UAE", "source": "Backend/services/ai/catalog.py#resolve_canonical_team_name"},
                    {"target": "Coding EGY", "country": "EGY", "source": "Backend/services/ai/catalog.py#resolve_canonical_team_name"},
                    {"target": "Submission", "country": "UAE", "source": "Backend/services/ai/catalog.py#resolve_canonical_team_name"},
                    {"target": "Submission EGY", "country": "EGY", "source": "Backend/services/ai/catalog.py#resolve_canonical_team_name"},
                    {"target": "Re-Submission", "country": "UAE", "source": "Backend/services/ai/catalog.py#resolve_canonical_team_name"},
                    {"target": "Resubmission", "country": "EGY", "source": "Backend/services/ai/catalog.py#resolve_canonical_team_name"},
                ],
                reason=(
                    "resolve_canonical_team_name picks Egypt or UAE from a region hint, including a hint parsed from the prompt. "
                    "This manifest does not call that function and does not pick a side."
                ),
                sources=["Backend/services/ai/catalog.py#resolve_canonical_team_name"],
            )
        name_map = self.sources["team_name_map"]
        db_map = self.sources["team_db_map"]
        for route_id in sorted(set(name_map) & set(db_map)):
            if name_map[route_id] != db_map[route_id]:
                self._conflict(
                    conflict_id=f"route-map:{route_id}",
                    kind="route_display_db_mismatch",
                    alias=route_id,
                    targets=[
                        {"target": name_map[route_id], "country": None, "source": "Frontend/src/types.ts#TEAM_NAME_MAP"},
                        {"target": db_map[route_id], "country": None, "source": "Frontend/src/types.ts#TEAM_DB_NAME_MAP"},
                    ],
                    reason="The same route id has different display and database names. Neither was chosen as a new team.",
                    sources=["Frontend/src/types.ts#TEAM_NAME_MAP", "Frontend/src/types.ts#TEAM_DB_NAME_MAP"],
                )
        action = self.sources["action_slugs"]
        collapsed = [
            ("pre-approvals-op-final", "pre-approvals-op-final-shj-ajm"),
            ("pre-approvals-ip-final", "pre-approvals-ip-final-shj-ajm"),
        ]
        for left, right in collapsed:
            if action.get(left) and action.get(left) == action.get(right):
                self._conflict(
                    conflict_id=f"action-slug:{left}",
                    kind="distinct_teams_collapsed_by_code",
                    alias=left,
                    targets=[
                        {"target": left, "country": "UAE", "source": "Backend/services/team_action_service.py#_SLUG_ALIASES"},
                        {"target": right, "country": "UAE", "source": "Backend/services/team_action_service.py#_SLUG_ALIASES"},
                        {"target": action[left], "country": "UAE", "source": "Backend/services/team_action_service.py#_SLUG_ALIASES"},
                    ],
                    reason=(
                        "Action-note slugs for two source teams store notes on one team row. "
                        "The source teams remain separate in the catalog."
                    ),
                    sources=["Backend/services/team_action_service.py#_SLUG_ALIASES"],
                )

    def _iter_groups(self, cfg: dict[str, Any]):
        data = cfg["data"]
        if isinstance(data.get("kpis"), list) and data["kpis"]:
            yield {
                "level": "Employee",
                "position": "",
                "basis": "template",
                "effective_from": None,
                "kpis": data["kpis"],
                "pointer": f"{cfg['path']}#kpis",
            }
        if isinstance(data.get("tracking_indicators"), list):
            yield {
                "level": "Employee",
                "position": "",
                "basis": "tracking_indicators",
                "effective_from": None,
                "kpis": data["tracking_indicators"],
                "pointer": f"{cfg['path']}#tracking_indicators",
                "declared_tracking": True,
            }
        levels = data.get("performance_levels") or {}
        if isinstance(levels, dict):
            for level_name in sorted(levels):
                level_cfg = levels[level_name]
                if not isinstance(level_cfg, dict):
                    continue
                if isinstance(level_cfg.get("kpis"), list) and level_cfg["kpis"]:
                    yield {
                        "level": str(level_name),
                        "position": "",
                        "basis": "template",
                        "effective_from": None,
                        "kpis": level_cfg["kpis"],
                        "pointer": f"{cfg['path']}#performance_levels.{level_name}.kpis",
                    }
                positions = level_cfg.get("positions") or {}
                if not isinstance(positions, dict):
                    continue
                for position_name in sorted(positions):
                    position_cfg = positions[position_name]
                    if not isinstance(position_cfg, dict):
                        continue
                    if isinstance(position_cfg.get("kpis"), list) and position_cfg["kpis"]:
                        yield {
                            "level": str(level_name),
                            "position": str(position_name),
                            "basis": "template",
                            "effective_from": None,
                            "kpis": position_cfg["kpis"],
                            "pointer": f"{cfg['path']}#performance_levels.{level_name}.positions.{position_name}.kpis",
                        }
                    for index, variant in enumerate(position_cfg.get("period_variants") or []):
                        if not isinstance(variant, dict):
                            continue
                        yield {
                            "level": str(level_name),
                            "position": str(position_name),
                            "basis": str(variant.get("id") or f"period_variant_{index + 1}"),
                            "effective_from": variant.get("effective_from"),
                            "kpis": variant.get("kpis") or [],
                            "pointer": (
                                f"{cfg['path']}#performance_levels.{level_name}.positions."
                                f"{position_name}.period_variants[{index}]"
                            ),
                        }

    def _kpi_record(self, cfg: dict[str, Any], group: dict[str, Any], kpi: dict[str, Any]) -> dict[str, Any]:
        weight = kpi.get("weight", 0)
        weight_number = Decimal(str(weight or 0))
        declared_tracking = bool(group.get("declared_tracking"))
        view_only = bool(kpi.get("view_only"))
        not_in_score = declared_tracking or view_only or weight_number <= 0
        method = None
        aggregation = kpi.get("aggregation")
        if isinstance(aggregation, dict):
            method = aggregation.get("method")
        population = population_from_method(str(method) if method else None)
        key = str(kpi.get("key") or "")
        level = group["level"]
        key_limit = MANAGEMENT_KPI_KEY_MAX if level in {"Managerial", "Corporate"} else KPI_VALUE_KEY_MAX
        reasons = []
        if len(key) > KPI_VALUE_KEY_MAX:
            reasons.append(
                f"kpi_key length {len(key)} exceeds kpi_values.kpi_key String({KPI_VALUE_KEY_MAX}) "
                "in Backend/models/models.py"
            )
        if len(key) > key_limit:
            reasons.append(
                f"kpi_key length {len(key)} exceeds the {level} config column limit String({key_limit})"
            )
        required = ["key", "label", "weight", "direction", "unit"]
        if not declared_tracking:
            required.extend(["actual_col", "target_col"])
        missing_fields = [field for field in required if field not in kpi or kpi.get(field) in (None, "")]
        if missing_fields:
            reasons.append("missing fields: " + ", ".join(missing_fields))
        direction = str(kpi.get("direction") or "")
        if direction and direction not in {"higher_better", "lower_better"}:
            reasons.append(f"direction {direction} is outside higher_better|lower_better")
        return {
            "team": cfg["team"],
            "country": country_from_region(cfg["region"]),
            "region": cfg["region"],
            "function": self.function_for_team(cfg["team"]) or cfg["team"],
            "level": level,
            "position": group["position"],
            "basis": group["basis"],
            "effective_from": group.get("effective_from") or kpi.get("effective_from"),
            "key": key,
            "label": kpi.get("label"),
            "unit": kpi.get("unit"),
            "direction": direction or None,
            "weight": quantize_number(weight),
            "not_in_score": not_in_score,
            "not_in_score_reason": (
                "declared tracking_indicators"
                if declared_tracking
                else "view_only"
                if view_only
                else "weight is 0"
                if weight_number <= 0
                else None
            ),
            "aggregation_method": method,
            "score_population": population,
            "score_population_source": "aggregation.method on the KPI definition; ratio, sum, and weighted_average are pooled, average is per-employee",
            "actual_col": kpi.get("actual_col"),
            "target_col": kpi.get("target_col"),
            "source": group["pointer"],
            "definition_issues": reasons,
        }

    def _weight_issue(self, kpis: list[dict[str, Any]]) -> str | None:
        scored = [kpi for kpi in kpis if not kpi["not_in_score"]]
        if not scored:
            return None
        total = sum((Decimal(str(kpi["weight"])) for kpi in scored), Decimal("0"))
        if abs(total - Decimal("1")) > WEIGHT_TOLERANCE:
            return f"scored weights sum to {total}, not 1"
        return None

    def _default_weight_parity(self, team: str, kpis: list[dict[str, Any]]) -> dict[str, Any]:
        defaults = self.sources["default_weights"].get(team)
        if not defaults:
            return {"status": "not_run", "reason": "team is not in kpi_service.DEFAULT_WEIGHTS"}
        scored = {kpi["key"]: Decimal(str(kpi["weight"])) for kpi in kpis if not kpi["not_in_score"]}
        default_map = {key: Decimal(str(value)) for key, value in defaults.items()}
        if scored == default_map:
            return {"status": "pass", "reason": "team JSON scored keys and weights match DEFAULT_WEIGHTS"}
        return {
            "status": "fail",
            "reason": "team JSON scored keys/weights differ from kpi_service.DEFAULT_WEIGHTS",
            "config_keys": sorted(scored),
            "default_keys": sorted(default_map),
        }

    def _outbound_parity(self, kpis: list[dict[str, Any]]) -> dict[str, Any]:
        config_keys = [kpi["key"] for kpi in kpis if not kpi["not_in_score"]]
        technical = [line["kpi_key"] for line in self.sources["technical_lines"]]
        august = [line["kpi_key"] for line in self.sources["august_lines"]]
        if config_keys == technical:
            return {
                "status": "fail" if august != technical else "pass",
                "reason": (
                    "outbound.json matches TECHNICAL_LINES, but AUGUST_LINES adds Productivity "
                    "and changes Attendance weight. The published month is not in the repo, so the active basis is not selected."
                    if august != technical
                    else "outbound.json matches the technical and August lines"
                ),
                "technical_keys": technical,
                "august_keys": august,
            }
        return {
            "status": "fail",
            "reason": "outbound.json scored keys differ from outbound_period_basis.TECHNICAL_LINES",
            "config_keys": config_keys,
            "technical_keys": technical,
        }

    def build(self) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        kpi_rows: list[dict[str, Any]] = []
        scopes: list[dict[str, Any]] = []
        for cfg in self.configs:
            functions = self.functions_for_team(cfg["team"]) or [cfg["team"]]
            primary = functions[0]
            ownership = ownership_for(cfg["region"], cfg.get("rcm_group"))
            entries.append(self._team_entry(cfg, primary, functions, ownership))
            grouped: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
            group_meta: dict[tuple, dict[str, Any]] = {}
            for group in self._iter_groups(cfg):
                records = [self._kpi_record(cfg, group, kpi) for kpi in group["kpis"] if isinstance(kpi, dict)]
                kpi_rows.extend(records)
                key = (group["level"], group["position"], group["basis"])
                grouped[key].extend(records)
                group_meta[key] = group
            for key in sorted(grouped):
                level, position, basis = key
                records = grouped[key]
                scored = [record for record in records if not record["not_in_score"]]
                tracking = [record for record in records if record["not_in_score"]]
                if scored:
                    scopes.append(
                        self._scope_from_config(
                            cfg,
                            primary,
                            functions,
                            ownership,
                            level,
                            position,
                            basis,
                            scored,
                            group_meta[key],
                        )
                    )
                for record in tracking:
                    tracking_group = dict(group_meta[key])
                    tracking_group["declared_tracking"] = True
                    tracking_group["pointer"] = record["source"]
                    scopes.append(
                        self._scope_from_config(
                            cfg,
                            primary,
                            functions,
                            ownership,
                            level,
                            position,
                            basis,
                            [record],
                            tracking_group,
                            measure=str(record["key"]),
                        )
                    )
        scopes.extend(self._derived_scopes())
        kpi_rows.extend(self._corporate_only_kpis(entries, scopes))
        kpi_rows.extend(self._volume_measures(scopes))
        matrix = [cell for scope in scopes for cell in self._cells_for_scope(scope)]
        matrix.sort(key=lambda cell: (cell["country"], cell["function"], cell["team"], cell["subteam"], cell["position"], cell["level"], cell["basis"], cell["measure"], cell["operation"]))
        reconciliation = self._reconcile(entries, kpi_rows, scopes)
        published = self._published_periods()
        manifest = {
            "manifest_version": MANIFEST_VERSION,
            "phase": PHASE,
            "baseline_commit": BASELINE_COMMIT,
            "generator": rel(Path(__file__)),
            "inputs_fingerprint": sha256_files(self._input_paths()),
            "rules": {
                "verified_requires": [
                    "a source-parity check that exists and passes for the cell",
                    "a permission check that exists and passes for the cell",
                ],
                "permission_checks_executed": False,
                "performance_records_read": published["read"],
                "no_employee_data": True,
                "ai_enabled": False,
                "default_status": "unknown or blocked with a reason; never verified from catalog presence alone",
                "prior_coverage_claims": "docs/plans/contextual-ai-assistant/coverage_manifest_v1.json was not used as evidence",
            },
            "catalog": self._catalog(entries, kpi_rows),
            "entries": entries,
            "kpis": kpi_rows,
            "matrix": matrix,
            "alias_report": self._alias_report(),
            "reconciliation": reconciliation,
            "published_periods": published,
            "undetermined_from_repo": self._undetermined(published),
            "counts": {},
        }
        manifest["counts"] = self._counts(manifest)
        manifest = sanitize(manifest)
        self._assert_no_employee_data(manifest)
        return manifest

    def _input_paths(self) -> list[Path]:
        paths = list(self.team_dir.glob("*.json"))
        paths.extend(
            [
                self.root / "Backend" / "services" / "ai" / "catalog.py",
                self.root / "Backend" / "services" / "ai" / "corporate_bsc_catalog_data.py",
                self.root / "Backend" / "services" / "kpi_service.py",
                self.root / "Backend" / "services" / "outbound_period_basis.py",
                self.root / "Backend" / "services" / "team_action_service.py",
                self.root / "Backend" / "services" / "tracking_indicators.py",
                self.root / "Backend" / "utils" / "report_scope.py",
                self.root / "Backend" / "utils" / "team_identity.py",
                self.root / "Backend" / "models" / "models.py",
                self.root / "Frontend" / "src" / "types.ts",
                self.root / "Frontend" / "src" / "features" / "team" / "countryTeamIdentity.ts",
                self.root / "Frontend" / "src" / "components" / "team" / "CallCenterChannelSummary.tsx",
            ]
        )
        return paths

    def _team_entry(self, cfg: dict[str, Any], primary: str, functions: list[str], ownership: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": f"team:{cfg['team']}",
            "kind": "team",
            "active": True,
            "team": cfg["team"],
            "db_name": cfg["db_name"],
            "subteam": "",
            "country": country_from_region(cfg["region"]),
            "region": cfg["region"],
            "function": primary,
            "functions": functions,
            "rcm_group": cfg.get("rcm_group"),
            "rcm_domain": cfg.get("rcm_domain"),
            "ownership": ownership,
            "source": cfg["path"],
            "freshness": "published period not in the repo",
            "missing_evidence": [
                "teams.is_active is database state and was not read",
                "upload_log / performance_records published months were not read",
            ],
            "explanation_source": cfg["path"],
        }

    def _scope_from_config(
        self,
        cfg: dict[str, Any],
        primary: str,
        functions: list[str],
        ownership: dict[str, Any],
        level: str,
        position: str,
        basis: str,
        kpis: list[dict[str, Any]],
        group: dict[str, Any],
        measure: str = "",
    ) -> dict[str, Any]:
        subteam = "Support Positions" if cfg["team"] == "Call Center" and position else ""
        weight_issue = self._weight_issue(kpis)
        issues = sorted({issue for kpi in kpis for issue in kpi["definition_issues"]})
        if weight_issue:
            issues.append(weight_issue)
        parity_checks = []
        if not measure and cfg["team"] in self.sources["default_weights"] and level == "Employee" and position == "" and basis == "template":
            parity_checks.append(self._default_weight_parity(cfg["team"], kpis))
        if not measure and cfg["team"] == "Outbound" and level == "Employee" and position == "" and basis == "template":
            parity_checks.append(self._outbound_parity(kpis))
        if not measure and level == "Corporate":
            parity_checks.append(self._corporate_parity(cfg["team"], kpis))
        route = self.sources["team_id_map"].get(cfg["team"])
        return {
            "country": country_from_region(cfg["region"]),
            "region": cfg["region"],
            "function": primary,
            "functions": functions,
            "team": cfg["team"],
            "subteam": subteam,
            "position": position,
            "level": level,
            "basis": basis,
            "effective_from": group.get("effective_from"),
            "measure": measure,
            "not_in_score": bool(measure),
            "ownership": ownership,
            "source": group["pointer"],
            "route_id": route,
            "kpis": kpis,
            "issues": issues,
            "parity_checks": parity_checks,
            "shared_country_blocked": country_from_region(cfg["region"]) == "shared",
            "period_basis_unselected": basis not in {"template", "tracking_indicators"} or bool(group.get("effective_from")),
            "tracking_only_row": bool(group.get("declared_tracking")) or (bool(kpis) and all(kpi["not_in_score"] for kpi in kpis)),
        }

    def _corporate_parity(self, team: str, kpis: list[dict[str, Any]]) -> dict[str, Any]:
        catalog = self.sources["corporate_bsc"].get(team)
        if not catalog:
            return {"status": "not_run", "reason": "no Management BSC catalog entry for this team"}
        config_keys = sorted(kpi["key"] for kpi in kpis)
        catalog_keys = sorted(str(item.get("key")) for item in catalog.get("kpis") or [])
        if config_keys == catalog_keys:
            return {"status": "pass", "reason": "corporate KPI keys match corporate_bsc_catalog_data.py"}
        return {
            "status": "fail",
            "reason": "corporate KPI keys differ between team JSON and corporate_bsc_catalog_data.py",
            "config_keys": config_keys,
            "catalog_keys": catalog_keys,
        }

    def _derived_scopes(self) -> list[dict[str, Any]]:
        scopes = []
        call_center = self.config_by_team.get("Call Center")
        if call_center:
            ownership = ownership_for(call_center["region"], None)
            scopes.append(
                {
                    "country": "EGY",
                    "region": call_center["region"],
                    "function": "Call Center",
                    "functions": ["Call Center"],
                    "team": "Call Center",
                    "subteam": "Support Positions",
                    "position": "",
                    "level": "Employee",
                    "basis": "channel-rollup",
                    "effective_from": None,
                    "measure": "",
                    "not_in_score": False,
                    "ownership": ownership,
                    "source": "Frontend/src/components/team/CallCenterChannelSummary.tsx",
                    "route_id": self.sources["team_id_map"].get("Call Center"),
                    "kpis": [],
                    "issues": [
                        "Support Positions is a Call Center channel, not a config team. "
                        "The UI says its channel score is a position average, while position KPI aggregation methods are on the Call Center config."
                    ],
                    "parity_checks": [
                        {
                            "status": "fail",
                            "reason": (
                                "CallCenterChannelSummary says Support Positions uses a position average, "
                                "while Call Center position KPIs declare weighted_average. The two rollups were not reconciled."
                            ),
                        }
                    ],
                    "shared_country_blocked": False,
                    "period_basis_unselected": False,
                    "tracking_only_row": False,
                    "derived_rule": "support_positions_channel",
                }
            )
        for name, description in (
            ("Pre-Approvals OP Final", "presentation merge of OP Dubai and OP Final SHJAJM"),
            ("Pre-Approvals IP Final", "presentation merge of IP Final Dubai and IP Final SHJAJM"),
            ("Pre-Approvals IP Elective", "presentation name beside Pre-Approvals IP Elective Dubai"),
            ("Pre-Approvals", "UAE parent route with no team JSON; source teams are the Dubai and SHJAJM configs"),
            ("Re-Submission EGY", "route and alias of Resubmission; no separate team JSON"),
            ("Administration", "TEAM_NAME_MAP display for route administration; config team is Offshore Admin & Management"),
        ):
            scopes.append(
                {
                    "country": "UAE" if name != "Re-Submission EGY" else "EGY",
                    "region": "UAE" if name != "Re-Submission EGY" else "EGY",
                    "function": "RCM" if name.startswith("Pre-Approvals") or name.startswith("Re-Submission") else "Administration",
                    "functions": ["RCM"] if "Pre-Approvals" in name or name.startswith("Re-Submission") else ["Administration"],
                    "team": name,
                    "subteam": "",
                    "position": "",
                    "level": "Employee",
                    "basis": "unsupported-name",
                    "effective_from": None,
                    "measure": "",
                    "not_in_score": False,
                    "ownership": {"scope": "UAE" if name != "Re-Submission EGY" else "EGY", "config_region": None, "rcm_group": None, "named_owner": None, "note": description},
                    "source": "Frontend/src/types.ts",
                    "route_id": self.sources["team_id_map"].get(name),
                    "kpis": [],
                    "issues": [f"{description}. No KPI config file."],
                    "parity_checks": [{"status": "fail", "reason": "no team JSON and no KPI rows"}],
                    "shared_country_blocked": False,
                    "period_basis_unselected": False,
                    "tracking_only_row": False,
                    "derived_rule": "name_without_config",
                    "inactive_or_unsupported": True,
                }
            )
        return scopes

    def _corporate_only_kpis(self, entries: list[dict[str, Any]], scopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        known = {entry["team"] for entry in entries}
        for team, info in sorted(self.sources["corporate_bsc"].items()):
            if any(scope["team"] == team and scope["level"] == "Corporate" and not scope["measure"] for scope in scopes):
                continue
            region = str(info.get("region") or "")
            positions = [str(item) for item in info.get("positions") or []]
            position = positions[0] if len(positions) == 1 else ""
            kpis = []
            for kpi in info.get("kpis") or []:
                record = {
                    "team": team,
                    "country": country_from_region(region),
                    "region": region,
                    "function": self.function_for_team(team) or team,
                    "level": "Corporate",
                    "position": position,
                    "basis": "corporate_bsc_catalog",
                    "effective_from": None,
                    "key": kpi.get("key"),
                    "label": kpi.get("label"),
                    "unit": kpi.get("unit"),
                    "direction": kpi.get("direction"),
                    "weight": quantize_number(kpi.get("weight")),
                    "not_in_score": False,
                    "not_in_score_reason": None,
                    "aggregation_method": None,
                    "score_population": "unknown",
                    "score_population_source": "corporate_bsc_catalog_data.py does not set aggregation.method",
                    "actual_col": None,
                    "target_col": None,
                    "source": "Backend/services/ai/corporate_bsc_catalog_data.py#CORPORATE_BSC_CATALOG_TEAMS",
                    "definition_issues": [
                        "actual_col and target_col are absent",
                        "live management_kpi_config rows were not read",
                    ],
                }
                if team not in self.config_by_team:
                    record["definition_issues"].append("no Backend/config/teams JSON for this corporate team")
                kpis.append(record)
                rows.append(record)
            functions = self.functions_for_team(team) or [team]
            ownership = ownership_for(region, None)
            weight_issue = self._weight_issue(kpis)
            issues = [
                "missing fields: actual_col, target_col",
                "corporate catalog only; live management_kpi_config was not read",
            ]
            if weight_issue:
                issues.append(weight_issue)
            if team not in known:
                entries.append(
                {
                    "id": f"bsc:{team}",
                    "kind": "team",
                    "active": True,
                    "team": team,
                    "db_name": info.get("db_name"),
                    "subteam": "",
                    "country": country_from_region(region),
                    "region": region,
                    "function": functions[0],
                    "functions": functions,
                    "rcm_group": None,
                    "rcm_domain": None,
                    "ownership": ownership,
                    "source": "Backend/services/ai/corporate_bsc_catalog_data.py",
                    "freshness": "published period not in the repo",
                    "missing_evidence": [
                        "no team JSON",
                        "management_kpi_config and management_kpi_snapshots were not read",
                    ],
                    "explanation_source": "corporate_bsc_catalog_data.py",
                    "derived_rule": "corporate_bsc_catalog_only",
                }
                )
            scopes.append(
                {
                    "country": country_from_region(region),
                    "region": region,
                    "function": functions[0],
                    "functions": functions,
                    "team": team,
                    "subteam": "",
                    "position": position,
                    "level": "Corporate",
                    "basis": "corporate_bsc_catalog",
                    "effective_from": None,
                    "measure": "",
                    "not_in_score": False,
                    "ownership": ownership,
                    "source": "Backend/services/ai/corporate_bsc_catalog_data.py",
                    "route_id": self.sources["team_id_map"].get(team),
                    "kpis": kpis,
                    "issues": issues,
                    "parity_checks": [
                        {
                            "status": "not_run",
                            "reason": (
                                "team JSON has no Corporate KPI block; management_kpi_config was not read"
                                if team in self.config_by_team
                                else "no team JSON; management_kpi_config was not read"
                            ),
                        }
                    ],
                    "shared_country_blocked": country_from_region(region) == "shared",
                    "period_basis_unselected": False,
                    "tracking_only_row": False,
                    "derived_rule": "corporate_bsc_catalog_only",
                }
            )
        return rows

    def _volume_measures(self, scopes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows = []
        for spec in RECORD_VOLUME_MEASURES:
            for team in spec["teams"]:
                cfg = self.config_by_team.get(team)
                if not cfg:
                    continue
                record = {
                    "team": team,
                    "country": country_from_region(cfg["region"]),
                    "region": cfg["region"],
                    "function": "Call Center",
                    "level": "Employee",
                    "position": "",
                    "basis": "record_contract",
                    "effective_from": None,
                    "key": spec["key"],
                    "label": spec["label"],
                    "unit": spec["unit"],
                    "direction": spec["direction"],
                    "weight": 0,
                    "not_in_score": True,
                    "not_in_score_reason": spec["note"],
                    "aggregation_method": "sum",
                    "score_population": "pooled",
                    "score_population_source": spec["sources"][0],
                    "actual_col": None,
                    "target_col": None,
                    "source": spec["sources"][0],
                    "definition_issues": ["not a team-config KPI; stored on the record payload, not confirmed in kpi_values"],
                }
                rows.append(record)
                scopes.append(
                    {
                        "country": record["country"],
                        "region": cfg["region"],
                        "function": "Call Center",
                        "functions": ["Call Center"],
                        "team": team,
                        "subteam": team,
                        "position": "",
                        "level": "Employee",
                        "basis": "record_contract",
                        "effective_from": None,
                        "measure": spec["key"],
                        "not_in_score": True,
                        "ownership": ownership_for(cfg["region"], None),
                        "source": spec["sources"][0],
                        "route_id": self.sources["team_id_map"].get(team),
                        "kpis": [record],
                        "issues": [spec["note"]],
                        "parity_checks": [
                            {
                                "status": "not_run",
                                "reason": "record-contract field only; performance_records payloads were not read and catalog.py verified flags were ignored",
                            }
                        ],
                        "shared_country_blocked": False,
                        "period_basis_unselected": False,
                        "tracking_only_row": True,
                        "derived_rule": "tracking_only_record_field",
                    }
                )
        for cfg in self.configs:
            for group in self._iter_groups(cfg):
                if not group.get("declared_tracking"):
                    continue
                # Tracking groups already produced a scope via _scope_from_config.
                # Mark that scope tracking-only; nothing else to add here.
                continue
        return rows

    def _cells_for_scope(self, scope: dict[str, Any]) -> list[dict[str, Any]]:
        cells = []
        for operation in OPERATIONS:
            status, reason, parity, permission = self._status(scope, operation)
            if status in {"verified", "verified no data"}:
                raise RuntimeError(f"refusing to emit {status} for {scope['team']} {operation}")
            cells.append(
                {
                    "country": scope["country"],
                    "function": scope["function"],
                    "team": scope["team"],
                    "subteam": scope["subteam"],
                    "position": scope["position"],
                    "level": scope["level"],
                    "basis": scope["basis"],
                    "measure": scope["measure"],
                    "operation": operation,
                    "status": status,
                    "reason": reason,
                    "not_in_score": bool(scope["not_in_score"] or scope["tracking_only_row"]),
                    "source": scope["source"],
                    "ownership": scope["ownership"]["scope"],
                    "freshness": scope.get("effective_from") or "published period not in the repo",
                    "missing_evidence": self._missing(scope, operation),
                    "source_parity": parity,
                    "permission_check": permission,
                }
            )
        return cells

    def _status(self, scope: dict[str, Any], operation: str) -> tuple[str, str, str, str]:
        permission = "not_run"
        checks = scope["parity_checks"]
        failed = [check for check in checks if check["status"] == "fail"]
        passed = [check for check in checks if check["status"] == "pass"]
        parity = "fail" if failed else "pass" if passed else "not_run"
        issues = scope["issues"]

        if operation == "follow-up":
            return (
                "blocked",
                "Follow-up is an AI conversation operation. AI stays off; this inventory does not enable it, and no per-scope permission check was executed.",
                parity,
                permission,
            )
        if scope.get("inactive_or_unsupported") or scope["basis"] == "unsupported-name":
            return (
                "blocked",
                issues[0] if issues else "Name has no KPI config.",
                "fail",
                permission,
            )
        if operation == "score" and (scope["tracking_only_row"] or scope["not_in_score"]):
            return (
                "not applicable",
                "Tracking-only or zero-weight measure. It does not count toward the score.",
                parity,
                permission,
            )
        if operation == "comparison" and scope["shared_country_blocked"]:
            return (
                "blocked",
                "Region All is shared ownership. A single-country comparison needs record-level attribution, which was not read. Team name was not used as a country.",
                parity,
                permission,
            )
        if operation == "navigation" and not scope.get("route_id") and scope["team"] not in self.sources["team_id_map"]:
            return (
                "blocked",
                "No TEAM_ID_MAP route for this scope. Permission was not checked.",
                parity,
                permission,
            )
        if failed and operation in {"score", "actual/target"}:
            return ("blocked", failed[0]["reason"], "fail", permission)
        if issues and operation in {"score", "actual/target"} and any("exceeds" in issue or "missing fields" in issue or "weights sum" in issue for issue in issues):
            return ("blocked", "; ".join(issues), "fail", permission)
        if scope["period_basis_unselected"] and operation in {"score", "actual/target", "trend", "ranking", "comparison"}:
            return (
                "unknown",
                "A period-specific KPI basis exists, and the published month is not in the repo, so the active basis cannot be selected. Permission check was not executed.",
                parity,
                permission,
            )
        if passed and not failed and operation in {"score", "actual/target"}:
            return (
                "partial",
                passed[0]["reason"] + " Permission check was not executed and performance_records were not read, so this is not verified.",
                "pass",
                permission,
            )
        if operation == "navigation" and scope.get("route_id"):
            return (
                "unknown",
                f"Route id {scope['route_id']} is present. Access was not checked with user_can_access_team.",
                parity,
                permission,
            )
        return (
            "unknown",
            "Definition is only in one repository source, or no second source agrees. performance_records were not read and no permission check was executed.",
            parity,
            permission,
        )

    def _missing(self, scope: dict[str, Any], operation: str) -> list[str]:
        missing = [
            "permission check not executed (Backend/utils/report_scope.py user_can_access_team / user_can_access_team_level)",
        ]
        if operation != "navigation":
            missing.append("published performance_records / upload_log months not in the repo")
        if scope["level"] in {"Managerial", "Corporate"}:
            missing.append("management_kpi_config and management_kpi_snapshots were not read")
        if scope["period_basis_unselected"]:
            missing.append("active scoring basis depends on a published period")
        return missing

    def _reconcile(self, entries: list[dict[str, Any]], kpis: list[dict[str, Any]], scopes: list[dict[str, Any]]) -> dict[str, Any]:
        config_teams = {cfg["team"] for cfg in self.configs}
        teams_with_kpis = {kpi["team"] for kpi in kpis}
        config_without_kpis = sorted(config_teams - teams_with_kpis)
        bsc_without_config = sorted(set(self.sources["corporate_bsc"]) - config_teams)
        kpis_without_team_config = [
            {"team": team, "kpi_count": sum(1 for kpi in kpis if kpi["team"] == team), "source": "Backend/services/ai/corporate_bsc_catalog_data.py"}
            for team in bsc_without_config
        ]
        inactive = [
            {
                "team": scope["team"],
                "status": "unsupported",
                "reason": scope["issues"][0],
                "source": scope["source"],
            }
            for scope in scopes
            if scope.get("inactive_or_unsupported")
        ]
        inactive.append(
            {
                "team": "Call Center",
                "status": "no-data",
                "reason": "team_action_service says the employee-level Call Center row may be inactive in the database after Inbound and Outbound were split. teams.is_active was not read. The config file is present.",
                "source": "Backend/services/team_action_service.py",
            }
        )
        inactive.append(
            {
                "team": "*",
                "status": "no-data",
                "reason": "No published month could be derived from repository data. upload_log and performance_records were not read.",
                "source": "Backend/models/models.py#UploadLog",
            }
        )
        explained_derived = sorted(
            {
                entry["team"]
                for entry in entries
                if entry["team"] not in config_teams
            }
        )
        active_teams = {entry["team"] for entry in entries if entry.get("active")}
        unexplained = sorted(active_teams - config_teams - set(explained_derived))
        # explained_derived is defined as every non-config active team, so unexplained stays empty
        # only when each of those teams has a derived_rule. Enforce that.
        derived_without_rule = sorted(
            entry["team"]
            for entry in entries
            if entry.get("active") and entry["team"] not in config_teams and not entry.get("derived_rule")
        )
        unexplained = sorted(set(unexplained) | set(derived_without_rule))
        zero_weight = [
            {"team": kpi["team"], "level": kpi["level"], "position": kpi["position"], "key": kpi["key"], "reason": kpi["not_in_score_reason"], "source": kpi["source"]}
            for kpi in kpis
            if kpi["not_in_score"]
        ]
        return {
            "config_without_kpis": config_without_kpis,
            "kpis_without_team_config": kpis_without_team_config,
            "inactive_unsupported_nodata": inactive,
            "not_in_score": zero_weight,
            "explained_derived_teams": [
                {
                    "team": entry["team"],
                    "derived_rule": entry.get("derived_rule"),
                    "source": entry["source"],
                }
                for entry in entries
                if entry["team"] not in config_teams
            ],
            "unexplained_active": unexplained,
            "corporate_region_disagreements": self._corporate_region_disagreements(),
        }

    def _corporate_region_disagreements(self) -> list[dict[str, Any]]:
        rows = []
        for team, info in sorted(self.sources["corporate_bsc"].items()):
            cfg = self.config_by_team.get(team)
            if not cfg:
                continue
            if country_from_region(cfg["region"]) != country_from_region(str(info.get("region") or "")):
                rows.append(
                    {
                        "team": team,
                        "config_region": cfg["region"],
                        "bsc_catalog_region": info.get("region"),
                        "resolution": "unresolved",
                        "reason": "Employee/config region and Management BSC catalog region differ. Levels were not merged.",
                    }
                )
        return rows

    def _published_periods(self) -> dict[str, Any]:
        code_basis = [
            {
                "team": "Outbound",
                "period": "2026-07",
                "source": "Backend/services/outbound_period_basis.py#JULY_LINES",
                "means": "code-declared scoring basis, not proof that July was published",
            },
            {
                "team": "Outbound",
                "period": "2026-08",
                "source": "Backend/services/outbound_period_basis.py#AUGUST_LINES",
                "means": "code-declared scoring basis, not proof that August was published",
            },
            {
                "team": "Pre-Approvals IP Offshore",
                "period": "2026-06",
                "source": "Backend/config/teams/pre_approvals_offshore.json#effective_from",
                "means": "KPI text says the controllable-rejection basis starts June 2026",
            },
            {
                "team": "Marketing",
                "period": "2026-05-01",
                "source": "Backend/config/teams/marketing.json#period_variants",
                "means": "position period variant effective_from, not a published-month inventory",
            },
        ]
        db_result: dict[str, Any] = {"read": False, "reason": "database read is off by default"}
        if self.database_url:
            db_result = self._read_db_periods(self.database_url)
        return {"read": bool(db_result.get("read")), "code_declared_basis": code_basis, "database": db_result}

    def _read_db_periods(self, database_url: str) -> dict[str, Any]:
        try:
            from sqlalchemy import create_engine, text
        except ImportError:
            return {"read": False, "reason": "sqlalchemy is not installed; database was not read"}
        engine = create_engine(database_url)
        statement = text(
            """
            SELECT team.name AS team_name,
                   team.region AS region,
                   team.is_active AS is_active,
                   record.performance_level AS performance_level,
                   record.month AS month,
                   record.year AS year,
                   COUNT(*) AS record_count
            FROM performance_records AS record
            JOIN teams AS team ON team.id = record.team_id
            GROUP BY team.name, team.region, team.is_active, record.performance_level, record.month, record.year
            ORDER BY team.name, record.year, record.month, record.performance_level
            """
        )
        try:
            with engine.connect() as connection:
                fetched = connection.execute(statement).mappings().all()
        except Exception as exc:  # noqa: BLE001 - surface a safe reason, never the URL
            return {"read": False, "reason": f"database read failed: {type(exc).__name__}"}
        periods = [
            {
                "team": row["team_name"],
                "region": row["region"],
                "is_active": bool(row["is_active"]),
                "level": row["performance_level"],
                "month": row["month"],
                "year": int(row["year"]),
                "record_count": int(row["record_count"]),
            }
            for row in fetched
        ]
        return {"read": True, "periods": periods}

    def _alias_report(self) -> dict[str, Any]:
        central = []
        by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for binding in self.bindings:
            by_source[binding["source"]].append(
                {
                    "alias": binding["alias"],
                    "target": binding["target"],
                    "country": binding.get("country"),
                    "kind": binding["kind"],
                }
            )
        for source in sorted(by_source):
            rows = sorted(by_source[source], key=lambda item: (item["alias"], item["target"], str(item["country"])))
            central.append({"source": source, "count": len(rows), "mappings": rows})
        egypt = sorted(cfg["team"] for cfg in self.configs if cfg.get("rcm_group") == "offshore_egy" or (country_from_region(cfg["region"]) == "EGY" and (self.function_for_team(cfg["team"]) == "RCM")))
        uae = sorted(
            cfg["team"]
            for cfg in self.configs
            if country_from_region(cfg["region"]) == "UAE" and self.function_for_team(cfg["team"]) == "RCM" and cfg["team"] != "RCM"
        )
        return {
            "central_tables": central,
            "conflicts": self.conflicts,
            "rcm_separation": {
                "rule": "RCM Egypt children and RCM UAE children are separate config teams. The RCM parent region All stays shared. No alias was resolved onto the other country.",
                "shared_parent": {"team": "RCM", "region": self.config_by_team["RCM"]["region"]},
                "egypt_teams": egypt,
                "uae_teams": uae,
                "kept_distinct_pairs": [
                    ["Coding EGY", "Coding"],
                    ["Submission EGY", "Submission"],
                    ["Resubmission", "Re-Submission"],
                    ["Pre-Approvals IP", "Pre-Approvals IP Offshore"],
                ],
            },
        }

    def _catalog(self, entries: list[dict[str, Any]], kpis: list[dict[str, Any]]) -> dict[str, Any]:
        countries = sorted({entry["country"] for entry in entries})
        functions = sorted({function for entry in entries for function in (entry.get("functions") or [entry["function"]])})
        teams = sorted({entry["team"] for entry in entries if entry["kind"] == "team"})
        positions = sorted({(kpi["team"], kpi["level"], kpi["position"]) for kpi in kpis if kpi["position"]})
        levels = sorted({kpi["level"] for kpi in kpis})
        return {
            "countries": countries,
            "functions": functions,
            "teams": teams,
            "position_levels": [
                {"team": team, "level": level, "position": position}
                for team, level, position in positions
            ],
            "levels": levels,
        }

    def _undetermined(self, published: dict[str, Any]) -> list[str]:
        items = [
            "Which months are published in performance_records and upload_log.",
            "Whether each teams.is_active flag is true in the database.",
            "Whether management_kpi_config rows match corporate_bsc_catalog_data.py.",
            "Whether stored kpi_values match team JSON keys, weights, direction, and units.",
            "Whether an authorized role can open each scope (permission checks were not executed).",
            "Which scoring basis is active for Outbound and Marketing when more than one basis exists.",
        ]
        if not published.get("read"):
            items.append("Database aggregate published periods. Re-run with --read-db and a repository DATABASE_URL to attach counts only.")
        return items

    def _counts(self, manifest: dict[str, Any]) -> dict[str, Any]:
        kpis = manifest["kpis"]
        matrix = manifest["matrix"]
        by_status: dict[str, int] = {status: 0 for status in STATUSES}
        for cell in matrix:
            by_status[cell["status"]] = by_status.get(cell["status"], 0) + 1
        positions = {(kpi["position"], kpi["level"]) for kpi in kpis if kpi["position"]}
        return {
            "countries": len(manifest["catalog"]["countries"]),
            "functions": len(manifest["catalog"]["functions"]),
            "teams": len(manifest["catalog"]["teams"]),
            "positions": len({kpi["position"] for kpi in kpis if kpi["position"]}),
            "position_level_pairs": len(positions),
            "levels": len(manifest["catalog"]["levels"]),
            "kpis": len(kpis),
            "kpis_not_in_score": sum(1 for kpi in kpis if kpi["not_in_score"]),
            "matrix_cells": len(matrix),
            "matrix_by_status": by_status,
            "alias_conflicts": len(manifest["alias_report"]["conflicts"]),
            "unexplained_active": len(manifest["reconciliation"]["unexplained_active"]),
        }

    def _assert_no_employee_data(self, manifest: dict[str, Any]) -> None:
        encoded = json.dumps(manifest)
        if re.search(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", encoded, re.I):
            raise RuntimeError("manifest contains an email address")
        if re.search(r"SGHD\d+", encoded, re.I):
            raise RuntimeError("manifest contains an employee identifier")
        if re.search(r"\b(employee_id|employee_name|full_name)\b", encoded):
            raise RuntimeError("manifest contains an employee field")


def render_csv(manifest: dict[str, Any]) -> str:
    fieldnames = [
        "country",
        "function",
        "team",
        "subteam",
        "position",
        "level",
        "basis",
        "measure",
        "operation",
        "status",
        "not_in_score",
        "ownership",
        "freshness",
        "source",
        "source_parity",
        "permission_check",
        "reason",
        "missing_evidence",
    ]
    writer_target = csv.StringIO(newline="")
    writer = csv.DictWriter(writer_target, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for cell in manifest["matrix"]:
        row = {key: cell.get(key, "") for key in fieldnames}
        row["missing_evidence"] = " | ".join(cell.get("missing_evidence") or [])
        writer.writerow(row)
    return writer_target.getvalue()


def render_markdown(manifest: dict[str, Any]) -> str:
    counts = manifest["counts"]
    status_lines = "\n".join(
        f"- {status}: {counts['matrix_by_status'].get(status, 0)}"
        for status in STATUSES
    )
    conflict_lines = []
    for conflict in manifest["alias_report"]["conflicts"]:
        seen_targets = []
        for item in conflict["targets"]:
            label = f"{item['target']}" + (f" ({item['country']})" if item.get("country") else "")
            if label not in seen_targets:
                seen_targets.append(label)
        targets = ", ".join(seen_targets)
        conflict_lines.append(
            f"- `{conflict['id']}` ({conflict['kind']}) alias `{conflict['alias']}` → {targets}. {conflict['reason']}"
        )
    recon = manifest["reconciliation"]
    derived = "\n".join(
        f"- {item['team']}: {item.get('derived_rule')} ({item['source']})"
        for item in recon["explained_derived_teams"]
    ) or "- none"
    unsupported = "\n".join(
        f"- {item['team']}: {item['status']} — {item['reason']}"
        for item in recon["inactive_unsupported_nodata"]
    )
    undetermined = "\n".join(f"- {item}" for item in manifest["undetermined_from_repo"])
    separation = manifest["alias_report"]["rcm_separation"]
    no_config = "\n".join(
        f"- {item['team']}: {item['kpi_count']} catalog KPIs, no team JSON"
        for item in recon["kpis_without_team_config"]
    ) or "- none"
    config_without = "\n".join(f"- {name}" for name in recon["config_without_kpis"]) or "- none"
    region_gaps = "\n".join(
        f"- {item['team']}: config {item['config_region']} vs BSC catalog {item['bsc_catalog_region']}"
        for item in recon["corporate_region_disagreements"]
    ) or "- none"
    return f"""# PMS Phase 2 coverage manifest

Version `{manifest['manifest_version']}` from repository sources at baseline `{manifest['baseline_commit']}`.
Input fingerprint `{manifest['inputs_fingerprint']}`.

No cell is verified. Verified would require a passing source-parity check and a passing permission check. Permission checks were not executed. Published performance rows were not read. AI is not enabled. The file has no employee names, identifiers, emails, or scores.

## Counts

- Countries: {counts['countries']} ({', '.join(manifest['catalog']['countries'])})
- Functions: {counts['functions']} ({', '.join(manifest['catalog']['functions'])})
- Teams: {counts['teams']}
- Positions: {counts['positions']}
- Position/level pairs: {counts['position_level_pairs']}
- Levels: {counts['levels']} ({', '.join(manifest['catalog']['levels'])})
- KPIs: {counts['kpis']} ({counts['kpis_not_in_score']} not in score)
- Matrix cells: {counts['matrix_cells']}

### Matrix cells by status

{status_lines}

## RCM Egypt and RCM UAE

Shared parent: {separation['shared_parent']['team']} region {separation['shared_parent']['region']}.

Egypt teams: {', '.join(separation['egypt_teams'])}.

UAE teams: {', '.join(separation['uae_teams'])}.

{separation['rule']}

## Unresolved alias conflicts

{chr(10).join(conflict_lines)}

## Reconciliation

Config entries with no KPIs:

{config_without}

KPIs whose team has no team JSON:

{no_config}

Corporate catalog region disagrees with team config:

{region_gaps}

Inactive, unsupported, or no-data:

{unsupported}

Derived names that are not config teams:

{derived}

Unexplained active entries: {len(recon['unexplained_active'])}.

## Not determined from the repo alone

{undetermined}

The cell-level matrix is in `coverage_matrix.csv`. Each row has its source, ownership, freshness, status reason, and missing evidence.
"""


def write_outputs(manifest: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "coverage_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (out_dir / "coverage_matrix.csv").write_text(render_csv(manifest), encoding="utf-8")
    (out_dir / "coverage_report.md").write_text(render_markdown(manifest), encoding="utf-8")


def build_manifest(database_url: str | None = None) -> dict[str, Any]:
    return ManifestBuilder(database_url=database_url).build()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the Phase 2 PMS coverage manifest from repository sources.")
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parent),
        help="Directory for coverage_manifest.json, coverage_matrix.csv, and coverage_report.md",
    )
    parser.add_argument(
        "--read-db",
        action="store_true",
        help="Optionally read aggregate published-period counts. Requires DATABASE_URL. Off by default.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Database URL used only with --read-db. The URL is not written to the manifest.",
    )
    args = parser.parse_args(argv)
    database_url = None
    if args.read_db:
        import os

        database_url = args.database_url or os.environ.get("DATABASE_URL")
        if not database_url:
            raise SystemExit("--read-db needs --database-url or DATABASE_URL")
    manifest = build_manifest(database_url=database_url)
    write_outputs(manifest, Path(args.out))
    counts = manifest["counts"]
    print(
        json.dumps(
            {
                "manifest_version": manifest["manifest_version"],
                "inputs_fingerprint": manifest["inputs_fingerprint"],
                "counts": counts,
                "unexplained_active": manifest["reconciliation"]["unexplained_active"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
