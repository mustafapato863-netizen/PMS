import type { AgentRecord, KPIConfig, LocationKey } from '../../types';
import { getWeightForLabel } from '../../utils/kpiScore';
import type { TeamConfig } from '../../schemas/teamConfig.schema';
import { aggregateConfiguredTeamKpis, calculateAggregatedTeamPerformance } from './teamKpiAggregator';

export interface TeamKpiVolumeData {
  totalBookings: number;
  totalAttended: number;
  prevTotalBookings: number | null;
  prevTotalAttended: number | null;
  bestTotalBookings: number | null;
  bestTotalBookingsMonth: string | null;
  bestTotalAttended: number | null;
  bestTotalAttendedMonth: string | null;
}

export interface TeamKpiAnalysis {
  key: string;
  label: string;
  unit: KPIConfig['unit'];
  lowerBetter: boolean;
  actual: number;
  target: number;
  previousActual: number | null;
  baselineActual: number | null;
  baselineMonth: string | null;
  previousBaselineActual: number | null;
  previousBaselineMonth: string | null;
  isNewBaseline: boolean;
  weight: number | null;
  contribution: number | null;
  capAchievement?: boolean;
  achievement: number | null;
  movementPercent: number | null;
  movementPositive: boolean | null;
  targetMet: boolean;
  gapPoints: number | null;
  severity: 'critical' | 'attention' | 'on_target' | 'configuration_requires_review';
  volumeData: TeamKpiVolumeData | null;
}

interface TeamKpiAnalysisOptions {
  includeNoShow?: boolean;
  includeAht?: boolean;
  location?: LocationKey;
  teamWeights?: Record<string, number>;
  baselineRecords?: AgentRecord[];
  teamConfig?: TeamConfig;
}

const normalizeKey = (label: string) => label.trim().toLowerCase().replace(/[^a-z0-9]+/g, '_');

const MONTH_NUMBER: Record<string, number> = {
  January: 1,
  February: 2,
  March: 3,
  April: 4,
  May: 5,
  June: 6,
  July: 7,
  August: 8,
  September: 9,
  October: 10,
  November: 11,
  December: 12,
};

const aggregate = (records: AgentRecord[], teamConfig?: TeamConfig, location: LocationKey = 'all') => {
  const buckets = new Map<string, {
    label: string;
    unit: KPIConfig['unit'];
    lowerBetter: boolean;
    actual: number;
    target: number;
    weight: number;
    weightCount: number;
    contribution: number;
    contributionCount: number;
    capAchievement: boolean;
    count: number;
  }>();

  const configured = calculateAggregatedTeamPerformance(records, teamConfig, { location })?.kpis
    ?? aggregateConfiguredTeamKpis(records, teamConfig, { location });
  configured.forEach((kpi) => {
      const key = normalizeKey(kpi.label);
      const bucket = buckets.get(key) || {
        label: kpi.label,
        unit: kpi.unit,
        lowerBetter: !!kpi.isLowerBetter,
        actual: 0,
        target: 0,
        weight: 0,
        weightCount: 0,
        contribution: 0,
        contributionCount: 0,
        capAchievement: kpi.capAchievement,
        count: 0,
      };
      bucket.actual = kpi.actual;
      bucket.target = kpi.target;
      bucket.count = 1;
      if (kpi.weight !== null) {
        bucket.weight = kpi.weight;
        bucket.weightCount = 1;
      }
      if (kpi.contribution !== null) {
        const weight = Math.max(Number(kpi.weight ?? 0), 0);
        bucket.contribution = Math.min(Math.max(Number(kpi.contribution), 0), weight * 100);
        bucket.contributionCount = 1;
      }
      bucket.capAchievement = true;
      buckets.set(key, bucket);
  });

  return new Map([...buckets.entries()].map(([key, value]) => [key, {
    ...value,
    actual: value.actual / value.count,
    target: value.target / value.count,
    weight: value.weightCount ? value.weight / value.weightCount : null,
    contribution: value.contributionCount ? value.contribution / value.contributionCount : null,
  }]));
};

const geoTotal = (record: AgentRecord, field: 'bookings' | 'attended', location: LocationKey) => {
  const values = record.geo?.[field];
  if (!values) return 0;
  if (location !== 'all') return Number(values[location]) || 0;
  return Object.values(values).reduce((sum, value) => sum + (Number(value) || 0), 0);
};

const addNoShowAnalysis = (
  buckets: ReturnType<typeof aggregate>,
  records: AgentRecord[],
  location: LocationKey,
) => {
  const totals = records.reduce(
    (result, record) => ({
      bookings: result.bookings + geoTotal(record, 'bookings', location),
      attended: result.attended + geoTotal(record, 'attended', location),
    }),
    { bookings: 0, attended: 0 },
  );
  if (totals.bookings <= 0) return;
  buckets.set('no_show_rate', {
    label: 'No Show Rate',
    unit: '%',
    lowerBetter: true,
    actual: (totals.bookings - totals.attended) / totals.bookings,
    target: 0.2,
    weight: null,
    weightCount: 0,
    contribution: null,
    contributionCount: 0,
    capAchievement: true,
    count: 1,
  });
};

const parseAhtMinutes = (value: unknown) => {
  if (typeof value === 'string' && value.includes(':')) {
    const [hours = 0, minutes = 0, seconds = 0] = value.split(':').map(Number);
    return hours * 60 + minutes + seconds / 60;
  }
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric <= 0) return 0;
  if (numeric < 1) return numeric * 24 * 60;
  if (numeric > 10) return numeric / 60;
  return numeric;
};

const addAhtAnalysis = (buckets: ReturnType<typeof aggregate>, records: AgentRecord[]) => {
  if ([...buckets.keys()].some((key) => key === 'aht' || key.includes('handle_time'))) return;

  let weightedMinutes = 0;
  let handledCalls = 0;
  let unweightedMinutes = 0;
  let recordCount = 0;
  let targetMinutes = 0;
  let targetCount = 0;

  records.forEach((record) => {
    const actual = parseAhtMinutes(record.calls?.aht_raw);
    if (actual > 0) {
      const handled = Number(record.calls?.total_handled) || 0;
      weightedMinutes += actual * handled;
      handledCalls += handled;
      unweightedMinutes += actual;
      recordCount += 1;
    }
    const target = parseAhtMinutes(record.raw_data?.['T.AHT'] ?? record.raw_data?.['T.AHTTarget'] ?? record.raw_data?.['T.AHT_Target']);
    if (target > 0) {
      targetMinutes += target;
      targetCount += 1;
    }
  });

  if (recordCount === 0 || targetCount === 0) return;
  buckets.set('aht', {
    label: 'AHT (Handle Time)',
    unit: 'min',
    lowerBetter: true,
    actual: handledCalls > 0 ? weightedMinutes / handledCalls : unweightedMinutes / recordCount,
    target: targetMinutes / targetCount,
    weight: null,
    weightCount: 0,
    contribution: null,
    contributionCount: 0,
    capAchievement: true,
    count: 1,
  });
};

const aggregateForAnalysis = (records: AgentRecord[], options: TeamKpiAnalysisOptions) => {
  const buckets = aggregate(records, options.teamConfig, options.location);
  if (options.includeNoShow) addNoShowAnalysis(buckets, records, options.location ?? 'all');
  if (options.includeAht) addAhtAnalysis(buckets, records);
  return buckets;
};

const historicalBaselines = (records: AgentRecord[], options: TeamKpiAnalysisOptions) => {
  const periods = new Map<string, { key: string; month: string; year: number | null; records: AgentRecord[] }>();
  records.forEach((record) => {
    const month = record.identity.month;
    if (!month) return;
    const year = record.year ?? null;
    const periodKey = `${year ?? 'unknown'}:${month}`;
    const period = periods.get(periodKey) ?? {
      key: periodKey,
      month,
      year,
      records: [],
    };
    period.records.push(record);
    periods.set(periodKey, period);
  });

  return [...periods.values()]
    .sort((left, right) =>
      (left.year ?? 0) - (right.year ?? 0)
      || (MONTH_NUMBER[left.month] ?? 0) - (MONTH_NUMBER[right.month] ?? 0))
    .map((period) => ({
      key: period.key,
      month: period.month,
      year: period.year,
      records: period.records,
      kpis: aggregateForAnalysis(period.records, options),
    }));
};

const selectBestBaseline = (
  periods: ReturnType<typeof historicalBaselines>,
  key: string,
  lowerBetter: boolean,
) => periods.reduce<{ actual: number; month: string } | null>((best, period) => {
  const candidate = period.kpis.get(key)?.actual;
  if (candidate === undefined || !Number.isFinite(candidate)) return best;
  if (best === null || (lowerBetter ? candidate < best.actual : candidate > best.actual)) {
    return { actual: candidate, month: period.month };
  }
  return best;
}, null);

const sumGeoField = (records: AgentRecord[], field: 'bookings' | 'attended', location: LocationKey = 'all') =>
  records.reduce((sum, r) => sum + geoTotal(r, field, location), 0);

type BaselinePeriodWithRecords = { key: string; month: string; year: number | null; records: AgentRecord[] };

const bestGeoMonth = (
  baselinePeriods: BaselinePeriodWithRecords[],
  field: 'bookings' | 'attended',
  location: LocationKey = 'all',
): { total: number; month: string } | null => {
  let best: { total: number; month: string } | null = null;
  baselinePeriods.forEach((period) => {
    const total = sumGeoField(period.records, field, location);
    if (total > 0 && (best === null || total > best.total)) {
      best = { total, month: period.month };
    }
  });
  return best;
};

export const buildTeamKpiAnalysis = (
  currentRecords: AgentRecord[],
  previousRecords: AgentRecord[] = [],
  options: TeamKpiAnalysisOptions = {},
): TeamKpiAnalysis[] => {
  const current = aggregateForAnalysis(currentRecords, options);
  const previous = aggregateForAnalysis(previousRecords, options);
  const baselines = historicalBaselines(options.baselineRecords ?? currentRecords, options);
  const currentContext = currentRecords[0];
  const currentPeriodKey = currentContext
    ? `${currentContext.year ?? 'unknown'}:${currentContext.identity.month}`
    : null;
  const currentMonthNumber = currentContext ? MONTH_NUMBER[currentContext.identity.month] ?? 0 : 0;
  const eligibleBaselines = !currentContext
    ? baselines
    : baselines.filter((period) => {
      if (currentContext.year !== undefined && period.year !== null) {
        return period.year < currentContext.year
          || (period.year === currentContext.year && (MONTH_NUMBER[period.month] ?? 0) <= currentMonthNumber);
      }
      return (MONTH_NUMBER[period.month] ?? 0) <= currentMonthNumber;
    });
  const previousBaselines = currentPeriodKey === null
    ? eligibleBaselines
    : eligibleBaselines.filter((period) => period.key !== currentPeriodKey);
  if (currentContext && options.teamWeights) {
    current.forEach((value) => {
      const configuredWeight = getWeightForLabel(
        options.teamWeights,
        value.label,
        currentContext.identity.team,
        currentContext.raw_data,
        currentContext.identity.month,
      );
      if (configuredWeight !== undefined) {
        value.weight = configuredWeight > 1 ? configuredWeight / 100 : configuredWeight;
      }
    });
  }

  // Pre-compute raw volume totals for Booking Rate & Attendance Rate
  const loc = options.location ?? 'all';
  const currentTotalBookings = sumGeoField(currentRecords, 'bookings', loc);
  const currentTotalAttended = sumGeoField(currentRecords, 'attended', loc);
  const prevTotalBookings = previousRecords.length > 0 ? sumGeoField(previousRecords, 'bookings', loc) : null;
  const prevTotalAttended = previousRecords.length > 0 ? sumGeoField(previousRecords, 'attended', loc) : null;
  const baselinePeriodsForGeo = (options.baselineRecords
    ? historicalBaselines(options.baselineRecords, options)
    : eligibleBaselines
  ).filter((p) => p.key !== currentPeriodKey);
  const bestBookingsMonth = bestGeoMonth(baselinePeriodsForGeo, 'bookings', loc);
  const bestAttendedMonth = bestGeoMonth(baselinePeriodsForGeo, 'attended', loc);

  return [...current.entries()].map(([key, value]) => {
    const previousActual = previous.get(key)?.actual ?? null;
    const previousBaseline = selectBestBaseline(previousBaselines, key, value.lowerBetter);
    const beatsPreviousBaseline = previousBaseline !== null
      && (value.lowerBetter ? value.actual < previousBaseline.actual : value.actual > previousBaseline.actual);
    const baseline = previousBaseline === null || beatsPreviousBaseline
      ? { actual: value.actual, month: currentContext?.identity.month ?? 'Current period' }
      : previousBaseline;
    const isNewBaseline = previousBaseline !== null && beatsPreviousBaseline;
    const targetMet = value.target > 0 && (value.lowerBetter ? value.actual <= value.target : value.actual >= value.target);
    const rawAchievement = value.target <= 0
      ? null
      : value.lowerBetter
        ? (value.actual <= 0 ? 100 : (value.target / value.actual) * 100)
        : (value.actual / value.target) * 100;
    const achievement = rawAchievement === null
      ? null
      : Math.min(Math.max(rawAchievement, 0), 100);
    const movementPercent = previousActual === null || previousActual === 0
      ? null
      : ((value.actual - previousActual) / Math.abs(previousActual)) * 100;
    const movementPositive = movementPercent === null || movementPercent === 0
      ? null
      : value.lowerBetter ? movementPercent < 0 : movementPercent > 0;
    const maxContribution = value.weight === null ? null : value.weight * 100;
    const gapPoints = achievement === null
      ? null
      : maxContribution === null || value.contribution === null
        ? Math.max(100 - achievement, 0)
        : Math.max(maxContribution - value.contribution, 0);
    const relativeTargetGap = value.target > 0 ? Math.abs(value.actual - value.target) / value.target : 0;
    const hasWeightedImpact = value.weight !== null && value.contribution !== null;
    const severity: TeamKpiAnalysis['severity'] = achievement === null
      ? 'configuration_requires_review'
      : targetMet
      ? 'on_target'
      : hasWeightedImpact
        ? (gapPoints ?? 0) >= 5 || relativeTargetGap >= 0.2 ? 'critical' : 'attention'
        : achievement < 80 ? 'critical' : 'attention';

    // Attach volume data for Booking Rate & Attendance Rate only
    let volumeData: TeamKpiVolumeData | null = null;
    if (key === 'booking_rate' || key === 'attendance_rate') {
      volumeData = {
        totalBookings: currentTotalBookings,
        totalAttended: currentTotalAttended,
        prevTotalBookings,
        prevTotalAttended,
        bestTotalBookings: bestBookingsMonth?.total ?? null,
        bestTotalBookingsMonth: bestBookingsMonth?.month ?? null,
        bestTotalAttended: bestAttendedMonth?.total ?? null,
        bestTotalAttendedMonth: bestAttendedMonth?.month ?? null,
      };
    }

    return {
      key,
      label: value.label,
      unit: value.unit,
      lowerBetter: value.lowerBetter,
      actual: value.actual,
      target: value.target,
      previousActual,
      baselineActual: (baseline?.actual ?? null) as number | null,
      baselineMonth: baseline?.month ?? null,
      previousBaselineActual: previousBaseline?.actual ?? null,
      previousBaselineMonth: previousBaseline?.month ?? null,
      isNewBaseline,
      weight: value.weight,
      contribution: value.contribution === null || value.weight === null
        ? value.contribution
        : Math.min(Math.max(value.contribution, 0), Math.max(value.weight, 0) * 100),
      achievement,
      movementPercent,
      movementPositive,
      targetMet,
      gapPoints,
      severity,
      volumeData,
    };
  }).sort((left, right) => {
    const priority: Record<TeamKpiAnalysis['severity'], number> = { critical: 0, attention: 1, configuration_requires_review: 2, on_target: 3 };
    const ls = left.severity as TeamKpiAnalysis['severity'];
    const rs = right.severity as TeamKpiAnalysis['severity'];
    return priority[ls] - priority[rs] || (right.gapPoints ?? -1) - (left.gapPoints ?? -1);
  });
};

export const formatTeamKpiValue = (value: number, unit: KPIConfig['unit']) => {
  if (unit === '%') return `${(value * 100).toFixed(1)}%`;
  if (unit === 'min') return `${value.toFixed(1)} min`;
  if (unit === 'currency') return `AED ${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}`;
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
};

export const buildTeamKpiRecommendation = (kpi: TeamKpiAnalysis) =>
  kpi.targetMet
    ? `Maintain ${kpi.label}`
    : `${kpi.lowerBetter ? 'Reduce' : 'Improve'} ${kpi.label}`;
