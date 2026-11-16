# Findings

- The current `a8c3e1f4d9b2` migration assigns existing rows `workspace` by default. Before origin tracking, the contextual assistant persisted conversation IDs through `/api/ai/chat`, so historical rows can come from either surface.
- `get_or_create_owned_conversation` returns an existing row by ID without comparing its stored origin to the requested surface. Workspace deep links also load detail without checking its returned origin.
- The route already has a promotion endpoint and maps stale-context errors to HTTP 409; use that explicit path for legacy-to-workspace continuation.
- A timestamp cutoff would leave old contextual-assistant records created after the first origin migration mislabeled as workspace. The follow-up migration now converts every pre-existing `workspace` value to `legacy`, preserves known `page_assistant` rows, and changes the database default to `legacy`; current clients send an explicit origin.
- Existing worktree contains broad unrelated pending AI corrective-action and Monthly Presentation changes. Keep this patch narrow and leave all existing edits intact.
- `rtk cat` is unavailable on this Windows install; use `rtk python` with explicit UTF-8 for text reads. A multi-line `python -c` read attempt failed due quoting; switched to one-line reads.
