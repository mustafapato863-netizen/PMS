from __future__ import annotations

import uuid
from typing import Any, Literal

from sqlalchemy.orm import Session

from api.dependencies import build_user_scope_from_db_user
from models.ai_schemas import (
    AiChatResponsePayload,
    AiClarificationPrompt,
    AiConversationContextPayload,
    AiConversationDetailPayload,
    AiConversationRetrySettings,
    AiConversationSummaryItem,
    AiConversationTurnDetail,
    ClarificationChoice,
    ConfirmedQueryContext,
    ConversationOriginType,
    SessionFilterContext,
)
from models.models import AiConversation, AiTurn, User
from repositories.ai_conversation_repository import (
    AiConversationRepository,
    ConversationAccessError,
    ConversationDeletedError,
    ConversationMigrationUnavailableError,
    ConversationOriginMismatchError,
    ConversationOwnershipError,
    ConversationStaleContextError,
    ConversationVersionConflictError,
    RequestIdReuseConflictError,
    TurnAlreadyInFlightError,
    compute_request_fingerprint,
    compute_scope_fingerprint,
)
from services.ai.catalog import evaluation_cache_identity
from services.ai.config import redact_secrets
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
    "ConversationOriginMismatchError",
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
        self._all_records_cache: list[Any] | None = None
        self._all_emp_index_cache: tuple[set[str], set[str]] | None = None
        self._scoped_emp_index_cache: dict[str, tuple[set[str], set[str]]] = {}

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

    def _is_region_authorized(self, region_name: str | None, eff_scope: dict[str, Any]) -> bool:
        if not region_name or region_name.strip().casefold() == "all":
            return True
        allowed = {
            str(region).strip().casefold()
            for region in (eff_scope.get("accessible_regions") or eff_scope.get("allowed_regions") or [])
            if str(region).strip()
        }
        if allowed:
            return "all" in allowed or region_name.strip().casefold() in allowed
        return eff_scope.get("role") != "Regional Manager"

    def _is_team_and_level_authorized(
        self,
        team_name: str | None,
        performance_level: str | None,
        eff_scope: dict[str, Any],
        region: str | None = None,
    ) -> bool:
        role = str(eff_scope.get("role") or "")
        lvl = str(performance_level or "Employee").strip()
        if lvl in ("Corporate", "Managerial"):
            if bool(eff_scope.get("is_self_only")) or role in SELF_SCOPED_ROLES:
                return False
        if team_name:
            if not user_can_access_team(eff_scope, team_name):
                return False
            if region and not self._is_region_authorized(region, eff_scope):
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

    @staticmethod
    def _build_employee_index(records: list[Any]) -> tuple[set[str], set[str]]:
        emp_ids: set[str] = set()
        emp_names: set[str] = set()
        for r in records:
            rid = str(getattr(r, "employee_id", "") or "").strip().casefold()
            if rid:
                emp_ids.add(rid)
            rname = str(getattr(r, "employee_name", "") or "").strip().casefold()
            if rname:
                emp_names.add(rname)
        return emp_ids, emp_names

    def _get_employee_auth_indexes(
        self,
        eff_scope: dict[str, Any],
    ) -> tuple[set[str], set[str], set[str], set[str]]:
        """Load and index employee IDs/names across full and scoped datasets at most once per request/scope."""
        if self._all_records_cache is None or self._all_emp_index_cache is None:
            all_recs = DashboardRecordService(self.db).list_analysis_records() or []
            self._all_records_cache = all_recs
            self._all_emp_index_cache = self._build_employee_index(all_recs)

        scope_fp = compute_scope_fingerprint(eff_scope)
        scoped_index = self._scoped_emp_index_cache.get(scope_fp)
        if scoped_index is None:
            scoped_recs = filter_records_by_scope(self._all_records_cache, eff_scope)
            scoped_index = self._build_employee_index(scoped_recs)
            self._scoped_emp_index_cache[scope_fp] = scoped_index

        all_ids, all_names = self._all_emp_index_cache
        scoped_ids, scoped_names = scoped_index
        return all_ids, all_names, scoped_ids, scoped_names

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

        # Unrestricted global roles and unrestricted Managers see all employee records in filter_records_by_scope,
        # so employee-level scoping is always satisfied without reloading the entire performance table.
        if not is_self_only and (
            role in {"Admin", "General Manager", "Performance Team", "Viewer"}
            or (role == "Manager" and bool(eff_scope.get("has_unrestricted_team_access")))
            or bool(eff_scope.get("legacy_unscoped"))
        ):
            return True

        try:
            all_ids, all_names, scoped_ids, scoped_names = self._get_employee_auth_indexes(eff_scope)
        except Exception:
            return False

        emp_id_norm = str(employee_id or "").strip().casefold()
        emp_name_norm = str(employee_name or "").strip().casefold()

        has_any_match = bool(
            (emp_id_norm and emp_id_norm in all_ids)
            or (emp_name_norm and emp_name_norm in all_names)
        )
        if has_any_match:
            return bool(
                (emp_id_norm and emp_id_norm in scoped_ids)
                or (emp_name_norm and emp_name_norm in scoped_names)
            )

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
        region: str | None = None,
        employee_id: str | None = None,
        employee_name: str | None = None,
    ) -> bool:
        """Check whether the given query plan / context dimensions are authorized under live scope."""
        if not self._is_function_authorized(function, scope):
            return False
        if not self._is_team_and_level_authorized(team, performance_level, scope, region=region):
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
        regs_to_check = (plan_scope.get("region"), struct_q.get("region"), resolved_st.get("region"), lcq.get("region"))
        eff_region = next((str(rg) for rg in regs_to_check if rg), None)
        for t in teams_to_check:
            if t and not self._is_team_and_level_authorized(str(t), eff_level, eff_scope, region=eff_region):
                return False
        if not any(teams_to_check) and eff_level in ("Corporate", "Managerial"):
            if not self._is_team_and_level_authorized(None, eff_level, eff_scope, region=eff_region):
                return False

        for fn in (plan_scope.get("function"), struct_q.get("function"), resolved_st.get("function"), lcq.get("function")):
            if fn and not self._is_function_authorized(str(fn), eff_scope):
                return False

        for reg in (plan_scope.get("region"), struct_q.get("region"), resolved_st.get("region"), lcq.get("region")):
            if reg and not self._is_region_authorized(str(reg), eff_scope):
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

        clarification = resp.get("clarification")
        choices = (clarification.get("choices") or []) if isinstance(clarification, dict) else []
        for person in [
            *(lcq.get("candidate_employees") or []),
            *(lcq.get("pending_clarification_choices") or []),
            *choices,
        ]:
            if not isinstance(person, dict):
                continue
            person_id = person.get("employee_id")
            if not self.is_plan_and_context_authorized(
                scope=eff_scope,
                team=person.get("team"),
                performance_level=person.get("performance_level"),
                branch=person.get("branch"),
                region=eff_region,
                employee_id=str(person_id) if person_id else None,
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
                if t_team and not self._is_team_and_level_authorized(str(t_team), str(t_lvl), eff_scope, region=eff_region):
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
        candidate_scope_allowed = (
            self._is_region_authorized(cc.region, eff_scope)
            and self.is_plan_and_context_authorized(
                scope=eff_scope,
                function=cc.function,
                team=cc.team,
                region=cc.region,
                performance_level=cc.performance_level,
                branch=cc.branch,
                branches=cc.branches,
            )
        )

        # 1. Reauthorize confirmed function, team, performance_level, branch, branches
        if cc.function and not self._is_function_authorized(cc.function, eff_scope):
            cc.function = None
            mutated = True

        if cc.team or cc.performance_level:
            if not self._is_team_and_level_authorized(cc.team, cc.performance_level, eff_scope, region=cc.region):
                if cc.team and (
                    not user_can_access_team(eff_scope, cc.team)
                    or (cc.region and not self._is_region_authorized(cc.region, eff_scope))
                ):
                    cc.team = None
                    cc.position = None
                    cc.metric_id = None
                    cc.metric_display_name = None
                if cc.performance_level and not self._is_team_and_level_authorized(
                    cc.team, cc.performance_level, eff_scope, region=cc.region
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

        if cc.region and not self._is_region_authorized(cc.region, eff_scope):
            cc.region = None
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

        if cc.candidate_employees:
            authorized_candidates = [
                candidate for candidate in cc.candidate_employees
                if candidate_scope_allowed and candidate.get("employee_id")
                and self._is_team_and_level_authorized(
                    candidate.get("team") or cc.team,
                    candidate.get("performance_level") or cc.performance_level,
                    eff_scope,
                    region=cc.region,
                )
                and self._is_employee_authorized_for_scope(
                    candidate["employee_id"], None, eff_scope
                )
            ]
            if len(authorized_candidates) != len(cc.candidate_employees):
                cc.candidate_employees = authorized_candidates
                mutated = True

        # Reauthorize pending clarification choices.
        def _choice_authorized(ch: ClarificationChoice) -> bool:
            if ch.team and not self._is_team_and_level_authorized(ch.team, ch.performance_level, eff_scope, region=cc.region):
                return False
            if ch.performance_level and not self._is_team_and_level_authorized(
                ch.team or cc.team, ch.performance_level, eff_scope, region=cc.region
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
    def _normalize_row_origin(row: AiConversation) -> ConversationOriginType:
        raw_origin = str(getattr(row, "origin", None) or "legacy").strip()
        if raw_origin in ("workspace", "page_assistant", "legacy"):
            return raw_origin  # type: ignore[return-value]
        return "legacy"

    @classmethod
    def _row_to_payload(cls, row: AiConversation) -> AiConversationContextPayload:
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

        safe_origin = cls._normalize_row_origin(row)
        return AiConversationContextPayload(
            conversation_id=str(row.id),
            owner_user_id=str(row.owner_user_id),
            origin=safe_origin,
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
        origin: ConversationOriginType = "workspace",
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
            origin=origin,
        )
        return self.sanitize_context_for_scope(row, eff_scope)

    def get_conversation_context(
        self,
        conversation_id: str,
        *,
        scope: dict[str, Any] | None = None,
        expected_origin: ConversationOriginType | None = None,
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
        if expected_origin is not None and self._normalize_row_origin(row) != expected_origin:
            raise ConversationOriginMismatchError(
                "This conversation belongs to a different assistant surface."
            )
        return self.sanitize_context_for_scope(row, eff_scope)

    def get_context(
        self,
        *,
        conversation_id: str | None = None,
        scope: dict[str, Any] | None = None,
        initial_state: SessionFilterContext | None = None,
        origin: ConversationOriginType = "workspace",
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
            origin=origin,
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
        variation_seed: int | None = None,
        origin: ConversationOriginType = "workspace",
        skip_record_lookup: bool = False,
    ) -> tuple[AiTurn, dict[str, Any] | None]:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, owner_role = self._resolve_owner(eff_scope)
        conv = self.repo.get_or_create_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_id,
            owner_role=owner_role,
            origin=origin,
        )
        eff_req_id = str(client_request_id or uuid.uuid4())
        session_filters = session_state.model_dump() if session_state is not None else {}
        req_fp = compute_request_fingerprint(
            prompt=prompt,
            clarification_choice_id=clarification_choice_id,
            answer_detail=answer_detail,
            session_filters=session_filters,
            variation_seed=variation_seed,
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
            prompt,
            known_employee_names=known_employee_names,
            db=None if skip_record_lookup else self.db,
        )
        clean_user_prompt = redact_secrets(prompt)

        turn_row, is_completed = self.repo.claim_or_get_turn(
            conversation_id=str(conv.id),
            client_request_id=eff_req_id,
            user_prompt=clean_user_prompt,
            user_prompt_redacted=redacted_prompt,
            request_fingerprint=req_fp,
            scope_fingerprint=scope_fp,
            eval_id=resolved_eval_id,
            expected_context_version=expected_context_version,
            current_context_version=int(conv.context_version),
            session_filters=session_filters,
            retry_settings={
                "session_state": {key: value for key, value in session_filters.items() if key != "last_confirmed_query"},
                "clarification_choice_id": clarification_choice_id,
                "answer_detail": answer_detail,
                "variation_seed": variation_seed,
            },
        )
        if is_completed and turn_row.response_payload:
            if self._is_turn_evidence_authorized(turn_row, eff_scope):
                return turn_row, dict(turn_row.response_payload)
            # Stored evidence is no longer authorized -> reclaim turn and recompute
            turn_row = self.repo.reclaim_turn_for_recompute(
                turn=turn_row,
                user_prompt=clean_user_prompt,
                user_prompt_redacted=redacted_prompt,
                request_fingerprint=req_fp,
                scope_fingerprint=scope_fp,
                eval_id=resolved_eval_id,
                was_completed=True,
            )

        return turn_row, None

    @staticmethod
    def _derive_conversation_title(prompt: str | None) -> str | None:
        clean = " ".join(redact_secrets(str(prompt or "")).strip().split())
        if not clean:
            return None
        if len(clean) > 80:
            return clean[:77].rstrip() + "..."
        return clean

    @staticmethod
    def _extract_period_used(response: AiChatResponsePayload | None) -> str | None:
        if response is None:
            return None
        st = response.resolved_session_state
        if st and st.month and st.year:
            return f"{st.month} {st.year}"
        if st and st.month:
            return st.month
        if response.validated_plan_v2 and response.validated_plan_v2.scope.periods:
            return response.validated_plan_v2.scope.periods[-1]
        if response.structured_query and response.structured_query.periods:
            return response.structured_query.periods[-1]
        return None

    def fail_turn(
        self,
        *,
        conversation_id: str | None,
        turn_id: str,
        claim_token: str | None,
        prompt: str | None = None,
        error_message: str,
    ) -> None:
        clean_err = redact_secrets(str(error_message or "Unable to complete analysis"))
        title_candidate = self._derive_conversation_title(prompt)
        self.repo.release_turn_claim(
            turn_id=turn_id,
            claim_token=claim_token,
            error_message=clean_err,
            conversation_id=conversation_id,
            title_candidate=title_candidate,
        )

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
        turn_row = self.db.query(AiTurn).filter(AiTurn.id == str(turn_id)).first()
        title_candidate = self._derive_conversation_title(
            (turn_row.user_prompt or turn_row.user_prompt_redacted) if turn_row is not None else None
        )
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
            title_candidate=title_candidate,
        )

    def list_conversations(
        self,
        *,
        scope: dict[str, Any] | None = None,
        limit: int = 30,
        origin: Literal["workspace", "page_assistant", "legacy", "all"] | None = "workspace",
    ) -> list[AiConversationSummaryItem]:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, _ = self._resolve_owner(eff_scope)
        rows = self.repo.list_owned_conversations(owner_user_id=owner_id, limit=limit, origin=origin)
        turns_by_conv = self.repo.list_turns_for_conversations(
            conversation_ids=[str(r.id) for r in rows]
        )
        summaries: list[AiConversationSummaryItem] = []
        for row in rows:
            conv_id = str(row.id)
            turns = turns_by_conv.get(conv_id, [])
            has_restricted = False
            last_turn_restricted = False
            for idx, t in enumerate(turns):
                is_restricted_turn = (
                    t.status == "completed" and not self._is_turn_evidence_authorized(t, eff_scope)
                )
                if is_restricted_turn:
                    has_restricted = True
                if idx == len(turns) - 1:
                    last_turn_restricted = is_restricted_turn

            last_turn = turns[-1] if turns else None
            if has_restricted:
                title = "Restricted conversation"
            else:
                title = (
                    (row.title or "").strip()
                    or (
                        self._derive_conversation_title(
                            turns[0].user_prompt or turns[0].user_prompt_redacted
                        )
                        if turns
                        else None
                    )
                    or "New conversation"
                )

            last_outcome: str | None = None
            last_scope_banner: str | None = None
            last_period: str | None = None
            if last_turn is not None:
                if last_turn_restricted:
                    last_outcome = "restricted_access"
                    last_scope_banner = None
                    last_period = None
                else:
                    last_outcome = (
                        "failed"
                        if last_turn.status == "failed"
                        else (last_turn.outcome or None)
                    )
                    if last_turn.status == "completed" and isinstance(last_turn.response_payload, dict):
                        try:
                            parsed_resp = AiChatResponsePayload.model_validate(last_turn.response_payload)
                            last_scope_banner = None if has_restricted else parsed_resp.scope_banner
                            last_period = None if has_restricted else self._extract_period_used(parsed_resp)
                        except Exception:
                            last_scope_banner = None
                            last_period = None

            safe_origin = self._normalize_row_origin(row)
            summaries.append(
                AiConversationSummaryItem(
                    conversation_id=conv_id,
                    title=title,
                    origin=safe_origin,
                    created_at=row.created_at.isoformat() if row.created_at else None,
                    updated_at=row.updated_at.isoformat() if row.updated_at else None,
                    turn_count=len(turns),
                    last_outcome=last_outcome,
                    last_scope_banner=last_scope_banner,
                    last_period=last_period,
                    has_restricted_turns=has_restricted,
                    context_version=int(row.context_version or 1),
                )
            )
        return summaries

    def get_conversation_detail(
        self,
        conversation_id: str,
        *,
        scope: dict[str, Any] | None = None,
        expected_origin: ConversationOriginType | None = None,
    ) -> AiConversationDetailPayload | None:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, _ = self._resolve_owner(eff_scope)
        row = self.repo.get_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_id,
            include_deleted=False,
        )
        if row is None:
            return None
        if expected_origin is not None and self._normalize_row_origin(row) != expected_origin:
            raise ConversationOriginMismatchError(
                "This conversation belongs to a different assistant surface."
            )
        sanitized_ctx = self.sanitize_context_for_scope(row, eff_scope)
        turns = self.repo.list_turns_for_conversation(conversation_id=str(row.id))

        turn_details: list[AiConversationTurnDetail] = []
        has_restricted = False
        for t in turns:
            if t.status == "completed" and not self._is_turn_evidence_authorized(t, eff_scope):
                has_restricted = True
                restricted_resp = AiChatResponsePayload(
                    trace_id="",
                    conversation_id=str(row.id),
                    turn_id=str(t.id),
                    context_version=int(row.context_version or 1),
                    outcome="restricted_access",
                    answer_detail="brief",
                    headline="This historical answer is hidden because your current permissions no longer include its data scope.",
                    narrative_bullets=[],
                    visual_cards=[],
                    citations=[],
                    deep_links=[],
                    primary_source_link=None,
                    suggested_followups=[],
                    resolved_session_state=SessionFilterContext(),
                    scope_banner=None,
                    typed_evidence=[],
                    evidence_envelope_v2=[],
                )
                turn_details.append(
                    AiConversationTurnDetail(
                        turn_id=str(t.id),
                        turn_index=int(t.turn_index),
                        status="restricted",
                        user_prompt="Restricted question (scope no longer authorized)",
                        error_message=None,
                        scope_used=None,
                        period_used=None,
                        created_at=t.created_at.isoformat() if t.created_at else None,
                        completed_at=t.completed_at.isoformat() if t.completed_at else None,
                        response=restricted_resp,
                    )
                )
                continue

            parsed_resp: AiChatResponsePayload | None = None
            if t.status == "completed" and isinstance(t.response_payload, dict) and t.response_payload:
                try:
                    parsed_resp = AiChatResponsePayload.model_validate(t.response_payload)
                except Exception:
                    parsed_resp = None

            turn_status = str(t.status or "pending")
            if turn_status not in ("pending", "completed", "failed", "superseded"):
                turn_status = "completed" if parsed_resp else "failed"

            retry_settings = None
            if turn_status in ("pending", "failed"):
                stored_retry = (t.evidence_summary or {}).get("retry_settings")
                if stored_retry:
                    settings = AiConversationRetrySettings.model_validate(stored_retry)
                    filters = settings.session_state
                    if self._is_region_authorized(filters.region, eff_scope) and self.is_plan_and_context_authorized(
                        scope=eff_scope,
                        team=filters.team,
                        function=filters.function,
                        branch=filters.branch,
                        region=filters.region,
                        performance_level=filters.performance_level,
                        employee_id=filters.employee_id,
                    ):
                        retry_settings = settings

            turn_details.append(
                AiConversationTurnDetail(
                    turn_id=str(t.id),
                    turn_index=int(t.turn_index),
                    status=turn_status,  # type: ignore[arg-type]
                    client_request_id=t.client_request_id,
                    retry_settings=retry_settings,
                    user_prompt=t.user_prompt or t.user_prompt_redacted or "",
                    error_message=t.error_message,
                    scope_used=parsed_resp.scope_banner if parsed_resp else None,
                    period_used=self._extract_period_used(parsed_resp),
                    created_at=t.created_at.isoformat() if t.created_at else None,
                    completed_at=t.completed_at.isoformat() if t.completed_at else None,
                    response=parsed_resp,
                )
            )

        if has_restricted:
            title = "Restricted conversation"
        else:
            title = (
                (row.title or "").strip()
                or (
                    self._derive_conversation_title(turns[0].user_prompt or turns[0].user_prompt_redacted)
                    if turns
                    else None
                )
            )

        safe_origin = self._normalize_row_origin(row)
        return AiConversationDetailPayload(
            conversation_id=str(row.id),
            owner_user_id=str(row.owner_user_id),
            title=title,
            origin=safe_origin,
            status=str(row.status or "active"),  # type: ignore[arg-type]
            context_version=int(sanitized_ctx.context_version),
            confirmed_context=sanitized_ctx.confirmed_context,
            pending_clarification=sanitized_ctx.pending_clarification,
            has_restricted_turns=has_restricted,
            created_at=row.created_at.isoformat() if row.created_at else None,
            updated_at=row.updated_at.isoformat() if row.updated_at else None,
            turns=turn_details,
        )

    def promote_conversation(
        self,
        conversation_id: str,
        *,
        scope: dict[str, Any] | None = None,
    ) -> AiConversationContextPayload:
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, _ = self._resolve_owner(eff_scope)
        row = self.repo.promote_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_id,
        )
        return self.sanitize_context_for_scope(row, eff_scope)

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

    def get_last_completed_turn_summary(
        self,
        conversation_id: str,
        *,
        scope: dict[str, Any] | None = None,
        batch_size: int = 15,
        max_batches: int = 4,
    ) -> dict[str, Any] | None:
        """Return bounded, RBAC-revalidated details of the last completed analytical/clarification turn.

        Queries completed turns in descending order with a bounded batch limit and minimal columns,
        never loading full history and never skipping past an unauthorized latest turn.
        """
        eff_scope = self.validate_live_account_and_scope(scope)
        owner_id, _ = self._resolve_owner(eff_scope)
        row = self.repo.get_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_id,
            include_deleted=False,
        )
        if row is None:
            return None

        cursor_idx: int | None = None
        safe_batch = max(1, min(int(batch_size), 50))
        safe_batches = max(1, min(int(max_batches), 10))
        for _ in range(safe_batches):
            turns = self.repo.list_recent_completed_turns_for_summary(
                conversation_id=str(row.id),
                limit=safe_batch,
                before_turn_index=cursor_idx,
            )
            if not turns:
                return None
            for turn in turns:
                cursor_idx = int(turn.turn_index)
                payload_dict = turn.response_payload if isinstance(turn.response_payload, dict) else None
                if not payload_dict:
                    continue
                cap_mode = str(payload_dict.get("capability_mode") or "")
                if cap_mode in ("greeting", "off_topic", "explain_previous", "capabilities_help", "clarification"):
                    continue
                if not self._is_turn_evidence_authorized(turn, eff_scope):
                    return {"restricted": True}
                headline = str(payload_dict.get("headline") or "").strip()
                if not headline:
                    continue
                sq = payload_dict.get("structured_query") if isinstance(payload_dict.get("structured_query"), dict) else {}
                compact_evidence: list[dict[str, Any]] = []
                for ev in (payload_dict.get("evidence_envelope_v2") or [])[:6]:
                    if isinstance(ev, dict):
                        ev_scope = ev.get("scope") if isinstance(ev.get("scope"), dict) else {}
                        compact_evidence.append(
                            {
                                "label": str(ev.get("metric_label") or ev.get("metric_id") or ev.get("kind") or "Metric"),
                                "value": str(ev.get("display_value") or ev.get("actual_display") or ev.get("value") or ""),
                                "target": str(ev.get("target_display") or ""),
                                "period": str(ev_scope.get("period") or ev.get("period") or ""),
                                "team": str(ev_scope.get("team") or ""),
                            }
                        )
                if not compact_evidence:
                    for tev in (payload_dict.get("typed_evidence") or [])[:6]:
                        if isinstance(tev, dict):
                            compact_evidence.append(
                                {
                                    "label": str(tev.get("kpi_label") or tev.get("metric_id") or "Metric"),
                                    "value": str(tev.get("actual_display") or ""),
                                    "target": str(tev.get("target_display") or ""),
                                    "period": str(tev.get("period") or ""),
                                    "team": str(tev.get("team") or ""),
                                }
                            )
                return {
                    "restricted": False,
                    "turn_index": int(turn.turn_index),
                    "headline": headline,
                    "narrative_bullets": [
                        str(b) for b in (payload_dict.get("narrative_bullets") or [])[:4] if b
                    ],
                    "detail_bullets": [
                        str(b) for b in (payload_dict.get("detail_bullets") or [])[:4] if b
                    ],
                    "scope_banner": payload_dict.get("scope_banner"),
                    "basis_warning": payload_dict.get("basis_warning"),
                    "outcome": str(turn.outcome or payload_dict.get("outcome") or "answer"),
                    "capability_mode": cap_mode or "performance_query",
                    "structured_query": {
                        "intent": sq.get("intent"),
                        "function": sq.get("function"),
                        "team": sq.get("team"),
                        "branch": sq.get("branch"),
                        "metric": sq.get("metric"),
                        "periods": list(sq.get("periods") or [])[:4],
                        "employee_name": sq.get("employee_name"),
                    },
                    "evidence_items": compact_evidence,
                }
            if len(turns) < safe_batch:
                break
        return None
