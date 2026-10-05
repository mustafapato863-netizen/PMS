"""SEC-F1-R1 residual on PR #9: teams-only Manager edits must not widen levels.

The Settings user form re-sends ``accessible_teams`` (no
``accessible_team_levels``) on every edit. Previously that replaced all
assignments with all-levels (NULL) rows, turning a level-restricted Manager
into an unrestricted one.
"""

from __future__ import annotations

import uuid

from models.models import UserTeamAssignment
from services.auth_service import AuthenticationService

from tests.test_security_findings_f1_f4 import (  # noqa: F401  (pytest fixtures)
    _admin_headers,
    _seed_teams,
    db_session,
    users_client,
)


def _add_assignment(db_session, user_id, team, level):
    db_session.add(
        UserTeamAssignment(
            id=uuid.uuid4(),
            user_id=user_id,
            team_id=team.id,
            performance_level=level,
            access_level="admin",
            assigned_by="Admin",
        )
    )


def _employee_level_manager(db_session, teams, username="lvl_mgr"):
    manager = AuthenticationService.create_user(
        db_session, username, f"{username}@test.com", "SecurePassword123!", "Manager"
    )
    for team in teams:
        _add_assignment(db_session, manager.id, team, "Employee")
    db_session.commit()
    return manager


def _assignment_map(db_session, user_id):
    db_session.expire_all()
    rows = db_session.query(UserTeamAssignment).filter(UserTeamAssignment.user_id == user_id).all()
    return sorted((row.team_id, row.performance_level) for row in rows)


def _put(users_client, headers, manager, **extra):
    body = {
        "id": str(manager.id),
        "name": extra.pop("name", "Level Manager"),
        "username": manager.username,
        "role": extra.pop("role", "Manager"),
        "is_active": True,
    }
    body.update(extra)
    response = users_client.put(f"/api/users/{manager.id}", headers=headers, json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True, payload
    return payload["data"]


class TestSecF1R1RenamePreservesLevels:
    def test_fe_style_rename_keeps_employee_levels_and_flag_false(self, users_client, db_session):
        """Exact repro: FE rename sends accessible_teams (all 3) without levels."""
        teams = _seed_teams(db_session)
        manager = _employee_level_manager(db_session, teams)
        before = _assignment_map(db_session, manager.id)
        headers = _admin_headers(db_session, "admin_r1_a")

        data = _put(
            users_client,
            headers,
            manager,
            name="Renamed Level Manager",
            accessible_teams=[team.name for team in teams],
            has_unrestricted_team_access=False,
        )

        assert _assignment_map(db_session, manager.id) == before
        assert all(level == "Employee" for _tid, level in before)
        assert data["has_unrestricted_team_access"] is False
        assert data["name"] == "Renamed Level Manager"
        assert sorted(map(tuple, data["accessible_team_levels"])) == sorted(
            (team.name, "Employee") for team in teams
        )

    def test_rename_without_flag_or_teams_keeps_levels(self, users_client, db_session):
        teams = _seed_teams(db_session)
        manager = _employee_level_manager(db_session, teams, "lvl_mgr_omit")
        before = _assignment_map(db_session, manager.id)
        headers = _admin_headers(db_session, "admin_r1_b")

        data = _put(users_client, headers, manager, name="Only Renamed")

        assert _assignment_map(db_session, manager.id) == before
        assert data["has_unrestricted_team_access"] is False

    def test_rename_keeps_mixed_levels_partial_null_scope(self, users_client, db_session):
        """NULL on 2 of 3 teams + Employee on the 3rd stays not-full-scope."""
        teams = _seed_teams(db_session)
        manager = AuthenticationService.create_user(
            db_session, "mixed_mgr", "mixed@test.com", "SecurePassword123!", "Manager"
        )
        _add_assignment(db_session, manager.id, teams[0], None)
        _add_assignment(db_session, manager.id, teams[1], None)
        _add_assignment(db_session, manager.id, teams[2], "Employee")
        db_session.commit()
        before = _assignment_map(db_session, manager.id)
        headers = _admin_headers(db_session, "admin_r1_c")

        data = _put(
            users_client,
            headers,
            manager,
            name="Mixed Renamed",
            accessible_teams=[team.name for team in teams],
        )

        assert _assignment_map(db_session, manager.id) == before
        assert data["has_unrestricted_team_access"] is False


class TestSecF1R1TeamsOnlyEdit:
    def test_remove_team_keeps_levels_on_remaining(self, users_client, db_session):
        teams = _seed_teams(db_session)
        manager = _employee_level_manager(db_session, teams, "lvl_mgr_rm")
        headers = _admin_headers(db_session, "admin_r1_d")

        data = _put(
            users_client,
            headers,
            manager,
            accessible_teams=[teams[0].name, teams[1].name],
        )

        assert _assignment_map(db_session, manager.id) == sorted(
            [(teams[0].id, "Employee"), (teams[1].id, "Employee")]
        )
        assert set(data["accessible_teams"]) == {teams[0].name, teams[1].name}
        assert data["has_unrestricted_team_access"] is False

    def test_add_team_keeps_existing_levels_and_grants_only_new_team(self, users_client, db_session):
        teams = _seed_teams(db_session)
        manager = AuthenticationService.create_user(
            db_session, "lvl_mgr_add", "add@test.com", "SecurePassword123!", "Manager"
        )
        _add_assignment(db_session, manager.id, teams[0], "Employee")
        _add_assignment(db_session, manager.id, teams[1], "Employee")
        db_session.commit()
        headers = _admin_headers(db_session, "admin_r1_e")

        data = _put(
            users_client,
            headers,
            manager,
            accessible_teams=[team.name for team in teams],
        )

        assert _assignment_map(db_session, manager.id) == sorted(
            [(teams[0].id, "Employee"), (teams[1].id, "Employee"), (teams[2].id, None)]
        )
        # Existing teams still restricted -> not full NULL-level scope.
        assert data["has_unrestricted_team_access"] is False

    def test_teams_only_edit_is_case_insensitive_and_does_not_duplicate(self, users_client, db_session):
        teams = _seed_teams(db_session)
        manager = _employee_level_manager(db_session, teams, "lvl_mgr_case")
        before = _assignment_map(db_session, manager.id)
        headers = _admin_headers(db_session, "admin_r1_f")

        _put(
            users_client,
            headers,
            manager,
            accessible_teams=[team.name.upper() for team in teams] + [teams[0].name],
        )

        assert _assignment_map(db_session, manager.id) == before

    def test_empty_teams_list_removes_all(self, users_client, db_session):
        teams = _seed_teams(db_session)
        manager = _employee_level_manager(db_session, teams, "lvl_mgr_empty")
        headers = _admin_headers(db_session, "admin_r1_g")

        data = _put(users_client, headers, manager, accessible_teams=[])

        assert _assignment_map(db_session, manager.id) == []
        assert data["accessible_teams"] == []
        assert data["has_unrestricted_team_access"] is False


class TestSecF1R1ExplicitLevelsAndFlag:
    def test_explicit_levels_replace_assignments(self, users_client, db_session):
        teams = _seed_teams(db_session)
        manager = _employee_level_manager(db_session, teams, "lvl_mgr_explicit")
        headers = _admin_headers(db_session, "admin_r1_h")

        data = _put(
            users_client,
            headers,
            manager,
            accessible_teams=[teams[0].name, teams[1].name],
            accessible_team_levels=[[teams[0].name, "Employee"], [teams[1].name, "Managerial"]],
        )

        rows = _assignment_map(db_session, manager.id)
        levels = sorted(level for _tid, level in rows)
        assert levels == ["Employee", "Managerial"]
        assert all(tid != teams[2].id for tid, _level in rows)
        assert data["has_unrestricted_team_access"] is False
        assert sorted(map(tuple, data["accessible_team_levels"])) == sorted(
            [(teams[0].name, "Employee"), (teams[1].name, "Managerial")]
        )

    def test_explicit_levels_can_narrow_to_single_level(self, users_client, db_session):
        teams = _seed_teams(db_session)
        manager = AuthenticationService.create_user(
            db_session, "null_mgr_narrow", "narrow@test.com", "SecurePassword123!", "Manager"
        )
        for team in teams:
            _add_assignment(db_session, manager.id, team, None)
        db_session.commit()
        headers = _admin_headers(db_session, "admin_r1_i")

        data = _put(
            users_client,
            headers,
            manager,
            accessible_team_levels=[[team.name, "Employee"] for team in teams],
        )

        assert _assignment_map(db_session, manager.id) == sorted(
            (team.id, "Employee") for team in teams
        )
        assert data["has_unrestricted_team_access"] is False

    def test_explicit_unrestricted_flag_still_widens(self, users_client, db_session):
        teams = _seed_teams(db_session)
        manager = _employee_level_manager(db_session, teams, "lvl_mgr_widen")
        headers = _admin_headers(db_session, "admin_r1_j")

        data = _put(
            users_client,
            headers,
            manager,
            accessible_teams=[team.name for team in teams],
            has_unrestricted_team_access=True,
        )

        assert _assignment_map(db_session, manager.id) == sorted((team.id, None) for team in teams)
        assert data["has_unrestricted_team_access"] is True


class TestP3GeneralManagerDemote:
    def _make_gm(self, db_session, teams, username):
        gm = AuthenticationService.create_user(
            db_session, username, f"{username}@test.com", "SecurePassword123!", "General Manager"
        )
        for team in teams:
            _add_assignment(db_session, gm.id, team, None)
        db_session.commit()
        return gm

    def test_demote_gm_to_manager_without_teams_clears_all_teams(self, users_client, db_session):
        teams = _seed_teams(db_session)
        gm = self._make_gm(db_session, teams, "gm_demote")
        headers = _admin_headers(db_session, "admin_p3_a")

        data = _put(users_client, headers, gm, role="Manager")

        assert data["role"] == "Manager"
        assert _assignment_map(db_session, gm.id) == []
        assert data["has_unrestricted_team_access"] is False

    def test_demote_gm_to_manager_with_one_team(self, users_client, db_session):
        teams = _seed_teams(db_session)
        gm = self._make_gm(db_session, teams, "gm_demote_one")
        headers = _admin_headers(db_session, "admin_p3_b")

        data = _put(users_client, headers, gm, role="Manager", accessible_teams=[teams[0].name])

        assert _assignment_map(db_session, gm.id) == [(teams[0].id, None)]
        assert data["has_unrestricted_team_access"] is False
