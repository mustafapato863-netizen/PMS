# Local evidence synthesis pilot

## Purpose and status

This is a local-only, opt-in pilot that lets Qwen compose answers for a narrow set of branch **booking-count** comparisons and direct team **overall-score** questions, using already scoped PMS evidence. It does not make Qwen the general response engine and is not approved for production. Keep `PMS_AI_LOCAL_SYNTHESIS_ENABLED` unset or false outside the local pilot until the broader evidence, authorization and regression gates are met.

The user question, reporting scope and period, and either the explicitly requested branch counts or one aggregate score are sent to an existing model endpoint on a loopback address. No other branches or employee records are deliberately included. Current account, team, function, branch and level access is checked before the model call and again before returning the response. Requests that mix counts with attendance, conversion, scores, rankings, causes, or actions are excluded from this pilot.

The model produces one brief answer. Before use, the server checks the reporting scope and period, requested numbers and units, and a narrow permitted vocabulary. For booking comparisons it also checks branch names, ordering, and the association of each branch with its count. These checks reduce specific risks but **do not prove semantic or numerical correctness**. Unexpected responses, timeouts, an unavailable model, and a busy model fall back to a server-computed summary. Zero counts are not asserted because the current source path cannot reliably distinguish zero from missing values. Unrelated charts are suppressed for these direct answers.

The endpoint is restricted to a literal loopback IP, HTTP and the known completion path, with redirects disabled. One in-process model request is allowed at a time; requests beyond that use the fallback. This is not a cross-process queue or a production capacity guarantee.

## Local operation

- Local override: `PMS_AI_LOCAL_SYNTHESIS_ENABLED=true` in `Backend/.env.local`.
- Optional bounded timeout: `PMS_AI_LOCAL_SYNTHESIS_TIMEOUT_SECONDS` (default 15 seconds, capped at 30).
- Local endpoint: `PMS_AI_LOCAL_ROUTER_URL`, default `http://127.0.0.1:18080/v1/chat/completions`.
- Disable or roll back by setting `PMS_AI_LOCAL_SYNTHESIS_ENABLED=false` and restarting the backend. The normal answer pipeline remains available.
- Successful responses identify `provider_used=llama_cpp`; the query's `resolution_source` continues to describe the routing step and may be `local_rules`.

## Local test observations

An isolated 50-question synthetic set previously met 35/50 basic checks. With the branch and direct team-score synthesis pilot, 42/50 met those same checks. Qwen wrote 15 answers; one case used the deterministic fallback after an invalid model response. These checks are preliminary, use one small synthetic dataset, and do not establish a general accuracy or production-readiness rate. The checks do not independently certify the semantic correctness of every answer. See the test run for the current code rather than treating this score as a release gate.

The model was also given eight manually prepared, independently specified evidence bundles in a separate probe. It correctly conveyed the main requested facts in several cases, but sometimes omitted a percentage sign or added an unsupported description. A nonempty response or matching a few tokens is not sufficient validation.

## Remaining work

- Obtain independently reviewed real-source parity fixtures, including branch-specific publication, zero vs missing values, aggregate precision, ties, role revocation and cache revision changes.
- Make planning request all independently necessary evidence for multi-part questions; wording alone cannot recover data that was never retrieved.
- Expand beyond branch counts only after implementing and testing fact-level grounding, answer completeness, misleading wording, unknown data, injection and per-role visibility. The pilot is not a general hallucination detector.
- Benchmark and review p50/p95 latency and throughput on the intended host, including model failure, concurrent processes, and resource limits.
- Retest UI responses, links and labels in Monthly Presentation and Team Dashboard across supported roles. Keep this feature local until the user accepts it.
