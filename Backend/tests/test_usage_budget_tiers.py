"""Tests for persona-tier usage budgets."""

import pytest

from services.ai.usage_budget import TIER_BUDGETS, tier_budget_for_role


def test_tier_budgets_defined():
    assert TIER_BUDGETS["global_exec"]["daily_turns"] == 100
    assert TIER_BUDGETS["scoped_manager"]["daily_turns"] == 50
    assert TIER_BUDGETS["self_only"]["daily_turns"] == 20
    assert TIER_BUDGETS["self_only"]["daily_tokens"] == 10_000


def test_tier_budget_admin():
    budget = tier_budget_for_role("Admin")
    assert budget["daily_turns"] == 100


def test_tier_budget_manager():
    budget = tier_budget_for_role("Manager")
    assert budget["daily_turns"] == 50


def test_tier_budget_agent():
    budget = tier_budget_for_role("Agent")
    assert budget["daily_turns"] == 20


def test_tier_budget_unknown_defaults_to_self_only():
    budget = tier_budget_for_role(None)
    assert budget["daily_turns"] == 20
