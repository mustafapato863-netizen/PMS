import type { TeamAgentRow } from '../hooks/usePerformanceData';
import type { AgentRecord } from '../types';
import { normalizeScore } from '../hooks/usePerformanceData';

/** Calculates the employee's rank within the entire team for the selected month */
export function calculateRank(employeeId: string, teamMembers: TeamAgentRow[]): number {
  if (!teamMembers || teamMembers.length === 0) return 0;
  const sorted = [...teamMembers].sort((a, b) => b.score - a.score);
  const index = sorted.findIndex(m => m.id === employeeId);
  return index >= 0 ? index + 1 : 0;
}

/** Calculates the percentile of the employee within the team */
export function calculatePercentile(rank: number, totalEmployees: number): number {
  if (totalEmployees <= 1 || rank === 0) return 100;
  // Formula: (Employees below employee / total employees) * 100
  const employeesBelow = totalEmployees - rank;
  return Math.round((employeesBelow / totalEmployees) * 100);
}

export type StabilityCategory = 'Stable' | 'Improving' | 'Volatile' | 'Declining';

interface PerformanceHistoryRecord {
  month: string;
  evaluation: {
    score: number;
    grade: string;
  };
}

/** Calculates performance stability index based on score history */
export function calculateStability(history: PerformanceHistoryRecord[]): StabilityCategory {
  if (!history || history.length < 2) return 'Stable';
  
  // Sort by month (assuming chronological order in history is present or sorting needed)
  // We'll just look at the raw evaluation scores.
  const scores = history.map(h => {
    return normalizeScore(h.evaluation.score);
  });

  const recent = scores.slice(-3);
  if (recent.length < 2) return 'Stable';
  
  const diffs = [];
  for (let i = 1; i < recent.length; i++) {
    diffs.push(recent[i] - recent[i - 1]);
  }

  const avgDiff = diffs.reduce((a, b) => a + b, 0) / diffs.length;
  const maxDiff = Math.max(...diffs.map(Math.abs));

  if (maxDiff > 20) return 'Volatile';
  if (avgDiff > 5) return 'Improving';
  if (avgDiff < -5) return 'Declining';
  return 'Stable';
}

/** Counts consecutive A grades from recent history (assuming history is chronological descending) */
export function calculateConsecutiveGrades(history: PerformanceHistoryRecord[], targetGrade: string = 'A'): number {
  if (!history) return 0;
  let count = 0;
  for (const record of history) {
    if (record.evaluation.grade === targetGrade) {
      count++;
    } else {
      break;
    }
  }
  return count;
}

/** Finds the employee's personal best historical month */
export function calculatePeakMonth(history: PerformanceHistoryRecord[]): { month: string, score: number, grade: string } | null {
  if (!history || history.length === 0) return null;
  let peak = history[0];
  let maxScore = normalizeScore(peak.evaluation.score);

  for (const record of history) {
    const score = normalizeScore(record.evaluation.score);
    if (score > maxScore) {
      maxScore = score;
      peak = record;
    }
  }

  return {
    month: peak.month,
    score: maxScore,
    grade: peak.evaluation.grade
  };
}

export type PerformanceArchetype = 
  | 'The Finisher' 
  | 'The Revenue Driver' 
  | 'The Workhorse' 
  | 'The Consistent Performer' 
  | 'The Rising Star' 
  | 'The Specialist'
  | 'Balanced Performer';

/** Classifies an employee into an archetype based on their KPIs and history */
export function getPerformanceArchetype(employee: TeamAgentRow, history: PerformanceHistoryRecord[]): PerformanceArchetype {
  const actual = employee.raw.actual || {};
  const ach = employee.raw.achievement || {};
  const stability = calculateStability(history);

  // Example logic based on common KPI names
  const bookingAch = ach.booking_ach || actual.booking_rate || 0;
  const attendAch = ach.attend_ach || actual.attend_rate || 0;
  const isSales = employee.team === 'Sales';
  
  if (stability === 'Improving' && employee.score > 80) return 'The Rising Star';
  if (stability === 'Stable' && employee.score > 85) return 'The Consistent Performer';
  
  if (isSales) {
    const revAch = (ach.op_revenue_ach || 0) + (ach.ip_revenue_ach || 0);
    const censusAch = (ach.op_census_ach || 0) + (ach.ip_census_ach || 0);
    if (revAch > 1.2 && revAch > censusAch) return 'The Revenue Driver';
    if (censusAch > 1.2 && censusAch > revAch) return 'The Finisher';
  } else {
    if (bookingAch > 0.8) return 'The Finisher';
    if (attendAch > 0.95 && employee.score > 80) return 'The Workhorse';
  }

  if (employee.score > 90) return 'The Specialist';
  return 'Balanced Performer';
}

/** Generates a human-readable root cause narrative comparing the employee to a benchmark */
export function generateRootCauseNarrative(employee: TeamAgentRow, benchmark: AgentRecord | null, mode: 'team_best' | 'team_avg' | 'personal_best' | 'none'): string[] {
  if (mode === 'none' || !benchmark) return [];
  
  const narratives: string[] = [];
  const empScore = employee.score;
  const benchScore = normalizeScore(benchmark.evaluation.score);
  
  const gap = empScore - benchScore;
  
  if (mode === 'team_best') {
    if (gap >= 0) {
      narratives.push(`Outstanding performance! This employee is currently setting the benchmark for the team.`);
      return narratives;
    }
    narratives.push(`Overall performance is ${Math.abs(gap).toFixed(1)}% below the team leader.`);
  } else if (mode === 'team_avg') {
    if (gap > 0) {
      narratives.push(`Performing ${Math.abs(gap).toFixed(1)}% above the team average.`);
    } else {
      narratives.push(`Performance is ${Math.abs(gap).toFixed(1)}% below the team average.`);
    }
  } else if (mode === 'personal_best') {
    if (gap >= 0) {
      narratives.push(`Employee is currently at their peak performance!`);
    } else {
      narratives.push(`Current score is ${Math.abs(gap).toFixed(1)}% below their historical peak.`);
    }
  }

  // Deep dive into KPIs (using raw data to find gaps)
  const eAch = employee.raw.achievement || {};
  const bAch = benchmark.achievement || {};
  
  let largestGapKpi = '';
  let largestGapValue = 0;
  
  const checkGap = (key: string, name: string) => {
    const eVal = eAch[key as keyof typeof eAch] || 0;
    const bVal = bAch[key as keyof typeof bAch] || 0;
    const kpiGap = eVal - bVal;
    if (kpiGap < largestGapValue) {
      largestGapValue = kpiGap;
      largestGapKpi = name;
    }
  };

  if (employee.team === 'Sales') {
    checkGap('op_revenue_ach', 'OP Revenue');
    checkGap('ip_revenue_ach', 'IP Revenue');
    checkGap('op_census_ach', 'OP Census');
    checkGap('ip_census_ach', 'IP Census');
    checkGap('activity_ach', 'Activity Score');
  } else {
    checkGap('booking_ach', 'Booking Rate');
    checkGap('attend_ach', 'Attendance');
    checkGap('quality_ach', 'Quality');
  }

  if (largestGapValue < -0.1) {
    narratives.push(`${largestGapKpi} is currently the largest performance gap.`);
  }

  return narratives;
}
