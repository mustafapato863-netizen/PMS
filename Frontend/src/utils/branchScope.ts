import type { AgentRecord, LocationKey } from '../types';

/**
 * Branch named by the source text of a row, in the server's fixed order
 * (`text_branch` in utils/branch_scope.py). Raw Team, Out Team, Branch, Site and
 * Area are read first; the team name only contributes Dubai, and only when the
 * raw text names no other branch.
 */
function textBranch(agent: AgentRecord): LocationKey | undefined {
  const raw = agent.raw_data || {};
  const text = ['Team', 'Out Team', 'Branch', 'Site', 'Area']
    .map((field) => String((raw as Record<string, unknown>)[field] ?? ''))
    .filter(Boolean).join(' ').toUpperCase();
  const team = String(agent.identity?.team ?? '').toUpperCase();
  if (text.includes('AJM') || text.includes('AJMAN')) return 'ajman';
  if (text.includes('SHJ') || text.includes('SHARJAH') || text.includes('SHARQA')) return 'sharjah';
  if (text.includes('DUBAI') || team.includes('DUBAI')) return 'dubai';
  if (text.includes('CLINIC')) return 'clinics';
  return undefined;
}

export const BRANCH_KEYS = ['dubai', 'sharjah', 'ajman', 'clinics'] as const;
export type BranchKey = (typeof BRANCH_KEYS)[number];

export function isBranchKey(value: string | null | undefined): value is BranchKey {
  const normalized = String(value ?? '').trim().toLowerCase();
  return (BRANCH_KEYS as readonly string[]).includes(normalized);
}

/**
 * The one branch rule (utils/branch_scope.py `record_matches_branch`): the stored
 * branch_key when the row has one; otherwise the source text; otherwise the row's
 * geo bookings or attendance for that branch.
 */
export function agentMatchesLocation(agent: AgentRecord, location: LocationKey): boolean {
  if (location === 'all') return true;
  const stored = agent.branch_key?.trim().toLowerCase();
  if (stored) return stored === location;
  const explicit = textBranch(agent);
  if (explicit) return explicit === location;
  return (agent.geo?.bookings?.[location] || 0) > 0 || (agent.geo?.attended?.[location] || 0) > 0;
}

function isAttendanceKpi(kpi: { kpi_key?: string | null; label?: string | null }): boolean {
  const key = String(kpi.kpi_key ?? '').trim().toLowerCase();
  const label = String(kpi.label ?? '').trim().toLowerCase();
  return key === 'attendance' || key.includes('attend') || label.includes('attend');
}

/**
 * Mirrors Backend `utils/branch_scope.py#project_record_for_branch`.
 *
 * For multi-branch Call Center records (Inbound / Outbound) whose attendance is
 * tracked per branch in `geo.bookings` and `geo.attended`, selecting a branch
 * projects Attendance Rate to `attended[branch] / bookings[branch]`, recomputes
 * its achievement ratio and contribution, and updates the agent's overall score.
 * Records without branch-partitioned geo activity are returned unchanged.
 */
export function projectAgentForBranch(
  agent: AgentRecord,
  branch: string | null | undefined,
): AgentRecord {
  const wanted = String(branch ?? '').trim().toLowerCase();
  if (!isBranchKey(wanted)) return agent;

  const bBookingsRaw = agent.geo?.bookings?.[wanted];
  const bAttendedRaw = agent.geo?.attended?.[wanted];
  const hasBookings = typeof bBookingsRaw === 'number' && Number.isFinite(bBookingsRaw);
  const hasAttended = typeof bAttendedRaw === 'number' && Number.isFinite(bAttendedRaw);
  if (!hasBookings && !hasAttended) return agent;

  const bookingsVal = Math.max(hasBookings ? bBookingsRaw : 0, 0);
  const attendedVal = Math.max(hasAttended ? bAttendedRaw : 0, 0);
  if (bookingsVal <= 0 && attendedVal <= 0) return agent;

  const kpis = agent.kpi_values;
  if (!Array.isArray(kpis) || !kpis.some(isAttendanceKpi)) return agent;

  const newActual = bookingsVal > 0 ? attendedVal / bookingsVal : 0;

  const projectedKpis = kpis.map((kpi) => {
    if (!isAttendanceKpi(kpi)) return { ...kpi };
    const target = Number.isFinite(kpi.target_value) && kpi.target_value > 0 ? kpi.target_value : 0.65;
    const rawRatio = target > 0 ? newActual / target : 1.0;
    const ratio = kpi.cap_achievement === false
      ? Math.max(rawRatio, 0)
      : Math.min(Math.max(rawRatio, 0), 1.0);
    const weight = Number.isFinite(kpi.weight_applied) ? kpi.weight_applied : 0.7;
    const contribution = ratio * weight;
    return {
      ...kpi,
      actual_value: newActual,
      achievement_ratio: ratio,
      contribution,
    };
  });

  const totalContribution = projectedKpis.reduce((sum, kpi) => {
    const c = Number(kpi.contribution);
    return Number.isFinite(c) ? sum + c : sum;
  }, 0);
  const newScorePct = Math.round(totalContribution * 10000) / 100;
  const prevScore = Number(agent.evaluation?.score);
  const usesRatioScale = Number.isFinite(prevScore) && prevScore > 0 && prevScore <= 1.5;
  const projectedEvalScore = usesRatioScale ? totalContribution : newScorePct;

  const nextRawData = agent.raw_data ? { ...agent.raw_data } : undefined;
  if (nextRawData) {
    if ('A.Attend%' in nextRawData) nextRawData['A.Attend%'] = String(newActual);
    if ('PerformanceScore' in nextRawData) nextRawData['PerformanceScore'] = String(newScorePct);
  }

  return {
    ...agent,
    branch_key: wanted,
    actual: agent.actual
      ? { ...agent.actual, attend_rate: newActual }
      : agent.actual,
    evaluation: agent.evaluation
      ? { ...agent.evaluation, score: projectedEvalScore }
      : agent.evaluation,
    kpi_values: projectedKpis,
    raw_data: nextRawData,
  };
}
