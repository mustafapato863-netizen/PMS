"""Dormant bounded stager and one-transaction promotion for an approved month.

This service does not dispatch a worker, register a route, or call
``EvaluationWorkflow.apply``. Pages read one keyset of the captured scope.
Promotion commits scores, one manifest revision, and one outbox row together,
or it commits nothing. The outbox stays unpublished; delivery is later work.

Row locks follow the upload team fence, then processing job, evaluation scope,
apply control, and performance record. Capture, stage, promote, and rollback
reread the persisted user after that fence. The read does not lock the user
row. A completed promote replay may carry a stale epoch and still must not
write. Source fingerprints reread the whole captured month, so a bounded page
is not linear query cost.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import uuid
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import and_, exists, func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from models.models import (
    CacheInvalidationOutbox,
    EvaluationApplyControl,
    EvaluationApplyStageRow,
    EvaluationRevision,
    EvaluationScope,
    KPIValue,
    PerformanceRecord,
    ProcessingJob,
    Team,
    TeamConfigurationVersion,
    User,
)
from services.evaluation.apply_job_schema import (
    JOB_KIND_EVALUATION_APPLY,
    NAMESPACE_DATA,
    STAGE_TABLE,
    cache_dedup_key,
    canonical_row_hash,
)
from services.evaluation.catalog import EvaluationCatalog
from services.evaluation.periods import month_aliases, month_name, month_number
from services.evaluation.resolver import (
    basis_payload,
    lock_team_rows,
    require_approved_capability,
    score_basis,
)
from services.evaluation.scoring import ENGINE_VERSION
from services.evaluation.workflow import (
    EvaluationConflict,
    EvaluationError,
    _captured_source,
    _checksum,
    _evidence_item,
    _evidence_matches,
    _freeze,
    _json_default,
    _known_actor,
    _payload_dict,
    _retained_source,
    _rules_checksum,
    _source_item,
    record_source_rows,
)
from services.evaluation.access import AccessDenied
from utils.performance_status import status_for_grade
from utils.team_identity import logical_team_name

logger = logging.getLogger(__name__)

MANIFEST_SCHEMA = "evaluation_apply_manifest_v1"
MANIFEST_FIELDS = (
    "schema",
    "job_id",
    "claim_epoch",
    "evidence_table",
    "record_count",
    "before_hash",
    "after_hash",
)
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500
SCAN_PAGE_SIZE = 200
FAULT_POINTS = (
    "before_score_write",
    "after_score_write",
    "before_revision_insert",
    "after_revision_insert",
    "before_control_promotion",
    "after_control_promotion",
    "before_outbox_insert",
    "after_outbox_insert",
    "before_commit",
)
_QUANTUM = {
    "score": Decimal("0.01"),
    "kpi": Decimal("0.0001"),
}


class StreamingChecksum:
    """ASCII SHA-256 of a JSON array, one object at a time.

    The digest matches ``workflow._checksum`` of that array. It is not
    ``canonical_row_hash``: that helper keeps Unicode code points, and this
    one uses the existing ASCII encoding.
    """

    def __init__(self) -> None:
        self._hash = hashlib.sha256()
        self._hash.update(b"[")
        self.count = 0

    def add(self, item: dict) -> None:
        if self.count:
            self._hash.update(b",")
        payload = json.dumps(item, sort_keys=True, separators=(",", ":"), default=_json_default)
        self._hash.update(payload.encode("utf-8"))
        self.count += 1

    def hexdigest(self) -> str:
        clone = self._hash.copy()
        clone.update(b"]")
        return clone.hexdigest()


def _manifest_problems(snapshot: dict) -> bool:
    if snapshot.get("schema") != MANIFEST_SCHEMA or "records" in snapshot:
        return True
    count = snapshot.get("record_count")
    epoch = snapshot.get("claim_epoch")
    if type(count) is not int or count < 0 or type(epoch) is not int or epoch < 0:
        return True
    if snapshot.get("evidence_table") != STAGE_TABLE:
        return True
    try:
        uuid.UUID(str(snapshot.get("job_id")))
    except (TypeError, ValueError, AttributeError):
        return True
    for key in ("before_hash", "after_hash"):
        value = snapshot.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            return True
    return False


def classify_snapshot(snapshot) -> str:
    """Legacy full snapshots stay legacy. Only the known manifest schema is staged evidence."""
    if not isinstance(snapshot, dict):
        return "legacy"
    schema = snapshot.get("schema")
    if not isinstance(schema, str) or not schema.startswith("evaluation_apply_manifest"):
        return "legacy"
    if schema != MANIFEST_SCHEMA:
        return "unknown_manifest"
    if _manifest_problems(snapshot):
        return "malformed"
    return "manifest"


def _require_manifest_agreement(applied, prior) -> None:
    """Prior and applied manifests are one document pair, not two independent hashes."""
    if classify_snapshot(applied) != "manifest" or classify_snapshot(prior) != "manifest":
        raise EvaluationConflict(
            "Stored revision manifest cannot be read.",
            code="invalid_manifest",
        )
    for key in MANIFEST_FIELDS:
        if applied.get(key) != prior.get(key):
            raise EvaluationConflict(
                "Stored revision manifest cannot be read.",
                code="invalid_manifest",
            )


def guard_loaded_manifest(db, applied, prior) -> None:
    """Legacy snapshots stay on their own path. A manifest must match staged hashes."""
    kind = classify_snapshot(applied)
    if kind == "legacy":
        return
    if kind != "manifest" or classify_snapshot(prior) != "manifest":
        raise EvaluationConflict(
            "Stored revision manifest cannot be read. Rollback made no changes.",
            code="invalid_manifest",
        )
    _require_manifest_agreement(applied, prior)
    service = BoundedApplyService(db)
    service._verify_stage_manifest(applied, side="after")


def applied_count(snapshot) -> int:
    """Count from the manifest. A legacy snapshot still uses its record list."""
    kind = classify_snapshot(snapshot)
    if kind == "legacy":
        if not isinstance(snapshot, dict):
            return 0
        records = snapshot.get("records")
        return len(records) if isinstance(records, list) else 0
    if kind == "manifest":
        return int(snapshot["record_count"])
    raise EvaluationConflict(
        "Stored revision manifest cannot be read.",
        code="invalid_manifest",
    )


def _scaled(value, places: str) -> str:
    quantum = _QUANTUM[places]
    number = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    text_value = format(number, "f")
    if "." in text_value:
        text_value = text_value.rstrip("0").rstrip(".")
    if text_value in {"", "-0"}:
        return "0"
    return text_value


def _page_size(value) -> int:
    if type(value) is not int or value < 1 or value > MAX_PAGE_SIZE:
        raise EvaluationError("Page size must be an integer from 1 to 500.", code="invalid_page")
    return value


def _encode_cursor(year: int, record_id) -> str:
    return f"{int(year)}:{record_id}"


def _decode_cursor(value: str | None):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or len(value) > 80 or ":" not in value:
        raise EvaluationError("Stage cursor is not valid.", code="invalid_cursor")
    year_text, id_text = value.split(":", 1)
    if not year_text.isdigit():
        raise EvaluationError("Stage cursor is not valid.", code="invalid_cursor")
    try:
        parsed = uuid.UUID(id_text)
    except (TypeError, ValueError, AttributeError) as exc:
        raise EvaluationError("Stage cursor is not valid.", code="invalid_cursor") from exc
    return int(year_text), parsed


def _sha256_text(value) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _kpi_identity(body: dict) -> list[str]:
    kpis = body.get("kpis")
    if not isinstance(kpis, list) or any(not isinstance(item, dict) or not item.get("id") for item in kpis):
        raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
    found = [str(item["id"]) for item in kpis]
    if len(found) != len(set(found)):
        raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
    return found


class BoundedApplyService:
    def __init__(self, db):
        self.db = db
        self.catalog = EvaluationCatalog(db)

    def capture(self, actor: dict, scope_id, year: int, month) -> dict:
        try:
            body = self._capture(actor, scope_id, year, month)
            self._fault("before_commit")
            self.db.commit()
            self.db.expunge_all()
            return body
        except Exception:
            self.db.rollback()
            self.db.expunge_all()
            raise

    def stage_page(
        self,
        actor: dict,
        job_id,
        *,
        page_size: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
        replay: bool = False,
        expected_epoch: int | None = None,
    ) -> dict:
        try:
            body = self._stage_page(
                actor,
                job_id,
                page_size=page_size,
                cursor=cursor,
                replay=replay,
                expected_epoch=expected_epoch,
            )
            self._fault("before_commit")
            self.db.commit()
            self.db.expunge_all()
            return body
        except Exception:
            self.db.rollback()
            self.db.expunge_all()
            raise

    def promote(self, actor: dict, job_id, *, expected_epoch: int | None = None) -> dict:
        try:
            body = self._promote(actor, job_id, expected_epoch=expected_epoch)
            self._fault("before_commit")
            self.db.commit()
            self.db.expunge_all()
            return body
        except Exception:
            self.db.rollback()
            self.db.expunge_all()
            raise

    def rollback_latest(self, actor: dict, revision_id) -> dict:
        try:
            body = self._rollback(actor, revision_id)
            self._fault("before_commit")
            self.db.commit()
            self.db.expunge_all()
            return body
        except Exception:
            self.db.rollback()
            self.db.expunge_all()
            raise

    def read_manifest(self, revision_id) -> dict:
        revision = self._revision(revision_id)
        self._require_manifest_pair(revision)
        _require_manifest_agreement(revision.applied_snapshot, revision.prior_snapshot)
        self._bind_promoted_identity(revision, revision.applied_snapshot)
        checked = self._verify_stage_manifest(revision.applied_snapshot, side="after")
        return {
            "schema": MANIFEST_SCHEMA,
            "job_id": str(checked["job_id"]),
            "claim_epoch": checked["claim_epoch"],
            "record_count": checked["record_count"],
            "before_hash": checked["before_hash"],
            "after_hash": checked["after_hash"],
            "verified": True,
        }

    def restore_manifest(self, revision: EvaluationRevision) -> list[dict]:
        """Restore one manifest inside the caller's open transaction. Does not commit."""
        self._require_manifest_pair(revision)
        _require_manifest_agreement(revision.applied_snapshot, revision.prior_snapshot)
        self._bind_promoted_identity(revision, revision.applied_snapshot)
        restored = self._restore_manifest_rows(revision)
        return [{"restored_count": restored}]

    def _capture(self, actor: dict, scope_id, year: int, month) -> dict:
        number = month_number(month)
        peeked = self._peek_scope(scope_id)
        team, user = self._team_fence(peeked.team_id, actor)
        open_peek = self._peek_open_control(peeked.id, int(year), number)
        if open_peek is not None:
            _job, control, scope = self._lock_existing_header(open_peek, team)
            if control.state == "promoting":
                raise EvaluationConflict("An evaluation apply is already promoting.", code="duplicate_binding")
            if control.state not in {"pending", "staging"}:
                raise EvaluationConflict("Captured scope identity no longer matches.", code="stale_preview")
            self._revalidate_scope_peek(peeked, scope, team)
            self._admit(scope, int(year), number)
            version, _resolved, rules = self._approved_version(scope, int(year), number, lock=True)
            proof = self._proof_header(version, scope, rules)
            fingerprint, expected = self._stream_source(scope, int(year), number, lock=True)
            self._require_source_proof(proof, fingerprint, expected)
            return self._capture_body(control, expected, resumed=True)
        scope = self._lock_query(
            self.db.query(EvaluationScope).filter(EvaluationScope.id == peeked.id),
            True,
        ).one_or_none()
        if scope is None:
            raise EvaluationError("Evaluation scope was not found.", code="not_found")
        self._revalidate_scope_peek(peeked, scope, team)
        self._admit(scope, int(year), number)
        version, _resolved, rules = self._approved_version(scope, int(year), number, lock=True)
        proof = self._proof_header(version, scope, rules)
        fingerprint, expected = self._stream_source(scope, int(year), number, lock=False)
        self._require_source_proof(proof, fingerprint, expected)
        lineage = self._lineage_fingerprint(scope, int(year), number)
        job = ProcessingJob(
            id=uuid.uuid4(),
            kind=JOB_KIND_EVALUATION_APPLY,
            status="queued",
            requested_by_user_id=user.id,
            requested_by_name=(user.full_name or user.username or "Admin")[:255],
            request_json={
                "scope_id": str(scope.id),
                "year": int(year),
                "month": number,
                "expected_count": expected,
            },
            result_json=None,
            claim_epoch=0,
            progress=0,
            idempotency_key=f"evaluation-apply:{scope.id}:{int(year)}:{number}:{uuid.uuid4().hex}",
        )
        self.db.add(job)
        self.db.flush()
        control = EvaluationApplyControl(
            job_id=job.id,
            scope_id=scope.id,
            version_id=version.id,
            team_id=scope.team_id,
            performance_level=scope.performance_level,
            position_name=scope.position_name or "",
            year=int(year),
            month=number,
            engine_version=ENGINE_VERSION,
            rules_checksum=rules,
            proof_source_fingerprint=fingerprint,
            lineage_fingerprint=lineage,
            requested_by_user_id=user.id,
            actor_snapshot=self._actor_snapshot(user),
            state="pending",
            claim_epoch=0,
            staged_count=0,
            promoted_count=0,
        )
        self.db.add(control)
        self.db.flush()
        control.state = "staging"
        job.status = "running"
        self.db.flush()
        confirmed, confirmed_count = self._stream_source(scope, int(year), number, lock=True)
        if confirmed != fingerprint or confirmed_count != expected:
            raise EvaluationConflict(
                "Impact preview is stale because stored evidence changed.",
                code="stale_preview",
            )
        logger.info("evaluation apply captured job=%s count=%s", control.job_id, expected)
        return self._capture_body(control, expected, resumed=False)

    def _stage_page(self, actor, job_id, *, page_size, cursor, replay, expected_epoch) -> dict:
        size = _page_size(page_size)
        user, job, control, scope = self._locked_header(job_id, actor)
        self._require_open_actor(control, user)
        if control.state != "staging":
            raise EvaluationConflict("Evaluation apply is not staging.", code="invalid_state")
        self._epoch(job, control, expected_epoch)
        version, resolved, rules = self._approved_version(scope, control.year, control.month, lock=True)
        self._require_captured_version(control, version, rules)
        fingerprint, live_count = self._stream_source(scope, control.year, control.month, lock=True)
        expected = self._expected_count(job)
        if fingerprint != control.proof_source_fingerprint or live_count != expected:
            raise EvaluationConflict(
                "Stored evidence changed between pages. Nothing else was staged.",
                code="evidence_changed",
            )
        start = self._page_start(control, cursor, replay)
        records = self._record_page(scope, control.year, control.month, start, size, lock=True)
        staged = self._stage_rows_for_page(control, records)
        inserted = 0
        for record in records:
            self._assert_month_text(record, control.month)
            before, after = self._project(version, record, resolved)
            if self._put_stage(control, record, before, after, staged):
                inserted += 1
        self.db.flush()
        if records and not replay:
            end = _encode_cursor(int(records[-1].year), records[-1].id)
            if control.stage_cursor != end:
                control.stage_cursor = end
            control.staged_count = int(control.staged_count or 0) + inserted
        elif records and replay and inserted:
            raise EvaluationConflict("A replay tried to add rows the cursor had not reached.", code="conflicting_stage")
        self.db.flush()
        self._release(records)
        staged = int(control.staged_count or 0)
        logger.info(
            "evaluation apply page job=%s epoch=%s inserted=%s staged=%s",
            control.job_id,
            control.claim_epoch,
            inserted,
            staged,
        )
        return {
            "job_id": str(control.job_id),
            "claim_epoch": int(control.claim_epoch),
            "page_cursor": "" if start is None else _encode_cursor(*start),
            "next_cursor": control.stage_cursor or "",
            "page_count": len(records),
            "inserted_count": inserted,
            "staged_count": staged,
            "complete": staged == expected and not (records and not replay and len(records) == size and staged < expected),
            "idempotent": inserted == 0,
        }

    def _promote(self, actor, job_id, *, expected_epoch) -> dict:
        user, job, control, scope = self._locked_header(job_id, actor)
        if control.state == "promoted" and control.promoted_revision_id is not None:
            # Read-only. A stale expected_epoch is tolerated and does not write.
            # The persisted user was reread after the team fence. The stored
            # actor snapshot remains attribution.
            return {
                "job_id": str(control.job_id),
                "revision_id": str(control.promoted_revision_id),
                "idempotent": True,
                "applied_count": int(control.promoted_count or 0),
                "state": "promoted",
            }
        self._require_open_actor(control, user)
        if control.state != "staging":
            raise EvaluationConflict("Evaluation apply is not ready to promote.", code="invalid_state")
        self._epoch(job, control, expected_epoch)
        version, _resolved, rules = self._approved_version(scope, control.year, control.month, lock=True)
        self._require_captured_version(control, version, rules)
        if control.engine_version != ENGINE_VERSION:
            raise EvaluationConflict("The scoring engine changed before promotion.", code="stale_preview")
        proof = self._proof_header(version, scope, rules)
        if rules != control.rules_checksum or proof.get("source_fingerprint") != control.proof_source_fingerprint:
            raise EvaluationConflict("Approved rules or proof changed before promotion.", code="stale_preview")
        lineage = self._lineage_fingerprint(scope, control.year, control.month)
        if lineage != control.lineage_fingerprint:
            raise EvaluationConflict("Revision lineage changed before promotion.", code="lineage_changed")
        fingerprint, live_count = self._stream_source(scope, control.year, control.month, lock=True)
        expected = self._expected_count(job)
        if fingerprint != control.proof_source_fingerprint or live_count != expected:
            raise EvaluationConflict("Stored evidence changed before promotion. Nothing was promoted.", code="evidence_changed")
        if expected <= 0 or int(control.staged_count or 0) != expected:
            raise EvaluationError("Staged evidence is incomplete. Promotion is blocked.", code="incomplete_stage")
        self._require_stage_coverage(control, scope, expected)
        self._fault("before_score_write")
        control.state = "promoting"
        self.db.flush()
        self._write_scores(control, scope)
        self._fault("after_score_write")
        manifest_body = self._manifest_document(control)
        self._fault("before_revision_insert")
        revision = self._insert_revision(scope, control, version, user, manifest_body)
        self._fault("after_revision_insert")
        self._fault("before_control_promotion")
        control.promoted_count = expected
        control.promoted_revision_id = revision.id
        control.state = "promoted"
        self.db.flush()
        self._fault("after_control_promotion")
        self._fault("before_outbox_insert")
        self._insert_outbox(control, revision)
        self._fault("after_outbox_insert")
        job.status = "succeeded"
        job.progress = 100
        job.result_json = {
            "outcome": "promoted",
            "revision_id": str(revision.id),
            "count": expected,
        }
        self.db.flush()
        logger.info("evaluation apply promoted job=%s revision=%s count=%s", control.job_id, revision.id, expected)
        return {
            "job_id": str(control.job_id),
            "revision_id": str(revision.id),
            "idempotent": False,
            "applied_count": expected,
            "state": "promoted",
        }

    def _rollback(self, actor, revision_id) -> dict:
        parsed = _uuid(revision_id, "Revision was not found.")
        peeked = (
            self.db.query(
                EvaluationRevision.id,
                EvaluationRevision.team_id,
                EvaluationRevision.performance_level,
                EvaluationRevision.position_name,
                EvaluationRevision.year,
                EvaluationRevision.month,
                EvaluationRevision.version_id,
            )
            .filter(EvaluationRevision.id == parsed)
            .one_or_none()
        )
        if peeked is None or peeked.team_id is None:
            raise EvaluationError("Revision was not found.", code="not_found")
        team, _user = self._team_fence(peeked.team_id, actor)
        loaded = self.db.query(EvaluationRevision).filter(EvaluationRevision.id == parsed).one_or_none()
        if loaded is None:
            raise EvaluationError("Revision was not found.", code="not_found")
        held_applied = copy.deepcopy(loaded.applied_snapshot) if isinstance(loaded.applied_snapshot, dict) else loaded.applied_snapshot
        held_prior = copy.deepcopy(loaded.prior_snapshot) if isinstance(loaded.prior_snapshot, dict) else loaded.prior_snapshot
        self.db.expire(loaded, ["applied_snapshot", "prior_snapshot"])
        self._lock_revision_graph(peeked, team, held_applied)
        revision = self._locked_revision(parsed)
        self._revalidate_revision_peek(peeked, revision, team)
        guard_loaded_manifest(self.db, held_applied, held_prior)
        self._require_latest(revision)
        kind = classify_snapshot(revision.applied_snapshot)
        if kind == "legacy":
            raise EvaluationConflict(
                "This rollback entry point is for a staged manifest. The stored snapshot is a legacy revision.",
                code="legacy_snapshot",
            )
        if kind != "manifest" or classify_snapshot(revision.prior_snapshot) != "manifest":
            raise EvaluationConflict("Stored revision manifest cannot be read. Rollback made no changes.", code="invalid_manifest")
        restored = self.restore_manifest(revision)
        revision.status = "rolled_back"
        self.db.flush()
        logger.info("evaluation apply rolled back revision=%s", revision.id)
        return {
            "revision_id": str(revision.id),
            "status": "rolled_back",
            "restored_basis": restored,
            "restored_revision_id": None,
        }

    def _write_scores(self, control, scope) -> None:
        cursor = None
        written = 0
        while True:
            records = self._record_page(scope, control.year, control.month, cursor, DEFAULT_PAGE_SIZE, lock=True)
            if not records:
                break
            identities = [(record.id, int(record.year)) for record in records]
            staged = {
                (row.record_id, int(row.record_year)): row
                for row in self.db.query(EvaluationApplyStageRow).filter(
                    EvaluationApplyStageRow.job_id == control.job_id,
                    EvaluationApplyStageRow.claim_epoch == control.claim_epoch,
                    EvaluationApplyStageRow.record_id.in_([item[0] for item in identities]),
                    EvaluationApplyStageRow.record_year == int(control.year),
                )
            }
            for record in records:
                stage = staged.get((record.id, int(record.year)))
                if stage is None:
                    raise EvaluationConflict("Staged evidence is incomplete. Promotion is blocked.", code="incomplete_stage")
                self._check_stage_row(control, stage)
                current = _evidence_item(record)
                if canonical_row_hash(current) != stage.before_hash or current != stage.before_row:
                    raise EvaluationConflict(
                        "Stored evidence changed before promotion. Nothing was promoted.",
                        code="evidence_changed",
                    )
                self._apply_after(record, stage.after_row)
                written += 1
            self.db.flush()
            cursor = (int(records[-1].year), records[-1].id)
            self._release(records)
            self._release(list(staged.values()))
        if written != int(control.staged_count or 0):
            raise EvaluationConflict("Staged evidence is incomplete. Promotion is blocked.", code="incomplete_stage")

    def _apply_after(self, record: PerformanceRecord, after: dict) -> None:
        if str(record.id) != str(after.get("id")) or int(record.year) != int(after.get("year")):
            raise EvaluationConflict("Stored evidence changed before promotion. Nothing was promoted.", code="evidence_changed")
        current = _evidence_item(record)
        live_ids = {item["id"] for item in current["kpis"]}
        saved_ids = _kpi_identity(after)
        if live_ids != set(saved_ids):
            raise EvaluationConflict("Stored KPI evidence changed before promotion. Nothing was promoted.", code="evidence_changed")
        by_id = {str(item["id"]): item for item in after["kpis"]}
        actuals = {item["id"]: item.get("actual") for item in current["kpis"]}
        for value in record.kpi_values:
            saved = by_id[str(value.id)]
            if saved.get("actual") != actuals.get(str(value.id)):
                raise EvaluationConflict(
                    "Stored evidence changed before promotion. Nothing was promoted.",
                    code="evidence_changed",
                )
            for field in ("target", "achievement", "weight", "contribution"):
                if saved.get(field) is None:
                    raise EvaluationConflict("Staged KPI evidence is incomplete. Promotion is blocked.", code="invalid_manifest")
            value.target_value = Decimal(str(saved["target"]))
            value.achievement_ratio = Decimal(str(saved["achievement"]))
            value.weight_applied = Decimal(str(saved["weight"]))
            value.contribution = Decimal(str(saved["contribution"]))
        record.score = Decimal(str(after["score"]))
        record.grade = after["grade"]
        record.status = after["status"]
        record.record_payload = after.get("payload")
        flag_modified(record, "record_payload")

    def _project(self, version, record, resolved) -> tuple[dict, dict]:
        before = _evidence_item(record)
        missing, rows, _conflicts = record_source_rows(version, record, resolved)
        if missing:
            raise EvaluationError(
                "A weighted KPI has no stored actual. Staging is blocked.",
                code="missing_evidence",
                missing_count=len(missing),
            )
        if not rows:
            raise EvaluationError("Stored results have no KPI actuals. Staging is blocked.", code="insufficient_data")
        scored = score_basis(version, rows, check_conflicts=False)
        if scored.get("score") is None or not scored.get("grade"):
            raise EvaluationError("Stored results could not be scored. Staging is blocked.", code="insufficient_data")
        by_key = {row["kpi_key"]: row for row in scored["rows"]}
        evidence_keys = {item["kpi_key"] for item in before["kpis"]}
        for key in by_key:
            if key not in evidence_keys:
                raise EvaluationError("A scored KPI is not stored on the record. Staging is blocked.", code="missing_evidence")
        after_kpis = []
        for item in before["kpis"]:
            copy = dict(item)
            incoming = by_key.get(item["kpi_key"])
            if incoming is not None:
                if incoming.get("target") is None or incoming.get("achievement") is None or incoming.get("contribution") is None:
                    raise EvaluationError("Scoring did not return a complete KPI result. Staging is blocked.", code="insufficient_data")
                copy["target"] = _scaled(incoming["target"], "kpi")
                copy["achievement"] = _scaled(incoming["achievement"], "kpi")
                copy["weight"] = _scaled(incoming["weight"], "kpi")
                copy["contribution"] = _scaled(incoming["contribution"], "kpi")
            after_kpis.append(copy)
        payload = dict(record.record_payload or {})
        if _retained_source(payload) is None:
            payload["source_evidence"] = _captured_source(rows)
        payload["evaluation_basis"] = basis_payload(version)
        evaluation = dict(payload.get("evaluation") or {})
        evaluation["score"] = float(Decimal(_scaled(scored["score"], "score")))
        evaluation["grade"] = scored["grade"]
        payload["evaluation"] = evaluation
        after = dict(before)
        after["score"] = _scaled(scored["score"], "score")
        after["grade"] = scored["grade"]
        after["status"] = status_for_grade(scored["grade"])
        after["payload"] = _freeze(payload)
        after["kpis"] = after_kpis
        canonical_row_hash(before)
        canonical_row_hash(after)
        return before, after

    def _stage_rows_for_page(self, control, records) -> dict:
        """One lookup for this page. The map is not the captured population."""
        if not records:
            return {}
        years = sorted({int(record.year) for record in records})
        rows = self.db.query(EvaluationApplyStageRow).filter(
            EvaluationApplyStageRow.job_id == control.job_id,
            EvaluationApplyStageRow.claim_epoch == int(control.claim_epoch),
            EvaluationApplyStageRow.record_id.in_([record.id for record in records]),
            EvaluationApplyStageRow.record_year.in_(years),
        ).all()
        return {_stage_key(row.record_id, row.record_year): row for row in rows}

    def _put_stage(self, control, record, before: dict, after: dict, staged: dict) -> bool:
        before_hash = canonical_row_hash(before)
        after_hash = canonical_row_hash(after)
        existing = staged.get(_stage_key(record.id, record.year))
        if existing is not None:
            same = (
                existing.before_hash == before_hash
                and existing.after_hash == after_hash
                and existing.rules_checksum == control.rules_checksum
                and existing.before_row == before
                and existing.after_row == after
            )
            if not same:
                raise EvaluationConflict(
                    "Staged evidence no longer matches this page. The page was not rewritten.",
                    code="conflicting_stage",
                )
            return False
        self.db.add(
            EvaluationApplyStageRow(
                job_id=control.job_id,
                claim_epoch=int(control.claim_epoch),
                record_id=record.id,
                record_year=int(record.year),
                before_row=before,
                after_row=after,
                before_hash=before_hash,
                after_hash=after_hash,
                rules_checksum=control.rules_checksum,
            )
        )
        return True

    def _insert_revision(self, scope, control, version, user, manifest: dict) -> EvaluationRevision:
        revisions = self._revision_rows(scope, control.year, control.month, lock=True)
        head = _chain_head(revisions)
        active_ids = [row.id for row in revisions if row.status == "active"]
        if active_ids:
            (
                self.db.query(EvaluationRevision)
                .filter(EvaluationRevision.id.in_(active_ids))
                .update({EvaluationRevision.status: "superseded"}, synchronize_session=False)
            )
        self.db.flush()
        revision = EvaluationRevision(
            team_id=scope.team_id,
            performance_level=scope.performance_level,
            position_name=scope.position_name or "",
            year=int(control.year),
            month=int(control.month),
            version_id=version.id,
            status="active",
            previous_revision_id=None if head is None else head.id,
            prior_snapshot=manifest,
            applied_snapshot=manifest,
            created_by_user_id=user.id,
            actor_snapshot=_known_actor(user),
        )
        self.db.add(revision)
        try:
            self.db.flush()
        except IntegrityError as exc:
            raise EvaluationConflict("Another apply already recorded this revision.", code="duplicate_binding") from exc
        return revision

    def _insert_outbox(self, control, revision) -> None:
        self.db.add(
            CacheInvalidationOutbox(
                id=uuid.uuid4(),
                job_id=control.job_id,
                revision_id=revision.id,
                namespace=NAMESPACE_DATA,
                dedup_key=cache_dedup_key(control.job_id, revision.id),
                delivery_attempts=0,
                published_at=None,
                last_error=None,
            )
        )
        self.db.flush()

    def _manifest_document(self, control) -> dict:
        before = StreamingChecksum()
        after = StreamingChecksum()
        seen = 0
        for page in self._iter_stage(control.job_id, int(control.claim_epoch)):
            for row in page:
                self._check_stage_row(control, row)
                before.add(row.before_row)
                after.add(row.after_row)
                seen += 1
        if seen != int(control.staged_count or 0):
            raise EvaluationConflict("Staged evidence is incomplete. Promotion is blocked.", code="incomplete_stage")
        return {
            "schema": MANIFEST_SCHEMA,
            "job_id": str(control.job_id),
            "claim_epoch": int(control.claim_epoch),
            "evidence_table": STAGE_TABLE,
            "record_count": seen,
            "before_hash": before.hexdigest(),
            "after_hash": after.hexdigest(),
        }

    def _verify_stage_manifest(self, snapshot: dict, *, side: str) -> dict:
        if classify_snapshot(snapshot) != "manifest":
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        job_id = uuid.UUID(str(snapshot["job_id"]))
        control = self.db.query(EvaluationApplyControl).filter(EvaluationApplyControl.job_id == job_id).one_or_none()
        if control is None or int(control.claim_epoch) != int(snapshot["claim_epoch"]):
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        if control.state != "promoted" or control.promoted_revision_id is None:
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        before = StreamingChecksum()
        after = StreamingChecksum()
        seen = 0
        for page in self._iter_stage(job_id, int(snapshot["claim_epoch"])):
            for row in page:
                self._check_stage_row(control, row)
                before.add(row.before_row)
                after.add(row.after_row)
                seen += 1
        if seen != int(snapshot["record_count"]) or seen == 0:
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        if before.hexdigest() != snapshot["before_hash"] or after.hexdigest() != snapshot["after_hash"]:
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        if side not in {"before", "after"}:
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        return snapshot

    def _restore_manifest_rows(self, revision: EvaluationRevision) -> int:
        snapshot = self._verify_stage_manifest(revision.applied_snapshot, side="after")
        prior = revision.prior_snapshot if isinstance(revision.prior_snapshot, dict) else {}
        if any(prior.get(key) != snapshot.get(key) for key in ("schema", "job_id", "claim_epoch", "record_count", "before_hash", "after_hash", "evidence_table")):
            raise EvaluationConflict("Stored revision manifest cannot be read. Rollback made no changes.", code="invalid_manifest")
        scope = self._scope_for_revision(revision)
        cursor = None
        restored = 0
        job_id = uuid.UUID(str(snapshot["job_id"]))
        while True:
            records = self._record_page(scope, revision.year, revision.month, cursor, DEFAULT_PAGE_SIZE, lock=True)
            if not records:
                break
            staged = {
                (row.record_id, int(row.record_year)): row
                for row in self.db.query(EvaluationApplyStageRow).filter(
                    EvaluationApplyStageRow.job_id == job_id,
                    EvaluationApplyStageRow.claim_epoch == int(snapshot["claim_epoch"]),
                    EvaluationApplyStageRow.record_id.in_([record.id for record in records]),
                    EvaluationApplyStageRow.record_year == int(revision.year),
                )
            }
            for record in records:
                stage = staged.get((record.id, int(record.year)))
                if stage is None:
                    raise EvaluationConflict("Stored evidence no longer matches the applied snapshot. Rollback made no changes.", code="evidence_changed")
                current = _evidence_item(record)
                if canonical_row_hash(current) != stage.after_hash or current != stage.after_row:
                    raise EvaluationConflict("Stored evidence no longer matches the applied snapshot. Rollback made no changes.", code="evidence_changed")
                self._apply_before(record, stage.before_row)
                restored += 1
            self.db.flush()
            cursor = (int(records[-1].year), records[-1].id)
            self._release(records)
            self._release(list(staged.values()))
        if restored != int(snapshot["record_count"]):
            raise EvaluationConflict("Stored evidence no longer matches the applied snapshot. Rollback made no changes.", code="evidence_changed")
        return restored

    def _apply_before(self, record: PerformanceRecord, before: dict) -> None:
        live_ids = {str(value.id) for value in record.kpi_values}
        saved_ids = _kpi_identity(before)
        if live_ids != set(saved_ids) or str(record.id) != str(before.get("id")) or int(record.year) != int(before.get("year")):
            raise EvaluationConflict("Stored evidence no longer matches the applied snapshot. Rollback made no changes.", code="evidence_changed")
        by_id = {str(item["id"]): item for item in before["kpis"]}
        record.score = Decimal(str(before["score"]))
        record.grade = before["grade"]
        record.status = before["status"]
        record.record_payload = before.get("payload")
        flag_modified(record, "record_payload")
        for value in record.kpi_values:
            saved = by_id[str(value.id)]
            for field in ("actual", "target", "achievement", "weight", "contribution"):
                if saved.get(field) is None:
                    raise EvaluationConflict("A snapshotted KPI value is incomplete. Rollback made no changes.", code="evidence_changed")
            value.actual_value = Decimal(str(saved["actual"]))
            value.target_value = Decimal(str(saved["target"]))
            value.achievement_ratio = Decimal(str(saved["achievement"]))
            value.weight_applied = Decimal(str(saved["weight"]))
            value.contribution = Decimal(str(saved["contribution"]))

    def _check_stage_row(self, control, row: EvaluationApplyStageRow) -> None:
        if int(row.record_year) != int(control.year) or int(row.claim_epoch) != int(control.claim_epoch):
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        if row.rules_checksum != control.rules_checksum:
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        if canonical_row_hash(row.before_row) != row.before_hash or canonical_row_hash(row.after_row) != row.after_hash:
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        if str(row.before_row.get("id")) != str(row.record_id) or int(row.before_row.get("year")) != int(row.record_year):
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        if str(row.after_row.get("id")) != str(row.record_id) or int(row.after_row.get("year")) != int(row.record_year):
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        if _kpi_identity(row.before_row) != _kpi_identity(row.after_row):
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")

    def _stream_source(self, scope, year: int, month: int, *, lock: bool) -> tuple[str, int]:
        """Hash the whole captured month. A later page repeats this full read.

        Releasing each page keeps the identity map bounded. It does not make
        the fingerprint query count linear in the page size.
        """
        digest = StreamingChecksum()
        cursor = None
        while True:
            records = self._record_page(scope, year, month, cursor, SCAN_PAGE_SIZE, lock=lock)
            if not records:
                break
            for record in records:
                self._assert_month_text(record, month)
                digest.add(_source_item(_evidence_item(record)))
            cursor = (int(records[-1].year), records[-1].id)
            self._release(records)
        return digest.hexdigest(), digest.count

    def _record_page(self, scope, year, month, cursor, size: int, *, lock: bool):
        query = self._scope_query(scope, year, month).options(
            selectinload(PerformanceRecord.kpi_values),
            selectinload(PerformanceRecord.employee),
        )
        if cursor is not None:
            cursor_year, cursor_id = cursor
            query = query.filter(
                or_(
                    PerformanceRecord.year > int(cursor_year),
                    and_(PerformanceRecord.year == int(cursor_year), PerformanceRecord.id > cursor_id),
                )
            )
        records = self._lock_query(
            query.order_by(PerformanceRecord.year.asc(), PerformanceRecord.id.asc()).limit(size),
            lock,
        ).all()
        if lock and records and self._postgres():
            self._lock_query(
                self.db.query(KPIValue)
                .filter(
                    KPIValue.record_id.in_([row.id for row in records]),
                    KPIValue.record_year == int(year),
                )
                .order_by(KPIValue.id.asc()),
                True,
            ).all()
        return records

    def _iter_stage(self, job_id, epoch: int):
        cursor = None
        while True:
            query = self.db.query(EvaluationApplyStageRow).filter(
                EvaluationApplyStageRow.job_id == job_id,
                EvaluationApplyStageRow.claim_epoch == int(epoch),
            )
            if cursor is not None:
                cursor_year, cursor_id = cursor
                query = query.filter(
                    or_(
                        EvaluationApplyStageRow.record_year > int(cursor_year),
                        and_(
                            EvaluationApplyStageRow.record_year == int(cursor_year),
                            EvaluationApplyStageRow.record_id > cursor_id,
                        ),
                    )
                )
            rows = (
                query.order_by(EvaluationApplyStageRow.record_year.asc(), EvaluationApplyStageRow.record_id.asc())
                .limit(SCAN_PAGE_SIZE)
                .all()
            )
            if not rows:
                break
            yield rows
            cursor = (int(rows[-1].record_year), rows[-1].record_id)

    def _scope_query(self, scope, year: int, month: int):
        aliases = [item.casefold() for item in month_aliases(month)]
        position = scope.position_name or ""
        return self.db.query(PerformanceRecord).filter(
            PerformanceRecord.team_id == scope.team_id,
            PerformanceRecord.performance_level == scope.performance_level,
            PerformanceRecord.year == int(year),
            func.lower(PerformanceRecord.month).in_(aliases),
            func.coalesce(PerformanceRecord.position_name, "") == position,
        )

    def _require_stage_coverage(self, control, scope, expected: int) -> None:
        stage_count = (
            self.db.query(func.count())
            .select_from(EvaluationApplyStageRow)
            .filter(
                EvaluationApplyStageRow.job_id == control.job_id,
                EvaluationApplyStageRow.claim_epoch == control.claim_epoch,
            )
            .scalar()
        )
        live_count = self._scope_query(scope, control.year, control.month).count()
        if int(stage_count or 0) != expected or int(live_count or 0) != expected:
            raise EvaluationConflict("Staged evidence is incomplete. Promotion is blocked.", code="incomplete_stage")
        stage_exists = exists().where(
            and_(
                EvaluationApplyStageRow.job_id == control.job_id,
                EvaluationApplyStageRow.claim_epoch == control.claim_epoch,
                EvaluationApplyStageRow.record_id == PerformanceRecord.id,
                EvaluationApplyStageRow.record_year == PerformanceRecord.year,
            )
        )
        missing = self._scope_query(scope, control.year, control.month).filter(~stage_exists).limit(1).with_entities(PerformanceRecord.id).first()
        if missing is not None:
            raise EvaluationConflict("Staged evidence does not cover the captured month. Promotion is blocked.", code="incomplete_stage")

    def _locked_header(self, job_id, actor: dict):
        parsed = _uuid(job_id, "Evaluation apply was not found.")
        kind = self.db.query(ProcessingJob.kind).filter(ProcessingJob.id == parsed).scalar()
        peeked = self._peek_control(parsed)
        if kind != JOB_KIND_EVALUATION_APPLY or peeked is None or peeked.team_id is None:
            raise EvaluationError("Evaluation apply was not found.", code="not_found")
        team, user = self._team_fence(peeked.team_id, actor)
        job, control, scope = self._lock_existing_header(peeked, team)
        return user, job, control, scope

    def _team_fence(self, team_id, actor: dict) -> tuple[Team, User]:
        """Hold the upload team row, then reread the persisted user.

        The user SELECT does not use FOR UPDATE. A role change that committed
        before this statement is visible. A commit after this statement is not
        held off for the rest of the transaction. The users row stays outside
        the job, scope, control, and record lock order.
        """
        team = self._lock_team_id(team_id)
        return team, self._admin(actor)

    def _admin(self, actor: dict) -> User:
        raw = (actor or {}).get("user_id")
        if raw is None or str(raw).strip() == "":
            raise AccessDenied("Evaluation settings are limited to Admin.")
        try:
            parsed = uuid.UUID(str(raw))
        except (TypeError, ValueError, AttributeError) as exc:
            raise AccessDenied("Evaluation settings are limited to Admin.") from exc
        user = self.db.query(User).populate_existing().filter(User.id == parsed).one_or_none()
        if user is None or user.role != "Admin" or user.is_active is not True:
            raise AccessDenied("Evaluation settings are limited to Admin.")
        return user

    def _require_open_actor(self, control, user: User) -> None:
        if control.requested_by_user_id is None or control.requested_by_user_id != user.id:
            raise AccessDenied("Evaluation settings are limited to Admin.")
        if user.role != "Admin" or user.is_active is not True:
            raise AccessDenied("Evaluation settings are limited to Admin.")

    def _actor_snapshot(self, user: User) -> dict:
        return {
            "state": "known",
            "user_id": str(user.id),
            "username": user.username,
            "full_name": user.full_name,
            "role": user.role,
        }

    def _lock_team_id(self, team_id) -> Team:
        rows = lock_team_rows(self.db, [team_id])
        team = rows[0] if rows else None
        if team is None or team.is_active is not True:
            raise EvaluationError(
                "This team is inactive. It stays outside the supported rollout.",
                code="scope_blocked",
            )
        return team

    def _peek_scope(self, scope_id):
        parsed = _uuid(scope_id, "Evaluation scope was not found.")
        peeked = (
            self.db.query(
                EvaluationScope.id,
                EvaluationScope.team_id,
                EvaluationScope.performance_level,
                EvaluationScope.position_name,
            )
            .filter(EvaluationScope.id == parsed)
            .one_or_none()
        )
        if peeked is None or peeked.team_id is None:
            raise EvaluationError("Evaluation scope was not found.", code="not_found")
        return peeked

    def _peek_control(self, job_id):
        return (
            self.db.query(
                EvaluationApplyControl.job_id,
                EvaluationApplyControl.scope_id,
                EvaluationApplyControl.team_id,
                EvaluationApplyControl.performance_level,
                EvaluationApplyControl.position_name,
                EvaluationApplyControl.year,
                EvaluationApplyControl.month,
                EvaluationApplyControl.version_id,
                EvaluationApplyControl.claim_epoch,
            )
            .filter(EvaluationApplyControl.job_id == job_id)
            .one_or_none()
        )

    def _peek_open_control(self, scope_id, year: int, month: int):
        return (
            self.db.query(
                EvaluationApplyControl.job_id,
                EvaluationApplyControl.scope_id,
                EvaluationApplyControl.team_id,
                EvaluationApplyControl.performance_level,
                EvaluationApplyControl.position_name,
                EvaluationApplyControl.year,
                EvaluationApplyControl.month,
                EvaluationApplyControl.version_id,
                EvaluationApplyControl.claim_epoch,
            )
            .filter(
                EvaluationApplyControl.scope_id == scope_id,
                EvaluationApplyControl.year == int(year),
                EvaluationApplyControl.month == int(month),
                EvaluationApplyControl.state.in_(("pending", "staging", "promoting")),
            )
            .one_or_none()
        )

    def _lock_existing_header(self, peeked, team):
        """Job, then scope, then control. The team fence is already held."""
        job = self._lock_query(
            self.db.query(ProcessingJob).filter(ProcessingJob.id == peeked.job_id),
            True,
        ).one_or_none()
        scope = self._lock_query(
            self.db.query(EvaluationScope).filter(EvaluationScope.id == peeked.scope_id),
            True,
        ).one_or_none()
        control = self._lock_query(
            self.db.query(EvaluationApplyControl).filter(EvaluationApplyControl.job_id == peeked.job_id),
            True,
        ).one_or_none()
        if job is None or scope is None or control is None or job.kind != JOB_KIND_EVALUATION_APPLY:
            raise EvaluationError("Evaluation apply was not found.", code="not_found")
        self._revalidate_captured(peeked, job, scope, control, team)
        return job, control, scope

    def _lock_revision_graph(self, peeked, team, applied) -> None:
        """Manifest rollback locks job, scope, and control before the revision row."""
        if classify_snapshot(applied) != "manifest" or not isinstance(applied, dict):
            self._lock_scope_identity(peeked, team)
            return
        try:
            job_id = uuid.UUID(str(applied.get("job_id")))
        except (TypeError, ValueError, AttributeError):
            self._lock_scope_identity(peeked, team)
            return
        control_peek = self._peek_control(job_id)
        if control_peek is None or not _same_uuid(control_peek.team_id, team.id):
            self._lock_scope_identity(peeked, team)
            return
        self._lock_existing_header(control_peek, team)

    def _lock_scope_identity(self, peeked, team) -> None:
        scope = self._lock_query(
            self.db.query(EvaluationScope).filter(
                EvaluationScope.team_id == peeked.team_id,
                EvaluationScope.performance_level == peeked.performance_level,
                EvaluationScope.position_name == (peeked.position_name or ""),
            ),
            True,
        ).one_or_none()
        if scope is None or not _same_uuid(scope.team_id, team.id):
            raise EvaluationError("Evaluation scope was not found.", code="not_found")

    def _revalidate_captured(self, peeked, job, scope, control, team) -> None:
        if job.kind != JOB_KIND_EVALUATION_APPLY or not _same_uuid(job.id, control.job_id):
            raise EvaluationConflict("Captured scope identity no longer matches.", code="stale_preview")
        if not _same_uuid(scope.id, control.scope_id) or not _same_uuid(scope.team_id, control.team_id):
            raise EvaluationConflict("Captured scope identity no longer matches.", code="stale_preview")
        if not _same_uuid(team.id, control.team_id) or not _same_uuid(peeked.team_id, control.team_id):
            raise EvaluationConflict("Captured scope identity no longer matches.", code="stale_preview")
        if not _same_uuid(peeked.scope_id, control.scope_id) or not _same_uuid(peeked.job_id, control.job_id):
            raise EvaluationConflict("Captured scope identity no longer matches.", code="stale_preview")
        if scope.performance_level != control.performance_level or (scope.position_name or "") != (control.position_name or ""):
            raise EvaluationConflict("Captured scope identity no longer matches.", code="stale_preview")
        if peeked.performance_level != control.performance_level or (peeked.position_name or "") != (control.position_name or ""):
            raise EvaluationConflict("Captured scope identity no longer matches.", code="stale_preview")
        if int(peeked.year) != int(control.year) or int(peeked.month) != int(control.month):
            raise EvaluationConflict("Captured scope identity no longer matches.", code="stale_preview")
        if not _same_uuid(peeked.version_id, control.version_id) or int(peeked.claim_epoch) != int(control.claim_epoch):
            raise EvaluationConflict("Captured scope identity no longer matches.", code="stale_preview")

    def _revalidate_scope_peek(self, peeked, scope, team) -> None:
        if not _same_uuid(scope.id, peeked.id) or not _same_uuid(scope.team_id, peeked.team_id) or not _same_uuid(team.id, scope.team_id):
            raise EvaluationConflict("Captured scope identity no longer matches.", code="stale_preview")
        if scope.performance_level != peeked.performance_level or (scope.position_name or "") != (peeked.position_name or ""):
            raise EvaluationConflict("Captured scope identity no longer matches.", code="stale_preview")

    def _revalidate_revision_peek(self, peeked, revision, team) -> None:
        if not _same_uuid(revision.id, peeked.id) or not _same_uuid(revision.team_id, peeked.team_id) or not _same_uuid(team.id, revision.team_id):
            raise EvaluationConflict("Captured scope identity no longer matches.", code="stale_preview")
        if revision.performance_level != peeked.performance_level or (revision.position_name or "") != (peeked.position_name or ""):
            raise EvaluationConflict("Captured scope identity no longer matches.", code="stale_preview")
        if int(revision.year) != int(peeked.year) or int(revision.month) != int(peeked.month):
            raise EvaluationConflict("Captured scope identity no longer matches.", code="stale_preview")
        if not _same_uuid(revision.version_id, peeked.version_id):
            raise EvaluationConflict("Captured scope identity no longer matches.", code="stale_preview")

    def _require_source_proof(self, proof: dict, fingerprint: str, expected: int) -> None:
        if expected <= 0:
            raise EvaluationError(
                "This period has no stored results to recalculate. Apply is blocked until evidence exists.",
                code="insufficient_data",
            )
        if fingerprint != proof.get("source_fingerprint"):
            raise EvaluationConflict(
                "Impact preview is stale because stored evidence changed.",
                code="stale_preview",
            )
        if type(proof.get("affected_count")) is int and proof.get("affected_count") != expected:
            raise EvaluationConflict(
                "Impact preview is stale because stored evidence changed.",
                code="stale_preview",
            )

    def _bind_promoted_identity(self, revision, snapshot: dict) -> EvaluationApplyControl:
        """The manifest, control, scope, and revision are one captured promotion."""
        if classify_snapshot(snapshot) != "manifest":
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        try:
            job_id = uuid.UUID(str(snapshot.get("job_id")))
        except (TypeError, ValueError, AttributeError) as exc:
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest") from exc
        control = self.db.query(EvaluationApplyControl).filter(EvaluationApplyControl.job_id == job_id).one_or_none()
        if control is None or control.state != "promoted" or control.promoted_revision_id is None:
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        if not _same_uuid(control.promoted_revision_id, getattr(revision, "id", None)):
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        parents = (
            self.db.query(EvaluationApplyControl)
            .filter(EvaluationApplyControl.promoted_revision_id == control.promoted_revision_id)
            .all()
        )
        if len(parents) != 1 or not _same_uuid(parents[0].job_id, control.job_id):
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        if int(control.claim_epoch) != int(snapshot["claim_epoch"]):
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        if not _same_uuid(control.team_id, revision.team_id) or control.performance_level != revision.performance_level:
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        if (control.position_name or "") != (revision.position_name or ""):
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        if int(control.year) != int(revision.year) or int(control.month) != int(revision.month):
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        if not _same_uuid(control.version_id, revision.version_id):
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        scope = self.db.query(EvaluationScope).filter(EvaluationScope.id == control.scope_id).one_or_none()
        if scope is None or not _same_uuid(scope.id, control.scope_id) or not _same_uuid(scope.team_id, revision.team_id):
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        if scope.performance_level != revision.performance_level or (scope.position_name or "") != (revision.position_name or ""):
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")
        return control

    def _admit(self, scope, year: int, month: int) -> None:
        decision = self.catalog.decision_for(scope, year, month)
        if not decision.allows_ratio_edit:
            raise EvaluationError(
                decision.reason,
                code="unsupported_calculation",
                edit_mode="blocked",
                weight_only_allowed=False,
            )

    def _approved_version(self, scope, year: int, month: int, *, lock: bool):
        """One approved row, one team-file load, and one rules checksum for this batch."""
        query = self.db.query(TeamConfigurationVersion).filter(
            TeamConfigurationVersion.team_id == scope.team_id,
            TeamConfigurationVersion.performance_level == scope.performance_level,
            TeamConfigurationVersion.position_name == (scope.position_name or ""),
            TeamConfigurationVersion.effective_from_year == int(year),
            TeamConfigurationVersion.effective_from_month == int(month),
            TeamConfigurationVersion.status == "approved",
        )
        try:
            version = self._lock_query(query, lock).one_or_none()
        except Exception as exc:
            raise EvaluationConflict("Approved version identity is ambiguous.", code="stale_preview") from exc
        if version is None:
            raise EvaluationError("Approve this month before applying it.", code="not_approved")
        team = self.db.query(Team).filter(Team.id == scope.team_id).one()
        raw, resolved = self._configs_for_team(team, scope)
        require_approved_capability(
            version,
            team_name=logical_team_name(team),
            config=raw,
            year=int(year),
            month=int(month),
        )
        snapshot = version.config_snapshot if isinstance(version.config_snapshot, dict) else {}
        rules = _rules_checksum(snapshot)
        return version, resolved, rules

    def _configs_for_team(self, team: Team, scope):
        try:
            from config.loader import load_team_config, resolve_team_config

            raw = load_team_config(logical_team_name(team))
            resolved = resolve_team_config(raw, scope.performance_level, scope.position_name or None)
        except Exception:
            return None, None
        return raw, resolved

    def _proof_header(self, version, scope, rules: str) -> dict:
        snapshot = version.config_snapshot if isinstance(version.config_snapshot, dict) else {}
        proof = snapshot.get("preview_evidence")
        if not isinstance(proof, dict):
            raise EvaluationConflict(
                "An impact preview of the stored records is required before approval.",
                code="preview_required",
            )
        if proof.get("rules_checksum") != rules or version.config_checksum != rules:
            raise EvaluationConflict("Impact preview is stale because the rules changed.", code="stale_preview")
        if str(proof.get("scope_id") or "") != str(scope.id) or str(proof.get("team_id") or "") != str(scope.team_id or ""):
            raise EvaluationConflict("Impact preview is for a different scope.", code="stale_preview")
        if proof.get("performance_level") != scope.performance_level or (proof.get("position_name") or "") != (scope.position_name or ""):
            raise EvaluationConflict("Impact preview is for a different scope.", code="stale_preview")
        if int(proof.get("year") or 0) != int(version.effective_from_year) or int(proof.get("month") or 0) != int(version.effective_from_month):
            raise EvaluationConflict("Impact preview is for a different period.", code="stale_preview")
        if not _sha256_text(proof.get("source_fingerprint")):
            raise EvaluationConflict("Impact preview is stale because stored evidence changed.", code="stale_preview")
        return proof

    def _require_captured_version(self, control, version, rules: str) -> None:
        if version.id != control.version_id or version.status != "approved":
            raise EvaluationConflict("The approved version changed before this apply could finish.", code="stale_preview")
        if version.config_checksum != control.rules_checksum or rules != control.rules_checksum:
            raise EvaluationConflict("Approved rules changed before this apply could finish.", code="stale_preview")
        self._admit(self.db.query(EvaluationScope).filter(EvaluationScope.id == control.scope_id).one(), control.year, control.month)

    def _lineage_fingerprint(self, scope, year: int, month: int) -> str:
        rows = self._revision_rows(scope, year, month, lock=False)
        head = _chain_head(rows)
        ordered = []
        by_id = {row.id: row for row in rows}
        cursor = head
        seen = set()
        while cursor is not None:
            if cursor.id in seen:
                raise EvaluationConflict("Revision history contains a cycle.", code="invalid_revision_chain")
            seen.add(cursor.id)
            ordered.append(
                {
                    "id": str(cursor.id),
                    "status": cursor.status,
                    "version_id": str(cursor.version_id),
                    "previous_revision_id": None if cursor.previous_revision_id is None else str(cursor.previous_revision_id),
                }
            )
            cursor = None if cursor.previous_revision_id is None else by_id.get(cursor.previous_revision_id)
        return _checksum(ordered)

    def _revision_rows(self, scope, year: int, month: int, *, lock: bool):
        """Identity columns only. Snapshot JSON is not part of the lineage checksum."""
        query = self.db.query(
            EvaluationRevision.id,
            EvaluationRevision.status,
            EvaluationRevision.version_id,
            EvaluationRevision.previous_revision_id,
        ).filter(
            EvaluationRevision.team_id == scope.team_id,
            EvaluationRevision.performance_level == scope.performance_level,
            EvaluationRevision.position_name == (scope.position_name or ""),
            EvaluationRevision.year == int(year),
            EvaluationRevision.month == int(month),
        )
        rows = self._lock_query(query, lock).all()
        return [
            _RevisionView(row.id, row.status, row.version_id, row.previous_revision_id)
            for row in rows
        ]

    def _expected_count(self, job: ProcessingJob) -> int:
        body = job.request_json if isinstance(job.request_json, dict) else {}
        count = body.get("expected_count")
        if type(count) is not int or count < 0:
            raise EvaluationConflict("Evaluation apply header is incomplete.", code="invalid_state")
        return count

    def _page_start(self, control, cursor: str | None, replay: bool):
        stored = control.stage_cursor or ""
        if not replay:
            if cursor is not None and cursor != stored:
                raise EvaluationError("Stage cursor does not match the captured page.", code="invalid_cursor")
            return _decode_cursor(stored or None)
        return _decode_cursor(cursor)

    def _epoch(self, job, control, expected_epoch) -> None:
        if int(job.claim_epoch or 0) != int(control.claim_epoch):
            raise EvaluationConflict("The staged attempt is no longer current.", code="stale_epoch")
        if expected_epoch is not None and int(expected_epoch) != int(control.claim_epoch):
            raise EvaluationConflict("The staged attempt is no longer current.", code="stale_epoch")

    def _assert_month_text(self, record, month: int) -> None:
        if str(record.month).strip().casefold() != month_name(month).casefold():
            raise EvaluationError("A stored month label does not match the captured month.", code="invalid_evidence")

    def _revision(self, revision_id) -> EvaluationRevision:
        parsed = _uuid(revision_id, "Revision was not found.")
        revision = self.db.query(EvaluationRevision).filter(EvaluationRevision.id == parsed).one_or_none()
        if revision is None:
            raise EvaluationError("Revision was not found.", code="not_found")
        return revision

    def _locked_revision(self, revision_id) -> EvaluationRevision:
        parsed = _uuid(revision_id, "Revision was not found.")
        revision = self._lock_query(
            self.db.query(EvaluationRevision).filter(EvaluationRevision.id == parsed),
            True,
        ).one_or_none()
        if revision is None:
            raise EvaluationError("Revision was not found.", code="not_found")
        return revision

    def _scope_for_revision(self, revision) -> EvaluationScope:
        scope = (
            self.db.query(EvaluationScope)
            .filter(
                EvaluationScope.team_id == revision.team_id,
                EvaluationScope.performance_level == revision.performance_level,
                EvaluationScope.position_name == (revision.position_name or ""),
            )
            .one_or_none()
        )
        if scope is None:
            raise EvaluationError("Evaluation scope was not found.", code="not_found")
        return scope

    def _require_latest(self, revision: EvaluationRevision) -> None:
        if revision.status == "rolled_back":
            raise EvaluationError("A rolled-back revision stays rolled back.", code="immutable")
        scope = self._scope_for_revision(revision)
        revisions = self._revision_rows(scope, revision.year, revision.month, lock=True)
        active = [row for row in revisions if row.status == "active"]
        referenced = any(row.previous_revision_id == revision.id for row in revisions)
        head = _chain_head(revisions)
        if revision.status != "active" or referenced or len(active) != 1 or active[0].id != revision.id or head is None or head.id != revision.id:
            raise EvaluationConflict("An older revision cannot roll back a newer one.", code="not_latest")

    def _require_manifest_pair(self, revision: EvaluationRevision) -> None:
        if classify_snapshot(revision.applied_snapshot) != "manifest" or classify_snapshot(revision.prior_snapshot) != "manifest":
            raise EvaluationConflict("Stored revision manifest cannot be read.", code="invalid_manifest")

    def _capture_body(self, control, expected: int, *, resumed: bool) -> dict:
        return {
            "job_id": str(control.job_id),
            "state": control.state,
            "claim_epoch": int(control.claim_epoch),
            "expected_count": expected,
            "rules_checksum": control.rules_checksum,
            "source_fingerprint": control.proof_source_fingerprint,
            "engine_version": control.engine_version,
            "resumed": resumed,
        }

    def _lock_query(self, query, lock: bool):
        query = query.populate_existing()
        if lock and self._postgres():
            query = query.with_for_update()
        return query

    def _postgres(self) -> bool:
        bind = self.db.get_bind()
        return bind is not None and bind.dialect.name == "postgresql"

    def _release(self, records) -> None:
        for record in records:
            values = list(getattr(record, "kpi_values", []) or [])
            for value in values:
                if value in self.db:
                    self.db.expunge(value)
            employee = getattr(record, "employee", None)
            if employee is not None and employee in self.db:
                self.db.expunge(employee)
            if record in self.db:
                self.db.expunge(record)

    def _fault(self, name: str) -> None:
        if name not in FAULT_POINTS:
            return
        if self.db.info.get("bounded_apply_fault") == name:
            raise EvaluationConflict("Bounded apply stopped before commit.", code="fault_injected")


def snapshot_evidence_matches(db, records, snapshot, revision=None) -> bool:
    """Legacy snapshots keep the full-list comparison. A manifest is streamed from stage rows.

    A manifest match requires the revision that owns the promoted control.
    The same stage hash on a different parent is not evidence.
    """
    kind = classify_snapshot(snapshot)
    if kind == "legacy":
        return _evidence_matches(records, snapshot)
    if kind != "manifest" or revision is None:
        return False
    try:
        applied = revision.applied_snapshot if isinstance(getattr(revision, "applied_snapshot", None), dict) else {}
        prior = revision.prior_snapshot if isinstance(getattr(revision, "prior_snapshot", None), dict) else {}
        _require_manifest_agreement(applied, prior)
        if any(applied.get(key) != snapshot.get(key) for key in MANIFEST_FIELDS):
            return False
        service = BoundedApplyService(db)
        service._bind_promoted_identity(revision, snapshot)
        checked = service._verify_stage_manifest(snapshot, side="after")
        control = db.query(EvaluationApplyControl).filter(
            EvaluationApplyControl.job_id == uuid.UUID(str(checked["job_id"]))
        ).one()
        scope = db.query(EvaluationScope).filter(EvaluationScope.id == control.scope_id).one()
        cursor = None
        seen = 0
        while True:
            page = service._record_page(scope, control.year, control.month, cursor, DEFAULT_PAGE_SIZE, lock=False)
            if not page:
                break
            staged = {
                (row.record_id, int(row.record_year)): row
                for row in db.query(EvaluationApplyStageRow).filter(
                    EvaluationApplyStageRow.job_id == control.job_id,
                    EvaluationApplyStageRow.claim_epoch == control.claim_epoch,
                    EvaluationApplyStageRow.record_id.in_([record.id for record in page]),
                    EvaluationApplyStageRow.record_year == int(control.year),
                )
            }
            for record in page:
                stage = staged.get((record.id, int(record.year)))
                if stage is None:
                    return False
                current = _evidence_item(record)
                if canonical_row_hash(current) != stage.after_hash:
                    return False
                seen += 1
            cursor = (int(page[-1].year), page[-1].id)
            service._release(page)
            service._release(list(staged.values()))
        return seen == int(checked["record_count"])
    except EvaluationConflict:
        return False


class _RevisionView:
    """Lineage fields without prior_snapshot or applied_snapshot."""

    def __init__(self, row_id, status, version_id, previous_revision_id):
        self.id = row_id
        self.status = status
        self.version_id = version_id
        self.previous_revision_id = previous_revision_id


def _chain_head(revisions):
    if not revisions:
        return None
    by_id = {row.id: row for row in revisions}
    referenced = {row.previous_revision_id for row in revisions if row.previous_revision_id is not None}
    heads = [row for row in revisions if row.id not in referenced]
    if len(by_id) != len(revisions) or len(heads) != 1:
        raise EvaluationConflict("Revision history is not a single valid chain.", code="invalid_revision_chain")
    return heads[0]


def _same_uuid(left, right) -> bool:
    if left is None or right is None:
        return False
    return str(left).replace("-", "").lower() == str(right).replace("-", "").lower()


def _stage_key(record_id, year) -> tuple[str, int]:
    return str(record_id).replace("-", "").lower(), int(year)


def _uuid(value, message: str):
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise EvaluationError(message, code="not_found") from exc


def _canon_or_same(value) -> str | None:
    from services.evaluation.workflow import _canon_decimal

    return _canon_decimal(value)
