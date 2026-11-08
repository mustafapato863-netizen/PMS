# Findings

- The current working tree contains user and/or Gemini changes; do not reset or overwrite them.
- The project already has AI routing, conversation, traces, feedback, Admin review and corrective-action services. Their behavior must be verified at the candidate commit; their presence is not proof of completion.
- Monthly Presentation includes hardcoded fallback material and cannot serve as verified evidence when real records are absent.
- Action's documented statuses include Open/In Progress/Completed/Cancelled and its default is Open. A review form before Save is distinct from a persisted draft; a new durable draft state needs explicit design.
- The local model is Qwen3 4B for the pilot. Its structured response has previously been invalid; prior synthetic benchmarks do not establish general quality.
- User feedback is a signal, not ground truth. The user approved an Admin-reviewed correction process and graduated rollout.
- No new model or new ML dependency is necessary to write the plan; avoid app and production changes during planning.
- User agreed that the engine can technically access the complete dataset when necessary, while each interactive answer remains limited to the requesting user's current authorization. Cross-organization evaluation and dataset preparation are separate Admin-managed workflows.
