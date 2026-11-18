# PMS AI Model-Led Transition: Active Workspace Entry Point

**Authoritative Specification:** [PMS AI Model-Led Implementation Plan](../PMS_AI_MODEL_LED_IMPLEMENTATION_PLAN.md)  
**EGM Swarm Review Report:** [EGM_SWARM_REVIEW_REPORT.md](EGM_SWARM_REVIEW_REPORT.md)  
**Cleanup Manifest:** [CLEANUP_MANIFEST.md](CLEANUP_MANIFEST.md)  
**Request Path Audit:** [REQUEST_PATH_AUDIT.md](REQUEST_PATH_AUDIT.md)  
**Phase 1 Provider Evidence:** [PHASE_1_PROVIDER_EVIDENCE.md](PHASE_1_PROVIDER_EVIDENCE.md)  
**Phase 1 Authenticated Revalidation:** [PHASE_1_AUTHENTICATED_REVALIDATION.md](PHASE_1_AUTHENTICATED_REVALIDATION.md)  
**Phase 5 Evaluation and Coordinator Handoff:** [PHASE_5_EVALUATION_AND_HANDOFF.md](PHASE_5_EVALUATION_AND_HANDOFF.md)  
**Phase 5 Review Report:** [PHASE_5_REVIEW_REPORT.md](PHASE_5_REVIEW_REPORT.md)  
**Phase 6 Cleanup & Handoff:** [PHASE_6_CLEANUP_AND_HANDOFF.md](PHASE_6_CLEANUP_AND_HANDOFF.md)
**Phase 6 Review Report:** [PHASE_6_REVIEW_REPORT.md](PHASE_6_REVIEW_REPORT.md)
**Phase 3 Coverage Audit:** [PHASE_3_COVERAGE_MATRIX.md](PHASE_3_COVERAGE_MATRIX.md)  
**Execution Ledger:** [task_plan.md](task_plan.md)  
**Findings:** [findings.md](findings.md)  
**Progress:** [progress.md](progress.md)  

---

## Current Status

- **Active Phase:** Phases 0–6 Complete & Accepted (`PHASE_6_REVIEW_REPORT.md`: `VERDICT: ACCEPTED`, 0 Blocker, 0 Major); halted before Phase 7.
- **Phase Boundary Rule:** Halted before Phase 7 staging/rollout. No `git push`, no production migrations, and no live rollout authorized yet.
- **Recovery Point:** `backups/snapshot_phase0_revalidated_20261117_132614/` captures the pre-edit current WIP; the tracked patch passed reverse-apply validation.
- **UI Availability:** No local frontend/backend listener was present during the signed-in UI check; HTTP verification uses synthetic in-memory data.

---

## Historical Documentation Index (Reference Only)

The following historical planning documents have been superseded by the authoritative plan. Their business calculations, data dictionaries, security contracts, and conversation persistence contracts remain preserved as domain references:

1. [PMS AI Evidence-First Implementation Plan](../PMS_AI_EVIDENCE_FIRST_IMPLEMENTATION_PLAN.md) — *Superseded (Qwen local focus retired; evidence & privacy contracts retained)*
2. [PMS AI All-Departments Roadmap](../PMS_AI_ALL_DEPARTMENTS_ROADMAP.md) — *Superseded (Milestones retired; scope coverage & hierarchy retained)*
3. [PMS AI Chatbot Implementation Plan](../pms-ai-chatbot-implementation-plan.md) — *Superseded (Local composition retired; presentation metrics retained)*
4. [Contextual AI Assistant Plan](../contextual-ai-assistant/IMPLEMENTATION_PLAN.md) — *Superseded (Historical local pilot reference)*
5. [Contextual AI Assistant Full Coverage Plan](../contextual-ai-assistant/FULL_COVERAGE_EXECUTION_PLAN.md) — *Superseded (Egypt/UAE separation & coverage retained)*
6. [PMS AI Conversation v2 Blueprint](../pms-ai-conversation-v2/IMPLEMENTATION_BLUEPRINT.md) — *Superseded (Turn lifecycle, ownership & idempotency retained)*
7. [PMS AI Conversation Origin Fix](../pms-ai-conversation-origin-fix/task_plan.md) — *Historical bug fix reference (Origin separation & thread isolation)*
8. [PMS AI Response Quality Final](../pms-ai-response-quality-final/task_plan.md) — *Historical regression & WIP quality findings*
9. [PMS AI Evidence-First PR Queue](../pms-ai-evidence-first/PR_EXECUTION_QUEUE.md) — *Superseded PR queue*
10. [PMS AI Classifier Evaluation Report](../pms-ai-classifier-evaluation-report.md) — *Historical experiment (Classifier disabled)*
11. [PMS AI Domain Dictionaries](../pms-ai-evidence-first/KPI_SOURCE_DICTIONARY.md) — *Active domain reference (KPI definitions, data relationships, glossary)*

---

## Key Operating Rules

1. **Model Distinction:** The model selected in the user's coding application (e.g., implementation assistant) is NOT automatically the PMS runtime model. The runtime provider is configured strictly via the application's environment configuration (`Backend/config/environment.py`, `UnifiedProviderEngine`).
2. **Zero Inventions:** Never invent an API model identifier or silently switch providers.
3. **Preserve Unrelated Work:** Maintain all existing WIP modifications across backend and frontend.
4. **No Premature Deletions:** No runtime modules, routes, or dependencies are to be deleted in Phase 0 or 1.
