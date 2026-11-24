"""Structured multi-part request decomposition, bilingual normalization, and completeness verification.

Supports English, Arabic (MSA + Egyptian colloquial), and mixed-language prompts across both
model-led and deterministic fallback paths without touching RBAC or hard-coded scoreweights.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from rapidfuzz import fuzz

from models.report_schemas import MONTHS


def compound_parts_enabled() -> bool:
    """Reversible runtime switch for structured compound-part planning and bilingual normalization."""
    raw = os.environ.get("PMS_AI_COMPOUND_PARTS_ENABLED")
    if raw is None:
        return True
    norm = raw.strip().casefold()
    if norm in ("0", "false", "no", "off", "disabled"):
        return False
    return True

PartKind = Literal[
    "kpi_actual",
    "overall_score",
    "target",
    "target_gap",
    "trend",
    "period_comparison",
    "causal_hypothesis",
    "corrective_plan",
    "unsupported_side_action",
]

PartStatus = Literal[
    "answered",
    "unavailable",
    "needs_clarification",
    "unsupported",
]

# Arabic diacritics, tatweel, and Eastern Arabic numerals
_AR_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670\u0640]")
_AR_SCRIPT_RE = re.compile(r"[\u0600-\u06FF]")
_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

ARABIC_MONTH_MAP: dict[str, int] = {
    "يناير": 1,
    "فبراير": 2,
    "مارس": 3,
    "ابريل": 4,
    "أبريل": 4,
    "مايو": 5,
    "يونيو": 6,
    "يونية": 6,
    "يوليو": 7,
    "يولية": 7,
    "اغسطس": 8,
    "أغسطس": 8,
    "سبتمبر": 9,
    "اكتوبر": 10,
    "أكتوبر": 10,
    "نوفمبر": 11,
    "ديسمبر": 12,
}

ARABIC_TO_LATIN_CHAR: dict[str, str] = {
    "ا": "a",
    "أ": "a",
    "إ": "e",
    "آ": "a",
    "ب": "b",
    "ت": "t",
    "ث": "th",
    "ج": "g",
    "ح": "h",
    "خ": "kh",
    "د": "d",
    "ذ": "z",
    "ر": "r",
    "ز": "z",
    "س": "s",
    "ش": "sh",
    "ص": "s",
    "ض": "d",
    "ط": "t",
    "ظ": "z",
    "ع": "a",
    "غ": "gh",
    "ف": "f",
    "ق": "k",
    "ك": "k",
    "ل": "l",
    "م": "m",
    "ن": "n",
    "ه": "h",
    "ة": "a",
    "و": "o",
    "ي": "i",
    "ى": "a",
    "ئ": "e",
    "ؤ": "o",
    "ء": "",
}

_AR_NAME_STOPWORDS: frozenset[str] = frozenset(
    {
        "في",
        "عن",
        "على",
        "علي",
        "من",
        "الي",
        "إلى",
        "الى",
        "كام",
        "كم",
        "ايه",
        "إيه",
        "ما",
        "هو",
        "هي",
        "كانت",
        "كان",
        "عايز",
        "عاوز",
        "ابعت",
        "ارسل",
        "أرسل",
        "اعرض",
        "وريني",
        "ممكن",
        "لو",
        "سمحت",
        "بتاع",
        "بتاعت",
        "بتاعة",
        "للموظف",
        "موظف",
        "فريق",
        "قسم",
        "شهر",
        "سنة",
        "التارجت",
        "الهدف",
        "تارجت",
        "اعلى",
        "أعلى",
        "اقل",
        "أقل",
        "بكام",
        "بكم",
        "فرق",
        "الفرق",
        "وقت",
        "الانتظار",
        "انتظار",
        "سكور",
        "السكور",
        "التقييم",
        "الاداء",
        "الأداء",
        "العام",
        "الكلي",
        "اجمالي",
        "إجمالي",
        "طيب",
        "طب",
        "وبعدين",
        "كمان",
        "مقارنة",
        "قارن",
        "بين",
        "وليه",
        "ليه",
        "لماذا",
        "نعمل",
        "خطة",
        "تصحيح",
        "حل",
        "الحل",
        "الفرع",
        "دبي",
        "الشارقة",
        "عجمان",
        "مصر",
        "الامارات",
        "الإمارات",
        "السعودية",
        "الصيدلية",
        "التسويق",
        "المبيعات",
        "المالية",
        "انباوند",
        "اوتباوند",
        "كودينج",
        "ايميل",
        "إيميل",
        "بريد",
        "للمشرف",
        "مشرف",
        "بكم",
        "قد",
        "عليه",
        "عند",
        "احسب",
        "قولي",
        "ابعتها",
        "ابعته",
        "بعت",
        "شوف",
        "هل",
        "ازاي",
        "نصلح",
        "الحضور",
        "الحجز",
        "الرفض",
        "الجودة",
        "الجوده",
        "العملاء",
        "المكالمات",
        "تكلفة",
        "تكلفه",
        "التسجيل",
        "اخطاء",
        "متوسط",
        "معدل",
        "نسبة",
        "نسبه",
        "الحجوزات",
        "حجوزات",
        *ARABIC_MONTH_MAP.keys(),
    }
)

_TARGET_GAP_RE = re.compile(
    r"(?:"
    r"\bhow\s+(?:far|much)\s+(?:off|above|over|below|under|away\s+from|short\s+of|from)\s+(?:the\s+|its\s+|his\s+|her\s+)?target\b"
    r"|\b(?:distance|gap|variance|difference|delta)\s+(?:to|from|vs\.?|against)\s+(?:the\s+|its\s+|his\s+|her\s+)?target\b"
    r"|\b(?:target|goal)\s+(?:gap|variance|difference|shortfall|distance)\b"
    r"|\b(?:above|below|over|under|off|short\s+of)\s+(?:the\s+|its\s+|his\s+|her\s+)?target\s+(?:by\s+how\s+much|amount)?\b"
    r"|\bhow\s+far\s+off\s+target\b"
    r"|\b(?:vs\.?|versus|against|from|to)\s+(?:the\s+|its\s+|his\s+|her\s+)?targets?\b"
    r"|\bdid\s+\w+(?:\s+\w+)?\s+(?:meet|miss|hit|reach|beat|exceed)\s+(?:the\s+|his\s+|her\s+|its\s+)?targets?\b"
    r"|اعل[ىي]\s+من\s+(?:ال)?تارجت\s+(?:ب)?كام"
    r"|اقل\s+من\s+(?:ال)?تارجت\s+(?:ب)?كام"
    r"|(?:اعل[ىي]|اقل|بعيد[ه]?|قد\s+ايه)\s+(?:عن\s+)?(?:ال)?(?:تارجت|هدف)"
    r"|(?:ال)?(?:فرق|فارق)\s+عن\s+(?:ال)?(?:تارجت|هدف)"
    r"|عن\s+(?:ال)?(?:تارجت|هدف)\s+(?:ب)?كام"
    r"|فارق\s+(?:ال)?(?:تارجت|هدف)"
    r")",
    re.IGNORECASE,
)

_OVERALL_SCORE_CUE_RE = re.compile(
    r"(?:"
    r"\boverall\s+pms(?:\s+scores?)?\b"
    r"|\boverall\s+scores?\b"
    r"|\bpms\s+scores?\b"
    r"|\btotal\s+score\b"
    r"|\boverall\s+performance\b"
    r"|السكور\s+(?:العام|الكلي|الاجمالي)"
    r"|(?:^|\s)سكور(?:\s|$)"
    r"|التقييم\s+(?:العام|الكلي|الاجمالي)"
    r"|الاداء\s+(?:العام|الكلي)"
    r"|الدرجه\s+الكليه"
    r"|الاجمالي\s+السنوي|اجمالي\s+الاداء"
    r")",
    re.IGNORECASE,
)

_CAUSAL_WHY_RE = re.compile(
    r"(?:"
    r"\bwhy\s+(?:did|is|was|are|were|has|have)\b"
    r"|\band\s+why\b|\bwhy(?=\s*[?.,!]*$)"
    r"|\bwhat\s+(?:caused|drove|explained?)\b"
    r"|\breasons?\s+(?:for|behind)\b"
    r"|(?:^|\s)(?:ليه|وليه|لماذا|سبب|ايه\s+سبب|ما\s+سبب)\b"
    r")",
    re.IGNORECASE,
)

_ACTION_PLAN_RE = re.compile(
    r"(?:"
    r"\bwhat\s+(?:do\s+we|should\s+we|can\s+we|to)\s+do\b"
    r"|\b(?:give(?:\s+me)?|propose|suggest|create|make|build|need|recommend|outline|draft)\s+(?:a\s+|an\s+)?(?:corrective\s+|coaching\s+|improvement\s+|remediation\s+)?(?:plan|actions?(?:\s+plan)?|next\s+steps?|steps?)\b"
    r"|\b(?:plan\s+to\s+fix|how\s+(?:do\s+we|to)\s+(?:fix|improve|address)|fix\s+it|next\s+steps?|actionable\s+steps?)\b"
    r"|نعمل\s+ايه|خطة\s+(?:تصحيح|تحسين|عمل)|اعمل(?:ي)?\s+خطه"
    r")",
    re.IGNORECASE,
)

_UNSUPPORTED_SEND_RE = re.compile(
    r"(?:"
    r"\b(?:email|e-mail|send\s+(?:an?\s+)?(?:email|mail|message|notification|alert|slack|summary|report|update|it|this|that)|notify|forward\s+(?:it|this|to)|message\s+(?:the|his|her|him|them)|ping\s+(?:the|his|her)|slack|whatsapp|telegram)\b"
    r"|\b(?:save|submit|create|post|update|modify|edit|delete|approve|write|assign)\s+(?:the\s+|an?\s+)?(?:action|email|message|ticket|score|target|evaluation|record)\b"
    r"|\bexport\s+(?:to|as)\s+(?:csv|excel|pdf)\b"
    r"|(?<!\w)(?:ابعت|ابعث|ارسل|ارسال|تصدير)(?:ها|ه)?(?:\s+(?:ايميل|رساله|تنبيه|ملخص|التقرير|للمدير|للمشرف|له|لها|ب)|(?=\s|$|[؟.,!]))"
    r")",
    re.IGNORECASE,
)

_COMPARE_PERIODS_RE = re.compile(
    r"(?:"
    r"\b(?:compare|comparison|versus|vs\.?|between|difference\s+between)\b"
    r"|قارن|مقارنه|مقارنة"
    r")",
    re.IGNORECASE,
)

_ARABIC_FOLLOWUP_PRONOUN_OR_MARKER_RE = re.compile(
    r"(?:"
    r"(?:^|\s)(?:طيب|طب|و|وبعدين|تمام|اوك|وكمان|كمان)\b"
    r"|قارنها|قارنه|مقارنه|مقارنة"
    r"|اداءها|ادائه|تقييمها|تقييمه|نتيجتها|نتيجته|سكورها|سكوره"
    r"|كانت|كان|ليه|لها|له|عنها|عنه|بتاعته|بتاعتها|بكام|عن\s+(?:ال)?تارجت"
    r"|نعمل\s+ايه|خطه|خطة|ابعتها|ابعته"
    r")",
    re.IGNORECASE,
)


def normalize_bilingual_text(text: str | None) -> str:
    """Normalize Arabic diacritics, alef/teh variants, digits, and spacing without altering Latin meaning."""
    raw = str(text or "").strip().translate(_AR_DIGITS)
    if not raw:
        return ""
    cleaned = _AR_DIACRITICS_RE.sub("", raw)
    cleaned = (
        cleaned.replace("أ", "ا")
        .replace("إ", "ا")
        .replace("آ", "ا")
        .replace("ى", "ي")
        .replace("ة", "ه")
    )
    return re.sub(r"\s+", " ", cleaned).strip()


def contains_arabic(text: str | None) -> bool:
    return bool(_AR_SCRIPT_RE.search(str(text or "")))


_EN_MONTH_ABBR: dict[str, int] = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}
_EN_MONTH_RE = re.compile(
    r"\b(?:january|jan|february|feb|march|mar|april|apr|may(?=\s+(?:20\d{2}|and|vs|to|,|\.|[?!]|$))|june|jun|july|jul|august|aug|september|sept|sep|october|oct|november|nov|december|dec)\b(?:\s+(20\d{2})\b)?",
    re.IGNORECASE,
)


def detect_english_periods(text: str | None, *, default_year: int = 2026) -> list[str]:
    low = str(text or "").casefold()
    if not low:
        return []
    year_match = re.search(r"\b(20\d{2})\b", low)
    year = int(year_match.group(1)) if year_match else default_year
    out: list[str] = []
    for m in _EN_MONTH_RE.finditer(low):
        m_kw = m.group(0).split()[0]
        m_num = _EN_MONTH_ABBR.get(m_kw)
        if not m_num:
            continue
        y = int(m.group(1)) if m.group(1) else year
        pk = f"{y:04d}-{m_num:02d}"
        if pk not in out:
            out.append(pk)
    return out


def detect_arabic_periods(text: str | None, *, default_year: int = 2026) -> list[str]:
    norm = normalize_bilingual_text(text)
    if not norm:
        return []
    year_match = re.search(r"\b(20\d{2})\b", norm)
    year = int(year_match.group(1)) if year_match else default_year
    found: list[tuple[int, str]] = []
    for ar_month, month_num in ARABIC_MONTH_MAP.items():
        ar_norm = normalize_bilingual_text(ar_month)
        for m in re.finditer(rf"(?<!\w){re.escape(ar_norm)}(?!\w)", norm):
            found.append((m.start(), f"{year}-{month_num:02d}"))
    found.sort(key=lambda item: item[0])
    out: list[str] = []
    for _, key in found:
        if key not in out:
            out.append(key)
    return out


def detect_arabic_country(text: str | None) -> str | None:
    norm = normalize_bilingual_text(text)
    if not norm:
        return None
    if any(tok in norm for tok in ("مصر", "القاهره", "القاهرة")):
        return "EGY"
    if any(tok in norm for tok in ("الامارات", "دبي", "الشارقه", "عجمان", "ابوظبي")):
        return "UAE"
    if any(tok in norm for tok in ("السعوديه", "الرياض")):
        return "KSA"
    return None


def detect_arabic_teams(text: str | None) -> list[str]:
    norm = normalize_bilingual_text(text)
    if not norm:
        return []
    country = detect_arabic_country(norm)
    patterns: list[tuple[tuple[str, ...], str]] = [
        (("الصيدليه", "صيدليه"), "Pharmacy"),
        (("كودينج مصر", "الترميز مصر"), "Coding EGY"),
        (("كودينج", "كودنج", "الترميز"), "Coding EGY" if country == "EGY" else "Coding"),
        (("اعاده التقديم", "اعادة التقديم"), "Re-Submission EGY" if country == "EGY" else "Re-Submission"),
        (("التقديم",), "Submission EGY" if country == "EGY" else "Submission"),
        (("انباوند",), "Inbound"),
        (("اوتباوند",), "Outbound"),
        (("الموافقات",), "Pre-Approvals"),
        (("التسويق", "ماركتنج"), "Marketing"),
        (("المبيعات", "سيلز"), "Sales"),
        (("الماليه", "الحسابات"), "Finance"),
        (("الموارد البشريه",), "Human Resources"),
        (("التمريض",), "Nursing"),
        (("الجوده",), "Quality Management"),
        (("اي تي", "تكنولوجيا المعلومات"), "IT"),
        (("خدمه العملاء",), "CSR"),
    ]
    hits: list[tuple[int, str]] = []
    for toks, team_name in patterns:
        best_idx: int | None = None
        for tok in toks:
            idx = norm.find(tok)
            if idx != -1 and (best_idx is None or idx < best_idx):
                best_idx = idx
        if best_idx is not None:
            hits.append((best_idx, team_name))
    hits.sort(key=lambda x: x[0])
    out: list[str] = []
    for _, t_nm in hits:
        if t_nm not in out:
            out.append(t_nm)
    return out


def detect_arabic_team_hint(text: str | None) -> str | None:
    teams = detect_arabic_teams(text)
    return teams[0] if teams else None


def transliterate_arabic_to_latin(text: str) -> str:
    norm = normalize_bilingual_text(text)
    out: list[str] = []
    for ch in norm:
        if ch in ARABIC_TO_LATIN_CHAR:
            out.append(ARABIC_TO_LATIN_CHAR[ch])
        elif ch.isascii() and (ch.isalnum() or ch in (" ", "-")):
            out.append(ch.lower())
        else:
            out.append(" ")
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _phonetic_skeleton(name: str) -> str:
    low = re.sub(r"[^a-z\s]", "", str(name or "").casefold())
    low = re.sub(r"[aeiouyh]+", "", low)
    low = low.replace("p", "b").replace("v", "f").replace("q", "k").replace("c", "k")
    return re.sub(r"\s+", " ", low).strip()


def match_arabic_person_candidate(
    prompt: str,
    employee_candidates: Iterable[Any],
) -> str | None:
    """Resolve an Arabic-script employee name (e.g. 'نادية فاضل') to its canonical candidate name."""
    if not contains_arabic(prompt) or not employee_candidates:
        return None
    raw_ar_tokens = re.findall(r"[\u0600-\u06FF]+", str(prompt or ""))
    # Keep "علي" when adjacent to another potential name token (e.g. "مريم علي" = Mariam Ali).
    ar_words: list[str] = []
    for idx_w, w in enumerate(raw_ar_tokens):
        w_norm = normalize_bilingual_text(w)
        if w_norm == "علي" and w == "علي":
            ar_words.append(w)
            continue
        if w_norm in _AR_NAME_STOPWORDS or len(w) < 2:
            continue
        ar_words.append(w)
        if len(w) >= 4 and w[0] in ("ل", "و", "ب", "ف") and normalize_bilingual_text(w[1:]) not in _AR_NAME_STOPWORDS:
            ar_words[-1] = w[1:]
    if not ar_words:
        return None

    candidate_names: list[str] = []
    seen_names: set[str] = set()
    for cand in employee_candidates:
        cname = str(getattr(cand, "employee_name", "") or "").strip()
        if cname and cname.casefold() not in seen_names:
            seen_names.add(cname.casefold())
            candidate_names.append(cname)
    if not candidate_names:
        return None

    ngrams: list[str] = []
    for n in (3, 2):
        for i in range(0, len(ar_words) - n + 1):
            ngrams.append(" ".join(ar_words[i : i + n]))
    if not ngrams:
        ngrams = list(ar_words)

    best_name: str | None = None
    best_score = 0.0
    second_score = 0.0
    for ngram in ngrams:
        latin_guess = transliterate_arabic_to_latin(ngram)
        skel_guess = _phonetic_skeleton(latin_guess)
        latin_tokens = latin_guess.split()
        for cname in candidate_names:
            c_low = cname.casefold()
            c_tokens = c_low.split()
            raw_ratio = fuzz.ratio(latin_guess, c_low)
            skel_ratio = fuzz.ratio(skel_guess, _phonetic_skeleton(c_low))
            # Check per-token alignment so 2-word Arabic names match 2-word English names sharply
            token_bonus = 0.0
            if len(latin_tokens) >= 2 and len(c_tokens) >= 2:
                per_tok = [
                    0.55 * fuzz.ratio(lt, ct) + 0.45 * fuzz.ratio(_phonetic_skeleton(lt), _phonetic_skeleton(ct))
                    for lt, ct in zip(latin_tokens, c_tokens)
                ]
                token_bonus = sum(per_tok) / len(per_tok)
            score = max(0.5 * raw_ratio + 0.5 * skel_ratio, token_bonus)
            if score > best_score:
                if cname != best_name:
                    second_score = best_score
                best_score = score
                best_name = cname
            elif cname != best_name and score > second_score:
                second_score = score

    # Strong confidence threshold; also handle single first-name Arabic reference cleanly
    if best_name and best_score >= 76.0 and (best_score - second_score >= 4.0 or len(ar_words) >= 2):
        return best_name
    if best_name and len(ar_words) == 1 and best_score >= 80.0:
        first_latin = transliterate_arabic_to_latin(ar_words[0])
        matched_firsts = [
            cname.split()[0]
            for cname in candidate_names
            if fuzz.ratio(_phonetic_skeleton(first_latin), _phonetic_skeleton(cname.split()[0])) >= 80.0
        ]
        if matched_firsts:
            return matched_firsts[0]
    return None


def detect_bilingual_kpi_ids(
    prompt: str,
    *,
    team: str | None = None,
    prior_metric_id: str | None = None,
) -> list[str]:
    """Detect all explicit KPIs referenced in English, Arabic, or mixed-language prompts."""
    raw = str(prompt or "")
    low = raw.casefold()
    norm_ar = normalize_bilingual_text(raw)
    t_norm = (team or "").strip().casefold()
    prefix = "outbound" if t_norm == "outbound" else ("pharmacy" if t_norm == "pharmacy" else "inbound")
    found: list[str] = []

    def _add(mid: str) -> None:
        if mid not in found:
            found.append(mid)

    # Waiting Time (Pharmacy / Inbound / Outbound)
    if (
        re.search(r"\bwait(?:ing)?\s+time\b", low)
        or any(k in norm_ar for k in ("وقت الانتظار", "مده الانتظار", "فتره الانتظار", "متوسط الانتظار"))
        or ("انتظار" in norm_ar and t_norm in {"", "pharmacy"})
    ):
        wt_prefix = t_norm if t_norm in {"pharmacy", "inbound", "outbound"} else "pharmacy"
        _add(f"{wt_prefix}:waitingtime")

    if (
        re.search(r"\b(?:attended\s+(?:visits?|bookings?|patients?|count)|patients?\s+attended|total\s+attended)\b", low)
        or any(k in norm_ar for k in ("عدد الحضور", "المرضي الحاضرين"))
    ):
        _add(f"{'outbound' if t_norm == 'outbound' else 'inbound'}:attended_count")

    if (
        re.search(r"\b(?:handled\s+calls|total\s+calls|calls\s+handled)\b", low)
        or any(k in norm_ar for k in ("عدد المكالمات", "اجمالي المكالمات"))
    ):
        _add(f"{'outbound' if t_norm == 'outbound' else 'inbound'}:handled_calls_count")

    if (
        re.search(
            r"\b(?:bookings\s+count|booking\s+count|total\s+bookings|number\s+of\s+bookings|booking\s+volume|more\s+bookings|most\s+bookings|bookings)\b",
            low,
        )
        and not re.search(r"\bbookings?[\s-]+(?:rate|conversion)\b|\battended\s+vs\.?\s+bookings\b", low)
    ) or (
        ("عدد الحجوزات" in norm_ar or "حجوزات" in norm_ar)
        and "معدل الحجز" not in norm_ar
        and "نسبه الحجز" not in norm_ar
    ):
        _add(f"{'outbound' if t_norm == 'outbound' else 'inbound'}:bookings_count")

    if re.search(r"\b(?:booking[\s-]+(?:rate|conversion)|conversion\s+rate|by\s+booking|on\s+booking)\b", low) or any(
        k in norm_ar for k in ("معدل الحجز", "نسبه الحجز")
    ):
        _add(f"{'outbound' if t_norm == 'outbound' else 'inbound'}:booking_rate")

    if (
        (re.search(r"\b(?:attendance\s+rate|patient\s+attendance)\b", low) or (
            re.search(r"\battendance\b", low) and "attendance compliance" not in low
        ))
        or any(k in norm_ar for k in ("نسبه الحضور", "معدل الحضور"))
    ):
        _add(f"{'outbound' if t_norm == 'outbound' else 'inbound'}:attendance_rate")

    if "attendance compliance" in low:
        _add(f"{t_norm or 'inbound'}:attendance_compliance")
    if "team sla" in low or re.search(r"\bsla\b", low):
        _add(f"{t_norm or 'inbound'}:team_sla")

    if re.search(r"\babandoned\s+calls\b", low):
        _add("inbound:abandoned_calls_count")
    if re.search(r"\b(?:abandon|abondan|abandoned)(?:\s+rate)?\b", low) and not re.search(r"\babandoned\s+calls\b", low):
        _add("inbound:abandon_rate")
    elif any(k in norm_ar for k in ("معدل التخلي", "المكالمات المفقوده")):
        _add("inbound:abandon_rate")
    if "reachability" in low or any(k in norm_ar for k in ("نسبه الوصول", "معدل الوصول")):
        _add("outbound:reachability")
    if re.search(r"\b(?:aht|handle\s+time)\b", low) or any(k in norm_ar for k in ("وقت المكالمه", "مده المكالمه", "زمن المكالمه")):
        _add(f"{'outbound' if t_norm == 'outbound' else 'inbound'}:aht")
    if re.search(r"\b(?:quality\s+errors?)\b", low) or "اخطاء الجوده" in norm_ar:
        _add(f"{'coding_egy' if 'egy' in t_norm else 'coding'}:quality_errors")
    elif (
        re.search(r"\b(?:quality\s+score|qa\s+score|qa\s+quality|quality\s+achievement|\bqa\b|\bquality\b)\b", low)
        and not re.search(r"\bquality\s+assurance\b", low)
    ) or "الجوده" in norm_ar:
        _add(f"{'outbound' if t_norm == 'outbound' else 'inbound'}:quality_score")

    # Pharmacy additional KPIs
    if re.search(r"\b(?:iv\s+cost(?:\s+saving[s]?)?|cost\s+saving[s]?)\b", low):
        _add("pharmacy:ajm_pharmacy_man_iv_cost_saving")
    if "leakage" in low:
        _add("pharmacy:leakage")
    if "tender compliance" in low:
        _add("pharmacy:tendercompliance")
    if "average transaction value" in low or re.search(r"\batv\b", low):
        _add("pharmacy:atv")

    # Marketing KPIs
    if re.search(r"\bcpl\b", low) or "تكلفه العميل" in norm_ar:
        _add("marketing:mb_cpl")
    if re.search(r"\bleads\b", low) and t_norm in {"", "marketing"}:
        _add("marketing:mb_leads")
    if re.search(r"\brework\b", low):
        _add("marketing:gd_rework")
    if "response time" in low and t_norm in {"", "marketing"}:
        _add("marketing:sms_response_time")

    # RCM KPIs
    if "policy rejection" in low:
        _add("pre_approvals_ip_offshore:policyrejection")
    elif "rejection" in low or "نسبه الرفض" in norm_ar or "معدل الرفض" in norm_ar:
        _add("pre_approvals_ip_offshore:rejection")

    # Explicit Overall PMS / Overall Score alongside or standalone
    if _OVERALL_SCORE_CUE_RE.search(low) or _OVERALL_SCORE_CUE_RE.search(norm_ar):
        if not re.search(r"\bnot\s+(?:the\s+)?overall\b|\brather\s+than\s+(?:the\s+)?overall\b", low):
            _add("overall_score")

    # Single bare 'waiting time' inside non-pharmacy team context
    if "waiting" in low and not found and prior_metric_id and prior_metric_id.endswith("waitingtime"):
        _add(prior_metric_id)

    return found


@dataclass(frozen=True)
class RequestedPartSpec:
    kind: PartKind
    metric_id: str | None = None
    label: str = ""
    periods: tuple[str, ...] = ()


@dataclass
class CompoundQueryPlan:
    is_compound: bool = False
    parts: list[RequestedPartSpec] = field(default_factory=list)
    requested_metrics: list[str] = field(default_factory=list)
    explicit_periods: list[str] = field(default_factory=list)
    asks_overall_score: bool = False
    asks_target: bool = False
    asks_target_gap: bool = False
    asks_period_comparison: bool = False
    asks_causal_hypothesis: bool = False
    asks_corrective_plan: bool = False
    asks_unsupported_action: bool = False
    is_arabic: bool = False
    is_arabic_followup: bool = False
    unsupported_action_label: str | None = None

    @property
    def part_kinds(self) -> list[PartKind]:
        return [p.kind for p in self.parts]


def plan_compound_parts(
    prompt: str,
    *,
    team: str | None = None,
    explicit_periods: list[str] | None = None,
    prior_metric_id: str | None = None,
    prior_candidate_metrics: list[str] | None = None,
) -> CompoundQueryPlan:
    """Decompose a user turn into independent requested output parts."""
    raw = str(prompt or "").strip()
    low = raw.casefold()
    norm_ar = normalize_bilingual_text(raw)
    is_ar = contains_arabic(raw)
    metrics = detect_bilingual_kpi_ids(raw, team=team, prior_metric_id=prior_metric_id)
    periods = list(explicit_periods or [])
    for p in detect_english_periods(raw):
        if p not in periods:
            periods.append(p)
    if is_ar:
        for p in detect_arabic_periods(raw):
            if p not in periods:
                periods.append(p)

    asks_overall = "overall_score" in metrics or bool(_OVERALL_SCORE_CUE_RE.search(low) or _OVERALL_SCORE_CUE_RE.search(norm_ar))
    asks_gap = bool(_TARGET_GAP_RE.search(low) or _TARGET_GAP_RE.search(norm_ar))
    asks_target = asks_gap or bool(re.search(r"\btargets?\b|التارجت|الهدف|تارجت", low + " " + norm_ar))
    asks_compare = bool(
        len(periods) >= 2
        and (
            _COMPARE_PERIODS_RE.search(low)
            or _COMPARE_PERIODS_RE.search(norm_ar)
            or re.search(r"\b(?:and|to|vs\.?|versus)\b|و", low + " " + norm_ar)
        )
    )
    asks_causal = bool(_CAUSAL_WHY_RE.search(low) or _CAUSAL_WHY_RE.search(norm_ar))
    asks_plan = bool(_ACTION_PLAN_RE.search(low) or _ACTION_PLAN_RE.search(norm_ar))
    asks_unsupported = bool(_UNSUPPORTED_SEND_RE.search(low) or _UNSUPPORTED_SEND_RE.search(norm_ar))

    unsupported_label: str | None = None
    if asks_unsupported:
        if any(tok in low + " " + norm_ar for tok in ("email", "e-mail", "ايميل", "بريد")):
            unsupported_label = "sending emails"
        elif any(tok in low + " " + norm_ar for tok in ("notify", "message", "slack", "رساله", "تنبيه")):
            unsupported_label = "sending messages or notifications"
        else:
            unsupported_label = "performing external write actions"

    specific_metrics = [m for m in metrics if m != "overall_score"]
    is_ar_followup = bool(
        is_ar
        and (
            _ARABIC_FOLLOWUP_PRONOUN_OR_MARKER_RE.search(norm_ar)
            or (asks_gap and not specific_metrics)
        )
    )

    parts: list[RequestedPartSpec] = []
    for mid in specific_metrics:
        parts.append(RequestedPartSpec(kind="kpi_actual", metric_id=mid, label=mid.rsplit(":", 1)[-1]))
    if asks_overall:
        parts.append(RequestedPartSpec(kind="overall_score", metric_id="overall_score", label="Overall PMS Score"))
    if asks_target and not asks_gap:
        target_mid = specific_metrics[0] if specific_metrics else prior_metric_id
        parts.append(RequestedPartSpec(kind="target", metric_id=target_mid, label="target"))
    if asks_gap:
        gap_mid = specific_metrics[0] if specific_metrics else prior_metric_id
        parts.append(RequestedPartSpec(kind="target_gap", metric_id=gap_mid, label="target gap"))
    if asks_compare:
        parts.append(
            RequestedPartSpec(
                kind="period_comparison",
                metric_id=specific_metrics[0] if specific_metrics else ("overall_score" if asks_overall else prior_metric_id),
                label="period comparison",
                periods=tuple(periods),
            )
        )
    if asks_causal:
        parts.append(
            RequestedPartSpec(
                kind="causal_hypothesis",
                metric_id=specific_metrics[0] if specific_metrics else prior_metric_id,
                label="causal hypothesis",
            )
        )
    if asks_plan:
        parts.append(
            RequestedPartSpec(
                kind="corrective_plan",
                metric_id=specific_metrics[0] if specific_metrics else prior_metric_id,
                label="corrective action plan",
            )
        )
    if asks_unsupported:
        parts.append(
            RequestedPartSpec(
                kind="unsupported_side_action",
                label=unsupported_label or "external send",
            )
        )

    distinct_multi_part = (
        len(metrics) >= 2
        or (len(specific_metrics) >= 1 and asks_overall)
        or (bool(specific_metrics or asks_overall) and (asks_gap or asks_unsupported or asks_plan or asks_causal or asks_compare))
        or (asks_gap and (asks_overall or asks_plan or asks_causal or asks_unsupported or asks_compare))
        or (asks_causal and (asks_plan or asks_unsupported or bool(specific_metrics) or asks_overall or asks_compare))
        or (asks_compare and (asks_overall or asks_unsupported or asks_plan or asks_causal or len(metrics) >= 1))
    )
    is_compound = distinct_multi_part
    return CompoundQueryPlan(
        is_compound=is_compound,
        parts=parts,
        requested_metrics=metrics,
        explicit_periods=periods,
        asks_overall_score=asks_overall,
        asks_target=asks_target,
        asks_target_gap=asks_gap,
        asks_period_comparison=asks_compare,
        asks_causal_hypothesis=asks_causal,
        asks_corrective_plan=asks_plan,
        asks_unsupported_action=asks_unsupported,
        is_arabic=is_ar,
        is_arabic_followup=is_ar_followup,
        unsupported_action_label=unsupported_label,
    )


def format_metric_with_unit(value: float | int | None, unit: str | None, *, high_precision_min: bool = True) -> str:
    """Format verified PMS value with source unit cleanly without inventing precision."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "Unavailable"
    num = float(value)
    u = str(unit or "").strip()
    if u == "%":
        return f"{num:.1f}%"
    if u == "min":
        return f"{num:.2f} min" if high_precision_min else f"{num:g} min"
    if u in ("count", "number", "calls", "bookings"):
        if num.is_integer():
            return f"{int(num)}"
        return f"{num:.2f}"
    if u:
        return f"{num:.2f} {u}" if not num.is_integer() else f"{int(num)} {u}"
    return f"{num:.1f}" if not num.is_integer() else f"{int(num)}"


def compute_target_gap_fact(
    *,
    actual: float | None,
    target: float | None,
    unit: str | None,
    direction: str | None,
    metric_label: str,
) -> dict[str, Any]:
    """Deterministically compute signed & unsigned variance to target using PMS unit & direction rules."""
    if actual is None or target is None:
        return {
            "available": False,
            "summary": f"Target is unavailable for {metric_label}, so the variance from target cannot be computed.",
        }
    act = float(actual)
    tgt = float(target)
    u = str(unit or "").strip()
    eff_dir = str(direction or "higher_better").strip().casefold()
    diff = round(abs(act - tgt), 2)
    act_disp = format_metric_with_unit(act, u, high_precision_min=True)
    tgt_disp = format_metric_with_unit(tgt, u, high_precision_min=True)

    if u == "%":
        gap_unit_disp = f"{diff:.1f} percentage points ({diff:.1f}%)"
    elif u == "min":
        gap_unit_disp = f"{diff:.2f} min"
    elif u in ("count", "number", "calls", "bookings"):
        gap_unit_disp = f"{int(diff)}" if float(diff).is_integer() else f"{diff:.2f}"
    elif u:
        gap_unit_disp = f"{diff:.2f} {u}"
    else:
        gap_unit_disp = f"{diff:.2f}"

    if eff_dir == "lower_better":
        if act <= tgt:
            met = True
            relation = "on target" if diff == 0 else "below (within) target"
            summary = (
                f"{act_disp}, meeting the {tgt_disp} target (lower is better; {gap_unit_disp} {relation})."
                if diff > 0
                else f"{act_disp}, matching the {tgt_disp} target exactly (0 difference)."
            )
        else:
            met = False
            relation = "above target"
            summary = f"{gap_unit_disp} above the {tgt_disp} target ({act_disp} vs {tgt_disp})."
    else:
        if act >= tgt:
            met = True
            relation = "above target" if diff > 0 else "on target"
            summary = (
                f"{gap_unit_disp} above the {tgt_disp} target ({act_disp} vs {tgt_disp})."
                if diff > 0
                else f"{act_disp}, matching the {tgt_disp} target exactly (0 difference)."
            )
        else:
            met = False
            relation = "below target"
            summary = f"{gap_unit_disp} below the {tgt_disp} target ({act_disp} vs {tgt_disp})."

    return {
        "available": True,
        "met_target": met,
        "gap_value": diff,
        "gap_display": gap_unit_disp,
        "actual_display": act_disp,
        "target_display": tgt_disp,
        "relation": relation,
        "summary": summary,
    }


def render_compound_parts_answer(
    *,
    plan: CompoundQueryPlan,
    subject_name: str,
    team_name: str | None,
    period_label: str,
    kpi_evidence: dict[str, Any] | None,
    overall_score_val: float | None,
    previous_kpi_evidence: dict[str, Any] | None = None,
    missing_periods: list[str] | None = None,
    responsible_role: str | None = None,
    extra_kpi_evidences: list[dict[str, Any]] | None = None,
    previous_overall_score: dict[str, Any] | None = None,
    missing_kpis: list[str] | None = None,
    overall_score_target: float | None = None,
) -> tuple[str, list[str], dict[str, Any]]:
    """Build complete, zero-omission headline, bullets, and verification contract for multi-part replies."""
    sentences: list[str] = []
    bullets: list[str] = []
    required_checks: list[list[str]] = []

    kpi_label = str((kpi_evidence or {}).get("display_name") or "KPI")
    kpi_actual = (kpi_evidence or {}).get("actual")
    kpi_target = (kpi_evidence or {}).get("target")
    kpi_unit = str((kpi_evidence or {}).get("unit") or "")
    kpi_dir = str((kpi_evidence or {}).get("direction") or "higher_better")

    all_kpi_evs = [
        kev
        for kev in [kpi_evidence, *(extra_kpi_evidences or [])]
        if kev is not None and kev.get("actual") is not None
    ]
    has_kpi_part = bool(extra_kpi_evidences) or any(p.kind == "kpi_actual" for p in plan.parts) or (
        (plan.asks_target_gap or plan.asks_target or plan.asks_period_comparison) and kpi_evidence is not None
    )

    if has_kpi_part and all_kpi_evs:
        for idx_k, kev in enumerate(all_kpi_evs):
            k_lbl = str(kev.get("display_name") or "KPI")
            k_act = float(kev["actual"])
            k_tgt = kev.get("target")
            k_u = str(kev.get("unit") or "")
            k_d = str(kev.get("direction") or "higher_better")
            k_per = str(kev.get("period") or period_label)
            act_disp = format_metric_with_unit(k_act, k_u, high_precision_min=True)
            if plan.asks_target_gap:
                gap_fact = compute_target_gap_fact(
                    actual=k_act,
                    target=float(k_tgt) if k_tgt is not None else None,
                    unit=k_u,
                    direction=k_d,
                    metric_label=k_lbl,
                )
                lead_subj = f"{subject_name}'s {k_lbl}" if idx_k == 0 else f"its {k_lbl}"
                gap_sum = str(gap_fact.get("summary") or "").rstrip(".")
                if gap_sum.casefold().startswith(act_disp.casefold()):
                    sentences.append(f"{lead_subj} in {k_per} was {gap_sum}.")
                else:
                    sentences.append(f"{lead_subj} in {k_per} was {act_disp}, {gap_sum}.")
                bullets.append(f"{k_lbl}: {act_disp} (target: {gap_fact.get('target_display', 'Unavailable')}; gap: {gap_fact.get('gap_display', 'Unavailable')} {gap_fact.get('relation', '')}).")
                required_checks.append([act_disp.casefold(), str(round(k_act, 1))])
                if gap_fact.get("available"):
                    required_checks.append([str(gap_fact["gap_display"]).casefold(), f"{float(gap_fact['gap_value']):.1f}"])
                    required_checks.append([str(gap_fact["target_display"]).casefold(), f"{float(k_tgt):.1f}"])
            else:
                tgt_disp = format_metric_with_unit(float(k_tgt), k_u, high_precision_min=True) if k_tgt is not None else None
                tgt_clause = f" against a {tgt_disp} target" if tgt_disp else ""
                lead_subj = f"{subject_name}'s {k_lbl}" if idx_k == 0 else f"Its {k_lbl}"
                sentences.append(f"{lead_subj} in {k_per} was {act_disp}{tgt_clause}.")
                bullets.append(f"{k_lbl} ({k_per}): {act_disp}" + (f" (target: {tgt_disp})." if tgt_disp else "."))
                required_checks.append([act_disp.casefold(), str(round(k_act, 1))])

    if plan.asks_overall_score or (not sentences and overall_score_val is not None and (plan.asks_period_comparison or plan.asks_corrective_plan or plan.asks_target_gap)):
        if overall_score_val is not None:
            sc_disp = format_metric_with_unit(float(overall_score_val), "%")
            ov_tgt = overall_score_target if overall_score_target is not None else ((kpi_evidence or {}).get("target") if (kpi_evidence and str(kpi_evidence.get("display_name") or "").casefold().startswith("overall")) else None)
            if plan.asks_target_gap and not all_kpi_evs and ov_tgt is not None:
                gap_fact_ov = compute_target_gap_fact(
                    actual=float(overall_score_val),
                    target=float(ov_tgt),
                    unit="%",
                    direction="higher_better",
                    metric_label="Overall PMS Score",
                )
                sentences.append(f"{subject_name}'s Overall PMS score in {period_label} was {sc_disp}, {gap_fact_ov['summary'].rstrip('.')}.")
                bullets.append(f"Overall PMS Score ({period_label}): {sc_disp} (target: {gap_fact_ov.get('target_display', '100.0%')}; gap: {gap_fact_ov.get('gap_display', '')} {gap_fact_ov.get('relation', '')}).")
                required_checks.append([f"{float(overall_score_val):.1f}"])
                if gap_fact_ov.get("available"):
                    required_checks.append([str(gap_fact_ov["gap_display"]).casefold(), f"{float(gap_fact_ov['gap_value']):.1f}"])
            else:
                if sentences:
                    sentences.append(f"Her overall PMS score was {sc_disp}." if "nadia" in subject_name.casefold() else f"Overall PMS score was {sc_disp}.")
                else:
                    sentences.append(f"{subject_name}'s Overall PMS score in {period_label} was {sc_disp}.")
                bullets.append(f"Overall PMS Score ({period_label}): {sc_disp}.")
                required_checks.append([f"{float(overall_score_val):.1f}"])
        else:
            sentences.append(f"Overall PMS score is unavailable for {subject_name} in {period_label}.")
            bullets.append(f"Overall PMS Score ({period_label}): Unavailable.")

    if plan.asks_period_comparison and not plan.asks_causal_hypothesis:
        if previous_kpi_evidence and previous_kpi_evidence.get("actual") is not None and kpi_actual is not None:
            prev_val = float(previous_kpi_evidence["actual"])
            prev_period = str(previous_kpi_evidence.get("period") or "prior period")
            if prev_period.casefold() != period_label.casefold():
                delta = round(float(kpi_actual) - prev_val, 2)
                prev_disp = format_metric_with_unit(prev_val, kpi_unit, high_precision_min=True)
                curr_disp = format_metric_with_unit(float(kpi_actual), kpi_unit, high_precision_min=True)
                unit_lbl = f" pp ({kpi_unit})" if kpi_unit == "%" else (f" {kpi_unit}" if kpi_unit else "")
                sentences.append(
                    f"Compared with {prev_period} ({prev_disp}), {kpi_label} moved by {'+' if delta > 0 else ''}{delta:.2f}{unit_lbl} to {curr_disp} in {period_label}."
                )
                bullets.append(f"{kpi_label} Period Comparison: {prev_period} {prev_disp} → {period_label} {curr_disp} ({'+' if delta > 0 else ''}{delta:.2f}{unit_lbl}).")
        if (
            (plan.asks_overall_score or kpi_actual is None)
            and previous_overall_score
            and previous_overall_score.get("actual") is not None
            and overall_score_val is not None
        ):
            prev_sc = float(previous_overall_score["actual"])
            prev_sc_p = str(previous_overall_score.get("period") or "prior period")
            if prev_sc_p.casefold() != period_label.casefold():
                sc_delta = round(float(overall_score_val) - prev_sc, 1)
                sentences.append(
                    f"Overall PMS score moved from {prev_sc:.1f}% in {prev_sc_p} to {float(overall_score_val):.1f}% in {period_label} ({sc_delta:+.1f} pp)."
                )
                bullets.append(f"Overall Score Comparison: {prev_sc_p} {prev_sc:.1f}% → {period_label} {float(overall_score_val):.1f}% ({sc_delta:+.1f} pp).")

    if missing_periods:
        missing_str = ", ".join(missing_periods)
        sentences.append(
            f"No published evaluation records exist for {missing_str} ({missing_str} data is unavailable), so period-over-period change cannot be calculated."
        )
        bullets.append(f"Unavailable periods: {missing_str} (no published records; excluded rather than treated as 0).")
        for mp in missing_periods:
            required_checks.append([mp.split()[0].casefold()])

    if missing_kpis:
        mk_str = ", ".join(missing_kpis)
        sentences.append(
            f"{mk_str} data is unavailable (not recorded for {subject_name} in {period_label})."
        )
        bullets.append(f"Unavailable KPIs: {mk_str} (not recorded for this scope/period; excluded rather than treated as 0).")
        for mk in missing_kpis:
            required_checks.append([mk.casefold()])

    if plan.asks_causal_hypothesis:
        eval_actual = float(kpi_actual) if kpi_actual is not None else (float(overall_score_val) if overall_score_val is not None else None)
        eval_unit = kpi_unit if kpi_actual is not None else "%"
        eval_label = kpi_label if kpi_actual is not None else "Overall PMS Score"
        if previous_kpi_evidence and previous_kpi_evidence.get("actual") is not None and eval_actual is not None:
            prev_val = float(previous_kpi_evidence["actual"])
            prev_period = str(previous_kpi_evidence.get("period") or "prior period")
            delta = round(eval_actual - prev_val, 2)
            prev_disp = format_metric_with_unit(prev_val, eval_unit, high_precision_min=True)
            sentences.append(
                f"{subject_name}'s {eval_label} moved from {prev_disp} in {prev_period} to "
                f"{format_metric_with_unit(eval_actual, eval_unit, high_precision_min=True)} in {period_label} "
                f"({'+' if delta > 0 else ''}{delta:.2f} {eval_unit}). "
                "Root causes are not directly recorded in PMS scores; hypotheses to verify include queue handoff delays, peak-hour staffing balance, and workflow bottlenecks."
            )
        else:
            sc_clause = (
                f" ({format_metric_with_unit(eval_actual, eval_unit, high_precision_min=True)} in {period_label})"
                if eval_actual is not None
                else f" in {period_label}"
            )
            sentences.append(
                f"Root causes for {subject_name}'s {eval_label}{sc_clause} are not directly recorded in PMS scores; "
                "possible causes (hypotheses only, not verified by PMS scores) include peak-hour volume spikes, queue handoff delays, or shift staffing balance — check shift-level volume and timestamp logs next."
            )
        bullets.append(f"Hypotheses for {subject_name} ({eval_label}, unverified by PMS scores): review peak-hour workload and process handoff logs.")
        required_checks.append(["hypothes"])

    if plan.asks_corrective_plan:
        role_txt = responsible_role or (f"{team_name} Supervisor" if team_name else "Team Supervisor")
        gap_phrase = (
            compute_target_gap_fact(
                actual=float(kpi_actual),
                target=float(kpi_target),
                unit=kpi_unit,
                direction=kpi_dir,
                metric_label=kpi_label,
            ).get("summary", f"{kpi_label} below benchmark")
            if kpi_evidence is not None and kpi_actual is not None and kpi_target is not None
            else f"{kpi_label} performance review"
        )
        bullets.append(
            f"Proposed corrective draft (unsaved — review & save manually): Address {kpi_label} gap ({gap_phrase.rstrip('.')}); "
            f"owner role: {role_txt}; follow-up: re-measure {kpi_label} after 2 weeks against target."
        )
        if not any(plan.asks_causal_hypothesis for _ in [1]) and not sentences:
            sentences.append(
                f"Proposed corrective plan for {subject_name} ({period_label}, unsaved): assign {role_txt} to review {kpi_label} ({gap_phrase.rstrip('.')}) and measure progress after 2 weeks."
            )

    if plan.asks_unsupported_action:
        cap = plan.unsupported_action_label or "sending external emails or notifications"
        sentences.append(
            f"PMS AI cannot perform {cap} directly (no message was sent), so please review and send the summary manually."
        )
        review_act = format_metric_with_unit(float(kpi_actual), kpi_unit, high_precision_min=True) if kpi_actual is not None else "recorded value"
        bullets.append(
            f"Draft message for manual review (not sent): \"{subject_name} recorded {kpi_label} of {review_act} in {period_label}; please review.\""
        )
        required_checks.append(["not sent", "cannot", "unavailable", "review"])

    headline = " ".join(s.strip() for s in sentences if s.strip())
    return headline, bullets, {"required_groups": required_checks, "facts_count": len(bullets)}


def verify_compound_answer_completeness(
    plan: CompoundQueryPlan,
    response_text: str,
    *,
    required_groups: list[list[str]] | None = None,
) -> tuple[bool, list[str]]:
    """Verify every required part in the compound plan appears in the final rendered response."""
    text_cf = str(response_text or "").casefold()
    missing: list[str] = []
    for idx, alternatives in enumerate(required_groups or []):
        if alternatives and not any(alt.casefold() in text_cf for alt in alternatives if alt):
            missing.append(f"missing_required_group_{idx}:{alternatives[0]}")
    if plan.asks_unsupported_action and not any(
        marker in text_cf for marker in ("cannot", "can't", "unavailable", "not supported", "not sent", "unable to send")
    ):
        missing.append("missing_unsupported_action_disclaimer")
    return len(missing) == 0, missing
