from services.ai.orchestrator import _relative_period_note


def test_relative_period_note_for_last_month():
    note = _relative_period_note("which team is weakest last month?", "September 2026")
    assert note and "September 2026" in note


def test_relative_period_note_for_arabic_this_month():
    assert _relative_period_note("ايه اكتر KPI بيهبط الشهر ده؟", "October 2026")


def test_no_note_when_month_named_or_no_relative_words():
    assert _relative_period_note("weakest team in October 2026", "October 2026") is None
    assert _relative_period_note("last month in Oct 2026", "October 2026") is None
    assert _relative_period_note("weakest team", "October 2026") is None
    assert _relative_period_note("last month", "") is None
