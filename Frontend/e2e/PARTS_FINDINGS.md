# Part-by-part end-to-end findings

Two runs of `Frontend/e2e/parts.spec.ts` against `http://127.0.0.1:5173` and `http://127.0.0.1:8000` on 2026-10-26. Logs: `run-1.log` and `run-2.log` in the scratch directory for this goal. Both runs list the same result for every part. No accounts, scores, actions, or settings were changed.

## Results

| Part | Run 1 | Run 2 | Observation in both logs |
| --- | --- | --- | --- |
| sign-in | blocked | blocked | `E2E_PART sign-in BLOCKED PMS_E2E_USERNAME or PMS_E2E_PASSWORD is unset` |
| executive | blocked | blocked | `E2E_PART executive BLOCKED PMS_E2E_USERNAME or PMS_E2E_PASSWORD is unset` |
| function-summary | blocked | blocked | `E2E_PART function-summary BLOCKED PMS_E2E_USERNAME or PMS_E2E_PASSWORD is unset` |
| team | blocked | blocked | `E2E_PART team BLOCKED PMS_E2E_USERNAME or PMS_E2E_PASSWORD is unset` |
| employee | blocked | blocked | `E2E_PART employee BLOCKED PMS_E2E_USERNAME or PMS_E2E_PASSWORD is unset` |
| insights | blocked | blocked | `E2E_PART insights BLOCKED PMS_E2E_USERNAME or PMS_E2E_PASSWORD is unset` |
| planning | blocked | blocked | `E2E_PART planning BLOCKED PMS_E2E_USERNAME or PMS_E2E_PASSWORD is unset` |
| corrective-actions | blocked | blocked | `E2E_PART corrective-actions BLOCKED PMS_E2E_USERNAME or PMS_E2E_PASSWORD is unset` |
| monthly-review | blocked | blocked | `E2E_PART monthly-review BLOCKED PMS_E2E_USERNAME or PMS_E2E_PASSWORD is unset` |
| account | blocked | blocked | `E2E_PART account BLOCKED PMS_E2E_USERNAME or PMS_E2E_PASSWORD is unset` |
| logged-out-gate | passed | passed | `E2E_PART logged-out-gate PASSED Username; Sign In; monthly review refused` |

The logged-out gate opened `/monthly-presentation` with no session. The screen showed the Username field and the Sign In button, and it did not show the Monthly Presentation overview. That is the refusal check. Frontend returned HTTP 200 and `/api/health` returned HTTP 200 before the suite started. The signed-in parts were not opened: the username and password were unset in the process, the user environment, and the machine environment.

## Issues

No product issue. The only part the runs opened behaved as required. A blocked part was not opened, so it has no issue and no recommendation.

## Recommendations

None. A recommendation is written only for a product issue the two runs showed.
