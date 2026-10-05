# Frontend contract — General Manager role (Backend Option A)

**Backend PR ships role string `"General Manager"`.** Frontend must redo PR #8 away from Option B (flag-as-GM).

## `/me` field rename (breaking)

| Old | New |
| --- | --- |
| `is_general_manager` | `has_unrestricted_team_access` |

- Returned by `GET /api/auth/me`, user admin payloads, and auth scope consumers.
- True for: `Admin`, role `General Manager`, or `Manager` with unrestricted assignments covering all active teams.
- Do **not** treat this boolean as “the General Manager role.” Use `role === "General Manager"` for role checks.

## Role unions

- Extend `User.role` / `UserRole` with `"General Manager"`.
- User form / filters: add **General Manager** option.
- When creating/editing GM: Backend auto-assigns all active teams (no per-team checklist required).

## RouteGuards (`App.tsx`)

Allow `'General Manager'` on product routes including:

- Team Management (`/team-management`)
- Report builder (`/reports/new`, `/reports/:id/edit`) + list/preview
- Insights, Planning, Corrective Actions

## Settings (locked soft-lock)

- **Show** Settings nav for GM (same as other non-Admins).
- Soft-lock content: unlock only when `role === 'Admin'` — **not** hide + redirect.
- Backend denies Settings admin APIs for GM (`manage_users`, `manage_permissions`, `restore_data`, `view_system_metrics`, system-errors `require_role(["Admin"])`).

## In-page Admin checks

Where GM should have product access (export, report edit, actions, people visibility, etc.), include `'General Manager'` alongside Admin (and Manager where applicable). Prefer a shared helper, e.g. `canAccessSettings(role) === (role === 'Admin')`.

## Out of scope for FE from this Backend PR

- No mass-migrate of existing Managers → General Manager.
- Employee delete / assignment remain Admin-only on Backend.
