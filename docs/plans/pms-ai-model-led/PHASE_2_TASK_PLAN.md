 # Phase 2 Task Plan: Gated Model-Led Pilot Path
 
 Authoritative Plan: docs/plans/PMS_AI_MODEL_LED_IMPLEMENTATION_PLAN.md
 Gate: Phase 0 and 1 complete (verified)
 
 ## Phase 2 Scope: Minimal Gated Model-Led Pilot
 
 ### Objective
 Replace lexical gates and regex overrides with a gated model-led tool-calling path while preserving 100% backend authority (RBAC, data retrieval, calculations, units, claim validation).
 
 ### Pilot Flag
 - PMS_AI_MODEL_LED_PILOT_ENABLED (default: false)
 - Admin-only toggle via existing read_ai_enabled(db) + role check
 - Seamless fallback to legacy deterministic path
 
 ## Implementation Tasks
 
 ### 1. Configuration: Add Pilot Flag
 - [ ] Add model_led_pilot_enabled to AiRuntimeConfig in Backend/services/ai/config.py
 - [ ] Read from PMS_AI_MODEL_LED_PILOT_ENABLED env var (default false)
 - [ ] Add to get_ai_runtime_config()
 
 ### 2. Contextual Assistant: Replace Lexical Gates
 - [ ] In contextual_assistant.py, gate detect_contextual_capability behind pilot flag
 - [ ] When pilot enabled: route greetings, help, off-topic, explain-previous to model
 - [ ] Preserve page context extraction, corrective action logic (unchanged)
 - [ ] Legacy path unchanged when pilot disabled
 
 ### 3. Router: Replace Regex Overrides with Structured Tool Calling
 - [ ] In router.py, add model-led path when pilot enabled
 - [ ] Define tool schemas: read_employee_metric, compare_branches, get_score_trend, rank_employees, get_kpi_diagnosis
 - [ ] Model receives typed tool schemas, selects tools and args
 - [ ] Backend validates and executes via DeterministicToolRegistry
 - [ ] Preserve RBAC, catalog validation, period availability checks
 - [ ] Legacy regex path unchanged when pilot disabled
 
 ### 4. Local Evidence Synthesis: Remove Synthesis Fences
 - [ ] In local_evidence_synthesis.py, gate synthesis fences behind pilot flag
 - [ ] When pilot enabled: allow employee-level queries to reach model synthesis
 - [ ] Remove hardcoded rejection of employee, person, agent keywords
 - [ ] Preserve claim validation via ClaimLedgerValidator
 
 ### 5. Orchestrator: Add Model-Led Pipeline
 - [ ] In orchestrator.py, add pilot path that:
   - Builds bounded context (recent dialogue + compact confirmed state + catalog refs)
   - Calls model with tool schemas
   - Executes validated tool calls
   - Passes typed evidence to model for answer composition
   - Validates claims via ClaimLedgerValidator
   - Falls back to deterministic on provider failure/validation failure
 - [ ] Preserve turn persistence, RBAC, conversation contracts
 
 ### 6. Tests: Verify Pilot Path
 - [ ] Add pilot-enabled test configurations
 - [ ] Verify model-led path works for: greetings, employee scores, trend, comparisons, country switch
 - [ ] Verify fallback to deterministic on provider failure
 - [ ] Verify RBAC still enforced
 - [ ] Verify ClaimLedgerValidator rejects hallucinated claims
 
 ### 7. Evaluation: Freeze New Blind Set
 - [ ] Create new blind evaluation fixture (separate from exposed sets)
 - [ ] Run pilot evaluation on dev + blind sets
 - [ ] Document results
 
 ## Success Criteria
 - [ ] Pilot flag toggles behavior without breaking legacy path
 - [ ] Model handles varied English (no lexical gate rejections)
 - [ ] Tool calls validated and executed by backend
 - [ ] Answers grounded in evidence, validated by ClaimLedgerValidator
 - [ ] All existing tests pass (legacy path)
 - [ ] New pilot tests pass
 - [ ] No secrets leaked, no PII sent to provider
 
 ## Rollback
 - Set PMS_AI_MODEL_LED_PILOT_ENABLED=false (default)
 - Legacy deterministic path remains fully functional
 - No database migrations required
