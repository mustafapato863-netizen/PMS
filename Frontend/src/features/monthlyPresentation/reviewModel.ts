/**
 * Monthly Performance Review calculations.
 * Records and actions passed in are already limited to one region and the
 * three (records) or two (actions) months the page fetched. This module does
 * not fetch, and it does not invent a month when the locked month is empty.
 */
import { GRADE_CLASSES, getGradeClass, getGradeClassOrNull, type GradeClass } from '../../constants/grades';
import {
  MONTHS, SUMMARY_BRANCHES, composeExecutiveSummary, localIsoDate, normalizeRegion, periodFromKey as execPeriodFromKey,
  type ExecRecord,
} from '../executive/compose';
import { EXECUTIVE_FUNCTIONS, executiveFunctionForTeam, summaryFunctionMatches, summaryTeamMatches } from '../executive/functions';
import type { TeamFunctionMap } from '../insights/filterCascade';
import type { InsightDriver, InsightItem } from '../insights/types';
import type { TeamConfig } from '../../schemas/teamConfig.schema';
import type { ExecutiveFunction, ExecutiveSummary, ExecutiveView } from '../executive/types';
import { MASKED_DETAILS_LABEL, nameMasker, type LockedPeriod, type RegionCode } from './model';

export const REVIEW_SECTIONS = [
  'summary', 'executive_story', 'comparison', 'performance_drivers', 'kpi_diagnosis', 'team_summaries', 'overall_trend', 'options',
] as const;

const GRADE_RANK: Record<GradeClass, number> = { A: 0, B: 1, C: 2, D: 3, E: 4 };
const STATUS_RANK = { overdue: 0, no_decision: 1, open: 2, in_progress: 3, completed: 4, cancelled: 5 } as const;

export type DecisionStatus = keyof typeof STATUS_RANK;
export type Outcome = 'Improved' | 'Unchanged' | 'Declined' | 'not_scored';

export interface ReviewAction {
  id: string;
  employeeId: string | null;
  employeeName: string | null;
  team: string | null;
  position: string | null;
  month: string | null;
  year: number | null;
  actionType: string | null;
  actionText: string | null;
  rootCause: string | null;
  ownerId: string | null;
  ownerName: string | null;
  priority: string | null;
  status: string | null;
  followUpState: string | null;
  dueDate: string | null;
  evidence: string | null;
  createdAt: string | null;
  completedAt: string | null;
}

export interface RegisterRow {
  employeeId: string;
  name: string;
  team: string;
  /** Role, when the person has one. Marketing cards count below-target rows by this. */
  position: string | null;
  score: number;
  grade: GradeClass;
  change: number | null;
  worst: { label: string; actual: number; target: number; ratio: number } | null;
  rootCause: string | null;
  decisionType: string | null;
  decisionText: string | null;
  owner: string | null;
  priority: string | null;
  status: DecisionStatus;
  dueDate: string | null;
  evidence: string | null;
  primary: ReviewAction | null;
  actions: ReviewAction[];
  earlier: ReviewAction[];
  kpis: ExecRecord['kpis'];
  history: Array<{ key: string; label: string; score: number | null; grade: GradeClass | null }>;
}

export interface Coverage {
  total: number;
  peopleWithDecision: number;
  open: number;
  inProgress: number;
  completed: number;
  overdue: number;
  noDecision: number;
  coveragePercent: number | null;
}

export interface EffectRow {
  id: string;
  employeeId: string | null;
  name: string;
  type: string;
  before: number | null;
  after: number | null;
  outcome: Outcome;
}

export interface EffectSummary {
  rows: EffectRow[];
  byType: Array<{ type: string; improved: number; scored: number; rate: number | null }>;
}

export interface RepeatRow {
  employeeId: string;
  name: string;
  team: string;
  streak: 2 | 3;
  scores: Array<{ label: string; score: number }>;
}

export interface GradeMove {
  employeeId: string;
  name: string;
  team: string;
  from: GradeClass;
  to: GradeClass;
}

/** People scored in both months, counted from last month's grade to this month's grade. */
export type GradeMatrix = Record<GradeClass, Record<GradeClass, number>>;

export function emptyGradeMatrix(): GradeMatrix {
  return Object.fromEntries(GRADE_CLASSES.map((from) => [from, Object.fromEntries(GRADE_CLASSES.map((to) => [to, 0]))])) as GradeMatrix;
}

export interface OwnerRow {
  owner: string;
  decisions: number;
  closedOnTime: number;
  overdue: number;
  averageDays: number | null;
}

export interface BranchRow {
  value: string;
  label: string;
  score: number | null;
  change: number | null;
  employees: number;
}

export interface MonthClose {
  results: string[];
  problems: string[];
  decisions: string[];
}

export interface MonthlyReview {
  summary: ExecutiveSummary;
  emptyMonth: boolean;
  actionsReady: boolean;
  rows: RegisterRow[];
  coverage: Coverage | null;
  effects: EffectSummary;
  repeats: RepeatRow[];
  up: GradeMove[];
  down: GradeMove[];
  matrix: GradeMatrix;
  top: Array<{ employeeId: string; name: string; team: string; score: number; grade: GradeClass }>;
  rewards: ReviewAction[];
  owners: OwnerRow[];
  branches: BranchRow[];
  close: MonthClose;
  people: number;
}

interface RawFollowUp {
  id?: string | number | null;
  employee_id?: string | null;
  employee_name?: string | null;
  team?: string | null;
  position?: string | null;
  month?: string | null;
  year?: number | string | null;
  status?: string | null;
  priority?: string | null;
  due_date?: string | null;
  owner?: { id?: string | null; name?: string | null } | null;
  completion_note?: string | null;
  completed_at?: string | null;
  follow_up_state?: string | null;
  timestamp?: string | null;
  created_at?: string | null;
  manager_action?: string | null;
  manager_notes?: string | null;
  root_cause?: string | null;
  suggested_action?: string | null;
}

const blank = (value: unknown): string | null => {
  const text = String(value ?? '').trim();
  if (!text || text.toLowerCase() === 'none' || text.toLowerCase() === 'nan') return null;
  return text;
};

const round1 = (value: number) => Math.round(value * 10) / 10;

const mean = (values: number[]) => (values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null);

export function summaryRecordsUrl(region: string, year: number, month: string): string {
  const regionKey = region.trim();
  const monthKey = month.trim();
  if (!regionKey || !Number.isInteger(year) || year < 1900 || !monthKey) {
    throw new Error('summary-records requires region, year and month');
  }
  return `/api/performance/summary-records?${new URLSearchParams({ region: regionKey, year: String(year), month: monthKey })}`;
}

export function followUpUrl(region: string, month: string): string {
  const regionKey = region.trim();
  const monthKey = month.trim();
  if (!regionKey || !monthKey) throw new Error('follow-up requires region and month');
  return `/api/corrective-actions/follow-up?${new URLSearchParams({ region: regionKey, month: monthKey })}`;
}

export function isBelowTarget(score: number | null | undefined): boolean {
  const grade = getGradeClassOrNull(score);
  return grade === 'C' || grade === 'D' || grade === 'E';
}

export function decisionStatus(action: ReviewAction | null, today: Date): DecisionStatus {
  if (!action) return 'no_decision';
  const open = action.status === 'Open' || action.status === 'In Progress';
  const due = action.dueDate ? action.dueDate.slice(0, 10) : null;
  if (action.followUpState === 'overdue' || (open && due !== null && due < localIsoDate(today))) return 'overdue';
  if (action.status === 'Completed') return 'completed';
  if (action.status === 'Cancelled') return 'cancelled';
  if (action.status === 'In Progress') return 'in_progress';
  return 'open';
}

export function mapReviewAction(item: RawFollowUp, index = 0): ReviewAction {
  const raw = String(item.manager_action ?? '');
  const sep = raw.indexOf(': ');
  const actionType = blank(item.suggested_action) ?? (sep > 0 ? blank(raw.slice(0, sep)) : null);
  const actionText = sep > 0 ? blank(raw.slice(sep + 2)) : blank(raw);
  const year = item.year == null || item.year === '' ? null : Number(item.year);
  return {
    id: String(item.id ?? `action-${index}`),
    employeeId: blank(item.employee_id),
    employeeName: blank(item.employee_name),
    team: blank(item.team),
    position: blank(item.position),
    month: blank(item.month),
    year: year != null && Number.isFinite(year) ? year : null,
    actionType,
    actionText,
    rootCause: blank(item.manager_notes) ?? blank(item.root_cause),
    ownerId: blank(item.owner?.id),
    ownerName: blank(item.owner?.name),
    priority: blank(item.priority),
    status: blank(item.status),
    followUpState: blank(item.follow_up_state),
    dueDate: blank(item.due_date),
    evidence: blank(item.completion_note),
    createdAt: blank(item.timestamp) ?? blank(item.created_at),
    completedAt: blank(item.completed_at),
  };
}

/** Seed aliases from a sorted name list so masking does not depend on render order. */
export function reviewMask(names: Array<string | null | undefined>, enabled: boolean) {
  if (!enabled) return (name: string | null | undefined) => blank(name) ?? '—';
  const mask = nameMasker();
  [...new Set(names.map((name) => blank(name)).filter((name): name is string => Boolean(name)))]
    .sort((a, b) => a.localeCompare(b))
    .forEach((name) => { mask(name); });
  return mask;
}

export function maskedDetail(value: string | null | undefined, masked: boolean): string {
  if (!blank(value)) return '—';
  return masked ? MASKED_DETAILS_LABEL : blank(value)!;
}

function periodKeyOf(action: ReviewAction): string | null {
  if (action.year == null || !action.month) return null;
  const index = MONTHS.findIndex((month) => month.toLowerCase() === action.month!.toLowerCase());
  if (index < 0) return null;
  return `${action.year}-${String(index + 1).padStart(2, '0')}`;
}

function asFunction(name: string | null | undefined): ExecutiveFunction | null {
  return EXECUTIVE_FUNCTIONS.find((fn) => fn === name) ?? null;
}

function scoreOn(records: Map<string, ExecRecord> | undefined, key: string): number | null {
  const score = records?.get(key)?.score;
  return score == null || !Number.isFinite(score) ? null : score;
}

export function outcomeOf(before: number | null, after: number | null): Outcome {
  if (before == null || after == null || !Number.isFinite(before) || !Number.isFinite(after)) return 'not_scored';
  const left = round1(before);
  const right = round1(after);
  if (right > left) return 'Improved';
  if (right < left) return 'Declined';
  return 'Unchanged';
}

function worstKpi(record: ExecRecord | undefined): RegisterRow['worst'] {
  const kpis = (record?.kpis ?? []).filter((kpi) => Number.isFinite(kpi.achievement_ratio));
  if (!kpis.length) return null;
  const worst = [...kpis].sort((a, b) => a.achievement_ratio - b.achievement_ratio || a.label.localeCompare(b.label))[0];
  return { label: worst.label || worst.kpi_key, actual: worst.actual_value, target: worst.target_value, ratio: worst.achievement_ratio };
}

function compareActions(left: ReviewAction, right: ReviewAction, today: Date): number {
  return STATUS_RANK[decisionStatus(left, today)] - STATUS_RANK[decisionStatus(right, today)]
    || String(left.dueDate ?? '9999-99-99').localeCompare(String(right.dueDate ?? '9999-99-99'))
    || left.id.localeCompare(right.id);
}

function daysBetween(start: string | null, end: string | null): number | null {
  if (!start || !end) return null;
  const from = Date.parse(start);
  const to = Date.parse(end);
  if (!Number.isFinite(from) || !Number.isFinite(to)) return null;
  return (to - from) / 86_400_000;
}

function teamInSelection(teamName: string | null, fn: string | null, team: string | null, teamFunctions?: TeamFunctionMap): boolean {
  if (!teamName) return false;
  if (team) return summaryTeamMatches(teamName, team);
  if (fn) return summaryFunctionMatches(teamName, fn, teamFunctions);
  return true;
}

function recordInSelection(record: ExecRecord, fn: string | null, team: string | null, position: string | null, teamFunctions?: TeamFunctionMap): boolean {
  if (position) {
    if (record.position !== position) return false;
    if (fn && !summaryFunctionMatches(record.team, fn, teamFunctions)) return false;
    if (team && !summaryTeamMatches(record.team, team)) return false;
    return true;
  }
  return teamInSelection(record.team, fn, team, teamFunctions);
}

function actionInScope(
  action: ReviewAction,
  employeeIds: Set<string>,
  fn: string | null,
  team: string | null,
  position: string | null,
  teamFunctions?: TeamFunctionMap,
): boolean {
  if (action.employeeId) return employeeIds.has(action.employeeId);
  if (position) {
    if (action.position && action.position === position) return true;
    if (action.team && (action.team === position || summaryTeamMatches(action.team, position))) return true;
    return false;
  }
  return teamInSelection(action.team, fn, team, teamFunctions);
}

function scopeTeam(scope: string | null | undefined): string | null {
  const [team] = String(scope ?? '').split(' · ');
  return blank(team);
}

/**
 * Insights was already limited to this team or function. Keep a driver that
 * arrived without a team, and drop one whose team sits outside the selection.
 * Compose still applies its own team filter, so a missing team is stamped here.
 */
export function prepareReviewDrivers<T extends InsightDriver>(
  drivers: T[],
  items: InsightItem[],
  selection: { fn: string | null; team: string | null },
  teamFunctions?: TeamFunctionMap,
): { drivers: T[]; items: InsightItem[] } {
  const team = selection.team?.trim() || null;
  const fn = selection.fn?.trim() || null;
  if (!team && !fn) return { drivers, items };
  const itemById = new Map(items.map((item) => [item.id, item]));
  const stamps = new Map<string, string>();
  const kept = drivers.flatMap((driver) => {
    const item = itemById.get(driver.insight_id);
    const known = blank(item?.team) ?? scopeTeam(driver.scope);
    if (known) {
      if (team) return summaryTeamMatches(known, team) ? [driver] : [];
      if (fn && executiveFunctionForTeam(known, teamFunctions) !== fn) return [];
      return [driver];
    }
    const stamp = team ?? fn;
    if (!stamp) return [driver];
    stamps.set(driver.insight_id, stamp);
    return [{ ...driver, scope: stamp }];
  });
  return {
    drivers: kept,
    items: items.map((item) => (stamps.has(item.id) ? { ...item, team: stamps.get(item.id)! } : item)),
  };
}

function indexRecords(records: ExecRecord[]): Map<string, Map<string, ExecRecord>> {
  const map = new Map<string, Map<string, ExecRecord>>();
  records.forEach((record) => {
    const byPeriod = map.get(record.employeeId) ?? new Map<string, ExecRecord>();
    byPeriod.set(record.period.key, record);
    map.set(record.employeeId, byPeriod);
  });
  return map;
}

function coverageOf(rows: RegisterRow[], actions: ReviewAction[], today: Date): Coverage {
  const statuses = actions.map((action) => decisionStatus(action, today));
  const peopleWithDecision = rows.filter((row) => row.status !== 'no_decision').length;
  return {
    total: actions.length,
    peopleWithDecision,
    open: statuses.filter((status) => status === 'open').length,
    inProgress: statuses.filter((status) => status === 'in_progress').length,
    completed: statuses.filter((status) => status === 'completed').length,
    overdue: statuses.filter((status) => status === 'overdue').length,
    noDecision: rows.filter((row) => row.status === 'no_decision').length,
    coveragePercent: rows.length ? round1((peopleWithDecision / rows.length) * 100) : null,
  };
}

function effectivenessOf(actions: ReviewAction[], byEmployee: Map<string, Map<string, ExecRecord>>, previousKey: string, selectedKey: string): EffectSummary {
  const rows = actions.filter((action) => action.employeeId).map((action) => {
    const history = byEmployee.get(action.employeeId!);
    const before = scoreOn(history, previousKey);
    const after = scoreOn(history, selectedKey);
    return {
      id: action.id,
      employeeId: action.employeeId,
      name: action.employeeName ?? history?.get(selectedKey)?.name ?? history?.get(previousKey)?.name ?? action.employeeId!,
      type: action.actionType ?? 'Decision',
      before, after, outcome: outcomeOf(before, after),
    };
  });
  const types = [...new Set(rows.map((row) => row.type))].sort((a, b) => a.localeCompare(b));
  return {
    rows,
    byType: types.map((type) => {
      const group = rows.filter((row) => row.type === type);
      const scored = group.filter((row) => row.outcome !== 'not_scored');
      const improved = scored.filter((row) => row.outcome === 'Improved').length;
      return { type, improved, scored: scored.length, rate: scored.length ? round1((improved / scored.length) * 100) : null };
    }),
  };
}

function repeatsOf(current: ExecRecord[], byEmployee: Map<string, Map<string, ExecRecord>>, keys: [string, string, string], labels: [string, string, string]): RepeatRow[] {
  return current.flatMap((record) => {
    if (!isBelowTarget(record.score)) return [];
    const history = byEmployee.get(record.employeeId);
    const previous = scoreOn(history, keys[1]);
    if (!isBelowTarget(previous)) return [];
    const older = scoreOn(history, keys[2]);
    const streak: 2 | 3 = isBelowTarget(older) ? 3 : 2;
    const scores = [
      ...(streak === 3 && older != null ? [{ label: labels[2], score: older }] : []),
      { label: labels[1], score: previous! },
      { label: labels[0], score: record.score },
    ];
    return [{ employeeId: record.employeeId, name: record.name, team: record.team, streak, scores }];
  }).sort((a, b) => b.streak - a.streak || a.name.localeCompare(b.name));
}

function movementOf(current: ExecRecord[], byEmployee: Map<string, Map<string, ExecRecord>>, previousKey: string): { up: GradeMove[]; down: GradeMove[]; matrix: GradeMatrix } {
  const up: GradeMove[] = [];
  const down: GradeMove[] = [];
  const matrix = emptyGradeMatrix();
  current.forEach((record) => {
    const previousScore = scoreOn(byEmployee.get(record.employeeId), previousKey);
    const from = getGradeClassOrNull(previousScore);
    const to = getGradeClassOrNull(record.score);
    if (!from || !to) return;
    matrix[from][to] += 1;
    if (from === to) return;
    const move = { employeeId: record.employeeId, name: record.name, team: record.team, from, to };
    if (GRADE_RANK[to] < GRADE_RANK[from]) up.push(move);
    else down.push(move);
  });
  up.sort((a, b) => a.name.localeCompare(b.name));
  down.sort((a, b) => a.name.localeCompare(b.name));
  return { up, down, matrix };
}

function ownersOf(actions: ReviewAction[], today: Date): OwnerRow[] {
  const groups = new Map<string, ReviewAction[]>();
  actions.forEach((action) => {
    const owner = action.ownerName ?? 'Unassigned';
    groups.set(owner, [...(groups.get(owner) ?? []), action]);
  });
  return [...groups.entries()].map(([owner, rows]) => {
    const closedOnTime = rows.filter((action) => {
      if (action.status !== 'Completed') return false;
      if (!action.dueDate) return true;
      const completed = action.completedAt?.slice(0, 10);
      return Boolean(completed && completed <= action.dueDate.slice(0, 10));
    }).length;
    const spans = rows
      .filter((action) => action.status === 'Completed')
      .map((action) => daysBetween(action.createdAt, action.completedAt))
      .filter((days): days is number => days != null);
    return {
      owner,
      decisions: rows.length,
      closedOnTime,
      overdue: rows.filter((action) => decisionStatus(action, today) === 'overdue').length,
      averageDays: spans.length ? round1(spans.reduce((sum, days) => sum + days, 0) / spans.length) : null,
    };
  }).sort((a, b) => b.overdue - a.overdue || b.decisions - a.decisions || a.owner.localeCompare(b.owner));
}

function branchesOf(records: ExecRecord[], code: RegionCode, selectedKey: string, previousKey: string): BranchRow[] {
  if (code !== 'UAE') return [];
  return SUMMARY_BRANCHES.map((branch) => {
    const current = records.filter((record) => record.period.key === selectedKey && record.branches?.includes(branch.value)).map((record) => record.score);
    const previous = records.filter((record) => record.period.key === previousKey && record.branches?.includes(branch.value)).map((record) => record.score);
    const score = mean(current);
    const before = mean(previous);
    return {
      value: branch.value,
      label: branch.label,
      score: score == null ? null : round1(score),
      change: score == null || before == null ? null : round1(score - before),
      employees: current.length,
    };
  });
}

function isReward(action: ReviewAction): boolean {
  const type = (action.actionType ?? '').trim().toLowerCase();
  return type === 'reward' || type === 'promotion';
}

function closeOf(summary: ExecutiveSummary, below: number, repeats: number, coverage: Coverage | null, actionsReady: boolean): MonthClose {
  const { hero } = summary;
  const grade = hero.grade ?? 'no grade';
  const compared = summary.period.previous;
  const lockedKey = summary.period.effective?.key ?? summary.period.requested?.key ?? null;
  const calendarKey = lockedKey ? shiftKey(lockedKey, -1) : null;
  const movement = hero.change == null || !compared
    ? 'There is no score for the previous month.'
    : `The score moved ${hero.change > 0 ? '+' : ''}${hero.change.toFixed(1)} points ${compared.key === calendarKey ? 'versus last month' : `versus ${compared.month} ${compared.year}`}.`;
  const results = [
    hero.score == null ? `${hero.label} has no score for this month.` : `${hero.label} scored ${hero.score.toFixed(1)}% (${grade}).`,
    movement,
    `${hero.employees} ${hero.employees === 1 ? 'person' : 'people'} evaluated.`,
  ];
  const drag = summary.drivers.negative[0];
  const problems = [
    drag ? `${drag.kpi_label} is the largest drag on the score.` : 'No KPI driver is available for this month.',
    `${below} ${below === 1 ? 'employee is' : 'employees are'} below target (grade C or lower).`,
    `${repeats} ${repeats === 1 ? 'employee has' : 'employees have'} been below target for at least two months in a row.`,
  ];
  const decisions = !actionsReady || !coverage
    ? ['Decisions are not available yet.']
    : [
      coverage.coveragePercent == null ? 'Nobody is below target, so decision coverage does not apply.' : `Decision coverage is ${coverage.coveragePercent.toFixed(1)}%.`,
      `${coverage.noDecision} below target with no decision yet.`,
      `${coverage.overdue} ${coverage.overdue === 1 ? 'decision is' : 'decisions are'} overdue.`,
    ];
  return { results, problems, decisions };
}

export interface BuildReviewInput {
  code: RegionCode;
  period: LockedPeriod;
  records: ExecRecord[];
  /** Null while follow-up is still loading or has failed. An empty array means the month has no actions. */
  actions: ReviewAction[] | null;
  fn: string | null;
  team: string | null;
  /** Marketing role. When set, the review stays a function view and does not look up a team with this name. */
  position?: string | null;
  teamFunctions?: TeamFunctionMap;
  teamConfigs?: TeamConfig[];
  drivers?: { drivers: InsightDriver[]; items: InsightItem[] } | null;
  role: string;
  today: Date;
}

export function buildMonthlyReview(input: BuildReviewInput): MonthlyReview {
  const functionName = asFunction(input.fn);
  const positionName = input.position?.trim() || null;
  const teamName = positionName ? null : (input.team?.trim() || null);
  const view: ExecutiveView = teamName ? 'managerial' : functionName ? 'function' : 'corporate';
  const regionRecords = input.records.filter((record) => normalizeRegion(record.region) === input.code);
  const summary = composeExecutiveSummary({
    view,
    role: input.role,
    records: regionRecords,
    comparisonRecords: regionRecords,
    filters: { region: input.code, ...(positionName ? { position: positionName } : {}) },
    requestedPeriodKey: input.period.key,
    team: teamName,
    teamScope: view === 'managerial' && teamName ? [teamName] : null,
    functionName,
    teamFunctions: input.teamFunctions,
    teamConfigs: input.teamConfigs,
    drivers: input.drivers ?? null,
    today: input.today,
  });
  const emptyMonth = summary.period.fallback_applied || summary.period.effective?.key !== input.period.key;
  const previous = execPeriodFromKey(shiftKey(input.period.key, -1));
  const older = execPeriodFromKey(shiftKey(input.period.key, -2));
  const blankReview = (ready: boolean): MonthlyReview => ({
    summary, emptyMonth: true, actionsReady: ready, rows: [], coverage: null, effects: { rows: [], byType: [] },
    repeats: [], up: [], down: [], matrix: emptyGradeMatrix(), top: [], rewards: [], owners: [], branches: [], people: 0,
    close: closeOf(summary, 0, 0, null, false),
  });
  if (emptyMonth || !previous || !older) return blankReview(input.actions != null);

  const scoped = regionRecords.filter((record) => recordInSelection(record, functionName, teamName, positionName, input.teamFunctions));
  const byEmployee = indexRecords(scoped);
  const selectedKey = input.period.key;
  const current = scoped.filter((record) => record.period.key === selectedKey);
  const actionsReady = input.actions != null;
  const idsIn = (key: string) => new Set(scoped.filter((record) => record.period.key === key).map((record) => record.employeeId));
  const inMonth = (key: string) => (input.actions ?? []).filter((action) => periodKeyOf(action) === key && actionInScope(action, idsIn(key), functionName, teamName, positionName, input.teamFunctions));
  const currentActions = actionsReady ? inMonth(selectedKey) : [];
  const earlierActions = actionsReady ? inMonth(previous.key) : [];
  const byPerson = new Map<string, ReviewAction[]>();
  currentActions.forEach((action) => {
    if (!action.employeeId) return;
    byPerson.set(action.employeeId, [...(byPerson.get(action.employeeId) ?? []), action]);
  });
  const earlierByPerson = new Map<string, ReviewAction[]>();
  earlierActions.forEach((action) => {
    if (!action.employeeId) return;
    earlierByPerson.set(action.employeeId, [...(earlierByPerson.get(action.employeeId) ?? []), action]);
  });
  const keys: [string, string, string] = [selectedKey, previous.key, older.key];
  const labels: [string, string, string] = [input.period.short, previous.month.slice(0, 3), older.month.slice(0, 3)];
  const rows = current.filter((record) => isBelowTarget(record.score)).map((record) => {
    const actions = [...(byPerson.get(record.employeeId) ?? [])].sort((a, b) => compareActions(a, b, input.today));
    const primary = actions[0] ?? null;
    const history = byEmployee.get(record.employeeId);
    const previousScore = scoreOn(history, previous.key);
    return {
      employeeId: record.employeeId,
      name: record.name,
      team: record.team,
      position: record.position,
      score: record.score,
      grade: getGradeClass(record.score),
      change: previousScore == null ? null : round1(record.score - previousScore),
      worst: worstKpi(record),
      rootCause: primary?.rootCause ?? null,
      decisionType: primary?.actionType ?? null,
      decisionText: primary?.actionText ?? null,
      owner: primary?.ownerName ?? null,
      priority: primary?.priority ?? null,
      status: decisionStatus(primary, input.today),
      dueDate: primary?.dueDate ?? null,
      evidence: primary?.evidence ?? null,
      primary,
      actions,
      earlier: earlierByPerson.get(record.employeeId) ?? [],
      kpis: record.kpis,
      history: keys.map((key, index) => {
        const score = scoreOn(history, key);
        return { key, label: labels[index], score, grade: getGradeClassOrNull(score) };
      }),
    };
  }).sort((a, b) => STATUS_RANK[a.status] - STATUS_RANK[b.status] || a.name.localeCompare(b.name));

  const registerActions = rows.flatMap((row) => row.actions);
  const coverage = actionsReady ? coverageOf(rows, registerActions, input.today) : null;
  const { up, down, matrix } = movementOf(current, byEmployee, previous.key);
  const repeats = repeatsOf(current, byEmployee, keys, labels);
  const top = current
    .filter((record) => { const grade = getGradeClassOrNull(record.score); return grade === 'A' || grade === 'B'; })
    .map((record) => ({ employeeId: record.employeeId, name: record.name, team: record.team, score: record.score, grade: getGradeClass(record.score) }))
    .sort((a, b) => b.score - a.score || a.name.localeCompare(b.name));
  const heroLabel = teamName ?? positionName ?? functionName ?? (input.code === 'UAE' ? 'UAE' : 'Egypt');
  const labelled = { ...summary, hero: { ...summary.hero, label: heroLabel } };
  return {
    summary: labelled,
    emptyMonth: false,
    actionsReady,
    rows,
    coverage,
    effects: actionsReady ? effectivenessOf(earlierActions, byEmployee, previous.key, selectedKey) : { rows: [], byType: [] },
    repeats,
    up, down, matrix, top,
    rewards: currentActions.filter(isReward),
    owners: actionsReady ? ownersOf(currentActions, input.today) : [],
    branches: branchesOf(scoped, input.code, selectedKey, previous.key),
    close: closeOf(labelled, rows.length, repeats.length, coverage, actionsReady),
    people: labelled.hero.employees,
  };
}

function shiftKey(key: string, delta: number): string {
  const period = execPeriodFromKey(key);
  if (!period) return key;
  const absolute = period.year * 12 + MONTHS.indexOf(period.month) + delta;
  const year = Math.floor(absolute / 12);
  const month = ((absolute % 12) + 12) % 12;
  return `${year}-${String(month + 1).padStart(2, '0')}`;
}

export function cascadeOptions(records: ExecRecord[], selectedKey: string, fn: string | null, teamFunctions?: TeamFunctionMap) {
  const current = records.filter((record) => record.period.key === selectedKey);
  const functions = [...new Set(current.map((record) => executiveFunctionForTeam(record.team, teamFunctions)).filter((name): name is ExecutiveFunction => name != null))]
    .sort((a, b) => a.localeCompare(b));
  const teams = [...new Set(current.filter((record) => !fn || summaryFunctionMatches(record.team, fn, teamFunctions)).map((record) => record.team))]
    .sort((a, b) => a.localeCompare(b));
  return { functions, teams };
}
