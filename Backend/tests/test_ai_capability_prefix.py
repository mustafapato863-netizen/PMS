"""'What can you do? Also <question>' answers both halves instead of dropping the first."""
from services.ai.orchestrator import CAPABILITY_SUMMARY, split_leading_capability_question


def test_split_returns_the_real_question():
    assert split_leading_capability_question(
        "What can you do? Also who is the top employee in Inbound in September 2026?"
    ) == "who is the top employee in Inbound in September 2026?"
    assert split_leading_capability_question(
        "How can you help me? Also why is Marketing low in September?"
    ) == "why is Marketing low in September?"


def test_plain_questions_are_not_split():
    assert split_leading_capability_question("What can you do?") is None
    assert split_leading_capability_question("who is the top employee in Inbound?") is None
    assert split_leading_capability_question("what can you do about Coding EGY in September 2026?") is None


def test_capability_summary_is_short_and_factual():
    assert len(CAPABILITY_SUMMARY) < 200 and "verified PMS performance" in CAPABILITY_SUMMARY
