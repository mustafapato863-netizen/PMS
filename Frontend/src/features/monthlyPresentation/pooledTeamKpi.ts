import { validateTeamConfig, type TeamConfig } from '../../schemas/teamConfig.schema';
import type { AgentRecord, LocationKey } from '../../types';
import { percentPointsFromRatio } from '../../utils/percentForm';
import type { ExecRecord } from '../executive/compose';
import { canonicalEgyptResubmissionTeam, mergedTeamName } from '../team/countryTeamIdentity';
import {
  achievementFor,
  calculateAggregatedTeamPerformance,
  type AggregatedTeamKpi,
} from '../team/teamKpiAggregator';
import {
  EGYPT_RESUBMISSION_TEAM_CONFIG,
  INBOUND_TEAM_CONFIG,
  OUTBOUND_TEAM_CONFIG,
  UAE_RESUBMISSION_TEAM_CONFIG,
} from './callCenterTeamConfigs';

const MERGED_TEAM_SOURCES: Record<string, string[]> = {
  'Pre-Approvals OP Final': ['Pre-Approvals OP Dubai', 'Pre-Approvals OP Final SHJAJM'],
  'Pre-Approvals IP Final': ['Pre-Approvals IP Final Dubai', 'Pre-Approvals IP Final SHJAJM'],
};

const round1 = (value: number): number => Math.round(value * 10) / 10;
const round2 = (value: number): number => Math.round(value * 100) / 100;

const norm = (value: string | undefined | null): string =>
  (value ?? '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '');

function kpiFamily(labelOrKey: string): string {
  const n = norm(labelOrKey);
  if (n.includes('attend')) return 'attendance';
  if (n.includes('booking')) return 'booking';
  if (n.includes('aht') || n.includes('handletime')) return 'aht';
  if (n.includes('quality')) return 'quality';
  if (n.includes('utz') || n.includes('utilization')) return 'utilization';
  if (n.includes('abandon')) return 'abandon';
  if (n.includes('reachability')) return 'reachability';
  return n;
}

export function resolveEffectiveLocation(agents: AgentRecord[]): LocationKey {
  const firstKey = agents[0]?.branch_key?.trim().toLowerCase();
  if (
    (firstKey === 'dubai' || firstKey === 'sharjah' || firstKey === 'ajman' || firstKey === 'clinics') &&
    agents.every((agent) => agent.branch_key?.trim().toLowerCase() === firstKey)
  ) {
    return firstKey;
  }
  return 'all';
}

function configMatchesName(config: TeamConfig, candidate: string): boolean {
  const normalizedTarget = norm(mergedTeamName(canonicalEgyptResubmissionTeam(candidate)));
  const rawTarget = norm(candidate);
  const names = [config.team, config.db_name, ...(config.aliases ?? [])].filter(
    (name): name is string => Boolean(name),
  );
  return names.some((name) => {
    const raw = norm(name);
    const merged = norm(mergedTeamName(canonicalEgyptResubmissionTeam(name)));
    return raw === rawTarget || merged === normalizedTarget;
  });
}

function mergeSourceConfigs(teamName: string, configs: TeamConfig[]): TeamConfig | undefined {
  if (!configs.length) return undefined;
  if (configs.length === 1) return configs[0];
  try {
    const base = configs[0];
    const positions = Object.fromEntries(
      configs.flatMap((config) => Object.entries(config.performance_levels?.Employee?.positions || {})),
    );
    return validateTeamConfig({
      ...base,
      team: teamName,
      db_name: teamName,
      kpis: [],
      performance_levels: {
        ...(base.performance_levels || {}),
        Employee: {
          ...(base.performance_levels?.Employee || {}),
          kpis: [],
          positions,
        },
      },
    });
  } catch {
    return configs[0];
  }
}

export function resolveTeamConfigForRecords(
  canonicalTeam: string,
  records: ExecRecord[],
  teamConfigs?: TeamConfig[],
): TeamConfig | undefined {
  const sourceTeams = [...new Set(records.map((record) => record.team.trim()).filter(Boolean))];
  const candidates = [
    ...(sourceTeams.length === 1 ? [sourceTeams[0]] : []),
    canonicalTeam,
    ...sourceTeams,
  ];

  if (teamConfigs && teamConfigs.length > 0) {
    const mergedKey = Object.keys(MERGED_TEAM_SOURCES).find(
      (key) => norm(key) === norm(canonicalTeam) || norm(key) === norm(mergedTeamName(canonicalTeam)),
    );
    if (mergedKey && sourceTeams.length > 1) {
      const sourceConfigs = MERGED_TEAM_SOURCES[mergedKey]
        .map((src) => teamConfigs.find((cfg) => configMatchesName(cfg, src)))
        .filter((cfg): cfg is TeamConfig => Boolean(cfg));
      const merged = mergeSourceConfigs(mergedKey, sourceConfigs);
      if (merged) return merged;
    }

    for (const candidate of candidates) {
      const exact = teamConfigs.find((cfg) => configMatchesName(cfg, candidate));
      if (exact) return exact;
    }
  }

  const normalizedCanonical = norm(canonicalTeam);
  if (normalizedCanonical === 'inbound') return INBOUND_TEAM_CONFIG;
  if (normalizedCanonical === 'outbound') return OUTBOUND_TEAM_CONFIG;
  if (sourceTeams.some((team) => norm(team) === 'resubmission')) return EGYPT_RESUBMISSION_TEAM_CONFIG;
  if (sourceTeams.some((team) => norm(team) === 'resubmission' || team.trim().toLowerCase() === 're-submission')) {
    return UAE_RESUBMISSION_TEAM_CONFIG;
  }
  return undefined;
}

export function buildPooledKpiMap(
  records: ExecRecord[],
  teamConfig: TeamConfig | undefined,
): Map<string, AggregatedTeamKpi> | null {
  if (!teamConfig || records.length === 0) return null;
  const agents = records
    .map((record) => record.rawAgent)
    .filter((agent): agent is AgentRecord => Boolean(agent));
  if (agents.length === 0 || agents.length !== records.length) return null;

  const isMergedTeam = new Set(records.map((r) => r.team.trim().toLowerCase())).size > 1;
  return (
    calculateAggregatedTeamPerformance(agents, teamConfig, {
      location: resolveEffectiveLocation(agents),
      preferConfiguredWeights: isMergedTeam,
    })?.kpis ?? null
  );
}

export function matchPooledKpi(
  pooledKpis: Map<string, AggregatedTeamKpi> | null,
  kpiKey: string,
  kpiLabel: string,
): AggregatedTeamKpi | null {
  if (!pooledKpis || pooledKpis.size === 0) return null;
  const keyNorm = norm(kpiKey);
  const labelNorm = norm(kpiLabel);
  const targetFamily = kpiFamily(kpiLabel || kpiKey);

  let familyMatch: AggregatedTeamKpi | null = null;
  for (const [mapKey, agg] of pooledKpis.entries()) {
    if (agg.basisVaries === true || !Number.isFinite(agg.actual)) continue;
    if ((keyNorm && norm(agg.key) === keyNorm) || (labelNorm && (norm(agg.label) === labelNorm || norm(mapKey) === labelNorm))) {
      return agg;
    }
    if (!familyMatch && targetFamily && (kpiFamily(agg.label) === targetFamily || kpiFamily(agg.key ?? '') === targetFamily)) {
      familyMatch = agg;
    }
  }
  return familyMatch;
}

export interface PooledKpiNumbers {
  actual: number;
  target: number | null;
  achievementPct: number;
  weightPct: number | null;
  contributionPct: number | null;
  metTarget: boolean | null;
}

export function pooledKpiDisplayNumbers(
  agg: AggregatedTeamKpi,
  fallbackUnit: string,
  fallbackActual: number | null = null,
  fallbackTarget: number | null = null,
): PooledKpiNumbers {
  const isPrescription = agg.label.toLowerCase().includes('prescription');
  const isPercent = agg.unit === '%' || fallbackUnit === '%';
  // Ratio-to-target volume KPIs (e.g., Sales OP/IP Revenue & Census where actual_col/target_col
  // are AED or counts and score_target is 1.0): preserve AED/count actual & target display
  // while still using the exact pooled sum(actual)/sum(target) achievement, weight, and contribution.
  const isRatioToTargetVolume =
    !isPercent &&
    !isPrescription &&
    Number.isFinite(agg.target) &&
    agg.target === 1 &&
    fallbackTarget !== null &&
    Number.isFinite(fallbackTarget) &&
    Math.abs(fallbackTarget) > 1.5;

  const actual = isRatioToTargetVolume && fallbackActual !== null && Number.isFinite(fallbackActual)
    ? round2(fallbackActual)
    : isPrescription
      ? round2(achievementFor(agg))
      : isPercent
        ? round2(percentPointsFromRatio(agg.actual))
        : round2(agg.actual);
  const target = isRatioToTargetVolume
    ? round2(fallbackTarget)
    : !Number.isFinite(agg.target)
      ? null
      : isPrescription
        ? 85
        : isPercent
          ? round2(percentPointsFromRatio(agg.target))
          : round2(agg.target);
  const achievementPct = round1(achievementFor(agg));
  const weightPct =
    agg.weight !== null && Number.isFinite(agg.weight)
      ? round1(agg.weight <= 1 ? agg.weight * 100 : agg.weight)
      : null;
  const contributionPct =
    agg.contribution !== null && Number.isFinite(agg.contribution)
      ? round1(Math.min(Math.max(agg.contribution, 0), weightPct ?? 100))
      : weightPct !== null
        ? round1((achievementPct / 100) * weightPct)
        : null;
  const metTarget = isRatioToTargetVolume
    ? achievementPct >= 99.95
    : target !== null
      ? agg.isLowerBetter
        ? actual <= target + 1e-6
        : actual >= target - 1e-6
      : null;

  return { actual, target, achievementPct, weightPct, contributionPct, metTarget };
}

/**
 * Computes pooled team/role achievement % directly from actual vs target
 * when aggregating multiple records without a TeamConfig counter definition.
 * Single-record scorecards (e.g., individual or leader scorecards with a
 * stored custom achievement ratio) keep their stored achievement %.
 */
export function computeRatioAchievementPct(
  actual: number | null,
  target: number | null,
  lowerBetter: boolean,
  fallbackPct: number,
  recordCount: number,
  isPenalty?: boolean,
): number {
  if (
    recordCount > 1 &&
    !isPenalty &&
    actual !== null &&
    target !== null &&
    Number.isFinite(actual) &&
    Number.isFinite(target) &&
    target > 0
  ) {
    const ratio = lowerBetter
      ? actual <= 0
        ? 1
        : target / actual
      : actual / target;
    return round1(Math.min(100, Math.max(0, ratio * 100)));
  }
  return fallbackPct;
}

export function normalizeWeightPct(weight: number | null | undefined): number | undefined {
  if (weight == null || !Number.isFinite(weight) || weight <= 0) return undefined;
  return round1(weight <= 1 ? weight * 100 : weight);
}
