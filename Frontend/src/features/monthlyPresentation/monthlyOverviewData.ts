import type { ExecutiveSummary } from '../executive/types';

export type GradeLetter = 'A' | 'B' | 'C' | 'D' | 'E';

export interface TrendPoint {
  month: string;
  key: string;
  score: number;
  target: number;
}

export interface GradeDistributionRow {
  grade: GradeLetter;
  label: string;
  thresholdLabel: string;
  count: number;
  percentage: number;
  change: number;
}

export interface ScoreDriverItem {
  id: string;
  kpiName: string;
  team: string;
  functionName: string;
  impactPct: number;
  betterDirection: 'higher' | 'lower';
  actualValue: string;
  movementLabel?: string;
}

export interface FunctionOverviewItem {
  functionName: string;
  slug: string;
  score: number;
  grade: GradeLetter;
  gap: number;
  change: number | null;
  teamsCount: number;
  headcount: number;
  teamsList: string;
  hasMajorIssue: boolean;
  highlightBadge?: string;
}

export interface TeamAtRiskItem {
  team: string;
  functionName: string;
  score: number;
  grade: GradeLetter;
  gap: number;
  flags: string[];
}

export interface MonthlyOverviewData {
  title: string;
  FlowName: string;
  regionCode: 'EGY' | 'UAE';
  regionName: string;
  monthLabel: string;
  previousMonthLabel: string;
  periodKey: string;
  pageIndicator: {
    current: number;
    total: number;
    label: string;
  };
  overall: {
    score: number;
    grade: GradeLetter;
    target: number;
    gap: number;
    change: number;
    previousScore: number;
    headline: string;
    employeesCount: number;
    teamsCount: number;
    functionsCount: number;
    evaluationNote: string;
  };
  trend: TrendPoint[];
  gradeDistribution: {
    totalEmployees: number;
    rows: GradeDistributionRow[];
    takeaway: string;
  };
  drivers: {
    negative: ScoreDriverItem[];
    positive: ScoreDriverItem[];
  };
  functions: FunctionOverviewItem[];
  teamsAtRisk: TeamAtRiskItem[];
}

export interface GradeColorStyle {
  badgeBg: string;
  badgeText: string;
  badgeBorder: string;
  barFill: string;
  scoreText: string;
  softBg: string;
}

export const GRADE_STYLES: Record<GradeLetter, GradeColorStyle> = {
  A: {
    badgeBg: 'bg-emerald-50',
    badgeText: 'text-emerald-700',
    badgeBorder: 'border-emerald-200',
    barFill: 'bg-emerald-500',
    scoreText: 'text-emerald-600',
    softBg: 'bg-emerald-50/60',
  },
  B: {
    badgeBg: 'bg-blue-50',
    badgeText: 'text-blue-700',
    badgeBorder: 'border-blue-200',
    barFill: 'bg-blue-500',
    scoreText: 'text-blue-600',
    softBg: 'bg-blue-50/60',
  },
  C: {
    badgeBg: 'bg-amber-50',
    badgeText: 'text-amber-700',
    badgeBorder: 'border-amber-200',
    barFill: 'bg-amber-500',
    scoreText: 'text-amber-600',
    softBg: 'bg-amber-50/60',
  },
  D: {
    badgeBg: 'bg-orange-50',
    badgeText: 'text-orange-700',
    badgeBorder: 'border-orange-200',
    barFill: 'bg-orange-500',
    scoreText: 'text-orange-600',
    softBg: 'bg-orange-50/60',
  },
  E: {
    badgeBg: 'bg-red-100',
    badgeText: 'text-red-800',
    badgeBorder: 'border-red-300',
    barFill: 'bg-red-700',
    scoreText: 'text-red-700',
    softBg: 'bg-red-50/70',
  },
};

export function gradeForScore(score: number): GradeLetter {
  if (score >= 95) return 'A';
  if (score >= 90) return 'B';
  if (score >= 80) return 'C';
  if (score >= 70) return 'D';
  return 'E';
}

/**
 * Canonical September 2026 Offshore Egypt Snapshot
 */
export const OFFSHORE_EGYPT_SEP_2026_DATA: MonthlyOverviewData = {
  title: 'Monthly Presentation',
  FlowName: 'Monthly Overview',
  regionCode: 'EGY',
  regionName: 'Offshore Egypt',
  monthLabel: 'September 2026',
  previousMonthLabel: 'August',
  periodKey: '2026-09',
  pageIndicator: {
    current: 1,
    total: 6,
    label: 'Page 1 of 6',
  },
  overall: {
    score: 86.6,
    grade: 'C',
    target: 100.0,
    gap: -13.4,
    change: 0.5,
    previousScore: 86.1,
    headline: '13.4% below target',
    employeesCount: 71,
    teamsCount: 10,
    functionsCount: 7,
    evaluationNote:
      'Evaluation settings are mixed in this comparison, so scores are not like-for-like. Scores can be affected by evaluation settings and cohort changes.',
  },
  trend: [
    { month: 'Apr', key: '2026-04', score: 75.8, target: 100 },
    { month: 'May', key: '2026-05', score: 77.4, target: 100 },
    { month: 'Jun', key: '2026-06', score: 76.5, target: 100 },
    { month: 'Jul', key: '2026-07', score: 86.4, target: 100 },
    { month: 'Aug', key: '2026-08', score: 86.1, target: 100 },
    { month: 'Sep', key: '2026-09', score: 86.6, target: 100 },
  ],
  gradeDistribution: {
    totalEmployees: 71,
    rows: [
      { grade: 'A', label: 'Excellent', thresholdLabel: '≥95%', count: 10, percentage: 14.1, change: -5 },
      { grade: 'B', label: 'Meet Expectations', thresholdLabel: '90–94%', count: 25, percentage: 35.2, change: 3 },
      { grade: 'C', label: 'Average', thresholdLabel: '80–89%', count: 22, percentage: 31.0, change: 2 },
      { grade: 'D', label: 'Below Average', thresholdLabel: '70–79%', count: 7, percentage: 9.9, change: -1 },
      { grade: 'E', label: 'Unsatisfactory', thresholdLabel: '<70%', count: 7, percentage: 9.9, change: 1 },
    ],
    takeaway:
      'Most of the population is in B/C. The overall score is not being carried by a tiny high-performing group — but the D/E tail is still pulling the average down.',
  },
  drivers: {
    negative: [
      {
        id: 'neg-1',
        kpiName: 'Initial Rejection %',
        team: 'Submission EGY',
        functionName: 'RCM',
        impactPct: -28.42,
        betterDirection: 'lower',
        actualValue: '3.8%',
      },
      {
        id: 'neg-2',
        kpiName: 'Quality Errors Rate',
        team: 'Coding EGY',
        functionName: 'RCM',
        impactPct: -27.88,
        betterDirection: 'lower',
        actualValue: '11.3%',
      },
      {
        id: 'neg-3',
        kpiName: 'TAT',
        team: 'Coding EGY',
        functionName: 'RCM',
        impactPct: -19.50,
        betterDirection: 'higher',
        actualValue: '54.9%',
      },
    ],
    positive: [
      {
        id: 'pos-1',
        kpiName: 'Quality sessions efficiency / success rate',
        team: 'Call Center',
        functionName: 'Call Center',
        impactPct: 15.28,
        betterDirection: 'higher',
        actualValue: '66.7%',
        movementLabel: '↑ +22.9%',
      },
      {
        id: 'pos-2',
        kpiName: 'Content delivery timeliness',
        team: 'Marketing',
        functionName: 'Marketing',
        impactPct: 15.09,
        betterDirection: 'higher',
        actualValue: '95.5%',
        movementLabel: '↑ +36.7%',
      },
    ],
  },
  functions: [
    {
      functionName: 'RCM',
      slug: 'rcm',
      score: 76.0,
      grade: 'D',
      gap: -24.0,
      change: -17.7,
      teamsCount: 4,
      headcount: 11,
      teamsList: 'Coding EGY · Pre-Approvals IP · Resubmission · Submission EGY',
      hasMajorIssue: true,
      highlightBadge: 'Major issue — deep dive next',
    },
    {
      functionName: 'Marketing',
      slug: 'marketing',
      score: 79.6,
      grade: 'D',
      gap: -20.4,
      change: 3.1,
      teamsCount: 1,
      headcount: 13,
      teamsList: 'Marketing',
      hasMajorIssue: true,
      highlightBadge: 'Major issue — deep dive next',
    },
    {
      functionName: 'IT',
      slug: 'it',
      score: 84.4,
      grade: 'C',
      gap: -15.6,
      change: -3.2,
      teamsCount: 1,
      headcount: 3,
      teamsList: 'IT',
      hasMajorIssue: false,
    },
    {
      functionName: 'Call Center',
      slug: 'call-center',
      score: 90.8,
      grade: 'B',
      gap: -9.2,
      change: 2.9,
      teamsCount: 2,
      headcount: 42,
      teamsList: 'Inbound · Outbound',
      hasMajorIssue: false,
    },
    {
      functionName: 'Human Resources',
      slug: 'human-resources',
      score: 95.6,
      grade: 'A',
      gap: -4.4,
      change: 1.0,
      teamsCount: 1,
      headcount: 3,
      teamsList: 'Human Resources',
      hasMajorIssue: false,
    },
    {
      functionName: 'Administration',
      slug: 'administration',
      score: 96.9,
      grade: 'A',
      gap: -3.1,
      change: -0.8,
      teamsCount: 1,
      headcount: 1,
      teamsList: 'Offshore Admin & Management',
      hasMajorIssue: false,
    },
    {
      functionName: 'Finance',
      slug: 'finance',
      score: 97.1,
      grade: 'A',
      gap: -2.9,
      change: null,
      teamsCount: 1,
      headcount: 1,
      teamsList: 'Finance',
      hasMajorIssue: false,
    },
  ],
  teamsAtRisk: [
    {
      team: 'Coding EGY',
      functionName: 'RCM',
      score: 53.6,
      grade: 'E',
      gap: -46.4,
      flags: ['Grade E', 'Lowest in function'],
    },
    {
      team: 'Submission EGY',
      functionName: 'RCM',
      score: 71.6,
      grade: 'D',
      gap: -28.4,
      flags: ['Grade D', 'Below function avg'],
    },
    {
      team: 'Resubmission',
      functionName: 'RCM',
      score: 77.7,
      grade: 'D',
      gap: -22.3,
      flags: ['Grade D'],
    },
    {
      team: 'Marketing',
      functionName: 'Marketing',
      score: 79.6,
      grade: 'D',
      gap: -20.4,
      flags: ['Grade D'],
    },
    {
      team: 'IT',
      functionName: 'IT',
      score: 84.4,
      grade: 'C',
      gap: -15.6,
      flags: ['Grade C', 'Significantly below target'],
    },
    {
      team: 'Outbound',
      functionName: 'Call Center',
      score: 87.0,
      grade: 'C',
      gap: -13.0,
      flags: ['Grade C', 'Lowest in function'],
    },
    {
      team: 'Pre-Approvals IP',
      functionName: 'RCM',
      score: 88.6,
      grade: 'C',
      gap: -11.4,
      flags: ['Grade C'],
    },
  ],
};

/**
 * UAE September 2026 fallback snapshot when switching the upper region filter to UAE.
 */
export const UAE_SEP_2026_DATA: MonthlyOverviewData = {
  ...OFFSHORE_EGYPT_SEP_2026_DATA,
  regionCode: 'UAE',
  regionName: 'UAE Region',
  overall: {
    score: 91.8,
    grade: 'B',
    target: 100.0,
    gap: -8.2,
    change: 1.9,
    previousScore: 89.9,
    headline: '8.2% below target',
    employeesCount: 25,
    teamsCount: 5,
    functionsCount: 5,
    evaluationNote:
      'Evaluation settings are consistent across the compared UAE periods.',
  },
  drivers: { negative: [], positive: [] },
  teamsAtRisk: [],
  functions: [
    {
      functionName: 'CSR',
      slug: 'csr',
      score: 58.3,
      grade: 'E',
      gap: -41.7,
      change: -4.2,
      teamsCount: 1,
      headcount: 106,
      teamsList: 'CSR',
      hasMajorIssue: true,
      highlightBadge: 'Major issue — deep dive next',
    },
    {
      functionName: 'Sales',
      slug: 'sales',
      score: 74.2,
      grade: 'D',
      gap: -25.8,
      change: -1.8,
      teamsCount: 1,
      headcount: 8,
      teamsList: 'Sales',
      hasMajorIssue: true,
      highlightBadge: 'Major issue — deep dive next',
    },
    {
      functionName: 'Pharmacy',
      slug: 'pharmacy',
      score: 88.4,
      grade: 'C',
      gap: -11.6,
      change: 1.4,
      teamsCount: 1,
      headcount: 12,
      teamsList: 'Pharmacy',
      hasMajorIssue: false,
    },
    {
      functionName: 'RCM',
      slug: 'rcm',
      score: 92.4,
      grade: 'B',
      gap: -7.6,
      change: 1.2,
      teamsCount: 4,
      headcount: 25,
      teamsList: 'Coding UAE · Submission UAE · Re-Submission · Pre-Approvals UAE',
      hasMajorIssue: false,
    },
    {
      functionName: 'Finance',
      slug: 'finance',
      score: 97.1,
      grade: 'A',
      gap: -2.9,
      change: null,
      teamsCount: 1,
      headcount: 1,
      teamsList: 'Finance',
      hasMajorIssue: false,
    },
  ],
};

function measuredGradeTakeaway(distribution: NonNullable<ExecutiveSummary['grade_distribution']>): string {
  const ab = (distribution.counts?.A ?? 0) + (distribution.counts?.B ?? 0);
  const de = (distribution.counts?.D ?? 0) + (distribution.counts?.E ?? 0);
  const people = distribution.total === 1 ? 'person' : 'people';
  return `${distribution.total} ${people} graded in this region. ${ab} in A/B and ${de} in D/E.`;
}

/**
 * Adapts live ExecutiveSummary data (when available and populated) into MonthlyOverviewData.
 * Egypt may keep its September snapshot when a section is empty. UAE must not borrow that snapshot.
 */
export function adaptSummaryToMonthlyOverview(
  summary: ExecutiveSummary | null | undefined,
  region: 'EGY' | 'UAE',
): MonthlyOverviewData {
  const fallback = region === 'UAE' ? UAE_SEP_2026_DATA : OFFSHORE_EGYPT_SEP_2026_DATA;
  if (!summary || !summary.data_status.has_data || summary.hero.score === null) {
    return fallback;
  }

  // If this is the default EGY Sep 2026 view, ensure rich snapshot fidelity while reflecting live numbers if present
  const score = summary.hero.score ?? fallback.overall.score;
  const grade = (summary.hero.grade as GradeLetter) || gradeForScore(score);
  const gap = summary.hero.gap ?? Number((score - 100).toFixed(1));
  const change = summary.hero.change ?? fallback.overall.change;
  const previousScore = summary.hero.previous_score ?? Number((score - change).toFixed(1));
  const monthLabel = summary.period.effective
    ? `${summary.period.effective.month} ${summary.period.effective.year}`
    : fallback.monthLabel;
  const previousMonthLabel = summary.period.previous?.month ?? fallback.previousMonthLabel;

  const trend: TrendPoint[] =
    summary.trend.length >= 2
      ? summary.trend.slice(-6).map((pt) => ({
          month: pt.period.month.slice(0, 3),
          key: pt.period.key,
          score: pt.score ?? 0,
          target: pt.target ?? 100,
        }))
      : fallback.trend;

  // Compose stores the mix as counts, percents, and movement. There is no `.grades` list.
  const distribution = summary.grade_distribution;
  const gradeRows: GradeDistributionRow[] =
    distribution && distribution.total > 0
      ? (['A', 'B', 'C', 'D', 'E'] as GradeLetter[]).map((g) => {
          const fb = fallback.gradeDistribution.rows.find((item) => item.grade === g);
          return {
            grade: g,
            label: fb?.label ?? g,
            thresholdLabel: fb?.thresholdLabel ?? '',
            count: distribution.counts?.[g] ?? 0,
            percentage: distribution.percents?.[g] ?? 0,
            change: distribution.movement?.[g] ?? 0,
          };
        })
      : fallback.gradeDistribution.rows;

  const negativeDrivers: ScoreDriverItem[] =
    summary.drivers.negative.length > 0
      ? summary.drivers.negative.slice(0, 4).map((d, idx) => ({
          id: `neg-${idx}`,
          kpiName: d.kpi_label,
          team: d.team ?? region,
          functionName: d.function ?? 'Operations',
          impactPct: d.weighted_impact ?? d.change_percent ?? 0,
          betterDirection: d.direction === 'lower_better' ? 'lower' : 'higher',
          actualValue: d.actual !== null && d.actual !== undefined ? `${ Number(d.actual).toFixed(1) }%` : '—',
        }))
      : region === 'UAE'
        ? []
        : fallback.drivers.negative;

  const positiveDrivers: ScoreDriverItem[] =
    summary.drivers.positive.length > 0
      ? summary.drivers.positive.slice(0, 4).map((d, idx) => ({
          id: `pos-${idx}`,
          kpiName: d.kpi_label,
          team: d.team ?? region,
          functionName: d.function ?? 'Operations',
          impactPct: d.weighted_impact ?? d.change_percent ?? 0,
          betterDirection: d.direction === 'lower_better' ? 'lower' : 'higher',
          actualValue: d.actual !== null && d.actual !== undefined ? `${ Number(d.actual).toFixed(1) }%` : '—',
        }))
      : region === 'UAE'
        ? []
        : fallback.drivers.positive;

  const functions: FunctionOverviewItem[] =
    summary.functions.length > 0
      ? summary.functions
          .filter((fn) => fn.score !== null)
          .map((fn) => {
            const fnScore = fn.score ?? 0;
            const fnGrade = (fn.grade as GradeLetter) || gradeForScore(fnScore);
            const hasMajorIssue = fnGrade === 'D' || fnGrade === 'E' || fnScore < 80;
            return {
              functionName: fn.function,
              slug: fn.function.toLowerCase().replace(/[^a-z0-9]+/g, '-'),
              score: fnScore,
              grade: fnGrade,
              gap: fn.gap ?? Number((fnScore - 100).toFixed(1)),
              change: fn.change,
              teamsCount: fn.teams?.length ?? 0,
              headcount: fn.employees,
              teamsList: (fn.teams ?? []).join(' · '),
              hasMajorIssue,
              highlightBadge: hasMajorIssue ? 'Major issue — deep dive next' : undefined,
            };
          })
          .sort((a, b) => a.score - b.score)
      : fallback.functions;

  const riskCandidates = summary.teams.filter(
    (t) => t.score !== null && (t.grade === 'D' || t.grade === 'E' || t.score < 85),
  );
  const teamsAtRisk: TeamAtRiskItem[] =
    riskCandidates.length > 0
      ? riskCandidates
          .sort((a, b) => (a.score ?? 0) - (b.score ?? 0))
          .map((t) => {
            const tScore = t.score ?? 0;
            const tGrade = (t.grade as GradeLetter) || gradeForScore(tScore);
            const flags: string[] = [`Grade ${tGrade}`];
            if (t.flags.includes('lowest_in_function')) flags.push('Lowest in function');
            if (t.flags.includes('below_function_average')) flags.push('Below function avg');
            return {
              team: t.team,
              functionName: t.function ?? 'General',
              score: tScore,
              grade: tGrade,
              gap: t.gap ?? Number((tScore - 100).toFixed(1)),
              flags,
            };
          })
      : region === 'UAE'
        ? []
        : fallback.teamsAtRisk;

  return {
    ...fallback,
    regionCode: region,
    regionName: region === 'EGY' ? 'Offshore Egypt' : 'UAE Region',
    monthLabel,
    previousMonthLabel,
    periodKey: summary.period.effective?.key ?? fallback.periodKey,
    overall: {
      score,
      grade,
      target: summary.hero.target ?? 100.0,
      gap,
      change,
      previousScore,
      headline: `${Math.abs(gap).toFixed(1)}% ${gap <= 0 ? 'below' : 'above'} target`,
      employeesCount: summary.hero.employees || fallback.overall.employeesCount,
      teamsCount: summary.hero.teams_count || fallback.overall.teamsCount,
      functionsCount: functions.length || fallback.overall.functionsCount,
      evaluationNote: summary.basis_context?.message || fallback.overall.evaluationNote,
    },
    trend,
    gradeDistribution: {
      totalEmployees: distribution?.total || fallback.gradeDistribution.totalEmployees,
      rows: gradeRows,
      takeaway: region === 'UAE' && distribution
        ? measuredGradeTakeaway(distribution)
        : fallback.gradeDistribution.takeaway,
    },
    drivers: {
      negative: negativeDrivers,
      positive: positiveDrivers,
    },
    functions,
    teamsAtRisk,
  };
}
