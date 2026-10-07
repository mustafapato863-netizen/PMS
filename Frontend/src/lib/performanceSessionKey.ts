/** Isolate cached performance evidence by the last server-confirmed user grants. */
export function performanceSessionKey(): string {
  try {
    const saved = localStorage.getItem('pms_session_v1');
    if (!saved) return 'anonymous';
    const user = JSON.parse(saved) as Record<string, unknown>;
    if (!user || typeof user !== 'object' || Array.isArray(user)) return 'anonymous';
    const grants = (value: unknown) => Array.isArray(value)
      ? [...new Set(value.filter((item): item is string => typeof item === 'string').map((item) => item.trim()).filter(Boolean))].sort()
      : [];
    return JSON.stringify([
      user.id || user.username || 'anonymous', user.role, user.employee_id,
      grants(user.accessible_branches), grants(user.accessible_regions),
      grants(user.accessible_functions), grants(user.accessible_teams),
      user.has_unrestricted_team_access, user.is_general_manager, user.is_self_only,
    ]);
  } catch {
    return 'anonymous';
  }
}
