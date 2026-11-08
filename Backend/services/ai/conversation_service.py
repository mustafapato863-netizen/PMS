from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from api.dependencies import build_user_scope_from_db_user
from models.ai_schemas import (
    AiClarificationPrompt,
    AiConversationContextPayload,
    ClarificationChoice,
    ConfirmedQueryContext,
    SessionFilterContext,
)
from models.models import AiConversation, AiTurn, User
from repositories.ai_conversation_repository import (
    AiConversationRepository,
    ConversationAccessError,
    ConversationDeletedError,
    ConversationMigrationUnavailableError,
    ConversationOwnershipError,
    ConversationStaleContextError,
    ConversationVersionConflictError,
    RequestIdReuseConflictError,
    TurnAlreadyInFlightError,
    compute_request_fingerprint,
    compute_scope_fingerprint,
)
from services.ai.catalog import evaluation_cache_identity
from services.ai.trace_logger import sanitize_prompt_for_router_training
from services.cache_invalidation_service import CacheInvalidationService
from services.dashboard_record_service import DashboardRecordService
from services.insights_service import InsightAccessError
from utils.report_scope import (
    FUNCTION_SCOPED_ROLES,
    SELF_SCOPED_ROLES,
    filter_records_by_scope,
    user_can_access_team,
    user_can_access_team_level,
)

__all__ = [
    "AiConversationService",
    "ConversationAccessError",
    "ConversationDeletedError",
    "ConversationMigrationUnavailableError",
    "ConversationOwnershipError",
    "ConversationStaleContextError",
    "ConversationVersionConflictError",
    "RequestIdReuseConflictError",
    "TurnAlreadyInFlightError",
    "compute_request_fingerprint",
    "compute_scope_fingerprint",
]


class AiConversationService:
    """Service layer for managing server-owned AI conversations, live RBAC revalidation, and context sanitization."""

    def __init__(self, db: Session, scope: dict[str, Any] | None = None) -> None:
        self.db = db
        self.scope = scope if scope is not None else {}
        self.repo = AiConversationRepository(db)
        self.owner_user_id = str(self.scope.get("user_id") or "anonymous")
        self.owner_role = str(self.scope.get("role") or "Manager")

    def is_schema_ready(self) -> bool:
        return self.repo.is_schema_ready()

    def _resolve_owner(self, scope: dict[str, Any] | None) -> tuple[str, str]:
        eff_scope = scope if scope is not None else self.scope
        return (
            str(eff_scope.get("user_id") or self.owner_user_id or "anonymous"),
            str(eff_scope.get("role") or self.owner_role or "Manager"),
        )

    def validate_live_account_and_scope(self, scope: dict[str, Any] | None = None) -> dict[str, Any]:
        """Rebuild and revalidate current account status, role, and all assignment tables from the authoritative DB mechanism."""
        target_dict = scope if scope is not None else self.scope
        eff_scope = dict(target_dict)
        if eff_scope.get("is_active") is False:
            raise InsightAccessError("User account is inactive or access has been revoked.")

        uid_str = str(eff_scope.get("user_id") or "").strip()
        was_db_backed = bool(eff_scope.get("_db_user_verified") or eff_scope.get("user") is not None)

        if uid_str and uid_str != "anonymous":
            parsed_uid: uuid.UUID | None = None
            try:
                parsed_uid = uuid.UUID(uid_str)
            except (ValueError, TypeError):
                parsed_uid = None

            if parsed_uid is not None:
                try:
                    user_row = self.db.query(User).filter(User.id == parsed_uid).first()
                except Exception as exc:
                    raise InsightAccessError("Unable to verify live user authorization state.") from exc

                if user_row is not None:
                    if not bool(getattr(user_row, "is_active", True)):
                        raise InsightAccessError("User account is inactive or access has been revoked.")
                    try:
                        live_scope = build_user_scope_from_db_user(self.db, user_row)
                    except Exception as exc:
                        raise InsightAccessError("Unable to rebuild live user authorization scope.") from exc
                    eff_scope.update(live_scope)
                    if isinstance(target_dict, dict):
                        target_dict.update(live_scope)
                    if isinstance(self.scope, dict) and str(self.scope.get("user_id") or "") == uid_str:
                        self.scope.update(live_scope)
                    self.owner_user_id = str(eff_scope.get("user_id") or "anonymous")
                    self.owner_role = str(eff_scope.get("role") or "Manager")
                elif was_db_backed:
                    raise InsightAccessError("Authenticated user account no longer exists.")

        role_now = str(eff_scope.get("role") or "Manager")
        if role_now in SELF_SCOPED_ROLES:
            eff_scope["is_self_only"] = True
            if isinstance(target_dict, dict):
                target_dict["is_self_only"] = True
        return eff_scope

    def _is_branch_authorized(self, branch: str | None, eff_scope: dict[str, Any]) -> bool:
        if not branch:
            return True
        b_norm = str(branch).strip().casefold()
        role = str(eff_scope.get("role") or "")
        allowed_branches = [
            str(x).strip().casefold()
            for x in (eff_scope.get("accessible_branches") or eff_scope.get("allowed_branches") or [])
            if str(x).strip()
        ]
        if b_norm in {"all", "all branches"}:
            if role == "Branch Director":
                return len(set(allowed_branches)) >= 4
            return True
        if role == "Branch Director" or allowed_branches:
            if not allowed_branches:
                return False
            return b_norm in set(allowed_branches)
        return True

    def _is_function_authorized(self, function_name: str | None, eff_scope: dict[str, Any]) -> bool:
        if not function_name:
            return True
        role = str(eff_scope.get("role") or "")
        if role in FUNCTION_SCOPED_ROLES:
            allowed_fns = {
                str(x).strip().casefold()
                for x in (eff_scope.get("accessible_functions") or eff_scope.get("allowed_functions") or [])
                if str(x).strip()
            }
            return str(function_name).strip().casefold() in allowed_fns
        return True

    def _is_team_and_level_authorized(
        self,
        team_name: str | None,
        performance_level: str | None,
        eff_scope: dict[str, Any],
    ) -> bool:
        role = str(eff_scope.get("role") or "")
        lvl = str(performance_level or "Employee").strip()
        if lvl in ("Corporate", "Managerial"):
            if bool(eff_scope.get("is_self_only")) or role in SELF_SCOPED_ROLES:
                return False
        if team_name:
            if not user_can_access_team(eff_scope, team_name):
                return False
            if not user_can_access_team_level(eff_scope, team_name, lvl):
                return False
        elif lvl in ("Corporate", "Managerial"):
            # Even if team is not explicitly set, verify the user has at least one team grant at that level
            if not eff_scope.get("has_unrestricted_team_access") and role not in {
                "Admin",
                "General Manager",
                "Performance Team",
                "Viewer",
            }:
                team_levels = eff_scope.get("accessible_team_levels") or []
                if team_levels:
                    has_lvl = any(
                        isinstance(item, (list, tuple))
                        and len(item) >= 2
                        and str(item[1]).strip().casefold() == lvl.casefold()
                        for item in team_levels
                    )
                    if not has_lvl:
                        return False
        return True

    def _is_employee_authorized_for_scope(
        self,
        employee_id: str | None,
        employee_name: str | None,
        eff_scope: dict[str, Any],
    ) -> bool:
        if not employee_id and not employee_name:
            return True
        role = str(eff_scope.get("role") or "")
        is_self_only = bool(eff_scope.get("is_self_only")) or (role in SELF_SCOPED_ROLES)
        caller_emp_id = str(eff_scope.get("employee_id") or "").strip()

        if is_self_only:
            if not caller_emp_id:
                return False
            if employee_id and str(employee_id).strip().casefold() != caller_emp_id.casefold():
                return False

        try:
            all_recs = DashboardRecordService(self.db).list_analysis_records() or []
        except Exception:
            return False

        emp_id_norm = str(employee_id or "").strip().casefold()
        emp_name_norm = str(employee_name or "").strip().casefold()

        matching_all = [
            r
            for r in all_recs
            if (emp_id_norm and str(getattr(r, "employee_id", "") or "").strip().casefold() == emp_id_norm)
            or (emp_name_norm and str(getattr(r, "employee_name", "") or "").strip().casefold() == emp_name_norm)
        ]
        scoped_recs = filter_records_by_scope(all_recs, eff_scope)
        matching_scoped = [
            r
            for r in scoped_recs
            if (emp_id_norm and str(getattr(r, "employee_id", "") or "").strip().casefold() == emp_id_norm)
            or (emp_name_norm and str(getattr(r, "employee_name", "") or "").strip().casefold() == emp_name_norm)
        ]

        if matching_all:
            return len(matching_scoped) > 0

        # If no records exist in the dataset for this employee at all:
        if is_self_only:
            return bool(emp_id_norm and caller_emp_id and emp_id_norm == caller_emp_id.casefold())
        if not eff_scope.get("has_unrestricted_team_access") and role not in {
            "Admin",
            "General Manager",
            "Performance Team",
        }:
            return False
        return True

    def is_plan_and_context_authorized(
        self,
        *,
        scope: dict[str, Any],
        team: str | None = None,
        function: str | None = None,
        branch: str | None = None,
        branches: list[str] | None = None,
        performance_level: str | None = None,
        employee_id: str | None = None,
        employee_name: str | None = None,
    ) -> bool:
        """Check whether the given query plan / context dimensions are authorized under live scope."""
        if not self._is_function_authorized(function, scope):
            return False
        if not self._is_team_and_level_authorized(team, performance_level, scope):
            return False
        if not self._is_branch_authorized(branch, scope):
            return False
        for b in branches or []:
            if not self._is_branch_authorized(b, scope):
                return False
        if not self._is_employee_authorized_for_scope(employee_id, employee_name, scope):
            return False
        return True

    def is_returned_evidence_authorized(
        self,
        *,
        scope: dict[str, Any],
        typed_evidence: list[Any] | None = None,
        tool_digests: list[dict[str, Any]] | None = None,
        fallback_branch: str | None = None,
        fallback_level: str | None = None,
    ) -> bool:
        """Verify that every returned evidence item and tool digest is authorized under the live scope."""
        eff_level = str(fallback_level or "Employee")
        for tev in typed_evidence or []:
            t_team = getattr(tev, "team", None) if not isinstance(tev, dict) else tev.get("team")
            t_lvl = (
                (getattr(tev, "performance_level", None) if not isinstance(tev, dict) else tev.get("performance_level"))
                or eff_level
            )
            t_branch = getattr(tev, "branch", None) if not isinstance(tev, dict) else tev.get("branch")
            eff_branch = t_branch if t_branch and str(t_branch).strip().casefold() not in {"all", "all branches"} else fallback_branch
            if not self.is_plan_and_context_authorized(
                scope=scope,
                team=str(t_team) if t_team else None,
                branch=str(eff_branch) if eff_branch else None,
                performance_level=str(t_lvl) if t_lvl else None,
            ):
                return False

        for td in tool_digests or []:
            if not isinstance(td, dict):
                continue
            d_team = td.get("team")
            d_lvl = td.get("performance_level") or eff_level
            d_branch = td.get("branch")
            d_emp_id = td.get("employee_id")
            d_emp_name = td.get("employee_name")
            if (d_team or d_branch or d_emp_id or d_emp_name) and not self.is_plan_and_context_authorized(
                scope=scope,
                team=str(d_team) if d_team else None,
                branch=str(d_branch) if d_branch and str(d_branch).strip().casefold() not in {"all", "all branches"} else fallback_branch,
                performance_level=str(d_lvl) if d_lvl else None,
                employee_id=str(d_emp_id) if d_emp_id else None,
                employee_name=str(d_emp_name) if d_emp_name else None,
            ):
                return False

            sp = td.get("spotlight") or td.get("agent_spotlight")
            if isinstance(sp, dict):
                sp_team = sp.get("team") or d_team
                sp_emp_id = sp.get("entity_id") or sp.get("employee_id")
                sp_emp_name = sp.get("entity_name") or sp.get("employee_name")
                if not self.is_plan_and_context_authorized(
                    scope=scope,
                    team=str(sp_team) if sp_team else None,
                    performance_level=str(d_lvl),
                    employee_id=str(sp_emp_id) if sp_emp_id else None,
                    employee_name=str(sp_emp_name) if sp_emp_name else None,
                ):
                    return False

            for list_key in ("ranked_employees", "top_agents", "bottom_agents"):
                emp_list = td.get(list_key)
                if isinstance(emp_list, list):
                    for emp in emp_list:
                        if not isinstance(emp, dict):
                            continue
                        e_id = emp.get("employee_id") or emp.get("entity_id")
                        e_name = emp.get("employee_name") or emp.get("entity_name")
                        e_team = emp.get("team") or d_team
                        e_branch = emp.get("branch")
                        if not self.is_plan_and_context_authorized(
                            scope=scope,
                            team=str(e_team) if e_team else None,
                            branch=str(e_branch) if e_branch and str(e_branch).strip().casefold() != "all" else None,
                            performance_level=str(d_lvl),
                            employee_id=str(e_id) if e_id else None,
                            employee_name=str(e_name) if e_name else None,
                        ):
                            return False

            for b_key in ("branch_rows", "branches"):
                b_list = td.get(b_key)
                if isinstance(b_list, list):
                    for br in b_list:
                        if isinstance(br, dict) and br.get("branch"):
                            if not self._is_branch_authorized(str(br.get("branch")), scope):
                                return False
        return True

    def _is_turn_evidence_authorized(self, turn_row: AiTurn, eff_scope: dict[str, Any]) -> bool:
        """Revalidate access to the specific stored plan, response payload, and evidence items before replaying."""
        v_plan = turn_row.validated_plan if isinstance(turn_row.validated_plan, dict) else {}
        plan_scope = v_plan.get("scope") if isinstance(v_plan.get("scope"), dict) else {}
        resp = turn_row.response_payload if isinstance(turn_row.response_payload, dict) else {}
        struct_q = resp.get("structured_query") if isinstance(resp.get("structured_query"), dict) else {}
        resolved_st = resp.get("resolved_session_state") if isinstance(resp.get("resolved_session_state"), dict) else {}
        lcq = resolved_st.get("last_confirmed_query") if isinstance(resolved_st.get("last_confirmed_query"), dict) else {}

        teams_to_check = [
            plan_scope.get("team"),
            struct_q.get("team"),
            resolved_st.get("team"),
            lcq.get("team"),
        ]
        levels_to_check = [
            plan_scope.get("performance_level"),
            struct_q.get("performance_level"),
            resolved_st.get("performance_level"),
            lcq.get("performance_level"),
        ]
        eff_level = next((str(lv) for lv in levels_to_check if lv), "Employee")
        for t in teams_to_check:
            if t and not self._is_team_and_level_authorized(str(t), eff_level, eff_scope):
                return False
        if not any(teams_to_check) and eff_level in ("Corporate", "Managerial"):
            if not self._is_team_and_level_authorized(None, eff_level, eff_scope):
                return False

        for fn in (plan_scope.get("function"), struct_q.get("function"), resolved_st.get("function"), lcq.get("function")):
            if fn and not self._is_function_authorized(str(fn), eff_scope):
                return False

        branches_to_check: list[str] = []
        for b in (
            plan_scope.get("branch"),
            struct_q.get("branch"),
            struct_q.get("compare_branch"),
            resolved_st.get("branch"),
            lcq.get("branch"),
        ):
            if b:
                branches_to_check.append(str(b))
        for blist in (plan_scope.get("branches"), struct_q.get("branches"), lcq.get("branches")):
            if isinstance(blist, list):
                branches_to_check.extend(str(x) for x in blist if x)
        for b in branches_to_check:
            if not self._is_branch_authorized(b, eff_scope):
                return False

        emp_id = (
            plan_scope.get("employee_id")
            or struct_q.get("employee_id")
            or resolved_st.get("employee_id")
            or lcq.get("last_subject_employee_id")
        )
        emp_name = (
            plan_scope.get("employee_name")
            or struct_q.get("employee_name")
            or lcq.get("last_subject_employee_name")
        )
        if (emp_id or emp_name) and not self._is_employee_authorized_for_scope(
            str(emp_id) if emp_id else None,
            str(emp_name) if emp_name else None,
            eff_scope,
        ):
            return False

        # Also validate every evidence item in evidence_summary and response_payload
        ev_sum = turn_row.evidence_summary if isinstance(turn_row.evidence_summary, dict) else {}
        ev_items = list(ev_sum.get("items") or []) + list(resp.get("evidence_envelope_v2") or [])
        for item in ev_items:
            if not isinstance(item, dict):
                continue
            item_scope = item.get("scope") if isinstance(item.get("scope"), dict) else {}
            it_team = item_scope.get("team")
            it_lvl = item_scope.get("performance_level") or eff_level
            it_fn = item_scope.get("function")
            it_branch = item_scope.get("branch")
            it_emp_id = item_scope.get("employee_id")
            it_emp_name = item_scope.get("employee_name")
            if not self.is_plan_and_context_authorized(
                scope=eff_scope,
                team=str(it_team) if it_team else None,
                function=str(it_fn) if it_fn else None,
                branch=str(it_branch) if it_branch else None,
                branches=item_scope.get("branches") if isinstance(item_scope.get("branches"), list) else None,
                performance_level=str(it_lvl) if it_lvl else None,
                employee_id=str(it_emp_id) if it_emp_id else None,
                employee_name=str(it_emp_name) if it_emp_name else None,
            ):
                return False

        typed_ev = resp.get("typed_evidence")
        if isinstance(typed_ev, list):
            for tev in typed_ev:
                if not isinstance(tev, dict):
                    continue
                t_team = tev.get("team")
                t_lvl = tev.get("performance_level") or eff_level
                t_branch = tev.get("branch")
                if t_team and not self._is_team_and_level_authorized(str(t_team), str(t_lvl), eff_scope):
                    return False
                if t_branch and not self._is_branch_authorized(str(t_branch), eff_scope):
                    return False

        return True

    def sanitize_context_for_scope(
        self,
        row: AiConversation,
        eff_scope: dict[str, Any],
    ) -> AiConversationContextPayload:
        """Reauthorize saved people, pending clarification choices, and confirmed scope before returning context.

        Any unauthorized fields are cleared/redacted both in the returned payload and in the stored conversation row
        without revealing restricted identities.
        """
        payload = self._row_to_payload(row)
        mutated = False
        cc = payload.confirmed_context

        # 1. Reauthorize confirmed function, team, performance_level, branch, branches
        if cc.function and not self._is_function_authorized(cc.function, eff_scope):
            cc.function = None
            mutated = True

        if cc.team or cc.performance_level:
            if not self._is_team_and_level_authorized(cc.team, cc.performance_level, eff_scope):
                if cc.team and not user_can_access_team(eff_scope, cc.team):
                    cc.team = None
                    cc.position = None
                    cc.metric_id = None
                    cc.metric_display_name = None
                if cc.performance_level and not self._is_team_and_level_authorized(
                    cc.team, cc.performance_level, eff_scope
                ):
                    cc.performance_level = None
                mutated = True

        if cc.branch and not self._is_branch_authorized(cc.branch, eff_scope):
            cc.branch = None
            mutated = True

        if cc.branches:
            auth_branches = [b for b in cc.branches if self._is_branch_authorized(b, eff_scope)]
            if len(auth_branches) != len(cc.branches):
                cc.branches = auth_branches
                mutated = True

        # 2. Reauthorize saved person (last_subject_employee_id / last_subject_employee_name)
        emp_id = payload.last_subject_employee_id or cc.last_subject_employee_id
        emp_name = payload.last_subject_employee_name or cc.last_subject_employee_name
        if emp_id or emp_name:
            if not self._is_employee_authorized_for_scope(emp_id, emp_name, eff_scope):
                payload.last_subject_employee_id = None
                payload.last_subject_employee_name = None
                cc.last_subject_employee_id = None
                cc.last_subject_employee_name = None
                cc.single_person = False
                if payload.last_operation_kind in ("person_best_period", "person_worst_period", "new_joiner_check"):
                    payload.last_operation_kind = None
                    cc.last_operation_kind = None
                mutated = True

        # 3. Reauthorize pending clarification choices &confirmed_context pending_clarification_choices
        def _choice_authorized(ch: ClarificationChoice) -> bool:
            if ch.team and not self._is_team_and_level_authorized(ch.team, ch.performance_level, eff_scope):
                return False
            if ch.performance_level and not self._is_team_and_level_authorized(
                ch.team or cc.team, ch.performance_level, eff_scope
            ):
                return False
            if ch.branch and not self._is_branch_authorized(ch.branch, eff_scope):
                return False
            if ch.employee_id and not self._is_employee_authorized_for_scope(
                ch.employee_id, ch.label, eff_scope
            ):
                return False
            return True

        if cc.pending_clarification_choices:
            auth_cc_choices = [ch for ch in cc.pending_clarification_choices if _choice_authorized(ch)]
            if len(auth_cc_choices) != len(cc.pending_clarification_choices):
                cc.pending_clarification_choices = auth_cc_choices
                if not auth_cc_choices:
                    cc.pending_clarification_code = None
                mutated = True

        if payload.pending_clarification is not None:
            orig_choices = payload.pending_clarification.choices or []
            auth_choices = [ch for ch in orig_choices if _choice_authorized(ch)]
            if len(auth_choices) != len(orig_choices):
                mutated = True
            if payload.pending_clarification.code in ("AMBIGUOUS_PERSON", "MISSING_HR_JOIN_DATE") and (
                not auth_choices and orig_choices
            ):
                payload.pending_clarification = None
                cc.pending_clarification_code = None
                cc.pending_clarification_choices = []
                mutated = True
            elif orig_choices and not auth_choices:
                payload.pending_clarification = None
                cc.pending_clarification_code = None
                cc.pending_clarification_choices = []
                mutated = True
            else:
                payload.pending_clarification.choices = auth_choices

        if mutated:
            row.confirmed_context = cc.model_dump()
            row.pending_clarification = (
                payload.pending_clarification.model_dump() if payload.pending_clarification else None
            )
            row.last_subject_employee_id = payload.last_subject_employee_id
            row.last_subject_employee_name = payload.last_subject_employee_name
            row.last_operation_kind = payload.last_operation_kind
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()

        return payload

    @staticmethod
    def _row_to_payload(row: AiConversation) -> AiConversationContextPayload:
        confirmed_dict = dict(row.confirmed_context or {})
        try:
            confirmed = ConfirmedQueryContext(**confirmed_dict) if confirmed_dict else ConfirmedQueryContext()
        except Exception:
            confirmed = ConfirmedQueryContext()

        pending_clar: AiClarificationPrompt | None = None
        if isinstance(row.pending_clarification, dict) and row.pending_clarification.get("code"):
            try:
                pending_clar = AiClarificationPrompt(**row.pending_clarification)
            except Exception:
                pending_clar = None

        return AiConversationContextPayload(
            conversation_id=str(row.id),
            owner_user_id=str(row.owner_user_id),
            status=str(row.status or "active"),  # type: ignore[arg-type]
            context_version=int(row.context_version or 1),
            confirmed_context=confirmed,
            pending_clarification=pending_clar,
            last_subject_employee_id=row.last_subject_employee_id,
            last_subject_employee_name=row.last_subject_employee_name,
            last_operation_kind=row.last_operation_kind,
            created_at=row.created_at.isoformat() if row.created_at else None,
            updated_at=row.updated_at.isoformat() if row.updated_at else None,
        )

    def create_conversation(
        self,
        *,
        scope: dict[str, Any] | None = None,
        session_state: SessionFilterContext | None = None,
        initial_state: SessionFilterContext | None = None,
    ) -> AiConversationContextPayload:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, owner_role = self._resolve_owner(eff_scope)
        st = session_state or initial_state
        initial_ctx: dict[str, Any] = {}
        if st is not None:
            if st.last_confirmed_query is not None:
                initial_ctx = st.last_confirmed_query.model_dump()
            else:
                initial_ctx = ConfirmedQueryContext(
                    team=st.team,
                    function=st.function,
                    position=st.position,
                    branch=st.branch,
                    performance_level=st.performance_level,
                ).model_dump()
        row = self.repo.create_conversation(
            owner_user_id=owner_id,
            owner_role=owner_role,
            initial_confirmed_context=initial_ctx,
        )
        return self.sanitize_context_for_scope(row, eff_scope)

    def get_conversation_context(
        self,
        conversation_id: str,
        *,
        scope: dict[str, Any] | None = None,
    ) -> AiConversationContextPayload | None:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, _ = self._resolve_owner(eff_scope)
        row = self.repo.get_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_id,
            include_deleted=False,
        )
        if row is None:
            return None
        return self.sanitize_context_for_scope(row, eff_scope)

    def get_context(
        self,
        *,
        conversation_id: str | None = None,
        scope: dict[str, Any] | None = None,
        initial_state: SessionFilterContext | None = None,
    ) -> AiConversationContextPayload:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, owner_role = self._resolve_owner(eff_scope)
        initial_ctx: dict[str, Any] = {}
        if initial_state is not None:
            if initial_state.last_confirmed_query is not None:
                initial_ctx = initial_state.last_confirmed_query.model_dump()
            else:
                initial_ctx = ConfirmedQueryContext(
                    team=initial_state.team,
                    function=initial_state.function,
                    position=initial_state.position,
                    branch=initial_state.branch,
                    performance_level=initial_state.performance_level,
                ).model_dump()
        row = self.repo.get_or_create_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_id,
            owner_role=owner_role,
            initial_confirmed_context=initial_ctx,
        )
        return self.sanitize_context_for_scope(row, eff_scope)

    def claim_or_replay_turn(
        self,
        *,
        conversation_id: str,
        scope: dict[str, Any] | None = None,
        prompt: str,
        client_request_id: str | None = None,
        expected_context_version: int | None = None,
        clarification_choice_id: str | None = None,
        answer_detail: str | None = None,
        session_state: SessionFilterContext | None = None,
        known_employee_names: list[str] | None = None,
        eval_id: str | None = None,
    ) -> tuple[AiTurn, dict[str, Any] | None]:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, owner_role = self._resolve_owner(eff_scope)
        conv = self.repo.get_or_create_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_id,
            owner_role=owner_role,
        )
        eff_req_id = str(client_request_id or uuid.uuid4())
        session_filters = session_state.model_dump() if session_state is not None else {}
        req_fp = compute_request_fingerprint(
            prompt=prompt,
            clarification_choice_id=clarification_choice_id,
            answer_detail=answer_detail,
            session_filters=session_filters,
        )
        scope_fp = compute_scope_fingerprint(eff_scope)
        resolved_eval_id = (
            eval_id
            if eval_id is not None
            else (
                f"{evaluation_cache_identity(self.db)}"
                f":d{CacheInvalidationService.get_data_version()}"
                f":c{CacheInvalidationService.get_config_version()}"
            )
        )
        redacted_prompt = sanitize_prompt_for_router_training(
            prompt, known_employee_names=known_employee_names, db=self.db
        )

        turn_row, is_completed = self.repo.claim_or_get_turn(
            conversation_id=str(conv.id),
            client_request_id=eff_req_id,
            user_prompt_redacted=redacted_prompt,
            request_fingerprint=req_fp,
            scope_fingerprint=scope_fp,
            eval_id=resolved_eval_id,
            expected_context_version=expected_context_version,
            current_context_version=int(conv.context_version),
            session_filters=session_filters,
        )
        if is_completed and turn_row.response_payload:
            if self._is_turn_evidence_authorized(turn_row, eff_scope):
                return turn_row, dict(turn_row.response_payload)
            # Stored evidence is no longer authorized -> reclaim turn and recompute
            turn_row = self.repo.reclaim_turn_for_recompute(
                turn=turn_row,
                user_prompt_redacted=redacted_prompt,
                request_fingerprint=req_fp,
                scope_fingerprint=scope_fp,
                eval_id=resolved_eval_id,
                was_completed=True,
            )

        return turn_row, None

    def complete_turn(
        self,
        *,
        conversation_id: str,
        turn_id: str,
        expected_context_version: int | None = None,
        claim_token: str | None = None,
        scope: dict[str, Any] | None = None,
        outcome: str,
        turn_kind: str,
        route_used: str,
        validated_plan: dict[str, Any],
        evidence_envelope: list[dict[str, Any]],
        response_payload: dict[str, Any],
        session_state: SessionFilterContext,
        confirmed_context: ConfirmedQueryContext | None,
        provider_calls: int,
        total_ms: float,
    ) -> int:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, _ = self._resolve_owner(eff_scope)
        ctx_dict = confirmed_context.model_dump() if confirmed_context is not None else {}
        pending_clar = response_payload.get("clarification") if isinstance(response_payload, dict) else None
        return self.repo.complete_turn_and_advance_context(
            conversation_id=conversation_id,
            owner_user_id=owner_id,
            expected_context_version=expected_context_version,
            turn_id=turn_id,
            claim_token=claim_token,
            validated_plan=validated_plan,
            evidence_summary={"turn_kind": turn_kind, "items": evidence_envelope},
            response_payload=response_payload,
            outcome=outcome,
            route_used=route_used,
            provider_calls=provider_calls,
            total_ms=total_ms,
            new_confirmed_context=ctx_dict,
            pending_clarification=pending_clar if isinstance(pending_clar, dict) else None,
            last_subject_employee_id=confirmed_context.last_subject_employee_id if confirmed_context else None,
            last_subject_employee_name=confirmed_context.last_subject_employee_name if confirmed_context else None,
            last_operation_kind=confirmed_context.last_operation_kind if confirmed_context else None,
        )

    def archive_conversation(
        self,
        conversation_id: str,
        *,
        scope: dict[str, Any] | None = None,
    ) -> AiConversationContextPayload:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, _ = self._resolve_owner(eff_scope)
        row = self.repo.archive_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_id,
        )
        return self.sanitize_context_for_scope(row, eff_scope)

    def delete_conversation(self, conversation_id: str, *, scope: dict[str, Any] | None = None) -> bool:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, _ = self._resolve_owner(eff_scope)
        return self.repo.soft_delete_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_id,
        )
