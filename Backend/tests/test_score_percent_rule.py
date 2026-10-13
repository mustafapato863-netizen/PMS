"""Score scale rule: (0, 1] is a ratio, above 1 is a percentage; Offshore is never rescaled (synthetic)."""
from __future__ import annotations

import pytest
from sqlalchemy import Column, Float, MetaData, String, Table, create_engine, select
from sqlalchemy.orm import sessionmaker

from repositories.json_repos import _sanitize_performance_record_item
from utils.scoring_rules import score_percent, score_percent_sql

OFFSHORE = "Pre-Approvals IP Offshore"
INBOUND = "Inbound"


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        (0.85, 85.0),  # ratio form
        (1.0, 100.0),  # exactly one is a ratio
        (0.5, 50.0),
        (1.5, 1.5),  # above one is already a percentage
        (5.48, 5.48),  # a real low score stays as it is
        (10.0, 10.0),  # no longer treated as a ratio
        (51.28, 51.28),  # a percentage-form score (Offshore-style) is returned unchanged
        (0.0, 0.0),
        (70.8, 70.8),
    ],
)
def test_score_percent_is_one_rule_for_every_team(stored, expected):
    assert score_percent(stored) == pytest.approx(expected)


def test_sql_form_matches_the_python_rule():
    engine = create_engine("sqlite:///:memory:")
    metadata = MetaData()
    table = Table(
        "scores",
        metadata,
        Column("id", String, primary_key=True),
        Column("team", String),
        Column("score", Float),
    )
    metadata.create_all(engine)
    rows = [
        ("a", INBOUND, 0.85),
        ("b", INBOUND, 1.0),
        ("c", INBOUND, 5.48),
        ("d", OFFSHORE, 51.28),
        ("e", OFFSHORE, 70.0),
    ]
    session = sessionmaker(bind=engine)()
    try:
        session.execute(table.insert(), [{"id": i, "team": t, "score": s} for i, t, s in rows])
        query = select(table.c.id, score_percent_sql(table.c.score)).order_by(table.c.id)
        sql_values = {row[0]: row[1] for row in session.execute(query)}
    finally:
        session.close()
        engine.dispose()

    for item_id, team, stored in rows:
        assert sql_values[item_id] == pytest.approx(score_percent(stored))
    assert sql_values["a"] == pytest.approx(85.0)
    assert sql_values["d"] == pytest.approx(51.28)


def test_legacy_json_loader_applies_the_one_rule():
    ratio = _sanitize_performance_record_item({"team": INBOUND, "evaluation": {"score": 0.5}})
    percent = _sanitize_performance_record_item({"team": OFFSHORE, "evaluation": {"score": 51.28}})

    assert ratio["evaluation"]["score"] == 50.0
    assert percent["evaluation"]["score"] == 51.28
