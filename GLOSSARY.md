# PMS Dashboard

The language for the performance review workspace: who is measured, over which month, and which screen shows it.

## Language

**User Rules Spec**:
A structured description of who the authenticated user is, what data they can access, and what they cannot access. Derived from the user's role, team/function/region/branch assignments, and RBAC scope. Injected into the AI assistant's context for every turn so the model never leaks data outside the user's permissions.
_Avoid_: user permissions, access control list, ACL

**360 Profile**:
The full employee performance profile including identity (name, team, region, level, position), complete monthly performance history, KPI breakdowns, corrective action history, and trend analysis. Accessible via `GET /api/employee/{employee_id}` with scope enforcement. Used by the assistant for self-service queries when an employee asks about their own numbers.
_Avoid_: employee scorecard, employee record, employee dashboard

**User Memory**:
A persistent per-user store of interaction patterns, preferences, frequent queries, and learned behaviors. Used to personalize intent classification, response formatting, evidence selection, and follow-up suggestions across sessions. Stored in `ai_user_memory` table, one row per user.
_Avoid_: user context, user profile, user preferences

**Self-Service Query**:
A query where the user asks about their own data (e.g., "How am I doing?", "What's my score?"). The assistant resolves the user's employee_id from their scope and fetches their 360 profile.
_Avoid_: personal query, my-data query

**Memory-Enhanced Classification**:
Using stored user memory to bias or improve intent classification. For example, if a user frequently asks about Inbound team, the classifier can pre-populate that context.
_Avoid_: personalized intent, adaptive classification

**Executive Summary**:
The corporate or managerial performance screen at `/executive`.
_Avoid_: Executive Overview, overview

**Monthly Review**:
The only speaking deck for a month of performance.
_Avoid_: Monthly Presentation, Monthly Performance Review, monthly view

**Insights**:
The working analysis screen of live performance. It can be shown in a meeting.
_Avoid_: Insights deck, second deck, analysis deck

**Speaking deck**:
The one narrative surface used to talk an audience through a month. Monthly Review is that surface.
_Avoid_: second deck, slide deck
