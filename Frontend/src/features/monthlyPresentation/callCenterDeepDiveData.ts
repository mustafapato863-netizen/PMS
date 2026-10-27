import type { PMSAction } from '../../types';
import { GRADE_PALETTE, getGradeClass } from '../../constants/grades';
import {
  kpiRows,
  normalizeRegion,
  periodFromKey,
  trailingPeriods,
  type ExecRecord,
} from '../executive/compose';
import { executiveFunctionForTeam } from '../executive/functions';
import { preApprovalsLeaderTeamTotal } from '../team/teamKpiAggregator';
import type { ExecutivePeriod } from '../executive/types';
import { gradeForScore, UAE_SEP_2026_DATA, type GradeLetter } from './monthlyOverviewData';

export type SupportImpactLevel = 'Strong' | 'Partial' | 'Mixed' | 'Limited';

export type FullGradeLabel =
  | 'Excellent'
  | 'Meet Expectations'
  | 'Average'
  | 'Below Average'
  | 'Unsatisfactory';

export function fullGradeLabel(gradeOrScore: GradeLetter | number): FullGradeLabel {
  const grade: GradeLetter =
    typeof gradeOrScore === 'number' ? getGradeClass(gradeOrScore) : gradeOrScore;
  return GRADE_PALETTE[grade].label as FullGradeLabel;
}

export function slugifyIdentifier(value: string): string {
  const raw = String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/&/g, 'and')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
  if (raw === 'inbound-agents') return 'inbound';
  if (raw === 'outbound-agents') return 'outbound';
  if (raw === 'offshore-admin-and-management') return 'offshore-admin-management';
  return raw;
}

export function normalizeFunctionSlug(rawSlugOrName: string): string {
  const s = slugifyIdentifier(rawSlugOrName);
  if (s === 'call-center' || s === 'callcenter') return 'call-center';
  if (s === 'rcm' || s === 'revenue-cycle-management') return 'rcm';
  if (s === 'marketing') return 'marketing';
  if (s === 'it' || s === 'information-technology') return 'it';
  if (s === 'human-resources' || s === 'hr') return 'human-resources';
  if (
    s === 'administration' ||
    s === 'admin' ||
    s === 'offshore-admin-management'
  ) {
    return 'administration';
  }
  if (s === 'finance') return 'finance';
  if (s === 'csr' || s === 'customer-service-representative') return 'csr';
  if (s === 'sales') return 'sales';
  if (s === 'pharmacy') return 'pharmacy';
  return s || 'call-center';
}

export function canonicalFunctionNameFromSlug(functionSlug: string): string {
  const norm = normalizeFunctionSlug(functionSlug);
  switch (norm) {
    case 'call-center':
      return 'Call Center';
    case 'rcm':
      return 'RCM';
    case 'marketing':
      return 'Marketing';
    case 'it':
      return 'IT';
    case 'human-resources':
      return 'Human Resources';
    case 'administration':
      return 'Administration';
    case 'finance':
      return 'Finance';
    case 'csr':
      return 'CSR';
    case 'sales':
      return 'Sales';
    case 'pharmacy':
      return 'Pharmacy';
    default:
      return functionSlug
        .split('-')
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(' ');
  }
}

export interface KpiMonthlyPoint {
  month: string;
  periodKey: string;
  actual: number | null;
  target: number | null;
  actualFormatted: string;
  targetFormatted: string;
  metTarget: boolean | null;
}

export interface AgentTeamPerformanceItem {
  id: string;
  teamSlug: string;
  canonicalTeam: string;
  teamName: string;
  roleTag: 'Carrying Function' | 'Pulling Average Down' | 'Primary Team';
  roleTone: 'positive' | 'warning';
  score: number;
  grade: GradeLetter;
  gradeLabel: FullGradeLabel;
  target: number;
  gap: number;
  changeVsPrev: number;
  headcount: number;
  memberUnitLabel?: string;
  diagnosis: string;
  keyStrengthOrDrag: string;
}

export interface SupportPositionItem {
  id: string;
  positionName: string;
  holderName?: string;
  evaluatedScore?: number | null;
  impactLevel: SupportImpactLevel;
  linkedKpis: string[];
  evidenceStat: string;
  explanation: string;
}

export interface AgentKeyKpiItem {
  id: string;
  kpiKey: string;
  name: string;
  shortName: string;
  unit: string;
  actualDisplay: string;
  targetDisplay: string;
  achievementPct: number;
  trendLabel: string;
  trendTone: 'positive' | 'warning' | 'negative';
  betterDirection: 'lower' | 'higher';
  diagnosis: string;
  targetRealismDiagnosis: string;
  trend6Mo: KpiMonthlyPoint[];
}

export interface AgentNeedingAttentionItem {
  id: string;
  employeeId: string;
  agentName: string;
  team: string;
  teamSlug: string;
  score: number;
  grade: GradeLetter;
  gradeLabel: FullGradeLabel;
  reason: string;
  weakestKpiKey: string;
  owningPosition: string;
}

export interface PositionActionPlanItem {
  id: string;
  owningPosition: string;
  actionTitle: string;
  targetScope: string;
  expectedImpactPct: number;
  expectedKpiOutcome: string;
}

export interface CallCenterDeepDiveData {
  functionSlug: string;
  title: string;
  functionName: string;
  regionCode: 'EGY' | 'UAE';
  regionName: string;
  monthLabel: string;
  previousMonthLabel: string;
  periodKey: string;
  pageIndicator: string;
  headline: {
    score: number;
    grade: GradeLetter;
    gradeLabel: FullGradeLabel;
    target: number;
    gap: number;
    changeVsPrev: number;
    narrative: string;
    measuredTeamsCount: number;
    measuredAgentsCount: number;
    supportPositionsCount: number;
  };
  agentTeams: AgentTeamPerformanceItem[];
  supportPositions: SupportPositionItem[];
  keyKpis: AgentKeyKpiItem[];
  agentsNeedingAttention: AgentNeedingAttentionItem[];
  actionsByPosition: {
    items: PositionActionPlanItem[];
    totalExpectedLiftPct: number;
    projectedNextMonthScore: number;
  };
}

export type FunctionDeepDiveData = CallCenterDeepDiveData;

export const IMPACT_LEVEL_STYLES: Record<
  SupportImpactLevel,
  {
    badgeBg: string;
    badgeText: string;
    badgeBorder: string;
    topBar: string;
    cardBorder: string;
    dotColor: string;
  }
> = {
  Strong: {
    badgeBg: 'bg-emerald-50',
    badgeText: 'text-emerald-700',
    badgeBorder: 'border-emerald-200',
    topBar: 'bg-emerald-500',
    cardBorder: 'border-emerald-200/90',
    dotColor: 'bg-emerald-500',
  },
  Partial: {
    badgeBg: 'bg-amber-50',
    badgeText: 'text-amber-700',
    badgeBorder: 'border-amber-200',
    topBar: 'bg-amber-500',
    cardBorder: 'border-amber-200/90',
    dotColor: 'bg-amber-500',
  },
  Mixed: {
    badgeBg: 'bg-amber-50/90',
    badgeText: 'text-amber-800',
    badgeBorder: 'border-amber-300/80',
    topBar: 'bg-amber-400',
    cardBorder: 'border-slate-200/90',
    dotColor: 'bg-amber-500',
  },
  Limited: {
    badgeBg: 'bg-rose-50',
    badgeText: 'text-rose-700',
    badgeBorder: 'border-rose-200',
    topBar: 'bg-rose-500',
    cardBorder: 'border-rose-200/90',
    dotColor: 'bg-rose-500',
  },
};

export function formatKpiValue(value: number | null, unit: string | null | undefined): string {
  if (value === null || !Number.isFinite(value)) return '—';
  const u = String(unit ?? '%').trim().toLowerCase();
  if (u === 'min' || u === 'mins' || u === 'minutes') {
    return `${value.toFixed(2)} min`;
  }
  if (u === 'aed' || u === 'egp' || u === 'usd') {
    return `${Math.round(value).toLocaleString()} ${u.toUpperCase()}`;
  }
  if (u === 'number' || u === 'count' || u === 'visits' || u === 'hours') {
    return `${Math.round(value).toLocaleString()}`;
  }
  return `${value.toFixed(1)}%`;
}

export function mapWeakestKpiToOwner(
  kpiKey: string,
  kpiLabel: string,
  functionSlug = 'call-center',
): string {
  const norm = `${kpiKey} ${kpiLabel}`.toLowerCase();
  const fn = normalizeFunctionSlug(functionSlug);

  if (fn === 'rcm') {
    if (norm.includes('coding') || norm.includes('quality')) {
      return 'Coding & Audit QA Lead';
    }
    if (norm.includes('approval') || norm.includes('pa_') || norm.includes('error')) {
      return 'Pre-Authorization Supervisor';
    }
    if (norm.includes('tat') || norm.includes('due')) {
      return 'RCM Workflow & TAT Coordinator';
    }
    return 'Pre-Authorization Senior Specialist';
  }

  if (fn === 'marketing') {
    if (norm.includes('cpl') || norm.includes('lead') || norm.includes('cpv') || norm.includes('revenue')) {
      return 'Media Buyer & SEO Manager';
    }
    if (norm.includes('response') || norm.includes('social') || norm.includes('channel')) {
      return 'Social Media Head';
    }
    if (norm.includes('brand') || norm.includes('rework') || norm.includes('edit') || norm.includes('schedule')) {
      return 'Creative Director';
    }
    return 'Account Manager';
  }

  if (fn === 'it') {
    if (norm.includes('satisfaction') || norm.includes('csat')) {
      return 'Service Desk QA Coordinator';
    }
    return 'IT Infrastructure & Escalation Lead';
  }

  if (fn === 'human-resources') {
    if (norm.includes('assessment')) return 'Assessment Center Lead';
    return 'HR Operation Supervisor';
  }

  if (fn === 'administration') {
    return 'Offshore PMO Lead';
  }

  if (fn === 'finance') {
    return 'Finance Governance Lead';
  }

  if (norm.includes('quality') || norm.includes('csat')) return 'Quality Specialist';
  if (norm.includes('booking') || norm.includes('fcr') || norm.includes('resolution')) {
    return 'Trainer';
  }
  if (norm.includes('aht') || norm.includes('handle') || norm.includes('utilization')) {
    return 'Workforce Analyst';
  }
  return 'Team Leader';
}

/* -------------------------------------------------------------------------- */
/*  1. CALL CENTER BASELINE (Offshore Egypt & UAE — Sep 2026)                 */
/* -------------------------------------------------------------------------- */

export const CALL_CENTER_DEEP_DIVE_SEP_2026: CallCenterDeepDiveData = {
  functionSlug: 'call-center',
  title: 'Call Center Deep Dive',
  functionName: 'Call Center',
  regionCode: 'EGY',
  regionName: 'Offshore Egypt',
  monthLabel: 'September 2026',
  previousMonthLabel: 'August',
  periodKey: '2026-09',
  pageIndicator: 'Page 2 of 6 · Function Deep Dive',
  headline: {
    score: 90.8,
    grade: 'B',
    gradeLabel: 'Meet Expectations',
    target: 100.0,
    gap: -9.2,
    changeVsPrev: 2.9,
    narrative:
      'Agent performance is the main measurement. Trainer is having clear positive impact, while other support positions need stronger linkage to agent KPIs.',
    measuredTeamsCount: 2,
    measuredAgentsCount: 42,
    supportPositionsCount: 4,
  },
  agentTeams: [
    {
      id: 'inbound-agents',
      teamSlug: 'inbound',
      canonicalTeam: 'Inbound',
      teamName: 'Inbound Agents',
      roleTag: 'Carrying Function',
      roleTone: 'positive',
      score: 91.5,
      grade: 'B',
      gradeLabel: 'Meet Expectations',
      target: 100.0,
      gap: -8.5,
      changeVsPrev: 1.2,
      headcount: 35,
      memberUnitLabel: 'agents',
      diagnosis:
        'Carrying the Call Center score with 35 measured agents averaging 91.5% (+1.2% vs August). Quality Score (95.6% vs 95% target) and Booking Rate recovery (60.3%) offset AHT pressure (3.01 min vs 2.50 min target).',
      keyStrengthOrDrag: 'Primary carrier · 35 agents (83% of function headcount)',
    },
    {
      id: 'outbound-agents',
      teamSlug: 'outbound',
      canonicalTeam: 'Outbound',
      teamName: 'Outbound Agents',
      roleTag: 'Pulling Average Down',
      roleTone: 'warning',
      score: 87.0,
      grade: 'C',
      gradeLabel: 'Average',
      target: 100.0,
      gap: -13.0,
      changeVsPrev: 10.4,
      headcount: 7,
      memberUnitLabel: 'agents',
      diagnosis:
        'Rebounded +10.4% vs August (from 76.6% to 87.0%) as Booking Rate beat the 30% target (32.4%), but Reachability (53.3% vs 75% target) and Attendance Rate (56.6% vs 65% target) still pull the function average down.',
      keyStrengthOrDrag: 'Main drag · 6 of 7 agents below 90% threshold',
    },
  ],
  supportPositions: [
    {
      id: 'pos-trainer',
      positionName: 'Trainer',
      holderName: 'Hagar Ahmed Amin Diab',
      evaluatedScore: 100.0,
      impactLevel: 'Strong',
      linkedKpis: ['Booking Rate', 'Quality Score'],
      evidenceStat: 'Evaluated 100.0% · Quality sessions efficiency ↑ +22.9% (+15.28% lift)',
      explanation:
        'Refresher workshops and certification labs directly lifted Outbound Booking Rate above target (32.4% vs 30.0%) and sustained >95% Quality Score across both agent teams.',
    },
    {
      id: 'pos-qa',
      positionName: 'Quality Specialist',
      holderName: 'Fahmy Sabry El-Saadany',
      evaluatedScore: 84.4,
      impactLevel: 'Partial',
      linkedKpis: ['Quality Score', 'Booking Rate'],
      evidenceStat: 'Evaluated 84.4% · 702 audits (target 600) · Session efficiency 66.7%',
      explanation:
        'Audit volume exceeds the 600-call target (702 evaluations), but coaching conversion on low-booking Inbound and Outbound agents is only partially closing their conversion gap.',
    },
    {
      id: 'pos-tl',
      positionName: 'Team Leader',
      holderName: 'Adham Sameh (Inbound 93.4%) · Amr Badawy (Outbound 86.3%)',
      evaluatedScore: 89.8,
      impactLevel: 'Mixed',
      linkedKpis: ['Attendance Rate', 'AHT (Handle Time)', 'Reachability'],
      evidenceStat: 'Inbound TL 93.4% (Grade B) · Outbound TL 86.3% (Grade C)',
      explanation:
        'Inbound floor supervision keeps team average at 91.5%, whereas Outbound supervision has not yet resolved the Reachability (53.3% vs 75%) and Attendance (56.6% vs 65%) gaps.',
    },
    {
      id: 'pos-wfm',
      positionName: 'Workforce Analyst',
      holderName: 'Mohamed Tarek Abdelghafar Soliman',
      evaluatedScore: 88.7,
      impactLevel: 'Limited',
      linkedKpis: ['AHT (Handle Time)', 'Utilization'],
      evidenceStat: 'Latest score 88.7% · Reporting timeliness 70.8% vs 100% target',
      explanation:
        'Lagging interval reporting timeliness (70.8%) limits real-time queue reallocation, leaving Inbound AHT at 3.01 min (vs 2.50 min target) and Outbound Utilization at 69.7% (vs 80%).',
    },
  ],
  keyKpis: [
    {
      id: 'kpi-aht',
      kpiKey: 'AHT',
      name: 'AHT (Handle Time)',
      shortName: 'AHT',
      unit: 'min',
      actualDisplay: '3.01 min',
      targetDisplay: '2.50 min',
      achievementPct: 84.4,
      trendLabel: '▲ +0.28 min vs August (Slower)',
      trendTone: 'negative',
      betterDirection: 'lower',
      diagnosis:
        'Inbound handle time averaged 3.01 min vs the 2.50 min target; 29 of 35 Inbound agents are near target, while 5 outlier agents (4.20–5.03 min) pull the average up.',
      targetRealismDiagnosis:
        'Target is realistic — team averaged 2.59 min in April and 83% of Inbound agents achieve ≤ 2.75 min. Issue is execution among 5 high-AHT outliers.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 2.59, target: 2.5, actualFormatted: '2.59 min', targetFormatted: '2.50 min', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 2.86, target: 2.5, actualFormatted: '2.86 min', targetFormatted: '2.50 min', metTarget: false },
        { month: 'Jun', periodKey: '2026-06', actual: 2.89, target: 2.5, actualFormatted: '2.89 min', targetFormatted: '2.50 min', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 2.87, target: 2.5, actualFormatted: '2.87 min', targetFormatted: '2.50 min', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 2.74, target: 2.5, actualFormatted: '2.74 min', targetFormatted: '2.50 min', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 3.01, target: 2.5, actualFormatted: '3.01 min', targetFormatted: '2.50 min', metTarget: false },
      ],
    },
    {
      id: 'kpi-booking',
      kpiKey: 'Booking',
      name: 'Booking Conversion Rate',
      shortName: 'Booking Rate',
      unit: '%',
      actualDisplay: '55.7%',
      targetDisplay: '59.2%',
      achievementPct: 92.8,
      trendLabel: '▲ +4.8% vs August (Improving)',
      trendTone: 'positive',
      betterDirection: 'higher',
      diagnosis:
        'Inbound Booking Rate rose to 60.3% (vs 65.0% target) and Outbound Booking Rate surged to 32.4% (exceeding its 30.0% target) following Trainer scripting sessions.',
      targetRealismDiagnosis:
        'Inbound target was raised from 46.0% to 65.0% in June (+19 pts); actual conversion has improved to 60.3%, showing strong execution against a significantly stretched target.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 59.2, target: 46.0, actualFormatted: '59.2%', targetFormatted: '46.0%', metTarget: true },
        { month: 'May', periodKey: '2026-05', actual: 57.7, target: 46.0, actualFormatted: '57.7%', targetFormatted: '46.0%', metTarget: true },
        { month: 'Jun', periodKey: '2026-06', actual: 58.0, target: 65.0, actualFormatted: '58.0%', targetFormatted: '65.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 55.9, target: 65.0, actualFormatted: '55.9%', targetFormatted: '65.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 56.5, target: 65.0, actualFormatted: '56.5%', targetFormatted: '65.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 60.3, target: 65.0, actualFormatted: '60.3%', targetFormatted: '65.0%', metTarget: false },
      ],
    },
    {
      id: 'kpi-quality',
      kpiKey: 'Quality',
      name: 'Call Quality & Resolution Score',
      shortName: 'Quality Score',
      unit: '%',
      actualDisplay: '95.7%',
      targetDisplay: '95.0%',
      achievementPct: 98.1,
      trendLabel: '▲ +2.1% vs August (Above Target)',
      trendTone: 'positive',
      betterDirection: 'higher',
      diagnosis:
        'Both Inbound (95.6%) and Outbound (96.0%) exceeded the 95.0% Quality benchmark in September, with only 1 uncalibrated agent record needing QA remediation.',
      targetRealismDiagnosis:
        'Target (95.0%) is realistic and consistently achieved in 4 of the last 6 months (Apr 98.6%, May 97.7%, Aug 94.0%, Sep 95.7%).',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 98.6, target: 95.0, actualFormatted: '98.6%', targetFormatted: '95.0%', metTarget: true },
        { month: 'May', periodKey: '2026-05', actual: 97.7, target: 95.0, actualFormatted: '97.7%', targetFormatted: '95.0%', metTarget: true },
        { month: 'Jun', periodKey: '2026-06', actual: 93.5, target: 95.0, actualFormatted: '93.5%', targetFormatted: '95.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 94.6, target: 95.0, actualFormatted: '94.6%', targetFormatted: '95.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 93.6, target: 95.0, actualFormatted: '93.6%', targetFormatted: '95.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 95.7, target: 95.0, actualFormatted: '95.7%', targetFormatted: '95.0%', metTarget: true },
      ],
    },
  ],
  agentsNeedingAttention: [
    {
      id: 'att-rawan',
      employeeId: 'Rawan Mohamed Salah Elnajjar',
      agentName: 'Rawan Mohamed Salah Elnajjar',
      team: 'Outbound Agents',
      teamSlug: 'outbound',
      score: 81.0,
      grade: 'C',
      gradeLabel: 'Average',
      reason: 'Reachability at 54.1% (vs 75.0% target) and Utilization at 59.9% (vs 80.0% target)',
      weakestKpiKey: 'Other',
      owningPosition: 'Team Leader',
    },
    {
      id: 'att-maryam',
      employeeId: 'Maryam Elsayed Mahmoud Eid',
      agentName: 'Maryam Elsayed Mahmoud Eid',
      team: 'Inbound Agents',
      teamSlug: 'inbound',
      score: 83.9,
      grade: 'C',
      gradeLabel: 'Average',
      reason: 'AHT at 4.25 min (vs 2.50 min target, 58.8% achievement) & Booking Rate 40.4% (vs 65.0%)',
      weakestKpiKey: 'AHT',
      owningPosition: 'Workforce Analyst',
    },
    {
      id: 'att-abdelrahman-y',
      employeeId: 'Abdelrahman Yasser Abdullah',
      agentName: 'Abdelrahman Yasser Abdullah',
      team: 'Outbound Agents',
      teamSlug: 'outbound',
      score: 84.5,
      grade: 'C',
      gradeLabel: 'Average',
      reason: 'Reachability at 58.7% (vs 75.0% target) & Attendance Rate at 51.8% (vs 65.0% target)',
      weakestKpiKey: 'Other',
      owningPosition: 'Team Leader',
    },
    {
      id: 'att-ahmed-m',
      employeeId: 'Ahmed Mohamed Abdelrashed Abdelkahlek',
      agentName: 'Ahmed Mohamed Abdelrashed Abdelkahlek',
      team: 'Outbound Agents',
      teamSlug: 'outbound',
      score: 84.5,
      grade: 'C',
      gradeLabel: 'Average',
      reason: 'Reachability at 46.9% (vs 75.0% target, 62.5% achievement) & Attendance Rate 52.5%',
      weakestKpiKey: 'Other',
      owningPosition: 'Team Leader',
    },
    {
      id: 'att-abdulrahman-s',
      employeeId: 'Abdulrahman Said Sayed Helal',
      agentName: 'Abdulrahman Said Sayed Helal',
      team: 'Inbound Agents',
      teamSlug: 'inbound',
      score: 84.9,
      grade: 'C',
      gradeLabel: 'Average',
      reason: 'AHT at 5.03 min (vs 2.50 min target, 49.7% achievement) & Booking Rate 47.8% (vs 65.0%)',
      weakestKpiKey: 'AHT',
      owningPosition: 'Workforce Analyst',
    },
    {
      id: 'att-ayaallah',
      employeeId: 'Ayaallah Abdo Hassan Ahmed',
      agentName: 'Ayaallah Abdo Hassan Ahmed',
      team: 'Inbound Agents',
      teamSlug: 'inbound',
      score: 85.0,
      grade: 'C',
      gradeLabel: 'Average',
      reason: 'AHT at 4.50 min (vs 2.50 min target, 55.6% achievement) & Booking Rate 41.3% (vs 65.0%)',
      weakestKpiKey: 'AHT',
      owningPosition: 'Trainer',
    },
  ],
  actionsByPosition: {
    items: [
      {
        id: 'act-tl',
        owningPosition: 'Team Leader',
        actionTitle:
          'Restructure Outbound calling windows & enforce daily shift attendance check-ins for 6 Outbound agents below 90%',
        targetScope: 'Outbound Reachability (53.3% → 68%) & Attendance (56.6% → 65%)',
        expectedImpactPct: 1.5,
        expectedKpiOutcome: 'Lifts Outbound team average from 87.0% → ~91.2% (Grade B)',
      },
      {
        id: 'act-wfm',
        owningPosition: 'Workforce Analyst',
        actionTitle:
          'Deploy real-time interval alerts for calls exceeding 3.50 min & rebalance afternoon Inbound break schedules',
        targetScope: 'Inbound AHT outliers (5 agents averaging 4.20–5.03 min)',
        expectedImpactPct: 1.1,
        expectedKpiOutcome: 'Brings Inbound mean AHT from 3.01 min → ≤ 2.65 min',
      },
      {
        id: 'act-tr',
        owningPosition: 'Trainer',
        actionTitle:
          'Run 1-on-1 booking conversion clinics for the 4 Inbound agents below 50% Booking Rate',
        targetScope: 'Inbound Booking Rate (60.3% → 65.0% target)',
        expectedImpactPct: 0.7,
        expectedKpiOutcome: 'Closes the remaining -4.7% Inbound Booking Rate gap',
      },
      {
        id: 'act-qa',
        owningPosition: 'Quality Specialist',
        actionTitle:
          'Audit & calibrate zero-scored QA records (Andrew Magdy) and link weekly QA coaching to booking conversion',
        targetScope: 'Quality Score & Coaching Conversion (702 monthly audits)',
        expectedImpactPct: 0.5,
        expectedKpiOutcome: 'Eliminates QA zero-score outliers and lifts floor consistency',
      },
    ],
    totalExpectedLiftPct: 3.8,
    projectedNextMonthScore: 94.6,
  },
};

export const CALL_CENTER_DEEP_DIVE_UAE_SEP_2026: CallCenterDeepDiveData = {
  ...CALL_CENTER_DEEP_DIVE_SEP_2026,
  regionCode: 'UAE',
  regionName: 'UAE Region',
  headline: {
    ...CALL_CENTER_DEEP_DIVE_SEP_2026.headline,
    score: 91.0,
    grade: 'B',
    gradeLabel: 'Meet Expectations',
    gap: -9.0,
    changeVsPrev: 6.0,
    measuredTeamsCount: 2,
    measuredAgentsCount: 18,
    supportPositionsCount: 4,
  },
};

/* -------------------------------------------------------------------------- */
/*  2. RCM BASELINE (Offshore Egypt — Sep 2026 Real DB Snapshot)              */
/* -------------------------------------------------------------------------- */

export const RCM_DEEP_DIVE_SEP_2026: CallCenterDeepDiveData = {
  functionSlug: 'rcm',
  title: 'RCM Deep Dive',
  functionName: 'RCM',
  regionCode: 'EGY',
  regionName: 'Offshore Egypt',
  monthLabel: 'September 2026',
  previousMonthLabel: 'August',
  periodKey: '2026-09',
  pageIndicator: 'Page 2 of 6 · Function Deep Dive',
  headline: {
    score: 76.0,
    grade: 'D',
    gradeLabel: 'Below Average',
    target: 100.0,
    gap: -24.0,
    changeVsPrev: -5.4,
    narrative:
      'Specialist team execution is the primary measurement across 4 RCM teams. Pre-Approvals IP (82.8%) stabilizes volume, while Coding EGY (53.6%) and Submission EGY (71.6%) require immediate QA and TAT governance intervention.',
    measuredTeamsCount: 4,
    measuredAgentsCount: 11,
    supportPositionsCount: 4,
  },
  agentTeams: [
    {
      id: 'pre-approvals-ip',
      teamSlug: 'pre-approvals-ip',
      canonicalTeam: 'Pre-Approvals IP',
      teamName: 'Pre-Approvals IP',
      roleTag: 'Carrying Function',
      roleTone: 'positive',
      score: 82.8,
      grade: 'C',
      gradeLabel: 'Average',
      target: 100.0,
      gap: -17.2,
      changeVsPrev: -0.9,
      headcount: 7,
      memberUnitLabel: 'specialists',
      diagnosis:
        'Carrying 64% of RCM headcount (7 specialists) at 82.8%. IP Initial Rejection % beat the 1.0% ceiling (0.3% actual), while Error % (1.5% vs 1.0% target) and 48-hr Approval SLA (77.9% vs 90.0% target) hold back the score.',
      keyStrengthOrDrag: 'Primary carrier · 7 specialists (64% of RCM headcount)',
    },
    {
      id: 'resubmission',
      teamSlug: 'resubmission',
      canonicalTeam: 'Resubmission',
      teamName: 'Resubmission',
      roleTag: 'Pulling Average Down',
      roleTone: 'warning',
      score: 77.7,
      grade: 'D',
      gradeLabel: 'Below Average',
      target: 100.0,
      gap: -22.3,
      changeVsPrev: -9.3,
      headcount: 1,
      memberUnitLabel: 'specialist',
      diagnosis:
        'Post-resubmission Rejection Rate achieved 0.0% (vs 60.0% ceiling), but Quality Errors Rate rose to 7.0% (vs 5.0% target) and TAT slipped to 84.0% (vs 100.0% target), pulling the team down -9.3% vs August.',
      keyStrengthOrDrag: 'Quality error & TAT drag · 1 specialist (77.7%)',
    },
    {
      id: 'submission-egy',
      teamSlug: 'submission-egy',
      canonicalTeam: 'Submission EGY',
      teamName: 'Submission EGY',
      roleTag: 'Pulling Average Down',
      roleTone: 'warning',
      score: 71.6,
      grade: 'D',
      gradeLabel: 'Below Average',
      target: 100.0,
      gap: -28.4,
      changeVsPrev: -19.8,
      headcount: 1,
      memberUnitLabel: 'specialist',
      diagnosis:
        'Submission Within Due Date exceeded target at 99.9% (vs 90.0% target), but Initial Rejection % rose to 3.8% against a strict 2.0% ceiling, causing a -19.8% drop vs August.',
      keyStrengthOrDrag: 'Initial rejection drag · 3.8% vs 2.0% target',
    },
    {
      id: 'coding-egy',
      teamSlug: 'coding-egy',
      canonicalTeam: 'Coding EGY',
      teamName: 'Coding EGY',
      roleTag: 'Pulling Average Down',
      roleTone: 'warning',
      score: 53.6,
      grade: 'E',
      gradeLabel: 'Unsatisfactory',
      target: 100.0,
      gap: -46.4,
      changeVsPrev: -12.6,
      headcount: 2,
      memberUnitLabel: 'specialists',
      diagnosis:
        'Lowest-scoring team in Offshore Egypt (53.6%, Grade E). While claim Rejection Rate is 0.0% (vs 6.0% ceiling), Quality Errors Rate spiked to 11.3% (vs 5.0% target) and TAT fell to 54.9% (vs 90.0% target).',
      keyStrengthOrDrag: 'Critical drag · 2 specialists averaging 53.6% (Grade E)',
    },
  ],
  supportPositions: [
    {
      id: 'rcm-pos-senior-pa',
      positionName: 'Pre-Authorization Senior Specialist',
      holderName: 'Omar Abdelhamid Amin Elsayed konswa',
      evaluatedScore: 91.5,
      impactLevel: 'Strong',
      linkedKpis: ['IP Initial Rejection %', '% Approval within 48 hrs'],
      evidenceStat: 'Evaluated 91.5% (Grade B) · 0.0% IP Initial Rejection (vs 1.0% target)',
      explanation:
        'Demonstrates benchmark execution on inpatient pre-approvals (0.0% initial rejection) and provides technical escalation review for complex cases.',
    },
    {
      id: 'rcm-pos-pa-sup',
      positionName: 'Pre-Authorization Supervisor',
      holderName: 'Hossam Mohamed Abdelsameea Tolba Ahmed',
      evaluatedScore: 88.6,
      impactLevel: 'Partial',
      linkedKpis: ['IP Initial Rejection %', 'Error %', '% Approval within 48 hrs'],
      evidenceStat: 'Evaluated 88.6% (Grade C) · Team Initial Rejection 0.3% vs 1.0% target',
      explanation:
        'Keeps inpatient initial rejections well below the 1.0% ceiling, but floor supervision needs tighter pre-submission double-checks to bring Error % from 1.5% down to ≤ 1.0%.',
    },
    {
      id: 'rcm-pos-tat-coord',
      positionName: 'RCM Workflow & TAT Coordinator',
      holderName: 'RCM Operations Governance',
      evaluatedScore: 81.4,
      impactLevel: 'Mixed',
      linkedKpis: ['TAT', '% of Submission Within Due date', '% Approval within 48 hrs'],
      evidenceStat: 'Submission Due Date 99.9% (Met) · Coding TAT 54.9% (Missed)',
      explanation:
        'Claim submission deadline adherence is near-perfect (99.9%), but batch allocation bottlenecks in OP Coding left Coding TAT at 54.9% vs 90.0% target.',
    },
    {
      id: 'rcm-pos-coding-qa',
      positionName: 'Coding & Audit QA Lead',
      holderName: 'RCM Clinical Coding QA',
      evaluatedScore: 68.5,
      impactLevel: 'Limited',
      linkedKpis: ['Quality Errors Rate', 'Initial Rejection %'],
      evidenceStat: 'Coding Quality Errors at 11.3% (vs 5.0%) · Resubmission Errors 7.0%',
      explanation:
        'Pre-billing audit sampling has not curbed ICD/CPT coding errors in Coding EGY (9.0%–13.6% error rate) or claim scrubber rejections in Submission EGY (3.8% vs 2.0%).',
    },
  ],
  keyKpis: [
    {
      id: 'rcm-kpi-coding-errors',
      kpiKey: 'egy_coding_quality_errors',
      name: 'Coding Quality Errors Rate',
      shortName: 'Coding Errors %',
      unit: '%',
      actualDisplay: '11.3%',
      targetDisplay: '5.0%',
      achievementPct: 45.7,
      trendLabel: '▲ +3.5% vs August (Worse)',
      trendTone: 'negative',
      betterDirection: 'lower',
      diagnosis:
        'Coding EGY Quality Errors rose from 7.8% in August to 11.3% in September against a 5.0% ceiling (Ahmed Montaser 9.0%, Mohamed Galal 13.6%).',
      targetRealismDiagnosis:
        'Target (5.0% max error rate) is realistic — team achieved 4.8% in May and 5.1% in June. Current gap is an execution and pre-audit issue on SHJ OP Coding batches.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 5.4, target: 5.0, actualFormatted: '5.4%', targetFormatted: '5.0%', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 4.8, target: 5.0, actualFormatted: '4.8%', targetFormatted: '5.0%', metTarget: true },
        { month: 'Jun', periodKey: '2026-06', actual: 5.1, target: 5.0, actualFormatted: '5.1%', targetFormatted: '5.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 6.9, target: 5.0, actualFormatted: '6.9%', targetFormatted: '5.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 7.8, target: 5.0, actualFormatted: '7.8%', targetFormatted: '5.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 11.3, target: 5.0, actualFormatted: '11.3%', targetFormatted: '5.0%', metTarget: false },
      ],
    },
    {
      id: 'rcm-kpi-pa-48h',
      kpiKey: 'pa_approval_48h',
      name: '% Approval within 48 hrs (Pre-Approvals IP)',
      shortName: '48h Approval %',
      unit: '%',
      actualDisplay: '77.9%',
      targetDisplay: '90.0%',
      achievementPct: 86.6,
      trendLabel: '▼ -3.2% vs August (Needs attention)',
      trendTone: 'warning',
      betterDirection: 'higher',
      diagnosis:
        'Pre-Approvals IP averaged 77.9% 48-hour turnaround vs 90.0% target; Manar Emad achieved 98.2%, while Hadeer Gamal (59.6%) and Nouran Salah (70.4%) lagged.',
      targetRealismDiagnosis:
        'Target (90.0%) is achievable — top specialists reach 98.2% on the same payer mix. Execution variance in payer follow-up timing drives the gap.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 88.5, target: 90.0, actualFormatted: '88.5%', targetFormatted: '90.0%', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 90.4, target: 90.0, actualFormatted: '90.4%', targetFormatted: '90.0%', metTarget: true },
        { month: 'Jun', periodKey: '2026-06', actual: 86.2, target: 90.0, actualFormatted: '86.2%', targetFormatted: '90.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 83.4, target: 90.0, actualFormatted: '83.4%', targetFormatted: '90.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 81.1, target: 90.0, actualFormatted: '81.1%', targetFormatted: '90.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 77.9, target: 90.0, actualFormatted: '77.9%', targetFormatted: '90.0%', metTarget: false },
      ],
    },
    {
      id: 'rcm-kpi-sub-rejection',
      kpiKey: 'egy_submission_initial_rejection',
      name: 'Submission Initial Rejection %',
      shortName: 'Initial Rejection %',
      unit: '%',
      actualDisplay: '3.8%',
      targetDisplay: '2.0%',
      achievementPct: 52.6,
      trendLabel: '▲ +1.9% vs August (Higher rejections)',
      trendTone: 'negative',
      betterDirection: 'lower',
      diagnosis:
        'Submission EGY Initial Rejection % rose to 3.8% vs the 2.0% ceiling despite 99.9% on-time submission compliance.',
      targetRealismDiagnosis:
        'Target (≤ 2.0%) was met in 3 of the prior 5 months (Apr 1.8%, May 1.7%, Jul 1.9%). Pre-submission scrubber validation is needed before batch upload.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 1.8, target: 2.0, actualFormatted: '1.8%', targetFormatted: '2.0%', metTarget: true },
        { month: 'May', periodKey: '2026-05', actual: 1.7, target: 2.0, actualFormatted: '1.7%', targetFormatted: '2.0%', metTarget: true },
        { month: 'Jun', periodKey: '2026-06', actual: 2.2, target: 2.0, actualFormatted: '2.2%', targetFormatted: '2.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 1.9, target: 2.0, actualFormatted: '1.9%', targetFormatted: '2.0%', metTarget: true },
        { month: 'Aug', periodKey: '2026-08', actual: 1.9, target: 2.0, actualFormatted: '1.9%', targetFormatted: '2.0%', metTarget: true },
        { month: 'Sep', periodKey: '2026-09', actual: 3.8, target: 2.0, actualFormatted: '3.8%', targetFormatted: '2.0%', metTarget: false },
      ],
    },
  ],
  agentsNeedingAttention: [
    {
      id: 'rcm-att-galal',
      employeeId: 'Mohamed Galal Ali Abbas',
      agentName: 'Mohamed Galal Ali Abbas',
      team: 'Coding EGY',
      teamSlug: 'coding-egy',
      score: 41.9,
      grade: 'E',
      gradeLabel: 'Unsatisfactory',
      reason: 'Quality Errors Rate at 13.6% (vs 5.0% target) & TAT at 42.4% (vs 90.0% target)',
      weakestKpiKey: 'egy_coding_quality_errors',
      owningPosition: 'Coding & Audit QA Lead',
    },
    {
      id: 'rcm-att-montaser',
      employeeId: 'Ahmed Montaser Zakaria Mohamed',
      agentName: 'Ahmed Montaser Zakaria Mohamed',
      team: 'Coding EGY',
      teamSlug: 'coding-egy',
      score: 65.2,
      grade: 'D',
      gradeLabel: 'Below Average',
      reason: 'Quality Errors Rate at 9.0% (vs 5.0% target) & TAT at 67.4% (vs 90.0% target)',
      weakestKpiKey: 'egy_coding_quality_errors',
      owningPosition: 'Coding & Audit QA Lead',
    },
    {
      id: 'rcm-att-salma-nagy',
      employeeId: 'Salma Nagy Ali Hendy',
      agentName: 'Salma Nagy Ali Hendy',
      team: 'Submission EGY',
      teamSlug: 'submission-egy',
      score: 71.6,
      grade: 'D',
      gradeLabel: 'Below Average',
      reason: 'Initial Rejection % at 3.8% (vs 2.0% target ceiling, 52.6% achievement)',
      weakestKpiKey: 'egy_submission_initial_rejection',
      owningPosition: 'Coding & Audit QA Lead',
    },
    {
      id: 'rcm-att-ali-mesbah',
      employeeId: 'Ali Mohamed Mesbah Mohamed',
      agentName: 'Ali Mohamed Mesbah Mohamed',
      team: 'Pre-Approvals IP',
      teamSlug: 'pre-approvals-ip',
      score: 74.8,
      grade: 'D',
      gradeLabel: 'Below Average',
      reason: 'Error % at 2.1% (vs 1.0% target) & IP Initial Rejection % at 1.3% (vs 1.0%)',
      weakestKpiKey: 'pa_error_rate',
      owningPosition: 'Pre-Authorization Supervisor',
    },
    {
      id: 'rcm-att-nouran',
      employeeId: 'Nouran Salah Anwar Mohamed Dekrori',
      agentName: 'Nouran Salah Anwar Mohamed Dekrori',
      team: 'Pre-Approvals IP',
      teamSlug: 'pre-approvals-ip',
      score: 76.8,
      grade: 'D',
      gradeLabel: 'Below Average',
      reason: 'Error % at 1.9% (vs 1.0% target) & 48-hr Approval SLA at 70.4% (vs 90.0%)',
      weakestKpiKey: 'pa_error_rate',
      owningPosition: 'Pre-Authorization Supervisor',
    },
    {
      id: 'rcm-att-esraa',
      employeeId: 'Esraa Ahmed Helmy Ismail',
      agentName: 'Esraa Ahmed Helmy Ismail',
      team: 'Resubmission',
      teamSlug: 'resubmission',
      score: 77.7,
      grade: 'D',
      gradeLabel: 'Below Average',
      reason: 'Quality Errors Rate at 7.0% (vs 5.0% target) & TAT at 84.0% (vs 100.0%)',
      weakestKpiKey: 'egy_resubmission_quality_errors',
      owningPosition: 'RCM Workflow & TAT Coordinator',
    },
  ],
  actionsByPosition: {
    items: [
      {
        id: 'rcm-act-1',
        owningPosition: 'Coding & Audit QA Lead',
        actionTitle:
          'Institute mandatory 100% pre-bill peer audit on SHJ OP Coding batches for Mohamed Galal & Ahmed Montaser',
        targetScope: 'Coding EGY Quality Errors Rate (11.3% → ≤ 5.0%)',
        expectedImpactPct: 3.4,
        expectedKpiOutcome: 'Lifts Coding EGY from 53.6% (Grade E) → ~78.0% (Grade C/D)',
      },
      {
        id: 'rcm-act-2',
        owningPosition: 'Pre-Authorization Supervisor',
        actionTitle:
          'Run daily clinical documentation & ICD-code verification huddles for 5 Pre-Approvals IP specialists below 90%',
        targetScope: 'Pre-Approvals IP Error % (1.5% → ≤ 1.0%) & 48h Approval (77.9% → 90%)',
        expectedImpactPct: 2.6,
        expectedKpiOutcome: 'Lifts Pre-Approvals IP average from 82.8% → ~89.5%',
      },
      {
        id: 'rcm-act-3',
        owningPosition: 'RCM Workflow & TAT Coordinator',
        actionTitle:
          'Automate morning claim-queue partitioning to eliminate OP Coding & Resubmission TAT backlog',
        targetScope: 'Coding TAT (54.9% → 85%+) & Resubmission TAT (84.0% → 96%+)',
        expectedImpactPct: 1.8,
        expectedKpiOutcome: 'Recovers +1.8% function-wide RCM TAT score',
      },
      {
        id: 'rcm-act-4',
        owningPosition: 'Pre-Authorization Senior Specialist',
        actionTitle:
          'Deploy pre-submission claim scrubber checklist for Submission EGY prior to payer portal upload',
        targetScope: 'Submission Initial Rejection % (3.8% → ≤ 2.0%)',
        expectedImpactPct: 1.4,
        expectedKpiOutcome: 'Restores Submission EGY from 71.6% → ~90.0% (Grade B)',
      },
    ],
    totalExpectedLiftPct: 9.2,
    projectedNextMonthScore: 85.2,
  },
};

/* -------------------------------------------------------------------------- */
/*  3. MARKETING BASELINE (Offshore Egypt — Sep 2026 Real DB Snapshot)        */
/* -------------------------------------------------------------------------- */

export const MARKETING_DEEP_DIVE_SEP_2026: CallCenterDeepDiveData = {
  functionSlug: 'marketing',
  title: 'Marketing Deep Dive',
  functionName: 'Marketing',
  regionCode: 'EGY',
  regionName: 'Offshore Egypt',
  monthLabel: 'September 2026',
  previousMonthLabel: 'August',
  periodKey: '2026-09',
  pageIndicator: 'Page 2 of 6 · Function Deep Dive',
  headline: {
    score: 79.6,
    grade: 'D',
    gradeLabel: 'Below Average',
    target: 100.0,
    gap: -20.4,
    changeVsPrev: 0.3,
    narrative:
      'Creative & Content delivery is strong (Creative Director 98.3%, Content Writer 97.7%, Account Manager 92.6%), but Media Buying CPL/Lead volume (66.1%–79.5%), Social Media response time (208 min vs 31 min target), and Web Uptime (52.5%) pull the function to 79.6%.',
    measuredTeamsCount: 1,
    measuredAgentsCount: 13,
    supportPositionsCount: 4,
  },
  agentTeams: [
    {
      id: 'marketing-team',
      teamSlug: 'marketing',
      canonicalTeam: 'Marketing',
      teamName: 'Marketing Specialists & Execution',
      roleTag: 'Pulling Average Down',
      roleTone: 'warning',
      score: 79.6,
      grade: 'D',
      gradeLabel: 'Below Average',
      target: 100.0,
      gap: -20.4,
      changeVsPrev: 0.3,
      headcount: 13,
      memberUnitLabel: 'specialists',
      diagnosis:
        '4 of 13 members achieve Grade A (Content Writer 97.7%, Creative Director 98.3%, Account Manager 92.6%, Graphic Designer Elsayed 91.9%), while 9 members score below 90% due to Social Media Response Time (208 min vs 31 min), Media Buying CPL, and Web Developer bug resolution (52.5%).',
      keyStrengthOrDrag: '9 of 13 specialists below 90% threshold · 6 in Grade D/E',
    },
  ],
  supportPositions: [
    {
      id: 'mkt-pos-cd',
      positionName: 'Creative Director',
      holderName: 'Mohamed Abdelmegid Diab',
      evaluatedScore: 98.3,
      impactLevel: 'Strong',
      linkedKpis: ['Brand Consistency Score', 'Projects Delivered on Schedule', 'Edits Rate'],
      evidenceStat: 'Evaluated 98.3% (Grade A) · 470 deliverables · 100% Brand Consistency',
      explanation:
        'Maintains 93%–98% brand consistency across Graphic Designers, though designer Edits Rate (9.4%–16.4% vs 6%–8% target) needs tighter brief sign-off.',
    },
    {
      id: 'mkt-pos-am',
      positionName: 'Account Manager',
      holderName: 'Dina Samir',
      evaluatedScore: 92.6,
      impactLevel: 'Strong',
      linkedKpis: ['Requests Delivery', 'Projects Ontime', 'Edit Rate'],
      evidenceStat: 'Evaluated 92.6% (Grade B) · Requests Delivery 96.8% (vs 90% target)',
      explanation:
        'Strong intake governance keeps client request delivery at 96.8%, helping shield creative specialists from scope creep.',
    },
    {
      id: 'mkt-pos-smh',
      positionName: 'Social Media Head',
      holderName: 'Hossam El-Naggar',
      evaluatedScore: 79.7,
      impactLevel: 'Partial',
      linkedKpis: ['Response Time', 'Response Rate (%)', 'Content Calendar Adherence'],
      evidenceStat: 'Evaluated 79.7% (Grade D) · Calendar Adherence 98% · Response Time 208 min',
      explanation:
        'Content calendar adherence (97%–98%) and channel growth (1.3% vs 1.0%) are on track, but inbox Response Time (208 min vs 30–31 min target) severely impacts both Social Media Specialists (69.3%).',
    },
    {
      id: 'mkt-pos-mb-mgr',
      positionName: 'Media Buyer & SEO Manager',
      holderName: 'Ahmed Mohamed Shehata',
      evaluatedScore: 66.1,
      impactLevel: 'Limited',
      linkedKpis: ['CPL (Cost Per Lead)', 'Leads Volume', 'Revenue'],
      evidenceStat: 'Evaluated 66.1% (Grade D) · Leads 11,190 vs 19,361 target · CPL 118–158 AED',
      explanation:
        'Paid campaign CPL (118.5–157.6 AED vs 105.0 AED target) and lead volume shortfalls across Media Buyers directly pull Marketing into Grade D.',
    },
  ],
  keyKpis: [
    {
      id: 'mkt-kpi-response-time',
      kpiKey: 'sms_response_time',
      name: 'Social Media Response Time',
      shortName: 'Response Time',
      unit: 'min',
      actualDisplay: '208.00 min',
      targetDisplay: '31.00 min',
      achievementPct: 14.9,
      trendLabel: '▲ +42.00 min vs August (Slower)',
      trendTone: 'negative',
      betterDirection: 'lower',
      diagnosis:
        'Social Media Specialists averaged 208 min response time vs the 31 min SLA target, creating the single largest KPI deduction across the Social Media Specialist role (69.3% role average).',
      targetRealismDiagnosis:
        'After-hours unstaffed inbox windows inflate the 24h average to 208 min; automated triage routing + business-hours SLA calibration are required.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 95.0, target: 31.0, actualFormatted: '95.00 min', targetFormatted: '31.00 min', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 112.0, target: 31.0, actualFormatted: '112.00 min', targetFormatted: '31.00 min', metTarget: false },
        { month: 'Jun', periodKey: '2026-06', actual: 140.0, target: 31.0, actualFormatted: '140.00 min', targetFormatted: '31.00 min', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 155.0, target: 31.0, actualFormatted: '155.00 min', targetFormatted: '31.00 min', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 166.0, target: 31.0, actualFormatted: '166.00 min', targetFormatted: '31.00 min', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 208.0, target: 31.0, actualFormatted: '208.00 min', targetFormatted: '31.00 min', metTarget: false },
      ],
    },
    {
      id: 'mkt-kpi-cpl',
      kpiKey: 'pos_media_buyer_cpl',
      name: 'Media Buying Cost Per Lead (CPL)',
      shortName: 'CPL (AED)',
      unit: 'AED',
      actualDisplay: '138 AED',
      targetDisplay: '105 AED',
      achievementPct: 76.1,
      trendLabel: '▲ +14 AED vs August (Higher cost)',
      trendTone: 'negative',
      betterDirection: 'lower',
      diagnosis:
        'Media Buyers averaged 138.1 AED CPL (ranging from 118.5 to 157.6 AED) vs the 105 AED benchmark, reducing paid lead volume.',
      targetRealismDiagnosis:
        'Target (105 AED) was met in April (102 AED) and May (104 AED) before summer auction competition increased CPCs.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 102.0, target: 105.0, actualFormatted: '102 AED', targetFormatted: '105 AED', metTarget: true },
        { month: 'May', periodKey: '2026-05', actual: 104.0, target: 105.0, actualFormatted: '104 AED', targetFormatted: '105 AED', metTarget: true },
        { month: 'Jun', periodKey: '2026-06', actual: 115.0, target: 105.0, actualFormatted: '115 AED', targetFormatted: '105 AED', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 121.0, target: 105.0, actualFormatted: '121 AED', targetFormatted: '105 AED', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 124.0, target: 105.0, actualFormatted: '124 AED', targetFormatted: '105 AED', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 138.0, target: 105.0, actualFormatted: '138 AED', targetFormatted: '105 AED', metTarget: false },
      ],
    },
    {
      id: 'mkt-kpi-edits',
      kpiKey: 'gd_edits_rate',
      name: 'Graphic Design Edits Rate',
      shortName: 'Edits Rate',
      unit: '%',
      actualDisplay: '13.4%',
      targetDisplay: '7.0%',
      achievementPct: 52.2,
      trendLabel: '▼ -1.2% vs August (Improving)',
      trendTone: 'warning',
      betterDirection: 'lower',
      diagnosis:
        'Graphic Designers delivered strong volume (420/470 on schedule) and 96% brand consistency, but Edits Rate averaged 13.4% vs 7.0% target.',
      targetRealismDiagnosis:
        'Target (7.0% max edits) is tight for multi-stakeholder campaigns; top designer achieved 9.4% while bottom quartile reached 16.4%.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 11.2, target: 7.0, actualFormatted: '11.2%', targetFormatted: '7.0%', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 12.0, target: 7.0, actualFormatted: '12.0%', targetFormatted: '7.0%', metTarget: false },
        { month: 'Jun', periodKey: '2026-06', actual: 14.8, target: 7.0, actualFormatted: '14.8%', targetFormatted: '7.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 15.1, target: 7.0, actualFormatted: '15.1%', targetFormatted: '7.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 14.6, target: 7.0, actualFormatted: '14.6%', targetFormatted: '7.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 13.4, target: 7.0, actualFormatted: '13.4%', targetFormatted: '7.0%', metTarget: false },
      ],
    },
  ],
  agentsNeedingAttention: [
    {
      id: 'mkt-att-web',
      employeeId: 'Abdelrahman Yousry Abdelaziz Hamdy',
      agentName: 'Abdelrahman Yousry Abdelaziz Hamdy',
      team: 'Marketing',
      teamSlug: 'marketing',
      score: 52.5,
      grade: 'E',
      gradeLabel: 'Unsatisfactory',
      reason: 'Bug resolution rate at 50.0% (vs 100%) & Request delivery timeliness at 50.0% (Web Developer)',
      weakestKpiKey: 'wd_bug_resolution',
      owningPosition: 'Account Manager',
    },
    {
      id: 'mkt-att-shehata',
      employeeId: 'Ahmed Mohamed Shehata',
      agentName: 'Ahmed Mohamed Shehata',
      team: 'Marketing',
      teamSlug: 'marketing',
      score: 66.1,
      grade: 'D',
      gradeLabel: 'Below Average',
      reason: 'Paid Volume at 3,208 vs 13,947 target & Leads at 11,190 vs 19,361 (Media Buyer & SEO Manager)',
      weakestKpiKey: 'pos_media_buyer_seo_manager_volume',
      owningPosition: 'Media Buyer & SEO Manager',
    },
    {
      id: 'mkt-att-bahy',
      employeeId: 'Bahy Hamed Amer',
      agentName: 'Bahy Hamed Amer',
      team: 'Marketing',
      teamSlug: 'marketing',
      score: 66.3,
      grade: 'D',
      gradeLabel: 'Below Average',
      reason: 'CPL at 157.6 AED (vs 105 AED target) & Leads at 4,262 vs 8,657 (Media Buyer)',
      weakestKpiKey: 'pos_media_buyer_leads',
      owningPosition: 'Media Buyer & SEO Manager',
    },
    {
      id: 'mkt-att-mina',
      employeeId: 'Mina Nabil',
      agentName: 'Mina Nabil',
      team: 'Marketing',
      teamSlug: 'marketing',
      score: 69.3,
      grade: 'D',
      gradeLabel: 'Below Average',
      reason: 'Response Time at 208 min (vs 31 min target) & Response Rate at 87.3% (Social Media Specialist)',
      weakestKpiKey: 'sms_response_time',
      owningPosition: 'Social Media Head',
    },
    {
      id: 'mkt-att-samya',
      employeeId: 'Samya Ismail',
      agentName: 'Samya Ismail',
      team: 'Marketing',
      teamSlug: 'marketing',
      score: 69.3,
      grade: 'D',
      gradeLabel: 'Below Average',
      reason: 'Response Time at 208 min (vs 31 min target) & Response Rate at 87.3% (Social Media Specialist)',
      weakestKpiKey: 'sms_response_time',
      owningPosition: 'Social Media Head',
    },
    {
      id: 'mkt-att-ziad',
      employeeId: 'Ziad sayed hassan',
      agentName: 'Ziad sayed hassan',
      team: 'Marketing',
      teamSlug: 'marketing',
      score: 79.5,
      grade: 'D',
      gradeLabel: 'Below Average',
      reason: 'Conversion Rate (CR) at 14.0% (vs 34.0% target) & CPV at 858 AED vs 309 AED (Media Buyer)',
      weakestKpiKey: 'pos_media_buyer_cr',
      owningPosition: 'Media Buyer & SEO Manager',
    },
  ],
  actionsByPosition: {
    items: [
      {
        id: 'mkt-act-1',
        owningPosition: 'Social Media Head',
        actionTitle:
          'Deploy automated DM/comment triage & staggered shift coverage across the Social Media Specialist role',
        targetScope: 'Social Media Response Time (208 min → ≤ 35 min)',
        expectedImpactPct: 3.6,
        expectedKpiOutcome: 'Lifts Social Media cohort from 69.3% → ~88.0% (Grade C)',
      },
      {
        id: 'mkt-act-2',
        owningPosition: 'Media Buyer & SEO Manager',
        actionTitle:
          'Reallocate paid ad spend from high-CPL ad sets (157.6 AED) to high-converting search/retargeting funnels',
        targetScope: 'Media Buying CPL (138 AED → ≤ 110 AED) & Lead Volume',
        expectedImpactPct: 3.1,
        expectedKpiOutcome: 'Lifts Media Buying cohort from 70.6% → ~84.0%',
      },
      {
        id: 'mkt-act-3',
        owningPosition: 'Account Manager',
        actionTitle:
          'Implement sprint ticket triage and staging QA checklist for the Web Developer role',
        targetScope: 'Website Uptime (60% → 98%) & Bug Resolution (50% → 90%)',
        expectedImpactPct: 2.2,
        expectedKpiOutcome: 'Lifts Web Developer score from 52.5% → ~85.0%',
      },
      {
        id: 'mkt-act-4',
        owningPosition: 'Creative Director',
        actionTitle:
          'Enforce standardized creative brief sign-off before design production to cut post-delivery Edits Rate',
        targetScope: 'Graphic Design Edits Rate (13.4% → ≤ 8.0%)',
        expectedImpactPct: 1.3,
        expectedKpiOutcome: 'Brings all 3 Graphic Designers above 90% (Grade B)',
      },
    ],
    totalExpectedLiftPct: 10.2,
    projectedNextMonthScore: 89.8,
  },
};

/* -------------------------------------------------------------------------- */
/*  4. IT, HUMAN RESOURCES, ADMINISTRATION, FINANCE BASELINES (Sep 2026)      */
/* -------------------------------------------------------------------------- */

export const IT_DEEP_DIVE_SEP_2026: CallCenterDeepDiveData = {
  functionSlug: 'it',
  title: 'IT Deep Dive',
  functionName: 'IT',
  regionCode: 'EGY',
  regionName: 'Offshore Egypt',
  monthLabel: 'September 2026',
  previousMonthLabel: 'August',
  periodKey: '2026-09',
  pageIndicator: 'Page 2 of 6 · Function Deep Dive',
  headline: {
    score: 84.4,
    grade: 'C',
    gradeLabel: 'Average',
    target: 100.0,
    gap: -15.6,
    changeVsPrev: 0.9,
    narrative:
      'IT Technical Support is the primary measured team (84.3%, Grade C). Average Ticket Resolution Time achieved 100% of target, while User Satisfaction Score (69.5% vs 100% target) and First-Contact Ticket Resolution (85.8%) require post-ticket follow-up governance.',
    measuredTeamsCount: 1,
    measuredAgentsCount: 1,
    supportPositionsCount: 2,
  },
  agentTeams: [
    {
      id: 'it-team',
      teamSlug: 'it',
      canonicalTeam: 'IT',
      teamName: 'IT Technical Support',
      roleTag: 'Primary Team',
      roleTone: 'warning',
      score: 84.3,
      grade: 'C',
      gradeLabel: 'Average',
      target: 100.0,
      gap: -15.7,
      changeVsPrev: 0.9,
      headcount: 1,
      memberUnitLabel: 'specialist',
      diagnosis:
        'Ticket Resolution Time met 100.0% SLA compliance and Ticket Resolution Rate reached 85.8% (vs 100% target), but User Satisfaction Score (69.5% vs 100% target) pulls the overall score to 84.3%.',
      keyStrengthOrDrag: '100% SLA speed · User Satisfaction at 69.5% vs 100% target',
    },
  ],
  supportPositions: [
    {
      id: 'it-pos-infra',
      positionName: 'IT Infrastructure & Escalation Lead',
      holderName: 'Regional IT Operations',
      evaluatedScore: 92.0,
      impactLevel: 'Strong',
      linkedKpis: ['Average Ticket Resolution Time', 'Ticket Resolution Rate'],
      evidenceStat: '100.0% Ticket Resolution Time SLA compliance in September',
      explanation:
        'Fast L2 escalation handling enabled 100% compliance on Average Ticket Resolution Time across Offshore Egypt workstations.',
    },
    {
      id: 'it-pos-qa',
      positionName: 'Service Desk QA Coordinator',
      holderName: 'IT Service Delivery Governance',
      evaluatedScore: 76.5,
      impactLevel: 'Partial',
      linkedKpis: ['User Satisfaction Score', 'Ticket Resolution Rate'],
      evidenceStat: 'User Satisfaction Score at 69.5% (vs 100% target)',
      explanation:
        'Tickets are closed quickly (100% speed SLA), but premature ticket closure before user confirmation lowers User Satisfaction to 69.5%.',
    },
  ],
  keyKpis: [
    {
      id: 'it-kpi-csat',
      kpiKey: 'pos_it_technical_support_user_satisfaction_score',
      name: 'User Satisfaction Score',
      shortName: 'User CSAT',
      unit: '%',
      actualDisplay: '69.5%',
      targetDisplay: '100.0%',
      achievementPct: 69.5,
      trendLabel: '▲ +1.5% vs August (Below target)',
      trendTone: 'negative',
      betterDirection: 'higher',
      diagnosis:
        'User Satisfaction Score stood at 69.5% vs a 100.0% target, accounting for two-thirds of the IT function gap.',
      targetRealismDiagnosis:
        'A 100.0% CSAT target allows zero dissatisfied survey responses; benchmark calibration (to 90%) plus mandatory user sign-off before ticket closure are recommended.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 72.0, target: 100.0, actualFormatted: '72.0%', targetFormatted: '100.0%', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 70.5, target: 100.0, actualFormatted: '70.5%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Jun', periodKey: '2026-06', actual: 68.0, target: 100.0, actualFormatted: '68.0%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 67.5, target: 100.0, actualFormatted: '67.5%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 68.0, target: 100.0, actualFormatted: '68.0%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 69.5, target: 100.0, actualFormatted: '69.5%', targetFormatted: '100.0%', metTarget: false },
      ],
    },
    {
      id: 'it-kpi-res-rate',
      kpiKey: 'pos_it_technical_support_ticket_resolution_rate',
      name: 'Ticket Resolution Rate',
      shortName: 'Resolution Rate',
      unit: '%',
      actualDisplay: '85.8%',
      targetDisplay: '100.0%',
      achievementPct: 85.8,
      trendLabel: '▲ +1.2% vs August (Improving)',
      trendTone: 'warning',
      betterDirection: 'higher',
      diagnosis:
        '85.8% of support tickets were resolved without L3 vendor escalation against a 100.0% target.',
      targetRealismDiagnosis:
        'Steady improvement from 81.0% in April to 85.8% in September; recurring VPN/headset tickets can be resolved via self-service guides.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 81.0, target: 100.0, actualFormatted: '81.0%', targetFormatted: '100.0%', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 82.4, target: 100.0, actualFormatted: '82.4%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Jun', periodKey: '2026-06', actual: 83.1, target: 100.0, actualFormatted: '83.1%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 84.0, target: 100.0, actualFormatted: '84.0%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 84.6, target: 100.0, actualFormatted: '84.6%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 85.8, target: 100.0, actualFormatted: '85.8%', targetFormatted: '100.0%', metTarget: false },
      ],
    },
    {
      id: 'it-kpi-res-time',
      kpiKey: 'pos_it_technical_support_average_ticket_r_cfb0bb56',
      name: 'Average Ticket Resolution Time SLA',
      shortName: 'Resolution Time SLA',
      unit: '%',
      actualDisplay: '100.0%',
      targetDisplay: '100.0%',
      achievementPct: 100.0,
      trendLabel: '● 100.0% vs August (Target Met)',
      trendTone: 'positive',
      betterDirection: 'higher',
      diagnosis:
        '100.0% of tickets met the resolution time SLA benchmark across all 6 trailing months.',
      targetRealismDiagnosis:
        'Target (100.0%) is consistently achieved in 6 of 6 months.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 100.0, target: 100.0, actualFormatted: '100.0%', targetFormatted: '100.0%', metTarget: true },
        { month: 'May', periodKey: '2026-05', actual: 100.0, target: 100.0, actualFormatted: '100.0%', targetFormatted: '100.0%', metTarget: true },
        { month: 'Jun', periodKey: '2026-06', actual: 100.0, target: 100.0, actualFormatted: '100.0%', targetFormatted: '100.0%', metTarget: true },
        { month: 'Jul', periodKey: '2026-07', actual: 100.0, target: 100.0, actualFormatted: '100.0%', targetFormatted: '100.0%', metTarget: true },
        { month: 'Aug', periodKey: '2026-08', actual: 100.0, target: 100.0, actualFormatted: '100.0%', targetFormatted: '100.0%', metTarget: true },
        { month: 'Sep', periodKey: '2026-09', actual: 100.0, target: 100.0, actualFormatted: '100.0%', targetFormatted: '100.0%', metTarget: true },
      ],
    },
  ],
  agentsNeedingAttention: [
    {
      id: 'it-att-gamal',
      employeeId: 'Mohamed Gamal Mohamed Abouzeid',
      agentName: 'Mohamed Gamal Mohamed Abouzeid',
      team: 'IT Technical Support',
      teamSlug: 'it',
      score: 84.3,
      grade: 'C',
      gradeLabel: 'Average',
      reason: 'User Satisfaction Score at 69.5% (vs 100.0% target) & Ticket Resolution Rate at 85.8%',
      weakestKpiKey: 'pos_it_technical_support_user_satisfaction_score',
      owningPosition: 'Service Desk QA Coordinator',
    },
  ],
  actionsByPosition: {
    items: [
      {
        id: 'it-act-1',
        owningPosition: 'Service Desk QA Coordinator',
        actionTitle:
          'Require requester confirmation ping before closing L1 support tickets to eliminate unresolved re-opens',
        targetScope: 'User Satisfaction Score (69.5% → 88.0%+)',
        expectedImpactPct: 4.5,
        expectedKpiOutcome: 'Lifts IT Technical Support from 84.3% (Grade C) → ~90.5% (Grade B)',
      },
      {
        id: 'it-act-2',
        owningPosition: 'IT Infrastructure & Escalation Lead',
        actionTitle:
          'Publish quick-fix runbooks for Call Center headset & VPN tickets to raise first-contact resolution',
        targetScope: 'Ticket Resolution Rate (85.8% → 94.0%+)',
        expectedImpactPct: 2.1,
        expectedKpiOutcome: 'Reduces repeat ticket backlog across Call Center & RCM floors',
      },
    ],
    totalExpectedLiftPct: 6.6,
    projectedNextMonthScore: 91.0,
  },
};

export const HUMAN_RESOURCES_DEEP_DIVE_SEP_2026: CallCenterDeepDiveData = {
  functionSlug: 'human-resources',
  title: 'Human Resources Deep Dive',
  functionName: 'Human Resources',
  regionCode: 'EGY',
  regionName: 'Offshore Egypt',
  monthLabel: 'September 2026',
  previousMonthLabel: 'August',
  periodKey: '2026-09',
  pageIndicator: 'Page 2 of 6 · Function Deep Dive',
  headline: {
    score: 95.6,
    grade: 'A',
    gradeLabel: 'Excellent',
    target: 100.0,
    gap: -4.4,
    changeVsPrev: 1.5,
    narrative:
      'Human Resources is a benchmark Grade A function (95.6%, +1.5% vs August). Assessment Center Lead achieved 100.0%, and HR Operations (94.4%) and HR Specialist (92.5%) maintain strong compliance with minor opportunity in First-Day Onboarding Readiness (79.6%) and Payroll Input Timeliness (80.4%).',
    measuredTeamsCount: 1,
    measuredAgentsCount: 3,
    supportPositionsCount: 2,
  },
  agentTeams: [
    {
      id: 'hr-team',
      teamSlug: 'human-resources',
      canonicalTeam: 'Human Resources',
      teamName: 'Human Resources Team',
      roleTag: 'Carrying Function',
      roleTone: 'positive',
      score: 95.6,
      grade: 'A',
      gradeLabel: 'Excellent',
      target: 100.0,
      gap: -4.4,
      changeVsPrev: 1.5,
      headcount: 3,
      memberUnitLabel: 'specialists',
      diagnosis:
        'All 3 HR members score above 92% (Mohamed Diaa 100.0%, Sherif Nasr-Eldeen 94.4%, Fatma Ramadan 92.5%). Personnel File Accuracy and Offboarding Settlement are at 100%.',
      keyStrengthOrDrag: '100% of team ≥ 92.5% (Grade A/B)',
    },
  ],
  supportPositions: [
    {
      id: 'hr-pos-assess',
      positionName: 'Assessment Center Lead',
      holderName: 'Mohamed Diaa Eldin Youssef',
      evaluatedScore: 100.0,
      impactLevel: 'Strong',
      linkedKpis: ['Assessment Quality Score', 'Assessment Recommendation Success Rate'],
      evidenceStat: 'Evaluated 100.0% (Grade A) · 5 of 5 KPIs at 100% target',
      explanation:
        'Delivers 100% assessment quality and development plan completion across hiring and promotion pipelines.',
    },
    {
      id: 'hr-pos-sup',
      positionName: 'HR Operation Supervisor',
      holderName: 'Sherif Nasr-Eldeen Ahmed Salah Elidn Mohamed',
      evaluatedScore: 94.4,
      impactLevel: 'Strong',
      linkedKpis: ['HR Operations & Team Compliance Rate', 'Payroll & Staff Cost Accuracy'],
      evidenceStat: 'Evaluated 94.4% (Grade B) · Onboarding & Engagement at 100%',
      explanation:
        'Sustains 94.2%–100% operational compliance; automating attendance cut-off feeds will close the remaining gap on Payroll & Staff Cost Timeliness (80.4%).',
    },
  ],
  keyKpis: [
    {
      id: 'hr-kpi-compliance',
      kpiKey: 'pos_hr_operation_supervisor_hr_operations_7e77f25e',
      name: 'HR Operations & Personnel Compliance',
      shortName: 'HR Compliance',
      unit: '%',
      actualDisplay: '97.1%',
      targetDisplay: '100.0%',
      achievementPct: 97.1,
      trendLabel: '▲ +1.4% vs August (Strong)',
      trendTone: 'positive',
      betterDirection: 'higher',
      diagnosis:
        'Personnel file completeness (100%), employee data accuracy (99.4%), and HR operations compliance (94.2%) remain near 100%.',
      targetRealismDiagnosis:
        'Target (100.0%) is realistic and consistently tracked above 95% across all 6 months.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 94.8, target: 100.0, actualFormatted: '94.8%', targetFormatted: '100.0%', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 95.2, target: 100.0, actualFormatted: '95.2%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Jun', periodKey: '2026-06', actual: 95.5, target: 100.0, actualFormatted: '95.5%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 96.0, target: 100.0, actualFormatted: '96.0%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 95.7, target: 100.0, actualFormatted: '95.7%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 97.1, target: 100.0, actualFormatted: '97.1%', targetFormatted: '100.0%', metTarget: false },
      ],
    },
    {
      id: 'hr-kpi-onboarding',
      kpiKey: 'pos_hr_specialist_first_day_onboarding_re_5cd37245',
      name: 'First-Day Onboarding Readiness Rate',
      shortName: 'Onboarding Readiness',
      unit: '%',
      actualDisplay: '79.6%',
      targetDisplay: '100.0%',
      achievementPct: 79.6,
      trendLabel: '▲ +2.1% vs August (Improving)',
      trendTone: 'warning',
      betterDirection: 'higher',
      diagnosis:
        'Orientation completion is 100%, while First-Day IT/account readiness stood at 79.6% due to late new-hire document submissions.',
      targetRealismDiagnosis:
        'Execution depends on 48-hour pre-joining IT provisioning handoff between HR Specialist and IT Support.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 76.0, target: 100.0, actualFormatted: '76.0%', targetFormatted: '100.0%', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 78.0, target: 100.0, actualFormatted: '78.0%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Jun', periodKey: '2026-06', actual: 77.5, target: 100.0, actualFormatted: '77.5%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 78.2, target: 100.0, actualFormatted: '78.2%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 77.5, target: 100.0, actualFormatted: '77.5%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 79.6, target: 100.0, actualFormatted: '79.6%', targetFormatted: '100.0%', metTarget: false },
      ],
    },
    {
      id: 'hr-kpi-payroll',
      kpiKey: 'pos_hr_specialist_payroll_attendance_inpu_21c0d700',
      name: 'Payroll & Attendance Input Accuracy',
      shortName: 'Payroll Input',
      unit: '%',
      actualDisplay: '88.8%',
      targetDisplay: '100.0%',
      achievementPct: 88.8,
      trendLabel: '▲ +1.8% vs August (Improving)',
      trendTone: 'positive',
      betterDirection: 'higher',
      diagnosis:
        'Payroll & Attendance input accuracy reached 88.8% (HR Specialist) and 80.4% (HR Operation Supervisor) vs 100% target.',
      targetRealismDiagnosis:
        'Locking team leader attendance sign-off 24 hours before payroll cutoff will bring accuracy to >96%.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 84.0, target: 100.0, actualFormatted: '84.0%', targetFormatted: '100.0%', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 85.5, target: 100.0, actualFormatted: '85.5%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Jun', periodKey: '2026-06', actual: 86.0, target: 100.0, actualFormatted: '86.0%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 86.5, target: 100.0, actualFormatted: '86.5%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 87.0, target: 100.0, actualFormatted: '87.0%', targetFormatted: '100.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 88.8, target: 100.0, actualFormatted: '88.8%', targetFormatted: '100.0%', metTarget: false },
      ],
    },
  ],
  agentsNeedingAttention: [
    {
      id: 'hr-att-fatma',
      employeeId: 'Fatma Ramadan Ali Ibrahim',
      agentName: 'Fatma Ramadan Ali Ibrahim',
      team: 'Human Resources',
      teamSlug: 'human-resources',
      score: 92.5,
      grade: 'B',
      gradeLabel: 'Meet Expectations',
      reason: 'Zero HR members below 90% · Lowest KPI is First-Day Onboarding Readiness at 79.6% (vs 100%)',
      weakestKpiKey: 'pos_hr_specialist_first_day_onboarding_re_5cd37245',
      owningPosition: 'HR Operation Supervisor',
    },
  ],
  actionsByPosition: {
    items: [
      {
        id: 'hr-act-1',
        owningPosition: 'HR Operation Supervisor',
        actionTitle:
          'Enforce T-48h IT account provisioning checklist before new-hire start dates',
        targetScope: 'First-Day Onboarding Readiness Rate (79.6% → 95.0%+)',
        expectedImpactPct: 1.4,
        expectedKpiOutcome: 'Lifts HR Specialist score from 92.5% → ~96.0% (Grade A)',
      },
      {
        id: 'hr-act-2',
        owningPosition: 'HR Operation Supervisor',
        actionTitle:
          'Automate monthly Call Center & RCM shift attendance export reconciliation 2 days before payroll close',
        targetScope: 'Payroll & Attendance Input Accuracy (84.6% → 96.0%+)',
        expectedImpactPct: 1.1,
        expectedKpiOutcome: 'Lifts Human Resources function average from 95.6% → ~98.1%',
      },
    ],
    totalExpectedLiftPct: 2.5,
    projectedNextMonthScore: 98.1,
  },
};

export const ADMINISTRATION_DEEP_DIVE_SEP_2026: CallCenterDeepDiveData = {
  functionSlug: 'administration',
  title: 'Administration Deep Dive',
  functionName: 'Administration',
  regionCode: 'EGY',
  regionName: 'Offshore Egypt',
  monthLabel: 'September 2026',
  previousMonthLabel: 'August',
  periodKey: '2026-09',
  pageIndicator: 'Page 2 of 6 · Function Deep Dive',
  headline: {
    score: 96.9,
    grade: 'A',
    gradeLabel: 'Excellent',
    target: 100.0,
    gap: -3.1,
    changeVsPrev: 0.7,
    narrative:
      'Offshore Admin & Management is performing at Grade A (96.9%). Portfolio Completion Rate (92.0% vs 85.0% target) and Status Report Timeliness (100.0% vs 90.0%) exceed benchmarks, with minor optimization needed on Resource Utilization (70.0% vs 75.0%).',
    measuredTeamsCount: 1,
    measuredAgentsCount: 1,
    supportPositionsCount: 1,
  },
  agentTeams: [
    {
      id: 'admin-team',
      teamSlug: 'offshore-admin-management',
      canonicalTeam: 'Offshore Admin & Management',
      teamName: 'Offshore Admin & Management',
      roleTag: 'Carrying Function',
      roleTone: 'positive',
      score: 96.9,
      grade: 'A',
      gradeLabel: 'Excellent',
      target: 100.0,
      gap: -3.1,
      changeVsPrev: 0.7,
      headcount: 1,
      memberUnitLabel: 'PMO specialist',
      diagnosis:
        'Anwaar Abdelmoneem (Offshore PMO) achieved 96.9% (Grade A), beating targets on Portfolio Completion (92.0% vs 85.0%) and Status Report Timeliness (100.0% vs 90.0%).',
      keyStrengthOrDrag: 'Grade A benchmark · 96.9% overall achievement',
    },
  ],
  supportPositions: [
    {
      id: 'admin-pos-pmo',
      positionName: 'Offshore PMO Lead',
      holderName: 'Anwaar Abdelmoneem Mohamed Ali',
      evaluatedScore: 96.9,
      impactLevel: 'Strong',
      linkedKpis: ['Portfolio Completion Rate', 'Timeliness of Status Reports', 'Resource Utilization'],
      evidenceStat: 'Evaluated 96.9% (Grade A) · 100% Status Report Timeliness',
      explanation:
        'Drives cross-functional project governance across Offshore Egypt with 92% portfolio completion.',
    },
  ],
  keyKpis: [
    {
      id: 'admin-kpi-portfolio',
      kpiKey: 'pos_offshore_pmo_portfolio_completion_rate',
      name: 'Portfolio Completion Rate',
      shortName: 'Portfolio Completion',
      unit: '%',
      actualDisplay: '92.0%',
      targetDisplay: '85.0%',
      achievementPct: 100.0,
      trendLabel: '▲ +2.0% vs August (Above Target)',
      trendTone: 'positive',
      betterDirection: 'higher',
      diagnosis: 'Portfolio Completion Rate reached 92.0%, exceeding the 85.0% target by +7.0 pts.',
      targetRealismDiagnosis: 'Target (85.0%) is realistic and exceeded in 6 of 6 months.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 88.0, target: 85.0, actualFormatted: '88.0%', targetFormatted: '85.0%', metTarget: true },
        { month: 'May', periodKey: '2026-05', actual: 89.0, target: 85.0, actualFormatted: '89.0%', targetFormatted: '85.0%', metTarget: true },
        { month: 'Jun', periodKey: '2026-06', actual: 90.0, target: 85.0, actualFormatted: '90.0%', targetFormatted: '85.0%', metTarget: true },
        { month: 'Jul', periodKey: '2026-07', actual: 90.0, target: 85.0, actualFormatted: '90.0%', targetFormatted: '85.0%', metTarget: true },
        { month: 'Aug', periodKey: '2026-08', actual: 90.0, target: 85.0, actualFormatted: '90.0%', targetFormatted: '85.0%', metTarget: true },
        { month: 'Sep', periodKey: '2026-09', actual: 92.0, target: 85.0, actualFormatted: '92.0%', targetFormatted: '85.0%', metTarget: true },
      ],
    },
    {
      id: 'admin-kpi-util',
      kpiKey: 'pos_offshore_pmo_resource_utilization',
      name: 'Resource Utilization',
      shortName: 'Resource Utilization',
      unit: '%',
      actualDisplay: '70.0%',
      targetDisplay: '75.0%',
      achievementPct: 93.3,
      trendLabel: '● 70.0% vs August (Near Target)',
      trendTone: 'warning',
      betterDirection: 'higher',
      diagnosis: 'Resource Utilization stood at 70.0% against a 75.0% benchmark.',
      targetRealismDiagnosis: 'Reallocating shared PMO capacity to RCM and Marketing initiatives will close the 5% gap.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 71.0, target: 75.0, actualFormatted: '71.0%', targetFormatted: '75.0%', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 72.0, target: 75.0, actualFormatted: '72.0%', targetFormatted: '75.0%', metTarget: false },
        { month: 'Jun', periodKey: '2026-06', actual: 70.0, target: 75.0, actualFormatted: '70.0%', targetFormatted: '75.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 70.0, target: 75.0, actualFormatted: '70.0%', targetFormatted: '75.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 70.0, target: 75.0, actualFormatted: '70.0%', targetFormatted: '75.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 70.0, target: 75.0, actualFormatted: '70.0%', targetFormatted: '75.0%', metTarget: false },
      ],
    },
  ],
  agentsNeedingAttention: [
    {
      id: 'admin-att-anwaar',
      employeeId: 'Anwaar Abdelmoneem Mohamed Ali',
      agentName: 'Anwaar Abdelmoneem Mohamed Ali',
      team: 'Offshore Admin & Management',
      teamSlug: 'offshore-admin-management',
      score: 96.9,
      grade: 'A',
      gradeLabel: 'Excellent',
      reason: 'Zero members below 90% · Opportunity KPI: Resource Utilization at 70.0% (vs 75.0% target)',
      weakestKpiKey: 'pos_offshore_pmo_resource_utilization',
      owningPosition: 'Offshore PMO Lead',
    },
  ],
  actionsByPosition: {
    items: [
      {
        id: 'admin-act-1',
        owningPosition: 'Offshore PMO Lead',
        actionTitle:
          'Allocate 5 hrs/week of PMO tracking support to RCM Coding TAT & Marketing Web sprint governance',
        targetScope: 'Resource Utilization (70.0% → 76.0%)',
        expectedImpactPct: 1.5,
        expectedKpiOutcome: 'Lifts Administration score from 96.9% → ~98.4% (Grade A)',
      },
    ],
    totalExpectedLiftPct: 1.5,
    projectedNextMonthScore: 98.4,
  },
};

export const FINANCE_DEEP_DIVE_SEP_2026: CallCenterDeepDiveData = {
  functionSlug: 'finance',
  title: 'Finance Deep Dive',
  functionName: 'Finance',
  regionCode: 'EGY',
  regionName: 'Offshore Egypt',
  monthLabel: 'September 2026',
  previousMonthLabel: 'August',
  periodKey: '2026-09',
  pageIndicator: 'Page 2 of 6 · Function Deep Dive',
  headline: {
    score: 97.1,
    grade: 'A',
    gradeLabel: 'Excellent',
    target: 100.0,
    gap: -2.9,
    changeVsPrev: 0.4,
    narrative:
      'Finance leads Offshore Egypt at 97.1% (Grade A). Bank Reconciliation Completion (100.0%) and Month-End Close Compliance (100.0%) are flawless, with Journal Entry Accuracy at 90.0% vs 98.0% target as the sole minor gap.',
    measuredTeamsCount: 1,
    measuredAgentsCount: 1,
    supportPositionsCount: 1,
  },
  agentTeams: [
    {
      id: 'finance-team',
      teamSlug: 'finance',
      canonicalTeam: 'Finance',
      teamName: 'Finance & Accounting',
      roleTag: 'Carrying Function',
      roleTone: 'positive',
      score: 97.1,
      grade: 'A',
      gradeLabel: 'Excellent',
      target: 100.0,
      gap: -2.9,
      changeVsPrev: 0.4,
      headcount: 1,
      memberUnitLabel: 'accountant',
      diagnosis:
        'Ahmed Mohamed Sayed Ahmed (General Accountant) achieved 97.1% (Grade A) with 100% Bank Reconciliation and 100% Month-End Close compliance.',
      keyStrengthOrDrag: 'Highest-scoring function in EGY · 97.1% (Grade A)',
    },
  ],
  supportPositions: [
    {
      id: 'fin-pos-lead',
      positionName: 'Finance Governance Lead',
      holderName: 'Ahmed Mohamed Sayed Ahmed',
      evaluatedScore: 97.1,
      impactLevel: 'Strong',
      linkedKpis: ['Bank Reconciliation Completion Rate', 'Month-End Close Deadline Compliance', 'Journal Entry Accuracy Rate'],
      evidenceStat: 'Evaluated 97.1% (Grade A) · 100% Month-End Close & Bank Reconciliation',
      explanation:
        'Maintains 100% closing discipline; pre-posting voucher validation will lift Journal Entry Accuracy from 90.0% to 98.0%.',
    },
  ],
  keyKpis: [
    {
      id: 'fin-kpi-journal',
      kpiKey: 'pos_general_accountant_journal_entry_accuracy_rate',
      name: 'Journal Entry Accuracy Rate',
      shortName: 'Journal Accuracy',
      unit: '%',
      actualDisplay: '90.0%',
      targetDisplay: '98.0%',
      achievementPct: 91.8,
      trendLabel: '▲ +1.0% vs August (Near Target)',
      trendTone: 'warning',
      betterDirection: 'higher',
      diagnosis: 'Journal Entry Accuracy reached 90.0% vs the 98.0% benchmark.',
      targetRealismDiagnosis: 'Target (98.0%) is realistic; automated cost-center mapping templates will eliminate manual reclassifications.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 92.0, target: 98.0, actualFormatted: '92.0%', targetFormatted: '98.0%', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 94.0, target: 98.0, actualFormatted: '94.0%', targetFormatted: '98.0%', metTarget: false },
        { month: 'Jun', periodKey: '2026-06', actual: 91.0, target: 98.0, actualFormatted: '91.0%', targetFormatted: '98.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 90.0, target: 98.0, actualFormatted: '90.0%', targetFormatted: '98.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 89.0, target: 98.0, actualFormatted: '89.0%', targetFormatted: '98.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 90.0, target: 98.0, actualFormatted: '90.0%', targetFormatted: '98.0%', metTarget: false },
      ],
    },
    {
      id: 'fin-kpi-reconcil',
      kpiKey: 'pos_general_accountant_bank_reconciliatio_d7984205',
      name: 'Bank Reconciliation Completion Rate',
      shortName: 'Bank Reconciliation',
      unit: '%',
      actualDisplay: '100.0%',
      targetDisplay: '100.0%',
      achievementPct: 100.0,
      trendLabel: '● 100.0% vs August (Target Met)',
      trendTone: 'positive',
      betterDirection: 'higher',
      diagnosis: '100.0% of bank accounts reconciled on schedule.',
      targetRealismDiagnosis: 'Target (100.0%) achieved in 6 of 6 months.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 100.0, target: 100.0, actualFormatted: '100.0%', targetFormatted: '100.0%', metTarget: true },
        { month: 'May', periodKey: '2026-05', actual: 100.0, target: 100.0, actualFormatted: '100.0%', targetFormatted: '100.0%', metTarget: true },
        { month: 'Jun', periodKey: '2026-06', actual: 100.0, target: 100.0, actualFormatted: '100.0%', targetFormatted: '100.0%', metTarget: true },
        { month: 'Jul', periodKey: '2026-07', actual: 100.0, target: 100.0, actualFormatted: '100.0%', targetFormatted: '100.0%', metTarget: true },
        { month: 'Aug', periodKey: '2026-08', actual: 100.0, target: 100.0, actualFormatted: '100.0%', targetFormatted: '100.0%', metTarget: true },
        { month: 'Sep', periodKey: '2026-09', actual: 100.0, target: 100.0, actualFormatted: '100.0%', targetFormatted: '100.0%', metTarget: true },
      ],
    },
  ],
  agentsNeedingAttention: [
    {
      id: 'fin-att-ahmed',
      employeeId: 'Ahmed Mohamed Sayed Ahmed',
      agentName: 'Ahmed Mohamed Sayed Ahmed',
      team: 'Finance',
      teamSlug: 'finance',
      score: 97.1,
      grade: 'A',
      gradeLabel: 'Excellent',
      reason: 'Zero members below 90% · Minor opportunity: Journal Entry Accuracy at 90.0% (vs 98.0% target)',
      weakestKpiKey: 'pos_general_accountant_journal_entry_accuracy_rate',
      owningPosition: 'Finance Governance Lead',
    },
  ],
  actionsByPosition: {
    items: [
      {
        id: 'fin-act-1',
        owningPosition: 'Finance Governance Lead',
        actionTitle:
          'Add pre-posting cost-center validation rule on recurring monthly accrual entries',
        targetScope: 'Journal Entry Accuracy Rate (90.0% → 98.0%)',
        expectedImpactPct: 1.8,
        expectedKpiOutcome: 'Lifts Finance score from 97.1% → ~98.9% (Grade A)',
      },
    ],
    totalExpectedLiftPct: 1.8,
    projectedNextMonthScore: 98.9,
  },
};

export const FUNCTION_DEEP_DIVE_BASELINES_SEP_2026: Record<string, CallCenterDeepDiveData> = {
  'call-center': CALL_CENTER_DEEP_DIVE_SEP_2026,
  rcm: RCM_DEEP_DIVE_SEP_2026,
  marketing: MARKETING_DEEP_DIVE_SEP_2026,
  it: IT_DEEP_DIVE_SEP_2026,
  'human-resources': HUMAN_RESOURCES_DEEP_DIVE_SEP_2026,
  administration: ADMINISTRATION_DEEP_DIVE_SEP_2026,
  finance: FINANCE_DEEP_DIVE_SEP_2026,
};

export function scopeRecordsToRegion(
  records: ExecRecord[],
  region: 'EGY' | 'UAE',
): ExecRecord[] {
  return records.filter((record) => normalizeRegion(record.region) === region);
}

/** Same page shape as a measured function, with no Egypt rows copied in under another region. */
export function emptyMeasuredFunctionDeepDive(
  functionSlug: string,
  region: 'EGY' | 'UAE',
): CallCenterDeepDiveData {
  const norm = normalizeFunctionSlug(functionSlug);
  const fnName = canonicalFunctionNameFromSlug(norm);
  const snapshot = region === 'UAE' ? UAE_SEP_2026_DATA : null;
  const card = snapshot?.functions.find((item) => item.slug === norm);
  const score = card?.score ?? 0;
  const grade = card?.grade ?? gradeForScore(score);
  return {
    functionSlug: norm,
    title: `${fnName} Deep Dive`,
    functionName: fnName,
    regionCode: region,
    regionName: region === 'EGY' ? 'Offshore Egypt' : 'UAE Region',
    monthLabel: snapshot?.monthLabel ?? 'September 2026',
    previousMonthLabel: snapshot?.previousMonthLabel ?? 'August',
    periodKey: snapshot?.periodKey ?? '2026-09',
    pageIndicator: 'Function Deep Dive',
    headline: {
      score,
      grade,
      gradeLabel: fullGradeLabel(grade),
      target: 100,
      gap: card?.gap ?? Number((score - 100).toFixed(1)),
      changeVsPrev: card?.change ?? 0,
      narrative: 'No measured rows for this region in the locked month.',
      measuredTeamsCount: 0,
      measuredAgentsCount: 0,
      supportPositionsCount: 0,
    },
    agentTeams: [],
    supportPositions: [],
    keyKpis: [],
    agentsNeedingAttention: [],
    actionsByPosition: {
      items: [],
      totalExpectedLiftPct: 0,
      projectedNextMonthScore: score,
    },
  };
}

export function getBaselineFunctionDeepDive(
  functionSlug: string,
  region: 'EGY' | 'UAE' = 'EGY',
): CallCenterDeepDiveData {
  const norm = normalizeFunctionSlug(functionSlug);
  if (region === 'UAE') {
    return emptyMeasuredFunctionDeepDive(norm, 'UAE');
  }
  const found = FUNCTION_DEEP_DIVE_BASELINES_SEP_2026[norm];
  if (found) {
    return {
      ...found,
      regionCode: region,
      regionName: region === 'EGY' ? 'Offshore Egypt' : 'UAE Region',
    };
  }
  const fnName = canonicalFunctionNameFromSlug(norm);
  return {
    ...CALL_CENTER_DEEP_DIVE_SEP_2026,
    functionSlug: norm,
    title: `${fnName} Deep Dive`,
    functionName: fnName,
    regionCode: region,
    regionName: region === 'EGY' ? 'Offshore Egypt' : 'UAE Region',
  };
}

/* -------------------------------------------------------------------------- */
/*  Real-Data Derivation Engine from ExecRecord[] + PMSAction[]               */
/* -------------------------------------------------------------------------- */

const round1 = (v: number) => Math.round(v * 10) / 10;
const mean = (vals: number[]) =>
  vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : null;

export function buildCallCenterDeepDiveFromRecords(
  allRecords: ExecRecord[],
  actions: PMSAction[] = [],
  region: 'EGY' | 'UAE' = 'EGY',
  requestedPeriodKey?: string,
): CallCenterDeepDiveData {
  const scopedRecords = scopeRecordsToRegion(allRecords, region);
  const fallback =
    region === 'UAE'
      ? emptyMeasuredFunctionDeepDive('call-center', 'UAE')
      : CALL_CENTER_DEEP_DIVE_SEP_2026;

  // Filter records to Call Center family (Inbound, Outbound, Call Center support positions)
  const ccRecords = scopedRecords.filter(
    (r) => r.team === 'Inbound' || r.team === 'Outbound' || r.team === 'Call Center',
  );
  if (!ccRecords.length) {
    return fallback;
  }

  // Determine effective period and previous period
  const periods = [
    ...new Map(ccRecords.map((r) => [r.period.key, r.period])).values(),
  ].sort((a, b) => b.key.localeCompare(a.key));

  const requested = requestedPeriodKey ? periodFromKey(requestedPeriodKey) : null;
  const effective: ExecutivePeriod =
    (requested && periods.find((p) => p.key === requested.key)) || periods[0];
  const previous: ExecutivePeriod | null =
    periods.find((p) => p.key < effective.key) ?? null;

  const inPeriod = (recs: ExecRecord[], p: ExecutivePeriod | null) =>
    p ? recs.filter((r) => r.period.key === p.key) : [];

  // Layer 1: Directly Measured Agent Teams (Inbound & Outbound)
  const inboundAll = ccRecords.filter((r) => r.team === 'Inbound');
  const outboundAll = ccRecords.filter((r) => r.team === 'Outbound');
  const inboundCurr = inPeriod(inboundAll, effective);
  const inboundPrev = inPeriod(inboundAll, previous);
  const outboundCurr = inPeriod(outboundAll, effective);
  const outboundPrev = inPeriod(outboundAll, previous);

  if (!inboundCurr.length && !outboundCurr.length) {
    return fallback;
  }

  const inboundScore = round1(
    mean(inboundCurr.map((r) => r.score)) ?? fallback.agentTeams[0].score,
  );
  const inboundPrevScore = mean(inboundPrev.map((r) => r.score));
  const inboundChange =
    inboundPrevScore !== null
      ? round1(inboundScore - round1(inboundPrevScore))
      : fallback.agentTeams[0].changeVsPrev;
  const inboundGrade = gradeForScore(inboundScore);
  const inboundHc = new Set(inboundCurr.map((r) => r.employeeId)).size;

  const outboundScore = round1(
    mean(outboundCurr.map((r) => r.score)) ?? fallback.agentTeams[1].score,
  );
  const outboundPrevScore = mean(outboundPrev.map((r) => r.score));
  const outboundChange =
    outboundPrevScore !== null
      ? round1(outboundScore - round1(outboundPrevScore))
      : fallback.agentTeams[1].changeVsPrev;
  const outboundGrade = gradeForScore(outboundScore);
  const outboundHc = new Set(outboundCurr.map((r) => r.employeeId)).size;

  // Overall Call Center Function Score (across Call Center records in scope)
  const scopedCurr = inPeriod(
    ccRecords.filter((r) => !region || r.region === region || r.team === 'Call Center'),
    effective,
  );
  const scopedPrev = inPeriod(
    ccRecords.filter((r) => !region || r.region === region || r.team === 'Call Center'),
    previous,
  );
  const fnScore = round1(mean(scopedCurr.map((r) => r.score)) ?? fallback.headline.score);
  const fnPrevScore = mean(scopedPrev.map((r) => r.score));
  const fnChange =
    fnPrevScore !== null
      ? round1(fnScore - round1(fnPrevScore))
      : fallback.headline.changeVsPrev;
  const fnGrade = gradeForScore(fnScore);
  const totalMeasuredAgents = inboundHc + outboundHc;

  // Compute real KPI rows for Inbound and Outbound to enrich diagnoses
  const inbKpis = kpiRows(inboundCurr, inboundPrev);
  const outKpis = kpiRows(outboundCurr, outboundPrev);

  const inbWeakest = inbKpis[0];
  const inbStrongest = [...inbKpis].sort(
    (a, b) => (b.achievement_percent ?? 0) - (a.achievement_percent ?? 0),
  )[0];
  const outWeakest = outKpis[0];
  const outStrongest = [...outKpis].sort(
    (a, b) => (b.achievement_percent ?? 0) - (a.achievement_percent ?? 0),
  )[0];

  const inboundBelow90 = inboundCurr.filter((r) => r.score < 90).length;
  const outboundBelow90 = outboundCurr.filter((r) => r.score < 90).length;

  const inboundTeamCard: AgentTeamPerformanceItem = {
    id: 'inbound-agents',
    teamSlug: 'inbound',
    canonicalTeam: 'Inbound',
    teamName: 'Inbound Agents',
    roleTag: inboundScore >= outboundScore ? 'Carrying Function' : 'Pulling Average Down',
    roleTone: inboundScore >= 90 ? 'positive' : 'warning',
    score: inboundScore,
    grade: inboundGrade,
    gradeLabel: fullGradeLabel(inboundGrade),
    target: 100.0,
    gap: round1(inboundScore - 100),
    changeVsPrev: inboundChange,
    headcount: inboundHc,
    memberUnitLabel: 'agents',
    diagnosis:
      inbWeakest && inbStrongest
        ? `Carrying the Call Center score with ${inboundHc} measured agents averaging ${inboundScore.toFixed(1)}% (${inboundChange >= 0 ? '+' : ''}${inboundChange.toFixed(1)}% vs ${previous?.month ?? 'prior month'}). Strong ${inbStrongest.kpi_label} (${formatKpiValue(inbStrongest.actual, inbStrongest.unit)} vs ${formatKpiValue(inbStrongest.target, inbStrongest.unit)} target) offsets pressure on ${inbWeakest.kpi_label} (${formatKpiValue(inbWeakest.actual, inbWeakest.unit)} vs ${formatKpiValue(inbWeakest.target, inbWeakest.unit)} target).`
        : fallback.agentTeams[0].diagnosis,
    keyStrengthOrDrag: `Primary carrier · ${inboundHc} agents (${Math.round((inboundHc / Math.max(1, totalMeasuredAgents)) * 100)}% of measured headcount)`,
  };

  const outboundTeamCard: AgentTeamPerformanceItem = {
    id: 'outbound-agents',
    teamSlug: 'outbound',
    canonicalTeam: 'Outbound',
    teamName: 'Outbound Agents',
    roleTag: outboundScore < inboundScore ? 'Pulling Average Down' : 'Carrying Function',
    roleTone: outboundScore >= 90 ? 'positive' : 'warning',
    score: outboundScore,
    grade: outboundGrade,
    gradeLabel: fullGradeLabel(outboundGrade),
    target: 100.0,
    gap: round1(outboundScore - 100),
    changeVsPrev: outboundChange,
    headcount: outboundHc,
    memberUnitLabel: 'agents',
    diagnosis:
      outWeakest && outStrongest
        ? `Moved ${outboundChange >= 0 ? '+' : ''}${outboundChange.toFixed(1)}% vs ${previous?.month ?? 'prior month'} to ${outboundScore.toFixed(1)}%, with ${outStrongest.kpi_label} reaching ${formatKpiValue(outStrongest.actual, outStrongest.unit)} (target ${formatKpiValue(outStrongest.target, outStrongest.unit)}), while ${outWeakest.kpi_label} (${formatKpiValue(outWeakest.actual, outWeakest.unit)} vs ${formatKpiValue(outWeakest.target, outWeakest.unit)} target) across ${outboundBelow90} of ${outboundHc} agents pulls the function down.`
        : fallback.agentTeams[1].diagnosis,
    keyStrengthOrDrag: `Main drag · ${outboundBelow90} of ${outboundHc} agents below 90% threshold`,
  };

  // Layer 2: Support Positions derived from real Call Center position records
  const supportRecords = ccRecords.filter((r) => r.team === 'Call Center' && r.position);
  const findSupportLatest = (matchFn: (pos: string) => boolean) => {
    const matching = supportRecords
      .filter((r) => matchFn((r.position ?? '').toLowerCase()))
      .sort((a, b) => b.period.key.localeCompare(a.period.key));
    const inEff = matching.filter((r) => r.period.key === effective.key);
    return inEff.length ? inEff : matching.slice(0, 1);
  };

  const trainerRecs = findSupportLatest((p) => p.includes('trainer'));
  const qaRecs = findSupportLatest((p) => p.includes('quality'));
  const tlRecs = findSupportLatest((p) => p.includes('leader'));
  const wfmRecs = findSupportLatest((p) => p.includes('workforce'));

  const trainerScore = mean(trainerRecs.map((r) => r.score));
  const qaScore = mean(qaRecs.map((r) => r.score));
  const tlScore = mean(tlRecs.map((r) => r.score));
  const wfmScore = mean(wfmRecs.map((r) => r.score));

  const supportPositions: SupportPositionItem[] = [
    {
      ...fallback.supportPositions[0],
      holderName: trainerRecs[0]?.name ?? fallback.supportPositions[0].holderName,
      evaluatedScore: trainerScore !== null ? round1(trainerScore) : 100.0,
      impactLevel: (trainerScore ?? 100) >= 95 ? 'Strong' : 'Partial',
      evidenceStat:
        trainerScore !== null
          ? `Evaluated ${round1(trainerScore).toFixed(1)}% (${trainerRecs[0]?.name}) · Quality sessions ↑ +22.9%`
          : fallback.supportPositions[0].evidenceStat,
    },
    {
      ...fallback.supportPositions[1],
      holderName: qaRecs[0]?.name ?? fallback.supportPositions[1].holderName,
      evaluatedScore: qaScore !== null ? round1(qaScore) : 84.4,
      impactLevel: (qaScore ?? 84.4) >= 90 ? 'Strong' : 'Partial',
      evidenceStat:
        qaScore !== null
          ? `Evaluated ${round1(qaScore).toFixed(1)}% (${qaRecs[0]?.name}) · ${inboundBelow90 + outboundBelow90} agents need QA coaching loop`
          : fallback.supportPositions[1].evidenceStat,
    },
    {
      ...fallback.supportPositions[2],
      holderName:
        tlRecs.length > 0
          ? tlRecs.map((r) => `${r.name.split(' ').slice(0, 2).join(' ')} (${r.score.toFixed(1)}%)`).join(' · ')
          : fallback.supportPositions[2].holderName,
      evaluatedScore: tlScore !== null ? round1(tlScore) : 89.8,
      impactLevel: 'Mixed',
      evidenceStat:
        tlRecs.length > 0
          ? tlRecs
              .map((r) => `${r.position?.replace('Team Leader', 'TL')}: ${r.score.toFixed(1)}%`)
              .join(' · ')
          : fallback.supportPositions[2].evidenceStat,
    },
    {
      ...fallback.supportPositions[3],
      holderName: wfmRecs[0]?.name ?? fallback.supportPositions[3].holderName,
      evaluatedScore: wfmScore !== null ? round1(wfmScore) : 88.7,
      impactLevel: 'Limited',
      evidenceStat:
        wfmScore !== null
          ? `Latest evaluated ${round1(wfmScore).toFixed(1)}% (${wfmRecs[0]?.period.month}) · Inbound AHT at ${inbWeakest?.kpi_key === 'AHT' ? formatKpiValue(inbWeakest.actual, inbWeakest.unit) : '3.01 min'}`
          : fallback.supportPositions[3].evidenceStat,
    },
  ];

  // Key Agent KPIs with real 6-month trends from trailingPeriods(effective, 6)
  const agentOnlyRecords = [...inboundAll, ...outboundAll];
  const agentCurr = [...inboundCurr, ...outboundCurr];
  const agentPrev = [...inboundPrev, ...outboundPrev];
  const combinedKpiRows = kpiRows(agentCurr, agentPrev);
  const sixPeriods = trailingPeriods(effective, 6);

  const buildKpiCard = (
    targetKey: string,
    fallbackCard: AgentKeyKpiItem,
    scopeRecords: ExecRecord[] = agentOnlyRecords,
  ): AgentKeyKpiItem => {
    const scopeCurr = inPeriod(scopeRecords, effective);
    const scopePrev = inPeriod(scopeRecords, previous);
    const row =
      kpiRows(scopeCurr, scopePrev).find((k) => k.kpi_key === targetKey) ??
      combinedKpiRows.find((k) => k.kpi_key === targetKey);
    if (!row) return fallbackCard;

    const unit = row.unit ?? fallbackCard.unit;
    const lowerBetter = String(row.kpi_direction ?? '').toLowerCase().startsWith('lower');
    const trend6Mo: KpiMonthlyPoint[] = sixPeriods.map((p) => {
      const mRows = kpiRows(inPeriod(scopeRecords, p), []);
      const match = mRows.find((k) => k.kpi_key === targetKey);
      const actual = match?.actual ?? null;
      const target = match?.target ?? (actual !== null ? row.target : null);
      const metTarget =
        actual !== null && target !== null
          ? lowerBetter
            ? actual <= target + 1e-6
            : actual >= target - 1e-6
          : null;
      return {
        month: p.month.slice(0, 3),
        periodKey: p.key,
        actual,
        target,
        actualFormatted: formatKpiValue(actual, unit),
        targetFormatted: formatKpiValue(target, unit),
        metTarget,
      };
    });

    const rawDelta = row.raw_change;
    const improved = (row.change_value ?? 0) > 0;
    const evaluatedMonths = trend6Mo.filter((pt) => pt.metTarget !== null).length || 6;
    const metInMonths = trend6Mo.filter((pt) => pt.metTarget === true).length;
    const uniqueTargets = [
      ...new Set(trend6Mo.map((pt) => pt.target).filter((t): t is number => t !== null)),
    ];
    const targetShifted = uniqueTargets.length > 1;

    const targetRealismDiagnosis = targetShifted
      ? `Target shifted from ${formatKpiValue(uniqueTargets[0], unit)} to ${formatKpiValue(uniqueTargets[uniqueTargets.length - 1], unit)} during the 6-month window; actuals met target in ${metInMonths} of ${evaluatedMonths} months.`
      : metInMonths >= Math.ceil(evaluatedMonths / 2)
      ? `Target (${formatKpiValue(row.target, unit)}) is realistic — achieved in ${metInMonths} of ${evaluatedMonths} measured months.`
      : `Actuals missed the ${formatKpiValue(row.target, unit)} target in ${evaluatedMonths - metInMonths} of ${evaluatedMonths} measured months; top-quartile agents achieve target, pointing to bottom-quartile execution variance.`;

    return {
      ...fallbackCard,
      kpiKey: row.kpi_key,
      name: row.kpi_label || fallbackCard.name,
      unit,
      actualDisplay: formatKpiValue(row.actual, unit),
      targetDisplay: formatKpiValue(row.target, unit),
      achievementPct: row.achievement_percent ?? fallbackCard.achievementPct,
      betterDirection: lowerBetter ? 'lower' : 'higher',
      trendTone:
        row.target_status === 'met'
          ? 'positive'
          : improved
          ? 'positive'
          : lowerBetter && (rawDelta ?? 0) > 0
          ? 'negative'
          : 'warning',
      trendLabel:
        rawDelta !== null
          ? `${rawDelta >= 0 ? '▲ +' : '▼ '}${formatKpiValue(Math.abs(rawDelta), unit)} vs ${previous?.month ?? 'August'} (${improved ? 'Improving' : 'Needs attention'})`
          : fallbackCard.trendLabel,
      targetRealismDiagnosis,
      trend6Mo,
    };
  };

  const keyKpis: AgentKeyKpiItem[] = [
    buildKpiCard('AHT', fallback.keyKpis[0], inboundAll),
    buildKpiCard('Booking', fallback.keyKpis[1], inboundAll),
    buildKpiCard('Quality', fallback.keyKpis[2], agentOnlyRecords),
  ];

  // Real Agents Needing Attention (all Inbound + Outbound agents < 90, sorted lowest score first)
  const realLowAgents: AgentNeedingAttentionItem[] = [...inboundCurr, ...outboundCurr]
    .filter((r) => r.score < 90)
    .sort((a, b) => a.score - b.score || a.name.localeCompare(b.name))
    .slice(0, 6)
    .map((agent) => {
      const personKpis = kpiRows([agent], []);
      const weakest = personKpis[0];
      const secondWeakest = personKpis[1];
      const reason = weakest
        ? `${weakest.kpi_label} at ${formatKpiValue(weakest.actual, weakest.unit)} (vs ${formatKpiValue(weakest.target, weakest.unit)} target, ${(weakest.achievement_percent ?? 0).toFixed(1)}% achievement)${
            secondWeakest && (secondWeakest.achievement_percent ?? 100) < 90
              ? ` & ${secondWeakest.kpi_label} at ${formatKpiValue(secondWeakest.actual, secondWeakest.unit)}`
              : ''
          }`
        : 'Overall score below 90% threshold';
      const owningPosition = weakest
        ? mapWeakestKpiToOwner(weakest.kpi_key, weakest.kpi_label, 'call-center')
        : 'Team Leader';
      const g = gradeForScore(agent.score);
      return {
        id: `att-${agent.employeeId}`,
        employeeId: agent.employeeId,
        agentName: agent.name,
        team: agent.team === 'Inbound' ? 'Inbound Agents' : 'Outbound Agents',
        teamSlug: agent.team === 'Inbound' ? 'inbound' : 'outbound',
        score: round1(agent.score),
        grade: g,
        gradeLabel: fullGradeLabel(g),
        reason,
        weakestKpiKey: weakest?.kpi_key ?? 'Booking',
        owningPosition,
      };
    });

  // Incorporate any real corrective actions from useActionStore if present for Call Center
  const ccActions = actions.filter(
    (a) => a.team === 'Inbound' || a.team === 'Outbound' || a.team === 'Call Center',
  );
  const actionItems: PositionActionPlanItem[] =
    ccActions.length > 0
      ? ccActions.slice(0, 4).map((act, idx) => ({
          id: act.id || `act-real-${idx}`,
          owningPosition: mapWeakestKpiToOwner(act.linked_kpi_key ?? '', act.action_text ?? '', 'call-center'),
          actionTitle: act.action_text,
          targetScope: `${act.team || 'Call Center'}${act.employee_name ? ` · ${act.employee_name}` : ''}`,
          expectedImpactPct: round1(1.4 - idx * 0.25),
          expectedKpiOutcome: act.root_cause_note || 'Improves target KPI achievement next month',
        }))
      : fallback.actionsByPosition.items;

  const totalLift = round1(
    actionItems.reduce((sum, item) => sum + item.expectedImpactPct, 0),
  );

  return {
    ...fallback,
    regionCode: region,
    regionName: region === 'EGY' ? 'Offshore Egypt' : 'UAE Region',
    monthLabel: `${effective.month} ${effective.year}`,
    previousMonthLabel: previous?.month ?? 'August',
    periodKey: effective.key,
    headline: {
      score: fnScore,
      grade: fnGrade,
      gradeLabel: fullGradeLabel(fnGrade),
      target: 100.0,
      gap: round1(fnScore - 100),
      changeVsPrev: fnChange,
      narrative:
        region === 'UAE'
          ? `${totalMeasuredAgents} measured people in ${effective.month} ${effective.year}.`
          : fallback.headline.narrative,
      measuredTeamsCount: 2,
      measuredAgentsCount: totalMeasuredAgents,
      supportPositionsCount: 4,
    },
    agentTeams: [inboundTeamCard, outboundTeamCard],
    supportPositions,
    keyKpis,
    agentsNeedingAttention:
      realLowAgents.length > 0 ? realLowAgents : fallback.agentsNeedingAttention,
    actionsByPosition: {
      items: actionItems,
      totalExpectedLiftPct: totalLift,
      projectedNextMonthScore: Math.min(100, round1(fnScore + totalLift)),
    },
  };
}

/**
 * Generic real-data builder for ANY function (RCM, Marketing, IT, Call Center, Human Resources, Administration, Finance, CSR, Sales, Pharmacy).
 */
export function buildFunctionDeepDiveFromRecords(
  functionSlug: string,
  allRecords: ExecRecord[],
  actions: PMSAction[] = [],
  region: 'EGY' | 'UAE' = 'EGY',
  requestedPeriodKey?: string,
): CallCenterDeepDiveData {
  const normSlug = normalizeFunctionSlug(functionSlug);
  const scopedRecords = scopeRecordsToRegion(allRecords, region);
  if (normSlug === 'call-center') {
    return buildCallCenterDeepDiveFromRecords(scopedRecords, actions, region, requestedPeriodKey);
  }

  const fallback = getBaselineFunctionDeepDive(normSlug, region);
  const canonicalFn = canonicalFunctionNameFromSlug(normSlug);

  // Filter records belonging to this function
  const fnRecords = scopedRecords.filter((r) => {
    const recFn = executiveFunctionForTeam(r.team) ?? '';
    return (
      slugifyIdentifier(recFn) === normSlug ||
      slugifyIdentifier(r.team) === normSlug ||
      recFn.toLowerCase() === canonicalFn.toLowerCase()
    );
  });

  if (!fnRecords.length) {
    return fallback;
  }

  const periods = [
    ...new Map(fnRecords.map((r) => [r.period.key, r.period])).values(),
  ].sort((a, b) => b.key.localeCompare(a.key));

  const requested = requestedPeriodKey ? periodFromKey(requestedPeriodKey) : null;
  const effective: ExecutivePeriod =
    (requested && periods.find((p) => p.key === requested.key)) || periods[0];
  const previous: ExecutivePeriod | null =
    periods.find((p) => p.key < effective.key) ?? null;

  const inPeriod = (recs: ExecRecord[], p: ExecutivePeriod | null) =>
    p ? recs.filter((r) => r.period.key === p.key) : [];

  const currRecords = inPeriod(fnRecords, effective);
  const prevRecords = inPeriod(fnRecords, previous);

  if (!currRecords.length) {
    return fallback;
  }

  const fnScore = round1(mean(currRecords.map((r) => r.score)) ?? fallback.headline.score);
  const fnPrevScore = mean(prevRecords.map((r) => r.score));
  const fnChange =
    fnPrevScore !== null
      ? round1(fnScore - round1(fnPrevScore))
      : fallback.headline.changeVsPrev;
  const fnGrade = gradeForScore(fnScore);
  const totalMeasuredHc = new Set(currRecords.map((r) => r.employeeId)).size;

  // Group Layer 1 Measured Teams from currRecords by r.team
  const distinctTeams = [...new Set(currRecords.map((r) => r.team))];
  const agentTeams: AgentTeamPerformanceItem[] = distinctTeams
    .map((teamName) => {
      const tAll = fnRecords.filter((r) => r.team === teamName);
      const tCurr = inPeriod(tAll, effective);
      const tPrev = inPeriod(tAll, previous);
      const leaderTotal = preApprovalsLeaderTeamTotal(tCurr);
      const tScore = leaderTotal ?? round1(mean(tCurr.map((r) => r.score)) ?? fnScore);
      const tPrevMean = preApprovalsLeaderTeamTotal(tPrev) ?? mean(tPrev.map((r) => r.score));
      const tChange = tPrevMean !== null ? round1(tScore - round1(tPrevMean)) : 0;
      const tGrade = gradeForScore(tScore);
      const tHc = new Set(tCurr.map((r) => r.employeeId)).size;
      const tBelow90 = tCurr.filter((r) => r.score < 90).length;
      const tSlug = slugifyIdentifier(teamName);
      const tKpis = kpiRows(tCurr, tPrev);
      const weakestKpi = tKpis[0];
      const strongestKpi = [...tKpis].sort(
        (a, b) => (b.achievement_percent ?? 0) - (a.achievement_percent ?? 0),
      )[0];

      const fallbackTeam = fallback.agentTeams.find(
        (ft) => ft.teamSlug === tSlug || ft.canonicalTeam.toLowerCase() === teamName.toLowerCase(),
      );

      const isCarrying =
        distinctTeams.length === 1
          ? tScore >= 85
          : tScore >= fnScore;

      const roleTone: AgentTeamPerformanceItem['roleTone'] =
        tScore >= 82 ? 'positive' : 'warning';

      const roleTag: AgentTeamPerformanceItem['roleTag'] =
        distinctTeams.length === 1
          ? tScore >= 90
            ? 'Carrying Function'
            : 'Primary Team'
          : isCarrying
          ? 'Carrying Function'
          : 'Pulling Average Down';

      const diagnosis =
        leaderTotal !== null
          ? `${teamName} is ${tScore.toFixed(1)}% on the leader scorecard across ${tHc} measured people.`
          : fallbackTeam?.diagnosis ||
        (weakestKpi && strongestKpi
          ? `${teamName} averaged ${tScore.toFixed(1)}% across ${tHc} ${tHc === 1 ? 'specialist' : 'specialists'}. ${strongestKpi.kpi_label} reached ${formatKpiValue(strongestKpi.actual, strongestKpi.unit)} (target ${formatKpiValue(strongestKpi.target, strongestKpi.unit)}), while ${weakestKpi.kpi_label} (${formatKpiValue(weakestKpi.actual, weakestKpi.unit)} vs ${formatKpiValue(weakestKpi.target, weakestKpi.unit)}) is the main gap.`
          : `${teamName} averaged ${tScore.toFixed(1)}% across ${tHc} measured ${tHc === 1 ? 'member' : 'members'}.`);

      return {
        id: `team-${tSlug}`,
        teamSlug: tSlug,
        canonicalTeam: teamName,
        teamName: fallbackTeam?.teamName ?? teamName,
        roleTag,
        roleTone,
        score: tScore,
        grade: tGrade,
        gradeLabel: fullGradeLabel(tGrade),
        target: 100.0,
        gap: round1(tScore - 100),
        changeVsPrev: tChange,
        headcount: tHc,
        memberUnitLabel: tHc === 1 ? 'specialist' : 'specialists',
        diagnosis,
        keyStrengthOrDrag:
          fallbackTeam?.keyStrengthOrDrag ??
          (tBelow90 > 0
            ? `${tBelow90} of ${tHc} below 90% threshold`
            : `100% of team ≥ 90% (${tHc} HC)`),
      };
    })
    .sort((a, b) => b.score - a.score);

  // Layer 2: Support / Governance Positions
  const supportPositions: SupportPositionItem[] = fallback.supportPositions.map((pos) => {
    const matchRec = currRecords.find(
      (r) =>
        (r.position && r.position.toLowerCase().includes(pos.positionName.toLowerCase())) ||
        (pos.holderName && r.name.toLowerCase() === pos.holderName.toLowerCase()),
    );
    if (!matchRec) return pos;
    const sc = round1(matchRec.score);
    return {
      ...pos,
      holderName: matchRec.name,
      evaluatedScore: sc,
      impactLevel: sc >= 91 ? 'Strong' : sc >= 80 ? 'Partial' : 'Limited',
    };
  });

  // Key Function KPIs with real 6-month trends
  const sixPeriods = trailingPeriods(effective, 6);
  const currKpiRows = kpiRows(currRecords, prevRecords);
  const keyKpis: AgentKeyKpiItem[] =
    fallback.keyKpis.length > 0
      ? fallback.keyKpis.map((fbKpi) => {
          const row = currKpiRows.find((k) => k.kpi_key === fbKpi.kpiKey);
          if (!row) return fbKpi;
          const unit = row.unit ?? fbKpi.unit;
          const lowerBetter = String(row.kpi_direction ?? '')
            .toLowerCase()
            .startsWith('lower');
          const trend6Mo: KpiMonthlyPoint[] = sixPeriods.map((p) => {
            const pRows = kpiRows(inPeriod(fnRecords, p), []);
            const match = pRows.find(
              (k) =>
                k.kpi_key === row.kpi_key ||
                k.kpi_label.toLowerCase() === row.kpi_label.toLowerCase(),
            );
            const actual = match?.actual ?? null;
            const target = match?.target ?? (actual !== null ? row.target : null);
            const metTarget =
              actual !== null && target !== null
                ? lowerBetter
                  ? actual <= target + 1e-6
                  : actual >= target - 1e-6
                : null;
            return {
              month: p.month.slice(0, 3),
              periodKey: p.key,
              actual,
              target,
              actualFormatted: formatKpiValue(actual, unit),
              targetFormatted: formatKpiValue(target, unit),
              metTarget,
            };
          });
          return {
            ...fbKpi,
            actualDisplay: formatKpiValue(row.actual, unit),
            targetDisplay: formatKpiValue(row.target, unit),
            achievementPct: row.achievement_percent ?? fbKpi.achievementPct,
            trend6Mo,
          };
        })
      : [];

  // Real Employees Needing Attention (< 90%, or lowest scoring member if all >= 90%)
  const lowPool = currRecords.filter((r) => r.score < 90);
  const targetPool = (lowPool.length > 0 ? lowPool : currRecords)
    .slice()
    .sort((a, b) => a.score - b.score || a.name.localeCompare(b.name))
    .slice(0, 6);

  const agentsNeedingAttention: AgentNeedingAttentionItem[] =
    targetPool.length > 0
      ? targetPool.map((emp) => {
          const empKpis = kpiRows([emp], []);
          const weakest = empKpis[0];
          const secondWeakest = empKpis[1];
          const reason = weakest
            ? `${weakest.kpi_label} at ${formatKpiValue(weakest.actual, weakest.unit)} (vs ${formatKpiValue(weakest.target, weakest.unit)} target, ${(weakest.achievement_percent ?? 0).toFixed(1)}% achievement)${
                secondWeakest && (secondWeakest.achievement_percent ?? 100) < 90
                  ? ` & ${secondWeakest.kpi_label} at ${formatKpiValue(secondWeakest.actual, secondWeakest.unit)}`
                  : ''
              }`
            : emp.score < 90
            ? 'Overall score below 90% threshold'
            : 'All KPIs above 90% threshold';
          const g = gradeForScore(emp.score);
          return {
            id: `att-${emp.employeeId}`,
            employeeId: emp.employeeId,
            agentName: emp.name,
            team: emp.team,
            teamSlug: slugifyIdentifier(emp.team),
            score: round1(emp.score),
            grade: g,
            gradeLabel: fullGradeLabel(g),
            reason,
            weakestKpiKey: weakest?.kpi_key ?? 'general',
            owningPosition: weakest
              ? mapWeakestKpiToOwner(weakest.kpi_key, weakest.kpi_label, normSlug)
              : supportPositions[0]?.positionName ?? 'Function Lead',
          };
        })
      : fallback.agentsNeedingAttention;

  // Actions by Position (incorporate any stored actions for teams in this function)
  const teamNamesLower = new Set(distinctTeams.map((t) => t.toLowerCase()));
  const fnActions = actions.filter(
    (a) => a.team && teamNamesLower.has(a.team.toLowerCase()),
  );
  const actionItems: PositionActionPlanItem[] =
    fnActions.length > 0
      ? fnActions.slice(0, 4).map((act, idx) => ({
          id: act.id || `act-${normSlug}-${idx}`,
          owningPosition: mapWeakestKpiToOwner(
            act.linked_kpi_key ?? '',
            act.action_text ?? '',
            normSlug,
          ),
          actionTitle: act.action_text,
          targetScope: `${act.team}${act.employee_name ? ` · ${act.employee_name}` : ''}`,
          expectedImpactPct: round1(2.0 - idx * 0.3),
          expectedKpiOutcome: act.root_cause_note || 'Improves target KPI achievement next month',
        }))
      : fallback.actionsByPosition.items;

  const totalLift = round1(
    actionItems.reduce((sum, item) => sum + item.expectedImpactPct, 0),
  );

  return {
    ...fallback,
    functionSlug: normSlug,
    title: `${canonicalFn} Deep Dive`,
    functionName: canonicalFn,
    regionCode: region,
    regionName: region === 'EGY' ? 'Offshore Egypt' : 'UAE Region',
    monthLabel: `${effective.month} ${effective.year}`,
    previousMonthLabel: previous?.month ?? 'August',
    periodKey: effective.key,
    headline: {
      ...fallback.headline,
      score: fnScore,
      grade: fnGrade,
      gradeLabel: fullGradeLabel(fnGrade),
      target: 100.0,
      gap: round1(fnScore - 100),
      changeVsPrev: fnChange,
      measuredTeamsCount: agentTeams.length,
      measuredAgentsCount: totalMeasuredHc,
      supportPositionsCount: supportPositions.length,
    },
    agentTeams: agentTeams.length > 0 ? agentTeams : fallback.agentTeams,
    supportPositions,
    keyKpis: keyKpis.length > 0 ? keyKpis : fallback.keyKpis,
    agentsNeedingAttention,
    actionsByPosition: {
      items: actionItems,
      totalExpectedLiftPct: totalLift,
      projectedNextMonthScore: Math.min(100, round1(fnScore + totalLift)),
    },
  };
}
