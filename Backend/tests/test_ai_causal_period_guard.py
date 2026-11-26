"""A causal 'why' answer never compares a month with itself and labels percent changes as pp."""
from services.ai.compound_parts_planner import plan_compound_parts, render_compound_parts_answer


def _render(prev_period, prev_actual=96.8):
    plan = plan_compound_parts("why is Marketing Rework percentage low in September 2026?", team="Marketing")
    plan.asks_causal_hypothesis = True
    headline, bullets, _ = render_compound_parts_answer(
        plan=plan,
        subject_name="Marketing",
        team_name="Marketing",
        period_label="September 2026",
        kpi_evidence={"display_name": "Rework percentage", "actual": 2.5, "target": 5.0, "unit": "%", "direction": "lower_better"},
        overall_score_val=82.2,
        previous_kpi_evidence={"actual": prev_actual, "period": prev_period},
    )
    return headline + " " + " ".join(bullets)


def test_same_period_is_not_reported_as_a_move():
    text = _render("September 2026")
    assert "moved from" not in text
    assert "hypotheses" in text.casefold()


def test_real_prior_period_uses_pp_not_percent_sign():
    text = _render("August 2026", prev_actual=4.0)
    assert "moved from" in text and "in August 2026" in text
    assert " pp)" in text and " %)" not in text
