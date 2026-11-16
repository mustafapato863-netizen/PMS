# PMS AI conversation origin fixes

## Goal
Keep new workspace and page-assistant chats separate, preserve pre-origin history without falsely classifying it, and require an explicit promotion before a thread changes surfaces.

## Phases
- [x] Inspect current migration, API, repository, and UI behavior; preserve unrelated dirty changes.
- [x] Add `legacy` origin for rows created before origin tracking, including a follow-up migration and visible history section.
- [x] Enforce origin on conversation detail/resume and chat writes; use the existing promotion endpoint for explicit moves.
- [x] Review the focused changes and record verification limits.

## Constraints
- Do not merge, push, deploy, or alter production data.
- Do not rewrite unrelated pending changes in the shared worktree.
- Do not run tests unless requested; update any directly obsolete expectation only when needed to keep the contract coherent.
