import type { User } from '../types';

/**
 * Frontend access helpers for the role model, including the General Manager role.
 *
 * Option A: "General Manager" is a **stored role string** (`User.role === 'General Manager'`),
 * aligned with the Backend constant `ROLE_GENERAL_MANAGER = "General Manager"`.
 * Access decisions key off the role string only. The legacy `is_general_manager`
 * flag (Admin, or Manager whose assignments cover all teams) stays on the User type
 * for API compatibility and team scoping, but does not grant these pages.
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

export const ROLE_ADMIN = 'Admin' as const;
export const ROLE_GENERAL_MANAGER = 'General Manager' as const;

/** Role options offered in the Admin user form / filters, in display order. */
export const USER_ROLE_OPTIONS: readonly AppRole[] = ['Admin', 'General Manager', 'Manager', 'Executive', 'Viewer', 'Agent'];

export const isAdminRole = (role: RoleInput): boolean => role === ROLE_ADMIN;

export const isGeneralManagerRole = (role: RoleInput): boolean => role === ROLE_GENERAL_MANAGER;

/** Admin or General Manager: may open the broad product pages (Reports, Insights, Planning, ...). */
export const canAccessBroadAppPages = (role: RoleInput): boolean =>
  isAdminRole(role) || isGeneralManagerRole(role);

/** Corrective Actions review: Admin, Executive or General Manager. */
export const canAccessCorrectiveActions = (role: RoleInput): boolean =>
  role === 'Executive' || canAccessBroadAppPages(role);

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
 * Team *scope* (not page access): Admin and General Manager see all teams. The legacy
 * `is_general_manager` flag (Manager whose assignments cover every team) also means
 * all-teams scope, so it is honoured here for API compatibility.
 */
export const hasAllTeamsScope = (
  role: RoleInput,
  user?: Pick<User, 'is_general_manager'> | null,
): boolean => isAdminRole(role) || isGeneralManagerRole(role) || Boolean(user?.is_general_manager);
