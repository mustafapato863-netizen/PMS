# Agent Instructions

You are working with standard engineering skills and best practices. Prefer using the appropriate skill instead of improvising.

## Skill Routing Rules

When the user describes a situation, prefer the following workflow:

### Starting New Work
- User has an idea but needs alignment → Suggest `/to-spec` or `/grilling`.
- Spec is ready and the work is large → Suggest `/to-tickets`.
- Spec or ticket is ready to build → Suggest `/implement`.
- Small change that doesn't need a full spec → Go straight to `/implement`.

### During Implementation
- User wants test-first development → Use `/tdd`.
- User wants to implement a ticket or spec → Use `/implement`.

### Quality & Review
- User wants to review code, a PR, or a diff → Use `/code-review` or `/code-reviewer`.
- User wants to improve architecture or module design → Use `/improve-codebase-architecture` or `/codebase-design`.

### After Work
- Work is finished and user wants to improve the process → Suggest `/retro`.

### When Unsure
- User doesn't know which skill to use → Tell them to run `/ask-matt`.

## General Rules
- Prefer the main engineering flow for non-trivial work: spec → tickets → implement → code-review.
- Do not skip speccing for medium or large features.
- When implementing, prefer test-first development where it makes sense.
- Always suggest the next logical step instead of jumping straight into coding when requirements are unclear.
- If already in the middle of an implementation flow, continue with the next logical skill.

## Domain Skills
Prefer using the relevant domain skill when available:
- Frontend work → `frontend-design` or `ui-ux-pro-max`
- Backend work → `senior-backend` or `senior-fullstack`
- Testing → `webapp-testing` or `tdd`
- Code review & quality → `clean-code` or `code-reviewer`
- Diagnostics & debugging → `debugger`
