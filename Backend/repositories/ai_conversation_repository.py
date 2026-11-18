from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import uuid
from typing import Any

from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from models.models import AiConversation, AiInteractionTrace, AiTurn
from services.ai.trace_logger import _ensure_conversation_v2_columns, ensure_trace_schema_once
from utils.report_scope import canonical_scope_identity


class ConversationRepositoryError(RuntimeError):
    """Base error for conversation persistence operations."""


class ConversationOwnershipError(PermissionError):
    """Raised when a caller attempts to access or mutate another user's conversation."""


ConversationAccessError = ConversationOwnershipError


class ConversationDeletedError(ConversationOwnershipError):
    """Raised when a caller sends a request for a conversation that was already deleted/reset."""


class ConversationOriginMismatchError(ConversationRepositoryError):
    """Raised when a conversation is accessed from a different assistant surface."""


class ConversationStaleContextError(ConversationRepositoryError):
    """Raised when a turn carries a stale context_version or superseded claim token."""


ConversationVersionConflictError = ConversationStaleContextError


class RequestIdReuseConflictError(ConversationStaleContextError):
    """Raised when a client_request_id is reused with different prompt or filter parameters."""


class TurnAlreadyInFlightError(ConversationRepositoryError):
    """Raised when a duplicate client_request_id is currently being processed by another worker."""


class ConversationMigrationUnavailableError(ConversationRepositoryError):
    """Raised when conversation persistence tables are not yet migrated in production/staging."""


VALID_CONVERSATION_ORIGINS: tuple[str, str, str] = ("workspace", "page_assistant", "legacy")


def _normalize_origin(origin: str | None) -> str:
    val = str(origin or "legacy").strip()
    if val not in VALID_CONVERSATION_ORIGINS:
        raise ValueError(f"Unsupported conversation origin: {val!r}")
    return val


def _norm_str(val: Any, default: str = "") -> str:
    if val is None:
        return default
    return " ".join(str(val).strip().casefold().split())


def _normalize_session_filters(session_filters: Any) -> dict[str, Any]:
    if session_filters is None:
        raw: dict[str, Any] = {}
    elif hasattr(session_filters, "model_dump"):
        raw = session_filters.model_dump()
    elif isinstance(session_filters, dict):
        raw = dict(session_filters)
    else:
        raw = {}

    periods_raw = raw.get("periods")
    norm_periods: list[str] = []
    if isinstance(periods_raw, (list, tuple)):
        norm_periods = [_norm_str(p) for p in periods_raw if _norm_str(p)]
    elif _norm_str(raw.get("period")):
        norm_periods = [_norm_str(raw.get("period"))]

    year_val = raw.get("year")
    norm_year = str(int(year_val)) if year_val is not None and str(year_val).strip() != "" else ""

    return {
        "function": _norm_str(raw.get("function") or "Call Center"),
        "team": _norm_str(raw.get("team")),
        "position": _norm_str(raw.get("position")),
        "employee_id": _norm_str(raw.get("employee_id")),
        "region": _norm_str(raw.get("region")),
        "branch": _norm_str(raw.get("branch")),
        "performance_level": _norm_str(raw.get("performance_level")),
        "month": _norm_str(raw.get("month")),
        "year": norm_year,
        "period": _norm_str(raw.get("period")),
        "periods": norm_periods,
    }


def compute_request_fingerprint(
    *,
    prompt: str,
    clarification_choice_id: str | None = None,
    answer_detail: str | None = None,
    session_filters: dict[str, Any] | Any | None = None,
    session_state: Any | None = None,
    variation_seed: int | None = None,
) -> str:
    """Compute a canonical SHA-256 request fingerprint binding prompt, clarification choice, answer detail, and session filters."""
    eff_filters = session_filters if session_filters is not None else session_state
    canonical: dict[str, Any] = {
        "prompt": _norm_str(prompt),
        "clarification_choice_id": _norm_str(clarification_choice_id),
        "answer_detail": _norm_str(answer_detail or "auto", default="auto"),
        "filters": _normalize_session_filters(eff_filters),
    }
    if variation_seed is not None and int(variation_seed) > 0:
        canonical["variation_seed"] = int(variation_seed)
    raw = json.dumps(canonical, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def compute_scope_fingerprint(scope: dict[str, Any] | None) -> str:
    """Compute a canonical SHA-256 scope fingerprint covering all effective authorization dimensions."""
    canonical = canonical_scope_identity(scope)
    raw = json.dumps(canonical, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AiConversationRepository:
    """Data access layer for server-owned AI conversations and idempotent turns."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self._schema_ready_cache: bool | None = None
        ensure_trace_schema_once(self.db)
        self.ensure_v2_columns()

    def ensure_v2_columns(self) -> None:
        """Backfill newly added v2 conversation/turn columns in local/test environments only."""
        app_env = os.environ.get("APP_ENV", "").strip().casefold()
        disable_ddl = os.environ.get("PMS_DISABLE_RUNTIME_DDL", "").strip().casefold() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if app_env in ("production", "staging", "prod", "stage") or disable_ddl:
            return
        try:
            _ensure_conversation_v2_columns(self.db.get_bind())
        except Exception:
            pass

    def is_schema_ready(self) -> bool:
        if self._schema_ready_cache is not None:
            return self._schema_ready_cache
        try:
            bind = self.db.get_bind()
            insp = sa_inspect(bind)
            tables = set(insp.get_table_names())
            required_columns = {
                "ai_conversations": {column.name for column in AiConversation.__table__.columns},
                "ai_turns": {column.name for column in AiTurn.__table__.columns},
            }
            ready = all(
                table in tables and columns <= {column["name"] for column in insp.get_columns(table)}
                for table, columns in required_columns.items()
            )
            self._schema_ready_cache = ready
            return ready
        except Exception:
            return False

    def _require_schema_ready(self) -> None:
        if not self.is_schema_ready():
            self.db.rollback()
            raise ConversationMigrationUnavailableError(
                "AI conversation persistence schema is not yet migrated. Run Alembic upgrade e2b4c8d9f0a1."
            )

    def create_conversation(
        self,
        *,
        owner_user_id: str,
        owner_role: str,
        initial_confirmed_context: dict[str, Any] | None = None,
        conversation_id: str | None = None,
        origin: str = "workspace",
    ) -> AiConversation:
        self._require_schema_ready()
        conv_id = str(conversation_id or uuid.uuid4())
        norm_origin = _normalize_origin(origin)
        now_dt = datetime.now(timezone.utc)
        row = AiConversation(
            id=conv_id,
            owner_user_id=str(owner_user_id or "anonymous"),
            owner_role=str(owner_role or "Manager"),
            origin=norm_origin,
            status="active",
            context_version=1,
            confirmed_context=dict(initial_confirmed_context or {}),
            pending_clarification=None,
            last_subject_employee_id=None,
            last_subject_employee_name=None,
            last_operation_kind=None,
            created_at=now_dt,
            updated_at=now_dt,
        )
        try:
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
            return row
        except IntegrityError:
            self.db.rollback()
            existing = self.get_owned_conversation(
                conversation_id=conv_id, owner_user_id=owner_user_id, include_deleted=True
            )
            if existing is None:
                raise
            if existing.status == "deleted":
                raise ConversationDeletedError("Conversation has been reset or deleted.")
            if _normalize_origin(existing.origin) != norm_origin:
                raise ConversationOriginMismatchError(
                    "This conversation belongs to a different assistant surface. Promote it before continuing here."
                )
            return existing
        except (OperationalError, ProgrammingError) as exc:
            self.db.rollback()
            raise ConversationMigrationUnavailableError(
                "AI conversation persistence schema is not yet migrated."
            ) from exc

    def get_owned_conversation(
        self,
        *,
        conversation_id: str,
        owner_user_id: str,
        include_deleted: bool = False,
    ) -> AiConversation | None:
        self._require_schema_ready()
        row = (
            self.db.query(AiConversation)
            .filter(AiConversation.id == str(conversation_id))
            .first()
        )
        if row is None:
            return None
        if str(row.owner_user_id) != str(owner_user_id or "anonymous"):
            raise ConversationOwnershipError("Conversation not found for current user.")
        if not include_deleted and row.status == "deleted":
            return None
        return row

    def get_or_create_owned_conversation(
        self,
        *,
        conversation_id: str | None,
        owner_user_id: str,
        owner_role: str,
        initial_confirmed_context: dict[str, Any] | None = None,
        origin: str = "workspace",
    ) -> AiConversation:
        self._require_schema_ready()
        if conversation_id:
            existing = self.get_owned_conversation(
                conversation_id=conversation_id,
                owner_user_id=owner_user_id,
                include_deleted=True,
            )
            if existing is not None:
                if existing.status == "deleted":
                    raise ConversationDeletedError("Conversation has been reset or deleted.")
                expected_origin = _normalize_origin(origin)
                if _normalize_origin(existing.origin) != expected_origin:
                    raise ConversationOriginMismatchError(
                        "This conversation belongs to a different assistant surface. Promote it before continuing here."
                    )
                return existing
        return self.create_conversation(
            owner_user_id=owner_user_id,
            owner_role=owner_role,
            initial_confirmed_context=initial_confirmed_context,
            conversation_id=conversation_id,
            origin=origin,
        )

    def list_owned_conversations(
        self,
        *,
        owner_user_id: str,
        limit: int = 30,
        origin: str | None = "workspace",
    ) -> list[AiConversation]:
        self._require_schema_ready()
        safe_limit = max(1, min(int(limit or 30), 50))
        query = self.db.query(AiConversation).filter(
            AiConversation.owner_user_id == str(owner_user_id or "anonymous"),
            AiConversation.status != "deleted",
            AiConversation.deleted_at.is_(None),
        )
        if origin not in (None, "all"):
            query = query.filter(AiConversation.origin == _normalize_origin(origin))
        return (
            query.order_by(AiConversation.updated_at.desc(), AiConversation.created_at.desc())
            .limit(safe_limit)
            .all()
        )

    def promote_conversation(
        self,
        *,
        conversation_id: str,
        owner_user_id: str,
    ) -> AiConversation:
        """Explicitly move a non-workspace conversation into workspace history without changing turns."""
        self._require_schema_ready()
        row = self.get_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_user_id,
            include_deleted=True,
        )
        if row is None:
            raise ConversationOwnershipError("Conversation not found.")
        if row.status == "deleted":
            raise ConversationDeletedError("Conversation has been reset or deleted.")
        if row.origin != "workspace":
            row.origin = "workspace"
            row.updated_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(row)
        return row

    def list_recent_completed_turns_for_summary(
        self,
        *,
        conversation_id: str,
        limit: int = 20,
        before_turn_index: int | None = None,
    ) -> list[Any]:
        """Fetch recent completed turns in descending order with only summary/auth fields."""
        self._require_schema_ready()
        safe_limit = max(1, min(int(limit), 50))
        query = (
            self.db.query(
                AiTurn.turn_index.label("turn_index"),
                AiTurn.outcome.label("outcome"),
                AiTurn.validated_plan.label("validated_plan"),
                AiTurn.evidence_summary.label("evidence_summary"),
                AiTurn.response_payload.label("response_payload"),
            )
            .filter(
                AiTurn.conversation_id == str(conversation_id),
                AiTurn.status == "completed",
            )
        )
        if before_turn_index is not None:
            query = query.filter(AiTurn.turn_index < int(before_turn_index))
        return (
            query.order_by(AiTurn.turn_index.desc(), AiTurn.created_at.desc())
            .limit(safe_limit)
            .all()
        )

    def list_turns_for_conversation(self, *, conversation_id: str) -> list[AiTurn]:
        self._require_schema_ready()
        return (
            self.db.query(AiTurn)
            .filter(AiTurn.conversation_id == str(conversation_id))
            .order_by(AiTurn.turn_index.asc(), AiTurn.created_at.asc())
            .all()
        )

    def list_turns_for_conversations(self, *, conversation_ids: list[str]) -> dict[str, list[AiTurn]]:
        self._require_schema_ready()
        if not conversation_ids:
            return {}
        rows = (
            self.db.query(AiTurn)
            .filter(AiTurn.conversation_id.in_([str(cid) for cid in conversation_ids]))
            .order_by(AiTurn.conversation_id.asc(), AiTurn.turn_index.asc(), AiTurn.created_at.asc())
            .all()
        )
        grouped: dict[str, list[AiTurn]] = {}
        for row in rows:
            grouped.setdefault(str(row.conversation_id), []).append(row)
        return grouped

    def archive_conversation(
        self,
        *,
        conversation_id: str,
        owner_user_id: str,
    ) -> AiConversation:
        self._require_schema_ready()
        row = self.get_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_user_id,
            include_deleted=True,
        )
        if row is None:
            raise ConversationOwnershipError("Conversation not found.")
        if row.status == "deleted":
            raise ConversationDeletedError("Conversation has been reset or deleted.")
        now_dt = datetime.now(timezone.utc)
        row.status = "archived"
        row.updated_at = now_dt
        self.db.commit()
        self.db.refresh(row)
        return row

    def soft_delete_conversation(
        self,
        *,
        conversation_id: str,
        owner_user_id: str,
    ) -> bool:
        self._require_schema_ready()
        row = self.get_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_user_id,
            include_deleted=False,
        )
        if row is None:
            return False
        now_dt = datetime.now(timezone.utc)
        row.status = "deleted"
        row.deleted_at = now_dt
        row.updated_at = now_dt
        row.confirmed_context = {}
        row.pending_clarification = None
        row.last_subject_employee_id = None
        row.last_subject_employee_name = None
        row.last_operation_kind = None
        self.db.commit()
        return True

    @staticmethod
    def _verify_legacy_request_compatibility(
        existing: AiTurn,
        user_prompt_redacted: str,
        session_filters: dict[str, Any] | None = None,
    ) -> None:
        stored_prompt = _norm_str(existing.user_prompt_redacted)
        incoming_prompt = _norm_str(user_prompt_redacted)
        if stored_prompt and incoming_prompt and stored_prompt != incoming_prompt:
            raise RequestIdReuseConflictError(
                "client_request_id was already used with a different prompt on a legacy turn."
            )
        if session_filters:
            norm_incoming = _normalize_session_filters(session_filters)
            resp_payload = existing.response_payload if isinstance(existing.response_payload, dict) else {}
            resolved_st = resp_payload.get("resolved_session_state") if isinstance(resp_payload, dict) else None
            if isinstance(resolved_st, dict):
                norm_stored = _normalize_session_filters(resolved_st)
                for key in ("function", "team", "position", "branch", "region", "performance_level", "employee_id"):
                    inc_val = norm_incoming.get(key, "")
                    st_val = norm_stored.get(key, "")
                    if inc_val and st_val and inc_val != st_val:
                        raise RequestIdReuseConflictError(
                            f"client_request_id was already used with a different {key} filter on a legacy turn."
                        )

    def claim_or_get_turn(
        self,
        *,
        conversation_id: str,
        client_request_id: str,
        user_prompt: str | None = None,
        user_prompt_redacted: str,
        request_fingerprint: str = "",
        scope_fingerprint: str = "",
        eval_id: str = "",
        expected_context_version: int | None = None,
        current_context_version: int | None = None,
        session_filters: dict[str, Any] | None = None,
        retry_settings: dict[str, Any] | None = None,
        deadline_seconds: int = 15,
    ) -> tuple[AiTurn, bool]:
        """Claim an idempotent turn slot using compare-and-swap semantics.

        Returns `(turn_row, is_already_completed)`.
        Never replays a turn when request_fingerprint, scope_fingerprint, or eval_id is missing/incomplete.
        Validates expected_context_version before creating or claiming a pending turn so stale requests
        do not leave claimed turns blocking corrected retries.
        """
        self._require_schema_ready()
        now_dt = datetime.now(timezone.utc)
        deadline_dt = now_dt + timedelta(seconds=max(5, deadline_seconds))
        claim_tok = str(uuid.uuid4())

        existing = (
            self.db.query(AiTurn)
            .filter(
                AiTurn.conversation_id == str(conversation_id),
                AiTurn.client_request_id == str(client_request_id),
            )
            .first()
        )
        if existing is not None:
            ev_sum = dict(existing.evidence_summary or {})
            stored_req_fp = str(ev_sum.get("request_fingerprint") or "").strip()
            stored_scope_fp = str(ev_sum.get("scope_fingerprint") or "").strip()
            stored_eval_id = str(ev_sum.get("eval_id") or "").strip()

            if stored_req_fp:
                if not request_fingerprint or stored_req_fp != request_fingerprint:
                    raise RequestIdReuseConflictError(
                        "client_request_id was already used with a different prompt or filter context."
                    )
            else:
                self._verify_legacy_request_compatibility(
                    existing,
                    user_prompt_redacted=user_prompt_redacted,
                    session_filters=session_filters,
                )

            was_completed = existing.status == "completed"
            has_complete_fingerprints = bool(
                stored_req_fp
                and stored_scope_fp
                and stored_eval_id
                and request_fingerprint
                and scope_fingerprint
                and eval_id
            )
            if was_completed and existing.response_payload and has_complete_fingerprints:
                if (
                    stored_req_fp == request_fingerprint
                    and stored_scope_fp == scope_fingerprint
                    and stored_eval_id == eval_id
                ):
                    return existing, True

            # Validate context_version BEFORE claiming or reclaiming a turn
            if (
                expected_context_version is not None
                and int(expected_context_version) > 0
                and current_context_version is not None
            ):
                allowed_versions = {int(current_context_version)}
                if was_completed:
                    allowed_versions.add(int(current_context_version) - 1)
                if int(expected_context_version) not in allowed_versions:
                    raise ConversationStaleContextError(
                        f"Stale context_version {expected_context_version}; current is {current_context_version}."
                    )

            existing_deadline = existing.processing_deadline
            if existing_deadline is not None and existing_deadline.tzinfo is None:
                existing_deadline = existing_deadline.replace(tzinfo=timezone.utc)
            if existing.status == "pending" and existing_deadline and existing_deadline > now_dt:
                raise TurnAlreadyInFlightError(
                    "Duplicate client_request_id is currently in flight."
                )

            return self.reclaim_turn_for_recompute(
                turn=existing,
                user_prompt=user_prompt,
                user_prompt_redacted=user_prompt_redacted,
                request_fingerprint=request_fingerprint,
                scope_fingerprint=scope_fingerprint,
                eval_id=eval_id,
                was_completed=was_completed,
                deadline_seconds=deadline_seconds,
            ), False

        # Brand new turn: verify expected_context_version BEFORE inserting a claimed pending turn
        if (
            expected_context_version is not None
            and int(expected_context_version) > 0
            and current_context_version is not None
            and int(expected_context_version) != int(current_context_version)
        ):
            raise ConversationStaleContextError(
                f"Stale context_version {expected_context_version}; current is {current_context_version}."
            )

        max_idx_row = (
            self.db.query(AiTurn.turn_index)
            .filter(AiTurn.conversation_id == str(conversation_id))
            .order_by(AiTurn.turn_index.desc())
            .first()
        )
        next_idx = (int(max_idx_row[0]) + 1) if max_idx_row and max_idx_row[0] is not None else 1

        turn = AiTurn(
            id=str(uuid.uuid4()),
            conversation_id=str(conversation_id),
            turn_index=next_idx,
            client_request_id=str(client_request_id),
            status="pending",
            claim_token=claim_tok,
            processing_deadline=deadline_dt,
            user_prompt=user_prompt,
            user_prompt_redacted=user_prompt_redacted,
            error_message=None,
            validated_plan={},
            evidence_summary={
                "request_fingerprint": request_fingerprint,
                "scope_fingerprint": scope_fingerprint,
                "eval_id": eval_id,
                "retry_settings": retry_settings,
            },
            response_payload={},
            outcome="answer",
            route_used="local_rules",
            provider_calls=0,
            total_ms=0.0,
            created_at=now_dt,
        )
        try:
            self.db.add(turn)
            self.db.commit()
            self.db.refresh(turn)
            return turn, False
        except IntegrityError:
            self.db.rollback()
            raced = (
                self.db.query(AiTurn)
                .filter(
                    AiTurn.conversation_id == str(conversation_id),
                    AiTurn.client_request_id == str(client_request_id),
                )
                .first()
            )
            if raced is not None:
                ev_raced = dict(raced.evidence_summary or {})
                stored_req_fp = str(ev_raced.get("request_fingerprint") or "").strip()
                stored_scope_fp = str(ev_raced.get("scope_fingerprint") or "").strip()
                stored_eval_id = str(ev_raced.get("eval_id") or "").strip()
                if stored_req_fp and request_fingerprint and stored_req_fp != request_fingerprint:
                    raise RequestIdReuseConflictError(
                        "client_request_id was already used with a different prompt or filter context."
                    )
                if (
                    raced.status == "completed"
                    and raced.response_payload
                    and stored_req_fp
                    and stored_scope_fp
                    and stored_eval_id
                    and stored_req_fp == request_fingerprint
                    and stored_scope_fp == scope_fingerprint
                    and stored_eval_id == eval_id
                ):
                    return raced, True
            raise TurnAlreadyInFlightError("Concurrent request is already processing this turn.")

    def reclaim_turn_for_recompute(
        self,
        *,
        turn: AiTurn,
        user_prompt: str | None = None,
        user_prompt_redacted: str,
        request_fingerprint: str,
        scope_fingerprint: str,
        eval_id: str,
        was_completed: bool = True,
        deadline_seconds: int = 15,
    ) -> AiTurn:
        """Atomically reclaim a turn so it can be recomputed under current scope/data."""
        now_dt = datetime.now(timezone.utc)
        deadline_dt = now_dt + timedelta(seconds=max(5, deadline_seconds))
        claim_tok = str(uuid.uuid4())
        ev_sum = dict(turn.evidence_summary or {})
        ev_sum["request_fingerprint"] = request_fingerprint
        ev_sum["scope_fingerprint"] = scope_fingerprint
        ev_sum["eval_id"] = eval_id
        ev_sum["reclaimed_from_completed"] = bool(was_completed)

        update_fields: dict[Any, Any] = {
            AiTurn.status: "pending",
            AiTurn.claim_token: claim_tok,
            AiTurn.processing_deadline: deadline_dt,
            AiTurn.user_prompt_redacted: user_prompt_redacted,
            AiTurn.error_message: None,
            AiTurn.evidence_summary: ev_sum,
        }
        if user_prompt is not None:
            update_fields[AiTurn.user_prompt] = user_prompt

        updated = (
            self.db.query(AiTurn)
            .filter(
                AiTurn.id == turn.id,
                AiTurn.claim_token == turn.claim_token,
            )
            .update(
                update_fields,
                synchronize_session=False,
            )
        )
        self.db.commit()
        if updated == 0:
            raise TurnAlreadyInFlightError(
                "Turn claim was acquired by another concurrent request."
            )
        self.db.refresh(turn)
        return turn

    def release_turn_claim(
        self,
        *,
        turn_id: str,
        claim_token: str | None,
        error_message: str | None = None,
        conversation_id: str | None = None,
        title_candidate: str | None = None,
    ) -> None:
        """Release an active turn claim when a request fails before or during completion."""
        if not turn_id or not claim_token:
            return
        now_dt = datetime.now(timezone.utc)
        update_fields: dict[Any, Any] = {
            AiTurn.status: "failed",
            AiTurn.processing_deadline: now_dt - timedelta(seconds=1),
        }
        if error_message is not None:
            update_fields[AiTurn.error_message] = str(error_message)[:500]
        updated = self.db.query(AiTurn).filter(
            AiTurn.id == str(turn_id),
            AiTurn.claim_token == str(claim_token),
            AiTurn.status == "pending",
        ).update(
            update_fields,
            synchronize_session=False,
        )
        if updated and conversation_id:
            conv_updates: dict[Any, Any] = {AiConversation.updated_at: now_dt}
            if title_candidate:
                conv_row = (
                    self.db.query(AiConversation)
                    .filter(AiConversation.id == str(conversation_id))
                    .first()
                )
                if conv_row is not None and not (conv_row.title or "").strip():
                    conv_updates[AiConversation.title] = title_candidate[:200]
            self.db.query(AiConversation).filter(
                AiConversation.id == str(conversation_id)
            ).update(conv_updates, synchronize_session=False)
        self.db.commit()

    def complete_turn_and_advance_context(
        self,
        *,
        conversation_id: str,
        owner_user_id: str,
        expected_context_version: int | None,
        turn_id: str,
        claim_token: str | None = None,
        validated_plan: dict[str, Any] | None = None,
        evidence_summary: dict[str, Any] | None = None,
        response_payload: dict[str, Any],
        outcome: str = "answer",
        route_used: str = "local_rules",
        provider_calls: int = 0,
        total_ms: float = 0.0,
        new_confirmed_context: dict[str, Any] | None = None,
        pending_clarification: dict[str, Any] | None = None,
        last_subject_employee_id: str | None = None,
        last_subject_employee_name: str | None = None,
        last_operation_kind: str | None = None,
        title_candidate: str | None = None,
    ) -> int:
        """Atomically verify claim ownership and context version, complete the turn, and advance context_version."""
        self._require_schema_ready()
        if not claim_token:
            raise ConversationStaleContextError("Missing turn claim_token for turn completion.")

        now_dt = datetime.now(timezone.utc)
        conv = self.get_owned_conversation(
            conversation_id=conversation_id,
            owner_user_id=owner_user_id,
            include_deleted=True,
        )
        if conv is None:
            raise ConversationOwnershipError("Conversation not found.")
        if conv.status == "deleted":
            raise ConversationDeletedError("Conversation was deleted before turn completion.")

        existing_turn = self.db.query(AiTurn).filter(AiTurn.id == str(turn_id)).first()
        reclaimed_completed = bool(
            existing_turn
            and isinstance(existing_turn.evidence_summary, dict)
            and existing_turn.evidence_summary.get("reclaimed_from_completed")
        )

        current_ver = int(conv.context_version)
        if expected_context_version is not None and int(expected_context_version) > 0:
            exp_ver = int(expected_context_version)
            if reclaimed_completed and current_ver == exp_ver + 1:
                target_version = current_ver
            else:
                target_version = exp_ver
        else:
            target_version = current_ver

        if current_ver != target_version:
            # Release the turn claim if owned by this worker so a retry is not blocked
            self.release_turn_claim(turn_id=str(turn_id), claim_token=str(claim_token))
            raise ConversationStaleContextError(
                f"Stale context_version {target_version}; current is {current_ver}."
            )

        next_version = target_version + 1
        response_with_version = dict(response_payload)
        response_with_version["conversation_id"] = str(conversation_id)
        response_with_version["turn_id"] = str(turn_id)
        response_with_version["context_version"] = next_version

        merged_ev_summary = dict((existing_turn.evidence_summary if existing_turn else None) or {})
        merged_ev_summary.update(dict(evidence_summary or {}))
        merged_ev_summary.pop("reclaimed_from_completed", None)

        updated_turn = (
            self.db.query(AiTurn)
            .filter(
                AiTurn.id == str(turn_id),
                AiTurn.conversation_id == str(conversation_id),
                AiTurn.status == "pending",
                AiTurn.claim_token == str(claim_token),
            )
            .update(
                {
                    AiTurn.status: "completed",
                    AiTurn.error_message: None,
                    AiTurn.validated_plan: dict(validated_plan or {}),
                    AiTurn.evidence_summary: merged_ev_summary,
                    AiTurn.response_payload: response_with_version,
                    AiTurn.outcome: str(outcome or "answer"),
                    AiTurn.route_used: str(route_used or "local_rules"),
                    AiTurn.provider_calls: int(provider_calls or 0),
                    AiTurn.total_ms: float(total_ms or 0.0),
                    AiTurn.completed_at: now_dt,
                },
                synchronize_session=False,
            )
        )
        if updated_turn == 0:
            self.db.rollback()
            raise ConversationStaleContextError(
                "Turn claim token was superseded or turn was already completed by another worker."
            )

        conv_update_fields: dict[Any, Any] = {
            AiConversation.context_version: next_version,
            AiConversation.confirmed_context: dict(new_confirmed_context or {}),
            AiConversation.pending_clarification: pending_clarification,
            AiConversation.last_subject_employee_id: last_subject_employee_id,
            AiConversation.last_subject_employee_name: last_subject_employee_name,
            AiConversation.last_operation_kind: last_operation_kind,
            AiConversation.updated_at: now_dt,
        }
        if title_candidate and not (conv.title or "").strip():
            conv_update_fields[AiConversation.title] = title_candidate[:200]

        updated_conv = (
            self.db.query(AiConversation)
            .filter(
                AiConversation.id == str(conversation_id),
                AiConversation.owner_user_id == str(owner_user_id or "anonymous"),
                AiConversation.status == "active",
                AiConversation.context_version == target_version,
            )
            .update(
                conv_update_fields,
                synchronize_session=False,
            )
        )
        if updated_conv == 0:
            self.db.rollback()
            self.release_turn_claim(turn_id=str(turn_id), claim_token=str(claim_token))
            raise ConversationStaleContextError(
                f"Concurrent turn advanced conversation context_version from {target_version}."
            )

        self.db.commit()
        return next_version

    def cleanup_expired_conversations_and_traces(
        self,
        *,
        conversation_retention_days: int = 30,
        trace_retention_days: int = 90,
    ) -> dict[str, int]:
        self._require_schema_ready()
        now_dt = datetime.now(timezone.utc)
        conv_cutoff = now_dt - timedelta(days=max(1, conversation_retention_days))
        trace_cutoff = now_dt - timedelta(days=max(1, trace_retention_days))

        deleted_convs = (
            self.db.query(AiConversation)
            .filter(AiConversation.updated_at < conv_cutoff)
            .delete(synchronize_session=False)
        )
        deleted_traces = (
            self.db.query(AiInteractionTrace)
            .filter(
                AiInteractionTrace.created_at < trace_cutoff,
                AiInteractionTrace.reviewer_verified.is_(False),
            )
            .delete(synchronize_session=False)
        )
        self.db.commit()
        return {
            "deleted_conversations": int(deleted_convs or 0),
            "deleted_traces": int(deleted_traces or 0),
        }
