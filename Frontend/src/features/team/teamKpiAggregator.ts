import type { KPI, TeamConfig } from '../../schemas/teamConfig.schema';
import type { AgentRecord, KPIConfig, LocationKey } from '../../types';
import { getKPIsForAgent } from '../../types';
import { getWeightForLabel } from '../../utils/kpiScore';

export interface AggregatedTeamKpi {
  key?: string;
  label: string;
  /** Absent when pinned cohorts do not share one unit. */
  unit?: KPIConfig['unit'];
  isLowerBetter?: boolean;
  color?: string;
  actual: number;
  target: number;
  weight: number | null;
  /** Score points on the team score. 0.7 means 0.7%, including values at or below 1. */
  contribution: number | null;
  scoreFormula: KPI['score_formula'];
  capAchievement: boolean;
  /** Stored applied basis. File weights must not replace a uniform pin. */
  evaluationPinned?: boolean;
  /** Pinned target, weight, direction, unit, or KPI identity does not agree, so they are not averaged. */
  basisVaries?: boolean;
}

interface Bucket extends Omit<AggregatedTeamKpi, 'actual' | 'target' | 'weight' | 'contribution'> {
  method: 'average' | 'sum' | 'ratio' | 'weighted_average';
  actualSum: number;
  targetSum: number;
  count: number;
  numerator: number;
  denominator: number;
  hasRatioCounters: boolean;
  weightedActual: number;
  aggregationWeight: number;
  scoreWeight: number;
  scoreWeightCount: number;
  contributionSum: number;
  contributionCount: number;
  scoreTarget?: number;
  pinnedCount: number;
  legacyCount: number;
  pinnedAgrees: boolean;
  pinnedTarget?: number;
  pinnedWeight?: number | null;
  pinnedLowerBetter?: boolean;
  pinnedUnit?: string;
  pinnedKey?: string;
  pinnedUnitAgrees: boolean;
  pinnedKeyAgrees: boolean;
}

const nearlyEqual = (left: number | null | undefined, right: number | null | undefined): boolean => {
  if (left == null || right == null) return left == null && right == null;
  return Math.abs(left - right) <= 1e-9;
};

const normalize = (value: string | undefined) => (value || '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '');

export interface TeamKpiAggregationOptions {
  location?: LocationKey;
  /** Prefer the active config when legacy persisted KPI rows contain stale weights. */
  preferConfiguredWeights?: boolean;
}

const geoSourceValue = (
  agent: AgentRecord,
  field: 'bookings' | 'attended',
  location: LocationKey,
) => {
  const values = agent.geo?.[field];
  if (!values) return 0;
  if (location !== 'all') return Number(values[location]) || 0;
  return Object.values(values).reduce((sum, value) => sum + (Number(value) || 0), 0);
};

const sourceValue = (
  agent: AgentRecord,
  source: string | undefined,
  location: LocationKey,
): number | undefined => {
  if (!source) return undefined;
  if (source === '$calls.total_handled') return Number(agent.calls?.total_handled) || 0;
  if (source === '$calls.abandoned') return Number(agent.calls?.abandoned) || 0;
  if (source === '$geo.bookings') return geoSourceValue(agent, 'bookings', location);
  if (source === '$geo.attended') return geoSourceValue(agent, 'attended', location);
  let rawValue = agent.raw_data?.[source];
  if (rawValue === undefined) {
    const aliases: Record<string, string[]> = {
      errosclaims: ['ErrorsClaims', 'ErrorClaims'],
      errorsclaims: ['ErrosClaims', 'ErrorClaims'],
      errorclaims: ['ErrosClaims', 'ErrorsClaims'],
    };
    const alternateKeys = aliases[normalize(source)] ?? [];
    rawValue = alternateKeys
      .map((key) => agent.raw_data?.[key])
      .find((value) => value !== undefined);
  }
  if (rawValue === undefined && source === 'A.DispensedItems') {
    rawValue = agent.raw_data?.['Dispensed Items'] ?? agent.raw_data?.['A.TotalDispensedPrescriptions'] ?? agent.raw_data?.['Dispensed Prescriptions'];
  }
  if (rawValue === undefined && source === 'A.TotalPrescribedItems') {
    rawValue = agent.raw_data?.['Total Prescribed Items'] ?? agent.raw_data?.['Total Prescriped Items'] ?? agent.raw_data?.['Prescribed Items'];
  }
  if (rawValue === undefined || rawValue === null || rawValue === '') return undefined;
  const rawText = String(rawValue).replace(/,/g, '').trim();
  const parsed = Number(rawText.replace(/%$/, ''));
  if (!Number.isFinite(parsed)) return undefined;
  const value = /%$/.test(rawText) || /%/.test(source) ? (parsed > 1 ? parsed / 100 : parsed) : parsed;
  return Number.isFinite(value) ? value : undefined;
};

const employeeDefinitions = (config: TeamConfig | undefined, agent: AgentRecord): KPI[] => {
  if (!config) return [];
  if (config.kpis.length > 0) return config.kpis;
  const positions = config.performance_levels?.Employee?.positions;
  if (!positions) return [];
  const position = agent.position || agent.identity.position;
  if (position) {
    const matched = Object.entries(positions).find(([name]) => normalize(name) === normalize(position));
    if (matched) return matched[1].kpis;
  }
  return Object.values(positions).flatMap((definition) => definition.kpis);
};

const findDefinition = (definitions: KPI[], kpi: KPIConfig) => {
  const label = normalize(kpi.label);
  const key = normalize(kpi.key);
  const exact = definitions.find((definition) =>
    normalize(definition.label) === label
    || normalize(definition.key) === label
    || (!!key && normalize(definition.key) === key),
  );
  if (exact) return exact;

  // Inbound and Outbound store their swappable fifth KPI under the canonical
  // config key "Other", while uploaded rows expose the measured KPI name.
  if (['utz', 'utilization', 'abandonrate', 'reachability'].some((alias) => label.includes(alias))) {
    return definitions.find((definition) => normalize(definition.key) === 'other');
  }
  return undefined;
};

const isUtilizationKpi = (kpi: KPIConfig) => {
  const label = normalize(kpi.label);
  return label.includes('utz') || label.includes('utilization');
};

export function aggregateConfiguredTeamKpis(
  agents: AgentRecord[],
  config: TeamConfig | undefined,
  options: TeamKpiAggregationOptions = {},
): Map<string, AggregatedTeamKpi> {
  const buckets = new Map<string, Bucket>();
  const location = options.location ?? 'all';

  agents.forEach((agent) => {
    const definitions = employeeDefinitions(config, agent);
    getKPIsForAgent(agent).forEach((kpi) => {
      const key = normalize(kpi.label);
      const pinned = kpi.evaluationPinned === true;
      const definition = findDefinition(definitions, kpi);
      if (definitions.length > 0 && !definition && !pinned) return;
      const aggregation = definition && normalize(definition.key) === 'other' && isUtilizationKpi(kpi)
        ? { method: 'average' as const }
        : definition?.aggregation ?? { method: 'average' as const };
      const bucket = buckets.get(key) ?? {
        key: definition?.key ?? kpi.key,
        label: kpi.label,
        unit: kpi.unit,
        isLowerBetter: kpi.isLowerBetter,
        color: kpi.color,
        method: aggregation.method,
        actualSum: 0,
        targetSum: 0,
        count: 0,
        numerator: 0,
        denominator: 0,
        hasRatioCounters: false,
        weightedActual: 0,
        aggregationWeight: 0,
        scoreWeight: 0,
        scoreWeightCount: 0,
        contributionSum: 0,
        contributionCount: 0,
        scoreFormula: definition?.score_formula ?? 'target_ratio',
        capAchievement: true,
        scoreTarget: definition?.score_target,
        pinnedCount: 0,
        legacyCount: 0,
        pinnedAgrees: true,
        pinnedUnitAgrees: true,
        pinnedKeyAgrees: true,
      };

      // Ratio KPIs should not fall back to a stale persisted actual when the
      // source row still exposes its canonical percentage/target columns.
      // Counters remain the preferred path below; this only covers rows where
      // one of the ratio counters is missing. An applied pin keeps its own
      // target and weight; the workbook column is the legacy target only.
      const configuredActual = definition?.actual_col
        ? sourceValue(agent, definition.actual_col, location)
        : undefined;
      const configuredTarget = definition?.target_col
        ? sourceValue(agent, definition.target_col, location)
        : undefined;
      if (pinned) {
        bucket.pinnedCount += 1;
        const pinnedWeight = kpi.weight ?? null;
        const samePinnedBasis = nearlyEqual(bucket.pinnedTarget, kpi.target)
          && nearlyEqual(bucket.pinnedWeight, pinnedWeight)
          && Boolean(bucket.pinnedLowerBetter) === Boolean(kpi.isLowerBetter)
          && (bucket.pinnedUnit ?? '') === (kpi.unit ?? '')
          && normalize(bucket.pinnedKey) === normalize(kpi.key);
        if (bucket.pinnedCount === 1) {
          bucket.pinnedTarget = kpi.target;
          bucket.pinnedWeight = pinnedWeight;
          bucket.pinnedLowerBetter = kpi.isLowerBetter;
          bucket.pinnedUnit = kpi.unit;
          bucket.pinnedKey = kpi.key;
        } else if (!samePinnedBasis) {
          if ((bucket.pinnedUnit ?? '') !== (kpi.unit ?? '')) bucket.pinnedUnitAgrees = false;
          if (normalize(bucket.pinnedKey) !== normalize(kpi.key)) bucket.pinnedKeyAgrees = false;
          bucket.pinnedAgrees = false;
        }
        bucket.actualSum += Number.isFinite(kpi.actual) ? kpi.actual : 0;
        bucket.targetSum += Number.isFinite(kpi.target) ? kpi.target : 0;
      } else {
        bucket.legacyCount += 1;
        bucket.actualSum += aggregation.method === 'ratio' && configuredActual !== undefined
          ? configuredActual
          : kpi.actual;
        bucket.targetSum += aggregation.method === 'ratio' && configuredTarget !== undefined
          ? configuredTarget
          : kpi.target;
      }
      bucket.count += 1;
      const effectiveWeight = pinned
        ? kpi.weight
        : options.preferConfiguredWeights
          ? (definition?.weight ?? kpi.weight)
          : (kpi.weight ?? definition?.weight);
      if (effectiveWeight !== undefined) {
        bucket.scoreWeight += effectiveWeight;
        bucket.scoreWeightCount += 1;
      }
      if (kpi.contribution !== undefined) {
        bucket.contributionSum += kpi.contribution;
        bucket.contributionCount += 1;
      }

      if (aggregation.method === 'ratio') {
        const numerator = sourceValue(agent, aggregation.numerator_col, location);
        const denominator = sourceValue(agent, aggregation.denominator_col, location);
        if (numerator !== undefined && denominator !== undefined) {
          bucket.hasRatioCounters = true;
          bucket.numerator += numerator;
          bucket.denominator += denominator;
        }
      } else if (aggregation.method === 'weighted_average') {
        const weight = sourceValue(agent, aggregation.weight_col, location) ?? 0;
        bucket.weightedActual += kpi.actual * weight;
        bucket.aggregationWeight += weight;
      }
      buckets.set(key, bucket);
    });
  });

  return new Map([...buckets.entries()].map(([key, bucket]) => {
    const fallbackAverage = bucket.count > 0 ? bucket.actualSum / bucket.count : 0;
    const pooledActual = bucket.method === 'sum'
      ? bucket.actualSum
      : bucket.method === 'ratio' && bucket.hasRatioCounters
        ? (bucket.denominator > 0 ? bucket.numerator / bucket.denominator : 0)
        : bucket.method === 'weighted_average' && bucket.aggregationWeight > 0
          ? bucket.weightedActual / bucket.aggregationWeight
          : fallbackAverage;
    // A shared label with two pin units or two pin keys has no single actual.
    // Same-unit target or direction variation keeps the pooled quantity.
    const actual = !bucket.pinnedUnitAgrees || !bucket.pinnedKeyAgrees
      ? Number.NaN
      : pooledActual;
    const mixedBasis = bucket.pinnedCount > 0 && (bucket.legacyCount > 0 || !bucket.pinnedAgrees);
    const uniformPin = bucket.pinnedCount > 0 && bucket.legacyCount === 0 && bucket.pinnedAgrees;
    // A ratio aggregation already converts its raw numerator/denominator
    // into a fraction (e.g. 0.884 for 88.4%).  Its scoring threshold must
    // therefore be expressed in the same fraction scale (score_target = 1.0),
    // not as the average source volume (e.g. 1351 census).
    // Disagreeing applied targets stay NaN so callers cannot average them.
    const target = mixedBasis
      ? Number.NaN
      : uniformPin
        ? (bucket.pinnedTarget ?? Number.NaN)
        : (bucket.method === 'ratio' && bucket.scoreTarget !== undefined)
          ? bucket.scoreTarget
          : bucket.method === 'sum'
            ? bucket.targetSum
            : (bucket.count > 0 && bucket.targetSum > 0)
              ? bucket.targetSum / bucket.count
              : 0;
    const weight = mixedBasis
      ? null
      : uniformPin
        ? (bucket.pinnedWeight ?? null)
        : (bucket.scoreWeightCount > 0 ? bucket.scoreWeight / bucket.scoreWeightCount : null);
    return [key, {
      key: bucket.pinnedKeyAgrees
        ? (bucket.pinnedCount > 0 ? (bucket.pinnedKey ?? bucket.key) : bucket.key)
        : undefined,
      label: bucket.label,
      unit: bucket.pinnedUnitAgrees ? bucket.unit : undefined,
      isLowerBetter: mixedBasis ? undefined : bucket.isLowerBetter,
      color: bucket.color,
      actual,
      target,
      weight,
      contribution: mixedBasis || bucket.contributionCount === 0
        ? null
        : bucket.contributionSum / bucket.contributionCount,
      scoreFormula: bucket.scoreFormula,
      capAchievement: bucket.capAchievement,
      evaluationPinned: uniformPin || (mixedBasis && bucket.legacyCount === 0),
      basisVaries: mixedBasis,
    }];
  }));
}

export interface AggregatedTeamPerformance {
  score: number;
  groupCount: number;
  /** At least one displayed KPI mixes incompatible applied bases. The score is still the headcount-weighted sum of those bases. */
  basisVaries: boolean;
  kpis: Map<string, AggregatedTeamKpi>;
}

const definitionsForAgent = (config: TeamConfig, agent: AgentRecord): KPI[] => employeeDefinitions(config, agent);

const positionGroup = (config: TeamConfig, agent: AgentRecord): string => {
  if (config.kpis.length > 0) return '__root__';
  const positions = config.performance_levels?.Employee?.positions;
  if (!positions) return '__root__';
  const position = normalize(agent.position ?? agent.identity.position ?? undefined);
  const matched = Object.keys(positions).find((name) => normalize(name) === position);
  return matched ?? `__unmatched__:${position}`;
};

/**
 * Records that share a position but not an applied target, weight, direction,
 * or KPI set are separate pools. Legacy rows stay in one pool per position.
 */
const basisGroupKey = (config: TeamConfig, agent: AgentRecord): string => {
  const position = positionGroup(config, agent);
  const pinned = (agent.kpi_values ?? []).filter((kpi) => kpi.evaluation_pinned === true);
  if (pinned.length === 0) return `${position}::legacy`;
  const signature = pinned
    .map((kpi) => [
      normalize(kpi.kpi_key || kpi.label),
      kpi.direction ?? '',
      kpi.unit ?? '',
      Number.isFinite(Number(kpi.target_value)) ? Number(kpi.target_value).toFixed(8) : 'nan',
      Number.isFinite(Number(kpi.weight_applied)) ? Number(kpi.weight_applied).toFixed(8) : 'nan',
    ].join('='))
    .sort()
    .join('&');
  return `${position}::${signature}`;
};

const rawTotal = (agents: AgentRecord[], key: string): number => agents.reduce((sum, agent) => {
  const value = Number(agent.raw_data?.[key]);
  return sum + (Number.isFinite(value) ? value : 0);
}, 0);

const achievementFor = (kpi: AggregatedTeamKpi): number => {
  if (!Number.isFinite(kpi.actual) || !Number.isFinite(kpi.target)) return 0;

  const isPrescription = kpi.label.toLowerCase().includes('prescription');
  if (isPrescription) {
    const ach = kpi.actual > 1.5 ? kpi.actual : kpi.actual * 100;
    return Math.min(Math.max(ach, 0), 100);
  }

  const isTimeKpi = kpi.unit === 'min' || kpi.label.toLowerCase().includes('aht') || kpi.label.toLowerCase().includes('waitingtime');
  let rawTarget = (isTimeKpi && kpi.target > 0 && kpi.target < 1.0) ? kpi.target * 1440 : kpi.target;
  let rawActual = kpi.actual;

  if (!isTimeKpi) {
    if (rawActual > 0 && rawActual <= 1.0 && rawTarget > 1.0) {
      rawActual = rawActual * 100;
    } else if (rawTarget > 0 && rawTarget <= 1.0 && rawActual > 1.0) {
      rawTarget = rawTarget * 100;
    }
  }

  let achievement: number;
  if (kpi.scoreFormula === 'baseline_80') {
    const denominator = rawTarget - 0.8;
    achievement = denominator > 0 ? ((rawActual - 0.8) / denominator) * 100 : 0;
  } else if (kpi.isLowerBetter) {
    achievement = rawActual <= 0 ? 100 : (rawTarget / rawActual) * 100;
  } else {
    achievement = rawTarget > 0 ? (rawActual / rawTarget) * 100 : 0;
  }

  return Math.min(Math.max(achievement, 0), 100);
};

export function recordsUseAppliedPin(agents: Array<{ kpi_values?: Array<{ evaluation_pinned?: boolean }> }>): boolean {
  return agents.some((agent) => (agent.kpi_values ?? []).some((kpi) => kpi.evaluation_pinned === true));
}

/**
 * Single-team headline and trend. Legacy rows keep the 15-point employee
 * average guard used when weights have not loaded. An applied pin is a
 * complete basis, so a larger gap — including a real zero — stays the pooled
 * score. Cross-team summaries keep their own guard in reconcileTeamSummaryScore.
 */
export function displayedTeamScore(
  canonical: number | null,
  employeeAverage: number,
  appliedPin: boolean,
): number {
  if (appliedPin) {
    return canonical !== null && Number.isFinite(canonical) ? canonical : employeeAverage;
  }
  if (
    canonical !== null
    && Number.isFinite(canonical)
    && canonical > 0
    && Math.abs(canonical - employeeAverage) <= 15
  ) {
    return canonical;
  }
  return employeeAverage;
}

/**
 * Canonical team roll-up: pool KPI source totals first, then apply the KPI
 * achievement formulas and effective weights. Employee scores are never
 * averaged to produce the team overall.
 */
export function calculateAggregatedTeamPerformance(
  agents: AgentRecord[],
  config: TeamConfig | undefined,
  options: TeamKpiAggregationOptions = {},
): AggregatedTeamPerformance | null {
  if (!config || agents.length === 0) return null;

  const groups = new Map<string, AgentRecord[]>();
  agents.forEach((agent) => {
    const groupKey = basisGroupKey(config, agent);
    groups.set(groupKey, [...(groups.get(groupKey) ?? []), agent]);
  });

  let weightedGroupScore = 0;
  let recordsUsed = 0;
  let groupCount = 0;
  const mergedKpis = new Map<string, AggregatedTeamKpi & { representedRecords: number }>();

  groups.forEach((groupAgents) => {
    const definitions = definitionsForAgent(config, groupAgents[0]);
    if (definitions.length === 0) return;
    const configuredWeights = Object.fromEntries(definitions.map((definition) => [definition.key, definition.weight]));
    const aggregateRawData = config.team === 'Pre-Approvals IP Offshore'
      ? { SubmittedClaims: String(rawTotal(groupAgents, 'SubmittedClaims')) }
      : undefined;
    const month = groupAgents[0].identity.month;
    const kpis = aggregateConfiguredTeamKpis(groupAgents, config, options);

    const scoredRows = [...kpis.entries()].map(([key, kpi]) => {
      const definition = findDefinition(definitions, {
        key: kpi.key,
        label: kpi.label,
        actual: kpi.actual,
        target: kpi.target,
        unit: kpi.unit ?? 'number',
        color: kpi.color ?? '#000000',
        isLowerBetter: kpi.isLowerBetter,
      });
      const uniformPin = kpi.evaluationPinned === true && kpi.basisVaries !== true;
      const basisVaries = kpi.basisVaries === true;
      let weight: number | null;
      let contribution: number | null;
      if (basisVaries) {
        weight = null;
        contribution = null;
      } else if (uniformPin) {
        // Pooled actual and the applied target already sit on kpi. Stored
        // individual contributions are a different contract and must not be averaged.
        weight = kpi.weight ?? 0;
        contribution = achievementFor(kpi) * weight;
      } else {
        const specialWeight = getWeightForLabel(
          configuredWeights,
          kpi.label,
          config.team,
          aggregateRawData,
          month,
        );
        weight = specialWeight ?? (options.preferConfiguredWeights
          ? (definition?.weight ?? kpi.weight)
          : (kpi.weight ?? definition?.weight)) ?? 0;
        contribution = achievementFor(kpi) * weight;
      }
      return { key, kpi, weight, contribution, uniformPin, basisVaries };
    });
    const groupScore = scoredRows.reduce(
      (sum, row) => sum + (row.basisVaries ? 0 : (row.contribution ?? 0)),
      0,
    );

    scoredRows.forEach(({ key, kpi, weight, contribution, uniformPin, basisVaries }) => {
      const existing = mergedKpis.get(key);
      const representedRecords = (existing?.representedRecords ?? 0) + groupAgents.length;
      // Position-only legacy rows keep the previous headcount average.
      // Blank metadata is for an applied pin that does not agree.
      const appliedInvolved = Boolean(
        existing
        && (
          basisVaries
          || existing.basisVaries
          || existing.evaluationPinned
          || uniformPin
          || kpi.evaluationPinned
        ),
      );
      const unitDiffers = (existing?.unit ?? '') !== (kpi.unit ?? '');
      const keyDiffers = normalize(existing?.key) !== normalize(kpi.key);
      const identityDiffers = unitDiffers || keyDiffers;
      const incompatible = Boolean(
        appliedInvolved
        && (
          basisVaries
          || existing?.basisVaries
          || identityDiffers
          || existing?.isLowerBetter !== kpi.isLowerBetter
          || existing?.scoreFormula !== kpi.scoreFormula
          || !nearlyEqual(existing?.target, basisVaries ? Number.NaN : kpi.target)
          || !nearlyEqual(existing?.weight, weight)
        ),
      );
      if (existing && incompatible) {
        mergedKpis.set(key, {
          ...existing,
          key: keyDiffers ? undefined : existing.key,
          unit: unitDiffers ? undefined : existing.unit,
          actual: identityDiffers
            ? Number.NaN
            : ((existing.actual * existing.representedRecords) + (kpi.actual * groupAgents.length)) / representedRecords,
          target: Number.NaN,
          weight: null,
          contribution: null,
          isLowerBetter: undefined,
          evaluationPinned: true,
          basisVaries: true,
          representedRecords,
        });
        return;
      }
      if (existing) {
        mergedKpis.set(key, {
          ...existing,
          actual: ((existing.actual * existing.representedRecords) + (kpi.actual * groupAgents.length)) / representedRecords,
          target: ((existing.target * existing.representedRecords) + (kpi.target * groupAgents.length)) / representedRecords,
          weight: (((existing.weight ?? 0) * existing.representedRecords) + ((weight ?? 0) * groupAgents.length)) / representedRecords,
          contribution: (((existing.contribution ?? 0) * existing.representedRecords) + ((contribution ?? 0) * groupAgents.length)) / representedRecords,
          evaluationPinned: existing.evaluationPinned === true && uniformPin,
          basisVaries: false,
          representedRecords,
        });
        return;
      }
      mergedKpis.set(key, {
        ...kpi,
        weight,
        contribution,
        target: basisVaries ? Number.NaN : kpi.target,
        evaluationPinned: kpi.evaluationPinned,
        basisVaries,
        representedRecords: groupAgents.length,
      });
    });

    weightedGroupScore += Math.min(groupScore, 100) * groupAgents.length;
    recordsUsed += groupAgents.length;
    groupCount += 1;
  });

  if (recordsUsed === 0) return null;
  // Incompatible bases keep their own cohort scores. The team score is the
  // headcount-weighted combination. Varied KPI metadata stays blank instead
  // of a fabricated zero or an average of the disagreeing targets.
  const mixedAppliedBasis = [...mergedKpis.values()].some((kpi) => kpi.basisVaries);
  return {
    score: weightedGroupScore / recordsUsed,
    basisVaries: mixedAppliedBasis,
    groupCount,
    kpis: new Map([...mergedKpis.entries()].map(([key, kpi]) => {
      const teamShare = kpi.representedRecords / recordsUsed;
      return [key, {
        key: kpi.key,
        label: kpi.label,
        unit: kpi.unit,
        isLowerBetter: kpi.isLowerBetter,
        color: kpi.color,
        actual: kpi.actual,
        target: kpi.basisVaries ? Number.NaN : kpi.target,
        weight: kpi.weight === null || kpi.basisVaries ? null : kpi.weight * teamShare,
        contribution: kpi.contribution === null || kpi.basisVaries ? null : kpi.contribution * teamShare,
        scoreFormula: kpi.scoreFormula,
        capAchievement: kpi.capAchievement,
        evaluationPinned: kpi.evaluationPinned,
        basisVaries: kpi.basisVaries,
      }];
    })),
  };
}
