import type { KPI, TeamConfig } from '../../schemas/teamConfig.schema';
import type { AgentRecord, KPIConfig, LocationKey } from '../../types';
import { getKPIsForAgent } from '../../types';
import { getWeightForLabel } from '../../utils/kpiScore';

export interface AggregatedTeamKpi {
  key?: string;
  label: string;
  unit: KPIConfig['unit'];
  isLowerBetter?: boolean;
  color?: string;
  actual: number;
  target: number;
  weight: number | null;
  contribution: number | null;
  scoreFormula: KPI['score_formula'];
  capAchievement: boolean;
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
}

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
  if (rawValue === undefined && source === 'A.DispensedItems') {
    rawValue = agent.raw_data?.['Dispensed Items'] ?? agent.raw_data?.['A.TotalDispensedPrescriptions'] ?? agent.raw_data?.['Dispensed Prescriptions'];
  }
  if (rawValue === undefined && source === 'A.TotalPrescribedItems') {
    rawValue = agent.raw_data?.['Total Prescribed Items'] ?? agent.raw_data?.['Total Prescriped Items'] ?? agent.raw_data?.['Prescribed Items'];
  }
  if (rawValue === undefined || rawValue === null || rawValue === '') return undefined;
  const value = Number(rawValue);
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
      const definition = findDefinition(definitions, kpi);
      if (definitions.length > 0 && !definition) return;
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
      };

      bucket.actualSum += kpi.actual;
      bucket.targetSum += kpi.target;
      bucket.count += 1;
      const effectiveWeight = options.preferConfiguredWeights
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
    const actual = bucket.method === 'sum'
      ? bucket.actualSum
      : bucket.method === 'ratio' && bucket.hasRatioCounters
        ? (bucket.denominator > 0 ? bucket.numerator / bucket.denominator : 0)
        : bucket.method === 'weighted_average' && bucket.aggregationWeight > 0
          ? bucket.weightedActual / bucket.aggregationWeight
          : fallbackAverage;
    // A ratio aggregation already converts its raw numerator/denominator
    // into a fraction (e.g. 0.884 for 88.4%).  Its scoring threshold must
    // therefore be expressed in the same fraction scale (score_target = 1.0),
    // not as the average source volume (e.g. 1351 census).
    const target = (bucket.method === 'ratio' && bucket.scoreTarget !== undefined)
      ? bucket.scoreTarget
      : bucket.method === 'sum'
      ? bucket.targetSum
      : (bucket.count > 0 && bucket.targetSum > 0)
      ? bucket.targetSum / bucket.count
      : 0;
    return [key, {
      label: bucket.label,
      unit: bucket.unit,
      isLowerBetter: bucket.isLowerBetter,
      color: bucket.color,
      actual,
      target,
      weight: bucket.scoreWeightCount > 0 ? bucket.scoreWeight / bucket.scoreWeightCount : null,
      contribution: bucket.contributionCount > 0 ? bucket.contributionSum / bucket.contributionCount : null,
      scoreFormula: bucket.scoreFormula,
      capAchievement: bucket.capAchievement,
    }];
  }));
}

export interface AggregatedTeamPerformance {
  score: number;
  groupCount: number;
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
    const groupKey = positionGroup(config, agent);
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

    const groupScore = [...kpis.entries()].reduce((sum, [key, kpi]) => {
      const definition = findDefinition(definitions, {
        key: kpi.key,
        label: kpi.label,
        actual: kpi.actual,
        target: kpi.target,
        unit: kpi.unit,
        color: kpi.color ?? '#000000',
        isLowerBetter: kpi.isLowerBetter,
      });
      const specialWeight = getWeightForLabel(
        configuredWeights,
        kpi.label,
        config.team,
        aggregateRawData,
        month,
      );
      const weight = specialWeight ?? (options.preferConfiguredWeights
        ? (definition?.weight ?? kpi.weight)
        : (kpi.weight ?? definition?.weight)) ?? 0;
      const contribution = achievementFor(kpi) * weight;
      const existing = mergedKpis.get(key);
      if (existing) {
        const representedRecords = existing.representedRecords + groupAgents.length;
        mergedKpis.set(key, {
          ...existing,
          actual: ((existing.actual * existing.representedRecords) + (kpi.actual * groupAgents.length)) / representedRecords,
          target: ((existing.target * existing.representedRecords) + (kpi.target * groupAgents.length)) / representedRecords,
          weight: (((existing.weight ?? 0) * existing.representedRecords) + (weight * groupAgents.length)) / representedRecords,
          contribution: (((existing.contribution ?? 0) * existing.representedRecords) + (contribution * groupAgents.length)) / representedRecords,
          representedRecords,
        });
      } else {
        mergedKpis.set(key, {
          ...kpi,
          weight,
          contribution,
          representedRecords: groupAgents.length,
        });
      }
      return sum + contribution;
    }, 0);

    weightedGroupScore += Math.min(groupScore, 100) * groupAgents.length;
    recordsUsed += groupAgents.length;
    groupCount += 1;
  });

  if (recordsUsed === 0) return null;
  return {
    score: weightedGroupScore / recordsUsed,
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
        target: kpi.target,
        weight: kpi.weight === null ? null : kpi.weight * teamShare,
        contribution: kpi.contribution === null ? null : kpi.contribution * teamShare,
        scoreFormula: kpi.scoreFormula,
        capAchievement: kpi.capAchievement,
      }];
    })),
  };
}
