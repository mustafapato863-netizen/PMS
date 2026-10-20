import type { AgentRecord, GradeClass } from '../../types';
import { normalizePerformanceScore } from '../../utils/kpiScore';
import type {
  MarketingAnalytics,
  MarketingEmployeeRow,
  MarketingFilters,
  MarketingInsight,
  MarketingKpiAggregate,
  MarketingKpiConfig,
  MarketingPeriod,
  MarketingPositionSummary,
  MarketingStatus,
  MarketingTeamConfig,
} from './types';

const MONTH_ORDER: Record<string, number> = {
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

const GRADES: GradeClass[] = ['A', 'B', 'C', 'D', 'E'];

export const normalizeMarketingScore = (score: number): number => normalizePerformanceScore(score);

export const getMarketingGrade = (
  record: AgentRecord,
  thresholds: MarketingTeamConfig['grade_thresholds'] = { A: 95, B: 90, C: 80, D: 70 },
): GradeClass => {
  const backendGrade = record.evaluation.grade?.trim().toUpperCase();
  if (GRADES.includes(backendGrade as GradeClass)) return backendGrade as GradeClass;
  const score = normalizeMarketingScore(record.evaluation.score);
  if (score >= thresholds.A) return 'A';
  if (score >= thresholds.B) return 'B';
  if (score >= thresholds.C) return 'C';
  if (score >= thresholds.D) return 'D';
  return 'E';
};

export const getMarketingStatus = (
  record: AgentRecord,
  thresholds?: MarketingTeamConfig['grade_thresholds'],
): Exclude<MarketingStatus, 'All'> => {
  if (record.status === 'Exceeds' || record.status === 'Meets' || record.status === 'Below') {
    return record.status;
  }
  const grade = getMarketingGrade(record, thresholds);
  if (grade === 'A') return 'Exceeds';
  if (grade === 'B' || grade === 'C') return 'Meets';
  return 'Below';
};

export const getMarketingPeriods = (records: AgentRecord[]): MarketingPeriod[] => {
  const periods = new Map<string, MarketingPeriod>();
  records.forEach((record) => {
    const year = Number(record.year);
    const month = record.identity.month;
    const monthNumber = MONTH_ORDER[month];
    if (!Number.isInteger(year) || !monthNumber) return;
    const key = `${year}-${String(monthNumber).padStart(2, '0')}`;
    periods.set(key, {
      year,
      month,
      key,
      label: `${month} ${year}`,
      sortValue: year * 12 + monthNumber,
    });
  });
  return [...periods.values()].sort((left, right) => left.sortValue - right.sortValue);
};

export const getPreviousMarketingPeriod = (
  periods: MarketingPeriod[],
  year: number,
  month: string,
): MarketingPeriod | null => {
  const currentIndex = periods.findIndex((period) => period.year === year && period.month === month);
  return currentIndex > 0 ? periods[currentIndex - 1] : null;
};

const recordPosition = (record: AgentRecord) => record.position || record.identity.position || '';
const recordRegion = (record: AgentRecord) => record.region || record.identity.region || 'Other';
const recordId = (record: AgentRecord) => record.identity.employee_id || record.identity.name;
const average = (values: number[]) => {
  const validValues = values.filter(Number.isFinite);
  return validValues.length
    ? validValues.reduce((total, value) => total + value, 0) / validValues.length
    : null;
};

type MarketingKpiValue = NonNullable<AgentRecord['kpi_values']>[number];

interface AggregatedKpiMetric {
  actual: number | null;
  target: number | null;
}

const sum = (values: number[]) => {
  const validValues = values.filter(Number.isFinite);
  return validValues.length ? validValues.reduce((total, value) => total + value, 0) : null;
};

const finiteValue = (value: unknown): number | null => {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const aggregateKpiMetric = (
  values: MarketingKpiValue[],
  definition: MarketingKpiConfig,
): AggregatedKpiMetric => {
  // Position KPI cards use the configured rollup across the selected employee-period rows.
  // The separate scoreAverage path below is intentionally the only performance-score average.
  const actualValues = values.map((value) => finiteValue(value.actual_value));
  const targetValues = values.map((value) => finiteValue(value.target_value));
  const actuals = actualValues.filter((value): value is number => value !== null);
  const targets = targetValues.filter((value): value is number => value !== null);
  if (!actuals.length && !targets.length) return { actual: null, target: null };

  const method = definition.aggregation?.method
    ?? (definition.unit.trim().toLowerCase() === 'count'
      || definition.unit.trim().toLowerCase() === 'number'
      || definition.unit.trim().toLowerCase() === 'visits'
      || /revenue|income|sales/i.test(definition.label)
      ? 'sum'
      : 'weighted_average');

  if (method === 'sum') {
    return { actual: sum(actuals), target: sum(targets) };
  }

  if (method === 'ratio') {
    const actualTotal = sum(actuals);
    const targetTotal = sum(targets);
    return {
      actual: actualTotal === null || targetTotal === null || targetTotal === 0
        ? null
        : actualTotal / targetTotal,
      target: targetTotal === null || targetTotal === 0 ? null : 1,
    };
  }

  if (method === 'weighted_average') {
    const weightedRows = values
      .map((value) => ({
        actual: finiteValue(value.actual_value),
        target: finiteValue(value.target_value),
      }))
      .filter((value): value is { actual: number; target: number | null } => value.actual !== null);
    const totalWeight = weightedRows.reduce(
      (total, value) => total + (value.target !== null && value.target > 0 ? value.target : 1),
      0,
    );
    const targetRows = weightedRows.filter((value): value is { actual: number; target: number } => value.target !== null);
    const targetWeight = targetRows.reduce(
      (total, value) => total + (value.target > 0 ? value.target : 1),
      0,
    );
    if (totalWeight > 0 && weightedRows.length > 0) {
      return {
        actual: weightedRows.reduce(
          (total, value) => total + value.actual * (value.target !== null && value.target > 0 ? value.target : 1),
          0,
        ) / totalWeight,
        target: targetWeight > 0
          ? targetRows.reduce(
            (total, value) => total + value.target * (value.target > 0 ? value.target : 1),
            0,
          ) / targetWeight
          : null,
      };
    }
  }

  return { actual: average(actuals), target: average(targets) };
};

const achievementRatio = (
  actual: number | null,
  target: number | null,
  direction: MarketingKpiConfig['direction'],
): number | null => {
  if (actual === null || target === null) return null;
  if (target <= 0) return 0;
  if (direction === 'lower_better') return actual <= 0 ? 1 : target / actual;
  return actual / target;
};

const achievementPercent = (
  metric: AggregatedKpiMetric,
  definition: MarketingKpiConfig,
): number | null => {
  const ratio = achievementRatio(metric.actual, metric.target, definition.direction);
  return ratio === null ? null : Math.min(Math.max(ratio, 0), 1) * 100;
};

const achievementGap = (
  metric: AggregatedKpiMetric,
  direction: MarketingKpiConfig['direction'],
): number | null => {
  if (metric.actual === null || metric.target === null) return null;
  return direction === 'lower_better'
    ? Math.max(metric.actual - metric.target, 0)
    : Math.max(metric.target - metric.actual, 0);
};

const periodSortValue = (year: number, month: string) => year * 12 + (MONTH_ORDER[month] || 0);

const filterScopeRecords = (
  records: AgentRecord[],
  filters: MarketingFilters,
  position = filters.position,
) => records.filter((record) => {
  if (filters.region !== 'All' && recordRegion(record) !== filters.region) return false;
  if (position && recordPosition(record) !== position) return false;
  return true;
});

const filterRecords = (
  records: AgentRecord[],
  filters: MarketingFilters,
  options: { includePosition?: boolean } = {},
) => records.filter((record) => {
  if (record.year !== filters.year || record.identity.month !== filters.month) return false;
  if (filters.region !== 'All' && recordRegion(record) !== filters.region) return false;
  if (options.includePosition !== false && filters.position && recordPosition(record) !== filters.position) return false;
  return true;
});

const filterYearRecords = (
  records: AgentRecord[],
  filters: MarketingFilters,
  options: { includePosition?: boolean } = {},
) => records.filter((record) => {
  if (record.year !== filters.year) return false;
  if (filters.region !== 'All' && recordRegion(record) !== filters.region) return false;
  if (options.includePosition !== false && filters.position && recordPosition(record) !== filters.position) return false;
  return true;
});

const uniqueEmployeeCount = (records: AgentRecord[]) => new Set(records.map(recordId).filter(Boolean)).size;

const gradeDistribution = (
  records: AgentRecord[],
  thresholds: MarketingTeamConfig['grade_thresholds'],
): Record<GradeClass, number> => {
  const result: Record<GradeClass, number> = { A: 0, B: 0, C: 0, D: 0, E: 0 };
  records.forEach((record) => {
    result[getMarketingGrade(record, thresholds)] += 1;
  });
  return result;
};

const normalizeKpiLabel = (label: string | undefined) => (
  String(label ?? '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()
);

const matchKeys = (definition: MarketingKpiConfig | string) => (
  typeof definition === 'string' ? [definition] : [definition.key, ...(definition.aliases ?? [])]
);

const resolveKpiValue = (record: AgentRecord, definition: MarketingKpiConfig | string) => {
  const keys = new Set(matchKeys(definition));
  return record.kpi_values?.find((value) => keys.has(value.kpi_key));
};

const storedWeight = (records: AgentRecord[], definition: MarketingKpiConfig | string) => {
  const values = records.map(record => resolveKpiValue(record, definition));
  if (!values.some(Boolean) || values.some(value => value && finiteValue(value.weight_applied) === null)) return null;
  // A KPI absent from a member of the selected cohort contributes zero weight.
  const weights = values.map(value => value ? finiteValue(value.weight_applied) ?? 0 : 0);
  return {
    weight: weights.reduce((total, weight) => total + weight, 0) / weights.length,
    weightVaries: weights.some(weight => Math.abs(weight - weights[0]) > 1e-9),
  };
};

/**
 * Stored employee-period definitions override catalog defaults, including known KPIs
 * whose weights changed. The catalog still supplies ordering/aggregation and legacy fallbacks.
 */
export const definitionsWithStoredKpis = (
  definitions: MarketingKpiConfig[],
  records: AgentRecord[],
): MarketingKpiConfig[] => {
  const configured = new Map(definitions.map(definition => [definition.key, definition]));
  const configuredByLabel = new Map<string, MarketingKpiConfig>();
  definitions.forEach((definition) => {
    const label = normalizeKpiLabel(definition.label);
    if (label && !configuredByLabel.has(label)) configuredByLabel.set(label, definition);
  });
  const stored = new Map<string, MarketingKpiConfig>();
  let displayOrder = definitions.reduce((highest, definition) => Math.max(highest, definition.display_order), 0);
  records.forEach((record) => {
    (record.kpi_values || []).forEach((value) => {
      const base = configured.get(value.kpi_key) ?? configuredByLabel.get(normalizeKpiLabel(value.label));
      const key = base?.key ?? value.kpi_key;
      const existing = stored.get(key);
      if (existing) {
        if (value.kpi_key !== key && !(existing.aliases ?? []).includes(value.kpi_key)) {
          stored.set(key, { ...existing, aliases: [...(existing.aliases ?? []), value.kpi_key] });
        }
        return;
      }
      if (!base) displayOrder += 1;
      stored.set(key, {
        key,
        label: value.label || base?.label || key,
        perspective: value.perspective || base?.perspective || '',
        weight: value.weight_applied,
        direction: value.direction,
        unit: value.unit || base?.unit || '',
        color: value.color || base?.color || '#64748B',
        display_order: base?.display_order ?? displayOrder,
        aggregation: base?.aggregation ?? { method: 'weighted_average', weight_col: 'Target Value' },
        ...(value.kpi_key !== key ? { aliases: [value.kpi_key] } : {}),
      });
    });
  });
  for (const [key, definition] of stored) {
    const sourceWeight = storedWeight(records, definition);
    if (sourceWeight) stored.set(key, { ...definition, ...sourceWeight });
  }
  return [
    ...definitions.map(definition => stored.get(definition.key) ?? definition),
    ...[...stored.values()].filter(definition => !configured.has(definition.key)),
  ];
};

interface MarketingKpiAggregationContext {
  historicalRecords?: AgentRecord[];
  currentPeriod?: MarketingPeriod | null;
  previousPeriod?: MarketingPeriod | null;
}

interface MarketingBaselineCandidate {
  actual: number;
  period: MarketingPeriod;
}

const selectBestBaseline = (
  candidates: MarketingBaselineCandidate[],
  direction: MarketingKpiConfig['direction'],
) => candidates.reduce<MarketingBaselineCandidate | null>((best, candidate) => {
  if (!best) return candidate;
  const isBetter = direction === 'lower_better'
    ? candidate.actual < best.actual
    : candidate.actual > best.actual;
  return isBetter ? candidate : best;
}, null);

const buildBaselineCandidates = (
  records: AgentRecord[],
  definition: MarketingKpiConfig,
  currentPeriod: MarketingPeriod | null | undefined,
) => getMarketingPeriods(records)
  .filter((period) => !currentPeriod || period.sortValue <= currentPeriod.sortValue)
  .map((period) => {
    const values = records
      .filter((record) => record.year === period.year && record.identity.month === period.month)
      .map((record) => resolveKpiValue(record, definition))
      .filter((value): value is MarketingKpiValue => Boolean(value));
    const actual = aggregateKpiMetric(values, definition).actual;
    return actual === null ? null : { actual, period };
  })
  .filter((candidate): candidate is MarketingBaselineCandidate => candidate !== null);

export const aggregateMarketingKpis = (
  records: AgentRecord[],
  previousRecords: AgentRecord[],
  definitions: MarketingKpiConfig[],
  context: MarketingKpiAggregationContext = {},
): MarketingKpiAggregate[] => definitions
  .slice()
  .sort((left, right) => left.display_order - right.display_order)
  .map((definition) => {
    const values = records
      .map((record) => resolveKpiValue(record, definition))
      .filter((value): value is MarketingKpiValue => Boolean(value));
    const previousValues = previousRecords
      .map((record) => resolveKpiValue(record, definition))
      .filter((value): value is MarketingKpiValue => Boolean(value));
    const currentMetric = aggregateKpiMetric(values, definition);
    const previousMetric = aggregateKpiMetric(previousValues, definition);
    const averageActual = currentMetric.actual;
    const averageTarget = currentMetric.target;
    const previousActual = previousMetric.actual;
    const previousTarget = previousMetric.target;
    const averageAchievement = achievementPercent(currentMetric, definition);
    const previousAchievement = achievementPercent(previousMetric, definition);
    const currentRatio = achievementRatio(currentMetric.actual, currentMetric.target, definition.direction);
    const sourceWeight = storedWeight(records, definition);
    const weight = sourceWeight?.weight ?? (
      !values.length && records.some(record => record.kpi_values?.length) ? 0 : definition.weight
    );
    const contributions = values.map(value => finiteValue(value.contribution));
    const hasStoredContributions = values.length > 0 && contributions.every(value => value !== null);
    // Average canonical score points over the whole selected cohort, not a fresh
    // calculation from pooled actuals and an obsolete configured weight.
    const averageContribution = hasStoredContributions
      ? contributions.reduce<number>((total, contribution) => total + (contribution ?? 0), 0) / records.length * 100
      : contributions.some(value => value !== null) || currentRatio === null
        ? null
        : Math.min(Math.max(currentRatio, 0), 1) * weight * 100;
    const employeeValues = new Map<string, MarketingKpiValue[]>();
    records.forEach((record) => {
      const value = resolveKpiValue(record, definition);
      const employeeId = recordId(record);
      if (!value || !employeeId) return;
      const employeeKpiValues = employeeValues.get(employeeId) || [];
      employeeKpiValues.push(value);
      employeeValues.set(employeeId, employeeKpiValues);
    });
    const affectedEmployees = [...employeeValues.values()].filter((employeeKpiValues) => {
      const metric = aggregateKpiMetric(employeeKpiValues, definition);
      const ratio = achievementRatio(metric.actual, metric.target, definition.direction);
      return ratio !== null && ratio < 1;
    });
    const currentPeriod = context.currentPeriod ?? getMarketingPeriods(records).at(-1) ?? null;
    const previousPeriod = context.previousPeriod ?? getMarketingPeriods(previousRecords).at(-1) ?? null;
    const baselineCandidates = buildBaselineCandidates(
      context.historicalRecords ?? records,
      definition,
      currentPeriod,
    );
    const baseline = selectBestBaseline(baselineCandidates, definition.direction);
    const previousBaseline = selectBestBaseline(
      baselineCandidates.filter((candidate) => !currentPeriod || candidate.period.key !== currentPeriod.key),
      definition.direction,
    );
    const isNewBaseline = averageActual !== null && previousBaseline !== null
      && (definition.direction === 'lower_better'
        ? averageActual < previousBaseline.actual
        : averageActual > previousBaseline.actual);
    return {
      ...definition,
      weight,
      weightVaries: sourceWeight?.weightVaries ?? false,
      currentPeriodLabel: currentPeriod?.label ?? null,
      previousPeriodLabel: previousPeriod?.label ?? null,
      averageActual,
      averageTarget,
      previousActual,
      previousTarget,
      averageAchievement,
      averageContribution,
      previousAchievement,
      achievementDelta: averageAchievement !== null && previousAchievement !== null && previousAchievement !== 0
        ? ((averageAchievement - previousAchievement) / previousAchievement) * 100
        : null,
      affectedEmployees: affectedEmployees.length,
      averageGap: achievementGap(currentMetric, definition.direction),
      baselineActual: baseline?.actual ?? null,
      baselinePeriodLabel: baseline?.period.label ?? null,
      previousBaselineActual: previousBaseline?.actual ?? null,
      previousBaselinePeriodLabel: previousBaseline?.period.label ?? null,
      isNewBaseline,
    };
  });

const weakestKpi = (aggregates: MarketingKpiAggregate[]) => (
  aggregates
    .filter((item) => item.averageAchievement !== null)
    .sort((left, right) => (left.averageAchievement ?? 0) - (right.averageAchievement ?? 0))[0] || null
);

const scoreAverage = (records: AgentRecord[]) => (
  average(records.map((record) => normalizeMarketingScore(record.evaluation.score))) ?? 0
);

interface MarketingEmployeeAggregate {
  records: AgentRecord[];
  record: AgentRecord;
  score: number;
}

const aggregateEmployeeRecords = (records: AgentRecord[]): MarketingEmployeeAggregate[] => {
  const grouped = new Map<string, AgentRecord[]>();
  records.forEach((record) => {
    const id = recordId(record);
    if (!id) return;
    const employeeRecords = grouped.get(id) || [];
    employeeRecords.push(record);
    grouped.set(id, employeeRecords);
  });

  return [...grouped.values()].map((employeeRecords) => {
    const sortedRecords = employeeRecords.slice().sort((left, right) => (
      periodSortValue(Number(left.year), left.identity.month)
      - periodSortValue(Number(right.year), right.identity.month)
    ));
    return {
      records: sortedRecords,
      record: sortedRecords[sortedRecords.length - 1],
      score: scoreAverage(sortedRecords),
    };
  });
};

const recordWithScore = (record: AgentRecord, score: number): AgentRecord => ({
  ...record,
  status: undefined,
  evaluation: { ...record.evaluation, score, grade: '' },
});

const gradeDistributionForEmployees = (
  employees: MarketingEmployeeAggregate[],
  thresholds: MarketingTeamConfig['grade_thresholds'],
): Record<GradeClass, number> => {
  const result: Record<GradeClass, number> = { A: 0, B: 0, C: 0, D: 0, E: 0 };
  employees.forEach((employee) => {
    result[getMarketingGrade(recordWithScore(employee.record, employee.score), thresholds)] += 1;
  });
  return result;
};

const percentageDelta = (
  current: number,
  previousRecords: AgentRecord[],
  previousValue: number,
): number | null => (
  previousRecords.length && previousValue !== 0
    ? ((current - previousValue) / previousValue) * 100
    : null
);

export const buildMarketingAnalytics = (
  records: AgentRecord[],
  config: MarketingTeamConfig,
  filters: MarketingFilters,
): MarketingAnalytics => {
  const isAllMonths = filters.month === 'All';
  const scopedRecords = filterScopeRecords(records, filters);
  const periods = getMarketingPeriods(scopedRecords);
  const yearPeriods = periods.filter((period) => period.year === filters.year);
  const currentPeriod = isAllMonths
    ? yearPeriods[yearPeriods.length - 1] ?? null
    : periods.find((period) => period.year === filters.year && period.month === filters.month) ?? null;
  const previousPeriod = isAllMonths
    ? null
    : getPreviousMarketingPeriod(periods, filters.year, filters.month);
  const currentRecords = isAllMonths ? filterYearRecords(records, filters) : filterRecords(records, filters);
  const previousFilters = previousPeriod
    ? { ...filters, year: previousPeriod.year, month: previousPeriod.month }
    : filters;
  const previousRecords = previousPeriod
    ? filterRecords(records, previousFilters)
    : [];
  const selectedPeriodSortValue = currentPeriod?.sortValue ?? periodSortValue(filters.year, filters.month);
  const historicalScopeRecords = scopedRecords.filter((record) => (
    periodSortValue(Number(record.year), record.identity.month) <= selectedPeriodSortValue
  ));

  const positions = config.available_positions?.length
    ? config.available_positions
    : Object.keys(config.positions);

  const positionSummaries: MarketingPositionSummary[] = positions.map((position) => {
    const definition = config.positions[position];
    const currentPositionRecords = currentRecords.filter((record) => recordPosition(record) === position);
    const previousPositionRecords = previousRecords.filter((record) => recordPosition(record) === position);
    const hasUploadedData = records.some((record) => recordPosition(record) === position);
    const currentEmployees = aggregateEmployeeRecords(currentPositionRecords);
    const currentGrades = isAllMonths
      ? gradeDistributionForEmployees(currentEmployees, config.grade_thresholds)
      : gradeDistribution(currentPositionRecords, config.grade_thresholds);
    const currentScore = isAllMonths
      ? average(currentEmployees.map((employee) => employee.score)) ?? 0
      : scoreAverage(currentPositionRecords);
    const previousScore = scoreAverage(previousPositionRecords);
    const historicalPositionRecords = filterScopeRecords(
      historicalScopeRecords,
      filters,
      position,
    );
    const kpis = aggregateMarketingKpis(
      currentPositionRecords,
      previousPositionRecords,
      definitionsWithStoredKpis(definition?.kpis || [], currentPositionRecords),
      { historicalRecords: historicalPositionRecords, currentPeriod, previousPeriod },
    );
    return {
      position,
      employeeCount: isAllMonths ? currentEmployees.length : uniqueEmployeeCount(currentPositionRecords),
      kpiCount: definitionsWithStoredKpis(definition?.kpis || [], currentPositionRecords).length,
      averageScore: currentPositionRecords.length ? currentScore : null,
      classABPercentage: currentEmployees.length
        ? ((currentGrades.A + currentGrades.B) / currentEmployees.length) * 100
        : 0,
      classDECount: currentGrades.D + currentGrades.E,
      scoreDelta: currentPositionRecords.length && previousPositionRecords.length && previousScore !== 0
        ? ((currentScore - previousScore) / previousScore) * 100
        : null,
      weakestKpi: weakestKpi(kpis),
      dataStatus: currentPositionRecords.length
        ? 'Active'
        : hasUploadedData
          ? 'No Results for Filters'
          : 'No Uploaded Data',
    };
  });

  const selectedPosition = filters.position;
  const selectedConfig = selectedPosition ? config.positions[selectedPosition] : null;
  const kpiAggregates = selectedConfig
    ? aggregateMarketingKpis(
        currentRecords,
        previousRecords,
        definitionsWithStoredKpis(selectedConfig.kpis, currentRecords),
        { historicalRecords: historicalScopeRecords, currentPeriod, previousPeriod },
      )
    : [];

  const currentEmployees = isAllMonths
    ? aggregateEmployeeRecords(currentRecords)
    : currentRecords.map((record) => ({ records: [record], record, score: scoreAverage([record]) }));
  const previousByEmployee = new Map(previousRecords.map((record) => [recordId(record), record]));
  const employeeRows: MarketingEmployeeRow[] = currentEmployees
    .map((employee) => {
      const record = employee.record;
      const previous = previousByEmployee.get(recordId(record));
      const score = employee.score;
      const previousScore = previous ? normalizeMarketingScore(previous.evaluation.score) : null;
      const definitions = definitionsWithStoredKpis(config.positions[recordPosition(record)]?.kpis || [], [record]);
      const employeeHistory = historicalScopeRecords.filter(
        (historicalRecord) => recordId(historicalRecord) === recordId(record),
      );
      const employeeKpis = aggregateMarketingKpis(
        employee.records,
        previous ? [previous] : [],
        definitions,
        { historicalRecords: employeeHistory, currentPeriod, previousPeriod },
      );
      return {
        id: recordId(record),
        name: record.identity.name,
        region: recordRegion(record),
        score,
        grade: getMarketingGrade(
          isAllMonths ? recordWithScore(record, score) : record,
          config.grade_thresholds,
        ),
        status: getMarketingStatus(
          isAllMonths ? recordWithScore(record, score) : record,
          config.grade_thresholds,
        ),
        scoreDelta: isAllMonths || previousScore === null || previousScore === 0
          ? null
          : ((score - previousScore) / previousScore) * 100,
        weakestKpi: weakestKpi(employeeKpis),
        record,
      };
    })
    .sort((left, right) => right.score - left.score);

  const trend = periods.filter((period) => period.sortValue <= selectedPeriodSortValue).map((period) => {
    const trendRecords = filterRecords(
      records,
      { ...filters, year: period.year, month: period.month },
    );
    return {
      period: period.label,
      year: period.year,
      month: period.month,
      score: scoreAverage(trendRecords),
      employeeCount: uniqueEmployeeCount(trendRecords),
    };
  }).filter((point) => point.employeeCount > 0).slice(-6);

  const grades = isAllMonths
    ? gradeDistributionForEmployees(currentEmployees, config.grade_thresholds)
    : gradeDistribution(currentRecords, config.grade_thresholds);
  const previousGrades = gradeDistribution(previousRecords, config.grade_thresholds);
  const employeeCount = isAllMonths ? currentEmployees.length : uniqueEmployeeCount(currentRecords);
  const previousEmployeeCount = uniqueEmployeeCount(previousRecords);
  const positionsWithData = new Set(currentRecords.map(recordPosition).filter(Boolean)).size;
  const previousPositionsWithData = new Set(previousRecords.map(recordPosition).filter(Boolean)).size;
  const averageScore = isAllMonths
    ? average(currentEmployees.map((employee) => employee.score)) ?? 0
    : scoreAverage(currentRecords);
  const previousAverageScore = scoreAverage(previousRecords);
  const belowTargetCount = grades.D + grades.E;
  const previousBelowTargetCount = previousGrades.D + previousGrades.E;
  const gradeDenominator = isAllMonths ? employeeCount : currentRecords.length;
  const classABPercentage = gradeDenominator ? ((grades.A + grades.B) / gradeDenominator) * 100 : 0;
  const classDEPercentage = gradeDenominator ? (belowTargetCount / gradeDenominator) * 100 : 0;
  const previousClassABPercentage = previousRecords.length
    ? ((previousGrades.A + previousGrades.B) / previousRecords.length) * 100
    : 0;
  const previousClassDEPercentage = previousRecords.length
    ? (previousBelowTargetCount / previousRecords.length) * 100
    : 0;

  return {
    currentRecords,
    previousRecords,
    previousPeriod,
    employeeCount,
    positionsWithData,
    averageScore,
    belowTargetCount,
    classABPercentage,
    classDEPercentage,
    employeeDelta: percentageDelta(employeeCount, previousRecords, previousEmployeeCount),
    positionCountDelta: percentageDelta(positionsWithData, previousRecords, previousPositionsWithData),
    scoreDelta: percentageDelta(averageScore, previousRecords, previousAverageScore),
    belowTargetDelta: percentageDelta(belowTargetCount, previousRecords, previousBelowTargetCount),
    classABDelta: percentageDelta(classABPercentage, previousRecords, previousClassABPercentage),
    classDEDelta: percentageDelta(classDEPercentage, previousRecords, previousClassDEPercentage),
    gradeDistribution: grades,
    positionSummaries,
    kpiAggregates,
    employeeRows,
    trend,
  };
};

export const buildMarketingInsights = (
  analytics: MarketingAnalytics,
  thresholds: MarketingTeamConfig['grade_thresholds'],
  teamLabel = 'Marketing',
): MarketingInsight[] => {
  const activePositions = analytics.positionSummaries.filter(
    (position) => position.dataStatus === 'Active' && position.averageScore !== null,
  );
  const declining = activePositions
    .filter((position) => position.scoreDelta !== null && position.scoreDelta < 0)
    .sort((left, right) => (left.scoreDelta ?? 0) - (right.scoreDelta ?? 0));
  const requiringAttention = activePositions
    .filter((position) => position.classDECount > 0 || (position.averageScore ?? 0) < thresholds.C)
    .sort((left, right) => (
      right.classDECount - left.classDECount
      || (left.averageScore ?? 0) - (right.averageScore ?? 0)
    ));
  const leader = activePositions
    .slice()
    .sort((left, right) => (right.averageScore ?? 0) - (left.averageScore ?? 0))[0];
  const insights: MarketingInsight[] = [];

  if (declining[0]) {
    const position = declining[0];
    insights.push({
      id: 'largest-decline',
      tone: 'critical',
      title: `${position.position} has the largest performance decline.`,
      detail: `Average score changed by ${Math.abs(position.scoreDelta ?? 0).toFixed(1)}% MoM. Review ${position.weakestKpi?.label || 'the weakest KPI'} first.`,
      position: position.position,
    });
  }

  if (requiringAttention.length) {
    insights.push({
      id: 'attention-count',
      tone: 'warning',
      title: `${requiringAttention.length} position${requiringAttention.length === 1 ? '' : 's'} require attention.`,
      detail: `${analytics.belowTargetCount} employee${analytics.belowTargetCount === 1 ? '' : 's'} are currently below target across the selected view.`,
      position: requiringAttention[0].position,
    });
  }

  if (leader) {
    insights.push({
      id: 'leading-position',
      tone: 'positive',
      title: `${leader.position} leads with a ${leader.averageScore?.toFixed(1)}% average.`,
      detail: `Maintain momentum and share effective practices across the selected ${teamLabel} scope.`,
      position: leader.position,
    });
  }

  if (!insights.length) {
    insights.push({
      id: 'no-results',
      tone: 'neutral',
      title: analytics.currentRecords.length
        ? `${teamLabel} performance is stable for the selected period.`
        : `No ${teamLabel} results match the selected filters.`,
      detail: analytics.currentRecords.length
        ? 'No material decline or below-target position is currently detected.'
        : 'Adjust Month, Region, or Position to review another performance scope.',
    });
  }

  return insights;
};
