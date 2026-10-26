import { isHossamRecord, type PMSAction } from '../../types';
import {
  kpiRows,
  periodFromKey,
  trailingPeriods,
  type ExecRecord,
} from '../executive/compose';
import { executiveFunctionForTeam } from '../executive/functions';
import { preApprovalsLeaderTeamTotal } from '../team/teamKpiAggregator';
import type { ExecutivePeriod } from '../executive/types';
import { gradeForScore, type GradeLetter } from './monthlyOverviewData';
import {
  FUNCTION_DEEP_DIVE_BASELINES_SEP_2026,
  formatKpiValue,
  fullGradeLabel,
  getBaselineFunctionDeepDive,
  mapWeakestKpiToOwner,
  scopeRecordsToRegion,
  slugifyIdentifier,
  type AgentKeyKpiItem,
  type CallCenterDeepDiveData,
  type FullGradeLabel,
  type KpiMonthlyPoint,
} from './callCenterDeepDiveData';

export type TeamSlug = string;
export type CallCenterTeamSlug = TeamSlug;

export interface TeamSibling {
  slug: string;
  label: string;
}

export interface TeamKpiItem {
  kpiKey: string;
  label: string;
  shortLabel: string;
  unit: string;
  betterDirection: 'lower' | 'higher';
  actual: number | null;
  target: number | null;
  actualFormatted: string;
  targetFormatted: string;
  achievementPct: number;
  movementFormatted: string;
  movementTone: 'positive' | 'warning' | 'negative';
  agentsMeetingTarget: number;
  totalAgents: number;
  /** Answers: "Is the target unrealistic or is execution the issue?" */
  verdictBadge: 'Execution Issue' | 'Stretched Target + Execution' | 'Target Met';
  explorerDiagnosis: string;
  trend6Mo: KpiMonthlyPoint[];
}

export interface AgentKpiCellValue {
  kpiKey: string;
  label: string;
  actualFormatted: string;
  targetFormatted: string;
  achievementPct: number;
  metTarget: boolean;
}

export interface AgentAverageOrBelowRow {
  employeeId: string;
  agentName: string;
  score: number;
  previousScore: number | null;
  changeVsPrev: number | null;
  grade: GradeLetter;
  /** Full words only: Average, Below Average, Unsatisfactory */
  gradeFullLabel: FullGradeLabel;
  kpiCells: AgentKpiCellValue[];
  mainIssue: string;
  weakestKpiKey: string;
  weakestKpiLabel: string;
}

export interface IndividualActionPlanCard {
  id: string;
  employeeId: string;
  agentName: string;
  score: number;
  grade: GradeLetter;
  /** Full words only: Average, Below Average, Unsatisfactory */
  gradeFullLabel: FullGradeLabel;
  mainIssue: string;
  actionText: string;
  owner: string;
  expectedImpact: string;
  linkedKpiKey: string;
  isSavedToStore?: boolean;
}

export interface TeamLevelActionPlanCard {
  id: string;
  title: string;
  targetKpi: string;
  scopeDescription: string;
  owner: string;
  expectedTeamImpact: string;
  status: 'Open' | 'In Progress' | 'Planned' | 'Completed';
  /** Stored due date when the action has one. Absent values stay unset. */
  dueDate?: string | null;
}

export function teamActionDueLabel(dueDate: string | null | undefined): string {
  const value = dueDate?.trim();
  return value ? value : 'No due date';
}

export interface TeamDeepDiveData {
  teamSlug: string;
  canonicalTeam: string;
  teamDisplayName: string;
  functionName: string;
  functionSlug?: string;
  siblingTeams?: TeamSibling[];
  regionCode: 'EGY' | 'UAE';
  regionName: string;
  monthLabel: string;
  previousMonthLabel: string;
  periodKey: string;
  summary: {
    score: number;
    grade: GradeLetter;
    /** Full words: Excellent, Meet Expectations, Average, Below Average, Unsatisfactory */
    gradeFullLabel: FullGradeLabel;
    target: number;
    gap: number;
    changeVsPrev: number;
    headcount: number;
    averageOrBelowCount: number;
    diagnosis: string;
  };
  kpis: TeamKpiItem[];
  agentsAverageOrBelow: AgentAverageOrBelowRow[];
  individualActionPlans: IndividualActionPlanCard[];
  teamActionPlans: TeamLevelActionPlanCard[];
}

const round1 = (v: number) => Math.round(v * 10) / 10;
const mean = (vals: number[]) =>
  vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : null;

function hasMeasuredValue(value: string): boolean {
  const trimmed = value.trim();
  return trimmed.length > 0 && trimmed !== '—' && trimmed !== '-';
}

function normalizeKpiLabel(value: string | null | undefined): string {
  return String(value ?? '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9%]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function sameMeasuredKpi(left: string | null | undefined, right: string | null | undefined): boolean {
  const a = normalizeKpiLabel(left);
  const b = normalizeKpiLabel(right);
  return a.length > 0 && a === b;
}

function personalKpiForColumn<T extends { kpi_key: string; kpi_label: string }>(
  rows: readonly T[],
  column: { kpiKey: string; label: string; shortLabel?: string },
): T | undefined {
  return (
    rows.find((row) => row.kpi_key === column.kpiKey) ??
    rows.find(
      (row) =>
        normalizeKpiLabel(row.kpi_label) === normalizeKpiLabel(column.label) ||
        normalizeKpiLabel(row.kpi_label) === normalizeKpiLabel(column.shortLabel),
    )
  );
}

function statedMeasurements(text: string): Array<{ label: string; actual: number }> {
  const found: Array<{ label: string; actual: number }> = [];
  const pattern = /([^,;&]+?)\s+(?:exceeded target at|rose to|at)\s+(\d+(?:\.\d+)?)%/gi;
  for (const match of text.matchAll(pattern)) {
    const label = match[1].replace(/^(?:but|and|while)\s+/i, '').trim();
    const actual = Number(match[2]);
    if (!label || !Number.isFinite(actual)) continue;
    found.push({ label, actual });
  }
  return found;
}

function statedActualForColumn(
  column: { label: string; shortLabel: string },
  texts: string[],
): number | null {
  for (const text of texts) {
    for (const item of statedMeasurements(text)) {
      if (sameMeasuredKpi(column.shortLabel, item.label) || sameMeasuredKpi(column.label, item.label)) {
        return item.actual;
      }
    }
  }
  return null;
}

/** Keep a shared KPI recommendation, then cite this agent's own issue so lookalike cards are not interchangeable. */
function citeMainIssue(actionText: string, mainIssue?: string): string {
  const issue = mainIssue?.trim();
  if (!issue) return actionText;
  if (actionText.toLowerCase().includes(issue.toLowerCase())) return actionText;
  return `${actionText} Specific issue: ${issue}.`;
}

export function recommendedActionForKpi(
  kpiKey: string,
  kpiLabel: string,
  team: string,
  actualFormatted: string,
  targetFormatted: string,
  mainIssue?: string,
): { actionText: string; owner: string } {
  const norm = `${kpiKey} ${kpiLabel}`.toLowerCase();
  const measured = hasMeasuredValue(actualFormatted) && hasMeasuredValue(targetFormatted);
  let actionText: string;
  let owner: string;

  if (norm.includes('aht') || norm.includes('handle')) {
    actionText = measured
      ? `Shadow peak-hour calls exceeding 3.50 min, streamline hold/transfer lookup steps, and set daily ${targetFormatted} AHT pacing check-ins (currently ${actualFormatted}).`
      : 'Shadow peak-hour calls, streamline hold and transfer steps, and set daily AHT pacing check-ins.';
    owner = 'Inbound Team Leader & Workforce Analyst';
  } else if (norm.includes('booking')) {
    actionText = measured
      ? `Complete 2 weekly objection-handling and appointment-closing calibration sessions to lift Booking Rate from ${actualFormatted} toward the ${targetFormatted} benchmark.`
      : 'Complete weekly objection-handling and appointment-closing calibration sessions to lift Booking Rate.';
    owner = 'Call Center Trainer';
  } else if (norm.includes('reachability')) {
    actionText = measured
      ? `Shift outbound callback attempts to high-answer evening/morning patient windows and audit unanswered retry intervals (currently ${actualFormatted} vs ${targetFormatted}).`
      : 'Shift outbound callback attempts to high-answer windows and audit unanswered retry intervals.';
    owner = 'Outbound Team Leader';
  } else if (norm.includes('quality')) {
    actionText = measured
      ? `Conduct targeted QA call listening & mandatory script verification review to resolve quality deductions (${actualFormatted} vs ${targetFormatted} target).`
      : 'Conduct targeted QA call listening and a script verification review to resolve quality deductions.';
    owner = 'Quality Specialist';
  } else if (norm.includes('utilization') || norm.includes('utz')) {
    actionText = measured
      ? `Realign wrap-up/AUX code usage and break adherence during high-volume intervals to raise Utilization from ${actualFormatted} to ${targetFormatted}.`
      : 'Realign wrap-up and AUX code usage during high-volume intervals to raise Utilization.';
    owner = 'Workforce Analyst & Team Leader';
  } else {
    actionText = measured
      ? `Enforce shift-start roster adherence and weekly attendance review to close the gap from ${actualFormatted} to the ${targetFormatted} target.`
      : `Enforce shift-start roster adherence and a weekly attendance review for ${team}.`;
    owner = `${team} Team Leader`;
  }

  return { actionText: citeMainIssue(actionText, mainIssue), owner };
}

/* -------------------------------------------------------------------------- */
/*  Real Database Baseline Snapshots (Inbound & Outbound — Sep 2026)          */
/* -------------------------------------------------------------------------- */

export const INBOUND_TEAM_DEEP_DIVE_SEP_2026: TeamDeepDiveData = {
  teamSlug: 'inbound',
  canonicalTeam: 'Inbound',
  teamDisplayName: 'Inbound Agents',
  functionName: 'Call Center',
  regionCode: 'EGY',
  regionName: 'Offshore Egypt',
  monthLabel: 'September 2026',
  previousMonthLabel: 'August',
  periodKey: '2026-09',
  summary: {
    score: 91.5,
    grade: 'B',
    gradeFullLabel: 'Meet Expectations',
    target: 100.0,
    gap: -8.5,
    changeVsPrev: 1.2,
    headcount: 35,
    averageOrBelowCount: 10,
    diagnosis:
      'Inbound Agents carry the Call Center at 91.5% (Meet Expectations), up +1.2% vs August. 25 of 35 agents score ≥ 90%, while 10 Average-grade agents (83.9%–89.9%) are held back by AHT outliers (4.20–5.03 min vs 2.50 min target) and a stretched 65% Booking Rate target.',
  },
  kpis: [
    {
      kpiKey: 'AHT',
      label: 'AHT (Handle Time)',
      shortLabel: 'AHT',
      unit: 'min',
      betterDirection: 'lower',
      actual: 3.01,
      target: 2.5,
      actualFormatted: '3.01 min',
      targetFormatted: '2.50 min',
      achievementPct: 84.4,
      movementFormatted: '▲ +0.28 min vs August',
      movementTone: 'negative',
      agentsMeetingTarget: 19,
      totalAgents: 35,
      verdictBadge: 'Execution Issue',
      explorerDiagnosis:
        'Execution is the primary issue, not the 2.50 min target: the team averaged 2.59 min in April and 19 of 35 Inbound agents currently achieve ≤ 2.65 min. The 3.01 min team average is skewed by 5 outlier agents averaging 4.20–5.03 min.',
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
      kpiKey: 'Booking',
      label: 'Booking Rate',
      shortLabel: 'Booking Rate',
      unit: '%',
      betterDirection: 'higher',
      actual: 60.3,
      target: 65.0,
      actualFormatted: '60.3%',
      targetFormatted: '65.0%',
      achievementPct: 91.6,
      movementFormatted: '▲ +3.8% vs August',
      movementTone: 'positive',
      agentsMeetingTarget: 14,
      totalAgents: 35,
      verdictBadge: 'Stretched Target + Execution',
      explorerDiagnosis:
        'Both target calibration and bottom-quartile execution play a role: the Booking Rate target was raised from 46.0% to 65.0% in June (+19 pts). Actual team conversion rose to a 6-month high of 60.3% in September, with 14 agents meeting 65% while 4 agents below 48% create the remaining gap.',
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
      kpiKey: 'Attendance',
      label: 'Attendance Rate',
      shortLabel: 'Attendance',
      unit: '%',
      betterDirection: 'higher',
      actual: 68.2,
      target: 75.0,
      actualFormatted: '68.2%',
      targetFormatted: '75.0%',
      achievementPct: 90.9,
      movementFormatted: '▲ +0.8% vs August',
      movementTone: 'warning',
      agentsMeetingTarget: 6,
      totalAgents: 35,
      verdictBadge: 'Stretched Target + Execution',
      explorerDiagnosis:
        'Structural gap: Inbound Attendance Rate has stayed within a narrow 67.3%–68.2% band across all 6 months against a 75.0% target, indicating shift-roster shrinkage assumptions should be reviewed alongside floor attendance coaching.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 67.3, target: 75.0, actualFormatted: '67.3%', targetFormatted: '75.0%', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 67.5, target: 75.0, actualFormatted: '67.5%', targetFormatted: '75.0%', metTarget: false },
        { month: 'Jun', periodKey: '2026-06', actual: 67.9, target: 75.0, actualFormatted: '67.9%', targetFormatted: '75.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 68.1, target: 75.0, actualFormatted: '68.1%', targetFormatted: '75.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 67.4, target: 75.0, actualFormatted: '67.4%', targetFormatted: '75.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 68.2, target: 75.0, actualFormatted: '68.2%', targetFormatted: '75.0%', metTarget: false },
      ],
    },
    {
      kpiKey: 'Quality',
      label: 'Quality Score',
      shortLabel: 'Quality Score',
      unit: '%',
      betterDirection: 'higher',
      actual: 95.6,
      target: 95.0,
      actualFormatted: '95.6%',
      targetFormatted: '95.0%',
      achievementPct: 97.1,
      movementFormatted: '▲ +2.4% vs August',
      movementTone: 'positive',
      agentsMeetingTarget: 34,
      totalAgents: 35,
      verdictBadge: 'Target Met',
      explorerDiagnosis:
        'Target (95.0%) is realistic and met: 34 of 35 Inbound agents achieved ≥ 95% Quality Score in September, lifting the team average to 95.6%.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 98.6, target: 95.0, actualFormatted: '98.6%', targetFormatted: '95.0%', metTarget: true },
        { month: 'May', periodKey: '2026-05', actual: 97.7, target: 95.0, actualFormatted: '97.7%', targetFormatted: '95.0%', metTarget: true },
        { month: 'Jun', periodKey: '2026-06', actual: 93.8, target: 95.0, actualFormatted: '93.8%', targetFormatted: '95.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 94.0, target: 95.0, actualFormatted: '94.0%', targetFormatted: '95.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 93.2, target: 95.0, actualFormatted: '93.2%', targetFormatted: '95.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 95.6, target: 95.0, actualFormatted: '95.6%', targetFormatted: '95.0%', metTarget: true },
      ],
    },
  ],
  agentsAverageOrBelow: [
    {
      employeeId: 'Maryam Elsayed Mahmoud Eid',
      agentName: 'Maryam Elsayed Mahmoud Eid',
      score: 83.9,
      previousScore: 86.2,
      changeVsPrev: -2.3,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'AHT',
      weakestKpiLabel: 'AHT (Handle Time)',
      mainIssue: 'AHT at 4.25 min (vs 2.50 min target) & Booking Rate at 40.4% (vs 65.0%)',
      kpiCells: [
        { kpiKey: 'AHT', label: 'AHT', actualFormatted: '4.25 min', targetFormatted: '2.50 min', achievementPct: 58.8, metTarget: false },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '40.4%', targetFormatted: '65.0%', achievementPct: 62.2, metTarget: false },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '64.2%', targetFormatted: '75.0%', achievementPct: 85.7, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '100.0%', targetFormatted: '95.0%', achievementPct: 100.0, metTarget: true },
      ],
    },
    {
      employeeId: 'Abdulrahman Said Sayed Helal',
      agentName: 'Abdulrahman Said Sayed Helal',
      score: 84.9,
      previousScore: 87.1,
      changeVsPrev: -2.2,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'AHT',
      weakestKpiLabel: 'AHT (Handle Time)',
      mainIssue: 'AHT at 5.03 min (vs 2.50 min target) & Booking Rate at 47.8% (vs 65.0%)',
      kpiCells: [
        { kpiKey: 'AHT', label: 'AHT', actualFormatted: '5.03 min', targetFormatted: '2.50 min', achievementPct: 49.7, metTarget: false },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '47.8%', targetFormatted: '65.0%', achievementPct: 73.6, metTarget: false },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '66.2%', targetFormatted: '75.0%', achievementPct: 88.3, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '100.0%', targetFormatted: '95.0%', achievementPct: 100.0, metTarget: true },
      ],
    },
    {
      employeeId: 'Ayaallah Abdo Hassan Ahmed',
      agentName: 'Ayaallah Abdo Hassan Ahmed',
      score: 85.0,
      previousScore: 86.8,
      changeVsPrev: -1.8,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'AHT',
      weakestKpiLabel: 'AHT (Handle Time)',
      mainIssue: 'AHT at 4.50 min (vs 2.50 min target) & Booking Rate at 41.3% (vs 65.0%)',
      kpiCells: [
        { kpiKey: 'AHT', label: 'AHT', actualFormatted: '4.50 min', targetFormatted: '2.50 min', achievementPct: 55.6, metTarget: false },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '41.3%', targetFormatted: '65.0%', achievementPct: 63.5, metTarget: false },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '65.2%', targetFormatted: '75.0%', achievementPct: 86.9, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '100.0%', targetFormatted: '95.0%', achievementPct: 100.0, metTarget: true },
      ],
    },
    {
      employeeId: 'Andrew Magdy George Moussa Ibrahim',
      agentName: 'Andrew Magdy George Moussa Ibrahim',
      score: 88.1,
      previousScore: 90.4,
      changeVsPrev: -2.3,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'Quality',
      weakestKpiLabel: 'Quality Score',
      mainIssue: 'Missing/zero Quality Score calibration & Utilization at 59.0% (vs 85.0%)',
      kpiCells: [
        { kpiKey: 'AHT', label: 'AHT', actualFormatted: '2.57 min', targetFormatted: '2.50 min', achievementPct: 97.4, metTarget: false },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '63.8%', targetFormatted: '65.0%', achievementPct: 98.2, metTarget: false },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '71.2%', targetFormatted: '75.0%', achievementPct: 94.9, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '0.0%', targetFormatted: '95.0%', achievementPct: 0.0, metTarget: false },
      ],
    },
    {
      employeeId: 'Radwa Ahmed Mohamed',
      agentName: 'Radwa Ahmed Mohamed',
      score: 88.2,
      previousScore: 89.1,
      changeVsPrev: -0.9,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'Attendance',
      weakestKpiLabel: 'Attendance Rate',
      mainIssue: 'Attendance Rate at 63.7% (vs 75.0% target) & Booking Rate at 61.2%',
      kpiCells: [
        { kpiKey: 'AHT', label: 'AHT', actualFormatted: '2.65 min', targetFormatted: '2.50 min', achievementPct: 94.3, metTarget: false },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '61.2%', targetFormatted: '65.0%', achievementPct: 94.1, metTarget: false },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '63.7%', targetFormatted: '75.0%', achievementPct: 84.9, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '96.0%', targetFormatted: '95.0%', achievementPct: 100.0, metTarget: true },
      ],
    },
    {
      employeeId: 'Abdelrahman Adnan El Sayed Abdelnaby',
      agentName: 'Abdelrahman Adnan El Sayed Abdelnaby',
      score: 89.3,
      previousScore: 88.7,
      changeVsPrev: 0.6,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'Attendance',
      weakestKpiLabel: 'Attendance Rate',
      mainIssue: 'Attendance Rate at 64.8% (vs 75.0% target) & AHT at 2.75 min',
      kpiCells: [
        { kpiKey: 'AHT', label: 'AHT', actualFormatted: '2.75 min', targetFormatted: '2.50 min', achievementPct: 90.9, metTarget: false },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '66.2%', targetFormatted: '65.0%', achievementPct: 100.0, metTarget: true },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '64.8%', targetFormatted: '75.0%', achievementPct: 86.4, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '98.0%', targetFormatted: '95.0%', achievementPct: 100.0, metTarget: true },
      ],
    },
    {
      employeeId: 'Mahmoud reda azab abdelhalim',
      agentName: 'Mahmoud reda azab abdelhalim',
      score: 89.5,
      previousScore: 90.1,
      changeVsPrev: -0.6,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'Utilization',
      weakestKpiLabel: 'Utilization',
      mainIssue: 'Utilization at 72.0% (vs 85.0% target) & Attendance Rate at 66.3%',
      kpiCells: [
        { kpiKey: 'AHT', label: 'AHT', actualFormatted: '2.28 min', targetFormatted: '2.50 min', achievementPct: 100.0, metTarget: true },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '59.5%', targetFormatted: '65.0%', achievementPct: 91.6, metTarget: false },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '66.3%', targetFormatted: '75.0%', achievementPct: 88.4, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '97.0%', targetFormatted: '95.0%', achievementPct: 100.0, metTarget: true },
      ],
    },
    {
      employeeId: 'Malak Sherif Ibrahim Alghandour',
      agentName: 'Malak Sherif Ibrahim Alghandour',
      score: 89.6,
      previousScore: 88.9,
      changeVsPrev: 0.7,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'AHT',
      weakestKpiLabel: 'AHT (Handle Time)',
      mainIssue: 'AHT at 4.20 min (vs 2.50 min target) & Booking Rate at 45.8% (vs 65.0%)',
      kpiCells: [
        { kpiKey: 'AHT', label: 'AHT', actualFormatted: '4.20 min', targetFormatted: '2.50 min', achievementPct: 59.5, metTarget: false },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '45.8%', targetFormatted: '65.0%', achievementPct: 70.5, metTarget: false },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '69.2%', targetFormatted: '75.0%', achievementPct: 92.3, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '100.0%', targetFormatted: '95.0%', achievementPct: 100.0, metTarget: true },
      ],
    },
    {
      employeeId: 'Aya Ramadan Helmy Ibrahim',
      agentName: 'Aya Ramadan Helmy Ibrahim',
      score: 89.6,
      previousScore: 88.4,
      changeVsPrev: 1.2,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'Booking',
      weakestKpiLabel: 'Booking Rate',
      mainIssue: 'Booking Rate at 47.7% (vs 65.0% target) & AHT at 3.10 min (vs 2.50 min)',
      kpiCells: [
        { kpiKey: 'AHT', label: 'AHT', actualFormatted: '3.10 min', targetFormatted: '2.50 min', achievementPct: 80.6, metTarget: false },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '47.7%', targetFormatted: '65.0%', achievementPct: 73.3, metTarget: false },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '69.0%', targetFormatted: '75.0%', achievementPct: 92.1, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '98.0%', targetFormatted: '95.0%', achievementPct: 100.0, metTarget: true },
      ],
    },
    {
      employeeId: 'lslam Mohamed Ali',
      agentName: 'lslam Mohamed Ali',
      score: 89.9,
      previousScore: 90.2,
      changeVsPrev: -0.3,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'AHT',
      weakestKpiLabel: 'AHT (Handle Time)',
      mainIssue: 'AHT at 4.60 min (vs 2.50 min target, 54.3% achievement)',
      kpiCells: [
        { kpiKey: 'AHT', label: 'AHT', actualFormatted: '4.60 min', targetFormatted: '2.50 min', achievementPct: 54.3, metTarget: false },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '60.9%', targetFormatted: '65.0%', achievementPct: 93.8, metTarget: false },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '67.3%', targetFormatted: '75.0%', achievementPct: 89.7, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '96.0%', targetFormatted: '95.0%', achievementPct: 100.0, metTarget: true },
      ],
    },
  ],
  individualActionPlans: [],
  teamActionPlans: [
    {
      id: 'team-act-inb-1',
      title: 'Deploy live AHT pacing alerts & fast-track doctor-schedule lookup cheat sheets for calls > 3.00 min',
      targetKpi: 'AHT (Handle Time) · 3.01 min → ≤ 2.60 min',
      scopeDescription: 'Whole Inbound cohort (focusing on 5 outlier agents averaging 4.20–5.03 min)',
      owner: 'Workforce Analyst & Inbound Team Leader',
      expectedTeamImpact: '+1.2% Inbound team score lift',
      status: 'In Progress',
    },
    {
      id: 'team-act-inb-2',
      title: 'Standardize clinic-slot alternative offer script before ending unbooked patient inquiries',
      targetKpi: 'Booking Rate · 60.3% → 65.0% target',
      scopeDescription: 'All 35 Inbound Agents during daily shift huddles',
      owner: 'Call Center Trainer',
      expectedTeamImpact: '+0.9% Inbound team score lift',
      status: 'Open',
    },
    {
      id: 'team-act-inb-3',
      title: 'Rebalance afternoon shift overlaps & review shrinkage assumptions against the 75% Attendance benchmark',
      targetKpi: 'Attendance Rate · 68.2% → 73.0%+',
      scopeDescription: 'Inbound shift scheduling & attendance governance',
      owner: 'Inbound Team Leader & Workforce Analyst',
      expectedTeamImpact: '+0.7% Inbound team score lift',
      status: 'Open',
    },
  ],
};

// Populate individualActionPlans from agentsAverageOrBelow for INBOUND_TEAM_DEEP_DIVE_SEP_2026
INBOUND_TEAM_DEEP_DIVE_SEP_2026.individualActionPlans =
  INBOUND_TEAM_DEEP_DIVE_SEP_2026.agentsAverageOrBelow.map((row, idx) => {
    const rec = recommendedActionForKpi(
      row.weakestKpiKey,
      row.weakestKpiLabel,
      'Inbound',
      row.kpiCells.find((c) => c.kpiKey === row.weakestKpiKey)?.actualFormatted ?? '',
      row.kpiCells.find((c) => c.kpiKey === row.weakestKpiKey)?.targetFormatted ?? '',
      row.mainIssue,
    );
    return {
      id: `ind-inb-${idx}`,
      employeeId: row.employeeId,
      agentName: row.agentName,
      score: row.score,
      grade: row.grade,
      gradeFullLabel: row.gradeFullLabel,
      mainIssue: row.mainIssue,
      actionText: rec.actionText,
      owner: rec.owner,
      expectedImpact: `+${Math.max(2.0, round1(92.0 - row.score)).toFixed(1)}% agent score (+0.2% team lift)`,
      linkedKpiKey: row.weakestKpiKey,
    };
  });

export const OUTBOUND_TEAM_DEEP_DIVE_SEP_2026: TeamDeepDiveData = {
  teamSlug: 'outbound',
  canonicalTeam: 'Outbound',
  teamDisplayName: 'Outbound Agents',
  functionName: 'Call Center',
  regionCode: 'EGY',
  regionName: 'Offshore Egypt',
  monthLabel: 'September 2026',
  previousMonthLabel: 'August',
  periodKey: '2026-09',
  summary: {
    score: 87.0,
    grade: 'C',
    gradeFullLabel: 'Average',
    target: 100.0,
    gap: -13.0,
    changeVsPrev: 10.4,
    headcount: 7,
    averageOrBelowCount: 6,
    diagnosis:
      'Outbound Agents rebounded +10.4% vs August to 87.0% (Average) after Booking Rate beat its recalibrated 30.0% target (32.4%). However, 6 of 7 agents remain in Average grade due to low Reachability (53.3% vs 75.0% target) and Attendance Rate (56.6% vs 65.0% target).',
  },
  kpis: [
    {
      kpiKey: 'Other',
      label: 'Reachability',
      shortLabel: 'Reachability',
      unit: '%',
      betterDirection: 'higher',
      actual: 53.3,
      target: 75.0,
      actualFormatted: '53.3%',
      targetFormatted: '75.0%',
      achievementPct: 71.1,
      movementFormatted: '▼ -0.1% vs August',
      movementTone: 'negative',
      agentsMeetingTarget: 0,
      totalAgents: 7,
      verdictBadge: 'Stretched Target + Execution',
      explorerDiagnosis:
        'Both target realism and dial-window execution are issues: Outbound Reachability has never reached the 75.0% target in any of the last 6 months (peaking at 64.7% in April and sliding to 53.3% in September, with 0 of 7 agents meeting 75%). Calling windows need re-timing and the 75% benchmark warrants review.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 64.7, target: 75.0, actualFormatted: '64.7%', targetFormatted: '75.0%', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 64.5, target: 75.0, actualFormatted: '64.5%', targetFormatted: '75.0%', metTarget: false },
        { month: 'Jun', periodKey: '2026-06', actual: 57.7, target: 75.0, actualFormatted: '57.7%', targetFormatted: '75.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 56.7, target: 75.0, actualFormatted: '56.7%', targetFormatted: '75.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 53.4, target: 75.0, actualFormatted: '53.4%', targetFormatted: '75.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 53.3, target: 75.0, actualFormatted: '53.3%', targetFormatted: '75.0%', metTarget: false },
      ],
    },
    {
      kpiKey: 'Booking',
      label: 'Booking Rate',
      shortLabel: 'Booking Rate',
      unit: '%',
      betterDirection: 'higher',
      actual: 32.4,
      target: 30.0,
      actualFormatted: '32.4%',
      targetFormatted: '30.0%',
      achievementPct: 95.8,
      movementFormatted: '▲ +14.1% vs August',
      movementTone: 'positive',
      agentsMeetingTarget: 3,
      totalAgents: 7,
      verdictBadge: 'Target Met',
      explorerDiagnosis:
        'Historical trend proves earlier targets (58% in Apr, 46% in May) were unrealistic; after recalibrating the target to 30.0% in June and delivering Trainer coaching, the team surged from 18.3% in August to 32.4% in September (exceeding target).',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 23.8, target: 58.0, actualFormatted: '23.8%', targetFormatted: '58.0%', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 23.2, target: 46.0, actualFormatted: '23.2%', targetFormatted: '46.0%', metTarget: false },
        { month: 'Jun', periodKey: '2026-06', actual: 20.2, target: 30.0, actualFormatted: '20.2%', targetFormatted: '30.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 17.8, target: 30.0, actualFormatted: '17.8%', targetFormatted: '30.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 18.3, target: 30.0, actualFormatted: '18.3%', targetFormatted: '30.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 32.4, target: 30.0, actualFormatted: '32.4%', targetFormatted: '30.0%', metTarget: true },
      ],
    },
    {
      kpiKey: 'Attendance',
      label: 'Attendance Rate',
      shortLabel: 'Attendance',
      unit: '%',
      betterDirection: 'higher',
      actual: 56.6,
      target: 65.0,
      actualFormatted: '56.6%',
      targetFormatted: '65.0%',
      achievementPct: 87.1,
      movementFormatted: '▲ +9.0% vs August',
      movementTone: 'warning',
      agentsMeetingTarget: 1,
      totalAgents: 7,
      verdictBadge: 'Stretched Target + Execution',
      explorerDiagnosis:
        'Target was raised from 55.0% to 65.0% in June (+10 pts); September actuals recovered +9.0% vs August to a 6-month high of 56.6% (above the old 55% target), showing improving execution against a higher bar.',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 52.8, target: 55.0, actualFormatted: '52.8%', targetFormatted: '55.0%', metTarget: false },
        { month: 'May', periodKey: '2026-05', actual: 52.2, target: 55.0, actualFormatted: '52.2%', targetFormatted: '55.0%', metTarget: false },
        { month: 'Jun', periodKey: '2026-06', actual: 50.8, target: 65.0, actualFormatted: '50.8%', targetFormatted: '65.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 52.3, target: 65.0, actualFormatted: '52.3%', targetFormatted: '65.0%', metTarget: false },
        { month: 'Aug', periodKey: '2026-08', actual: 47.6, target: 65.0, actualFormatted: '47.6%', targetFormatted: '65.0%', metTarget: false },
        { month: 'Sep', periodKey: '2026-09', actual: 56.6, target: 65.0, actualFormatted: '56.6%', targetFormatted: '65.0%', metTarget: false },
      ],
    },
    {
      kpiKey: 'Quality',
      label: 'Quality Score',
      shortLabel: 'Quality Score',
      unit: '%',
      betterDirection: 'higher',
      actual: 96.0,
      target: 95.0,
      actualFormatted: '96.0%',
      targetFormatted: '95.0%',
      achievementPct: 100.0,
      movementFormatted: '▼ -0.2% vs August',
      movementTone: 'positive',
      agentsMeetingTarget: 7,
      totalAgents: 7,
      verdictBadge: 'Target Met',
      explorerDiagnosis:
        'Target (95.0%) is realistic and achieved by 100% of Outbound agents (7 of 7 agents ≥ 95.0% in September).',
      trend6Mo: [
        { month: 'Apr', periodKey: '2026-04', actual: 99.4, target: 95.0, actualFormatted: '99.4%', targetFormatted: '95.0%', metTarget: true },
        { month: 'May', periodKey: '2026-05', actual: 98.7, target: 95.0, actualFormatted: '98.7%', targetFormatted: '95.0%', metTarget: true },
        { month: 'Jun', periodKey: '2026-06', actual: 94.2, target: 95.0, actualFormatted: '94.2%', targetFormatted: '95.0%', metTarget: false },
        { month: 'Jul', periodKey: '2026-07', actual: 97.6, target: 95.0, actualFormatted: '97.6%', targetFormatted: '95.0%', metTarget: true },
        { month: 'Aug', periodKey: '2026-08', actual: 96.2, target: 95.0, actualFormatted: '96.2%', targetFormatted: '95.0%', metTarget: true },
        { month: 'Sep', periodKey: '2026-09', actual: 96.0, target: 95.0, actualFormatted: '96.0%', targetFormatted: '95.0%', metTarget: true },
      ],
    },
  ],
  agentsAverageOrBelow: [
    {
      employeeId: 'Rawan Mohamed Salah Elnajjar',
      agentName: 'Rawan Mohamed Salah Elnajjar',
      score: 81.0,
      previousScore: 75.4,
      changeVsPrev: 5.6,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'Other',
      weakestKpiLabel: 'Reachability',
      mainIssue: 'Reachability at 54.1% (vs 75.0% target) & Utilization at 59.9% (vs 80.0%)',
      kpiCells: [
        { kpiKey: 'Other', label: 'Reachability', actualFormatted: '54.1%', targetFormatted: '75.0%', achievementPct: 72.1, metTarget: false },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '23.0%', targetFormatted: '30.0%', achievementPct: 76.6, metTarget: false },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '52.7%', targetFormatted: '65.0%', achievementPct: 81.1, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '95.0%', targetFormatted: '95.0%', achievementPct: 100.0, metTarget: true },
      ],
    },
    {
      employeeId: 'Abdelrahman Yasser Abdullah',
      agentName: 'Abdelrahman Yasser Abdullah',
      score: 84.5,
      previousScore: 76.1,
      changeVsPrev: 8.4,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'Other',
      weakestKpiLabel: 'Reachability',
      mainIssue: 'Reachability at 58.7% (vs 75.0% target) & Attendance Rate at 51.8% (vs 65.0%)',
      kpiCells: [
        { kpiKey: 'Other', label: 'Reachability', actualFormatted: '58.7%', targetFormatted: '75.0%', achievementPct: 78.3, metTarget: false },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '47.2%', targetFormatted: '30.0%', achievementPct: 100.0, metTarget: true },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '51.8%', targetFormatted: '65.0%', achievementPct: 79.7, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '98.0%', targetFormatted: '95.0%', achievementPct: 100.0, metTarget: true },
      ],
    },
    {
      employeeId: 'Ahmed Mohamed Abdelrashed Abdelkahlek',
      agentName: 'Ahmed Mohamed Abdelrashed Abdelkahlek',
      score: 84.5,
      previousScore: 75.8,
      changeVsPrev: 8.7,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'Other',
      weakestKpiLabel: 'Reachability',
      mainIssue: 'Reachability at 46.9% (vs 75.0% target, 62.5% achievement) & Attendance Rate at 52.5%',
      kpiCells: [
        { kpiKey: 'Other', label: 'Reachability', actualFormatted: '46.9%', targetFormatted: '75.0%', achievementPct: 62.5, metTarget: false },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '29.5%', targetFormatted: '30.0%', achievementPct: 98.5, metTarget: false },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '52.5%', targetFormatted: '65.0%', achievementPct: 80.8, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '96.0%', targetFormatted: '95.0%', achievementPct: 100.0, metTarget: true },
      ],
    },
    {
      employeeId: 'Ammar Yasser sayed Ghareb',
      agentName: 'Ammar Yasser sayed Ghareb',
      score: 86.5,
      previousScore: 77.2,
      changeVsPrev: 9.3,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'Other',
      weakestKpiLabel: 'Reachability',
      mainIssue: 'Reachability at 50.0% (vs 75.0% target) & Utilization at 67.2% (vs 80.0%)',
      kpiCells: [
        { kpiKey: 'Other', label: 'Reachability', actualFormatted: '50.0%', targetFormatted: '75.0%', achievementPct: 66.6, metTarget: false },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '27.9%', targetFormatted: '30.0%', achievementPct: 92.9, metTarget: false },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '56.5%', targetFormatted: '65.0%', achievementPct: 86.9, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '96.0%', targetFormatted: '95.0%', achievementPct: 100.0, metTarget: true },
      ],
    },
    {
      employeeId: 'Salma Ali El-Sayed Khalafallah',
      agentName: 'Salma Ali El-Sayed Khalafallah',
      score: 88.5,
      previousScore: 78.0,
      changeVsPrev: 10.5,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'Other',
      weakestKpiLabel: 'Reachability',
      mainIssue: 'Reachability at 56.6% (vs 75.0% target) & Booking Rate at 26.1% (vs 30.0%)',
      kpiCells: [
        { kpiKey: 'Other', label: 'Reachability', actualFormatted: '56.6%', targetFormatted: '75.0%', achievementPct: 75.5, metTarget: false },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '26.1%', targetFormatted: '30.0%', achievementPct: 86.9, metTarget: false },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '57.7%', targetFormatted: '65.0%', achievementPct: 88.8, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '96.0%', targetFormatted: '95.0%', achievementPct: 100.0, metTarget: true },
      ],
    },
    {
      employeeId: 'Aya Shaaban Abdelazim Mohamed',
      agentName: 'Aya Shaaban Abdelazim Mohamed',
      score: 89.5,
      previousScore: 79.1,
      changeVsPrev: 10.4,
      grade: 'C',
      gradeFullLabel: 'Average',
      weakestKpiKey: 'Other',
      weakestKpiLabel: 'Reachability',
      mainIssue: 'Reachability at 57.6% (vs 75.0% target) & Booking Rate at 25.7% (vs 30.0%)',
      kpiCells: [
        { kpiKey: 'Other', label: 'Reachability', actualFormatted: '57.6%', targetFormatted: '75.0%', achievementPct: 76.7, metTarget: false },
        { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '25.7%', targetFormatted: '30.0%', achievementPct: 85.6, metTarget: false },
        { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '58.6%', targetFormatted: '65.0%', achievementPct: 90.1, metTarget: false },
        { kpiKey: 'Quality', label: 'Quality', actualFormatted: '95.0%', targetFormatted: '95.0%', achievementPct: 100.0, metTarget: true },
      ],
    },
  ],
  individualActionPlans: [],
  teamActionPlans: [
    {
      id: 'team-act-out-1',
      title: 'Re-time Outbound campaign dial windows to 10:00–13:00 & 17:00–20:00 and clean disconnected patient numbers',
      targetKpi: 'Reachability · 53.3% → 66.0%+',
      scopeDescription: 'All 7 Outbound Agents (0 of 7 currently meeting 75% Reachability)',
      owner: 'Outbound Team Leader & Workforce Analyst',
      expectedTeamImpact: '+2.4% Outbound team score lift',
      status: 'In Progress',
    },
    {
      id: 'team-act-out-2',
      title: 'Submit formal target calibration review for Outbound Reachability (75% → 65%) based on 6-month historical ceiling (64.7%)',
      targetKpi: 'Reachability Target Governance',
      scopeDescription: 'Outbound KPI evaluation settings alignment',
      owner: 'Outbound Team Leader & Performance Management',
      expectedTeamImpact: '+1.6% Outbound team score lift',
      status: 'Open',
    },
    {
      id: 'team-act-out-3',
      title: 'Pair top-converting Outbound agent (Abdelrahman Yasser, 47.2% booking) with 4 agents below 28% Booking Rate',
      targetKpi: 'Booking Rate · 32.4% → 35.0%+',
      scopeDescription: 'Peer call-shadowing across Outbound cohort',
      owner: 'Call Center Trainer',
      expectedTeamImpact: '+0.9% Outbound team score lift',
      status: 'Open',
    },
  ],
};

OUTBOUND_TEAM_DEEP_DIVE_SEP_2026.individualActionPlans =
  OUTBOUND_TEAM_DEEP_DIVE_SEP_2026.agentsAverageOrBelow.map((row, idx) => {
    const rec = recommendedActionForKpi(
      row.weakestKpiKey,
      row.weakestKpiLabel,
      'Outbound',
      row.kpiCells.find((c) => c.kpiKey === row.weakestKpiKey)?.actualFormatted ?? '',
      row.kpiCells.find((c) => c.kpiKey === row.weakestKpiKey)?.targetFormatted ?? '',
      row.mainIssue,
    );
    return {
      id: `ind-out-${idx}`,
      employeeId: row.employeeId,
      agentName: row.agentName,
      score: row.score,
      grade: row.grade,
      gradeFullLabel: row.gradeFullLabel,
      mainIssue: row.mainIssue,
      actionText: rec.actionText,
      owner: rec.owner,
      expectedImpact: `+${Math.max(2.5, round1(91.0 - row.score)).toFixed(1)}% agent score (+0.6% team lift)`,
      linkedKpiKey: row.weakestKpiKey,
    };
  });

/* -------------------------------------------------------------------------- */
/*  Real-Data Derivation Engine for Team Deep Dive                            */
/* -------------------------------------------------------------------------- */

const CALL_CENTER_SIBLINGS: TeamSibling[] = [
  { slug: 'inbound', label: 'Inbound Agents' },
  { slug: 'outbound', label: 'Outbound Agents' },
];

function withCallCenterNav(data: TeamDeepDiveData, region: 'EGY' | 'UAE'): TeamDeepDiveData {
  return {
    ...data,
    functionName: 'Call Center',
    functionSlug: 'call-center',
    siblingTeams: CALL_CENTER_SIBLINGS,
    regionCode: region,
    regionName: region === 'EGY' ? 'Offshore Egypt' : 'UAE Region',
  };
}

function locateBaselineTeam(teamSlug: string): {
  data: CallCenterDeepDiveData;
  teamIndex: number;
} | null {
  for (const data of Object.values(FUNCTION_DEEP_DIVE_BASELINES_SEP_2026)) {
    const teamIndex = data.agentTeams.findIndex(
      (team) =>
        team.teamSlug === teamSlug ||
        slugifyIdentifier(team.canonicalTeam) === teamSlug ||
        slugifyIdentifier(team.teamName) === teamSlug,
    );
    if (teamIndex >= 0) return { data, teamIndex };
  }
  return null;
}

function kpiFromBaseline(kpi: AgentKeyKpiItem, headcount: number): TeamKpiItem {
  return {
    kpiKey: kpi.kpiKey,
    label: kpi.name,
    shortLabel: kpi.shortName,
    unit: kpi.unit,
    betterDirection: kpi.betterDirection,
    actual: kpi.trend6Mo[kpi.trend6Mo.length - 1]?.actual ?? null,
    target: kpi.trend6Mo[kpi.trend6Mo.length - 1]?.target ?? null,
    actualFormatted: kpi.actualDisplay,
    targetFormatted: kpi.targetDisplay,
    achievementPct: kpi.achievementPct,
    movementFormatted: kpi.trendLabel,
    movementTone: kpi.trendTone,
    agentsMeetingTarget: 0,
    totalAgents: headcount,
    verdictBadge: kpi.trendTone === 'positive' ? 'Target Met' : 'Execution Issue',
    explorerDiagnosis: kpi.targetRealismDiagnosis || kpi.diagnosis,
    trend6Mo: kpi.trend6Mo,
  };
}

function teamFromBaseline(
  located: { data: CallCenterDeepDiveData; teamIndex: number },
  region: 'EGY' | 'UAE',
): TeamDeepDiveData {
  const team = located.data.agentTeams[located.teamIndex];
  const siblings = located.data.agentTeams.map((item) => ({
    slug: item.teamSlug,
    label: item.teamName,
  }));
  const people = located.data.agentsNeedingAttention.filter(
    (agent) => agent.teamSlug === team.teamSlug || slugifyIdentifier(agent.team) === team.teamSlug,
  );
  const kpis = located.data.keyKpis.slice(0, 4).map((kpi) => kpiFromBaseline(kpi, team.headcount));
  const agentsAverageOrBelow: AgentAverageOrBelowRow[] = people.map((agent) => ({
    employeeId: agent.employeeId,
    agentName: agent.agentName,
    score: agent.score,
    previousScore: null,
    changeVsPrev: null,
    grade: agent.grade,
    gradeFullLabel: agent.gradeLabel,
    kpiCells: kpis.map((kpi) => {
      const texts = people.length === 1 ? [agent.reason, team.diagnosis] : [agent.reason];
      const actual = statedActualForColumn(kpi, texts);
      const metTarget =
        actual !== null && kpi.target !== null
          ? kpi.betterDirection === 'lower'
            ? actual <= kpi.target + 1e-6
            : actual >= kpi.target - 1e-6
          : false;
      const achievementPct =
        actual !== null && kpi.target !== null && kpi.target > 0 && actual > 0
          ? round1(kpi.betterDirection === 'lower' ? (kpi.target / actual) * 100 : (actual / kpi.target) * 100)
          : 0;
      return {
        kpiKey: kpi.kpiKey,
        label: kpi.shortLabel,
        actualFormatted: actual === null ? '—' : formatKpiValue(actual, kpi.unit),
        targetFormatted: kpi.targetFormatted,
        achievementPct,
        metTarget,
      };
    }),
    mainIssue: agent.reason,
    weakestKpiKey: agent.weakestKpiKey,
    weakestKpiLabel: agent.reason.split(' at ')[0] || kpis[0]?.label || 'KPI',
  }));
  return {
    teamSlug: team.teamSlug,
    canonicalTeam: team.canonicalTeam,
    teamDisplayName: team.teamName,
    functionName: located.data.functionName,
    functionSlug: located.data.functionSlug,
    siblingTeams: siblings,
    regionCode: region,
    regionName: region === 'EGY' ? 'Offshore Egypt' : 'UAE Region',
    monthLabel: located.data.monthLabel,
    previousMonthLabel: located.data.previousMonthLabel,
    periodKey: located.data.periodKey,
    summary: {
      score: team.score,
      grade: team.grade,
      gradeFullLabel: team.gradeLabel,
      target: team.target,
      gap: team.gap,
      changeVsPrev: team.changeVsPrev,
      headcount: team.headcount,
      averageOrBelowCount: agentsAverageOrBelow.length,
      diagnosis: team.diagnosis,
    },
    kpis,
    agentsAverageOrBelow,
    individualActionPlans: agentsAverageOrBelow.map((row, index) => ({
      id: `ind-${team.teamSlug}-${index}`,
      employeeId: row.employeeId,
      agentName: row.agentName,
      score: row.score,
      grade: row.grade,
      gradeFullLabel: row.gradeFullLabel,
      mainIssue: row.mainIssue,
      actionText: recommendedActionForKpi(
        row.weakestKpiKey,
        row.weakestKpiLabel,
        team.canonicalTeam,
        row.kpiCells.find((cell) => cell.kpiKey === row.weakestKpiKey)?.actualFormatted ?? '',
        row.kpiCells.find((cell) => cell.kpiKey === row.weakestKpiKey)?.targetFormatted ?? '',
        row.mainIssue,
      ).actionText,
      owner: people[index]?.owningPosition || `${team.teamName} lead`,
      expectedImpact: `+${Math.max(1, Math.round((90 - row.score) * 10) / 10).toFixed(1)}% score lift`,
      linkedKpiKey: row.weakestKpiKey,
    })),
    teamActionPlans: located.data.actionsByPosition.items.slice(0, 3).map((item) => ({
      id: item.id,
      title: item.actionTitle,
      targetKpi: item.targetScope,
      scopeDescription: item.expectedKpiOutcome,
      owner: item.owningPosition,
      expectedTeamImpact: `+${item.expectedImpactPct.toFixed(1)}%`,
      status: 'Open' as const,
    })),
  };
}

function recordsForSlug(allRecords: ExecRecord[], teamSlug: string, canonicalTeam: string): ExecRecord[] {
  return allRecords.filter(
    (record) =>
      slugifyIdentifier(record.team) === teamSlug ||
      record.team.toLowerCase() === canonicalTeam.toLowerCase(),
  );
}

/** A leader scorecard month uses that scorecard. A month without one keeps everyone on the team. */
function recordsForTeamKpis(records: ExecRecord[]): ExecRecord[] {
  if (preApprovalsLeaderTeamTotal(records) === null) return records;
  const leaders = records.filter((record) => isHossamRecord(record));
  return leaders.length > 0 ? leaders : records;
}

function buildGenericTeamDeepDive(
  teamSlug: string,
  allRecords: ExecRecord[],
  actions: PMSAction[],
  region: 'EGY' | 'UAE',
  requestedPeriodKey?: string,
): TeamDeepDiveData {
  const located = region === 'UAE' ? null : locateBaselineTeam(teamSlug);
  const canonicalTeam = located?.data.agentTeams[located.teamIndex].canonicalTeam ?? teamSlug;
  const teamRecords = recordsForSlug(allRecords, teamSlug, canonicalTeam);
  if (!teamRecords.length) {
    if (located) return teamFromBaseline(located, region);
    const fallbackFn = getBaselineFunctionDeepDive('call-center', region);
    return {
      teamSlug,
      canonicalTeam,
      teamDisplayName: canonicalTeam,
      functionName: executiveFunctionForTeam(canonicalTeam) || 'Team',
      functionSlug: slugifyIdentifier(executiveFunctionForTeam(canonicalTeam) || 'team'),
      siblingTeams: [],
      regionCode: region,
      regionName: region === 'EGY' ? 'Offshore Egypt' : 'UAE Region',
      monthLabel: fallbackFn.monthLabel,
      previousMonthLabel: fallbackFn.previousMonthLabel,
      periodKey: requestedPeriodKey || fallbackFn.periodKey,
      summary: {
        score: 0,
        grade: 'E',
        gradeFullLabel: 'Unsatisfactory',
        target: 100,
        gap: -100,
        changeVsPrev: 0,
        headcount: 0,
        averageOrBelowCount: 0,
        diagnosis: 'No scored people for this team in the locked month.',
      },
      kpis: [],
      agentsAverageOrBelow: [],
      individualActionPlans: [],
      teamActionPlans: [],
    };
  }

  const periods = [...new Map(teamRecords.map((record) => [record.period.key, record.period])).values()].sort(
    (a, b) => b.key.localeCompare(a.key),
  );
  const requested = requestedPeriodKey ? periodFromKey(requestedPeriodKey) : null;
  const effective = (requested && periods.find((period) => period.key === requested.key)) || periods[0];
  const previous = periods.find((period) => period.key < effective.key) ?? null;
  const current = teamRecords.filter((record) => record.period.key === effective.key);
  const before = previous ? teamRecords.filter((record) => record.period.key === previous.key) : [];
  if (!current.length && located) return teamFromBaseline(located, region);

  const leaderNow = preApprovalsLeaderTeamTotal(current);
  const leaderPrev = preApprovalsLeaderTeamTotal(before);
  const score = leaderNow ?? round1(mean(current.map((record) => record.score)) ?? located?.data.agentTeams[located.teamIndex].score ?? 0);
  const prevScore = leaderPrev ?? mean(before.map((record) => record.score));
  const changeVsPrev = prevScore !== null ? round1(score - round1(prevScore)) : located?.data.agentTeams[located.teamIndex].changeVsPrev ?? 0;
  const grade = gradeForScore(score);
  const headcount = new Set(current.map((record) => record.employeeId)).size;
  const fnName =
    located?.data.functionName ||
    executiveFunctionForTeam(current[0]?.team || canonicalTeam) ||
    'Team';
  const fnSlug = located?.data.functionSlug || slugifyIdentifier(fnName);
  const siblingSource = allRecords.filter((record) => executiveFunctionForTeam(record.team) === fnName);
  const siblingNames = [...new Set((siblingSource.length ? siblingSource : current).map((record) => record.team))];
  const siblingTeams: TeamSibling[] =
    located?.data.agentTeams.map((team) => ({ slug: team.teamSlug, label: team.teamName })) ||
    siblingNames.map((name) => ({ slug: slugifyIdentifier(name), label: name }));
  const currentKpis = kpiRows(recordsForTeamKpis(current), recordsForTeamKpis(before)).slice(0, 4);
  const sixPeriods = trailingPeriods(effective, 6);
  const kpis: TeamKpiItem[] = currentKpis.map((row) => {
    const unit = row.unit ?? '%';
    const lowerBetter = String(row.kpi_direction ?? '').toLowerCase().startsWith('lower');
    const trend6Mo: KpiMonthlyPoint[] = sixPeriods.map((period) => {
      const monthRecords = teamRecords.filter((record) => record.period.key === period.key);
      const match = kpiRows(recordsForTeamKpis(monthRecords), []).find((item) => item.kpi_key === row.kpi_key);
      const actual = match?.actual ?? null;
      const target = match?.target ?? null;
      return {
        month: period.month.slice(0, 3),
        periodKey: period.key,
        actual,
        target,
        actualFormatted: formatKpiValue(actual, unit),
        targetFormatted: formatKpiValue(target, unit),
        metTarget:
          actual !== null && target !== null
            ? lowerBetter
              ? actual <= target + 1e-6
              : actual >= target - 1e-6
            : null,
      };
    });
    let agentsMeetingTarget = 0;
    current.forEach((agent) => {
      const agentRow = kpiRows([agent], []).find((item) => item.kpi_key === row.kpi_key);
      if (agentRow?.target_status === 'met') agentsMeetingTarget += 1;
    });
    return {
      kpiKey: row.kpi_key,
      label: row.kpi_label,
      shortLabel: row.kpi_label,
      unit,
      betterDirection: lowerBetter ? 'lower' : 'higher',
      actual: row.actual,
      target: row.target,
      actualFormatted: formatKpiValue(row.actual, unit),
      targetFormatted: formatKpiValue(row.target, unit),
      achievementPct: row.achievement_percent ?? 0,
      movementFormatted: row.raw_change !== null ? formatKpiValue(row.raw_change, unit) : '—',
      movementTone: row.target_status === 'met' ? 'positive' : 'warning',
      agentsMeetingTarget,
      totalAgents: headcount,
      verdictBadge: row.target_status === 'met' ? 'Target Met' : 'Execution Issue',
      explorerDiagnosis: `${row.kpi_label} is ${formatKpiValue(row.actual, unit)} against ${formatKpiValue(row.target, unit)}.`,
      trend6Mo,
    };
  });
  const low = current.filter((record) => record.score < 90).sort((a, b) => a.score - b.score);
  const agentsAverageOrBelow: AgentAverageOrBelowRow[] = low.map((agent) => {
    const g = gradeForScore(agent.score);
    const agentKpiRows = kpiRows([agent], []);
    const weakest = agentKpiRows[0];
    return {
      employeeId: agent.employeeId,
      agentName: agent.name,
      score: round1(agent.score),
      previousScore: null,
      changeVsPrev: null,
      grade: g,
      gradeFullLabel: fullGradeLabel(g),
      kpiCells: kpis.map((kpi) => {
        const match = personalKpiForColumn(agentKpiRows, kpi);
        return {
          kpiKey: kpi.kpiKey,
          label: kpi.shortLabel,
          actualFormatted: match ? formatKpiValue(match.actual, match.unit ?? kpi.unit) : '—',
          targetFormatted: kpi.targetFormatted,
          achievementPct: match?.achievement_percent ?? 0,
          metTarget: match?.target_status === 'met',
        };
      }),
      mainIssue: weakest
        ? `${weakest.kpi_label} at ${formatKpiValue(weakest.actual, weakest.unit)}`
        : 'Score below 90%',
      weakestKpiKey: weakest?.kpi_key ?? kpis[0]?.kpiKey ?? 'general',
      weakestKpiLabel: weakest?.kpi_label ?? 'KPI',
    };
  });
  const savedFor = (row: AgentAverageOrBelowRow) =>
    actions.find(
      (action) =>
        action.employee_id?.toLowerCase() === row.employeeId.toLowerCase() ||
        action.employee_name?.toLowerCase() === row.agentName.toLowerCase(),
    );

  return {
    teamSlug,
    canonicalTeam,
    teamDisplayName: located?.data.agentTeams[located.teamIndex].teamName ?? canonicalTeam,
    functionName: fnName,
    functionSlug: fnSlug,
    siblingTeams,
    regionCode: region,
    regionName: region === 'EGY' ? 'Offshore Egypt' : 'UAE Region',
    monthLabel: `${effective.month} ${effective.year}`,
    previousMonthLabel: previous?.month ?? 'August',
    periodKey: effective.key,
    summary: {
      score,
      grade,
      gradeFullLabel: fullGradeLabel(grade),
      target: 100,
      gap: round1(score - 100),
      changeVsPrev,
      headcount,
      averageOrBelowCount: agentsAverageOrBelow.length,
      diagnosis:
        leaderNow !== null
          ? `${canonicalTeam} is ${score.toFixed(1)}% on the leader scorecard, across ${headcount} measured people.`
          : located?.data.agentTeams[located.teamIndex].diagnosis ??
            `${canonicalTeam} averaged ${score.toFixed(1)}% across ${headcount} people.`,
    },
    kpis,
    agentsAverageOrBelow,
    individualActionPlans: agentsAverageOrBelow.map((row, index) => {
      const saved = savedFor(row);
      return {
        id: saved?.id ?? `ind-${teamSlug}-${index}`,
        employeeId: row.employeeId,
        agentName: row.agentName,
        score: row.score,
        grade: row.grade,
        gradeFullLabel: row.gradeFullLabel,
        mainIssue: saved?.root_cause_note || row.mainIssue,
        actionText:
          saved?.action_text ||
          recommendedActionForKpi(
            row.weakestKpiKey,
            row.weakestKpiLabel,
            canonicalTeam,
            row.kpiCells.find((cell) => cell.kpiKey === row.weakestKpiKey)?.actualFormatted ?? '',
            row.kpiCells.find((cell) => cell.kpiKey === row.weakestKpiKey)?.targetFormatted ?? '',
            row.mainIssue,
          ).actionText,
        owner: saved?.owner?.name || `${canonicalTeam} lead`,
        expectedImpact: `+${Math.max(1, round1(90 - row.score)).toFixed(1)}% score lift`,
        linkedKpiKey: row.weakestKpiKey,
        isSavedToStore: Boolean(saved),
      };
    }),
    teamActionPlans: located?.data.actionsByPosition.items.slice(0, 3).map((item) => ({
      id: item.id,
      title: item.actionTitle,
      targetKpi: item.targetScope,
      scopeDescription: item.expectedKpiOutcome,
      owner: item.owningPosition,
      expectedTeamImpact: `+${item.expectedImpactPct.toFixed(1)}%`,
      status: 'Open' as const,
    })) ?? [],
  };
}

export function buildTeamDeepDiveFromRecords(
  teamSlug: TeamSlug,
  allRecords: ExecRecord[],
  actions: PMSAction[] = [],
  region: 'EGY' | 'UAE' = 'EGY',
  requestedPeriodKey?: string,
): TeamDeepDiveData {
  const scopedRecords = scopeRecordsToRegion(allRecords, region);
  const normalizedSlug = slugifyIdentifier(teamSlug);
  if (normalizedSlug !== 'inbound' && normalizedSlug !== 'outbound') {
    return buildGenericTeamDeepDive(normalizedSlug, scopedRecords, actions, region, requestedPeriodKey);
  }
  const canonicalTeam: 'Inbound' | 'Outbound' =
    normalizedSlug === 'outbound' ? 'Outbound' : 'Inbound';
  const fallback =
    canonicalTeam === 'Outbound'
      ? OUTBOUND_TEAM_DEEP_DIVE_SEP_2026
      : INBOUND_TEAM_DEEP_DIVE_SEP_2026;

  const teamRecords = scopedRecords.filter((r) => r.team === canonicalTeam);
  if (!teamRecords.length) {
    if (region === 'UAE') {
      return buildGenericTeamDeepDive(normalizedSlug, [], actions, region, requestedPeriodKey);
    }
    return withCallCenterNav(
      {
        ...fallback,
        teamSlug: normalizedSlug,
      },
      region,
    );
  }

  const periods = [
    ...new Map(teamRecords.map((r) => [r.period.key, r.period])).values(),
  ].sort((a, b) => b.key.localeCompare(a.key));

  const requested = requestedPeriodKey ? periodFromKey(requestedPeriodKey) : null;
  const effective: ExecutivePeriod =
    (requested && periods.find((p) => p.key === requested.key)) || periods[0];
  const previous: ExecutivePeriod | null =
    periods.find((p) => p.key < effective.key) ?? null;

  const inPeriod = (recs: ExecRecord[], p: ExecutivePeriod | null) =>
    p ? recs.filter((r) => r.period.key === p.key) : [];

  const current = inPeriod(teamRecords, effective);
  const before = inPeriod(teamRecords, previous);

  if (!current.length) {
    if (region === 'UAE') {
      return buildGenericTeamDeepDive(normalizedSlug, [], actions, region, requestedPeriodKey);
    }
    return withCallCenterNav({ ...fallback, teamSlug: normalizedSlug }, region);
  }

  const score = round1(mean(current.map((r) => r.score)) ?? fallback.summary.score);
  const prevScore = mean(before.map((r) => r.score));
  const changeVsPrev =
    prevScore !== null ? round1(score - round1(prevScore)) : fallback.summary.changeVsPrev;
  const grade = gradeForScore(score);
  const gradeFull = fullGradeLabel(grade);
  const headcount = new Set(current.map((r) => r.employeeId)).size;

  // Build real KPI items + 6-month trends
  const currentKpiRows = kpiRows(current, before);
  const sixPeriods = trailingPeriods(effective, 6);

  const kpis: TeamKpiItem[] =
    currentKpiRows.length > 0
      ? currentKpiRows.slice(0, 4).map((row) => {
          const unit = row.unit ?? '%';
          const lowerBetter = String(row.kpi_direction ?? '')
            .toLowerCase()
            .startsWith('lower');

          const trend6Mo: KpiMonthlyPoint[] = sixPeriods.map((p) => {
            const pRows = kpiRows(inPeriod(teamRecords, p), []);
            const match = pRows.find((k) => k.kpi_key === row.kpi_key);
            const actual = match?.actual ?? null;
            const target = match?.target ?? null;
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

          // Count how many agents in current period met this KPI's target
          let agentsMeetingTarget = 0;
          current.forEach((agent) => {
            const aRow = kpiRows([agent], []).find((k) => k.kpi_key === row.kpi_key);
            if (aRow?.target_status === 'met') agentsMeetingTarget += 1;
          });

          const metMonths = trend6Mo.filter((pt) => pt.metTarget === true).length;
          const uniqueTargets = [
            ...new Set(
              trend6Mo.map((pt) => pt.target).filter((t): t is number => t !== null),
            ),
          ];
          const targetChanged = uniqueTargets.length > 1;

          const verdictBadge: TeamKpiItem['verdictBadge'] =
            row.target_status === 'met'
              ? 'Target Met'
              : targetChanged || (metMonths === 0 && agentsMeetingTarget < headcount * 0.25)
              ? 'Stretched Target + Execution'
              : 'Execution Issue';

          const explorerDiagnosis =
            row.target_status === 'met'
              ? `Target (${formatKpiValue(row.target, unit)}) is realistic and achieved: ${agentsMeetingTarget} of ${headcount} agents met the benchmark in ${effective.month}, with the team averaging ${formatKpiValue(row.actual, unit)}.`
              : targetChanged
              ? `Target shifted from ${formatKpiValue(uniqueTargets[0], unit)} to ${formatKpiValue(uniqueTargets[uniqueTargets.length - 1], unit)} over the last 6 months. ${agentsMeetingTarget} of ${headcount} agents met the current target in ${effective.month}, showing both a tougher target bar and coaching opportunity for the bottom quartile.`
              : agentsMeetingTarget >= Math.ceil(headcount * 0.4)
              ? `Execution is the primary issue, not the ${formatKpiValue(row.target, unit)} target: ${agentsMeetingTarget} of ${headcount} agents already achieve target in ${effective.month}, while low-performing outliers pull the team average to ${formatKpiValue(row.actual, unit)}.`
              : `Structural gap across 6 months: only ${agentsMeetingTarget} of ${headcount} agents met the ${formatKpiValue(row.target, unit)} target in ${effective.month} (team met target in ${metMonths} of 6 months). Both workflow/window changes and target calibration review are needed.`;

          const rawChange = row.raw_change;
          const improved = (row.change_value ?? 0) > 0;

          return {
            kpiKey: row.kpi_key,
            label: row.kpi_label,
            shortLabel: row.kpi_label.replace(/\s*\(.*?\)\s*/g, ''),
            unit,
            betterDirection: lowerBetter ? 'lower' : 'higher',
            actual: row.actual,
            target: row.target,
            actualFormatted: formatKpiValue(row.actual, unit),
            targetFormatted: formatKpiValue(row.target, unit),
            achievementPct: row.achievement_percent ?? 0,
            movementFormatted:
              rawChange !== null
                ? `${rawChange >= 0 ? '▲ +' : '▼ '}${formatKpiValue(Math.abs(rawChange), unit)} vs ${previous?.month ?? 'August'}`
                : '—',
            movementTone:
              row.target_status === 'met' || improved
                ? 'positive'
                : lowerBetter && (rawChange ?? 0) > 0
                ? 'negative'
                : 'warning',
            agentsMeetingTarget,
            totalAgents: headcount,
            verdictBadge,
            explorerDiagnosis,
            trend6Mo,
          };
        })
      : fallback.kpis;

  // Build Agents — Average and Below (Grade C or lower: score < 90)
  const kpiColumns = kpis.slice(0, 4);
  const lowAgentRecords = current
    .filter((r) => r.score < 90)
    .sort((a, b) => a.score - b.score || a.name.localeCompare(b.name));

  const agentsAverageOrBelow: AgentAverageOrBelowRow[] =
    lowAgentRecords.length > 0
      ? lowAgentRecords.map((agent) => {
          const prevRec = before.find((b) => b.employeeId === agent.employeeId);
          const prevAgentScore = prevRec ? round1(prevRec.score) : null;
          const delta =
            prevAgentScore !== null ? round1(round1(agent.score) - prevAgentScore) : null;
          const agentKpiRows = kpiRows([agent], []);
          const weakest = agentKpiRows[0];
          const secondWeakest = agentKpiRows[1];
          const g = gradeForScore(agent.score);

          const kpiCells: AgentKpiCellValue[] = kpiColumns.map((col) => {
            const match = personalKpiForColumn(agentKpiRows, col);
            return {
              kpiKey: col.kpiKey,
              label: col.shortLabel,
              actualFormatted: match
                ? formatKpiValue(match.actual, match.unit ?? col.unit)
                : '—',
              targetFormatted: col.targetFormatted,
              achievementPct: match?.achievement_percent ?? 0,
              metTarget: match?.target_status === 'met',
            };
          });

          const mainIssue = weakest
            ? `${weakest.kpi_label} at ${formatKpiValue(weakest.actual, weakest.unit)} (vs ${formatKpiValue(weakest.target, weakest.unit)} target, ${(weakest.achievement_percent ?? 0).toFixed(1)}% achievement)${
                secondWeakest && (secondWeakest.achievement_percent ?? 100) < 88
                  ? ` & ${secondWeakest.kpi_label} at ${formatKpiValue(secondWeakest.actual, secondWeakest.unit)}`
                  : ''
              }`
            : 'Score below 90% threshold';

          return {
            employeeId: agent.employeeId,
            agentName: agent.name,
            score: round1(agent.score),
            previousScore: prevAgentScore,
            changeVsPrev: delta,
            grade: g,
            gradeFullLabel: fullGradeLabel(g),
            kpiCells,
            mainIssue,
            weakestKpiKey: weakest?.kpi_key ?? kpiColumns[0]?.kpiKey ?? 'Booking',
            weakestKpiLabel: weakest?.kpi_label ?? kpiColumns[0]?.label ?? 'Booking Rate',
          };
        })
      : fallback.agentsAverageOrBelow;

  // Build Individual Action Plans (merging any saved actions from useActionStore)
  const individualActionPlans: IndividualActionPlanCard[] = agentsAverageOrBelow.map(
    (row, idx) => {
      const savedAction = actions.find(
        (a) =>
          (a.employee_id &&
            a.employee_id.toLowerCase() === row.employeeId.toLowerCase()) ||
          (a.employee_name &&
            a.employee_name.toLowerCase() === row.agentName.toLowerCase()),
      );
      const weakestCell = row.kpiCells.find((c) => c.kpiKey === row.weakestKpiKey);
      const recommended = recommendedActionForKpi(
        row.weakestKpiKey,
        row.weakestKpiLabel,
        canonicalTeam,
        weakestCell?.actualFormatted ?? '',
        weakestCell?.targetFormatted ?? '',
        row.mainIssue,
      );

      const lift = Math.max(2.0, round1(91.5 - row.score));
      const teamLift = round1(lift / Math.max(1, headcount));

      return {
        id: savedAction?.id ?? `ind-${teamSlug}-${idx}`,
        employeeId: row.employeeId,
        agentName: row.agentName,
        score: row.score,
        grade: row.grade,
        gradeFullLabel: row.gradeFullLabel,
        mainIssue: savedAction?.root_cause_note || row.mainIssue,
        actionText: savedAction?.action_text || recommended.actionText,
        owner:
          savedAction?.owner?.name ||
          (savedAction ? mapWeakestKpiToOwner(row.weakestKpiKey, row.weakestKpiLabel) : recommended.owner),
        expectedImpact: `+${lift.toFixed(1)}% agent score (+${teamLift.toFixed(1)}% team lift)`,
        linkedKpiKey: row.weakestKpiKey,
        isSavedToStore: Boolean(savedAction),
      };
    },
  );

  return withCallCenterNav({
    teamSlug: normalizedSlug,
    canonicalTeam,
    teamDisplayName: `${canonicalTeam} Agents`,
    functionName: 'Call Center',
    regionCode: region,
    regionName: region === 'EGY' ? 'Offshore Egypt' : 'UAE Region',
    monthLabel: `${effective.month} ${effective.year}`,
    previousMonthLabel: previous?.month ?? 'August',
    periodKey: effective.key,
    summary: {
      score,
      grade,
      gradeFullLabel: gradeFull,
      target: 100.0,
      gap: round1(score - 100),
      changeVsPrev,
      headcount,
      averageOrBelowCount: agentsAverageOrBelow.length,
      diagnosis: fallback.summary.diagnosis,
    },
    kpis,
    agentsAverageOrBelow,
    individualActionPlans,
    teamActionPlans: fallback.teamActionPlans,
  }, region);
}
