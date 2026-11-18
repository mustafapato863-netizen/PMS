# ADR 0002: Persistent User Memory for AI Assistant Personalization

## Status
Proposed

## Context
The PMS AI assistant currently treats every conversation as stateless. It has access to the user's scope (role, teams, functions, regions, branches) but does not remember past interactions, preferences, or learned patterns. This means:
- Intent classification cannot be biased by a user's frequent query patterns
- Response formatting cannot adapt to user preferences (brief vs detailed)
- Evidence selection cannot prioritize KPIs the user cares about
- Follow-up suggestions are generic rather than personalized

Additionally, when an employee (agent) asks about "their numbers", the assistant does not automatically fetch their 360 profile — it requires explicit employee_id references.

## Decision
We will implement a persistent `AiUserMemory` table (one row per user) that stores:
- **Preferences**: preferred response detail level, preferred metrics, communication style
- **Query patterns**: frequently asked topics, common teams/KPIs
- **Interaction summaries**: rolling summary of recent conversations
- **Feedback signals**: thumbs up/down history, correction patterns

The memory will be:
1. **Loaded at turn start** — injected into the orchestrator context as "user context"
2. **Updated after each turn** — append new patterns, update preferences based on feedback
3. **Decayed over time** — old entries expire, keeping only relevant patterns

Additionally, we will add a "User Rules Spec" — a structured object derived from scope that explicitly states what the user can and cannot see, injected into every prompt.

For employees/agents, we will add self-service intent detection that automatically fetches their 360 profile when they ask about their own numbers.

## Consequences
- **Positive**: Better personalization, faster intent classification, more relevant responses
- **Negative**: Additional DB table, memory load/write latency per turn, privacy considerations (memory must be clearable)
- **Risk**: Memory could become stale or biased; mitigation via decay and admin clear endpoint

## Alternatives Considered
1. **Session-only memory** — Rejected: doesn't persist across sessions, loses value
2. **Embedding-based memory** — Rejected: over-engineered for current scale; structured key-value is simpler and auditable
3. **No memory, just better prompts** — Rejected: doesn't solve the fundamental lack of personalization
