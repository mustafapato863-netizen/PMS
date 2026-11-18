# Phase 3: User Memory System (Persistence)

## Status: Ready to implement

### 3.1 Design AiUserMemory model
Fields:
- id (UUID, PK)
- user_id (UUID, FK to users.id, unique, indexed)
- preferences (JSON) - preferred detail level, communication style, preferred metrics
- query_patterns (JSON) - frequently asked topics, common teams/KPIs, query frequency
- interaction_summary (Text) - rolling summary of recent conversations
- feedback_signals (JSON) - thumbs up/down history, correction patterns
- created_at, updated_at
- last_accessed_at (for decay/pruning)

### 3.2 Migration
Create Alembic migration for ai_user_memory table.

### 3.3 Memory read/write service
- `UserMemoryService.load_memory(user_id)` → returns memory dict or None
- `UserMemoryService.save_memory(user_id, updates)` → upserts memory
- `UserMemoryService.decay_memory(user_id)` → prunes old entries

### 3.4 Memory schema
```json
{
  "preferences": {
    "detail_level": "brief" | "detailed" | "auto",
    "communication_style": "formal" | "casual" | "auto",
    "preferred_metrics": ["Booking Rate", "Attendance Rate"],
    "preferred_teams": ["Inbound", "Outbound"]
  },
  "query_patterns": {
    "frequent_topics": ["score", "trend", "comparison"],
    "frequent_teams": {"Inbound": 5, "Outbound": 3},
    "frequent_kpis": {"Booking Rate": 8, "Attendance Rate": 4},
    "query_count": 42
  },
  "interaction_summary": "User frequently asks about Inbound team performance...",
  "feedback_signals": {
    "positive_count": 10,
    "negative_count": 2,
    "corrections": ["User corrected metric name from 'booking' to 'Booking Rate'"]
  }
}
```

### 3.5 Wire into orchestrator
- Load memory at turn start
- Inject memory summary into system context
- Update memory after turn (async, non-blocking)

### 3.6 Memory decay/pruning
- Entries older than 30 days with no access → prune
- Keep top 10 frequent items per category
- Cap interaction_summary at 500 chars
