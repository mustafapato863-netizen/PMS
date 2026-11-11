"""Auditable evidence for PMS AI catalog claims.

A passing state is only ``verified`` or ``verified_no_data``, and only when
the reference names tests, a fixture or source version, a review date, and a
reviewer. An empty or pending reviewer is not a pass. Callers must publish
through ``publish_evidence`` so a bare ``verified`` flag cannot leak.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

EVIDENCE_STATES = frozenset({"verified", "verified_no_data", "partial", "blocked", "not_applicable"})
PASSING_EVIDENCE_STATES = frozenset({"verified", "verified_no_data"})
_PENDING_REVIEWERS = frozenset({"", "pending", "unknown", "none", "n/a", "na", "tbd", "unreviewed"})
_REVIEW_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class CatalogEvidence:
    state: str = "blocked"
    tests: tuple[str, ...] = ()
    fixture_or_source_version: str = ""
    reviewed_on: str = ""
    reviewer: str = "pending"


def evidence_passes(evidence: CatalogEvidence) -> bool:
    """Return True only for a complete, reviewed passing state."""
    state = str(evidence.state or "").strip()
    if state not in PASSING_EVIDENCE_STATES:
        return False
    tests = tuple(str(item).strip() for item in evidence.tests)
    if not tests or any(not item for item in tests):
        return False
    if not str(evidence.fixture_or_source_version or "").strip():
        return False
    if _REVIEW_DATE.match(str(evidence.reviewed_on or "").strip()) is None:
        return False
    reviewer = str(evidence.reviewer or "").strip().casefold()
    if reviewer in _PENDING_REVIEWERS:
        return False
    return True


def publish_evidence(evidence: CatalogEvidence) -> tuple[str, bool]:
    """Return the state a caller may show, and whether it counts as a pass.

    A passing label with missing evidence is reported as ``blocked``.
    """
    state = str(evidence.state or "").strip()
    if state not in EVIDENCE_STATES:
        state = "blocked"
    passes = evidence_passes(evidence)
    if state in PASSING_EVIDENCE_STATES and not passes:
        return "blocked", False
    if state not in PASSING_EVIDENCE_STATES:
        return state, False
    return state, True


def evidence_dict(evidence: CatalogEvidence) -> dict[str, object]:
    return {
        "tests": list(evidence.tests),
        "fixture_or_source_version": evidence.fixture_or_source_version,
        "reviewed_on": evidence.reviewed_on,
        "reviewer": evidence.reviewer if str(evidence.reviewer or "").strip() else "pending",
    }
