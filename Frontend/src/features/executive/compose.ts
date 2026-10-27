/**
 * Compose the Executive / Function Summary payload from data that already
 * exists. The backend has no `GET /api/executive/summary` route (API_NEEDS.md).
 *
 * Inputs are the authorized performance records the existing dashboards use
 * (`usePerformanceData`: scoped records API or legacy `/api/performance`), the
 * Insights drivers (optional) and corrective-action follow-up (optional).
 * Anything that cannot be derived honestly is left `null` and listed in
 * `meta.unavailable`, so the UI hides or softens it instead of inventing it.
 */
import { normalizePercentageKpiForDisplay } from '../../components/common/performanceKpiProgress';
import { GRADE_CLASSES, getGradeClassOrNull, type GradeClass } from '../../constants/grades';
import { CALL_CENTER_TEAM, RCM_TEAM, canonicalTeamName, isMergedBranchTeam, sameEgyptRcmTeam, type AgentRecord } from '../../types';
import type { TeamConfig } from '../../schemas/teamConfig.schema';
import { calculateAggregatedTeamPerformance, displayedTeamScore, preApprovalsLeaderTeamTotal, recordsUseAppliedPin } from '../team/teamKpiAggregator';
import { normalizePerformanceScore } from '../../utils/kpiScore';
import { kpiCountsInScore } from '../../utils/kpiCountsInScore';
import { compareScoringBasis, type BasisRecord } from '../evaluation/scoringBasisComparison';
import { agentMatchesLocation } from '../../utils/branchScope';
import { summarizeActionAnalytics } from './actionAnalytics';
import type { InsightDriver, InsightItem, InsightTrendStatus } from '../insights/types';
import type { TeamFunctionMap } from '../insights/filterCascade';
import { teamBelongsToFunction } from '../insights/filterCascade';
import { EXECUTIVE_FUNCTIONS, executiveFunctionForTeam, isPreApprovalsSubTeam, summaryFunctionMatches, summaryTeamMatches } from './functions';
import type {
  ExecutiveActionItem,
  ExecutiveCorrectiveActions,
  ExecutiveDriver,
  ExecutiveFunction,
  ExecutiveFunctionCard,
  ExecutiveFunctionCohort,
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
export const SUMMARY_LEVELS = ['Employee', 'Managerial', 'Corporate'] as const;
export const SUMMARY_BRANCHES = [
  { value: 'dubai', label: 'Dubai' },
  { value: 'sharjah', label: 'Sharjah (Sharqa)' },
  { value: 'ajman', label: 'Ajman' },
  { value: 'clinics', label: 'Clinics' },
];
export function normalizeRegion(r: string | null | undefined): string | null {
  if (!r) return null;
  const s = String(r).trim().toUpperCase();
  if (s === 'EGYPT' || s === 'OFFSHORE EGYPT' || s === 'EGY') return 'EGY';
  if (s === 'UAE' || s === 'UAE REGION') return 'UAE';
  return s;
}

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
  branches?: string[];
  period: ExecutivePeriod;
  score: number;
  kpis: NonNullable<AgentRecord['kpi_values']>;
  /** Range mode only: counted months behind a person's range score. */
  months?: number;
  /** Range mode only: KPI keys whose target changed within the range for this person. */
  targetVaries?: string[];
  rawAgent?: AgentRecord;
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

const ACTIVITY_BRANCHES = ['dubai', 'sharjah', 'ajman', 'clinics'] as const;

/** Mirrors the server's `_number`: only a number above zero counts; anything else is zero. */
function aboveZero(value: unknown): boolean {
  if (typeof value === 'number') return Number.isFinite(value) && value > 0;
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    const parsed = Number(value.trim().replace('%', ''));
    return Number.isFinite(parsed) && parsed > 0;
  }
  return false;
}

/**
 * The server's rule for an employee-month with no activity (`_has_real_activity`,
 * performance_dashboard_read_service.py). The row is active when any of these is above
 * zero: the score, a KPI contribution, a call count, a geo booking or attendance count,
 * or a raw value. A row named "total" is never active. Inactive rows are left out of
 * headcount, averages, grade shares, teams, levels and regions.
 */
export function hasRealActivity(agent: AgentRecord): boolean {
  if ((agent.identity?.name ?? '').trim().toLowerCase() === 'total') return false;
  if (aboveZero(agent.evaluation?.score)) return true;
  if ((agent.kpi_values ?? []).some((kpi) => aboveZero(kpi?.contribution))) return true;
  const calls = agent.calls;
  if ([calls?.inbound, calls?.outbound, calls?.total_handled, calls?.abandoned].some(aboveZero)) return true;
  if (ACTIVITY_BRANCHES.some((branch) => aboveZero(agent.geo?.bookings?.[branch]) || aboveZero(agent.geo?.attended?.[branch]))) return true;
  return Object.values(agent.raw_data ?? {}).some(aboveZero);
}

export function toExecRecords(agents: AgentRecord[], fallbackYear = new Date().getFullYear()): ExecRecord[] {
  return agents.flatMap((agent) => {
    const month = agent.identity?.month;
    const team = canonicalTeamName(agent.identity?.team);
    if (!month || !MONTHS.includes(month) || !team) return [];
    if ((agent.identity.name || '').trim().toLowerCase() === 'total') return [];
    if (agent.evaluation?.score == null) return [];
    if (!hasRealActivity(agent)) return [];
    const raw = Number(agent.evaluation?.score);
    if (!Number.isFinite(raw)) return [];
    return [{
      employeeId: String(agent.identity.employee_id || agent.identity.name),
      name: agent.identity.name,
      team,
      region: (agent.region || agent.identity.region || null) as string | null,
      position: (agent.position || agent.identity.position || agent.raw_data?.Position || null) as string | null,
      level: agent.performance_level || 'Employee',
      branches: SUMMARY_BRANCHES.filter((branch) => agentMatchesLocation(agent, branch.value as Parameters<typeof agentMatchesLocation>[1])).map((branch) => branch.value),
      period: periodOf(agent.year || fallbackYear, month),
      score: normalizePerformanceScore(raw),
      // Departmental lists show only KPIs that count in the score (stored weight above 0).
      kpis: (agent.kpi_values || []).filter((kpi) => kpiCountsInScore(kpi.weight_applied)),
      rawAgent: agent,
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

/** Missing points times people. This is the rank key for the company gap. */
function gapWeight(score: number | null, employees: number): number {
  if (score === null) return 0;
  return Math.max(TARGET - score, 0) * Math.max(employees, 0);
}

function stampGapShares<T extends { score: number | null; employees: number; gap_share_percent?: number | null }>(rows: T[]): void {
  const total = rows.reduce((sum, row) => sum + gapWeight(row.score, row.employees), 0);
  rows.forEach((row) => {
    const weight = gapWeight(row.score, row.employees);
    row.gap_share_percent = total > 0 ? round1((weight / total) * 100) : null;
  });
}

function byGapShare(left: { gap_share_percent?: number | null; score: number | null; team?: string; function?: string }, right: { gap_share_percent?: number | null; score: number | null; team?: string; function?: string }): number {
  const leftShare = left.gap_share_percent ?? -1;
  const rightShare = right.gap_share_percent ?? -1;
  if (leftShare !== rightShare) return rightShare - leftShare;
  if (left.score === null) return 1;
  if (right.score === null) return -1;
  if (left.score !== right.score) return left.score - right.score;
  return (left.team ?? left.function ?? '').localeCompare(right.team ?? right.function ?? '');
}

function lowestTeamOf(teams: ExecutiveTeam[], name: string): ExecutiveFunctionCard['lowest_team'] {
  const lowest = teams
    .filter((team) => team.function === name && team.score !== null)
    .sort((left, right) => (left.score ?? 0) - (right.score ?? 0) || left.team.localeCompare(right.team))[0];
  if (!lowest || lowest.score === null) return null;
  return {
    team: lowest.team,
    score: lowest.score,
    kpi: lowest.flag_detail?.text ?? null,
    score_basis: lowest.score_basis ?? 'people_average',
  };
}

function employeesOf(records: ExecRecord[]): number {
  return new Set(records.map((record) => record.employeeId)).size;
}

function inPeriod(records: ExecRecord[], period: ExecutivePeriod | null) {
  return period ? records.filter((record) => record.period.key === period.key) : [];
}

function exactPreviousPeriod(period: ExecutivePeriod): ExecutivePeriod {
  const index = MONTHS.indexOf(period.month);
  if (index <= 0) return periodOf(period.year - 1, 'December');
  return periodOf(period.year, MONTHS[index - 1]);
}

function asBasisRecords(records: ExecRecord[]): BasisRecord[] {
  return records.map((record) => ({
    employee_id: record.employeeId,
    team: record.team,
    position: record.position,
    performance_level: record.level,
    year: record.period.year,
    month: record.period.month,
    kpi_values: record.kpis,
  }));
}

/** Exact calendar month, even when the score delta uses a later available month. */
function basisFor(records: ExecRecord[], period: ExecutivePeriod) {
  return compareScoringBasis(asBasisRecords(inPeriod(records, period)), asBasisRecords(inPeriod(records, exactPreviousPeriod(period))));
}

/** The one function every listed team belongs to; null when they span several functions (or none). */
function sharedFunctionOf(teams: string[], teamFunctions?: TeamFunctionMap): ExecutiveFunction | null {
  const functions = new Set(teams.map((team) => executiveFunctionForTeam(team, teamFunctions)).filter((fn): fn is ExecutiveFunction => fn !== null));
  return functions.size === 1 ? [...functions][0] : null;
}

/** Six calendar months ending at `period` (oldest first). */
export function trailingPeriods(period: ExecutivePeriod, count = 6): ExecutivePeriod[] {
  const absolute = period.year * 12 + MONTHS.indexOf(period.month);
  return Array.from({ length: count }, (_, index) => {
    const value = absolute - (count - 1 - index);
    return periodOf(Math.floor(value / 12), MONTHS[value % 12]);
  });
}

function shiftPeriod(period: ExecutivePeriod, delta: number): ExecutivePeriod {
  const value = period.year * 12 + MONTHS.indexOf(period.month) + delta;
  return periodOf(Math.floor(value / 12), MONTHS[((value % 12) + 12) % 12]);
}

/** Every month from `start` to `end` inclusive, oldest first. Empty when `end` is before `start`. */
export function monthsBetween(start: ExecutivePeriod, end: ExecutivePeriod): ExecutivePeriod[] {
  const count = (end.year * 12 + MONTHS.indexOf(end.month)) - (start.year * 12 + MONTHS.indexOf(start.month)) + 1;
  return Array.from({ length: Math.max(0, count) }, (_, index) => shiftPeriod(start, index));
}

/** The range of the same length immediately before `months` (Jun–Sep compares with Feb–May). */
export function previousRangeOf(months: ExecutivePeriod[]): ExecutivePeriod[] {
  if (!months.length) return [];
  return monthsBetween(shiftPeriod(months[0], -months.length), shiftPeriod(months[0], -1));
}

const shortMonth = (period: ExecutivePeriod) => period.month.slice(0, 3);

type KpiRecord = ExecRecord['kpis'][number];

/** One KPI per person across the range: mean actual, achievement and weight; the target only when it never changed. */
function collapseKpis(records: ExecRecord[]): ExecRecord['kpis'] {
  const buckets = new Map<string, { template: KpiRecord; actual: number[]; achievement: number[]; weight: number[]; targets: number[] }>();
  records.forEach((record) => record.kpis.forEach((kpi) => {
    if (!kpi?.kpi_key) return;
    const bucket = buckets.get(kpi.kpi_key) ?? { template: kpi, actual: [], achievement: [], weight: [], targets: [] };
    if (Number.isFinite(kpi.actual_value)) bucket.actual.push(Number(kpi.actual_value));
    if (Number.isFinite(kpi.achievement_ratio)) bucket.achievement.push(Number(kpi.achievement_ratio));
    if (Number.isFinite(kpi.weight_applied)) bucket.weight.push(Number(kpi.weight_applied));
    if (Number.isFinite(kpi.target_value)) bucket.targets.push(Number(kpi.target_value));
    buckets.set(kpi.kpi_key, bucket);
  }));
  return [...buckets.values()].map(({ template, actual, achievement, weight, targets }) => ({
    ...template,
    actual_value: mean(actual) ?? template.actual_value,
    achievement_ratio: mean(achievement) ?? template.achievement_ratio,
    weight_applied: mean(weight) ?? template.weight_applied,
    // The mean target; `collapseRange` records when it changed (`targetVaries`), and the table shows "Varies".
    target_value: mean(targets) ?? template.target_value,
  }));
}

/**
 * Range mode, person-first. One record per person (employee and level) for the whole range: the person's
 * score is the mean of their counted months, which sets their range grade. A month with several rows counts
 * once, as the mean of its rows. Team, region, position and level come from the latest counted month. The
 * record sits at `anchor` (the range's last month) so the single-month aggregates apply unchanged.
 */
export function collapseRange(monthly: ExecRecord[], months: ExecutivePeriod[], anchor: ExecutivePeriod): ExecRecord[] {
  const keys = new Set(months.map((period) => period.key));
  const groups = new Map<string, ExecRecord[]>();
  monthly.forEach((record) => {
    if (!keys.has(record.period.key)) return;
    const groupKey = `${record.employeeId}:${record.level}`;
    groups.set(groupKey, [...(groups.get(groupKey) ?? []), record]);
  });
  return [...groups.values()].map((records) => {
    const byMonth = new Map<string, ExecRecord[]>();
    records.forEach((record) => byMonth.set(record.period.key, [...(byMonth.get(record.period.key) ?? []), record]));
    const monthKeys = [...byMonth.keys()].sort();
    const monthScores = monthKeys.map((key) => mean(byMonth.get(key)!.map((record) => record.score)) ?? 0);
    const latest = byMonth.get(monthKeys[monthKeys.length - 1])![0];
    const targetVaries = [...new Set(records.flatMap((record) => record.kpis.map((kpi) => kpi.kpi_key)))]
      .filter((kpiKey) => new Set(records.flatMap((record) => record.kpis
        .filter((kpi) => kpi.kpi_key === kpiKey && Number.isFinite(kpi.target_value))
        .map((kpi) => Number(kpi.target_value).toFixed(4)))).size > 1);
    return {
      ...latest,
      period: anchor,
      score: mean(monthScores) ?? 0,
      months: monthKeys.length,
      kpis: collapseKpis(records),
      targetVaries,
    };
  });
}

/**
 * Evaluation-basis note for a scope. One month: as today. A range: every month inside it that shows a basis
 * change against its own previous month, labelled by month; no note when none does.
 */
function basisForScope(monthly: ExecRecord[], effective: ExecutivePeriod, months: ExecutivePeriod[] | null) {
  // One month, as today: the exact note, unchanged.
  if (!months || months.length <= 1) return basisFor(monthly, effective);
  const changed = months
    .filter((month) => inPeriod(monthly, month).length > 0)
    .map((month) => ({ month, context: basisFor(monthly, month) }))
    .filter(({ context }) => context.state === 'changed' && context.message);
  if (!changed.length) return { ...basisFor(monthly, effective), message: null };
  return { ...changed[0].context, message: changed.map(({ month, context }) => `${shortMonth(month)}: ${context.message}`).join(' ') };
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
  // Combined shares come from the counts and are rounded once, never from the rounded per-grade shares.
  const combined_percents = {
    AB: round1(((counts.A + counts.B) / total) * 100),
    DE: round1(((counts.D + counts.E) / total) * 100),
  };
  let previousCounts: Record<GradeClass, number> | null = null;
  let movement: Record<GradeClass, number> | null = null;
  if (previous.length) {
    const prev = emptyCounts();
    previous.forEach((record) => { prev[getGradeClassOrNull(record.score) ?? 'E'] += 1; });
    previousCounts = prev;
    movement = emptyCounts();
    GRADE_CLASSES.forEach((grade) => { movement![grade] = counts[grade] - prev[grade]; });
  }
  const people = new Set(current.map((record) => record.employeeId)).size;
  return { total, people, counts, percents, combined_percents, previous_counts: previousCounts, movement };
}

const TOLERANCE = 1e-9;

function trendStatusOf(changeValue: number | null): InsightTrendStatus | null {
  if (changeValue === null) return null;
  if (Math.abs(changeValue) < 0.05) return 'stable';
  return changeValue > 0 ? 'improving' : 'declining';
}

/**
 * Percent display scale for one stored KPI.
 * A paired target in (0, 1] is a ratio (1 means 100%), matching
 * `normalizePercentageKpiForDisplay`. A percent-point target such as 0.1
 * against 5, or 88 against 90, stays on the stored scale. Counts, currency,
 * and durations are unchanged.
 */
function executivePercentValue(value: number, unit: string | null | undefined, target: number | null): number {
  const kind = String(unit ?? '').trim().toLowerCase();
  if (kind === 'percent' || kind === 'percentage') {
    return target !== null && target > 0 && target <= 1 ? value * 100 : value;
  }
  if (kind === '%') return normalizePercentageKpiForDisplay(value, target ?? Number.NaN, '%');
  return value;
}

/** Direction-aware KPI rows (worst achievement first) from per-employee `kpi_values`. */
export function kpiRows(current: ExecRecord[], previous: ExecRecord[], options?: { range?: boolean }): ExecutiveKpiRow[] {
  type Bucket = { label: string; unit: string | null; direction: string | null; actual: number[]; target: number[]; weight: number[]; achievement: number[]; teams: Set<string> };
  const collect = (records: ExecRecord[]) => {
    const buckets = new Map<string, Bucket>();
    records.forEach((record) => record.kpis.forEach((kpi) => {
      if (!kpi?.kpi_key || !kpiCountsInScore(kpi.weight_applied)) return;
      const bucket = buckets.get(kpi.kpi_key) ?? {
        label: kpi.label || kpi.kpi_key, unit: kpi.unit ?? null, direction: kpi.direction ?? null,
        actual: [], target: [], weight: [], achievement: [], teams: new Set<string>(),
      };
      const storedTarget = Number.isFinite(kpi.target_value) ? Number(kpi.target_value) : null;
      if (Number.isFinite(kpi.actual_value)) {
        bucket.actual.push(executivePercentValue(Number(kpi.actual_value), kpi.unit, storedTarget));
      }
      if (storedTarget !== null) bucket.target.push(executivePercentValue(storedTarget, kpi.unit, storedTarget));
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
    // A range shows a target only when every person and month shares it; otherwise "Varies".
    const targetVaries = Boolean(options?.range) && (current.some((record) => record.targetVaries?.includes(key))
      || new Set(current.flatMap((record) => record.kpis
        .filter((kpi) => kpi.kpi_key === key && Number.isFinite(kpi.target_value))
        .map((kpi) => Number(kpi.target_value).toFixed(4)))).size > 1);
    const target = targetVaries ? null : mean(bucket.target);
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
      ...(options?.range ? { target_varies: targetVaries } : {}),
    });
  });
  return rows.sort((left, right) => (left.achievement_percent ?? 101) - (right.achievement_percent ?? 101) || left.kpi_label.localeCompare(right.kpi_label));
}

function levels(current: ExecRecord[], previous: ExecRecord[]): ExecutiveLevel[] {
  return SUMMARY_LEVELS.map((level) => {
    const records = current.filter((record) => record.level === level);
    const score = scoreOf(records);
    const previousScore = scoreOf(previous.filter((record) => record.level === level));
    return { level, employees: employeesOf(records), score, previous_score: previousScore, change: diff(score, previousScore), grade: getGradeClassOrNull(score) };
  });
}

function people(current: ExecRecord[], previous: ExecRecord[]): ExecutivePeople {
  const key = (record: ExecRecord) => `${record.employeeId}:${record.level}`;
  const groups = new Map<string, ExecRecord[]>();
  current.forEach((record) => groups.set(key(record), [...(groups.get(key(record)) ?? []), record]));
  const persons: ExecutivePerson[] = [...groups.values()].map((records) => {
    const record = records[0];
    const previousScore = scoreOf(previous.filter((item) => key(item) === key(record)));
    const score = scoreOf(records);
    return {
      employee_id: record.employeeId,
      name: record.name,
      position: record.position,
      team: record.team,
      region: record.region,
      performance_level: record.level,
      score,
      previous_score: previousScore,
      change: diff(score, previousScore),
      grade: getGradeClassOrNull(score),
      ...(record.months !== undefined ? { months: record.months } : {}),
    };
  });
  const byName = (left: ExecutivePerson, right: ExecutivePerson) => left.name.localeCompare(right.name);
  return {
    below_90: persons.filter((person) => person.score !== null && person.score < 90)
      .sort((l, r) => (l.score ?? 0) - (r.score ?? 0) || byName(l, r)),
    bottom: [...persons].sort((l, r) => (l.score ?? 0) - (r.score ?? 0) || byName(l, r)).slice(0, 4),
    biggest_drops: persons.filter((person) => person.change !== null && person.change < 0)
      .sort((l, r) => (l.change ?? 0) - (r.change ?? 0) || byName(l, r)).slice(0, 4),
    top: [...persons].sort((l, r) => (r.score ?? 0) - (l.score ?? 0) || byName(l, r)).slice(0, 3),
  };
}

function teamNamesMatch(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return false;
  const normA = a.trim().toLowerCase().replace(/[^a-z0-9]+/g, '');
  const normB = b.trim().toLowerCase().replace(/[^a-z0-9]+/g, '');
  if (normA === normB) return true;
  return canonicalTeamName(a).toLowerCase() === canonicalTeamName(b).toLowerCase();
}

export function findTeamConfig(
  teamConfigs: Map<string, TeamConfig> | Record<string, TeamConfig> | TeamConfig[] | undefined,
  teamName: string,
): TeamConfig | null {
  if (!teamConfigs || !teamName) return null;
  const list: TeamConfig[] = teamConfigs instanceof Map
    ? [...teamConfigs.values()]
    : Array.isArray(teamConfigs)
      ? teamConfigs
      : Object.values(teamConfigs);

  return list.find((cfg) =>
    teamNamesMatch(cfg.team, teamName) || teamNamesMatch(cfg.db_name, teamName)
  ) ?? null;
}

function teamsOf(
  scoped: ExecRecord[],
  effective: ExecutivePeriod,
  previous: ExecutivePeriod | null,
  teamFunctions: TeamFunctionMap | undefined,
  byRole = false,
  monthly: ExecRecord[] | null = null,
  rangeMonths: ExecutivePeriod[] | null = null,
  teamConfigs?: Map<string, TeamConfig> | Record<string, TeamConfig> | TeamConfig[],
  unlevelMonthly?: ExecRecord[],
): ExecutiveTeam[] {
  const groupName = (record: ExecRecord) => byRole ? record.position || record.team : record.team;
  const monthlyRecords = monthly ?? scoped;
  const names = [...new Set(inPeriod(scoped, effective).map(groupName))];
  const base = names.map((team) => {
    const records = scoped.filter((record) => groupName(record) === team);
    // The trend and the basis note read the team's monthly records; the aggregates read `records`.
    const monthlyTeam = monthlyRecords.filter((record) => groupName(record) === team);
    const current = inPeriod(records, effective);
    const teamConfig = byRole ? null : findTeamConfig(teamConfigs, team);
    const isParentSupportPositions = sameTeamName(team, CALL_CENTER_TEAM) || sameTeamName(team, RCM_TEAM);
    const useCanonical = Boolean(teamConfig && !rangeMonths && !isMergedBranchTeam(team) && !isParentSupportPositions);

    let score = scoreOf(current);
    let previousScore = scoreOf(inPeriod(records, previous));
    let scoreBasis: ExecutiveTeam['score_basis'] = 'people_average';
    let trend = trendOf(monthlyTeam, effective);

    const isPreApprovals = team === 'Pre-Approvals IP'
      || team === 'Pre-Approvals IP Offshore'
      || isPreApprovalsSubTeam(team)
      || sameEgyptRcmTeam(team, 'Pre-Approvals IP');

    // The leader scorecard belongs only to the team on that record. Sibling pre-approvals
    // teams stay on their own average even when they share the unlevel month.
    const teamPool = (unlevelMonthly ?? monthlyRecords).filter((record) => groupName(record) === team);
    const leaderTotal = (period: ExecutivePeriod | null) => (
      isPreApprovals && period ? preApprovalsLeaderTeamTotal(inPeriod(teamPool, period)) : null
    );
    const leaderNow = leaderTotal(effective);
    const leaderPrev = leaderTotal(previous);
    // The leader scorecard is the team total even when a later employee-only roll-up would average the specialists.
    if (leaderNow !== null) {
      score = leaderNow;
      scoreBasis = 'leader_scorecard';
    }
    if (leaderPrev !== null) previousScore = leaderPrev;

    if (isPreApprovals) {
      const periods = trailingPeriods(effective);
      trend = periods.map((period) => {
        const periodRecords = inPeriod(monthlyTeam, period);
        const periodLeader = leaderTotal(period);
        const periodScore = periodLeader !== null ? periodLeader : scoreOf(periodRecords);
        return {
          period,
          score: periodScore,
          employees: employeesOf(periodRecords),
          has_data: periodRecords.length > 0 || periodLeader !== null,
          basis_context: null,
        };
      });
    }

    if (useCanonical && teamConfig && leaderNow === null) {
      const currentAgents = current.map((record) => record.rawAgent).filter((a): a is AgentRecord => Boolean(a));
      if (currentAgents.length > 0) {
        const canonical = calculateAggregatedTeamPerformance(currentAgents, teamConfig)?.score ?? null;
        if (canonical !== null) {
          score = round1(displayedTeamScore(canonical, score ?? 0, recordsUseAppliedPin(currentAgents)));
          scoreBasis = 'team_scorecard';
        }
      }
    }

    if (useCanonical && teamConfig && leaderPrev === null) {
      const previousRecords = inPeriod(records, previous);
      const previousAgents = previousRecords.map((record) => record.rawAgent).filter((a): a is AgentRecord => Boolean(a));
      if (previousAgents.length > 0) {
        const canonicalPrev = calculateAggregatedTeamPerformance(previousAgents, teamConfig)?.score ?? null;
        if (canonicalPrev !== null) {
          previousScore = round1(displayedTeamScore(canonicalPrev, previousScore ?? 0, recordsUseAppliedPin(previousAgents)));
        }
      }
    }

    if (useCanonical && teamConfig) {
      const periods = trailingPeriods(effective);
      trend = periods.map((period) => {
        const periodRecords = inPeriod(monthlyTeam, period);
        const periodLeader = leaderTotal(period);
        const periodAgents = periodRecords.map((r) => r.rawAgent).filter((a): a is AgentRecord => Boolean(a));
        const avgPeriod = scoreOf(periodRecords);
        let computedScore: number | null = periodLeader;
        if (computedScore === null && periodAgents.length > 0) {
          const canonical = calculateAggregatedTeamPerformance(periodAgents, teamConfig)?.score ?? null;
          computedScore = canonical !== null
            ? round1(displayedTeamScore(canonical, avgPeriod ?? 0, recordsUseAppliedPin(periodAgents)))
            : avgPeriod;
        }

        const finalScore = period.key === effective.key
          ? score
          : previous && period.key === previous.key
            ? previousScore
            : computedScore;

        return {
          period,
          score: finalScore,
          employees: employeesOf(periodRecords),
          has_data: periodRecords.length > 0,
          basis_context: null,
        };
      });
    }

    const worstKpi = kpiRows(current, inPeriod(records, previous))[0];
    return {
      team,
      position: byRole ? team : null,
      source_team: records[0].team,
      function: executiveFunctionForTeam(records[0].team, teamFunctions),
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
      gap_share_percent: null as number | null,
      score_basis: scoreBasis,
      flags: [] as ExecutiveTeamFlag[],
      basis_context: basisForScope(monthlyTeam, effective, rangeMonths),
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
    if (team.grade === 'C') team.flags.unshift('grade_c');
    if (team.grade === 'D') team.flags.unshift('grade_d');
    if (team.grade === 'E') team.flags.unshift('grade_e');
    if (fallingMonths(team.trend) >= 2) team.flags.push('falling_2_months');
  });
  stampGapShares(base);
  return base.sort(byGapShare);
}

export function isAtRisk(team: ExecutiveTeam) {
  return team.flags.some((flag) => flag === 'grade_c' || flag === 'grade_d' || flag === 'grade_e' || flag === 'falling_2_months');
}

const sameTeamName = (left: string, right: string) => canonicalTeamName(left).trim().toLowerCase() === canonicalTeamName(right).trim().toLowerCase();

/** Supportive positions sit on the parent team. Operational teams are the employees. */
function supportiveTeam(team: string, fn: ExecutiveFunction): boolean {
  if (fn === 'Call Center') return sameTeamName(team, CALL_CENTER_TEAM);
  if (fn === 'RCM') return sameTeamName(team, RCM_TEAM);
  return false;
}

function cohortOf(current: ExecRecord[], previous: ExecRecord[]): ExecutiveFunctionCohort {
  const score = scoreOf(current);
  return {
    employees: employeesOf(current),
    score,
    gap: score === null ? null : round1(score - TARGET),
    grade: getGradeClassOrNull(score),
    change: diff(score, scoreOf(previous)),
    teams: [...new Set(current.map((record) => canonicalTeamName(record.team)))].sort(),
  };
}

function functionCohorts(name: ExecutiveFunction, current: ExecRecord[], previous: ExecRecord[]): ExecutiveFunctionCard['cohorts'] {
  if (name !== 'Call Center' && name !== 'RCM') return null;
  const supportNow = current.filter((record) => supportiveTeam(record.team, name));
  const employeesNow = current.filter((record) => !supportiveTeam(record.team, name));
  if (!employeesOf(supportNow) || !employeesOf(employeesNow)) return null;
  return {
    employees: cohortOf(employeesNow, previous.filter((record) => !supportiveTeam(record.team, name))),
    support: cohortOf(supportNow, previous.filter((record) => supportiveTeam(record.team, name))),
  };
}

function functionCards(scoped: ExecRecord[], effective: ExecutivePeriod, previous: ExecutivePeriod | null, teamFunctions?: TeamFunctionMap, monthly: ExecRecord[] | null = null, rangeMonths: ExecutivePeriod[] | null = null): ExecutiveFunctionCard[] {
  const monthlyRecords = monthly ?? scoped;
  const cards = EXECUTIVE_FUNCTIONS.flatMap((name): ExecutiveFunctionCard[] => {
    const records = scoped.filter((record) => executiveFunctionForTeam(record.team, teamFunctions) === name);
    const current = inPeriod(records, effective);
    if (!current.length) return [];
    const previousRows = inPeriod(records, previous);
    const score = scoreOf(current);
    const previousScore = scoreOf(previousRows);
    const monthlyFunction = monthlyRecords.filter((record) => executiveFunctionForTeam(record.team, teamFunctions) === name);
    const trend = trendOf(monthlyFunction, effective);
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
      basis_context: basisForScope(monthlyFunction, effective, rangeMonths),
      cohorts: functionCohorts(name, current, previousRows),
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
    .sort(byGapShare);
}

/* ── Drivers (from the Insights workspace) ── */

/** Branch/role drivers use only persisted contributions inside the selected scope. */
export function scopedRecordDrivers(current: ExecRecord[], previous: ExecRecord[], teamFunctions?: TeamFunctionMap) {
  const points = (value: number) => Math.abs(value) <= 1 ? value * 100 : value;
  const contributions = (records: ExecRecord[], team: string, key: string) => records
    .filter((record) => record.team === team)
    .flatMap((record) => record.kpis.filter((kpi) => kpi.kpi_key === key
      && kpiCountsInScore(kpi.weight_applied)
      && Number.isFinite(kpi.contribution)));
  const all: ExecutiveDriver[] = [];
  for (const team of new Set(current.map((record) => record.team))) {
    const rows = kpiRows(current.filter((record) => record.team === team), previous.filter((record) => record.team === team));
    for (const row of rows) {
      if (row.gap_value === null) continue;
      const now = contributions(current, team, row.kpi_key);
      if (!now.length) continue;
      const before = contributions(previous, team, row.kpi_key);
      const currentImpact = now.reduce((total, kpi) => total + points(kpi.contribution!), 0) / current.length;
      const targetImpact = now.reduce((total, kpi) => total + points(kpi.weight_applied!), 0) / current.length;
      const previousImpact = before.length ? before.reduce((total, kpi) => total + points(kpi.contribution!), 0) / previous.length : null;
      const change = previousImpact === null ? null : currentImpact - previousImpact;
      all.push({
        kpi_key: row.kpi_key, kpi_label: row.kpi_label, team,
        function: executiveFunctionForTeam(team, teamFunctions), kpi_direction: row.kpi_direction,
        unit: row.unit, current_value: row.actual, previous_value: row.previous_actual,
        raw_change: row.raw_change, change_value: row.change_value, trend_status: row.trend_status,
        gap_value: row.gap_value, achievement_percent: row.achievement_percent, weight: row.weight,
        impact_points: change, impact_change_points: change,
        weighted_gap_points: currentImpact - targetImpact,
      });
    }
  }
  if (!all.length) return null;
  return {
    negative: all.filter((driver) => driver.weighted_gap_points! < 0).sort((left, right) => left.weighted_gap_points! - right.weighted_gap_points!).slice(0, 3),
    positive: all.filter((driver) => (driver.impact_change_points ?? 0) > 0).sort((left, right) => right.impact_change_points! - left.impact_change_points!).slice(0, 3),
    metric: 'weighted_gap' as const, hasWeightedGap: true,
  };
}

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
    // API details keep percent measures as ratios when the paired target is in
    // (0, 1]. Impact and achievement already use display points; weight stays a fraction.
    const storedTarget = detail?.target_value != null && Number.isFinite(detail.target_value)
      ? detail.target_value
      : null;
    const displayMeasure = (value: number | null | undefined) => (
      value == null || !Number.isFinite(value) ? null : executivePercentValue(value, detail?.unit, storedTarget)
    );
    const rawChange = detail?.raw_change ?? (
      detail?.current_value != null && detail?.previous_value != null
        ? detail.current_value - detail.previous_value
        : null
    );
    merged.set(key, {
      kpi_key: item?.kpi_key ?? null,
      kpi_label: driver.driver,
      team,
      function: executiveFunctionForTeam(team, teamFunctions),
      kpi_direction: driver.kpi_direction ?? detail?.direction ?? null,
      unit: detail?.unit ?? null,
      current_value: displayMeasure(detail?.current_value),
      previous_value: displayMeasure(detail?.previous_value),
      raw_change: displayMeasure(rawChange),
      change_value: displayMeasure(detail?.change_value),
      trend_status: detail?.trend_status ?? null,
      gap_value: displayMeasure(detail?.gap_value),
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
  action_text?: string | null;
  employee_id?: string | null;
  month?: string;
  created_at?: string | null;
  root_cause_note?: string | null;
  linked_kpi_key?: string | null;
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
/** `pending` = actions queued on this device and not yet synced (Pending Sync); they never change the totals above. */
export function summarizeActions(actions: FollowUpAction[], today: Date, effective: ExecutivePeriod | null, pending: FollowUpAction[] = [], periodKeys?: string[]): ExecutiveCorrectiveActions {
  const todayIso = localIsoDate(today);
  const weekEnd = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 6);
  const weekEndIso = localIsoDate(weekEnd);
  const isOpen = (action: FollowUpAction) => OPEN_STATUSES.has(String(action.status || ''));
  const dueDate = (action: FollowUpAction) => (action.due_date ? String(action.due_date).slice(0, 10) : null);
  const overdue = (action: FollowUpAction) => isOpen(action) && (action.follow_up_state === 'overdue' || (dueDate(action) !== null && dueDate(action)! < todayIso));
  const dueThisWeek = (action: FollowUpAction) => isOpen(action) && !overdue(action) && dueDate(action) !== null && dueDate(action)! >= todayIso && dueDate(action)! <= weekEndIso;
  const closedInMonth = effective
    ? actions.filter((action) => action.status === 'Completed' && (periodKeys ?? [effective.key]).includes(String(action.completed_at || '').slice(0, 7))).length
    : null;
  const toItem = (action: FollowUpAction): ExecutiveActionItem => ({
    id: String(action.id),
    title: action.title || action.action_type || action.description || 'Corrective action',
    team: action.team ?? null,
    region: action.region ?? null,
    employee_name: action.employee_name ?? null,
    owner: action.owner ?? null,
    due_date: dueDate(action),
    status: String(action.status || ''),
    follow_up_state: overdue(action) ? 'overdue' : dueThisWeek(action) ? 'due_this_week' : (action.follow_up_state ?? null),
    employee_id: action.employee_id ?? null,
    month: action.month,
    action_type: action.action_type ?? null,
    action_text: action.action_text ?? action.description ?? null,
    root_cause: action.root_cause_note ?? null,
    linked_kpi_key: action.linked_kpi_key ?? null,
    created_at: action.created_at ?? null,
    completed_at: action.completed_at ?? null,
  });
  const rank = (action: FollowUpAction) => (overdue(action) ? 0 : dueThisWeek(action) ? 1 : isOpen(action) ? 2 : 3);
  const items: ExecutiveActionItem[] = actions.filter(isOpen)
    .sort((l, r) => rank(l) - rank(r) || String(dueDate(l) ?? '9999').localeCompare(String(dueDate(r) ?? '9999')))
    .slice(0, 4)
    .map(toItem);
  // Full list for the card: open actions plus those closed in the period. Overdue first, then due soonest,
  // then newest; actions without a due date come after the dated ones in their group.
  const closedInPeriod = (action: FollowUpAction) => effective !== null && action.status === 'Completed'
    && (periodKeys ?? [effective.key]).includes(String(action.completed_at || '').slice(0, 7));
  const rows: ExecutiveActionItem[] = actions.filter((action) => isOpen(action) || closedInPeriod(action))
    .sort((l, r) => rank(l) - rank(r)
      || String(dueDate(l) ?? '9999-99-99').localeCompare(String(dueDate(r) ?? '9999-99-99'))
      || String(r.created_at ?? '').localeCompare(String(l.created_at ?? '')))
    .slice(0, 200)
    .map(toItem);
  return {
    analytics: summarizeActionAnalytics(actions, effective, pending, periodKeys),
    summary: {
      as_of: todayIso,
      open: actions.filter(isOpen).length,
      overdue: actions.filter(overdue).length,
      due_this_week: actions.filter(dueThisWeek).length,
      closed_in_month: closedInMonth,
    },
    actions: items,
    rows,
  };
}

/* ── Composition ── */

export interface ComposeInput {
  view: ExecutiveView;
  role: string;
  records: ExecRecord[];
  filters: { region?: string; branch?: string; teamFunction?: string; team?: string; position?: string; performanceLevel?: string };
  requestedPeriodKey?: string | null;
  /** Managerial: the manager's team; Function view: the selected function. */
  team?: string | null;
  /** Managerial: every team the viewer may see. Records and drivers outside them never enter the summary. */
  teamScope?: string[] | null;
  functionName?: ExecutiveFunction | null;
  accessibleFunctions?: string[];
  teamFunctions?: TeamFunctionMap;
  drivers?: { drivers: InsightDriver[]; items: InsightItem[] } | null;
  deriveScopedDrivers?: boolean;
  actions?: FollowUpAction[] | null;
  /** Range mode: the months to average (oldest first) and the range of the same length before them. */
  range?: { months: ExecutivePeriod[]; previousMonths: ExecutivePeriod[] } | null;
  /** Local actions not yet synced, already filtered to the page scope. Counted as Pending Sync only. */
  pendingActions?: FollowUpAction[] | null;
  /** Records outside the viewer's scope for aggregate comparisons (never available client-side for Manager / Function Viewer). */
  comparisonRecords?: ExecRecord[] | null;
  teamConfigs?: Map<string, TeamConfig> | Record<string, TeamConfig> | TeamConfig[];
  today: Date;
}

function applyFilters(records: ExecRecord[], input: ComposeInput, teamFunctions?: TeamFunctionMap) {
  const { region, branch, teamFunction, team, position, performanceLevel } = input.filters;
  return records.filter((record) => (
    (!normalizeRegion(region) || normalizeRegion(record.region) === normalizeRegion(region))
    && (!branch || record.branches?.includes(branch))
    && (!position || record.position === position)
    && (!performanceLevel || record.level === performanceLevel)
    && (!teamFunction || (input.view === 'function'
      ? summaryFunctionMatches(record.team, teamFunction, teamFunctions)
      : teamBelongsToFunction(record.team, teamFunction, teamFunctions)))
    && (!team || summaryTeamMatches(record.team, team))
    && (!input.teamScope || input.teamScope.some((allowed) => summaryTeamMatches(record.team, allowed)))
  ));
}

export function composeExecutiveSummary(input: ComposeInput): ExecutiveSummary {
  const { view, teamFunctions } = input;
  const unavailable = new Set<ExecutiveSection>(['upload_meta']);
  const scopeFilters = { ...input.filters };
  if (view === 'managerial' && input.team) scopeFilters.team = input.team;
  if (view === 'function' && input.functionName) scopeFilters.teamFunction = input.functionName;
  // The monthly, scope-filtered records: the trend, the month list and the monthly basis read these.
  const monthly = applyFilters(input.records, { ...input, filters: scopeFilters }, teamFunctions);
  const unlevelFilters = { ...scopeFilters };
  delete unlevelFilters.performanceLevel;
  const unlevelMonthly = applyFilters(input.records, { ...input, filters: unlevelFilters }, teamFunctions);
  // Managerial: the function of the selected team, or the one function all visible teams share.
  const managerFunction = view === 'managerial'
    ? (input.team ? executiveFunctionForTeam(input.team, teamFunctions) : sharedFunctionOf(input.teamScope ?? [], teamFunctions))
    : null;

  const periods = [...new Map(monthly.map((record) => [record.period.key, record.period])).values()]
    .sort((l, r) => r.key.localeCompare(l.key));
  // Range mode: each person's counted months are averaged into one record at the range's last month, and the
  // range of the same length before it into another. The aggregates then run exactly as for one month.
  const range = input.range ?? null;
  const rangeEnd = range && range.months.length ? range.months[range.months.length - 1] : null;
  const previousEnd = range && range.previousMonths.length ? range.previousMonths[range.previousMonths.length - 1] : null;
  const rangeCurrent = range && rangeEnd ? collapseRange(monthly, range.months, rangeEnd) : [];
  const rangePrevious = range && previousEnd ? collapseRange(monthly, range.previousMonths, previousEnd) : [];
  const scoped = range ? [...rangeCurrent, ...rangePrevious] : monthly;
  const requested = range || !input.requestedPeriodKey ? null : periodFromKey(input.requestedPeriodKey);
  const effective = range
    ? (rangeCurrent.length ? rangeEnd : null)
    : (requested && periods.some((period) => period.key === requested.key) ? requested : periods[0] ?? null);
  const fallbackApplied = Boolean(requested && effective && requested.key !== effective.key);
  const previous = range
    ? (rangePrevious.length ? previousEnd : null)
    : (effective ? periods.find((period) => period.key < effective.key) ?? null : null);
  const rangeMonths = range && rangeEnd ? range.months : null;
  const rangeBlock = range && rangeEnd ? {
    start: range.months[0],
    end: rangeEnd,
    months: range.months,
    months_with_data: range.months.filter((month) => inPeriod(monthly, month).length > 0).length,
    previous: range.previousMonths.length && previousEnd && rangePrevious.length ? {
      start: range.previousMonths[0],
      end: previousEnd,
      months_with_data: range.previousMonths.filter((month) => inPeriod(monthly, month).length > 0).length,
    } : null,
  } : null;

  const current = inPeriod(scoped, effective);
  const before = inPeriod(scoped, previous);
  let score = scoreOf(current);
  let previousScore = scoreOf(before);
  let scoreBasis: ExecutiveSummary['hero']['score_basis'] = 'people_average';
  if (view === 'managerial' && input.team && !rangeMonths) {
    const isPreApprovalsTeam = input.team === 'Pre-Approvals IP'
      || input.team === 'Pre-Approvals IP Offshore'
      || isPreApprovalsSubTeam(input.team)
      || sameEgyptRcmTeam(input.team, 'Pre-Approvals IP');
    const leaderOnThisTeam = (period: ExecutivePeriod | null) => (
      period
        ? preApprovalsLeaderTeamTotal(inPeriod(unlevelMonthly, period).filter((record) => record.team === input.team))
        : null
    );
    const leaderNow = isPreApprovalsTeam ? leaderOnThisTeam(effective) : null;
    const leaderPrev = isPreApprovalsTeam ? leaderOnThisTeam(previous) : null;
    if (leaderNow !== null) {
      score = leaderNow;
      scoreBasis = 'leader_scorecard';
    }
    if (leaderPrev !== null) previousScore = leaderPrev;
    const mgrConfig = findTeamConfig(input.teamConfigs, input.team);
    if (mgrConfig && !isMergedBranchTeam(input.team)) {
      const currentAgents = current.map((r) => r.rawAgent).filter((a): a is AgentRecord => Boolean(a));
      const beforeAgents = before.map((r) => r.rawAgent).filter((a): a is AgentRecord => Boolean(a));
      if (leaderNow === null && currentAgents.length > 0) {
        const canonical = calculateAggregatedTeamPerformance(currentAgents, mgrConfig)?.score ?? null;
        if (canonical !== null) {
          score = round1(displayedTeamScore(canonical, score ?? 0, recordsUseAppliedPin(currentAgents)));
          scoreBasis = 'team_scorecard';
        }
      }
      if (leaderPrev === null && beforeAgents.length > 0) {
        const canonicalPrev = calculateAggregatedTeamPerformance(beforeAgents, mgrConfig)?.score ?? null;
        if (canonicalPrev !== null) {
          previousScore = round1(displayedTeamScore(canonicalPrev, previousScore ?? 0, recordsUseAppliedPin(beforeAgents)));
        }
      }
    }
  }

  const teams = effective ? teamsOf(scoped, effective, previous, teamFunctions, view === 'function' && input.functionName === 'Marketing', monthly, rangeMonths, input.teamConfigs, unlevelMonthly) : [];
  const functions = effective ? functionCards(scoped, effective, previous, teamFunctions, monthly, rangeMonths) : [];
  // The company or function comparison is per month; a range does not compare with it.
  const comparison = input.comparisonRecords && effective && !range
    ? applyFilters(input.comparisonRecords, { ...input, filters: { region: input.filters.region, branch: input.filters.branch, performanceLevel: input.filters.performanceLevel } }, teamFunctions)
    : null;

  // Comparison line: managerial = function average, function = company average.
  let comparisonBlock: ExecutiveSummary['hero']['comparison'] = null;
  let comparisonTrend: Array<number | null> | null = null;
  if (view === 'managerial') {
    const fn = managerFunction;
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

  // The score trend stays monthly; in range mode the months inside the range are flagged.
  const trend: ExecutiveTrendPoint[] = effective
    ? trendOf(monthly, effective).map((point, index) => ({
      ...point,
      comparison_score: comparisonTrend?.[index] ?? null,
      target: TARGET,
      basis_context: basisFor(monthly, point.period),
      ...(rangeMonths ? { in_range: rangeMonths.some((month) => month.key === point.period.key) } : {}),
    }))
    : [];

  if (view === 'managerial' && input.team && !rangeMonths) {
    const mgrConfig = findTeamConfig(input.teamConfigs, input.team);
    const isPreApprovalsTeam = input.team === 'Pre-Approvals IP'
      || input.team === 'Pre-Approvals IP Offshore'
      || isPreApprovalsSubTeam(input.team)
      || sameEgyptRcmTeam(input.team, 'Pre-Approvals IP');
    if (mgrConfig && !isMergedBranchTeam(input.team)) {
      trend.forEach((point) => {
        if (point.period.key === effective?.key) {
          point.score = score;
        } else if (previous && point.period.key === previous.key) {
          point.score = previousScore;
        } else if (point.score !== null) {
          const periodLeader = isPreApprovalsTeam
            ? preApprovalsLeaderTeamTotal(inPeriod(unlevelMonthly, point.period).filter((record) => record.team === input.team))
            : null;
          if (periodLeader !== null) {
            point.score = periodLeader;
          } else {
            const mRecords = inPeriod(monthly, point.period);
            const mAgents = mRecords.map((r) => r.rawAgent).filter((a): a is AgentRecord => Boolean(a));
            if (mAgents.length > 0) {
              const canonical = calculateAggregatedTeamPerformance(mAgents, mgrConfig)?.score ?? null;
              if (canonical !== null) {
                point.score = round1(displayedTeamScore(canonical, point.score ?? 0, recordsUseAppliedPin(mAgents)));
              }
            }
          }
        }
      });
    }
  }

  const rawSplit = input.deriveScopedDrivers ? scopedRecordDrivers(current, before, teamFunctions) : input.drivers
    ? mapDrivers(input.drivers.drivers, input.drivers.items, teamFunctions, view === 'function' ? Number.POSITIVE_INFINITY : 3)
    : null;
  // Function view: Insights' function filter is overlapping, Executive membership is disjoint.
  // Managerial: drivers outside the viewer's teams never show, even if Insights returns them.
  const teamInScope = (team: string | null) => !input.teamScope || (team !== null && input.teamScope.some((allowed) => summaryTeamMatches(team, allowed)));
  const managerSplit = rawSplit && view === 'managerial' && input.teamScope
    ? { ...rawSplit, negative: rawSplit.negative.filter((driver) => teamInScope(driver.team)), positive: rawSplit.positive.filter((driver) => teamInScope(driver.team)) }
    : rawSplit;
  const driverSplit = managerSplit && view === 'function' && input.functionName
    ? {
      ...managerSplit,
      negative: managerSplit.negative.filter((driver) => input.functionName === 'Pre-Approvals' ? teamBelongsToFunction(driver.team ?? '', 'Pre-Approvals') : driver.function === input.functionName).slice(0, 3),
      positive: managerSplit.positive.filter((driver) => input.functionName === 'Pre-Approvals' ? teamBelongsToFunction(driver.team ?? '', 'Pre-Approvals') : driver.function === input.functionName).slice(0, 3),
    }
    : managerSplit;
  if (!driverSplit) unavailable.add('drivers');
  else if (!driverSplit.hasWeightedGap) unavailable.add('drivers_weighted_gap');

  const kpis = kpiRows(current, before, range ? { range: true } : undefined);
  if (!kpis.length) unavailable.add('kpis');
  const grades = gradeDistribution(current, before);
  if (!grades) unavailable.add('grade_mix');
  const actions = input.actions ? summarizeActions(input.actions, input.today, effective, input.pendingActions ?? [], rangeMonths?.map((month) => month.key)) : null;
  if (!actions) unavailable.add('corrective_actions');

  // Function view: "most improved" compares against the other functions, which
  // needs all-teams records; without them, never claim it.
  if (view === 'function') {
    const leader = comparison && effective ? functionCards(comparison, effective, previous, teamFunctions).find((card) => card.is_most_improved) : null;
    functions.forEach((card) => { card.is_most_improved = Boolean(leader && leader.function === card.function); });
  }
  const mostImproved = functions.find((card) => card.is_most_improved) ?? null;
  const lowestTeam = view === 'function' ? teams.find((team) => team.flags.includes('lowest_in_function')) ?? null : null;
  stampGapShares(functions);
  functions.forEach((card) => {
    card.score_basis = 'people_average';
    card.lowest_team = lowestTeamOf(teams, card.function);
  });
  functions.sort(byGapShare);
  const worstFunction = functions.find((card) => card.score !== null) ?? null;
  const matchedDriver = worstFunction
    ? driverSplit?.negative.find((driver) => driver.function === worstFunction.function) ?? null
    : null;
  const drag = matchedDriver;

  const label = view === 'managerial' ? (input.team ?? 'Your teams') : view === 'function' ? (input.functionName ?? 'Function') : 'Company';
  return {
    period: {
      requested,
      effective,
      previous,
      fallback_applied: fallbackApplied,
      notice: fallbackApplied && requested && effective
        ? `No performance data for ${formatPeriod(requested)} yet — showing ${formatPeriod(effective)}, the latest month with data.`
        : null,
      ...(rangeBlock ? { range: rangeBlock } : {}),
    },
    data_status: { has_data: range ? rangeCurrent.length > 0 : periods.length > 0, last_upload: null, effective_uploaded_at: null },
    scope: {
      view,
      role: input.role,
      locked: { region: view === 'managerial', function: view === 'managerial', team: view === 'managerial' },
      team: view === 'managerial' ? input.team ?? null : input.filters.team ?? null,
      function: view === 'function' ? input.functionName ?? null : (view === 'managerial' ? managerFunction : input.filters.teamFunction ?? null),
      region: view === 'managerial' ? ([...new Set(current.map((record) => record.region).filter(Boolean))][0] ?? null) : input.filters.region ?? null,
      accessible_functions: input.accessibleFunctions ?? [...EXECUTIVE_FUNCTIONS],
      branch: input.filters.branch ?? null,
      performance_level: input.filters.performanceLevel ?? null,
      position: input.filters.position ?? null,
    },
    hero: {
      label,
      score,
      previous_score: previousScore,
      change: diff(score, previousScore),
      gap: score === null ? null : round1(score - TARGET),
      target: TARGET,
      grade: getGradeClassOrNull(score),
      score_basis: scoreBasis,
      employees: employeesOf(current),
      teams_count: new Set(current.map((record) => record.team)).size,
      functions_count: functions.length,
      story: {
        headline: null,
        biggest_drag: worstFunction ? {
          function: worstFunction.function,
          team: drag?.team ?? worstFunction.lowest_team?.team ?? null,
          kpi_key: drag?.kpi_key ?? null,
          kpi_label: drag?.kpi_label ?? null,
          share_percent: worstFunction.gap_share_percent ?? null,
          score: worstFunction.score,
          cause: drag ? null : worstFunction.lowest_team?.kpi ?? null,
        } : null,
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
    people: people(current, before),
    highlights: {
      most_improved: mostImproved && mostImproved.change !== null ? { type: 'function', name: mostImproved.function, change: mostImproved.change } : null,
      lowest_in_function: lowestTeam && lowestTeam.function && lowestTeam.score !== null
        ? { team: lowestTeam.team, function: lowestTeam.function, score: lowestTeam.score }
        : null,
    },
    corrective_actions: actions,
    // Same comparison the composed team, function and trend notes use, for the selected month on this scope.
    basis_context: effective ? (rangeMonths ? basisForScope(monthly, effective, rangeMonths) : basisFor(scoped, effective)) : null,
    periods,
    meta: {
      source: 'composed',
      unavailable: [...unavailable],
      driver_metric: driverSplit?.metric ?? 'contribution_change',
    },
  };
}
