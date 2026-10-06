/**
 * Compose the Executive / Function Summary payload from data that already
 * exists, while `GET /api/executive/summary` is being built (API_NEEDS.md).
 *
 * Inputs are the authorized performance records the existing dashboards use
 * (`usePerformanceData`: scoped records API or legacy `/api/performance`), the
 * Insights drivers (optional) and corrective-action follow-up (optional).
 * Anything that cannot be derived honestly is left `null` and listed in
 * `meta.unavailable`, so the UI hides or softens it instead of inventing it.
 */
import { GRADE_CLASSES, getGradeClassOrNull, type GradeClass } from '../../constants/grades';
import { canonicalTeamName } from '../../types';
import type { AgentRecord } from '../../types';
import { normalizePerformanceScore } from '../../utils/kpiScore';
import type { InsightDriver, InsightItem, InsightTrendStatus } from '../insights/types';
import type { TeamFunctionMap } from '../insights/filterCascade';
import { teamBelongsToFunction } from '../insights/filterCascade';
import { EXECUTIVE_FUNCTIONS, executiveFunctionForTeam } from './functions';
import type {
  ExecutiveActionItem,
  ExecutiveCorrectiveActions,
  ExecutiveDriver,
  ExecutiveFunction,
  ExecutiveFunctionCard,
  ExecutiveGradeDistribution,
  ExecutiveKpiRow,
  ExecutiveLevel,
  ExecutivePeople,
  ExecutivePeriod,
  ExecutivePerson,
  ExecutiveRegion,
  ExecutiveSection,
  ExecutiveSummary,
  ExecutiveTeam,
  ExecutiveTeamFlag,
  ExecutiveTrendPoint,
  ExecutiveView,
} from './types';

export const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const TARGET = 100;
const REGION_LABELS: Record<string, string> = { EGY: 'Offshore Egypt', UAE: 'UAE Region' };

/** One employee-month, normalised from `AgentRecord`. */
export interface ExecRecord {
  employeeId: string;
  name: string;
  team: string;
  region: string | null;
  position: string | null;
  level: string;
  period: ExecutivePeriod;
  score: number;
  kpis: NonNullable<AgentRecord['kpi_values']>;
}

export function periodOf(year: number, month: string): ExecutivePeriod {
  const index = MONTHS.indexOf(month);
  return { year, month, key: `${year}-${String(index + 1).padStart(2, '0')}` };
}

export function periodFromKey(key: string): ExecutivePeriod | null {
  const match = /^(\d{4})-(\d{2})$/.exec(key || '');
  if (!match) return null;
  const month = MONTHS[Number(match[2]) - 1];
  return month ? periodOf(Number(match[1]), month) : null;
}

export function formatPeriod(period: ExecutivePeriod | null | undefined): string {
  return period ? `${period.month} ${period.year}` : '';
}

export function toExecRecords(agents: AgentRecord[], fallbackYear = new Date().getFullYear()): ExecRecord[] {
  return agents.flatMap((agent) => {
    const month = agent.identity?.month;
    const team = canonicalTeamName(agent.identity?.team);
    if (!month || !MONTHS.includes(month) || !team) return [];
    if ((agent.identity.name || '').trim().toLowerCase() === 'total') return [];
    const raw = Number(agent.evaluation?.score);
    if (!Number.isFinite(raw)) return [];
    return [{
      employeeId: String(agent.identity.employee_id || agent.identity.name),
      name: agent.identity.name,
      team,
      region: (agent.region || agent.identity.region || null) as string | null,
      position: (agent.position || agent.identity.position || null) as string | null,
      level: agent.performance_level || 'Employee',
      period: periodOf(agent.year || fallbackYear, month),
      score: normalizePerformanceScore(raw),
      kpis: agent.kpi_values || [],
    }];
  });
}

const round1 = (value: number) => Math.round(value * 10) / 10;
const mean = (values: number[]) => (values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null);
const r1 = (value: number | null) => (value === null ? null : round1(value));
const diff = (current: number | null, previous: number | null) => (current === null || previous === null ? null : round1(current - previous));

function scoreOf(records: ExecRecord[]): number | null {
  return r1(mean(records.map((record) => record.score)));
}

function employeesOf(records: ExecRecord[]): number {
  return new Set(records.map((record) => record.employeeId)).size;
}

function inPeriod(records: ExecRecord[], period: ExecutivePeriod | null) {
  return period ? records.filter((record) => record.period.key === period.key) : [];
}

/** Six calendar months ending at `period` (oldest first). */
export function trailingPeriods(period: ExecutivePeriod, count = 6): ExecutivePeriod[] {
  const absolute = period.year * 12 + MONTHS.indexOf(period.month);
  return Array.from({ length: count }, (_, index) => {
    const value = absolute - (count - 1 - index);
    return periodOf(Math.floor(value / 12), MONTHS[value % 12]);
  });
}

function trendOf(records: ExecRecord[], period: ExecutivePeriod) {
  return trailingPeriods(period).map((point) => ({ period: point, score: scoreOf(inPeriod(records, point)) }));
}

/** Consecutive month-over-month falls ending at the last point (needs measured adjacent months). */
export function fallingMonths(trend: Array<{ score: number | null }>): number {
  let count = 0;
  for (let index = trend.length - 1; index > 0; index -= 1) {
    const current = trend[index].score;
    const previous = trend[index - 1].score;
    if (current === null || previous === null || current >= previous) break;
    count += 1;
  }
  return count;
}

function emptyCounts(): Record<GradeClass, number> {
  return { A: 0, B: 0, C: 0, D: 0, E: 0 };
}

/** Grade mix with the live 95/90/80/70 palette, computed from scores (CoS). */
export function gradeDistribution(current: ExecRecord[], previous: ExecRecord[]): ExecutiveGradeDistribution | null {
  if (!current.length) return null;
  const counts = emptyCounts();
  current.forEach((record) => { counts[getGradeClassOrNull(record.score) ?? 'E'] += 1; });
  const total = current.length;
  const percents = emptyCounts();
  GRADE_CLASSES.forEach((grade) => { percents[grade] = round1((counts[grade] / total) * 100); });
  let previousCounts: Record<GradeClass, number> | null = null;
  let movement: Record<GradeClass, number> | null = null;
  if (previous.length) {
    const prev = emptyCounts();
    previous.forEach((record) => { prev[getGradeClassOrNull(record.score) ?? 'E'] += 1; });
    previousCounts = prev;
    movement = emptyCounts();
    GRADE_CLASSES.forEach((grade) => { movement![grade] = counts[grade] - prev[grade]; });
  }
  return { total, counts, percents, previous_counts: previousCounts, movement };
}

const TOLERANCE = 1e-9;

function trendStatusOf(changeValue: number | null): InsightTrendStatus | null {
  if (changeValue === null) return null;
  if (Math.abs(changeValue) < 0.05) return 'stable';
  return changeValue > 0 ? 'improving' : 'declining';
}

/** Direction-aware KPI rows (worst achievement first) from per-employee `kpi_values`. */
export function kpiRows(current: ExecRecord[], previous: ExecRecord[]): ExecutiveKpiRow[] {
  type Bucket = { label: string; unit: string | null; direction: string | null; actual: number[]; target: number[]; weight: number[]; achievement: number[]; teams: Set<string> };
  const collect = (records: ExecRecord[]) => {
    const buckets = new Map<string, Bucket>();
    records.forEach((record) => record.kpis.forEach((kpi) => {
      if (!kpi?.kpi_key) return;
      const bucket = buckets.get(kpi.kpi_key) ?? {
        label: kpi.label || kpi.kpi_key, unit: kpi.unit ?? null, direction: kpi.direction ?? null,
        actual: [], target: [], weight: [], achievement: [], teams: new Set<string>(),
      };
      if (Number.isFinite(kpi.actual_value)) bucket.actual.push(Number(kpi.actual_value));
      if (Number.isFinite(kpi.target_value)) bucket.target.push(Number(kpi.target_value));
      if (Number.isFinite(kpi.weight_applied)) bucket.weight.push(Number(kpi.weight_applied));
      if (Number.isFinite(kpi.achievement_ratio)) bucket.achievement.push(Math.min(Math.max(Number(kpi.achievement_ratio), 0), 1) * 100);
      bucket.teams.add(record.team);
      buckets.set(kpi.kpi_key, bucket);
    }));
    return buckets;
  };
  const now = collect(current);
  const before = collect(previous);
  const rows: ExecutiveKpiRow[] = [];
  now.forEach((bucket, key) => {
    const actual = mean(bucket.actual);
    const target = mean(bucket.target);
    const previousActual = before.has(key) ? mean(before.get(key)!.actual) : null;
    const direction = String(bucket.direction ?? '').toLowerCase();
    const lower = direction.startsWith('lower');
    const known = lower || direction.startsWith('higher');
    const rawGap = actual !== null && target !== null ? actual - target : null;
    const rawChange = actual !== null && previousActual !== null ? actual - previousActual : null;
    const gapValue = rawGap === null || !known ? null : (lower ? -rawGap : rawGap);
    const changeValue = rawChange === null || !known ? null : (lower ? -rawChange : rawChange);
    const achievement = mean(bucket.achievement);
    rows.push({
      kpi_key: key,
      kpi_label: bucket.label,
      kpi_direction: bucket.direction,
      unit: bucket.unit,
      actual: actual === null ? null : Number(actual.toFixed(2)),
      target: target === null ? null : Number(target.toFixed(2)),
      previous_actual: previousActual === null ? null : Number(previousActual.toFixed(2)),
      gap_value: gapValue === null ? null : Number(gapValue.toFixed(2)),
      raw_gap: rawGap === null ? null : Number(rawGap.toFixed(2)),
      raw_change: rawChange === null ? null : Number(rawChange.toFixed(2)),
      change_value: changeValue === null ? null : Number(changeValue.toFixed(2)),
      trend_status: trendStatusOf(changeValue),
      weight: mean(bucket.weight),
      achievement_percent: r1(achievement),
      grade: getGradeClassOrNull(achievement),
      target_status: gapValue === null ? null : (gapValue >= -TOLERANCE ? 'met' : 'missed'),
      teams: [...bucket.teams].sort(),
    });
  });
  return rows.sort((left, right) => (left.achievement_percent ?? 101) - (right.achievement_percent ?? 101) || left.kpi_label.localeCompare(right.kpi_label));
}

function levels(current: ExecRecord[], previous: ExecRecord[]): ExecutiveLevel[] {
  const groups = new Map<string, ExecRecord[]>();
  current.forEach((record) => {
    const key = record.position || 'Unassigned';
    groups.set(key, [...(groups.get(key) ?? []), record]);
  });
  return [...groups.entries()].map(([level, records]) => {
    const score = scoreOf(records);
    const previousScore = scoreOf(previous.filter((record) => (record.position || 'Unassigned') === level));
    return { level, employees: employeesOf(records), score, previous_score: previousScore, change: diff(score, previousScore), grade: getGradeClassOrNull(score) };
  }).sort((left, right) => (left.score ?? 0) - (right.score ?? 0));
}

function people(current: ExecRecord[], previous: ExecRecord[]): ExecutivePeople {
  const previousByEmployee = new Map(previous.map((record) => [record.employeeId, record.score]));
  const persons: ExecutivePerson[] = current.map((record) => {
    const previousScore = previousByEmployee.get(record.employeeId);
    const score = round1(record.score);
    return {
      employee_id: record.employeeId,
      name: record.name,
      position: record.position,
      score,
      previous_score: previousScore === undefined ? null : round1(previousScore),
      change: previousScore === undefined ? null : round1(record.score - previousScore),
      grade: getGradeClassOrNull(record.score),
    };
  });
  const byName = (left: ExecutivePerson, right: ExecutivePerson) => left.name.localeCompare(right.name);
  return {
    bottom: [...persons].sort((l, r) => (l.score ?? 0) - (r.score ?? 0) || byName(l, r)).slice(0, 4),
    biggest_drops: persons.filter((person) => person.change !== null && person.change < 0)
      .sort((l, r) => (l.change ?? 0) - (r.change ?? 0) || byName(l, r)).slice(0, 4),
    top: [...persons].sort((l, r) => (r.score ?? 0) - (l.score ?? 0) || byName(l, r)).slice(0, 3),
  };
}

function teamsOf(
  scoped: ExecRecord[],
  effective: ExecutivePeriod,
  previous: ExecutivePeriod | null,
  teamFunctions: TeamFunctionMap | undefined,
): ExecutiveTeam[] {
  const names = [...new Set(inPeriod(scoped, effective).map((record) => record.team))];
  const base = names.map((team) => {
    const records = scoped.filter((record) => record.team === team);
    const current = inPeriod(records, effective);
    const score = scoreOf(current);
    const previousScore = scoreOf(inPeriod(records, previous));
    const trend = trendOf(records, effective);
    const worstKpi = kpiRows(current, inPeriod(records, previous))[0];
    return {
      team,
      function: executiveFunctionForTeam(team, teamFunctions),
      regions: [...new Set(current.map((record) => record.region).filter((value): value is string => Boolean(value)))].sort(),
      employees: employeesOf(current),
      score,
      previous_score: previousScore,
      change: diff(score, previousScore),
      gap: score === null ? null : round1(score - TARGET),
      grade: getGradeClassOrNull(score),
      trend,
      vs_function_avg: null as number | null,
      rank_in_function: null as number | null,
      flags: [] as ExecutiveTeamFlag[],
      flag_detail: worstKpi && worstKpi.achievement_percent !== null && worstKpi.achievement_percent < 100 ? {
        kpi_key: worstKpi.kpi_key,
        kpi_label: worstKpi.kpi_label,
        kpi_direction: worstKpi.kpi_direction,
        current_value: worstKpi.actual,
        target_value: worstKpi.target,
        unit: worstKpi.unit,
        text: `${worstKpi.kpi_label} at ${worstKpi.achievement_percent}% of target`,
      } : null,
    };
  });
  const byFunction = new Map<string, typeof base>();
  base.forEach((team) => {
    if (!team.function) return;
    byFunction.set(team.function, [...(byFunction.get(team.function) ?? []), team]);
  });
  byFunction.forEach((teams, name) => {
    const functionScore = scoreOf(inPeriod(scoped.filter((record) => executiveFunctionForTeam(record.team, teamFunctions) === name), effective));
    const ranked = [...teams].sort((l, r) => (r.score ?? 0) - (l.score ?? 0));
    ranked.forEach((team, index) => {
      team.rank_in_function = index + 1;
      team.vs_function_avg = diff(team.score, functionScore);
      if (team.vs_function_avg !== null && team.vs_function_avg < 0) team.flags.push('below_function_avg');
    });
    if (ranked.length > 1) ranked[ranked.length - 1].flags.push('lowest_in_function');
  });
  base.forEach((team) => {
    if (team.grade === 'D') team.flags.unshift('grade_d');
    if (team.grade === 'E') team.flags.unshift('grade_e');
    if (fallingMonths(team.trend) >= 2) team.flags.push('falling_2_months');
  });
  return base.sort((l, r) => (l.score ?? 0) - (r.score ?? 0));
}

export function isAtRisk(team: ExecutiveTeam) {
  return team.flags.some((flag) => flag === 'grade_d' || flag === 'grade_e' || flag === 'falling_2_months');
}

function functionCards(scoped: ExecRecord[], effective: ExecutivePeriod, previous: ExecutivePeriod | null, teamFunctions?: TeamFunctionMap): ExecutiveFunctionCard[] {
  const cards = EXECUTIVE_FUNCTIONS.flatMap((name): ExecutiveFunctionCard[] => {
    const records = scoped.filter((record) => executiveFunctionForTeam(record.team, teamFunctions) === name);
    const current = inPeriod(records, effective);
    if (!current.length) return [];
    const score = scoreOf(current);
    const previousScore = scoreOf(inPeriod(records, previous));
    const trend = trendOf(records, effective);
    return [{
      function: name,
      score,
      previous_score: previousScore,
      change: diff(score, previousScore),
      gap: score === null ? null : round1(score - TARGET),
      grade: getGradeClassOrNull(score),
      employees: employeesOf(current),
      teams: [...new Set(current.map((record) => record.team))].sort(),
      regions: [...new Set(current.map((record) => record.region).filter((value): value is string => Boolean(value)))].sort(),
      falling_months: fallingMonths(trend),
      trend,
      is_most_improved: false,
    }];
  });
  const improved = cards.filter((card) => (card.change ?? 0) > 0).sort((l, r) => (r.change ?? 0) - (l.change ?? 0))[0];
  if (improved) improved.is_most_improved = true;
  return cards;
}

function regions(current: ExecRecord[], previous: ExecRecord[]): ExecutiveRegion[] {
  const names = [...new Set(current.map((record) => record.region).filter((value): value is string => Boolean(value)))];
  const totalEmployees = employeesOf(current);
  const raw = names.map((region) => {
    const records = current.filter((record) => record.region === region);
    const score = scoreOf(records);
    const previousScore = scoreOf(previous.filter((record) => record.region === region));
    const employees = employeesOf(records);
    const teams = [...new Set(records.map((record) => record.team))].sort();
    return {
      region,
      label: REGION_LABELS[region] ?? region,
      score,
      previous_score: previousScore,
      change: diff(score, previousScore),
      gap: score === null ? null : round1(score - TARGET),
      grade: getGradeClassOrNull(score),
      employees,
      teams_count: teams.length,
      teams,
      gap_share_percent: null as number | null,
      headcount_share_percent: totalEmployees ? round1((employees / totalEmployees) * 100) : null,
      weight: score === null ? 0 : Math.max(TARGET - score, 0) * employees,
    };
  });
  const totalWeight = raw.reduce((sum, item) => sum + item.weight, 0);
  return raw.map(({ weight, ...item }) => ({ ...item, gap_share_percent: totalWeight ? round1((weight / totalWeight) * 100) : null }))
    .sort((l, r) => (l.region === 'EGY' ? -1 : r.region === 'EGY' ? 1 : l.region.localeCompare(r.region)));
}

/* ── Drivers (from the Insights workspace) ── */

function splitScope(scope: string): { team: string | null } {
  const [team] = String(scope || '').split(' · ');
  return { team: team?.trim() || null };
}

export function mapDrivers(
  drivers: Array<InsightDriver & { weighted_gap_points?: number | null; impact_change_points?: number | null }>,
  items: InsightItem[],
  teamFunctions?: TeamFunctionMap,
  limit = 3,
): { negative: ExecutiveDriver[]; positive: ExecutiveDriver[]; metric: 'weighted_gap' | 'contribution_change'; hasWeightedGap: boolean } {
  const itemById = new Map(items.map((item) => [item.id, item]));
  // Drivers arrive per team · position; merge them per KPI × team.
  const merged = new Map<string, ExecutiveDriver>();
  drivers.forEach((driver) => {
    const item = itemById.get(driver.insight_id);
    const team = item?.team ?? splitScope(driver.scope).team;
    const key = `${item?.kpi_key ?? driver.driver}::${team ?? ''}`;
    const detail = item?.detail;
    const existing = merged.get(key);
    const add = (left: number | null | undefined, right: number | null | undefined) => (
      left == null && right == null ? null : (left ?? 0) + (right ?? 0)
    );
    if (existing) {
      existing.impact_points = add(existing.impact_points, driver.impact_points);
      existing.weighted_gap_points = add(existing.weighted_gap_points, driver.weighted_gap_points);
      existing.impact_change_points = add(existing.impact_change_points, driver.impact_change_points);
      return;
    }
    merged.set(key, {
      kpi_key: item?.kpi_key ?? null,
      kpi_label: driver.driver,
      team,
      function: executiveFunctionForTeam(team, teamFunctions),
      kpi_direction: driver.kpi_direction ?? detail?.direction ?? null,
      unit: detail?.unit ?? null,
      current_value: detail?.current_value ?? null,
      previous_value: detail?.previous_value ?? null,
      raw_change: detail?.raw_change ?? (detail?.current_value != null && detail?.previous_value != null ? detail.current_value - detail.previous_value : null),
      change_value: detail?.change_value ?? null,
      trend_status: detail?.trend_status ?? null,
      gap_value: detail?.gap_value ?? null,
      achievement_percent: detail?.achievement_percent ?? null,
      weight: (item as (InsightItem & { weight?: number | null }) | undefined)?.weight ?? null,
      impact_points: driver.impact_points ?? null,
      weighted_gap_points: driver.weighted_gap_points ?? null,
      impact_change_points: driver.impact_change_points ?? null,
      insight_id: driver.insight_id,
    });
  });
  const all = [...merged.values()];
  const hasWeightedGap = all.some((driver) => typeof driver.weighted_gap_points === 'number');
  const hasChange = all.some((driver) => typeof driver.impact_change_points === 'number');
  const negativeValue = (driver: ExecutiveDriver) => (hasWeightedGap ? driver.weighted_gap_points : driver.impact_points) ?? 0;
  const positiveValue = (driver: ExecutiveDriver) => (hasChange ? driver.impact_change_points : driver.impact_points) ?? 0;
  return {
    negative: all.filter((driver) => negativeValue(driver) < 0).sort((l, r) => negativeValue(l) - negativeValue(r)).slice(0, limit),
    positive: all.filter((driver) => positiveValue(driver) > 0).sort((l, r) => positiveValue(r) - positiveValue(l)).slice(0, limit),
    metric: hasWeightedGap ? 'weighted_gap' : 'contribution_change',
    hasWeightedGap,
  };
}

/* ── Corrective actions (from /api/corrective-actions/follow-up) ── */

export interface FollowUpAction {
  id: string | number;
  title?: string | null;
  action_type?: string | null;
  description?: string | null;
  team?: string | null;
  region?: string | null;
  employee_name?: string | null;
  owner?: { id: string; name: string } | null;
  due_date?: string | null;
  status?: string | null;
  follow_up_state?: string | null;
  completed_at?: string | null;
}

export function localIsoDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

const OPEN_STATUSES = new Set(['Open', 'In Progress']);

/** Corrective-action summary; "Due this week" counts from today (Mustafa): today ≤ due ≤ today + 6. */
export function summarizeActions(actions: FollowUpAction[], today: Date, effective: ExecutivePeriod | null): ExecutiveCorrectiveActions {
  const todayIso = localIsoDate(today);
  const weekEnd = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 6);
  const weekEndIso = localIsoDate(weekEnd);
  const isOpen = (action: FollowUpAction) => OPEN_STATUSES.has(String(action.status || ''));
  const dueDate = (action: FollowUpAction) => (action.due_date ? String(action.due_date).slice(0, 10) : null);
  const overdue = (action: FollowUpAction) => isOpen(action) && (action.follow_up_state === 'overdue' || (dueDate(action) !== null && dueDate(action)! < todayIso));
  const dueThisWeek = (action: FollowUpAction) => isOpen(action) && !overdue(action) && dueDate(action) !== null && dueDate(action)! >= todayIso && dueDate(action)! <= weekEndIso;
  const closedInMonth = effective
    ? actions.filter((action) => action.status === 'Completed' && String(action.completed_at || '').slice(0, 7) === effective.key).length
    : null;
  const rank = (action: FollowUpAction) => (overdue(action) ? 0 : dueThisWeek(action) ? 1 : isOpen(action) ? 2 : 3);
  const items: ExecutiveActionItem[] = actions.filter(isOpen)
    .sort((l, r) => rank(l) - rank(r) || String(dueDate(l) ?? '9999').localeCompare(String(dueDate(r) ?? '9999')))
    .slice(0, 4)
    .map((action) => ({
      id: String(action.id),
      title: action.title || action.action_type || action.description || 'Corrective action',
      team: action.team ?? null,
      region: action.region ?? null,
      employee_name: action.employee_name ?? null,
      owner: action.owner ?? null,
      due_date: dueDate(action),
      status: String(action.status || ''),
      follow_up_state: overdue(action) ? 'overdue' : dueThisWeek(action) ? 'due_this_week' : (action.follow_up_state ?? null),
    }));
  return {
    summary: {
      as_of: todayIso,
      open: actions.filter(isOpen).length,
      overdue: actions.filter(overdue).length,
      due_this_week: actions.filter(dueThisWeek).length,
      closed_in_month: closedInMonth,
    },
    actions: items,
  };
}

/* ── Composition ── */

export interface ComposeInput {
  view: ExecutiveView;
  role: string;
  records: ExecRecord[];
  filters: { region?: string; teamFunction?: string; team?: string; performanceLevel?: string };
  requestedPeriodKey?: string | null;
  /** Managerial: the manager's team; Function view: the selected function. */
  team?: string | null;
  functionName?: ExecutiveFunction | null;
  accessibleFunctions?: string[];
  teamFunctions?: TeamFunctionMap;
  drivers?: { drivers: InsightDriver[]; items: InsightItem[] } | null;
  actions?: FollowUpAction[] | null;
  /** Records outside the viewer's scope for aggregate comparisons (never available client-side for Manager / Function Viewer). */
  comparisonRecords?: ExecRecord[] | null;
  today: Date;
}

function applyFilters(records: ExecRecord[], input: ComposeInput, teamFunctions?: TeamFunctionMap) {
  const { region, teamFunction, team, performanceLevel } = input.filters;
  return records.filter((record) => (
    (!region || record.region === region)
    && (!performanceLevel || record.level === performanceLevel)
    && (!teamFunction || (input.view === 'function'
      ? executiveFunctionForTeam(record.team, teamFunctions) === teamFunction
      : teamBelongsToFunction(record.team, teamFunction, teamFunctions)))
    && (!team || record.team === canonicalTeamName(team))
  ));
}

export function composeExecutiveSummary(input: ComposeInput): ExecutiveSummary {
  const { view, teamFunctions } = input;
  const unavailable = new Set<ExecutiveSection>(['upload_meta']);
  const scopeFilters = { ...input.filters };
  if (view === 'managerial' && input.team) scopeFilters.team = input.team;
  if (view === 'function' && input.functionName) scopeFilters.teamFunction = input.functionName;
  const scoped = applyFilters(input.records, { ...input, filters: scopeFilters }, teamFunctions);

  const periods = [...new Map(scoped.map((record) => [record.period.key, record.period])).values()]
    .sort((l, r) => r.key.localeCompare(l.key));
  const requested = input.requestedPeriodKey ? periodFromKey(input.requestedPeriodKey) : null;
  const effective = requested && periods.some((period) => period.key === requested.key) ? requested : periods[0] ?? null;
  const fallbackApplied = Boolean(requested && effective && requested.key !== effective.key);
  const previous = effective ? periods.find((period) => period.key < effective.key) ?? null : null;

  const current = inPeriod(scoped, effective);
  const before = inPeriod(scoped, previous);
  const score = scoreOf(current);
  const previousScore = scoreOf(before);

  const teams = effective ? teamsOf(scoped, effective, previous, teamFunctions) : [];
  const functions = effective ? functionCards(scoped, effective, previous, teamFunctions) : [];
  const comparison = input.comparisonRecords && effective
    ? applyFilters(input.comparisonRecords, { ...input, filters: { region: input.filters.region, performanceLevel: input.filters.performanceLevel } }, teamFunctions)
    : null;

  // Comparison line: managerial = function average, function = company average.
  let comparisonBlock: ExecutiveSummary['hero']['comparison'] = null;
  let comparisonTrend: Array<number | null> | null = null;
  if (view === 'managerial') {
    const fn = executiveFunctionForTeam(input.team, teamFunctions);
    if (fn && comparison) {
      const fnRecords = comparison.filter((record) => executiveFunctionForTeam(record.team, teamFunctions) === fn);
      const fnScore = scoreOf(inPeriod(fnRecords, effective));
      comparisonBlock = { label: `${fn} average`, score: fnScore, difference: diff(score, fnScore) };
      comparisonTrend = effective ? trendOf(fnRecords, effective).map((point) => point.score) : null;
    } else {
      unavailable.add('function_average');
    }
  }
  if (view === 'function') {
    if (comparison) {
      const companyScore = scoreOf(inPeriod(comparison, effective));
      comparisonBlock = { label: 'Company average', score: companyScore, difference: diff(score, companyScore) };
      comparisonTrend = effective ? trendOf(comparison, effective).map((point) => point.score) : null;
    } else {
      unavailable.add('company_average');
    }
  }

  const trend: ExecutiveTrendPoint[] = effective
    ? trendOf(scoped, effective).map((point, index) => ({ ...point, comparison_score: comparisonTrend?.[index] ?? null, target: TARGET }))
    : [];

  const rawSplit = input.drivers
    ? mapDrivers(input.drivers.drivers, input.drivers.items, teamFunctions, view === 'function' ? Number.POSITIVE_INFINITY : 3)
    : null;
  // Function view: Insights' function filter is overlapping, Executive membership is disjoint.
  const driverSplit = rawSplit && view === 'function' && input.functionName
    ? {
      ...rawSplit,
      negative: rawSplit.negative.filter((driver) => driver.function === input.functionName).slice(0, 3),
      positive: rawSplit.positive.filter((driver) => driver.function === input.functionName).slice(0, 3),
    }
    : rawSplit;
  if (!driverSplit) unavailable.add('drivers');
  else if (!driverSplit.hasWeightedGap) unavailable.add('drivers_weighted_gap');

  const kpis = kpiRows(current, before);
  if (!kpis.length) unavailable.add('kpis');
  const grades = gradeDistribution(current, before);
  if (!grades) unavailable.add('grade_mix');
  const actions = input.actions ? summarizeActions(input.actions, input.today, effective) : null;
  if (!actions) unavailable.add('corrective_actions');

  const mostImproved = functions.find((card) => card.is_most_improved) ?? null;
  const lowestTeam = view === 'function' ? teams.find((team) => team.flags.includes('lowest_in_function')) ?? null : null;
  const worstFunction = [...functions].sort((l, r) => (
    (Math.max(TARGET - (r.score ?? TARGET), 0) * r.employees) - (Math.max(TARGET - (l.score ?? TARGET), 0) * l.employees)
  ))[0] ?? null;
  const drag = driverSplit?.negative.find((driver) => !worstFunction || driver.function === worstFunction.function) ?? driverSplit?.negative[0] ?? null;

  const label = view === 'managerial' ? (input.team ?? 'Your team') : view === 'function' ? (input.functionName ?? 'Function') : 'Company';
  return {
    period: {
      requested,
      effective,
      previous,
      fallback_applied: fallbackApplied,
      notice: fallbackApplied && requested && effective
        ? `No performance data for ${formatPeriod(requested)} yet — showing ${formatPeriod(effective)}, the latest month with data.`
        : null,
    },
    data_status: { has_data: periods.length > 0, last_upload: null, effective_uploaded_at: null },
    scope: {
      view,
      role: input.role,
      locked: { region: view === 'managerial', function: view === 'managerial', team: view === 'managerial' },
      team: view === 'managerial' ? input.team ?? null : input.filters.team ?? null,
      function: view === 'function' ? input.functionName ?? null : (view === 'managerial' ? executiveFunctionForTeam(input.team, teamFunctions) : input.filters.teamFunction ?? null),
      region: view === 'managerial' ? ([...new Set(current.map((record) => record.region).filter(Boolean))][0] ?? null) : input.filters.region ?? null,
      accessible_functions: input.accessibleFunctions ?? [...EXECUTIVE_FUNCTIONS],
    },
    hero: {
      label,
      score,
      previous_score: previousScore,
      change: diff(score, previousScore),
      gap: score === null ? null : round1(score - TARGET),
      target: TARGET,
      grade: getGradeClassOrNull(score),
      employees: employeesOf(current),
      teams_count: new Set(current.map((record) => record.team)).size,
      functions_count: functions.length,
      story: {
        headline: null,
        biggest_drag: worstFunction ? { function: worstFunction.function, team: drag?.team ?? null, kpi_key: drag?.kpi_key ?? null, kpi_label: drag?.kpi_label ?? null } : null,
        most_improved: mostImproved && mostImproved.change !== null ? { function: mostImproved.function, change: mostImproved.change } : null,
      },
      comparison: comparisonBlock,
    },
    trend,
    functions,
    regions: regions(current, before),
    drivers: { negative: driverSplit?.negative ?? [], positive: driverSplit?.positive ?? [] },
    teams,
    grade_distribution: grades,
    kpis,
    levels: levels(current, before),
    people: view === 'managerial' ? people(current, before) : null,
    highlights: {
      most_improved: mostImproved && mostImproved.change !== null ? { type: 'function', name: mostImproved.function, change: mostImproved.change } : null,
      lowest_in_function: lowestTeam && lowestTeam.function && lowestTeam.score !== null
        ? { team: lowestTeam.team, function: lowestTeam.function, score: lowestTeam.score }
        : null,
    },
    corrective_actions: actions,
    periods,
    meta: {
      source: 'composed',
      unavailable: [...unavailable],
      driver_metric: driverSplit?.metric ?? 'contribution_change',
    },
  };
}
