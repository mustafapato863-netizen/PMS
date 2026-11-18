# Phase 3 Coverage Evidence Audit

**Document version:** 1.1 — evidence correction, 2026-11-17  
**Scope:** local synthetic tests and repository coverage manifest only  
**Governing plan:** `docs/plans/PMS_AI_MODEL_LED_IMPLEMENTATION_PLAN.md`

## Status vocabulary

- **Synthetic parity:** a named operation was exercised against synthetic records. This does not certify published PMS data.
- **Published proof:** the operation was compared with an authorized published source and reviewed. No such proof is recorded in this audit.
- **Verified no data:** a scoped read of the authoritative published source returned no published rows and has review evidence. No scope is certified this way.
- **Unsupported:** the authorized tool contract explicitly does not support the requested operation or scope. The current local fixtures do not establish this status for whole departments.
- **Not verified:** no matching operation-level or published-source evidence is available.

## Operation evidence

All six tool schemas are present and match the registry contract. The strongest synthetic execution coverage is the Inbound fixture. Department-specific checks below exercise `read_employee_metric` only; they do not prove every tool, KPI, level, or geography for that department.

| Authorized operation | Local synthetic evidence | Status and limits |
| :--- | :--- | :--- |
| `read_employee_metric` | Waiting Time, booking count/rate, and zero preservation in Inbound; country isolation for Coding UAE/EGY; individual metric checks for Pharmacy, Marketing, Finance, Human Resources, IT, and Sales Managerial. | **Synthetic parity** for these fixture examples only. No published-source proof. |
| `get_employee_history` | Inbound employee history for Nadia Fadel across August and September 2026. | **Synthetic parity** for this employee, metric, and period pair only. |
| `compare_branches` | Inbound fixture branches; separate negative tests deny inaccessible branches. | **Synthetic parity** for the fixture branch set only. |
| `get_score_trend` | Inbound Waiting Time history and unit/direction checks. | **Synthetic parity** for tested Inbound history only. |
| `rank_employees` | Inbound employee ranking, evidence values, and denominator checks. | **Synthetic parity** for the tested Employee-level fixture only. |
| `get_kpi_diagnosis` | Inbound Booking diagnosis and pre-query access checks. | **Synthetic parity** for the tested Inbound fixture only. |

## Scope coverage

| Team / scope | Country | Performance level | Operation-level evidence in this execution | Status |
| :--- | :--- | :--- | :--- | :--- |
| Inbound | EGY fixture | Employee | All six operations above; synthetic Waiting Time and booking evidence. | **Synthetic parity**, selected fixtures only |
| Coding | UAE | Employee | `read_employee_metric`; paired country-isolation test. | **Synthetic parity**, selected fixture only |
| Coding EGY | EGY | Employee | `read_employee_metric`; paired country-isolation test. | **Synthetic parity**, selected fixture only |
| Pharmacy | UAE fixture | Employee | `read_employee_metric` Waiting Time. | **Synthetic parity**, one metric |
| Marketing | UAE fixture | Employee | `read_employee_metric` currency unit. | **Synthetic parity**, one metric |
| Finance | Fixture scope | Employee | `read_employee_metric` department KPI. | **Synthetic parity**, one metric; country not certified |
| Human Resources | Fixture scope | Employee | `read_employee_metric` department KPI. | **Synthetic parity**, one metric; country not certified |
| IT | Fixture scope | Employee | `read_employee_metric` department KPI. | **Synthetic parity**, one metric; country not certified |
| IT | EGY | Corporate | `read_employee_metric` and `rank_employees` with `performance_level=Corporate` (`test_it_corporate_level_execution`), plus negative Employee-level leak assertions. | **Synthetic parity**, selected Corporate fixture only |
| Sales | Fixture scope | Managerial | `read_employee_metric` with `performance_level=Managerial`. | **Synthetic parity**, one level and metric |
| Other departments and team variants | UAE / EGY | Employee / Managerial / Corporate | No exact operation-by-scope evidence assembled here. | **Not verified** |
| Any department | KSA | Employee / Managerial / Corporate | Negative scope verification only: explicit KSA queries (`p516_t4` / `test_phase5_ksa_scope_isolation`) return synthetic `unavailable_data` with zero evidence (`EGY` records isolated); repository manifest contains no KSA cells and no published-source query was run. | **Not verified** (negative synthetic `unavailable_data` verification only; do not report “verified no data”) |
| Corporate level (non-IT scopes) | Any country | Corporate | Only `IT | EGY | Corporate` has synthetic execution coverage (`test_it_corporate_level_execution`); other departments at Corporate level are not exercised. | **Not verified** |

## Repository manifest snapshot

`build_coverage_manifest(db=None)` was run without opening a database connection. It inspected repository aggregate snapshot metadata only. It returned 96 cells: 0 certified, 36 partial, 5 blocked-source, 55 not applicable, and 0 verified-no-data. Every cell had reviewer status `pending`. The country labels present were `All`, `EGY`, and `UAE`; KSA was absent. Aggregate source inventory counts are not proof that an operation can query or publish those records at runtime.

Accordingly, the former broad `verified` and `no published data` labels have been removed. No matrix cell currently has **Published proof** or **Verified no data** status. Keep any later certification tied to an exact country, team, level, operation, source revision, and reviewer decision.

**2026-11-17 recheck:** KSA employee, managerial, and corporate scope remain **Not verified**. Corporate performance-level execution remains **Not verified**; the selected Sales Managerial synthetic example is not Corporate-level evidence.

**2026-11-18 recheck:** Added `IT | EGY | Corporate` **Synthetic parity** coverage from `test_it_corporate_level_execution` (`read_employee_metric` and `rank_employees` at `performance_level=Corporate`, plus Employee-level isolation assertions). KSA employee, managerial, and corporate scopes remain **Not verified** (covered only by negative synthetic `unavailable_data` scope-isolation checks); non-IT Corporate scopes remain **Not verified**.

## Authorization and data integrity evidence

The focused synthetic tests exercise self-only employee restrictions, branch restrictions, team restrictions, cross-country Coding isolation, valid zero versus missing values, and preservation of units such as `%`, `min`, `AED`, and `count`. These tests establish local contract behavior for their fixtures. They do not establish production role mappings, published source parity, or coverage for untested team/level combinations.
