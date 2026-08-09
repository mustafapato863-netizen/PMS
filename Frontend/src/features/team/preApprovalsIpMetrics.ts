import type { AgentRecord, RawData } from '../../types';
import { calculateWeightedKpiBreakdown } from '../../utils/kpiScore';

const DEFAULT_WEIGHTS = {
  Rejection: 0.50,
  InitialError: 0.20,
  Submission: 0.30,
};

const readRawNumber = (rawData: RawData | undefined, keys: string[]): number | undefined => {
  for (const key of keys) {
    const rawValue = rawData?.[key];
    if (rawValue === undefined || rawValue === null || rawValue === '') continue;
    const value = Number(rawValue);
    if (Number.isFinite(value)) return value;
  }
  return undefined;
};

const averageActualRate = (
  agents: AgentRecord[],
  selector: (agent: AgentRecord) => number | undefined,
) => {
  const values = agents.map(selector).filter((value): value is number => Number.isFinite(value));
  return values.length > 0 ? (values.reduce((sum, value) => sum + value, 0) / values.length) * 100 : 0;
};

const pooledRate = (
  agents: AgentRecord[],
  numeratorKeys: string[],
  denominatorKeys: string[],
  fallback: (agent: AgentRecord) => number | undefined,
) => {
  let numerator = 0;
  let denominator = 0;
  let hasRawCounters = false;

  agents.forEach((agent) => {
    const rawNumerator = readRawNumber(agent.raw_data, numeratorKeys);
    const rawDenominator = readRawNumber(agent.raw_data, denominatorKeys);
    if (rawNumerator !== undefined || rawDenominator !== undefined) hasRawCounters = true;
    numerator += rawNumerator ?? 0;
    denominator += rawDenominator ?? 0;
  });

  if (!hasRawCounters) return averageActualRate(agents, fallback);
  return denominator > 0 ? (numerator / denominator) * 100 : 0;
};

const summarizeScorePart = (agents: AgentRecord[], label: string) => {
  if (agents.length === 0) return { weight: 0, contribution: 0 };
  const totals = agents.reduce((sum, agent) => {
    const item = calculateWeightedKpiBreakdown(agent, DEFAULT_WEIGHTS)
      .find((kpi) => kpi.label === label);
    const weight = Math.max(Number(item?.weight ?? 0), 0);
    const contribution = Math.min(Math.max(Number(item?.contribution ?? 0), 0), weight * 100);
    return {
      weight: sum.weight + weight,
      contribution: sum.contribution + contribution,
    };
  }, { weight: 0, contribution: 0 });

  return {
    weight: totals.weight / agents.length,
    contribution: totals.contribution / agents.length,
  };
};

export function aggregatePreApprovalsIpMetrics(agents: AgentRecord[]) {
  const rejection = summarizeScorePart(agents, 'Rejection Rate');
  const error = summarizeScorePart(agents, 'Initial Error Rate');
  const submission = summarizeScorePart(agents, 'Submission Rate');

  return {
    rejectionRate: pooledRate(
      agents,
      ['RejectedRequests'],
      ['AssignedRequest'],
      (agent) => agent.actual.rejection_rate,
    ),
    errorRate: pooledRate(
      agents,
      ['ErrosClaims', 'ErrorsClaims'],
      ['SubmittedClaims'],
      (agent) => agent.actual.initial_error_rate,
    ),
    submissionRate: pooledRate(
      agents,
      ['ApprovalWithin48HR', 'ApprovalWithin48hrs'],
      ['ApprovedRequests'],
      (agent) => agent.actual.submission_rate,
    ),
    rejectionWeight: rejection.weight,
    rejectionContribution: rejection.contribution,
    errorWeight: error.weight,
    errorContribution: error.contribution,
    submissionWeight: submission.weight,
    submissionContribution: submission.contribution,
  };
}
