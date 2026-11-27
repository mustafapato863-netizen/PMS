"""Report-only data quality check over a saved GET /api/performance/summary-records response.

Flags (never changes data): exact ID twins, zero scores, region "All" employee rows, double-space names,
teams with missing months. Prints counts and record ids only, no employee names.
Usage: python Backend/scripts/report_data_quality.py summary_records.json
"""
import collections
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from utils.id_twins import find_id_twin_rows  # noqa: E402


def main(path: str) -> None:
    data = json.loads(Path(path).read_text())
    rows = data.get("data", data)
    emp = [r for r in rows if r.get("performance_level") == "Employee"]
    twins = find_id_twin_rows(
        {"key": r["id"], "employee_id": r["employee_id"], "name": r["employee_name"], "year": r["year"], "month": r["month"],
         "team_id": r["team"], "level": r["performance_level"], "score": r["evaluation"]["score"]}
        for r in emp
    )
    zero = [r["id"] for r in rows if (r.get("evaluation") or {}).get("score") == 0]
    region_all = [r["id"] for r in emp if r.get("region") == "All"]
    dbl = sum(1 for r in emp if "  " in r["employee_name"])
    per = {(r["year"], r["month"]) for r in rows}
    cover = collections.defaultdict(set)
    for r in rows:
        cover[r["team"]].add((r["year"], r["month"]))
    print(f"rows={len(rows)} id_twin_rows={len(twins)} zero_scores={len(zero)} region_All_employee_rows={len(region_all)} double_space_names={dbl}")
    print("zero score record ids:", zero)
    print("region All record ids:", region_all)
    print("teams missing months:", {t: len(per - v) for t, v in cover.items() if per - v})
    print("id twin record ids to be hidden when PMS_EXCLUDE_ID_TWINS=on:", twins)


if __name__ == "__main__":
    main(sys.argv[1])
