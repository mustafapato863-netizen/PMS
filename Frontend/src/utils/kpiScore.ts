import { getKPIsForAgent, isPreApprovalsIpElectiveTeam, type AgentRecord, type RawData } from '../types';

function normalizeWeight(weight: number | undefined): number {
  if (!Number.isFinite(weight ?? NaN)) return 0;
  return (weight ?? 0) > 1 ? (weight ?? 0) / 100 : (weight ?? 0);
}

const isPreApprovalsIpElective = (agent: AgentRecord): boolean =>
  isPreApprovalsIpElectiveTeam(agent.identity.team);

// Source of truth for the three-team scoring model:
// THREE_TEAMS_KPI_CALCULATION_GUIDE.md
export function getKpiWeightKeys(label: string): string[] {
  const normalized = label.toLowerCase();
  if (normalized.includes('quality errors rate')) return ['quality_errors_rate'];
  if (normalized.includes('rejection rate after re-submission')) return ['rejection_rate_after_resubmission'];
  if (normalized === 'tat') return ['tat', 'TAT'];
  if (normalized.includes('initial rejection rate')) return ['initial_rejection_rate', 'Rejection'];
  if (normalized.includes('submission within due date')) return ['submission_within_due_date', 'Submission'];
  if (normalized.includes('attendance')) return ['Attendance', 'Attend'];
  if (normalized.includes('booking')) return ['Booking'];
  if (normalized === 'aht' || normalized.includes('aht') || normalized.includes('handle time') || normalized.includes('avg. handle time')) return ['AHT', 'AHT (Handle Time)', 'TAT'];
  if (normalized.includes('turnaround time')) return ['TAT'];
  if (normalized.includes('quality errors')) return ['QualityErrors'];
  if (normalized.includes('quality score') || normalized === 'quality') return ['Quality'];
  if (normalized.includes('queries handled')) return ['Queries'];
  if (normalized.includes('attended cr') || normalized.includes('attendedcr')) return ['AttendedCR'];
  if (normalized.includes('waiting time')) return ['WaitingTime'];
  if (normalized.includes('average transaction value') || normalized.includes('atv')) return ['ATV'];
  if (normalized.includes('prescription contribution') || normalized.includes('prescription')) return ['Prescription'];
  if (normalized.includes('tender compliance')) return ['TenderCompliance'];
  if (normalized.includes('leakage')) return ['Leakage'];
  if (normalized.includes('reachability') || normalized.includes('abandon') || normalized.includes('utz') || normalized.includes('utilization')) return ['Other'];
  if (normalized.includes('rejection')) return ['Rejection'];
  if (normalized.includes('initial error')) return ['InitialError'];
  if (normalized.includes('submission')) return ['Submission', 'submission_within_due_date'];
  if (label === 'OP Census Ach') return ['OPCensus'];
  if (label === 'OP Revenue Ach') return ['OPRevenue'];
  if (label === 'IP Census Ach') return ['IPCensus'];
  if (label === 'IP Revenue Ach') return ['IPRevenue'];
  if (normalized.includes('activity score')) return ['Activity'];
  return [''];
}

export function getWeightForLabel(
  teamWeights: Record<string, number> | undefined,
  label: string,
  teamName?: string,
  rawData?: RawData,
  month?: string
): number | undefined {
  const normTeam = teamName?.trim().toLowerCase();
  const normMonth = month?.trim().toLowerCase();

  if (normTeam === 'pre-approvals ip offshore') {
    const claims = Number(rawData?.SubmittedClaims) || 0;
    const normalized = label.toLowerCase();
    if (claims === 0) {
      if (normalized.includes('rejection')) return 0.60;
      if (normalized.includes('error')) return 0.00;
      if (normalized.includes('submission')) return 0.40;
    } else {
      if (normalized.includes('rejection')) return 0.50;
      if (normalized.includes('error')) return 0.20;
      if (normalized.includes('submission')) return 0.30;
    }
  }

  if (normTeam === 'inbound') {
    const normalized = label.toLowerCase();
    if (normMonth === 'june') {
      if (normalized.includes('quality')) return 0.00;
      if (normalized.includes('utz') || normalized.includes('utilization') || normalized.includes('abandon')) return 0.15;
    }
  }

  if (normTeam === 'outbound') {
    const normalized = label.toLowerCase();
    if (normMonth === 'june') {
      if (normalized.includes('quality')) return 0.00;
      if (normalized.includes('reachability') || normalized.includes('other')) return 0.20;
    }
  }

  if (!teamWeights) return undefined;
  for (const key of getKpiWeightKeys(label)) {
    const value = teamWeights[key];
    if (value !== undefined) return value;
  }
  return undefined;
}

export function calculateWeightedKpiScore(
  agent: AgentRecord,
  teamWeights: Record<string, number> | undefined,
): number | null {
  const breakdown = calculateWeightedKpiBreakdown(agent, teamWeights);
  if (!breakdown.length) return null;

  return Math.min(breakdown.reduce((sum, kpi) => sum + kpi.contribution, 0), 100);
}

export interface WeightedKpiBreakdownItem {
  label: string;
  achievement: number;
  weight: number;
  contribution: number;
}

export function calculateWeightedKpiBreakdown(
  agent: AgentRecord,
  teamWeights: Record<string, number> | undefined,
): WeightedKpiBreakdownItem[] {
  const kpis = getKPIsForAgent(agent);
  if (!kpis.length) return [];

  const hasWeights = !!teamWeights && Object.keys(teamWeights).length > 0;
  if (!hasWeights) return [];

  const validKpis = kpis.filter((kpi) => Number.isFinite(kpi.target) && kpi.target > 0);
  if (!validKpis.length) return [];

  return validKpis.map((kpi) => {
    const achievement = kpi.achievement !== undefined
      ? kpi.achievement
      : kpi.isLowerBetter
        ? (kpi.actual <= 0 ? 100 : (kpi.target / kpi.actual) * 100)
        : (kpi.actual / kpi.target) * 100;
    const effective = Math.min(Math.max(achievement, 0), 100);
    const weight = normalizeWeight(getWeightForLabel(teamWeights, kpi.label, agent.identity.team, agent.raw_data, agent.identity.month));
    return {
      label: kpi.label,
      achievement: effective,
      weight,
      contribution: effective * weight,
    };
  });
}

export function normalizePerformanceScore(score: number): number {
  if (!Number.isFinite(score) || score <= 0) return 0;
  if (score <= 1) return score * 100;
  return Math.min(score, 100);
}

/** Canonical score used by cards, trends, tables, and month-over-month comparisons. */
export function resolveDisplayScore(
  agent: AgentRecord,
  teamWeights: Record<string, number> | undefined,
): number {
  // This team's historical SQL rows can retain an old evaluation score or
  // unrelated combined KPIs. Its canonical score is always the weighted sum
  // of the two workstream KPIs returned by getKPIsForAgent().
  if (isPreApprovalsIpElective(agent)) {
    const kpis = getKPIsForAgent(agent);
    const score = kpis.reduce((sum, kpi) => {
      const weight = normalizeWeight(kpi.weight ?? getWeightForLabel(
        teamWeights,
        kpi.label,
        agent.identity.team,
        agent.raw_data,
        agent.identity.month,
      ));
      const achievement = kpi.achievement !== undefined && Number.isFinite(kpi.achievement)
        ? kpi.achievement
        : kpi.isLowerBetter
          ? (kpi.actual <= 0 ? 100 : (kpi.target / kpi.actual) * 100)
          : (kpi.target > 0 ? (kpi.actual / kpi.target) * 100 : 0);
      return sum + Math.min(Math.max(0, achievement), 100) * weight;
    }, 0);
    return Math.min(Math.round(score * 100) / 100, 100);
  }

  if (agent.evaluation?.score != null && Number.isFinite(agent.evaluation.score)) {
    return normalizePerformanceScore(agent.evaluation.score);
  }
  const kpis = getKPIsForAgent(agent);
  if (kpis.length > 0) {
    const kpiContribSum = kpis.reduce((sum, kpi) => {
      const w = kpi.weight ?? getWeightForLabel(teamWeights, kpi.label, agent.identity.team, agent.raw_data, agent.identity.month) ?? 0;
      let ach = kpi.achievement;
      if (ach === undefined || !Number.isFinite(ach)) {
        if (Number.isFinite(kpi.target) && kpi.target > 0) {
          ach = kpi.isLowerBetter
            ? (kpi.actual <= 0 ? 100 : (kpi.target / kpi.actual) * 100)
            : (kpi.actual / kpi.target) * 100;
        } else {
          ach = 0;
        }
      }
      const cappedContrib = (Math.min(Math.max(ach, 0), 100) / 100) * w * 100;
      return sum + (kpi.contribution !== undefined
        ? Math.min(Math.max(kpi.contribution, 0), w * 100)
        : cappedContrib);
    }, 0);
    if (kpiContribSum > 0) {
      return Math.min(Math.round(kpiContribSum * 100) / 100, 100);
    }
  }
  return normalizePerformanceScore(agent.evaluation.score);
}
