import { useState, useEffect, useMemo } from 'react';
import type { AgentRecord, LocationKey, MonthKey, PerformanceLevelFilter, GeoBreakdown, EmployeeCRMRecord, EmployeeStatus, PlanningCategory, Trend, PreApprovalsWorkflowFilter, CallCenterChannelFilter, RcmDomainFilter, RcmGroupFilter } from '../types';
import { canonicalTeamName, getKPIsForAgent, TEAM_ID_MAP, PRE_APPROVALS_UAE_TEAM, CALL_CENTER_TEAM, RCM_TEAM, isMergedBranchTeam, isPreApprovalsUaeTeam, isPreApprovalsWorkflowTeam, isCallCenterTeam, isCallCenterChannelTeam, isRcmTeam, isRcmDomainTeam, isRcmGroupTeam, sameCanonicalTeam } from '../types';
import { getGradeClass } from '../constants/grades';
import { apiFetch } from '../lib/apiClient';
import { normalizePerformanceScore, resolveDisplayScore } from '../utils/kpiScore';
import { normalizeTeamName } from './api/useKpiWeights';
import { calculatePerformanceSummary } from '../utils/performanceSummary';
import { useAllTeamConfigs } from './useTeamConfig';
import { calculateAggregatedTeamPerformance } from '../features/team/teamKpiAggregator';
import { scopedPerformanceApiEnabled } from './api/usePerformanceDashboard';

const MONTH_ORDER: Record<string, number> = {
  January: 1, February: 2, March: 3, April: 4, May: 5, June: 6,
  July: 7, August: 8, September: 9, October: 10, November: 11, December: 12,
};

export function normalizeScore(score: number): number {
  return normalizePerformanceScore(score);
}

function sameTeam(left: string | null | undefined, right: string | null | undefined): boolean {
  return sameCanonicalTeam(left, right);
}

export function resolveTeamMonths(agents: AgentRecord[], teamName: string | null): string[] {
  const months = new Set(
    agents
      .filter((agent) => !teamName || sameTeam(agent.identity.team, teamName))
      .map((agent) => agent.identity.month)
      .filter(Boolean),
  );
  return Array.from(months).sort((left, right) => (MONTH_ORDER[left] || 0) - (MONTH_ORDER[right] || 0));
}

export function getLatestRecordPerEmployee(records: AgentRecord[]): AgentRecord[] {
  const latestMap = new Map<string, AgentRecord>();
  for (const record of records) {
    const key = record.identity.employee_id || record.identity.name;
    if (!key || record.identity.name.toLowerCase() === 'total') continue;
    const existing = latestMap.get(key);
    if (!existing) {
      latestMap.set(key, record);
    } else {
      const recordPeriod = [(record.year || 0), MONTH_ORDER[record.identity.month] || 0];
      const existingPeriod = [(existing.year || 0), MONTH_ORDER[existing.identity.month] || 0];
      if (
        recordPeriod[0] > existingPeriod[0] ||
        (recordPeriod[0] === existingPeriod[0] && recordPeriod[1] > existingPeriod[1])
      ) {
        latestMap.set(key, record);
      }
    }
  }
  return Array.from(latestMap.values());
}

export function resolveHeadcountSnapshot(
  records: AgentRecord[],
  selectedMonth: string,
): { month: string; totalAgents: number; uniqueTeamCount: number } {
  if (selectedMonth !== 'All') {
    const snapshotRecords = records.filter((record) => record.identity.month === selectedMonth);
    const employeeKeys = new Set(
      snapshotRecords
        .map((record) => record.identity.employee_id || record.identity.name)
        .filter(Boolean),
    );
    const teams = new Set(
      snapshotRecords
        .map((record) => normalizeTeamName(record.identity.team || ''))
        .filter(Boolean),
    );
    return {
      month: selectedMonth,
      totalAgents: employeeKeys.size,
      uniqueTeamCount: teams.size,
    };
  }

  const latestRecord = records.reduce<AgentRecord | null>((latest, record) => {
    if (!latest) return record;
    const recordPeriod = [(record.year || 0), MONTH_ORDER[record.identity.month] || 0];
    const latestPeriod = [(latest.year || 0), MONTH_ORDER[latest.identity.month] || 0];
    return recordPeriod[0] > latestPeriod[0]
      || (recordPeriod[0] === latestPeriod[0] && recordPeriod[1] > latestPeriod[1])
      ? record
      : latest;
  }, null);

  const maxMonth = latestRecord?.identity.month || '';
  const maxYear = latestRecord?.year || 0;
  const snapshotRecords = records.filter((record) => (
    record.identity.month === maxMonth && (record.year || 0) === maxYear
  ));
  const latestEmployees = new Set(
    snapshotRecords
      .map((record) => record.identity.employee_id || record.identity.name)
      .filter(Boolean),
  );
  const activeTeams = new Set(
    snapshotRecords
      .map((record) => normalizeTeamName(record.identity.team || ''))
      .filter(Boolean),
  );

  return {
    month: maxMonth || 'All',
    totalAgents: latestEmployees.size,
    uniqueTeamCount: activeTeams.size,
  };
}

export function resolveRecordGradeClass(record: AgentRecord, score?: number): import('../types').GradeClass {
  const resolvedScore = score ?? normalizeScore(record.evaluation.score);
  const storedGrade = record.evaluation.grade?.trim().toUpperCase();
  if (storedGrade === 'A' || storedGrade === 'B' || storedGrade === 'C' || storedGrade === 'D' || storedGrade === 'E') {
    return storedGrade;
  }
  if (sameTeam(record.identity.team, 'Marketing')) {
    if (resolvedScore >= 95) return 'A';
    if (resolvedScore >= 85) return 'B';
    if (resolvedScore >= 75) return 'C';
    if (resolvedScore >= 65) return 'D';
    return 'E';
  }
  return getGradeClass(resolvedScore);
}

export function resolveAutoRootCause(
  record: AgentRecord,
  gradeClass: import('../types').GradeClass,
): string {
  if (gradeClass === 'A' || gradeClass === 'B') return '';

  const rootCause = record.evaluation.root_cause;
  if (rootCause?.kpi) {
    const kpiLabelMap: Record<string, string> = {
      Attend: 'Attend ↓',
      Booking: 'Booking ↓',
      Quality: 'Quality ↓',
      AHT: 'AHT ↑',
      Rejection: 'Rejection ↑',
      InitialError: 'Initial Error ↑',
      Submission: 'Submission ↓',
      Other: 'Other ↓',
    };
    return `${kpiLabelMap[rootCause.kpi] || rootCause.kpi} (main issue)`;
  }

  const configuredKpis = getKPIsForAgent(record).filter((kpi) => kpi.weight !== 0);
  const targetReview = configuredKpis.find((kpi) => kpi.target === 0);
  if (targetReview) return `${targetReview.label} target requires review`;

  const weakestKpi = configuredKpis
    .filter((kpi) => kpi.achievement !== undefined && Number.isFinite(kpi.achievement))
    .slice()
    .sort((left, right) => (left.achievement ?? 0) - (right.achievement ?? 0))[0];
  if (weakestKpi && (weakestKpi.achievement ?? 100) < 100) {
    return `${weakestKpi.label} (main issue)`;
  }

  return 'All metrics good';
}

// Module-level shared cache and listeners for Backend API data
const STALE_TIME_MS = 10 * 60 * 1000;
let cachedData: AgentRecord[] | null = null;
let lastFetchTime = 0;
const listeners = new Set<(data: AgentRecord[]) => void>();
let isFetching = false;
let lastDataSource: 'api' | 'empty' = 'empty';
let lastErrorMessage: string | null = null;
let scopedRefreshVersion = 0;
const scopedRefreshListeners = new Set<() => void>();

type ScopedPerformancePeriod = { key: string; month: string; year: number };
type ScopedPerformanceCatalog = { periods: ScopedPerformancePeriod[] };
type ScopedRecordItem = Record<string, unknown>;
type ScopedRecordPage = {
  items: ScopedRecordItem[];
  next_cursor?: string | null;
  has_more?: boolean;
};

let scopedCatalog: ScopedPerformanceCatalog | null = null;
let scopedCatalogSession = '';
let scopedCatalogFetchedAt = 0;
let scopedCatalogRequest: Promise<ScopedPerformanceCatalog> | null = null;
let scopedCatalogRequestSession = '';

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function numberValue(value: unknown, fallback = 0): number {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function stringValue(value: unknown, fallback = ''): string {
  return typeof value === 'string' ? value : value == null ? fallback : String(value);
}

function scopedSessionKey(): string {
  try {
    const saved = localStorage.getItem('pms_session_v1');
    if (!saved) return 'anonymous';
    const user = JSON.parse(saved) as { id?: string; username?: string };
    return user.id || user.username || 'anonymous';
  } catch {
    return 'anonymous';
  }
}

function geoValue(value: unknown): GeoBreakdown {
  const source = objectValue(value);
  return {
    dubai: numberValue(source.dubai),
    sharjah: numberValue(source.sharjah),
    ajman: numberValue(source.ajman),
    clinics: numberValue(source.clinics),
  };
}

/** Adapt the bounded REST record contract to the existing dashboard view model. */
export function mapScopedPerformanceRecord(item: ScopedRecordItem): AgentRecord {
  const identity = objectValue(item.identity);
  const calls = objectValue(item.calls);
  const geo = objectValue(item.geo);
  const actual = objectValue(item.actual);
  const achievement = objectValue(item.achievement);
  const evaluation = objectValue(item.evaluation);
  const level = stringValue(item.performance_level, 'Employee');
  const performanceLevel: AgentRecord['performance_level'] = level === 'Managerial' || level === 'Corporate'
    ? level
    : 'Employee';
  const score = numberValue(evaluation.score ?? item.score);

  return {
    raw_data: objectValue(item.raw_data) as AgentRecord['raw_data'],
    region: stringValue(item.region ?? identity.region, '') || undefined,
    year: item.year == null ? undefined : numberValue(item.year),
    position: stringValue(item.position ?? identity.position, '') || undefined,
    status: stringValue(item.status, '') || undefined,
    performance_level: performanceLevel,
    kpi_values: (Array.isArray(item.kpi_values) ? item.kpi_values : []) as AgentRecord['kpi_values'],
    identity: {
      name: stringValue(item.employee_name ?? identity.name),
      month: stringValue(item.month ?? identity.month),
      team: stringValue(item.team ?? identity.team, '') || undefined,
      employee_id: stringValue(item.employee_id ?? identity.employee_id, '') || undefined,
      position: stringValue(item.position ?? identity.position, '') || undefined,
      region: stringValue(item.region ?? identity.region, '') || undefined,
    },
    calls: {
      inbound: numberValue(calls.inbound),
      outbound: numberValue(calls.outbound),
      total_handled: numberValue(calls.total_handled),
      total_calls: calls.total_calls == null ? undefined : numberValue(calls.total_calls),
      abandoned: numberValue(calls.abandoned),
      aht_raw: stringValue(calls.aht_raw, '00:00:00'),
    },
    geo: {
      bookings: geoValue(geo.bookings),
      attended: geoValue(geo.attended),
    },
    actual: {
      booking_rate: numberValue(actual.booking_rate),
      attend_rate: numberValue(actual.attend_rate),
      abandon_rate: numberValue(actual.abandon_rate),
      reachability_rate: numberValue(actual.reachability_rate),
      rejection_rate: numberValue(actual.rejection_rate),
      initial_error_rate: numberValue(actual.initial_error_rate),
      submission_rate: numberValue(actual.submission_rate),
      quality_rate: numberValue(actual.quality_rate),
      utz_rate: numberValue(actual.utz_rate),
    },
    achievement: {
      booking_ach: numberValue(achievement.booking_ach),
      attend_ach: numberValue(achievement.attend_ach),
      quality_ach: numberValue(achievement.quality_ach),
      aht_ach: numberValue(achievement.aht_ach),
      reachability_ach: numberValue(achievement.reachability_ach),
      abandon_ach: numberValue(achievement.abandon_ach),
      rejection_ach: numberValue(achievement.rejection_ach),
      initial_error_ach: numberValue(achievement.initial_error_ach),
      submission_ach: numberValue(achievement.submission_ach),
      op_census_ach: numberValue(achievement.op_census_ach),
      op_revenue_ach: numberValue(achievement.op_revenue_ach),
      ip_census_ach: numberValue(achievement.ip_census_ach),
      ip_revenue_ach: numberValue(achievement.ip_revenue_ach),
      activity_ach: numberValue(achievement.activity_ach),
    },
    evaluation: {
      score,
      grade: stringValue(evaluation.grade ?? item.grade, 'E'),
      root_cause: evaluation.root_cause as AgentRecord['evaluation']['root_cause'],
      suggested_action: stringValue(evaluation.suggested_action, '') || null,
      corrective_action: stringValue(evaluation.corrective_action, '') || null,
      manager_notes: stringValue(evaluation.manager_notes, '') || null,
      planning_category: Array.isArray(evaluation.planning_category)
        ? evaluation.planning_category.filter((value): value is string => typeof value === 'string')
        : [],
      trend_status: evaluation.trend_status as AgentRecord['evaluation']['trend_status'],
    },
  };
}

async function getScopedCatalog(): Promise<ScopedPerformanceCatalog> {
  const session = scopedSessionKey();
  const cacheIsFresh = scopedCatalog
    && scopedCatalogSession === session
    && Date.now() - scopedCatalogFetchedAt < 2 * 60 * 1000;
  if (cacheIsFresh) return scopedCatalog!;
  if (scopedCatalogRequest && scopedCatalogRequestSession === session) return scopedCatalogRequest;

  scopedCatalogRequestSession = session;
  scopedCatalogRequest = apiFetch<{
    success: boolean;
    data?: ScopedPerformanceCatalog;
    message?: string;
  }>('/api/performance/catalog').then((response) => {
    if (!response.success || !response.data) {
      throw new Error(response.message || 'Performance catalog request failed');
    }
    scopedCatalog = response.data;
    scopedCatalogSession = session;
    scopedCatalogFetchedAt = Date.now();
    return response.data;
  }).finally(() => {
    scopedCatalogRequest = null;
  });
  return scopedCatalogRequest;
}

function periodsForRequest(
  catalog: ScopedPerformanceCatalog,
  month: MonthKey,
  periodCount = 2,
): ScopedPerformancePeriod[] {
  const periods = (catalog.periods || []).slice().sort((left, right) => right.key.localeCompare(left.key));
  if (!periods.length) return [];
  const active = month !== 'All'
    ? periods.find((period) => period.key === month || period.month === month) || periods[0]
    : periods[0];
  const activeIndex = periods.findIndex((period) => period.key === active.key);
  return periods.slice(activeIndex, activeIndex + Math.max(1, periodCount)).filter(
    (period, index, values): period is ScopedPerformancePeriod => values.findIndex((item) => item.key === period.key) === index,
  );
}

async function fetchScopedPerformanceData(
  month: MonthKey,
  region: 'All' | 'EGY' | 'UAE',
  performanceLevel: PerformanceLevelFilter,
  location: LocationKey,
  team?: string,
): Promise<AgentRecord[]> {
  const catalog = await getScopedCatalog();
  const periods = periodsForRequest(catalog, month, month === 'All' ? 6 : 2);
  const records: AgentRecord[] = [];

  for (const period of periods) {
    let cursor: string | undefined;
    let pageCount = 0;
    do {
      const params = new URLSearchParams({
        period: period.key,
        detail: 'full',
        page_size: '100',
      });
      if (region !== 'All') params.set('region', region);
      if (performanceLevel !== 'All') params.set('performance_level', performanceLevel);
      if (location !== 'all') params.set('location', location);
      if (team) params.set('team', team);
      if (cursor) params.set('cursor', cursor);

      const response = await apiFetch<{
        success: boolean;
        data?: ScopedRecordPage;
        message?: string;
      }>(`/api/performance/records?${params.toString()}`);
      if (!response.success || !response.data) {
        throw new Error(response.message || 'Performance records request failed');
      }
      records.push(...(response.data.items || []).map(mapScopedPerformanceRecord));
      cursor = response.data.has_more && response.data.next_cursor
        ? response.data.next_cursor
        : undefined;
      pageCount += 1;
      if (pageCount >= 1000 && cursor) {
        throw new Error('Performance records pagination exceeded the safety limit');
      }
    } while (cursor);
  }

  return records;
}

async function fetchPerformanceData(force = false) {
  if (!force && isFetching) return;
  if (!force && cachedData && lastDataSource === 'api' && Date.now() - lastFetchTime < STALE_TIME_MS) {
    lastDataSource = 'api';
    lastErrorMessage = null;
    listeners.forEach((listener) => listener(cachedData!));
    return;
  }
  isFetching = true;
  try {
    const result = await apiFetch<{ success: boolean; data: AgentRecord[]; message?: string }>('/api/performance');
    if (result && result.success && Array.isArray(result.data)) {
      cachedData = result.data;
      lastFetchTime = Date.now();
      lastDataSource = 'api';
      lastErrorMessage = null;
    } else {
      throw new Error(result?.message || 'Invalid API response structure');
    }
    listeners.forEach((listener) => listener(cachedData!));
  } catch (error) {
    console.warn('Failed to fetch performance data from the Backend API.');
    cachedData = [];
    lastFetchTime = Date.now();
    lastDataSource = 'empty';
    lastErrorMessage = error instanceof Error ? error.message : 'Failed to fetch performance data';
    listeners.forEach((listener) => listener(cachedData!));
  } finally {
    isFetching = false;
  }
}

/** Force a re-fetch from the backend API (e.g. after a new file upload). */
export function refreshPerformanceData() {
  if (scopedPerformanceApiEnabled) {
    scopedCatalog = null;
    scopedCatalogFetchedAt = 0;
    scopedRefreshVersion += 1;
    scopedRefreshListeners.forEach((listener) => listener());
    return;
  }
  cachedData = null;
  lastFetchTime = 0;
  isFetching = false;
  lastDataSource = 'empty';
  lastErrorMessage = null;
  fetchPerformanceData(true);
}

/* ── Helpers ── */

function getGeoValue(geo: GeoBreakdown, location: LocationKey): number {
  if (location === 'all') {
    return geo.dubai + geo.sharjah + geo.ajman + geo.clinics;
  }
  return geo[location];
}

export function agentMatchesLocation(a: AgentRecord, location: LocationKey): boolean {
  if (location === 'all') return true;

  // Source branch/team fields are authoritative for branch-scoped uploads.
  // Geo totals are often copied or synthesized during ingestion, so checking
  // them first can make every SHJ/AJM employee appear in both branches.
  const raw = a.raw_data || {};
  const explicitBranchText = [
    raw.Team,
    raw['Out Team'],
    raw.Branch,
    raw.Site,
    raw.Area,
  ].filter(Boolean).join(' ').toUpperCase();
  const identityTeam = String(a.identity.team || '').toUpperCase();
  const explicitBranch = explicitBranchText.includes('AJM') || explicitBranchText.includes('AJMAN')
    ? 'ajman'
    : explicitBranchText.includes('SHJ') || explicitBranchText.includes('SHARJAH') || explicitBranchText.includes('SHARQA')
      ? 'sharjah'
      : explicitBranchText.includes('DUBAI') || identityTeam.includes('DUBAI')
        ? 'dubai'
        : explicitBranchText.includes('CLINIC')
          ? 'clinics'
          : undefined;
  if (explicitBranch) return explicitBranch === location;

  // Legacy call-center rows may not carry a branch field; retain the geo
  // fallback for those records only.
  const bookings = a.geo?.bookings?.[location] || 0;
  const attended = a.geo?.attended?.[location] || 0;
  return bookings > 0 || attended > 0;
}

/**
 * Pick the score shown in cross-team summaries without allowing a malformed
 * or stale pooled KPI aggregate to replace the score already shown for the
 * same employees on the team dashboard.
 *
 * Aggregation remains the preferred source when it agrees with the employee
 * scores.  When the two values are materially different (for example, Sales
 * records loaded before their weights are available), the employee-score
 * average is the reliable, user-visible value.
 */
export function reconcileTeamSummaryScore(
  aggregateScore: number | null | undefined,
  employeeScores: number[],
): number {
  const validScores = employeeScores.filter((score) => Number.isFinite(score));
  const employeeAverage = validScores.length > 0
    ? validScores.reduce((sum, score) => sum + score, 0) / validScores.length
    : 0;

  if (!Number.isFinite(aggregateScore ?? NaN) || (aggregateScore ?? 0) <= 0) {
    return employeeAverage;
  }
  if (validScores.length === 0) return aggregateScore ?? 0;

  return Math.abs((aggregateScore as number) - employeeAverage) <= 15
    ? aggregateScore as number
    : employeeAverage;
}

export function hasRealActivity(r: AgentRecord): boolean {
  if (!r || !r.identity || !r.identity.name) return false;
  if (r.identity.name.toLowerCase() === 'total') return false;

  // 1. If backend kpi_values exist:
  if (r.kpi_values && r.kpi_values.length > 0) {
    const hasAnyKpiActual = r.kpi_values.some((k) => Number(k.actual_value) > 0);
    if (hasAnyKpiActual) return true;
  }

  // 2. Check call center volumes
  if ((r.calls?.total_handled ?? 0) > 0) return true;
  if ((r.calls?.total_calls ?? 0) > 0) return true;
  if ((r.calls?.inbound ?? 0) > 0) return true;
  if ((r.calls?.outbound ?? 0) > 0) return true;

  // 3. Check geo volumes
  const bookingsSum = Object.values(r.geo?.bookings || {}).reduce((s, v) => s + (Number(v) || 0), 0);
  if (bookingsSum > 0) return true;
  const attendedSum = Object.values(r.geo?.attended || {}).reduce((s, v) => s + (Number(v) || 0), 0);
  if (attendedSum > 0) return true;

  // 4. Check raw_data for any non-zero operational actual
  if (r.raw_data) {
    const rawValues = Object.entries(r.raw_data);
    const hasOperationalActual = rawValues.some(([key, val]) => {
      const num = Number(val);
      if (!Number.isFinite(num) || num <= 0) return false;
      const lKey = key.toLowerCase();
      if (lKey.includes('id') || lKey.includes('name') || lKey.startsWith('t.') || lKey.includes('target') || lKey.includes('weight')) {
        return false;
      }
      return true;
    });
    if (hasOperationalActual) return true;
  }

  // 5. If evaluation score > 0
  if ((r.evaluation?.score ?? 0) > 0) return true;

  return false;
}


/** Parse "HH:MM:SS" → total seconds */
export function parseAHTtoSeconds(aht: string): number {
  const parts = aht.split(':').map(Number);
  return (parts[0] || 0) * 3600 + (parts[1] || 0) * 60 + (parts[2] || 0);
}

/** Seconds → "M:SS" display */
export function formatSecondsToMMSS(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.round(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

/* ── Exported Interfaces ── */

export interface MonthSummary {
  month: string;
  monthFull: string;
  totalBookings: number;
  totalAttended: number;
  totalInbound: number;
  totalAbandoned: number;
  totalHandled: number;
  avgBookingRate: number;
  avgAttendRate: number;
  avgAbandonRate: number;
  avgScore: number;
  agentCount: number;
}

export interface CumulativeMonthPoint {
  month: string;
  attended: number;
  target: number;
}

export interface LocationSummary {
  location: string;
  bookings: number;
  attended: number;
  showUpRate: number;
  noShowRate: number;
}

export interface ValueLeakageData {
  noShowRate: number;
  unconvertedRate: number;
  lostVisits: number;
  lostCalls: number;
}

export interface FunnelData {
  calls: number;
  bookings: number;
  attended: number;
  callToBookingRate: number;
  bookingToAttendRate: number;
}

export interface KpiVsTarget {
  label: string;
  actual: number;
  target: number;
  unit: string;
  isLowerBetter: boolean;
  isMet: boolean;
}

export interface AgentWithLocation extends AgentRecord {
  locationBookings: number;
  locationAttended: number;
  locationAttendRate: number;
}

/* ── Main Hook ── */

export function usePerformanceData(
  month: MonthKey,
  location: LocationKey,
  region: 'All' | 'EGY' | 'UAE' = 'All',
  performanceLevel: PerformanceLevelFilter = 'All',
  enabled = true,
  scopedTeam?: string,
) {
  const [allData, setAllData] = useState<AgentRecord[]>(scopedPerformanceApiEnabled ? [] : cachedData || []);
  const [loading, setLoading] = useState(enabled && (scopedPerformanceApiEnabled || !cachedData));
  const [dataSource, setDataSource] = useState<'api' | 'empty'>(scopedPerformanceApiEnabled ? 'empty' : lastDataSource);
  const [errorMessage, setErrorMessage] = useState<string | null>(scopedPerformanceApiEnabled ? null : lastErrorMessage);
  const [refreshVersion, setRefreshVersion] = useState(scopedRefreshVersion);

  useEffect(() => {
    const listener = () => setRefreshVersion(scopedRefreshVersion);
    scopedRefreshListeners.add(listener);
    return () => {
      scopedRefreshListeners.delete(listener);
    };
  }, []);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    if (scopedPerformanceApiEnabled) {
      let cancelled = false;
      fetchScopedPerformanceData(month, region, performanceLevel, location, scopedTeam)
        .then((newData) => {
          if (cancelled) return;
          setAllData(newData);
          setLoading(false);
          setDataSource('api');
          setErrorMessage(null);
        })
        .catch((error: unknown) => {
          if (cancelled) return;
          console.warn('Failed to fetch bounded performance data from the Backend API.');
          setAllData([]);
          setLoading(false);
          setDataSource('empty');
          setErrorMessage(error instanceof Error ? error.message : 'Failed to fetch performance data');
        });
      return () => {
        cancelled = true;
      };
    }

    const listener = (newData: AgentRecord[]) => {
      setAllData(newData);
      setLoading(false);
      setDataSource(lastDataSource);
      setErrorMessage(lastErrorMessage);
    };
    listeners.add(listener);

    if (!cachedData || lastDataSource !== 'api' || Date.now() - lastFetchTime >= STALE_TIME_MS) {
      fetchPerformanceData();
    }

    return () => {
      listeners.delete(listener);
    };
  }, [enabled, location, month, performanceLevel, refreshVersion, region, scopedTeam]);

  return useMemo(() => {
    const levelData = performanceLevel === 'All'
      ? allData
      : allData.filter((record) => (record.performance_level || 'Employee') === performanceLevel);

    // Step 0: Get unique months dynamically from allData
    const monthsSet = new Set<string>();
    levelData.forEach((r) => {
      if (r.identity && r.identity.month && r.identity.name.toLowerCase() !== 'total') {
        monthsSet.add(r.identity.month);
      }
    });
    const uniqueMonths = Array.from(monthsSet);
    uniqueMonths.sort((a, b) => (MONTH_ORDER[a] || 0) - (MONTH_ORDER[b] || 0));

    // Step 1: Filter by month
    let filtered = levelData;
    if (month !== 'All') {
      filtered = filtered.filter((r) => r.identity.month === month);
    }

    // Step 1.5: Filter by Region
    if (region !== 'All') {
      filtered = filtered.filter((r) => {
        const rRegion = r.region || (sameTeam(r.identity.team, 'Inbound UAE') ? 'UAE' : 'EGY');
        return rRegion.toUpperCase() === region.toUpperCase();
      });
    }

    // Step 2: Separate agents from "Total" rows
    const agents = filtered.filter(hasRealActivity);
    const totalRows = filtered.filter(
      (r) => r.identity.name.toLowerCase() === 'total'
    );

    // Step 3: Compute agent-level display values adjusted by location
    const agentsWithLocationData: AgentWithLocation[] = agents.map((agent) => {
      const bookings = getGeoValue(agent.geo.bookings, location);
      const attended = getGeoValue(agent.geo.attended, location);
      const rawData = agent.raw_data as Record<string, unknown> | undefined;

      // Fix AHT raw if zero or empty
      let ahtMins = parseAHTtoMinutes(agent.calls.aht_raw);
      if (ahtMins === 0 && rawData) {
        const rawVal = rawData['AHT_Minutes'] ?? rawData['A.AHT'] ?? rawData.AHT;
        if (rawVal) {
          if (typeof rawVal === 'number') {
            ahtMins = rawVal < 1.0 ? rawVal * 24 * 60 : rawVal;
          } else if (typeof rawVal === 'string') {
            ahtMins = parseAHTtoMinutes(rawVal);
          }
        }
      }

      if (ahtMins > 0 && (agent.calls.aht_raw === '00:00:00' || !agent.calls.aht_raw)) {
        const h = Math.floor(ahtMins / 60);
        const m = Math.floor(ahtMins % 60);
        const s = Math.round((ahtMins * 60) % 60);
        agent.calls.aht_raw = `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
      }

      return {
        ...agent,
        locationBookings: bookings,
        locationAttended: attended,
        locationAttendRate: bookings > 0 ? attended / bookings : 0,
      };
    });

    // Step 4: Build monthly summaries for charts (single pass grouping)
    const monthBuckets: Record<string, AgentRecord[]> = {};
    for (const r of levelData) {
      const m = r.identity.month;
      if (r.identity.name.toLowerCase() === 'total') continue;
      if (!monthBuckets[m]) monthBuckets[m] = [];
      monthBuckets[m].push(r);
    }
    const monthSummaries: MonthSummary[] = uniqueMonths.map((m) => {
      const monthAgents = monthBuckets[m] || [];
      let totalBookings = 0, totalAttended = 0, totalInbound = 0, totalAbandoned = 0, totalHandled = 0;
      let sumBooking = 0, sumAttend = 0, sumAbandon = 0, sumScore = 0;
      for (const a of monthAgents) {
        totalBookings += getGeoValue(a.geo.bookings, location);
        totalAttended += getGeoValue(a.geo.attended, location);
        totalInbound += a.calls.inbound;
        totalAbandoned += a.calls.abandoned;
        totalHandled += a.calls.total_handled;
        sumBooking += a.actual.booking_rate;
        sumAttend += a.actual.attend_rate;
        sumAbandon += a.actual.abandon_rate;
        let sc = a.evaluation.score;
        if (sc <= 10.0 && sc > 0) sc = sc * 100;
        sumScore += sc;
      }
      const count = monthAgents.length;
      return {
        month: m.substring(0, 3),
        monthFull: m,
        totalBookings, totalAttended, totalInbound, totalAbandoned, totalHandled,
        avgBookingRate: count > 0 ? sumBooking / count : 0,
        avgAttendRate: count > 0 ? sumAttend / count : 0,
        avgAbandonRate: count > 0 ? sumAbandon / count : 0,
        avgScore: count > 0 ? sumScore / count : 0,
        agentCount: count,
      };
    });

    // Step 5: Build per-month data for growth trend chart
    const cumulativeData: CumulativeMonthPoint[] = monthSummaries.map((ms) => ({
      month: `${ms.monthFull} 2026`,
      attended: ms.totalAttended,
      target: Math.round(ms.totalBookings * 0.75),
    }));

    // Step 6: Build location summaries with show-up & no-show rates
    const locationKeys: { key: keyof GeoBreakdown; label: string }[] = [
      { key: 'dubai', label: 'Dubai' },
      { key: 'sharjah', label: 'Sharjah' },
      { key: 'ajman', label: 'Ajman' },
      { key: 'clinics', label: 'Clinics' },
    ];

    const locationSummaries: LocationSummary[] = locationKeys.map(({ key, label }) => {
      let bookings = 0;
      let attended = 0;
      agents.forEach((a) => {
        bookings += a.geo.bookings[key];
        attended += a.geo.attended[key];
      });
      const showUpRate = bookings > 0 ? Math.round((attended / bookings) * 1000) / 10 : 0;
      return {
        location: label,
        bookings,
        attended,
        showUpRate,
        noShowRate: Math.round((100 - showUpRate) * 10) / 10,
      };
    });

    // Step 7: Compute grand totals (single pass)
    let gInbound = 0, gOutbound = 0, gHandled = 0, gAbandoned = 0, gBookings = 0, gAttended = 0;
    let gScore = 0, gAHT = 0;
    for (const a of agents) {
      gInbound += a.calls.inbound;
      gOutbound += a.calls.outbound;
      gHandled += a.calls.total_handled;
      gAbandoned += a.calls.abandoned;
      gBookings += getGeoValue(a.geo.bookings, location);
      gAttended += getGeoValue(a.geo.attended, location);
      gScore += a.evaluation.score;
      gAHT += parseAHTtoSeconds(a.calls.aht_raw);
    }
    const grandTotals = {
      inbound: gInbound, outbound: gOutbound, totalHandled: gHandled,
      abandoned: gAbandoned, totalBookings: gBookings, totalAttended: gAttended,
    };

    const overallBookingRate =
      grandTotals.totalHandled > 0 ? grandTotals.totalBookings / grandTotals.totalHandled : 0;
    const overallAttendRate =
      grandTotals.totalBookings > 0 ? grandTotals.totalAttended / grandTotals.totalBookings : 0;
    const overallAbandonRate =
      grandTotals.totalHandled > 0 ? grandTotals.abandoned / grandTotals.totalHandled : 0;

    // Step 8: Value leakage metrics
    const valueLeakage: ValueLeakageData = {
      noShowRate: 1 - overallAttendRate,
      unconvertedRate: 1 - overallBookingRate,
      lostVisits: grandTotals.totalBookings - grandTotals.totalAttended,
      lostCalls: grandTotals.totalHandled - grandTotals.totalBookings,
    };

    // Step 9: Strategic score
    const avgScore = agents.length > 0 ? gScore / agents.length : 0;

    // Step 10: Conversion funnel data
    const funnelData: FunnelData = {
      calls: grandTotals.totalHandled,
      bookings: grandTotals.totalBookings,
      attended: grandTotals.totalAttended,
      callToBookingRate: overallBookingRate,
      bookingToAttendRate: overallAttendRate,
    };

    // Step 11: Average AHT
    const avgAHTSeconds = agents.length > 0 ? gAHT / agents.length : 0;

    // Step 12: KPI vs Target
    const kpiVsTarget: KpiVsTarget[] = [
      {
        label: 'Booking Rate',
        actual: overallBookingRate * 100,
        target: 45,
        unit: '%',
        isLowerBetter: false,
        isMet: overallBookingRate * 100 >= 45,
      },
      {
        label: 'Attendance Rate',
        actual: overallAttendRate * 100,
        target: 75,
        unit: '%',
        isLowerBetter: false,
        isMet: overallAttendRate * 100 >= 75,
      },
      {
        label: 'Avg. Handle Time',
        actual: avgAHTSeconds,
        target: 150, // 2:30
        unit: 'time',
        isLowerBetter: true,
        isMet: avgAHTSeconds <= 150,
      },
      {
        label: 'Abandon Rate',
        actual: overallAbandonRate * 100,
        target: 1,
        unit: '%',
        isLowerBetter: true,
        isMet: overallAbandonRate * 100 <= 1,
      },
    ];

    // Step 13: Outlier detection
    const outliers = {
      highBookingLowAttend: agentsWithLocationData.filter(
        (a) => a.actual.booking_rate >= 0.5 && a.actual.attend_rate < 0.5
      ),
      highAHT: agentsWithLocationData.filter(
        (a) => parseAHTtoSeconds(a.calls.aht_raw) > 150
      ),
      highAbandon: agentsWithLocationData.filter(
        (a) => a.actual.abandon_rate > 0.02
      ),
    };

    // Step 13.5: Calculate Trends for Comparison
    let trends = null;
    const currMonthName = month === 'All'
      ? (uniqueMonths[uniqueMonths.length - 1] || 'March')
      : month;
    const currIdx = uniqueMonths.indexOf(currMonthName);
    const prevMonthName = currIdx > 0 ? uniqueMonths[currIdx - 1] : null;
    
    if (prevMonthName) {
      const currSum = monthSummaries.find(m => m.monthFull === currMonthName);
      const prevSum = monthSummaries.find(m => m.monthFull === prevMonthName);
      
      if (currSum && prevSum) {
        // Attendance
        const currAttend = currSum.avgAttendRate;
        const prevAttend = prevSum.avgAttendRate;
        const attendDiff = prevAttend > 0 ? ((currAttend - prevAttend) / prevAttend) * 100 : 0;
        
        // Booking
        const currBooking = currSum.avgBookingRate * 100;
        const prevBooking = prevSum.avgBookingRate * 100;
        const bookingDiff = currBooking - prevBooking;
        
        // Abandon
        const currAbandon = currSum.avgAbandonRate * 100;
        const prevAbandon = prevSum.avgAbandonRate * 100;
        const abandonDiff = currAbandon - prevAbandon;

        // Calculate AHT and Score directly from allData for those specific months
        const currAgents = levelData.filter((r) => r.identity.month === currMonthName && r.identity.name.toLowerCase() !== 'total');
        const prevAgents = levelData.filter((r) => r.identity.month === prevMonthName && r.identity.name.toLowerCase() !== 'total');
        
        const currAHT = currAgents.length > 0 ? currAgents.reduce((s, a) => s + parseAHTtoSeconds(a.calls.aht_raw), 0) / currAgents.length : 0;
        const prevAHT = prevAgents.length > 0 ? prevAgents.reduce((s, a) => s + parseAHTtoSeconds(a.calls.aht_raw), 0) / prevAgents.length : 0;
        const ahtDiff = currAHT - prevAHT;

        const currScore = currAgents.length > 0 ? currAgents.reduce((s, a) => {
          let sc = a.evaluation.score;
          if (sc <= 10.0 && sc > 0) sc = sc * 100;
          return s + sc;
        }, 0) / currAgents.length : 0;
        const prevScore = prevAgents.length > 0 ? prevAgents.reduce((s, a) => {
          let sc = a.evaluation.score;
          if (sc <= 10.0 && sc > 0) sc = sc * 100;
          return s + sc;
        }, 0) / prevAgents.length : 0;
        const scoreDiff = currScore - prevScore;

        trends = {
          attendRate: `${attendDiff > 0 ? '+' : ''}${attendDiff.toFixed(1)}%`,
          attendRatePositive: attendDiff >= 0,
          bookingRate: `${bookingDiff > 0 ? '+' : ''}${bookingDiff.toFixed(1)}%`,
          bookingRatePositive: bookingDiff >= 0,
          abandonRate: `${abandonDiff > 0 ? '+' : ''}${abandonDiff.toFixed(1)}%`,
          abandonRatePositive: abandonDiff <= 0,
          aht: `${ahtDiff > 0 ? '+' : ''}${Math.round(ahtDiff)}s`,
          ahtPositive: ahtDiff <= 0,
          score: `${scoreDiff > 0 ? '+' : ''}${scoreDiff.toFixed(1)}%`,
          scorePositive: scoreDiff >= 0,
        };
      }
    }

    return {
      uniqueMonths,
      trends,
      agents: agentsWithLocationData,
      totalRows,
      monthSummaries,
      cumulativeData,
      locationSummaries,
      valueLeakage,
      strategicScore: Math.round(avgScore),
      grandTotals: {
        ...grandTotals,
        overallBookingRate,
        overallAttendRate,
        overallAbandonRate,
      },
      funnelData,
      avgAHTSeconds,
      kpiVsTarget,
      outliers,
      loading: enabled ? loading : false,
      dataSource,
      errorMessage,
    };
  }, [allData, month, location, region, performanceLevel, loading, dataSource, errorMessage, enabled]);
}

export function useCRMData(month: MonthKey, location: LocationKey, performanceLevel: PerformanceLevelFilter = 'All') {
  const { agents, loading } = usePerformanceData(month, location, 'All', performanceLevel);

  const data = useMemo(() => {
    return agents.map((agent, i) => {
      let score = agent.evaluation.score;
      score = normalizeScore(score);

      let status: EmployeeStatus = 'Average';
      let trend: Trend = 'Stable';
      let planningCategory: PlanningCategory = 'Training';

      const backendRootCause = agent.evaluation.root_cause?.kpi;
      const backendSuggestedAction = agent.evaluation.suggested_action;

      let rootCause = backendRootCause || 'Process adherence';
      let aiSuggestion = backendSuggestedAction || 'Review standard operating procedures.';

      if (score >= 95) {
        status = 'Exceeds'; trend = 'Up'; planningCategory = 'Promotion';
        if (!backendRootCause) rootCause = 'Consistent high quality';
        if (!backendSuggestedAction) aiSuggestion = 'Ready for leadership training.';
      } else if (score >= 85) {
        status = 'Meet'; trend = 'Stable'; planningCategory = 'Reward';
        if (!backendRootCause) rootCause = 'Good communication skills';
        if (!backendSuggestedAction) aiSuggestion = 'Assign as peer mentor.';
      } else if (score < 60) {
        status = 'SIP'; trend = 'Down'; planningCategory = 'SIP';
        if (!backendRootCause) rootCause = 'Attendance & Quality';
        if (!backendSuggestedAction) aiSuggestion = 'Immediate intervention required.';
      } else if (score < 75) {
        status = 'PI'; trend = 'Down'; planningCategory = 'PI';
        if (!backendRootCause) rootCause = 'Product knowledge gaps';
        if (!backendSuggestedAction) aiSuggestion = 'Assign product refresher modules.';
      }

      return {
        id: agent.identity.employee_id || `emp-${i}`,
        name: agent.identity.name,
        team: agent.identity.team || 'Customer Success',
        score: score,
        grade: agent.evaluation.grade,
        status: status,
        planningCategory: planningCategory,
        trend: trend,
        rootCause: rootCause,
        aiSuggestion: aiSuggestion,
        managerNotes: agent.evaluation.manager_notes || 'No notes yet.',
        correctiveAction: agent.evaluation.corrective_action || undefined,
        recentActions: [],
        stats: agent
      } as EmployeeCRMRecord;
    });
  }, [agents]);

  return { data, loading };
}

// ─── Team-level hooks (for TeamDashboardView & ExecutiveView) ─────────────────

/** Parse "HH:MM:SS" → total minutes */
export function parseAHTtoMinutes(aht: string): number {
  return parseAHTtoSeconds(aht) / 60;
}

export interface TeamAgentRow {
  id: string;
  name: string;
  team: string;
  month: string;
  performanceLevel: import('../types').PerformanceLevel;
  score: number;          // 0-100
  displayWeightedScore?: number;
  gradeClass: import('../types').GradeClass;
  gradeLabel: string;     // raw grade from backend
  status: 'Meet' | 'Average' | 'Below';
  rootCauseAuto: string;
  rootCauseNote: string;  // from backend manager_notes
  correctiveAction: string;
  suggestedAction: string;
  ahtMinutes: number;
  bookingRate: number;    // 0-1
  attendRate: number;     // 0-1
  raw: import('../types').AgentRecord;
}

export interface TeamWeightConfig {
  team: string;
  db_name?: string;
  name?: string;
  weights: Record<string, number>;
  scopes?: Array<{
    position: string | null;
    weights: Record<string, number>;
  }>;
}

/**
 * Returns agents for a specific team with all computed display fields.
 * teamName = exact team string from backend ("Inbound", "Outbound", etc.)
 */
export function useTeamData(
  teamName: string | null,
  month: MonthKey,
  region: 'All' | 'EGY' | 'UAE' = 'All',
  location: LocationKey = 'all',
  weightsList?: TeamWeightConfig[],
  performanceLevel: PerformanceLevelFilter = 'All',
  selectedLocations?: LocationKey[],
  preApprovalsWorkflow: PreApprovalsWorkflowFilter = 'all',
  callCenterChannel: CallCenterChannelFilter = 'all',
  rcmDomain: RcmDomainFilter = 'all',
  rcmGroup: RcmGroupFilter = 'all',
  legacyEnabled = true,
) {
  const sourceMonth = scopedPerformanceApiEnabled ? month : 'All';
  const scopedTeam = scopedPerformanceApiEnabled && teamName && !['Call Center', 'Pre-Approvals', 'RCM'].includes(teamName)
    ? teamName
    : undefined;
  const { agents: allAgents, loading, dataSource, errorMessage } = usePerformanceData(
    sourceMonth,
    location,
    region,
    performanceLevel,
    legacyEnabled,
    scopedTeam,
  );

  return useMemo(() => {
    let filtered = teamName
      ? allAgents.filter((a) => sameTeam(a.identity.team, teamName))
      : allAgents;

    if (teamName && (isPreApprovalsUaeTeam(teamName) || (isRcmTeam(teamName) && rcmDomain === 'pre_approvals')) && preApprovalsWorkflow !== 'all') {
      filtered = filtered.filter((agent) => isPreApprovalsWorkflowTeam(agent.identity.team, preApprovalsWorkflow));
    }
    if (teamName && isCallCenterTeam(teamName) && callCenterChannel !== 'all') {
      filtered = filtered.filter((agent) => isCallCenterChannelTeam(agent.identity.team, callCenterChannel));
    }
    if (teamName && isRcmTeam(teamName) && rcmDomain !== 'all') {
      filtered = filtered.filter((agent) => isRcmDomainTeam(agent.identity.team, rcmDomain));
    }
    if (teamName && isRcmTeam(teamName) && rcmGroup !== 'all') {
      filtered = filtered.filter((agent) => isRcmGroupTeam(agent.identity.team, rcmGroup, agent.region ?? agent.identity.region));
    }

    const branchFilter = selectedLocations && selectedLocations.length > 0
      ? selectedLocations
      : [location];
    if (!branchFilter.includes('all')) {
      filtered = filtered.filter((a) => branchFilter.some((branch) => agentMatchesLocation(a, branch)));
    }

    const teamMonths = resolveTeamMonths(filtered, null);

    // Get previous month's agents for trend calculation
    const currMonthName = month === 'All'
      ? (teamMonths[teamMonths.length - 1] || '')
      : month;
    const currIdx = teamMonths.indexOf(currMonthName);
    const prevMonth = currIdx > 0 ? teamMonths[currIdx - 1] : null;
    const headcountSnapshot = resolveHeadcountSnapshot(filtered, month);

    // Current month's records for display: when month is 'All', resolve each employee's latest available month
    const currentFiltered = month === 'All'
      ? getLatestRecordPerEmployee(filtered)
      : filtered.filter((a) => a.identity.month === currMonthName);

    const rows: TeamAgentRow[] = currentFiltered.map((agent, i) => {
      const rowWeights = weightsList?.find((w) => sameTeam(w.team, agent.identity.team))?.weights;
      const score = resolveDisplayScore(agent, rowWeights);

      const gradeClass = resolveRecordGradeClass(agent, score);

      const status: 'Meet' | 'Average' | 'Below' =
        gradeClass === 'A' || gradeClass === 'B'
          ? 'Meet'
          : gradeClass === 'C'
            ? 'Average'
            : 'Below';

      const ahtMins = parseAHTtoMinutes(agent.calls.aht_raw);

      const rootCauseAuto = resolveAutoRootCause(agent, gradeClass);

      return {
        id: agent.identity.employee_id || `emp-${i}`,
        name: agent.identity.name,
        team: teamName === RCM_TEAM
          ? (agent.identity.team || RCM_TEAM)
          : teamName && (isMergedBranchTeam(teamName) || teamName === PRE_APPROVALS_UAE_TEAM || teamName === CALL_CENTER_TEAM)
          ? canonicalTeamName(teamName)
          : agent.identity.team || '',
        month: agent.identity.month || month,
        performanceLevel: agent.performance_level || 'Employee',
        score,
        displayWeightedScore: score,
        gradeClass,
        gradeLabel: agent.evaluation.grade,
        status,
        rootCauseAuto,
        rootCauseNote: agent.evaluation.manager_notes || '',
        correctiveAction: agent.evaluation.corrective_action || '',
        suggestedAction: agent.evaluation.suggested_action || '',
        ahtMinutes: ahtMins,
        bookingRate: agent.actual.booking_rate,
        attendRate: agent.actual.attend_rate,
        raw: agent,
      };
    });

    // Sort by score descending by default
    rows.sort((a, b) => b.score - a.score);

    const summary = calculatePerformanceSummary(
      rows.map((row) => ({
        team: row.team,
        month: row.month,
        score: row.score,
        gradeClass: row.gradeClass,
        employee_id: row.id,
      })),
      {
        // RCM rows intentionally retain their source-team identity for actions
        // and history; the rows are already scoped before this summary runs.
        // Applying a literal `team: RCM` filter here would exclude every source row.
        team: teamName && teamName !== RCM_TEAM ? teamName : undefined,
        month,
      }
    );

    // Calculate previous month overall stats for MoM trends
    let prevAvgScore = 0;
    let prevPctAB = 0;
    let prevPctDE = 0;
    let prevTotalAgents = 0;
    if (prevMonth) {
      const prevFiltered = filtered.filter((a) => a.identity.month === prevMonth);

      const prevRowsScores = prevFiltered.map((agent) => {
        const rowWeights = weightsList?.find((weightConfig) => sameTeam(weightConfig.team, agent.identity.team))?.weights;
        const score = resolveDisplayScore(agent, rowWeights);
        return { score, grade: resolveRecordGradeClass(agent, score) };
      });
      prevTotalAgents = resolveHeadcountSnapshot(filtered, prevMonth).totalAgents;
      if (prevRowsScores.length > 0) {
        prevAvgScore = prevRowsScores.reduce((total, item) => total + item.score, 0) / prevRowsScores.length;
        const abCount = prevRowsScores.filter((item) => item.grade === 'A' || item.grade === 'B').length;
        const deCount = prevRowsScores.filter((item) => item.grade === 'D' || item.grade === 'E').length;
        prevPctAB = (abCount / prevRowsScores.length) * 100;
        prevPctDE = (deCount / prevRowsScores.length) * 100;
      }
    }

    return {
      rows,
      avgScore: summary.averagePerformanceScore,
      classCounts: summary.classCounts,
      pctAB: summary.classABPercentage,
      pctDE: summary.classDEPercentage,
      totalAgents: headcountSnapshot.totalAgents,
      uniqueTeamCount: headcountSnapshot.uniqueTeamCount,
      prevMonth,
      currMonthName,
      loading,
      dataSource,
      errorMessage,
      prevAvgScore,
      prevPctAB,
      prevPctDE,
      prevTotalAgents,
    };
  }, [allAgents, teamName, month, location, loading, dataSource, errorMessage, weightsList, selectedLocations, preApprovalsWorkflow, callCenterChannel, rcmDomain, rcmGroup]);
}

/** Returns per-team aggregates for the Executive Summary table */
export function useAllTeamsSummary(
  month: MonthKey,
  region: 'All' | 'EGY' | 'UAE' = 'All',
  location: LocationKey = 'all',
  performanceLevel: PerformanceLevelFilter = 'All',
  weightsList?: TeamWeightConfig[],
  legacyEnabled = true,
) {
  const { data: teamConfigs = [], isLoading: configsLoading } = useAllTeamConfigs();
  const {
    rows,
    totalAgents,
    uniqueTeamCount,
    currMonthName,
    loading,
    dataSource,
    errorMessage,
  } = useTeamData(null, month, region, location, weightsList, performanceLevel, undefined, 'all', 'all', 'all', 'all', legacyEnabled);

  return useMemo(() => {
    const summary = calculatePerformanceSummary(
      rows.map((row) => ({
        team: row.team,
        month: row.month,
        score: row.score,
        gradeClass: row.gradeClass,
        employee_id: row.id,
      })),
      {}
    );

    const teamMap = new Map<string, { teamName: string; agents: import('../types').AgentRecord[] }>();

    rows.forEach((row) => {
      const rawTeamName = row.team || 'Unknown';
      const logicalName = isRcmTeam(rawTeamName)
        ? RCM_TEAM
        : isPreApprovalsUaeTeam(rawTeamName)
        ? PRE_APPROVALS_UAE_TEAM
        : isCallCenterTeam(rawTeamName)
          ? CALL_CENTER_TEAM
        : canonicalTeamName(rawTeamName) || 'Unknown';
      const normalizedTeamKey = normalizeTeamName(logicalName) || logicalName.toLowerCase().replace(/\s+/g, '-');
      const existing = teamMap.get(normalizedTeamKey);
      if (existing) {
        existing.agents.push(row.raw);
      } else {
        teamMap.set(normalizedTeamKey, { teamName: logicalName, agents: [row.raw] });
      }
    });

    const summaries: import('../types').TeamSummary[] = [];

    teamMap.forEach(({ teamName }, teamKey) => {
      const classCounts = { A: 0, B: 0, C: 0, D: 0, E: 0 };
      const snapshotEmployeeIds = new Set<string>();

      const teamRows = rows.filter((row) => sameCanonicalTeam(row.team, teamName));
      const teamMonths = Array.from(new Set(teamRows.map((r) => r.month))).sort(
        (a, b) => (MONTH_ORDER[a] || 0) - (MONTH_ORDER[b] || 0)
      );
      const teamLatestMonth = month === 'All' ? (teamMonths[teamMonths.length - 1] || currMonthName) : month;

      const latestTeamRows = teamRows.filter((row) => row.month === teamLatestMonth);
      latestTeamRows.forEach((row) => {
        if (row.month === teamLatestMonth && row.id) snapshotEmployeeIds.add(row.id);
        classCounts[row.gradeClass]++;
      });
      const config = isMergedBranchTeam(teamName) || isPreApprovalsUaeTeam(teamName) || teamName === CALL_CENTER_TEAM || teamName === RCM_TEAM
        ? undefined
        : teamConfigs.find((candidate) => sameCanonicalTeam(candidate.team, teamName));
      const aggregateScore = calculateAggregatedTeamPerformance(
        latestTeamRows.map((row) => row.raw),
        config,
        { location },
      )?.score ?? null;

      // The settings endpoint may still be loading when this hook first
      // renders.  Recreate configured weights from the team definition so the
      // displayed employee score is stable and does not briefly fall back to
      // a stale persisted fraction (e.g. 9.3% for Sales).
      const configuredWeights = config?.kpis.length
        ? Object.fromEntries(config.kpis.map((kpi) => [kpi.key, kpi.weight]))
        : undefined;
      const weightConfig = weightsList?.find((candidate) => sameCanonicalTeam(candidate.team, teamName));
      const employeeScores = teamName === RCM_TEAM
        ? latestTeamRows.map((row) => row.score)
        : latestTeamRows.map((row) => resolveDisplayScore(
          row.raw,
          weightConfig?.weights ?? configuredWeights,
        ));

      summaries.push({
        teamId: TEAM_ID_MAP[teamName] || teamKey,
        teamName,
        agentCount: snapshotEmployeeIds.size,
        avgScore: reconcileTeamSummaryScore(aggregateScore, employeeScores),
        classA: classCounts.A,
        classB: classCounts.B,
        classC: classCounts.C,
        classD: classCounts.D,
        classE: classCounts.E,
      });
    });

    summaries.sort((a, b) => b.avgScore - a.avgScore);
    const scoredTeams = summaries.filter((team) => team.agentCount > 0);
    const overallAggregateScore = scoredTeams.length > 0
      ? scoredTeams.reduce((sum, team) => sum + team.avgScore, 0) / scoredTeams.length
      : 0;

    return {
      summaries,
      totalAgents,
      uniqueTeamCount,
      overallAvgScore: overallAggregateScore,
      pctAB: summary.classABPercentage,
      pctDE: summary.classDEPercentage,
      allClassCounts: summary.classCounts,
      loading: loading || configsLoading,
      dataSource,
      errorMessage,
    };
  }, [rows, month, totalAgents, uniqueTeamCount, currMonthName, loading, dataSource, errorMessage, teamConfigs, configsLoading, location, weightsList]);
}
