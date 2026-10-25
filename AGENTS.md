## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, use the installed graphify skill or instructions before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
# Agent Instructions

You are working with Matt Pocock's skills system. Prefer using the appropriate skill instead of improvising.

## Skill Routing Rules

When the user describes a situation, prefer the following skills:

### Starting New Work
- User has an idea but no clear plan → Suggest `/grill-with-docs` (or `/grill-me` if no existing codebase).
- After grilling is done and decisions are clear → Suggest `/to-spec`.
- Spec is ready and the work is large → Suggest `/to-tickets`.
- Spec or ticket is ready to build → Suggest `/implement`.
- Small change that doesn't need a full spec → Go straight to `/implement`.

### During Implementation
- User wants test-first development → Use `/tdd`.
- User wants to implement a ticket or spec → Use `/implement`.

### Quality & Review
- User wants to review code, a PR, or a diff → Use `/code-review`.
- User wants to improve architecture or module design → Use `/improve-codebase-architecture` or `/codebase-design`.

### After Work
- Work is finished and user wants to improve the process → Suggest `/retro`.

### When Unsure
- User doesn't know which skill to use → Tell them to run `/ask-matt`.

## General Rules
- Prefer the main flow for non-trivial work: grill → spec → tickets → implement → code-review.
- Do not skip grilling and speccing for medium or large features.
- When implementing, prefer test-first where it makes sense.
- Always suggest the next skill instead of jumping straight into coding when the work is not yet specified.
- If the user is already in the middle of a flow, continue with the next logical skill.

## ECC Skills
You have ECC skills installed in ~/.grok/skills/.
Prefer using these skills when relevant:
- Frontend work → frontend-patterns
- Security checks → security-review
- Code quality → coding-standards
- API design → api-design
- Backend work → backend-patterns
- Testing → tdd-workflow or e2e-testing
- Accessibility → accessibility