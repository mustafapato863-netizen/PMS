from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy.orm import Session

from models.models import Action, Team, User
from repositories.action_repository import ActionRepository
from utils.report_scope import user_can_access_team
from utils.team_identity import logical_team_name


class TeamActionService:
    def __init__(self, db: Session):
        self.db = db
        self.actions = ActionRepository(db)

    # Frontend route id → display_name of the team row that stores its team-level
    # notes. Mirrors the canonical route ids in types.ts TEAM_ID_MAP (plus the legacy
    # ids and the elective display slug the frontend still accepts).
    _SLUG_ALIASES: dict[str, str] = {
        "rcm": "RCM",
        "call-center": "Call Center",
        "pre-approvals-uae": "Pre-Approvals",
        "inbound": "Inbound",
        "outbound": "Outbound",
        "inbound-uae": "Inbound UAE",
        "pre-approvals": "Pre-Approvals IP Offshore",
        "sales": "Sales",
        "coding": "Coding",
        "csr": "CSR",
        "pharmacy": "Pharmacy",
        "submission": "Submission",
        "re-submission": "Re-Submission",
        "pre-approvals-op-dubai": "Pre-Approvals OP Dubai",
        # Final Pre-Approvals teams are presentation-level teams backed by
        # source teams. Actions remain persisted on the existing employee
        # team row until a shared action identity is introduced.
        "pre-approvals-op-final": "Pre-Approvals OP Dubai",
        "pre-approvals-op-final-shj-ajm": "Pre-Approvals OP Dubai",
        "pre-approvals-ip-final-dubai": "Pre-Approvals IP Final Dubai",
        "pre-approvals-ip-final": "Pre-Approvals IP Final Dubai",
        "pre-approvals-ip-final-shj-ajm": "Pre-Approvals IP Final Dubai",
        "pre-approvals-ip-elective": "Pre-Approvals IP Elective Dubai",
        "pre-approvals-ip-elective-dubai": "Pre-Approvals IP Elective Dubai",
        "marketing": "Marketing",
    }
    # Parent views. Call Center is a merged dashboard backed by Inbound and Outbound;
    # its employee-level identity may be inactive after the source teams were split,
    # but the dashboard still stores a parent-level action. RCM and the UAE
    # Pre-Approvals parent are looked up the same way.
    _PARENT_ROUTES: frozenset[str] = frozenset({"call-center", "rcm", "pre-approvals-uae"})

    @staticmethod
    def _route_slug(value: str) -> str:
        return str(value).strip().casefold().replace("_", "-").replace(" ", "-")

    def _team(self, reference: str) -> Team:
        normalized = self._route_slug(reference)
        if not normalized:
            raise ValueError("Team not found")
        # A route id names the team row that stores its notes. Any other reference is
        # matched only against a team's own names: the alias of one team is never
        # offered to every team, which is how every page used to land on the first row.
        alias = self._SLUG_ALIASES.get(normalized)
        wanted = self._route_slug(alias if alias is not None else reference)
        query = self.db.query(Team).filter(Team.team_level == "employee")
        if normalized not in self._PARENT_ROUTES:
            query = query.filter(Team.is_active.is_(True))
        teams = query.all()
        matches = [team for team in teams if self._route_slug(logical_team_name(team)) == wanted]
        if not matches and alias is None:
            matches = [
                team
                for team in teams
                if normalized in {str(team.id).casefold(), self._route_slug(team.name), self._route_slug(team.db_name)}
            ]
        if not matches:
            raise ValueError("Team not found")
        if len(matches) > 1:
            raise ValueError("Team reference matches more than one team")
        return matches[0]

    @staticmethod
    def _ensure_team_action_scope(scope: dict, team_name: str) -> None:
        # Team-wide notes have no branch attribution, so a branch-scoped role
        # cannot safely read or change them until the data model is branch-aware.
        role = str(scope.get("role", "")).strip().casefold().replace("_", " ")
        if role == "branch director":
            raise PermissionError("Branch Directors cannot access unscoped team actions")
        if not user_can_access_team(scope, team_name):
            raise PermissionError("The team is outside your authorized action scope")

    @staticmethod
    def _serialize(action: Action) -> dict:
        return {
            "team_id": logical_team_name(action.team),
            "month": action.month,
            "year": action.year,
            "overall_action": action.action_text,
            "updated_at": (action.updated_at or action.created_at).isoformat() if (action.updated_at or action.created_at) else None,
            "updated_by": action.updated_by_user.username if action.updated_by_user else "Admin",
        }

    def get(self, *, team_reference: str, month: str, year: int, scope: dict) -> dict | None:
        team = self._team(team_reference)
        team_name = logical_team_name(team)
        self._ensure_team_action_scope(scope, team_name)
        action = self.actions.get_active_team_summary(team.id, month, year)
        return self._serialize(action) if action else None

    def save(
        self,
        *,
        team_reference: str,
        month: str,
        year: int,
        overall_action: str,
        scope: dict,
        user_id: str | None,
    ) -> dict:
        team = self._team(team_reference)
        team_name = logical_team_name(team)
        self._ensure_team_action_scope(scope, team_name)

        actor_id = None
        try:
            candidate = uuid.UUID(str(user_id)) if user_id else None
            if candidate and self.db.query(User.id).filter(User.id == candidate).first():
                actor_id = candidate
        except (TypeError, ValueError):
            actor_id = None

        try:
            action = self.actions.get_active_team_summary(team.id, month, year)
            if action:
                action.action_text = overall_action.strip()
                action.updated_by_user_id = actor_id
                action.updated_at = dt.datetime.now(dt.timezone.utc)
            else:
                action = Action(
                    team_id=team.id,
                    employee_id=None,
                    month=month,
                    year=year,
                    action_type="Team Action",
                    action_text=overall_action.strip(),
                    status="Open",
                    is_active=True,
                    created_by_user_id=actor_id,
                    updated_by_user_id=actor_id,
                )
                self.actions.add(action)
            self.db.commit()
            self.db.refresh(action)
            return self._serialize(action)
        except Exception:
            self.db.rollback()
            raise
