"""Untrusted, ignored workbook diagnostics cannot break scored responses."""
import json
from decimal import Decimal

import pytest

from services.evaluation.access import EvaluationError
from services.evaluation.scoring import overall_score, score_rows


@pytest.mark.parametrize("ignored", [float("nan"), float("inf"), Decimal("1e999"), "unavailable"])
def test_ignored_workbook_achievement_does_not_drive_score_or_break_json(ignored):
    rows = score_rows("Employee", [{"kpi_key": "A", "weight": 1, "direction": "higher_better", "target_mode": "fixed", "target": 10}], [{"kpi_key": "A", "actual": 8, "workbook_target": 10, "precomputed_achievement": ignored}])
    assert overall_score(rows) == 80
    assert rows[0]["ignored_precomputed_achievement"] is None
    json.dumps(rows, allow_nan=False)


def test_overflowing_contribution_total_is_refused_before_score_cap():
    with pytest.raises(EvaluationError) as rejected:
        overall_score([{"contribution": 1e308}, {"contribution": 1e308}])
    assert rejected.value.data["code"] == "nonfinite_evidence"
