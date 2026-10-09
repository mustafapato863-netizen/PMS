"""Independent probes for authorized, saved row-basis overlays."""
from services.evaluation.resolver import overlay_pinned_kpis


def _record(lines, year=2026):
    return {
        "team": "Coding", "performance_level": "Employee", "position_name": "",
        "year": 2026, "month": "July",
        "record_payload": {"evaluation_basis": {
            "pinned": True, "version_id": "same-version", "year": year, "month": 7,
            "lines": lines,
        }},
    }


def _line(key, target):
    return {"kpi_key": key, "direction": "higher_better", "weight": 0.5,
            "target_mode": "fixed", "target": target}


def test_same_version_label_does_not_hide_disagreeing_saved_kpi_fields():
    kpis = [{"key": "one", "weight": 0.3}, {"key": "two", "weight": 0.7}]
    records = [_record([_line("one", 55), _line("two", 65)]),
               _record([_line("one", 65), _line("two", 55)])]
    assert overlay_pinned_kpis(None, "Coding", "Employee", "", 2026, 7, kpis, records) == kpis


def test_malformed_saved_period_is_not_used_as_scoring_basis():
    kpis = [{"key": "one", "weight": 0.3}]
    records = [_record([_line("one", 55)], year="invalid")]
    assert overlay_pinned_kpis(None, "Coding", "Employee", "", 2026, 7, kpis, records) == kpis
