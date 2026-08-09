import type { AgentRecord, PMSAction } from '../../types';

/** Keep corrective actions inside the same employee scope as the executive dashboard filters. */
export function filterActionsByPerformanceScope(
  actions: PMSAction[],
  scopedAgents: AgentRecord[],
): PMSAction[] {
  const employeeIds = new Set(
    scopedAgents
      .map((agent) => String(agent.identity.employee_id || '').trim().toLocaleLowerCase())
      .filter(Boolean),
  );

  return actions.filter((action) =>
    employeeIds.has(String(action.employee_id || '').trim().toLocaleLowerCase())
  );
}
