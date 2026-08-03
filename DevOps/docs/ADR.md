# Architecture Decision Records (ADR)

This document contains the Architecture Decision Records (ADRs) for the PMS Dashboard, detailing the context, decisions, consequences, and alternatives considered for key architectural choices.

---

## ADR-001: DB-First Read Path for Dashboard Metrics

### Status
Accepted

### Context
The dashboard requires real-time aggregations, filters by operational team, grade distribution metrics, and detailed agent lists. We need a scalable, consistent, and relational data access strategy that allows complex joins and indexing.

### Decision
Implement a database-first read path utilizing PostgreSQL via SQLAlchemy ORM. All client dashboard queries must hit PostgreSQL tables as the primary source of truth, utilizing indexes (such as trigram GIN indexes on employee names) to optimize read performance.

### Consequences
- **Positive:** Standardized query capabilities, high consistency, transaction support, and scalable indexing.
- **Negative:** Requires a running PostgreSQL instance; latency is bound by database queries.
- **Verification:** Unit and integration tests verify direct query results from the database engine.

### Alternatives Considered
- *JSON-Only Data Source:* Storing all metrics in JSON files would eliminate database overhead but would scale extremely poorly, prevent relational integrity, and make concurrent updates difficult.
- *Cache-Only Architecture:* Storing live data solely in Redis would lead to data durability risks and query limitations.

---

## ADR-002: Static JSON Repository Fallbacks

### Status
Accepted

### Context
In disconnected local development, initial setup environments, or during temporary PostgreSQL database connection losses, a fail-shut system would crash the dashboard entirely, rendering the UI unusable.

### Decision
Implement transparent JSON fallbacks within the repository layer (`Backend/repositories/`). If a database query fails or the database is detected as empty, the repository interceptor transparently reads from static pre-seeded JSON files in `Backend/data/`.

### Consequences
- **Positive:** Graceful degradation of service, high resilience during offline environments or bootstrap seeding.
- **Negative:** Risk of stale fallback data; extra code complexity in the repository layer to maintain dual-path logic.
- **Verification:** Tested by mocking PostgreSQL connection failures and verifying that seed data is returned.

### Alternatives Considered
- *Fail-Shut System:* Throwing immediate HTTP 500 errors. Rejected to preserve user experience during quick restarts or migrations.

---

## ADR-003: Config-Driven Team Onboarding

### Status
Accepted

### Context
Operational teams frequently adjust KPI metrics, weights, column mappings, and grading thresholds. Modifying code or writing custom database schemas for every new team creates code bloat and testing overhead.

### Decision
Define team KPI metadata, actual/target Excel column names, grade thresholds, and UI configurations inside standalone JSON files under `Backend/config/teams/`. The backend dynamically loads and validates these configs at startup.

### Consequences
- **Positive:** Adding a new team requires zero backend code changes if their Excel upload layout conforms to standard parsing. De-couples domain logic from database schema changes.
- **Negative:** Requires strict JSON schema validation to prevent malformed configs from crashing the application.
- **Verification:** Dynamic team config loaders validate configurations on FastAPI startup and throw structured errors for invalid schemas.

### Alternatives Considered
- *Hardcoded Database Models:* Creating specific tables/columns for each team. Rejected because it requires database migrations and schema changes for every KPI change.

---

## ADR-004: Unified KPI Scoring Engine with Capped Contribution

### Status
Accepted

### Context
Different operational teams track a wide variety of KPIs (e.g. Average Handle Time vs. Patient Attendance). To display consistent dashboard rankings, score distributions, and executive summaries, we need a unified calculation model.

### Decision
Implement a unified calculation engine where:
1. KPI achievement is calculated based on direction (`higher_better` vs `lower_better`) and capped at 100% before it is persisted or displayed.
2. Effective KPI achievement remains capped at 100% for final score aggregation.
3. KPI Contribution is calculated as: $\text{Effective Achievement} \times \text{KPI Weight}$.
4. The Final Performance Score is the sum of all contributions, capped at 100%.

### Consequences
- **Positive:** Prevents a single over-achieving KPI from artificially masking poor performance in other critical KPIs. Ensures all final scores reside on a standard 0–100% scale.
- **Negative:** Agents do not receive scoring credit on the dashboard for performing far beyond 100% on a specific KPI; the product intentionally uses a single comparable scale.
- **Verification:** Unit tests inside `test_three_teams.py` and `test_submission_team.py` validate this calculation.

### Alternatives Considered
- *Uncapped Score Summation:* Letting scores exceed 100%. Rejected because it distorts grade distributions and makes executive comparisons impossible.

---

## ADR-005: Scoped Real-Time Socket.IO Notification Delivery

### Status
Accepted

### Context
Managers and admins must receive immediate notifications when new Excel workbooks are processed, when performance alerts are generated, or when corrective actions are recorded. Broadcasting all alerts globally to everyone violates privacy boundaries and increases browser message load.

### Decision
Use Socket.IO rooms to scope real-time events. Admin accounts subscribe to a global admin room, while managers and agents join rooms specific to their assigned teams. The server routes events specifically to targeted rooms.

### Consequences
- **Positive:** Low network traffic, localized scope, and improved user privacy.
- **Negative:** Requires active socket connections; message delivery fails if a user is offline (resolved by writing notification history to the database).
- **Verification:** Connection events and room joining behavior are verified using Socket.IO integration tests.

### Alternatives Considered
- *HTTP Long Polling:* High CPU and network overhead on the server.
- *Server-Sent Events (SSE):* Unidirectional only, making it harder to coordinate bidirectional interactive components.

---

## ADR-006: Role-Based Sidebar and Route Protection

### Status
Accepted

### Context
The PMS Dashboard includes administrative pages (User management, Team configurations, Planning workspace) containing sensitive settings that must not be accessed by viewers or regular agents.

### Decision
Enforce Role-Based Access Control (RBAC) at both the client app shell and backend routes. The frontend React application hides sidebar links and block-routes based on the active session role (`Admin`, `Manager`, `Executive`, `Viewer`). The backend middleware validates JWT payloads and active database records on every REST request.

### Consequences
- **Positive:** Clear, uncluttered user interface tailored to specific duties; secure backend rejection of unauthorized actions.
- **Negative:** Frontend role mappings must be kept in sync with database role enums (`user_role`).
- **Verification:** Router tests verify that non-admin requests receive HTTP 403 Forbidden on management routes.

### Alternatives Considered
- *Client-Only Hiding:* Hiding UI components without backend validation. Rejected as it allows trivial security bypasses via postman or console requests.

---

## ADR-007: Defaulting Month Filters to Latest Month containing data

### Status
Accepted

### Context
Selecting "All Months" compiles multiple records per employee, distorting the active headcount count. Defaulting the dashboard to a static initial month (e.g. January) displays empty dashboards if data has not yet been uploaded for that month.

### Decision
By default, load all dashboard pages using the latest available month containing performance records in the database. If "All Months" is selected, aggregate all trends and scores, but restrict the "Total Agents" headcount card to show the headcount of that latest available month, alongside a warning note.

### Consequences
- **Positive:** The dashboard is populated with relevant data immediately upon loading; headcount counts are accurate and not artificially inflated.
- **Negative:** Requires a dynamic query at startup to resolve what the latest month is.
- **Verification:** Manual verification in the frontend and integration checks on filter endpoint parameters.

### Alternatives Considered
- *Current Calendar Month Default:* Defaulting to the active calendar month (e.g. June). Rejected because operational data uploads are typically delayed by a few weeks, leading to default empty screens.
