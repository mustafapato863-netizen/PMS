import type { User } from '../types';

/**
 * Frontend access helpers for the role model, including the General Manager role.
 *
 * Option A: "General Manager" is a **stored role string** (`User.role === 'General Manager'`),
 * aligned with the Backend constant `ROLE_GENERAL_MANAGER = "General Manager"`.
 * Access decisions key off the role string only. The boolean
 * `has_unrestricted_team_access` (renamed from `is_general_manager` in Backend PR #9)
 * means all-teams scope for Admin / GM / Manager with unrestricted assignments — it is
 * **not** the General Manager role. Use `role === "General Manager"` for role checks.
 *
 * Matrix (see docs/GENERAL_MANAGER_ROLE_DESIGN.md §4):
 * - General Manager ≈ Admin for product pages (Reports list/preview/builder, Insights,
 *   Planning, Corrective Actions).
 * - Standalone Team Management (`/team-management`): Admin and General Manager.
 * - Settings: show + soft-lock. `/settings` is unguarded, the nav link shows for every
 *   non-Agent role, and `SettingsView` renders admin panels for Admin only; General
 *   Manager gets the "Administrator access required" panel (no users / system-errors /
 *   restore / upload admin UI).
 * - Settings / upload / user-management search shortcuts stay Admin-only.
 */
export type AppRole = User['role'];

type RoleInput = string | null | undefined;

export type UnrestrictedTeamAccessUser = Pick<
  User,
  'has_unrestricted_team_access' | 'is_general_manager'
> | null | undefined;

export const ROLE_ADMIN = 'Admin' as const;
export const ROLE_GENERAL_MANAGER = 'General Manager' as const;
export const ROLE_MANAGER = 'Manager' as const;
/**
 * Read-only role scoped to one or more functions (Executive + Function Summary v1).
 * Backend is adding it; CoS default: the stored string is "Function Viewer".
 * Change it here only — every check goes through this constant.
 */
export const ROLE_FUNCTION_VIEWER = 'Function Viewer' as const;

/** Role options offered in the Admin user form / filters, in display order. */
export const USER_ROLE_OPTIONS: readonly AppRole[] = ['Admin', 'General Manager', 'Manager', 'Executive', 'Viewer', 'Agent'];

export const isAdminRole = (role: RoleInput): boolean => role === ROLE_ADMIN;

export const isGeneralManagerRole = (role: RoleInput): boolean => role === ROLE_GENERAL_MANAGER;

/** Admin or General Manager: may open the broad product pages (Reports, Insights, Planning, ...). */
export const canAccessBroadAppPages = (role: RoleInput): boolean =>
  isAdminRole(role) || isGeneralManagerRole(role);

export const isManagerRole = (role: RoleInput): boolean => role === ROLE_MANAGER;

export const isFunctionViewerRole = (role: RoleInput): boolean => role === ROLE_FUNCTION_VIEWER;

/**
 * Corrective Actions: Admin, Executive, General Manager and Manager (Mustafa,
 * Executive v1: Managers see their own team's actions; the backend already
 * scopes `/api/corrective-actions/*` to the manager's teams).
 */
export const canAccessCorrectiveActions = (role: RoleInput): boolean =>
  role === 'Executive' || isManagerRole(role) || canAccessBroadAppPages(role);

/** Planning: Admin, General Manager and Manager (team-scoped by the backend `view_plans` scope). */
export const canAccessPlanning = (role: RoleInput): boolean =>
  canAccessBroadAppPages(role) || isManagerRole(role);

/** Reports list: Admin, General Manager and Manager in the sidebar (route also admits Executive / Viewer). */
export const canSeeReportsNav = (role: RoleInput): boolean =>
  canAccessBroadAppPages(role) || isManagerRole(role);

/** Insights stays Admin / General Manager only (Mustafa, Executive v1). */
export const canAccessInsights = (role: RoleInput): boolean => canAccessBroadAppPages(role);

/** Function Summary page: Admin, General Manager and Function Viewer (limited to its functions). */
export const canAccessFunctionSummary = (role: RoleInput): boolean =>
  canAccessBroadAppPages(role) || isFunctionViewerRole(role);

/**
 * Route guard role lists (App.tsx). Kept here so the sidebar, search and the
 * guards cannot drift apart; access.test.ts pins them.
 */
export const ROUTE_ROLES = {
  insights: ['Admin', 'General Manager'],
  planning: ['Admin', 'General Manager', 'Manager'],
  correctiveActions: ['Admin', 'Executive', 'General Manager', 'Manager'],
  functionSummary: ['Admin', 'General Manager', ROLE_FUNCTION_VIEWER],
} as const satisfies Record<string, readonly AppRole[]>;

/** Which Executive Summary layout a role gets on `/executive`. */
export type ExecutiveViewForRole = 'corporate' | 'managerial' | 'function';

/**
 * Admin / GM → Corporate (full); Executive / Viewer → Corporate read-only;
 * Manager → Managerial (own team); Function Viewer → Function Summary.
 */
export const executiveViewForRole = (role: RoleInput): ExecutiveViewForRole => {
  if (isManagerRole(role)) return 'managerial';
  if (isFunctionViewerRole(role)) return 'function';
  return 'corporate';
};

/** Corporate is read-only for Executive and Viewer (no upload / manage actions). */
export const isCorporateReadOnly = (role: RoleInput): boolean => !canAccessBroadAppPages(role);

type FunctionScopedUser = { accessible_functions?: string[] | null } | null | undefined;

/** `accessible_functions` from `/api/auth/me` (Function Viewer); empty when the backend does not send it. */
export const readAccessibleFunctions = (user: FunctionScopedUser): string[] =>
  Array.isArray(user?.accessible_functions)
    ? user!.accessible_functions!.map((name) => String(name ?? '').trim()).filter(Boolean)
    : [];

/**
 * Settings *content* (panels, admin APIs) is Admin-only. Every other non-Agent role,
 * General Manager included, sees the soft-lock panel on `/settings`.
 */
export const canAccessSettingsContent = (role: RoleInput): boolean => isAdminRole(role);

/** Alias of {@link canAccessSettingsContent}, kept for existing call sites. */
export const canAccessSettings = canAccessSettingsContent;

/** Standalone Team Management page: Admin or General Manager. */
export const canAccessTeamManagement = (role: RoleInput): boolean =>
  isAdminRole(role) || isGeneralManagerRole(role);

/** Route-level check used by `RouteGuard`: a plain role allow-list. */
export const canAccessRoute = ({
  role,
  allowedRoles,
}: {
  role: RoleInput;
  allowedRoles: readonly string[];
}): boolean => Boolean(role) && allowedRoles.includes(role as string);

/** Label shown in the sidebar chip / header profile. The stored role is already human-readable. */
export const getRoleDisplayLabel = (role: RoleInput): string => role ?? '';

/**
 * Read all-teams boolean from a user payload.
 * Prefers `has_unrestricted_team_access`; falls back to legacy `is_general_manager`
 * so older backends do not blank the flag during transition.
 */
export const readHasUnrestrictedTeamAccess = (user?: UnrestrictedTeamAccessUser): boolean =>
  Boolean(user?.has_unrestricted_team_access ?? user?.is_general_manager);

/**
 * Team *scope* (not page access): Admin and General Manager see all teams.
 * `has_unrestricted_team_access` (Manager whose assignments cover every team, etc.)
 * also means all-teams scope.
 */
export const hasAllTeamsScope = (
  role: RoleInput,
  user?: UnrestrictedTeamAccessUser,
): boolean => isAdminRole(role) || isGeneralManagerRole(role) || readHasUnrestrictedTeamAccess(user);
