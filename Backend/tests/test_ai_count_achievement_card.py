"""Item 3(c) (PR #84): a count headline must not sit next to a KPI
Achievement card showing rate achievements.

Background: for "How many Clinics bookings in September 2026?" the headline
correctly reads "Bookings (Count) reached 30 count", but the answer also
carried a "KPI Achievement Breakdown" card whose bars were the Booking Rate
and other rate achievements (e.g. "93.3% ach"). Those achievements belong to
unrelated rate KPIs, not to the count the question asked about, so the card
is omitted for count-kind questions. For a rate question the card stays:
it is the achievement breakdown of the metric actually asked about.

The KPI Diagnosis & Target Gap table is unchanged: it is labelled per KPI
(actual vs target) and remains legitimate diagnostic context.
"""
from __future__ import annotations

import pytest

from test_ai_booking_count_parity import _ask


def _achievement_cards(res):
    return [
        c
        for c in (res.visual_cards or [])
        if (c.title or "").startswith("KPI Achievement Breakdown")
    ]


def test_count_question_has_no_kpi_achievement_card(monkeypatch):
    res = _ask(monkeypatch, "How many Clinics bookings in September 2026?")
    assert "Bookings (Count) reached 30" in res.headline
    assert _achievement_cards(res) == [], (
        "a count headline must not sit next to rate achievements: "
        f"found {[c.title for c in _achievement_cards(res)]}"
    )


def test_count_question_inbound_bookings_has_no_kpi_achievement_card(monkeypatch):
    res = _ask(monkeypatch, "How many Inbound bookings in September 2026?")
    assert "Bookings (Count) reached 500" in res.headline
    assert _achievement_cards(res) == []


def test_rate_question_keeps_kpi_achievement_card(monkeypatch):
    res = _ask(monkeypatch, "What is the Inbound Booking Rate in September 2026?")
    assert "Booking Rate is at 28.0%" in res.headline
    cards = _achievement_cards(res)
    assert cards, "a rate question should still carry its achievement breakdown"
    assert any("Booking Rate" in (b.label or "") for b in cards[0].bars)
