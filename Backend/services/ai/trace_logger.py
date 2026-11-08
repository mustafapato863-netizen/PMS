from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import re
import threading
import unicodedata
import uuid
from typing import Any

from sqlalchemy.orm import Session

from models.ai_schemas import AiDistillationRecord, SessionFilterContext
from models.models import AiConversation, AiInteractionTrace, AiTurn, Employee
from services.ai.config import get_ai_runtime_config, redact_secrets
from services.audit_service import AuditService

logger = logging.getLogger(__name__)

_PII_ID_RE = re.compile(
    r"\b(?:EMP[-_ ]?\d+|SGHD\d+|SGHA\d+|INB[-_]\w+|OUT[-_]\w+|SUP[-_]\w+|\d{5,8})\b",
    re.IGNORECASE,
)
_EMP_ROUTE_RE = re.compile(r"(/employee/)([^/?#\s]+)", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_RE = re.compile(
    r"(?:\+\d{1,3}[\s-]?)?(?:\(?\d{2,4}\)?[\s-])\d{3,4}[\s-]\d{4}\b|\b05\d[\s-]?\d{3}[\s-]?\d{4}\b"
)

_NON_NAME_DOMAIN_WORDS: frozenset[str] = frozenset(
    {
        "call",
        "center",
        "inbound",
        "outbound",
        "support",
        "positions",
        "position",
        "coding",
        "submission",
        "resubmission",
        "marketing",
        "pharmacy",
        "sales",
        "csr",
        "finance",
        "human",
        "resources",
        "dubai",
        "sharjah",
        "ajman",
        "clinics",
        "all",
        "uae",
        "egy",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "employee",
        "employees",
        "managerial",
        "corporate",
        "manager",
        "admin",
        "agent",
        "agents",
        "supervisor",
        "quality",
        "assurance",
        "training",
        "trainer",
        "workforce",
        "analyst",
        "analytics",
        "specialist",
        "social",
        "media",
        "buyer",
        "graphic",
        "designer",
        "account",
        "attendance",
        "booking",
        "bookings",
        "attended",
        "abandon",
        "abandoned",
        "reachability",
        "score",
        "scores",
        "scored",
        "scoring",
        "target",
        "targets",
        "trend",
        "trends",
        "best",
        "worst",
        "lowest",
        "highest",
        "peak",
        "weakest",
        "strongest",
        "month",
        "months",
        "period",
        "periods",
        "team",
        "teams",
        "branch",
        "branches",
        "rate",
        "overall",
        "weighted",
        "pms",
        "rank",
        "ranks",
        "ranking",
        "grade",
        "what",
        "which",
        "who",
        "where",
        "when",
        "how",
        "why",
        "was",
        "were",
        "is",
        "are",
        "did",
        "does",
        "had",
        "has",
        "have",
        "his",
        "her",
        "their",
        "the",
        "and",
        "for",
        "from",
        "with",
        "into",
        "over",
        "across",
        "show",
        "compare",
        "diagnose",
        "summary",
        "performance",
        "performer",
        "performers",
        "evaluation",
        "record",
        "records",
        "published",
        "available",
        "unavailable",
        "verified",
        "joiner",
        "join",
        "joined",
        "joining",
        "date",
        "history",
        "full",
        "note",
        "tied",
        "top",
        "bottom",
        "first",
        "last",
        "prior",
        "current",
        "kpi",
        "kpis",
        "metric",
        "metrics",
        "bsc",
        "scorecard",
        "yes",
        "no",
        "هل",
        "ما",
        "هو",
        "هي",
        "من",
        "في",
        "عن",
        "على",
        "الى",
        "إلى",
        "او",
        "أو",
        "فريق",
        "تيم",
        "شهر",
        "سبتمبر",
        "أغسطس",
        "اغسطس",
        "يوليو",
        "يونيو",
        "مايو",
        "أبريل",
        "ابريل",
        "مارس",
        "فبراير",
        "يناير",
        "أكتوبر",
        "اكتوبر",
        "نوفمبر",
        "ديسمبر",
        "دبي",
        "الشارقة",
        "عجمان",
        "عيادات",
        "أداء",
        "اداء",
        "تقييم",
        "نتيجة",
        "موظف",
        "الموظف",
        "الموظفة",
        "موظفة",
        "ايجنت",
        "أيجنت",
        "حجز",
        "حجوزات",
        "الحجوزات",
        "حضور",
        "الحضور",
        "مؤشر",
        "مؤشرات",
        "تارجت",
        "انباوند",
        "إنباوند",
        "اوتباوند",
        "أوتباوند",
        "كول",
        "سنتر",
        "الكول",
        "جديد",
        "جديدة",
        "أفضل",
        "افضل",
        "أسوأ",
        "اسوا",
        "أقل",
        "اقل",
        "أعلى",
        "اعلى",
    }
)

_ARABIC_PREFIXES = ("و", "ف", "ب", "ل", "ك")

_ENGINE_INIT_LOCK = threading.Lock()
_INITIALIZED_ENGINE_KEYS: set[str] = set()

PRIVILEGED_REVIEWER_ROLES: frozenset[str] = frozenset(
    {"Admin", "General Manager", "Performance Team"}
)


def _normalize_unicode_token(tok: str) -> str:
    """Normalize a Unicode word token (strips Latin accents and unifies Arabic Alef/Yeh/Teh-Marbuta)."""
    if not tok:
        return ""
    nfc = unicodedata.normalize("NFC", tok).strip().casefold()
    # Strip combining marks (accents/harakat) while preserving base letters
    decomposed = unicodedata.normalize("NFKD", nfc)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    # Normalize common Arabic orthographic variants
    stripped = (
        stripped.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ٱ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
        .replace("ؤ", "و")
        .replace("ئ", "ي")
    )
    return unicodedata.normalize("NFC", stripped)


def _is_alpha_unicode_token(tok: str) -> bool:
    if not tok:
        return False
    return all(ch.isalpha() or ch in ("-", "'", "’") for ch in tok) and any(ch.isalpha() for ch in tok)


def _min_name_token_len(tok: str) -> int:
    # Arabic/CJK/non-Latin names can be 2 characters (e.g., "مي", "طه"), Latin tokens >= 3 chars
    return 2 if any(ord(ch) > 127 for ch in tok) else 3


def _build_name_token_set(
    known_employee_names: list[str] | set[str] | tuple[str, ...] | None,
) -> set[str]:
    if not known_employee_names:
        return set()
    tokens: set[str] = set()
    for raw in known_employee_names:
        clean = unicodedata.normalize("NFC", str(raw or "")).strip()
        if not clean:
            continue
        for part in re.split(r"[\s\-/]+", clean):
            tok = part.strip(" ,.'\"’()[]{}؟،؛:!?").casefold()
            if tok.endswith("'s") or tok.endswith("’s"):
                tok = tok[:-2]
            if not _is_alpha_unicode_token(tok):
                continue
            if len(tok) < _min_name_token_len(tok):
                continue
            norm_tok = _normalize_unicode_token(tok)
            if tok in _NON_NAME_DOMAIN_WORDS or norm_tok in _NON_NAME_DOMAIN_WORDS:
                continue
            tokens.add(tok)
            if norm_tok and len(norm_tok) >= _min_name_token_len(norm_tok):
                tokens.add(norm_tok)
    return tokens


_UNICODE_WORD_TOKEN_RE = re.compile(
    r"(?<!\w)([^\W\d_]{2,}(?:['’\-][^\W\d_]{2,})?)(?:('s|’s))?(?!\w)",
    re.UNICODE,
)
_CONSECUTIVE_EMP_NAME_RE = re.compile(
    r"<EMPLOYEE_NAME>(?:[\s·\-]+<EMPLOYEE_NAME>)+('s|’s)?",
    re.UNICODE,
)
_AGENT_PILL_RE = re.compile(
    r"\b(Agent|Employee)\s*·\s*([^\n·()]+)",
    re.IGNORECASE | re.UNICODE,
)
_POSSESSIVE_PERSON_RE = re.compile(
    r"(?<!\w)([^\W\d_]{3,}(?:\s+[^\W\d_]{3,}){0,2})(?:'s|’s)\s+(?=score|performance|best|worst|lowest|highest|trend|month|position|record|history|kpi|evaluation|first\s+available)",
    re.IGNORECASE | re.UNICODE,
)
_ARABIC_PERSON_CONTEXT_RE = re.compile(
    r"(?:الموظف|الموظفة|موظف|موظفة|الايجنت|الأيجنت|ايجنت|أيجنت|أداء|اداء|تقييم|نتيجة)\s+([\u0600-\u06FF]{2,}(?:\s+[\u0600-\u06FF]{2,}){0,2})",
    re.UNICODE,
)


def _token_matches_name_set(word: str, token_set: set[str]) -> bool:
    if not word or not token_set:
        return False
    cf = word.casefold()
    norm = _normalize_unicode_token(cf)
    if cf in _NON_NAME_DOMAIN_WORDS or norm in _NON_NAME_DOMAIN_WORDS:
        return False
    if cf in token_set or norm in token_set:
        return True
    # Check hyphenated sub-parts
    if "-" in cf:
        parts = [p for p in cf.split("-") if p]
        if parts and any(_token_matches_name_set(p, token_set) for p in parts):
            return True
    # Check attached single-letter Arabic prefixes (e.g. لمريم, ومريم, بمريم)
    if len(cf) >= 4 and any("\u0600" <= ch <= "\u06FF" for ch in cf) and cf[0] in _ARABIC_PREFIXES:
        stem = cf[1:]
        stem_norm = _normalize_unicode_token(stem)
        if stem not in _NON_NAME_DOMAIN_WORDS and (stem in token_set or stem_norm in token_set):
            return True
    return False


def sanitize_prompt_for_router_training(
    prompt: str,
    *,
    known_employee_names: list[str] | set[str] | tuple[str, ...] | None = None,
    db: Session | None = None,
    run_syntactic_extraction: bool = True,
    _precomputed_tokens: set[str] | None = None,
) -> str:
    """Replace concrete employee IDs, emails, phones, keys, and Unicode employee names with canonical tokens."""
    cleaned = unicodedata.normalize("NFC", redact_secrets(prompt or ""))
    cleaned = _EMAIL_RE.sub("<EMAIL>", cleaned)
    cleaned = _PHONE_RE.sub("<PHONE>", cleaned)
    cleaned = _EMP_ROUTE_RE.sub(r"\1<EMPLOYEE_ID>", cleaned)
    cleaned = _PII_ID_RE.sub("<EMPLOYEE_ID>", cleaned)
    cleaned = _AGENT_PILL_RE.sub(r"\1 · <EMPLOYEE_NAME>", cleaned)

    if _precomputed_tokens is not None:
        token_set = set(_precomputed_tokens)
    else:
        eff_names = list(known_employee_names or [])
        if db is not None:
            try:
                eff_names = TrainingTraceLogger(db)._collect_known_employee_names(eff_names)
            except Exception:
                pass
        token_set = _build_name_token_set(eff_names)

    if run_syntactic_extraction:
        try:
            from services.ai.entity_resolver import extract_person_token_from_prompt

            extracted = extract_person_token_from_prompt(cleaned)
            if extracted:
                token_set.update(_build_name_token_set([extracted]))
        except Exception:
            pass

        # Extract possessive person names (e.g. "Adham's worst month", "Renée's score")
        for m_pos in _POSSESSIVE_PERSON_RE.finditer(cleaned):
            cand_phrase = m_pos.group(1)
            token_set.update(_build_name_token_set([cand_phrase]))

        # Extract Arabic person names following person/performance context markers
        for m_ar in _ARABIC_PERSON_CONTEXT_RE.finditer(cleaned):
            cand_ar = m_ar.group(1)
            token_set.update(_build_name_token_set([cand_ar]))

    if token_set:
        def _replace_word(match: re.Match[str]) -> str:
            base_word = match.group(1)
            possessive_suffix = match.group(2)
            if base_word in ("EMPLOYEE_NAME", "EMPLOYEE_ID", "EMAIL", "PHONE", "REDACTED"):
                return match.group(0)
            if _token_matches_name_set(base_word, token_set):
                return "<EMPLOYEE_NAME>'s" if possessive_suffix else "<EMPLOYEE_NAME>"
            return match.group(0)

        cleaned = _UNICODE_WORD_TOKEN_RE.sub(_replace_word, cleaned)
        cleaned = _CONSECUTIVE_EMP_NAME_RE.sub(
            lambda m: "<EMPLOYEE_NAME>'s" if m.group(1) else "<EMPLOYEE_NAME>",
            cleaned,
        )

    return cleaned.strip()


def redact_nested_payload(
    value: Any,
    *,
    known_employee_names: list[str] | None = None,
    _precomputed_tokens: set[str] | None = None,
) -> Any:
    """Recursively redact PII, Unicode employee names, and secrets from nested trace and export structures."""
    tokens = (
        set(_precomputed_tokens)
        if _precomputed_tokens is not None
        else _build_name_token_set(known_employee_names)
    )
    if isinstance(value, str):
        return sanitize_prompt_for_router_training(
            value,
            run_syntactic_extraction=True,
            _precomputed_tokens=tokens,
        )
    if isinstance(value, list):
        return [
            redact_nested_payload(item, _precomputed_tokens=tokens)
            for item in value
        ]
    if isinstance(value, dict):
        # First harvest any explicit employee name fields inside this dict into tokens
        for k_scan, v_scan in value.items():
            if str(k_scan).casefold() in (
                "employee_name",
                "agent_name",
                "last_subject_employee_name",
                "subject_employee_name",
                "person_name",
                "candidate_name",
                "employee",
            ) and isinstance(v_scan, str) and v_scan.strip():
                tokens.update(_build_name_token_set([v_scan]))

        redacted: dict[str, Any] = {}
        for k, v in value.items():
            key_lower = str(k).casefold()
            if key_lower in ("raw_data", "workbook_bytes", "api_key", "password", "token"):
                continue
            if key_lower in (
                "employee_id",
                "emp_id",
                "last_subject_employee_id",
                "subject_employee_id",
                "entity_id",
            ) and v:
                redacted[k] = "<EMPLOYEE_ID>"
            elif key_lower in (
                "employee_name",
                "agent_name",
                "last_subject_employee_name",
                "subject_employee_name",
                "person_name",
                "candidate_name",
                "employee",
            ) and v:
                redacted[k] = "<EMPLOYEE_NAME>"
            elif key_lower == "entity_name" and isinstance(v, str) and v.strip():
                if "trajectory" in v.casefold():
                    redacted[k] = sanitize_prompt_for_router_training(
                        v, run_syntactic_extraction=True, _precomputed_tokens=tokens
                    )
                else:
                    tokens.update(_build_name_token_set([v]))
                    redacted[k] = "<EMPLOYEE_NAME>"
            else:
                redacted[k] = redact_nested_payload(v, _precomputed_tokens=tokens)
        return redacted
    return value


def assess_pii_quarantine(
    sanitized_text: str,
    *,
    original_text: str | None = None,
    known_employee_names: list[str] | None = None,
    _precomputed_tokens: set[str] | None = None,
) -> tuple[bool, list[str]]:
    """Evaluate whether a sanitized string still carries residual PII or uncertain unredacted person references.

    Does not rely solely on a regex to prove text is PII-free: if person-oriented cues (joiner/tenure/pronoun/possessive
    or unknown non-domain proper/Unicode tokens) remain without a corresponding `<EMPLOYEE_NAME>` or `<EMPLOYEE_ID>` placeholder,
    quarantines the example for explicit Admin review.
    """
    reasons: list[str] = []
    text = unicodedata.normalize("NFC", sanitized_text or "")
    tokens = (
        set(_precomputed_tokens)
        if _precomputed_tokens is not None
        else _build_name_token_set(known_employee_names)
    )

    if _EMAIL_RE.search(text):
        reasons.append("residual_email")
    if _PHONE_RE.search(text):
        reasons.append("residual_phone")
    if _PII_ID_RE.search(text):
        reasons.append("residual_employee_id")

    # Check if any known employee name token survived sanitization
    for match in _UNICODE_WORD_TOKEN_RE.finditer(text):
        word = match.group(1)
        if word in ("EMPLOYEE_NAME", "EMPLOYEE_ID", "EMAIL", "PHONE", "REDACTED"):
            continue
        if _token_matches_name_set(word, tokens):
            reasons.append(f"residual_known_name:{word}")
            break

    # Heuristic quarantine for uncertain person-targeted queries that produced no redaction placeholder
    lower_orig = (original_text or text).casefold()
    has_redaction_token = "<EMPLOYEE_NAME>" in text or "<EMPLOYEE_ID>" in text
    person_specific_cue = bool(
        re.search(
            r"\b(?:new\s+joiner|joining\s+date|hire\s+date|when\s+did\s+\S+\s+join|is\s+\S+\s+a\s+new\s+joiner)\b",
            lower_orig,
        )
        or re.search(r"(?:هل\s+\S+.*موظف|تاريخ\s+تعيين|انضم\s+حديثا)", lower_orig)
    )
    if person_specific_cue and not has_redaction_token:
        reasons.append("uncertain_person_query_without_redaction_token")

    # Check for unknown non-domain Arabic words or multi-word capitalized names in person-query contexts
    if not has_redaction_token:
        for match in _UNICODE_WORD_TOKEN_RE.finditer(text):
            word = match.group(1)
            if word in ("EMPLOYEE_NAME", "EMPLOYEE_ID", "EMAIL", "PHONE", "REDACTED"):
                continue
            cf = word.casefold()
            norm = _normalize_unicode_token(cf)
            if any("\u0600" <= ch <= "\u06FF" for ch in word):
                stem = cf[1:] if (len(cf) >= 4 and cf[0] in _ARABIC_PREFIXES) else cf
                stem_norm = _normalize_unicode_token(stem)
                if (
                    cf not in _NON_NAME_DOMAIN_WORDS
                    and norm not in _NON_NAME_DOMAIN_WORDS
                    and stem not in _NON_NAME_DOMAIN_WORDS
                    and stem_norm not in _NON_NAME_DOMAIN_WORDS
                ):
                    reasons.append(f"uncertain_unrecognized_unicode_token:{word}")
                    break

    return (len(reasons) > 0), reasons


def ensure_trace_schema_once(db: Session) -> None:
    """Ensure AI tables exist once per database engine in local/test environments only.

    Request-time DDL is strictly prohibited in production and staging; Alembic migrations must establish the schema.
    """
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
        bind = db.get_bind()
        root_engine = getattr(bind, "engine", bind)
        engine_key = f"{id(root_engine)}:{getattr(root_engine, 'url', '')}"
        if engine_key in _INITIALIZED_ENGINE_KEYS:
            return
        with _ENGINE_INIT_LOCK:
            if engine_key in _INITIALIZED_ENGINE_KEYS:
                return
            AiConversation.__table__.create(bind=bind, checkfirst=True)
            AiTurn.__table__.create(bind=bind, checkfirst=True)
            AiInteractionTrace.__table__.create(bind=bind, checkfirst=True)
            _INITIALIZED_ENGINE_KEYS.add(engine_key)
    except Exception as exc:
        logger.debug("AI schema one-time check skipped: %s", exc)


class TraceOwnershipError(PermissionError):
    """Raised when a user attempts to modify feedback on another user's trace."""


class TrainingTraceLogger:
    """Persists AI turns with Unicode-safe redaction and curates Admin-verified anonymized training pairs."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def _collect_known_employee_names(self, extra_names: list[str] | None = None) -> list[str]:
        names: set[str] = set()
        if extra_names:
            for n in extra_names:
                if n and str(n).strip():
                    names.add(str(n).strip())
        try:
            emp_rows = self.db.query(Employee.name).limit(2000).all()
            for (fn,) in emp_rows:
                if fn and str(fn).strip():
                    names.add(str(fn).strip())
            from services.dashboard_record_service import DashboardRecordService

            for rec in DashboardRecordService(self.db).list_analysis_records() or []:
                emp_nm = getattr(rec, "employee_name", None)
                if emp_nm and str(emp_nm).strip():
                    names.add(str(emp_nm).strip())
        except Exception:
            try:
                self.db.rollback()
            except Exception:
                pass
        return sorted(names, key=len, reverse=True)

    def record_turn(
        self,
        *,
        user_id: str | None,
        role: str,
        prompt: str,
        session_state: SessionFilterContext,
        tool_calls: list[dict[str, Any]],
        tool_digest: dict[str, Any],
        structured_response: dict[str, Any],
        provider_name: str,
        model_name: str,
        latency_ms: int,
        non_empty_evidence: bool,
        guardrail_triggered: bool,
        known_employee_names: list[str] | None = None,
        turn_id: str | None = None,
    ) -> str:
        trace_uuid = uuid.uuid4()
        cfg = get_ai_runtime_config()
        all_names = self._collect_known_employee_names(known_employee_names)
        name_tokens = _build_name_token_set(all_names)

        # Also harvest any employee names inside tool_digest or structured_response before sanitizing prompt
        redact_nested_payload(tool_digest, _precomputed_tokens=name_tokens)
        redact_nested_payload(structured_response, _precomputed_tokens=name_tokens)

        sanitized = sanitize_prompt_for_router_training(
            prompt,
            known_employee_names=all_names,
            _precomputed_tokens=name_tokens,
        )
        is_quarantined, quarantine_reasons = assess_pii_quarantine(
            sanitized,
            original_text=prompt,
            _precomputed_tokens=name_tokens,
        )
        stored_prompt = sanitized if cfg.redact_raw_prompts else redact_secrets(prompt)
        redacted_session = redact_nested_payload(
            session_state.model_dump(), _precomputed_tokens=name_tokens
        )
        redacted_digest = redact_nested_payload(
            tool_digest, _precomputed_tokens=name_tokens
        )
        if isinstance(redacted_digest, dict) and is_quarantined:
            redacted_digest = dict(redacted_digest)
            redacted_digest["pii_quarantine"] = {
                "quarantined": True,
                "reasons": quarantine_reasons,
            }
        redacted_calls = redact_nested_payload(
            tool_calls, _precomputed_tokens=name_tokens
        )
        redacted_response = redact_nested_payload(
            structured_response, _precomputed_tokens=name_tokens
        )
        try:
            ensure_trace_schema_once(self.db)
            row = AiInteractionTrace(
                id=trace_uuid,
                turn_id=str(turn_id) if turn_id else None,
                user_id=str(user_id) if user_id else None,
                role=role or "Manager",
                prompt=stored_prompt,
                sanitized_prompt=sanitized,
                session_state=redacted_session,
                tool_calls=redacted_calls,
                tool_digest=redacted_digest,
                structured_response=redacted_response,
                provider_name=provider_name,
                model_name=model_name,
                latency_ms=max(0, int(latency_ms)),
                non_empty_evidence=bool(non_empty_evidence),
                guardrail_triggered=bool(guardrail_triggered),
                is_distillation_eligible=False,
                reviewer_verified=False,
            )
            self.db.add(row)
            self.db.commit()
        except Exception as exc:
            self.db.rollback()
            logger.warning("Failed to persist AI interaction trace: %s", redact_secrets(str(exc)))
        return str(trace_uuid)

    def record_feedback(
        self,
        *,
        trace_id: str,
        rating: str,
        category: str | None = None,
        reason: str | None = None,
        caller_user_id: str | None = None,
        caller_role: str | None = None,
        reviewer_verified: bool | None = None,
    ) -> tuple[bool, bool]:
        """Upsert user ✓/✕ feedback on an existing trace. Enforces trace ownership and never self-certifies non-Admin users."""
        try:
            ensure_trace_schema_once(self.db)
            parsed_id = uuid.UUID(str(trace_id))
        except (ValueError, TypeError):
            return False, False

        try:
            row = self.db.query(AiInteractionTrace).filter(AiInteractionTrace.id == parsed_id).first()
            if not row:
                return False, False

            owner_id = str(row.user_id or "").strip()
            caller_id = str(caller_user_id or "").strip()
            is_admin_reviewer = str(caller_role or "") == "Admin" and reviewer_verified is not None
            if owner_id and caller_id and owner_id != caller_id and not is_admin_reviewer:
                raise TraceOwnershipError("Cannot submit feedback for another user's interaction trace")
            if owner_id and not caller_id and not is_admin_reviewer and caller_role is not None:
                raise TraceOwnershipError("Cannot submit feedback for another user's interaction trace")

            all_names = self._collect_known_employee_names()
            row.feedback_rating = rating
            combined_reason = reason or ""
            if category and reason:
                combined_reason = f"[{category}] {reason}"
            elif category and not reason:
                combined_reason = f"[{category}]"
            row.feedback_reason = (
                sanitize_prompt_for_router_training(combined_reason, known_employee_names=all_names)
                if combined_reason
                else None
            )
            if category and isinstance(row.structured_response, dict):
                updated_resp = dict(row.structured_response)
                updated_resp["feedback_category"] = category
                row.structured_response = updated_resp
            row.is_distillation_eligible = bool(
                rating == "up" and row.non_empty_evidence and not row.guardrail_triggered
            )
            # New feedback changes the reviewable example. A prior review must not
            # automatically certify a later change to the rating or feedback.
            row.reviewer_verified = False
            row.reviewer_id = None
            row.reviewed_at = None
            if isinstance(row.structured_response, dict):
                updated_resp = dict(row.structured_response)
                updated_resp["reviewer_verified"] = False
                row.structured_response = updated_resp
            # Only an explicit Admin verification can certify this feedback.
            if is_admin_reviewer:
                row.reviewer_verified = bool(reviewer_verified)
                row.reviewer_id = caller_id or "admin"
                row.reviewed_at = datetime.now(timezone.utc)
                if isinstance(row.structured_response, dict):
                    updated_resp = dict(row.structured_response)
                    updated_resp["reviewer_verified"] = bool(reviewer_verified)
                    row.structured_response = updated_resp
            self.db.commit()
            return True, bool(row.is_distillation_eligible)
        except TraceOwnershipError:
            self.db.rollback()
            raise
        except Exception as exc:
            self.db.rollback()
            logger.warning("Failed to update feedback on trace %s: %s", trace_id, redact_secrets(str(exc)))
            return False, False

    def review_trace(
        self,
        *,
        trace_id: str,
        reviewer_verified: bool,
        reviewer_id: str,
        caller_role: str,
        notes: str | None = None,
    ) -> tuple[bool, bool, str]:
        """Admin-only trace verification for distillation curation."""
        if str(caller_role or "") != "Admin":
            raise PermissionError("Only Admin reviewers can verify AI traces for distillation.")
        try:
            ensure_trace_schema_once(self.db)
            parsed_id = uuid.UUID(str(trace_id))
        except (ValueError, TypeError):
            return False, False, ""

        try:
            row = self.db.query(AiInteractionTrace).filter(AiInteractionTrace.id == parsed_id).first()
            if not row:
                return False, False, ""
            now_dt = datetime.now(timezone.utc)
            all_names = self._collect_known_employee_names()
            row.reviewer_verified = bool(reviewer_verified)
            row.reviewer_id = str(reviewer_id or "admin")
            row.reviewed_at = now_dt
            if notes:
                row.feedback_reason = sanitize_prompt_for_router_training(
                    notes, known_employee_names=all_names
                )
            if isinstance(row.structured_response, dict):
                updated_resp = dict(row.structured_response)
                updated_resp["reviewer_verified"] = bool(reviewer_verified)
                row.structured_response = updated_resp
            self.db.commit()
            return True, bool(row.is_distillation_eligible and row.reviewer_verified), now_dt.isoformat()
        except Exception as exc:
            self.db.rollback()
            logger.warning("Failed to review trace %s: %s", trace_id, redact_secrets(str(exc)))
            return False, False, ""

    def export_distillation_dataset(
        self,
        *,
        verified_only: bool = True,
        limit: int = 500,
        performed_by_user_id: str | None = None,
        ip_address: str | None = None,
        request_id: str | None = None,
        known_employee_names: list[str] | None = None,
    ) -> list[AiDistillationRecord]:
        try:
            ensure_trace_schema_once(self.db)
            query = self.db.query(AiInteractionTrace)
            if verified_only:
                # Verified-only export MUST contain ONLY explicitly Admin-reviewed examples
                query = query.filter(
                    AiInteractionTrace.is_distillation_eligible.is_(True),
                    AiInteractionTrace.reviewer_verified.is_(True),
                )
            rows = query.order_by(AiInteractionTrace.created_at.desc()).limit(max(1, min(limit, 2000))).all()
        except Exception as exc:
            self.db.rollback()
            logger.warning("Failed to export distillation dataset: %s", redact_secrets(str(exc)))
            return []

        all_names = self._collect_known_employee_names(known_employee_names)
        base_tokens = _build_name_token_set(all_names)
        records: list[AiDistillationRecord] = []
        for r in rows:
            rev_verified = bool(getattr(r, "reviewer_verified", False))
            if verified_only and not rev_verified:
                continue

            row_tokens = set(base_tokens)
            # Harvest any employee names embedded inside legacy tool_digest or structured_response
            clean_digest = redact_nested_payload(r.tool_digest or {}, _precomputed_tokens=row_tokens)
            clean_session = redact_nested_payload(r.session_state or {}, _precomputed_tokens=row_tokens)
            if isinstance(clean_session, dict):
                clean_session.pop("employee_id", None)
                if isinstance(clean_session.get("last_confirmed_query"), dict):
                    clean_session["last_confirmed_query"].pop("last_subject_employee_id", None)
                    clean_session["last_confirmed_query"].pop("last_subject_employee_name", None)
            clean_calls = redact_nested_payload(r.tool_calls or [], _precomputed_tokens=row_tokens)
            clean_resp = redact_nested_payload(r.structured_response or {}, _precomputed_tokens=row_tokens)

            sanitized_prompt = sanitize_prompt_for_router_training(
                r.sanitized_prompt or r.prompt or "",
                _precomputed_tokens=row_tokens,
            )
            quarantined, q_reasons = assess_pii_quarantine(
                sanitized_prompt,
                original_text=r.prompt or r.sanitized_prompt or "",
                _precomputed_tokens=row_tokens,
            )
            # Always block any record that still contains a known residual PII token;
            # also quarantine uncertain unreviewed examples from unverified exports.
            has_hard_residual = any(
                reason.startswith("residual_") for reason in q_reasons
            )
            stored_quarantined = isinstance(r.tool_digest, dict) and bool(r.tool_digest.get("pii_quarantined"))
            if has_hard_residual or ((quarantined or stored_quarantined) and not rev_verified):
                continue

            router_pair = {
                "schema_version": "pms-ai-router-v1",
                "sanitized_prompt": sanitized_prompt,
                "session_filter_state": clean_session,
                "expected_tool_calls": clean_calls,
                "tool_digest": clean_digest,
            }
            narrative_pair = None
            if r.is_distillation_eligible and isinstance(clean_resp, dict):
                headline_redacted = sanitize_prompt_for_router_training(
                    str(clean_resp.get("headline") or ""),
                    _precomputed_tokens=row_tokens,
                )
                bullets_redacted = [
                    sanitize_prompt_for_router_training(str(b), _precomputed_tokens=row_tokens)
                    for b in (clean_resp.get("narrative_bullets") or [])
                ]
                citations_redacted = redact_nested_payload(
                    clean_resp.get("citations") or [],
                    _precomputed_tokens=row_tokens,
                )
                narrative_pair = {
                    "schema_version": "pms-ai-narrative-v1",
                    "headline": headline_redacted,
                    "narrative_bullets": bullets_redacted,
                    "citations": citations_redacted,
                }
            records.append(
                AiDistillationRecord(
                    trace_id=str(r.id),
                    created_at=r.created_at.isoformat() if r.created_at else "",
                    role=r.role,
                    router_training_pair=router_pair,
                    narrative_training_pair=narrative_pair,
                    provider_name=r.provider_name,
                    model_name=r.model_name,
                    reviewer_verified=rev_verified,
                )
            )

        # Audit the distillation export
        try:
            AuditService.log_operation(
                self.db,
                table_name="ai_interaction_traces",
                operation="EXPORT",
                record_id=str(uuid.uuid4()),
                old_values=None,
                new_values={
                    "verified_only": verified_only,
                    "limit": limit,
                    "exported_count": len(records),
                },
                performed_by_user_id=performed_by_user_id if performed_by_user_id else None,
                ip_address=ip_address,
                request_id=request_id,
            )
        except Exception as exc:
            logger.debug("Audit log for AI trace export skipped: %s", redact_secrets(str(exc)))

        return records
