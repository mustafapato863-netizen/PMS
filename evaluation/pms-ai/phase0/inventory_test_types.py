#!/usr/bin/env python3
"""Plan Phase 1.5 test-type inventory for the Phase 0 set and the AI tests it relates to.

Labels are only: synthetic, mocked, live-model, source-parity, browser.
A file may carry more than one label. This script does not import the assistant
and does not run the tests.

Rules, applied to file text:
- browser: imports Playwright. Vitest and Testing Library are not browser tests.
- live-model: the file skips a test unless PMS_AI_RUN_LIVE_MODEL_TESTS=true.
  A function named test_live_ that does not use that switch is not a live model.
- source-parity: the file does not import services.ai, and it checks a
  deterministic non-AI result against checked-in team config, schema, or a
  golden reference. A mocked model compared with rules is not source-parity.
- mocked: the file stubs the model, HTTP, or AI orchestrator (MagicMock,
  monkeypatch of an AI symbol, vi.mock, vi.fn, or DeterministicLocalProviderAdapter).
- synthetic: none of the above. In-memory shapes and fixtures only.

Evidence status uses the roadmap words. A green file is not "verified".
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PHASE0 = Path(__file__).resolve().parent
LABELS = ("synthetic", "mocked", "live-model", "source-parity", "browser")

GLOBS = (
    "Backend/tests/test_ai_*.py",
    "Backend/tests/test_pms_ai_phase0_*.py",
    "Backend/tests/test_local_*.py",
    "Backend/tests/test_evaluation_outbound_productivity_golden.py",
    "Backend/tests/test_evaluation_provenance.py",
    "Frontend/src/components/ai/**/*.test.tsx",
    "Frontend/src/pages/PmsAiWorkspaceView.test.tsx",
    "Frontend/src/components/settings/shell/AiFeatureSwitch.test.tsx",
)

RUNNERS = (
    "evaluation/pms-ai/phase0/run_rules_only_baseline.py",
)

ABSENT_OWNER_PATHS = (
    {
        "path": "Frontend/tests/pms-ai.spec.ts",
        "claimed_in": "docs/plans/pms-ai-evidence-first/PHASE_1_BASELINE.md section 4",
        "evidence_status": "not applicable",
        "note": "The path is not in this tree. It is not a browser test.",
    },
    {
        "path": "Frontend/src/features/pmsAi/__tests__/",
        "claimed_in": "docs/plans/pms-ai-evidence-first/PHASE_1_BASELINE.md section 4",
        "evidence_status": "not applicable",
        "note": "The directory is not in this tree. It is not a browser test.",
    },
)


def _rel(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def discover() -> list[Path]:
    found: list[Path] = []
    for pattern in GLOBS:
        found.extend(ROOT.glob(pattern))
    unique = sorted({path.resolve() for path in found if path.is_file()}, key=_rel)
    if not unique:
        raise SystemExit("test-type inventory found no files")
    return unique


def classify(path: Path, text: str) -> list[str]:
    rel = _rel(path)
    labels: list[str] = []
    if re.search(r"@playwright/test|from ['\"]playwright", text) or "/e2e/" in rel:
        labels.append("browser")
    if "PMS_AI_RUN_LIVE_MODEL_TESTS" in text:
        labels.append("live-model")
    imports_assistant = bool(
        re.search(r"(?m)^(?:from|import) services\.ai\b", text)
    )
    if not imports_assistant and (
        "golden" in path.name or "derive_expected" in text or path.name == "test_pms_ai_phase0_derivation.py"
    ):
        labels.append("source-parity")
    stubs_model = any(
        token in text
        for token in (
            "MagicMock",
            "unittest.mock",
            "DeterministicLocalProviderAdapter",
            "vi.mock",
            "vi.fn",
        )
    )
    patches_ai = "monkeypatch.setattr" in text and imports_assistant
    if stubs_model or patches_ai:
        labels.append("mocked")
    if not labels:
        labels.append("synthetic")
    unknown = [label for label in labels if label not in LABELS]
    if unknown:
        raise SystemExit(f"unknown label {unknown} for {rel}")
    return labels


def evidence_status(labels: list[str], kind: str) -> str:
    if kind == "runner":
        return "not applicable"
    if "live-model" in labels and labels == ["live-model"]:
        return "blocked"
    if "source-parity" in labels:
        return "partial"
    if "mocked" in labels or "live-model" in labels:
        return "partial" if "mocked" in labels else "blocked"
    if "browser" in labels:
        return "partial"
    return "not applicable"


def _cases(path: Path, text: str) -> int:
    if path.suffix == ".py":
        return len(re.findall(r"^def test_", text, re.M))
    return len(re.findall(r"\bit(?:\.[a-zA-Z]+)?\(", text))


def _entry(path: Path, kind: str) -> dict:
    text = _read(path)
    labels = classify(path, text) if kind == "test" else ["synthetic"]
    rel = _rel(path)
    note = ""
    if "live-model" in labels:
        note = "The live-model test is skipped unless PMS_AI_RUN_LIVE_MODEL_TESTS=true. Default CI does not call Qwen."
    elif rel.endswith("test_ai_booking_count_parity.py"):
        note = "The module text says source parity. The model side is DeterministicLocalProviderAdapter, so the label is mocked."
    elif rel.endswith("test_evaluation_outbound_productivity_golden.py"):
        note = "Compares EmployeePolicy with outbound-anonymous-reference.json. That file is source_reference_only_not_activated, so the parity status is partial."
    elif rel.endswith("test_pms_ai_phase0_derivation.py"):
        note = "Recomputes v1 from team config and the employee schema. It does not call the assistant. Reviewer sign-off is still open, so the status is partial."
    elif rel.endswith("run_rules_only_baseline.py"):
        note = "Rules-only runner. PHASE_1_BASELINE.md records zero performance records and zero model turns for this kind of run. It is not a factual score."
    return {
        "path": rel,
        "kind": kind,
        "labels": labels,
        "cases": _cases(path, text) if kind == "test" else 0,
        "evidence_status": evidence_status(labels, kind),
        "note": note,
    }


def build() -> dict:
    tests = [_entry(path, "test") for path in discover()]
    runners = []
    for rel in RUNNERS:
        path = ROOT / rel
        if not path.is_file():
            raise SystemExit(f"missing runner {rel}")
        runners.append(_entry(path, "runner"))
    for claimed in ABSENT_OWNER_PATHS:
        if (ROOT / claimed["path"]).exists():
            raise SystemExit(f"owner path now exists and must be classified: {claimed['path']}")
    counts = {label: 0 for label in LABELS}
    for item in tests:
        for label in item["labels"]:
            counts[label] += 1
    return {
        "plan_phase": "1.5",
        "plan_doc": "docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md",
        "owner_inventory": "docs/plans/pms-ai-evidence-first/PHASE_1_BASELINE.md",
        "labels": list(LABELS),
        "file_count": len(tests),
        "case_count": sum(item["cases"] for item in tests),
        "files_by_label": counts,
        "tests": tests,
        "runners": runners,
        "absent_owner_paths": list(ABSENT_OWNER_PATHS),
        "status_note": (
            "verified is not used. source-parity here is partial because the reviewer has not "
            "signed the values and the Outbound reference is not an activated publication. "
            "mocked and synthetic results are not source-parity. live-model is blocked in default CI."
        ),
    }


def render(report: dict) -> str:
    lines = [
        "# Plan Phase 1.5 test-type inventory",
        "",
        "Generated by `evaluation/pms-ai/phase0/inventory_test_types.py`.",
        "Scope: Phase 0 tests, the non-AI scoring check they use, and the AI tests those cases relate to.",
        "The owner's registers stay in `docs/plans/pms-ai-evidence-first/`. This file does not replace them.",
        "",
        report["status_note"],
        "",
        "## Counts",
        "",
        f"Test files: {report['file_count']}. Test functions or `it` blocks: {report['case_count']}.",
        "A file can carry more than one label, so the label counts can add up to more than the file count.",
        "",
        "| Label | Files | Evidence status of what the label proves |",
        "| --- | ---: | --- |",
    ]
    status_for = {
        "synthetic": "not applicable",
        "mocked": "partial",
        "live-model": "blocked",
        "source-parity": "partial",
        "browser": "not applicable",
    }
    for label in LABELS:
        lines.append(f"| `{label}` | {report['files_by_label'][label]} | {status_for[label]} |")
    lines.extend(["", "## Files", "", "| Path | Kind | Labels | Cases | Evidence status |", "| --- | --- | --- | ---: | --- |"])
    for item in report["tests"] + report["runners"]:
        labels = ", ".join(f"`{label}`" for label in item["labels"])
        lines.append(
            f"| `{item['path']}` | {item['kind']} | {labels} | {item['cases']} | {item['evidence_status']} |"
        )
    notes = [item for item in report["tests"] + report["runners"] if item["note"]]
    if notes:
        lines.extend(["", "## Notes", ""])
        for item in notes:
            lines.append(f"- `{item['path']}`: {item['note']}")
    lines.extend(
        [
            "",
            "## Paths named in the owner baseline that are not in this tree",
            "",
            "Status: not applicable. They are not counted as browser tests.",
            "",
        ]
    )
    for claimed in report["absent_owner_paths"]:
        lines.append(f"- `{claimed['path']}` is named in `{claimed['claimed_in']}`. {claimed['note']}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    report = build()
    (PHASE0 / "test_type_inventory.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (PHASE0 / "TEST_TYPE_INVENTORY.md").write_text(render(report), encoding="utf-8")
    print(
        f"files={report['file_count']} cases={report['case_count']} "
        + " ".join(f"{label}={report['files_by_label'][label]}" for label in LABELS)
    )


if __name__ == "__main__":
    main()
