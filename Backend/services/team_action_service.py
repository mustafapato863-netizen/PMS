from __future__ import annotations

import datetime as dt
import json
import uuid
from typing import Any, Optional

from sqlalchemy.orm import Session

from models.models import Action, Team, User
from repositories.action_repository import ActionRepository
from services.corrective_action_service import month_match_values
from utils.regions import first_region
from utils.report_scope import user_can_access_region, user_can_access_team
from utils.team_identity import logical_team_name

_COHORT_PLAN_PREFIX = "cohort-plan:"
_VALID_PLAN_ITEM_STATUSES = frozenset({"Open", "In Progress", "Completed", "Planned"})


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

    def _team(self, reference: str, region: Optional[str] = None) -> Team:
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
        region_key = first_region(region).casefold()
        if region_key and matches:
            region_matches = [
                team
                for team in matches
                if first_region(getattr(team, "region", None)).casefold() == region_key
            ]
            if region_matches:
                matches = region_matches
            elif any(first_region(getattr(team, "region", None)) for team in matches):
                matches = []
        if not matches and region_key == "egy":
            egy_slugs = {f"{wanted}-egy", f"{wanted}-eg"}
            if wanted == "re-submission":
                egy_slugs.add("resubmission")
            matches = [
                team
                for team in teams
                if first_region(getattr(team, "region", None)).casefold() == "egy"
                and (
                    self._route_slug(logical_team_name(team)) in egy_slugs
                    or self._route_slug(team.name) in egy_slugs
                    or self._route_slug(team.db_name) in egy_slugs
                )
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
    def _scope_from_current_user(current_user: Any) -> dict:
        if isinstance(current_user, dict):
            return current_user
        if current_user is None:
            return {}
        return {
            "user_id": str(getattr(current_user, "id", "") or ""),
            "role": str(getattr(current_user, "role", "") or ""),
            "accessible_teams": list(getattr(current_user, "accessible_teams", []) or []),
            "accessible_regions": list(getattr(current_user, "accessible_regions", []) or []),
            "accessible_functions": list(getattr(current_user, "accessible_functions", []) or []),
            "has_unrestricted_team_access": bool(getattr(current_user, "has_unrestricted_team_access", False)),
        }

    @staticmethod
    def _ensure_region_scope(scope: dict, resolved_team: Team) -> None:
        role = str(scope.get("role", "")).strip()
        is_global = role in {"Admin", "General Manager", "Performance Team"} or bool(scope.get("has_unrestricted_team_access"))
        if role == "Regional Manager" or (not is_global and scope.get("accessible_regions")):
            if not user_can_access_region(scope, getattr(resolved_team, "region", None)):
                raise PermissionError("The team region is outside your authorized scope")

    @staticmethod
    def _parse_due_date(value: Any) -> dt.date | None:
        if value is None or value == "":
            return None
        if isinstance(value, dt.datetime):
            return value.date()
        if isinstance(value, dt.date):
            return value
        raw = str(value).strip()
        if not raw:
            return None
        try:
            return dt.date.fromisoformat(raw[:10])
        except ValueError as exc:
            raise ValueError(f"Invalid due_date: {value}") from exc

    @staticmethod
    def _serialize_plan_item(action: Action, resolved_team: Team | None = None) -> dict:
        team_obj = resolved_team or action.team
        evidence_ref = str(action.evidence_reference or "")
        card_id = evidence_ref[len(_COHORT_PLAN_PREFIX):] if evidence_ref.startswith(_COHORT_PLAN_PREFIX) else str(action.id)
        meta: dict[str, Any] = {}
        if action.root_cause_note:
            try:
                parsed = json.loads(action.root_cause_note)
                if isinstance(parsed, dict):
                    meta = parsed
            except (TypeError, ValueError):
                meta = {}
        ui_status = str(meta.get("ui_status") or action.status or "Open")
        if ui_status not in _VALID_PLAN_ITEM_STATUSES:
            ui_status = action.status or "Open"
        timestamp = action.updated_at or action.created_at
        return {
            "id": str(action.id),
            "card_id": card_id,
            "team": logical_team_name(team_obj) if team_obj else "",
            "region": getattr(team_obj, "region", None) if team_obj else None,
            "month": action.month,
            "year": action.year,
            "title": action.action_text,
            "target_kpi": str(meta.get("target_kpi") or ""),
            "scope_description": str(meta.get("scope_description") or ""),
            "owner": str(meta.get("owner") or ""),
            "status": ui_status,
            "due_date": action.due_date.isoformat() if action.due_date else None,
            "expected_team_impact": str(meta.get("expected_team_impact") or ""),
            "updated_at": timestamp.isoformat() if timestamp else None,
        }

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

    def _actor_uuid(self, user_id: Any) -> uuid.UUID | None:
        try:
            candidate = uuid.UUID(str(user_id)) if user_id else None
            if candidate and self.db.query(User.id).filter(User.id == candidate).first():
                return candidate
        except (TypeError, ValueError):
            return None
        return None

    def list_plan_items(
        self,
        team_name: str,
        month: str,
        year: int,
        current_user: Any = None,
        region: Optional[str] = None,
    ) -> list[dict]:
        scope = self._scope_from_current_user(current_user)
        if not scope:
            raise PermissionError("Authentication required")
        resolved_team = self._team(team_name, region=region)
        resolved_name = logical_team_name(resolved_team)
        self._ensure_team_action_scope(scope, resolved_name)
        self._ensure_region_scope(scope, resolved_team)

        month_clean = str(month or "").strip()
        if not month_clean:
            raise ValueError("month is required")
        month_variants = month_match_values(month_clean)
        rows = self.actions.list_active_cohort_plan_items(resolved_team.id, month_variants, int(year))
        return [self._serialize_plan_item(row, resolved_team) for row in rows]

    def save_plan_item(self, payload: dict, current_user: Any = None) -> dict:
        scope = self._scope_from_current_user(current_user)
        if not scope:
            raise PermissionError("Authentication required")

        card_id = str(payload.get("card_id") or "").strip()
        if not card_id:
            raise ValueError("card_id is required")
        team_ref = str(payload.get("team") or payload.get("team_id") or "").strip()
        if not team_ref:
            raise ValueError("team is required")
        month_clean = str(payload.get("month") or "").strip()
        if not month_clean:
            raise ValueError("month is required")
        try:
            year_val = int(payload["year"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Valid year is required") from exc
        if year_val < 2000 or year_val > 2100:
            raise ValueError("Year out of range")

        title = str(payload.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")

        ui_status = str(payload.get("status") or "Open").strip()
        if ui_status not in _VALID_PLAN_ITEM_STATUSES:
            raise ValueError(f"Invalid status: {ui_status}")
        db_status = "Open" if ui_status == "Planned" else ui_status
        parsed_due = self._parse_due_date(payload.get("due_date"))

        resolved_team = self._team(team_ref, region=payload.get("region"))
        resolved_name = logical_team_name(resolved_team)
        self._ensure_team_action_scope(scope, resolved_name)
        self._ensure_region_scope(scope, resolved_team)

        actor_id = self._actor_uuid(scope.get("user_id"))
        month_variants = month_match_values(month_clean)
        evidence_ref = f"{_COHORT_PLAN_PREFIX}{card_id}"
        meta_json = json.dumps(
            {
                "target_kpi": str(payload.get("target_kpi") or "").strip(),
                "scope_description": str(payload.get("scope_description") or "").strip(),
                "owner": str(payload.get("owner") or "").strip(),
                "expected_team_impact": str(payload.get("expected_team_impact") or "").strip(),
                "ui_status": ui_status,
            }
        )

        try:
            action = self.actions.get_active_cohort_plan_item(
                resolved_team.id,
                month_variants,
                year_val,
                card_id,
            )
            now = dt.datetime.now(dt.timezone.utc)
            if action:
                action.plan_title = title[:255]
                action.action_text = title
                action.root_cause_note = meta_json
                action.status = db_status
                action.due_date = parsed_due
                action.updated_by_user_id = actor_id
                action.updated_at = now
            else:
                action = Action(
                    team_id=resolved_team.id,
                    employee_id=None,
                    month=month_clean,
                    year=year_val,
                    action_type="Team Action",
                    plan_title=title[:255],
                    action_text=title,
                    root_cause_note=meta_json,
                    status=db_status,
                    due_date=parsed_due,
                    evidence_reference=evidence_ref,
                    is_active=True,
                    created_by_user_id=actor_id,
                    updated_by_user_id=actor_id,
                )
                self.actions.add(action)
            self.db.commit()
            self.db.refresh(action)
            return self._serialize_plan_item(action, resolved_team)
        except Exception:
            self.db.rollback()
            raise
