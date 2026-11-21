"""Compare AI ranking reads with the Monthly Review calculator on an explicit offline copy."""
import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "Backend"))

from config.loader import ConfigurationError, load_team_config
from models.ai_schemas import SessionFilterContext
from services.ai.tool_registry import DeterministicToolRegistry, ToolExecutionContext
from services.planning_service import MONTH_ORDER


def compare(path: Path) -> list[dict]:
    import sqlite3

    database = path.resolve(strict=True).as_uri() + "?mode=ro"
    engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(database, uri=True))
    with Session(engine) as db:
        ctx = ToolExecutionContext(db=db, scope={"role": "Admin", "has_unrestricted_team_access": True},
                                   session_state=SessionFilterContext())
        registry = DeterministicToolRegistry(ctx)
        records = ctx.get_scoped_records()
        configs = {}
        for name in {row.team for row in records}:
            try:
                configs[name] = load_team_config(name)
            except ConfigurationError:
                continue
        cells = []
        periods = sorted({(r.region, r.year, MONTH_ORDER[r.month], r.performance_level) for r in records
                          if r.region in {"EGY", "UAE"} and r.year and r.month in MONTH_ORDER})
        for region, year, month, level in periods:
            period = f"{year:04d}-{month:02d}"
            for entity in ("department", "team"):
                result = registry.execute_query_rankings(entity=entity, region=region, performance_level=level,
                                                        period=period, limit=50)
                query_result = result.digest["query_rankings"]
                for row in query_result["rows"]:
                    cells.append(dict(entity=entity, region=region, level=level, period=period,
                                      name=row["name"], chat=round(row["score"], 1)))
                for row in query_result.get("excluded_unverified", []):
                    cells.append(dict(
                        entity=entity,
                        region=region,
                        level=level,
                        period=period,
                        name=row["name"],
                        chat=None,
                        backend_excluded=True,
                        exclusion_reason=row.get("reason") or "Official score unavailable.",
                    ))
        bundle = dict(records=[r.model_dump(mode="json") for r in records], configs=configs, cells=cells)
    engine.dispose()
    result = subprocess.run(["node", "scripts/compare-monthly-review.mjs"], cwd=ROOT / "Frontend",
                            input=json.dumps(bundle), text=True, encoding="utf-8", capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr[-1800:])
    return json.loads(result.stdout)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sqlite", type=Path, required=True)
    args = parser.parse_args()
    comparisons = compare(args.sqlite)
    counts = Counter()
    mismatches = []
    excluded_unverified = []
    for cell in comparisons:
        if cell.get("backend_excluded"):
            if cell["official"] is None:
                counts["excluded_unverified"] += 1
                excluded_unverified.append({
                    "entity": cell["entity"],
                    "region": cell["region"],
                    "level": cell["level"],
                    "period": cell["period"],
                    "name": cell["name"],
                    "reason": cell["exclusion_reason"],
                })
                continue
            cell["different_reason"] = "Backend excluded this score, but Monthly Review produced a value."
            status = "different"
        else:
            status = ("missing_reference" if cell["official"] is None else
                      "match" if abs(cell["official"] - cell["chat"]) < 0.05 else "different")
        counts[status] += 1
        if status == "different":
            mismatches.append(cell)
    print(json.dumps({
        "total": len(comparisons),
        "counts": counts,
        "differences": mismatches,
        "excluded_unverified": excluded_unverified,
    }, indent=2))
