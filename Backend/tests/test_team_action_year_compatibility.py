from models.schemas import TeamAction
from repositories import json_repos
from repositories.json_repos import JSONTeamActionsRepository


def action(year: int, text: str) -> TeamAction:
    return TeamAction(team_id="inbound", month="June", year=year, overall_action=text, updated_at="2026-07-18T00:00:00")


def test_team_action_keys_do_not_collide_across_years(tmp_path, monkeypatch):
    monkeypatch.setattr(json_repos, "DATA_DIR", str(tmp_path))
    json_repos._cache.clear()
    repository = JSONTeamActionsRepository()
    repository.save(action(2025, "Prior year"))
    repository.save(action(2026, "Current year"))
    assert repository.get_action("inbound", "June", 2025).overall_action == "Prior year"
    assert repository.get_action("inbound", "June", 2026).overall_action == "Current year"


def test_year_aware_read_can_fall_back_to_legacy_record(tmp_path, monkeypatch):
    monkeypatch.setattr(json_repos, "DATA_DIR", str(tmp_path))
    json_repos._cache.clear()
    repository = JSONTeamActionsRepository()
    legacy = TeamAction(team_id="inbound", month="June", overall_action="Legacy", updated_at="2026-07-18T00:00:00")
    repository.save(legacy)
    assert repository.get_action("inbound", "June", 2026).overall_action == "Legacy"
