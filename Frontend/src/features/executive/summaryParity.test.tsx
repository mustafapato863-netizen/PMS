/**
 * Executive Summary (/executive) and Departmental Summary (/departmental-summary)
 * on one synthetic dataset. This is the permanent contract between the server
 * summary and the browser composition.
 *
 * The Executive page reads the server summary (`/api/performance/summary`, one
 * request per filter set). The Departmental page asks `/api/executive/summary`
 * (not implemented by the backend), then composes the summary in the browser
 * from `/api/performance/summary-records`. The fixture is captured by
 * `Backend/tests/test_summary_parity_capture.py` from a synthetic seed.
 *
 * Three checks, all against the real hooks:
 *  1. Each page's numbers equal its own rule replayed from the same records
 *     (the server rule for Executive, the composed rule for Departmental).
 *  2. Every Executive-versus-Departmental mismatch must be explained by a named
 *     gap that is present in that cell. Anything else fails and prints the table.
 *  3. Each named gap that is still open has an expected-failure assertion
 *     (`it.fails`). Closed gaps are passing assertions.
 */
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import bundleJson from './summary-parity.fixture.json';
import { ApiError } from '../../lib/apiClient';
import { mapBackendAction } from '../../hooks/useActionStore';
import { summarizeRootCauses } from '../../utils/rootCauseInsights';
import { actionAnalyticsStats, actionsInActivePeriod } from './actionAnalytics';
import type { ExecutiveSummary } from './types';

const mocks = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock('../../lib/apiClient', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../lib/apiClient')>(),
  apiFetch: mocks.apiFetch,
}));

type Filters = { region?: string; location?: string; performance_level?: string };
interface EmployeeMonth {
  employee_id: string;
  employee_name?: string;
  team: string;
  month: string;
  year: number;
  region: string | null;
  performance_level: string;
  branch_key: string | null;
  raw_data: Record<string, unknown> | null;
  calls?: { inbound?: number; outbound?: number; total_handled?: number; abandoned?: number };
  geo?: { bookings?: Record<string, number>; attended?: Record<string, number> };
  kpi_values?: Array<{ contribution?: number | null }>;
  evaluation: { score: number; grade: string };
}
interface CorrectiveAction {
  month: string;
  year: number;
  team: string | null;
  employee_id: string | null;
  linked_kpi_key: string | null;
  [key: string]: unknown;
}
interface Bundle {
  periods: string[];
  filter_sets: Filters[];
  catalog: unknown;
  summaries: Record<string, unknown>;
  summary_records: EmployeeMonth[];
  corrective_actions: CorrectiveAction[];
  follow_up: unknown;
}
const bundle = bundleJson as unknown as Bundle;

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const GRADES = ['A', 'B', 'C', 'D', 'E'] as const;
type Grade = (typeof GRADES)[number];
const keyOf = (rec: { year: number; month: string }) => `${rec.year}-${String(MONTHS.indexOf(rec.month) + 1).padStart(2, '0')}`;
const round = (value: number, places: number) => Math.round(value * 10 ** places) / 10 ** places;
const fmt1 = (value: number | null) => (value === null ? '—' : value.toFixed(1));

/* ── Rules as written in the server and the browser ── */

// utils/scoring_rules.py `score_percent`: (0, 1] is a ratio, anything above 1 is already a percentage.
const serverScore = (score: number) => (score > 0 && score <= 1 ? score * 100 : score);
// utils/kpiScore.ts `normalizePerformanceScore` (the browser's scale rule, with its cap at 100).
const composeScore = (score: number) => (!Number.isFinite(score) || score <= 0 ? 0 : score <= 1 ? score * 100 : Math.min(score, 100));
// constants/grades.ts `getGradeClass`, the same cut-offs as utils/scoring_rules.py `letter_grade`.
const thresholdGrade = (score: number): Grade => (score >= 95 ? 'A' : score >= 90 ? 'B' : score >= 80 ? 'C' : score >= 70 ? 'D' : 'E');

// utils/branch_scope.py `text_branch`: raw text in the server's fixed order; the team name counts only for Dubai.
function textBranch(rec: EmployeeMonth): string | null {
  const raw = rec.raw_data ?? {};
  const text = ['Team', 'Out Team', 'Branch', 'Site', 'Area'].map((field) => String(raw[field] ?? '')).filter(Boolean).join(' ').toUpperCase();
  const team = rec.team.toUpperCase();
  if (text.includes('AJM') || text.includes('AJMAN')) return 'ajman';
  if (text.includes('SHJ') || text.includes('SHARJAH') || text.includes('SHARQA')) return 'sharjah';
  if (text.includes('DUBAI') || team.includes('DUBAI')) return 'dubai';
  if (text.includes('CLINIC')) return 'clinics';
  return null;
}
// utils/branch_scope.py `record_matches_branch` (server) and utils/branchScope.ts `agentMatchesLocation` (browser):
// the stored branch_key first, then the text, then the geo activity of that branch.
function branchMatch(rec: EmployeeMonth, location: string): boolean {
  if (location === 'all') return true;
  if (rec.branch_key?.trim()) return rec.branch_key.trim().toLowerCase() === location;
  const explicit = textBranch(rec);
  if (explicit) return explicit === location;
  return (rec.geo?.bookings?.[location] ?? 0) > 0 || (rec.geo?.attended?.[location] ?? 0) > 0;
}

// performance_dashboard_read_service.py `_has_real_activity`, copied here so the test does not call the code it checks.
const serverNumber = (value: unknown) => {
  if (typeof value === 'number') return Number.isFinite(value) ? value : 0;
  if (typeof value === 'boolean') return value ? 1 : 0;
  if (typeof value === 'string') {
    const parsed = Number(value.trim().replace('%', ''));
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
};
function serverActive(rec: EmployeeMonth): boolean {
  if ((rec.employee_name ?? '').trim().toLowerCase() === 'total') return false;
  if (serverNumber(rec.evaluation.score) > 0) return true;
  if ((rec.kpi_values ?? []).some((kpi) => serverNumber(kpi.contribution) > 0)) return true;
  const calls = rec.calls ?? {};
  if ([calls.inbound, calls.outbound, calls.total_handled, calls.abandoned].some((value) => serverNumber(value) > 0)) return true;
  const branches = ['dubai', 'sharjah', 'ajman', 'clinics'];
  if (branches.some((branch) => serverNumber(rec.geo?.bookings?.[branch]) > 0 || serverNumber(rec.geo?.attended?.[branch]) > 0)) return true;
  return Object.values(rec.raw_data ?? {}).some((value) => serverNumber(value) > 0);
}

type Rule = 'server' | 'compose';
interface Replay { headcount: number; avg: number | null; grades: number[] }

/** One page's numbers for one month key, computed from the records by that page's rule. */
function replay(rule: Rule, key: string, filters: Filters): Replay {
  const counted = bundle.summary_records.filter((rec) => keyOf(rec) === key
    && (!filters.region || rec.region === filters.region)
    && (!filters.performance_level || rec.performance_level === filters.performance_level)
    && branchMatch(rec, filters.location ?? 'all')
    && serverActive(rec));
  const scores = counted.map((rec) => (rule === 'server' ? serverScore(rec.evaluation.score) : composeScore(rec.evaluation.score)));
  const mean = scores.length ? scores.reduce((sum, value) => sum + value, 0) / scores.length : null;
  const grades = [0, 0, 0, 0, 0];
  counted.forEach((rec, index) => {
    // The server reports the stored letter; the browser grades the normalised score.
    const letter: Grade = rule === 'server' ? (rec.evaluation.grade as Grade) : thresholdGrade(scores[index]);
    grades[GRADES.indexOf(letter)] += 1;
  });
  return {
    headcount: rule === 'server' ? counted.length : new Set(counted.map((rec) => rec.employee_id)).size,
    avg: mean === null ? null : round(mean, rule === 'server' ? 2 : 1),
    grades,
  };
}

/* ── Routing for the mocked API ── */

const envelope = (data: unknown) => Promise.resolve({ success: true, data });
function summaryKey(params: URLSearchParams) {
  return [
    `period=${params.get('period')}`,
    `region=${params.get('region') ?? 'All'}`,
    `location=${params.get('location') ?? 'all'}`,
    `performance_level=${params.get('performance_level') ?? 'All'}`,
  ].join('|');
}
function routeApi(url: string): Promise<unknown> {
  const [path, query = ''] = url.split('?');
  if (path === '/api/performance/catalog') return envelope(bundle.catalog);
  if (path === '/api/performance/summary') {
    const key = summaryKey(new URLSearchParams(query));
    if (!(key in bundle.summaries)) return Promise.reject(new Error(`no captured summary for ${key}`));
    return envelope(bundle.summaries[key]);
  }
  if (path === '/api/performance/summary-records') return envelope(bundle.summary_records);
  // The backend has no executive summary route; the Departmental page falls back on this 404.
  if (path === '/api/executive/summary') return Promise.reject(new ApiError('Not Found', 404));
  if (path === '/api/corrective-actions/follow-up') return envelope(bundle.follow_up);
  if (path === '/api/corrective-actions/') return envelope(bundle.corrective_actions);
  return Promise.reject(new Error(`unrouted request ${url}`));
}

/* ── Open gaps (each one names its cause in the code) ── */

interface KnownGap { id: string; title: string; cause: string }
const KNOWN_GAPS: KnownGap[] = [
  {
    id: 'G-DUP',
    title: 'One employee on two levels in one month',
    cause: 'Executive "Total Agents" is the number of employee-month rows (server `_summary` total_agents); Departmental "Employees" is the number of distinct people (compose.ts `employeesOf`). Headcount moves to people in the unified summary (Step B decision); the server keeps counting rows until the old page is removed.',
  },
  {
    id: 'G-ACT-SCOPE',
    title: 'Executive action statistics ignore region, branch and level',
    cause: 'ExecutiveView.tsx scopes actions only by period and role in scoped mode (`filterActionsByPerformanceScope` runs only on the legacy path). The composed path applies region, branch and level to actions (compose `scopeAction`).',
  },
  {
    id: 'G-ACT-LINK',
    title: 'Linked KPI counted only on the Departmental side',
    cause: 'actionAnalytics.ts adds `linked_kpi_key` to KPI mentions; ExecutiveView uses summarizeRootCauses, which reads `root_cause_note` only.',
  },
];

/* ── Page values ── */

interface Side {
  headcount: number;
  teams: number;
  avg: number | null;
  rawAvg: number | null;
  pctAB: number | null;
  pctDE: number | null;
  grades: number[] | null;
  previousAvg: number | null;
  previousKey: string | null;
  activeKey: string | null;
  teamRows: string[];
  actionTotal: number;
  actionEmployees: number;
  actionTypes: string[];
  actionKpis: string[];
}

interface ScopedResult {
  totalAgents: number;
  uniqueTeamCount: number;
  overallAvgScore: number;
  pctAB: number;
  pctDE: number;
  allClassCounts: { A: number; B: number; C: number; D: number; E: number };
  summaries: Array<{ teamName: string; agentCount: number; avgScore: number }>;
  previousPeriod: { key: string } | null;
  previousOverallAvgScore: number;
  activePeriod: { key: string; month: string } | null;
  loading: boolean;
}
interface ComposedResult { summary: ExecutiveSummary | null; isLoading: boolean }

type MappedAction = ReturnType<typeof mapBackendAction>;

const sideFromExecutive = (e: ScopedResult, actions: MappedAction[]): Side => {
  const activeMonth = e.activePeriod?.month ?? '';
  // Mirrors ExecutiveView.tsx: actions in the active period (year and month), then summarised.
  const stats = summarizeRootCauses(actionsInActivePeriod(actions, activeMonth, e.activePeriod?.key ?? null));
  const empty = e.totalAgents === 0;
  return {
    headcount: e.totalAgents,
    teams: e.uniqueTeamCount,
    avg: empty ? null : round(e.overallAvgScore, 1),
    rawAvg: empty ? null : e.overallAvgScore,
    pctAB: empty ? null : round(e.pctAB, 1),
    pctDE: empty ? null : round(e.pctDE, 1),
    grades: empty ? null : GRADES.map((grade) => e.allClassCounts[grade]),
    previousAvg: e.previousPeriod ? round(e.previousOverallAvgScore, 1) : null,
    previousKey: e.previousPeriod?.key ?? null,
    activeKey: e.activePeriod?.key ?? null,
    teamRows: e.summaries.map((team) => `${team.teamName} ${team.agentCount} ${fmt1(round(team.avgScore, 1))}`).sort(),
    actionTotal: stats.total,
    actionEmployees: stats.employeesActioned,
    actionTypes: Object.entries(stats.byType).filter(([, count]) => count > 0).map(([type, count]) => `${type}:${count}`).sort(),
    actionKpis: Object.entries(stats.rootCauses).filter(([label]) => label !== 'Other').map(([label, count]) => `${label}:${count}`).sort(),
  };
};

const sideFromComposed = (summary: ExecutiveSummary): Side => {
  const analytics = summary.corrective_actions?.analytics;
  const stats = analytics ? actionAnalyticsStats(analytics.actions) : null;
  const empty = summary.hero.employees === 0;
  const distribution = summary.grade_distribution;
  return {
    headcount: summary.hero.employees,
    teams: summary.hero.teams_count,
    avg: empty ? null : summary.hero.score,
    rawAvg: empty ? null : summary.hero.score,
    pctAB: empty ? null : (distribution?.combined_percents?.AB ?? null),
    pctDE: empty ? null : (distribution?.combined_percents?.DE ?? null),
    grades: distribution ? GRADES.map((grade) => distribution.counts[grade]) : null,
    previousAvg: summary.period.previous ? summary.hero.previous_score : null,
    previousKey: summary.period.previous?.key ?? null,
    activeKey: summary.period.effective?.key ?? null,
    teamRows: summary.teams.map((team) => `${team.team} ${team.employees} ${fmt1(team.score)}`).sort(),
    actionTotal: stats?.total ?? 0,
    actionEmployees: stats?.employees ?? 0,
    actionTypes: (stats?.types ?? []).map((row) => `${row.label}:${row.count}`).sort(),
    actionKpis: (stats?.kpis ?? []).map((row) => `${row.label}:${row.count}`).sort(),
  };
};

/* ── Matrix ── */

const cellLabel = (period: string, filters: Filters) => `${period} | ${filters.region ?? 'all regions'} | ${filters.location ?? 'all branches'} | ${filters.performance_level ?? 'all levels'}`;

interface Row { cell: string; metric: string; executive: string; departmental: string; match: boolean; gaps: string[] }
interface SelfCheck { cell: string; page: 'Executive' | 'Departmental'; field: string; expected: string; actual: string; ok: boolean }

const METRICS: Array<[string, (side: Side) => string]> = [
  ['headcount', (side) => String(side.headcount)],
  ['teams', (side) => String(side.teams)],
  ['avg', (side) => fmt1(side.avg)],
  ['pctAB', (side) => fmt1(side.pctAB)],
  ['pctDE', (side) => fmt1(side.pctDE)],
  ['grades', (side) => (side.grades ? side.grades.join('/') : '—')],
  ['previousAvg', (side) => fmt1(side.previousAvg)],
  ['previousPeriod', (side) => side.previousKey ?? '—'],
  ['activePeriod', (side) => side.activeKey ?? '—'],
  ['teamRows', (side) => side.teamRows.join('; ') || '—'],
  ['actionsTotal', (side) => String(side.actionTotal)],
  ['actionsEmployees', (side) => String(side.actionEmployees)],
  ['actionsTypes', (side) => side.actionTypes.join(',') || '—'],
  ['actionsKpis', (side) => side.actionKpis.join(',') || '—'],
];

/** Facts that can explain a mismatch in a cell. */
function factsFor(filters: Filters, keys: Array<string | null>) {
  const live = keys.filter((key): key is string => Boolean(key));
  const scoped = bundle.summary_records.filter((rec) => live.includes(keyOf(rec))
    && serverActive(rec)
    && (!filters.region || rec.region === filters.region)
    && (!filters.performance_level || rec.performance_level === filters.performance_level));
  const perEmployeeMonth = new Map<string, number>();
  scoped.forEach((rec) => {
    const id = `${rec.employee_id}|${keyOf(rec)}`;
    perEmployeeMonth.set(id, (perEmployeeMonth.get(id) ?? 0) + 1);
  });
  return {
    duplicateRows: [...perEmployeeMonth.values()].reduce((sum, count) => sum + Math.max(count - 1, 0), 0),
    actionLinked: bundle.corrective_actions.some((action) => Boolean(action.linked_kpi_key)
      && live.includes(`${action.year}-${String(MONTHS.indexOf(action.month) + 1).padStart(2, '0')}`)),
  };
}

function gapsFor(metric: string, filters: Filters, facts: ReturnType<typeof factsFor>): string[] {
  const gaps: string[] = [];
  if (metric === 'headcount' && facts.duplicateRows > 0) gaps.push('G-DUP');
  if (metric.startsWith('actions')) {
    if (filters.region || filters.location || filters.performance_level) gaps.push('G-ACT-SCOPE');
    if (metric === 'actionsKpis' && facts.actionLinked) gaps.push('G-ACT-LINK');
  }
  return [...new Set(gaps)];
}

function renderWithClient<T>(hook: () => T) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return renderHook(hook, { wrapper });
}

async function runExecutive(useHook: (period: string, filters: Filters) => ScopedResult, period: string, filters: Filters) {
  const { result, unmount } = renderWithClient(() => useHook(period, filters));
  await waitFor(() => expect(result.current.loading).toBe(false));
  const value = result.current;
  unmount();
  return value;
}

async function runComposed(useHook: (args: unknown) => ComposedResult, period: string, filters: Filters) {
  const { result, unmount } = renderWithClient(() => useHook({
    view: 'corporate',
    role: 'General Manager',
    filters: {
      periodKey: period === 'All' ? undefined : period,
      region: filters.region,
      branch: filters.location,
      performanceLevel: filters.performance_level,
    },
    today: new Date(2026, 7, 13),
  }));
  await waitFor(() => expect(result.current.isLoading).toBe(false));
  await waitFor(() => expect(result.current.summary).not.toBeNull());
  const value = result.current.summary as ExecutiveSummary;
  unmount();
  return value;
}

/* ── Test body ── */

let useScopedExecutiveSummary: (month: string, region: string, location: string, level: string) => ScopedResult;
let useExecutiveSummary: (args: unknown) => ComposedResult;
let scopedApiEnabled = false;

async function buildMatrix() {
  const actions = bundle.corrective_actions.map((item) => mapBackendAction(item as never));
  const rows: Row[] = [];
  const checks: SelfCheck[] = [];
  for (const period of [...bundle.periods, 'All']) {
    for (const filters of bundle.filter_sets) {
      const cell = cellLabel(period, filters);
      const executive = await runExecutive((month, f) => useScopedExecutiveSummary(month, f.region ?? 'All', f.location ?? 'all', f.performance_level ?? 'All'), period, filters);
      const composed = await runComposed(useExecutiveSummary, period, filters);
      const exec = sideFromExecutive(executive, actions);
      const dept = sideFromComposed(composed);
      const execReplay = replay('server', exec.activeKey ?? '', filters);
      const deptReplay = replay('compose', dept.activeKey ?? '', filters);
      checks.push(
        { cell, page: 'Executive', field: 'headcount', expected: String(execReplay.headcount), actual: String(exec.headcount), ok: execReplay.headcount === exec.headcount },
        { cell, page: 'Executive', field: 'avg', expected: fmt1(execReplay.avg), actual: fmt1(exec.rawAvg), ok: execReplay.avg === exec.rawAvg },
        { cell, page: 'Executive', field: 'grades', expected: execReplay.grades.join('/'), actual: (exec.grades ?? [0, 0, 0, 0, 0]).join('/'), ok: execReplay.grades.join('/') === (exec.grades ?? [0, 0, 0, 0, 0]).join('/') },
        { cell, page: 'Departmental', field: 'headcount', expected: String(deptReplay.headcount), actual: String(dept.headcount), ok: deptReplay.headcount === dept.headcount },
        { cell, page: 'Departmental', field: 'avg', expected: fmt1(deptReplay.avg), actual: fmt1(dept.rawAvg), ok: deptReplay.avg === dept.rawAvg },
        { cell, page: 'Departmental', field: 'grades', expected: deptReplay.grades.join('/'), actual: (dept.grades ?? [0, 0, 0, 0, 0]).join('/'), ok: deptReplay.grades.join('/') === (dept.grades ?? [0, 0, 0, 0, 0]).join('/') },
      );
      const facts = factsFor(filters, [exec.activeKey, exec.previousKey, dept.activeKey, dept.previousKey]);
      METRICS.forEach(([metric, format]) => {
        const ex = format(exec);
        const dp = format(dept);
        const match = ex === dp;
        rows.push({ cell, metric, executive: ex, departmental: dp, match, gaps: match ? [] : gapsFor(metric, filters, facts) });
      });
    }
  }
  return { rows, checks };
}

const formatTable = (rows: Row[]) => [
  'cell | metric | executive | departmental | gaps',
  ...rows.map((row) => `${row.cell} | ${row.metric} | ${row.executive} | ${row.departmental} | ${row.gaps.join(',') || 'UNEXPLAINED'}`),
].join('\n');

const formatChecks = (checks: SelfCheck[]) => [
  'cell | page | field | expected (replayed rule) | shown',
  ...checks.filter((check) => !check.ok).map((check) => `${check.cell} | ${check.page} | ${check.field} | ${check.expected} | ${check.actual}`),
].join('\n');

describe('Executive vs Departmental summary parity (synthetic dataset)', () => {
  let matrix: { rows: Row[]; checks: SelfCheck[] };

  beforeAll(async () => {
    vi.stubEnv('VITE_SCOPED_PERFORMANCE_API', 'true');
    vi.resetModules();
    const scoped = await import('../../hooks/api/usePerformanceDashboard');
    const composed = await import('./useExecutiveSummary');
    scopedApiEnabled = scoped.scopedPerformanceApiEnabled;
    useScopedExecutiveSummary = scoped.useScopedExecutiveSummary as unknown as typeof useScopedExecutiveSummary;
    useExecutiveSummary = composed.useExecutiveSummary as unknown as typeof useExecutiveSummary;
    mocks.apiFetch.mockImplementation((url: string) => routeApi(url));
    matrix = await buildMatrix();
  }, 300_000);

  afterAll(() => {
    vi.unstubAllEnvs();
  });

  const cell = (period: string, filters: Filters, metric: string) => {
    const label = cellLabel(period, filters);
    const row = matrix.rows.find((candidate) => candidate.cell === label && candidate.metric === metric);
    if (!row) throw new Error(`no matrix row for ${label} ${metric}`);
    return row;
  };

  it('reads the scoped summary API on the Executive side', () => {
    expect(scopedApiEnabled).toBe(true);
  });

  it('each page reproduces its own rule replayed from the same records', () => {
    const failing = matrix.checks.filter((check) => !check.ok);
    expect(failing, formatChecks(matrix.checks)).toEqual([]);
  });

  it('every Executive-versus-Departmental mismatch is explained by a named open gap', () => {
    const unexplained = matrix.rows.filter((row) => !row.match && row.gaps.length === 0);
    const mismatches = matrix.rows.filter((row) => !row.match);
    expect(unexplained, `${mismatches.length} mismatches, ${unexplained.length} unexplained\n${formatTable(unexplained)}`).toEqual([]);
  });

  it.each(KNOWN_GAPS.map((gap) => [gap.id, gap.title] as const))('%s (%s) is observed in the matrix', (id) => {
    expect(matrix.rows.some((row) => row.gaps.includes(id)), `${id} explains no row; retire it or fix the classifier`).toBe(true);
  });

  it('the Outbound anchor (July 82.85 / August 79.82 stored) agrees on both pages', () => {
    expect(cell('2026-07', {}, 'teamRows').executive).toContain('Outbound 2 87.0');
    expect(cell('2026-07', {}, 'teamRows').departmental).toContain('Outbound 2 87.0');
    expect(cell('2026-07', {}, 'avg').match).toBe(true);
    expect(cell('2026-08', {}, 'previousAvg').match).toBe(true);
    // July headcount differs only by the duplicate Managerial row (G-DUP), not by the anchor rows.
    expect(cell('2026-07', {}, 'headcount').gaps).toEqual(['G-DUP']);
  });

  it('ratio-form scores: a score of 1 counts as 100 and 0.85 as 85 on both pages', () => {
    // Inbound July: 97.5, 71 and 1 (a ratio, 100): (97.5 + 71 + 100) / 3 = 89.5.
    expect(cell('2026-07', {}, 'teamRows').executive).toContain('Inbound 3 89.5');
    expect(cell('2026-07', {}, 'teamRows').departmental).toContain('Inbound 3 89.5');
    // Inbound August: 84, 63 and 0.85 (a ratio, 85): (84 + 63 + 85) / 3 = 77.3.
    expect(cell('2026-08', {}, 'teamRows').executive).toContain('Inbound 3 77.3');
    expect(cell('2026-08', {}, 'teamRows').departmental).toContain('Inbound 3 77.3');
  });

  it('a low percentage score stays as it is: the 5.5 score in August is 5.5 on both pages', () => {
    const row = cell('2026-08', { location: 'sharjah' }, 'avg');
    expect(row.executive).toBe('5.5');
    expect(row.departmental).toBe(row.executive);
  });

  it('branch_key wins over the raw text: the July Sharjah row (tagged Dubai, raw text "SHJ") is not Sharjah, so July has no Sharjah rows', () => {
    // No counted Sharjah row in July: both pages fall back to August, the newest Sharjah month with counted rows.
    expect(cell('2026-07', { location: 'sharjah' }, 'activePeriod').executive).toBe('2026-08');
    expect(cell('2026-07', { location: 'sharjah' }, 'activePeriod').departmental).toBe('2026-08');
    expect(cell('2026-07', { location: 'sharjah' }, 'headcount').executive).toBe('1');
    expect(cell('2026-07', { location: 'sharjah' }, 'headcount').departmental).toBe('1');
  });

  it('a row without branch_key falls back to its text: IB-02 (raw "SHJ AJM") counts for Ajman on both pages', () => {
    expect(cell('2026-08', { location: 'ajman' }, 'headcount').executive).toBe('1');
    expect(cell('2026-08', { location: 'ajman' }, 'headcount').departmental).toBe('1');
  });

  it('G-SCALE closed: August average is 70.8 on both pages (5.5 is not scaled to 550)', () => {
    const row = cell('2026-08', {}, 'avg');
    expect(row.executive).toBe('70.8');
    expect(row.departmental).toBe(row.executive);
  });

  it('G-BRANCH closed: Dubai August headcount is 1 on both pages (branch_key says Dubai)', () => {
    const row = cell('2026-08', { location: 'dubai' }, 'headcount');
    expect(row.executive).toBe('1');
    expect(row.departmental).toBe(row.executive);
  });

  it('G-PERIOD-FALLBACK closed: a Managerial August request shows July on both pages', () => {
    const row = cell('2026-08', { performance_level: 'Managerial' }, 'activePeriod');
    expect(row.executive).toBe('2026-07');
    expect(row.departmental).toBe(row.executive);
  });

  it('G-PREV-SCOPE closed: Sharjah August has no earlier Sharjah month on either page', () => {
    const row = cell('2026-08', { location: 'sharjah' }, 'previousPeriod');
    expect(row.executive).toBe('—');
    expect(row.departmental).toBe(row.executive);
  });

  it('G-CATALOG closed: the default month is August (the newest with counted rows), and it agrees on both pages', () => {
    const row = cell('All', {}, 'headcount');
    expect(row.executive).toBe('7');
    expect(row.departmental).toBe(row.executive);
    expect(cell('All', {}, 'activePeriod').executive).toBe('2026-08');
  });

  it('a requested month with no counted rows shows the newest counted month on both pages (September -> August)', () => {
    expect(cell('2026-09', {}, 'activePeriod').executive).toBe('2026-08');
    expect(cell('2026-09', {}, 'activePeriod').departmental).toBe('2026-08');
  });

  it.fails('G-DUP: July headcount counts a person on two levels twice on the Executive page', () => {
    const row = cell('2026-07', {}, 'headcount');
    expect(row.departmental).toBe(row.executive);
  });

  it.fails('G-ACT-SCOPE: a UAE filter leaves the Executive August action count unchanged; the composed page drops it', () => {
    const row = cell('2026-08', { region: 'UAE' }, 'actionsTotal');
    expect(row.departmental).toBe(row.executive);
  });

  it.fails('G-ACT-LINK: July KPI mentions differ; the Departmental side adds the linked KPI', () => {
    const row = cell('2026-07', {}, 'actionsKpis');
    expect(row.departmental).toBe(row.executive);
  });
});
