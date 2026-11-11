# PMS AI — PR Execution Queue & GitHub Ticket Index

**Master Tracking Epic:** [#104](https://github.com/mustafapato863-netizen/PMS/issues/104)  
**Governing Plan:** [`docs/plans/PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md`](../PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md)  
**Baseline Commit:** `f8c0e3cd` (`main` — Phase 1 runtime, diagnostics, routing, and slot/header hotfix merged)

---

## Execution Rules for Engineers & Cloud Agents

1. **Disjoint Wave Parallelism:** Tickets within the same **Wave** own disjoint file sets and can be developed in parallel from `main` without merge conflicts.
2. **First Product Milestone:** **Contextual Corrective-Action Suggestions** inside `EmployeeActionModal.tsx` behind a separate default-off Admin flag (`ai_corrective_action_pilot_enabled`). Standalone AI chat (`ai_enabled`) stays **off and hidden** during this pilot.
3. **Test Inventory Sync on Rebase:** Whenever rebasing onto `main` after another PR merges, run:
   ```bash
   python evaluation/pms-ai/phase0/inventory_test_types.py
   ```
   so `evaluation/pms-ai/phase0/TEST_TYPE_INVENTORY.md` and `test_type_inventory.json` stay synchronized in CI.
4. **Governance & Safety:** Never invent PMS numbers, coerce `None` to `0`, treat a score tie as a single winner, mutate database rows from AI read tools, start a second LLM container on the 8 GB KVM 2 VPS, or send employee PII to external models.

---

## Ticket & Wave Matrix

| Issue | Wave | Target Branch | Plan Scope | Depends On |
| :--- | :--- | :--- | :--- | :--- |
| [#94](https://github.com/mustafapato863-netizen/PMS/issues/94) | **Wave 1** | `feat/ai-phase2-domain-reconciliation` | Phase 2: Reconcile 21 doc/config mismatches, runtime status vocabulary, and 37 alias collisions | `main` (`f8c0e3cd`) |
| [#95](https://github.com/mustafapato863-netizen/PMS/issues/95) | **Wave 1** | `feat/ai-pilot-corrective-action-evidence` | Pilot + Phase 3: Separate default-off pilot switch & authorized corrective-action read evidence | `main` (`f8c0e3cd`) |
| [#96](https://github.com/mustafapato863-netizen/PMS/issues/96) | **Wave 1** | `feat/ai-phase3-parity-and-readonly-guard` | Phase 3: Read-only DB transaction guard & source-to-response parity + RBAC matrix | `main` (`f8c0e3cd`) |
| [#97](https://github.com/mustafapato863-netizen/PMS/issues/97) | **Owner / Ops** | *(Non-code / read-only ops)* | Owner expected-value sign-off (`DERIVATION.md`), `--read-db` manifest snapshot, VPS GGUF `sha256sum` | Parallel track |
| [#98](https://github.com/mustafapato863-netizen/PMS/issues/98) | **Wave 2** | `feat/ai-pilot-qwen-action-drafter` | Pilot + Phases 4–5: Qwen corrective-action suggestion drafter, strict draft validator & API | [#94](https://github.com/mustafapato863-netizen/PMS/issues/94), [#95](https://github.com/mustafapato863-netizen/PMS/issues/95) |
| [#99](https://github.com/mustafapato863-netizen/PMS/issues/99) | **Wave 2** | `feat/ai-phase4-5-claim-validator` | Phases 4–5: Bounded Qwen tool loop & deterministic claim ledger validator | [#94](https://github.com/mustafapato863-netizen/PMS/issues/94), [#96](https://github.com/mustafapato863-netizen/PMS/issues/96) |
| [#100](https://github.com/mustafapato863-netizen/PMS/issues/100) | **Wave 3** | `feat/ai-pilot-corrective-action-ui` | Pilot + Phase 5 UX: Contextual suggestion card in `EmployeeActionModal.tsx` (chat stays hidden) | [#98](https://github.com/mustafapato863-netizen/PMS/issues/98) |
| [#101](https://github.com/mustafapato863-netizen/PMS/issues/101) | **Wave 3** | `feat/ai-phase6-feedback-governance` | Phase 6: Feedback PII redaction, retention, failure clustering & human-gated offline review | [#99](https://github.com/mustafapato863-netizen/PMS/issues/99) |
| [#102](https://github.com/mustafapato863-netizen/PMS/issues/102) | **Wave 4** | `feat/ai-phase7-eval-and-cleanup` | Phase 7 (+ Phase 8 Gate): Rules-only vs Qwen-on comparative evaluation & verified legacy cleanup | [#100](https://github.com/mustafapato863-netizen/PMS/issues/100), [#101](https://github.com/mustafapato863-netizen/PMS/issues/101) |
| [#103](https://github.com/mustafapato863-netizen/PMS/issues/103) | **Wave 4** | `chore/ai-phase9-pilot-release-gate` | Phase 9: Staging/VPS readiness script, latency/CPU benchmark, rollback rehearsal & sign-off checklist | [#102](https://github.com/mustafapato863-netizen/PMS/issues/102), [#97](https://github.com/mustafapato863-netizen/PMS/issues/97) |
