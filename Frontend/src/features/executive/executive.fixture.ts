/**
 * Deterministic fixtures for the Executive / Function Summary (tests and the
 * screenshot harness). Shapes mirror the live endpoints: performance records
 * (`AgentRecord`), the Insights workspace drivers and follow-up actions.
 * Not imported by product code.
 */
import type { AgentRecord } from '../../types';
import type { InsightDriver, InsightItem } from '../insights/types';
import type { TeamFunctionMap } from '../insights/filterCascade';
import { MONTHS, localIsoDate, type FollowUpAction } from './compose';

type Dir = 'higher_better' | 'lower_better';
interface KpiDef { key: string; label: string; unit: string; direction: Dir; target: number; weight: number; tilt: number }
interface TeamDef { team: string; region: 'EGY' | 'UAE'; headcount: number; scores: number[]; kpis: KpiDef[] }

const CC_KPIS: KpiDef[] = [
  { key: 'abandon_rate', label: 'Abandon Rate', unit: '%', direction: 'lower_better', target: 5, weight: 0.15, tilt: -12 },
  { key: 'aht', label: 'Average Handle Time', unit: 's', direction: 'lower_better', target: 360, weight: 0.25, tilt: -4 },
  { key: 'fcr', label: 'First Call Resolution', unit: '%', direction: 'higher_better', target: 80, weight: 0.2, tilt: -1 },
  { key: 'qa_score', label: 'QA Score', unit: '%', direction: 'higher_better', target: 90, weight: 0.25, tilt: 6 },
  { key: 'schedule_adherence', label: 'Schedule Adherence', unit: '%', direction: 'higher_better', target: 92, weight: 0.15, tilt: 14 },
];
const RCM_KPIS: KpiDef[] = [
  { key: 'clean_claim_rate', label: 'Clean Claim Rate', unit: '%', direction: 'higher_better', target: 95, weight: 0.4, tilt: 4 },
  { key: 'denial_rate', label: 'Denial Rate', unit: '%', direction: 'lower_better', target: 5, weight: 0.3, tilt: -3 },
  { key: 'tat_days', label: 'Turnaround Time', unit: 'days', direction: 'lower_better', target: 3, weight: 0.3, tilt: -6 },
];
const PA_KPIS: KpiDef[] = [
  { key: 'initial_rejection', label: 'Initial Rejection %', unit: '%', direction: 'lower_better', target: 8, weight: 0.4, tilt: -10 },
  { key: 'approval_tat', label: 'Approval TAT', unit: 'min', direction: 'lower_better', target: 45, weight: 0.3, tilt: -2 },
  { key: 'pa_accuracy', label: 'Accuracy', unit: '%', direction: 'higher_better', target: 97, weight: 0.3, tilt: 5 },
];
const MKT_KPIS: KpiDef[] = [
  { key: 'response_rate', label: 'Response Rate', unit: '%', direction: 'higher_better', target: 90, weight: 0.5, tilt: 4 },
  { key: 'cpl', label: 'Cost per Lead', unit: 'AED', direction: 'lower_better', target: 120, weight: 0.5, tilt: -2 },
];
const CSR_KPIS: KpiDef[] = [
  { key: 'queries_handled', label: 'Queries Handled', unit: '%', direction: 'higher_better', target: 100, weight: 0.6, tilt: -4 },
  { key: 'rejection', label: 'Rejection', unit: '%', direction: 'lower_better', target: 5, weight: 0.4, tilt: -8 },
];

export const FIXTURE_TEAMS: TeamDef[] = [
  { team: 'Inbound', region: 'EGY', headcount: 12, scores: [85.4, 86.2, 87.0, 87.6, 87.1, 86.0], kpis: CC_KPIS },
  { team: 'Outbound', region: 'EGY', headcount: 8, scores: [88.0, 88.4, 87.2, 87.9, 88.3, 88.9], kpis: CC_KPIS },
  { team: 'Call Center', region: 'UAE', headcount: 6, scores: [80.5, 81.0, 79.4, 80.2, 78.8, 77.9], kpis: CC_KPIS },
  { team: 'Coding', region: 'EGY', headcount: 8, scores: [86.0, 86.5, 87.2, 87.9, 88.6, 90.4], kpis: RCM_KPIS },
  { team: 'Submission', region: 'EGY', headcount: 7, scores: [87.5, 87.1, 88.0, 88.4, 88.0, 90.6], kpis: RCM_KPIS },
  { team: 'Re-Submission', region: 'EGY', headcount: 6, scores: [84.0, 84.6, 85.1, 85.0, 84.2, 86.0], kpis: RCM_KPIS },
  { team: 'Pre-Approvals IP Offshore', region: 'EGY', headcount: 5, scores: [88.2, 88.0, 87.6, 88.9, 89.1, 89.8], kpis: PA_KPIS },
  { team: 'Pre-Approvals OP Final', region: 'UAE', headcount: 6, scores: [84.5, 84.0, 83.6, 83.9, 83.5, 81.3], kpis: PA_KPIS },
  { team: 'Pre-Approvals IP Final Dubai', region: 'UAE', headcount: 6, scores: [80.0, 79.1, 78.4, 79.0, 76.4, 74.2], kpis: PA_KPIS },
  { team: 'Pre-Approvals IP Elective', region: 'UAE', headcount: 4, scores: [85.0, 84.6, 85.2, 84.8, 84.1, 83.4], kpis: PA_KPIS },
  { team: 'Marketing', region: 'EGY', headcount: 5, scores: [90.0, 90.6, 91.2, 91.0, 91.6, 93.4], kpis: MKT_KPIS },
  { team: 'Content', region: 'EGY', headcount: 3, scores: [91.0, 91.5, 92.0, 92.4, 91.8, 92.9], kpis: MKT_KPIS },
  { team: 'CSR', region: 'UAE', headcount: 5, scores: [73.0, 72.4, 71.8, 72.6, 70.9, 68.4], kpis: CSR_KPIS },
];

/** Backend `options.team_functions` (PR #14): UAE pre-approvals under both, CSR its own function. */
export const FIXTURE_TEAM_FUNCTIONS: TeamFunctionMap = {
  Inbound: ['Call Center'],
  Outbound: ['Call Center'],
  'Call Center': ['Call Center'],
  Coding: ['RCM'],
  Submission: ['RCM'],
  'Re-Submission': ['RCM'],
  'Pre-Approvals IP Offshore': ['RCM', 'Pre-Approvals'],
  'Pre-Approvals OP Final': ['RCM', 'Pre-Approvals'],
  'Pre-Approvals IP Final Dubai': ['RCM', 'Pre-Approvals'],
  'Pre-Approvals IP Elective': ['RCM', 'Pre-Approvals'],
  Marketing: ['Marketing'],
  Content: ['Marketing'],
  CSR: ['CSR'],
};

const FIRST = ['Ahmed', 'Nour', 'Karim', 'Yara', 'Omar', 'Salma', 'Hossam', 'Reem', 'Mariam', 'Youssef', 'Dina', 'Tamer', 'Rania', 'Hany', 'Mona', 'Sara', 'Ali', 'Laila'];
const LAST = ['Fawzy', 'El-Sayed', 'Adel', 'Hassan', 'Khaled', 'Reda', 'Tarek', 'Gamal', 'Samir', 'Mostafa', 'Fouad', 'Saleh', 'Adly', 'Nabil'];
const POSITIONS = ['Agent L1', 'Agent L2', 'Agent L1', 'Senior Agent', 'Agent L2', 'Team Lead'];

const round = (value: number, digits = 2) => Number(value.toFixed(digits));

export interface FixtureOptions {
  months?: number;
  year?: number;
  teams?: TeamDef[];
}

/** AgentRecord-shaped performance rows (only the fields the Executive page reads). */
export function fixtureAgentRecords({ months = 6, year = 2026, teams = FIXTURE_TEAMS }: FixtureOptions = {}): AgentRecord[] {
  const rows: AgentRecord[] = [];
  let seq = 0;
  teams.forEach((team, teamIndex) => {
    const offsets = Array.from({ length: team.headcount }, (_, index) => (team.headcount === 1 ? 0 : -9 + (18 * index) / (team.headcount - 1)));
    for (let monthIndex = 0; monthIndex < months; monthIndex += 1) {
      offsets.forEach((offset, index) => {
        const drift = ((index * 7 + monthIndex * 3 + teamIndex) % 5) - 2;
        const score = Math.max(40, Math.min(100, team.scores[monthIndex] + offset + drift * 0.6));
        const id = `E${String(teamIndex).padStart(2, '0')}${String(index).padStart(2, '0')}`;
        const name = `${FIRST[(teamIndex * 3 + index) % FIRST.length]} ${LAST[(teamIndex + index * 5) % LAST.length]}`;
        const kpis = team.kpis.map((kpi) => {
          const achievement = Math.max(0.3, Math.min(1.12, (score + kpi.tilt) / 100));
          const actual = kpi.direction === 'higher_better' ? kpi.target * achievement : kpi.target / achievement;
          return {
            kpi_key: kpi.key, label: kpi.label, unit: kpi.unit, direction: kpi.direction,
            actual_value: round(actual), target_value: kpi.target, achievement_ratio: round(Math.min(achievement, 1), 4),
            weight_applied: kpi.weight, contribution: round(Math.min(achievement, 1) * kpi.weight, 4),
          };
        });
        seq += 1;
        rows.push({
          year,
          region: team.region,
          position: POSITIONS[index % POSITIONS.length],
          performance_level: 'Employee',
          identity: { name, month: MONTHS[monthIndex], team: team.team, employee_id: id, position: POSITIONS[index % POSITIONS.length], region: team.region },
          evaluation: { score: round(score / 100, 4) },
          kpi_values: kpis,
          // Enough of the legacy shape for usePerformanceData consumers.
          calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
          geo: { bookings: {}, attended: {} },
          actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
          _seq: seq,
        } as unknown as AgentRecord);
      });
    }
  });
  return rows;
}

interface DriverSeed { kpi: string; label: string; team: string; position: string; impact: number; weighted?: number; change?: number; direction: Dir; unit: string; current: number; previous: number }

const DRIVER_SEEDS: DriverSeed[] = [
  { kpi: 'initial_rejection', label: 'Initial Rejection %', team: 'Pre-Approvals IP Final', position: 'Agent L1', impact: -0.42, weighted: -4.8, direction: 'lower_better', unit: '%', current: 9.8, previous: 8.2 },
  { kpi: 'aht', label: 'Average Handle Time', team: 'Inbound', position: 'Agent L1', impact: -0.31, weighted: -2.1, direction: 'lower_better', unit: 's', current: 440, previous: 418 },
  { kpi: 'fcr', label: 'First Call Resolution', team: 'Call Center', position: 'Agent L2', impact: -0.24, weighted: -3.2, direction: 'higher_better', unit: '%', current: 71, previous: 74 },
  { kpi: 'rejection', label: 'Rejection', team: 'CSR', position: 'Agent L1', impact: -0.2, weighted: -5.6, direction: 'lower_better', unit: '%', current: 7.9, previous: 7.1 },
  { kpi: 'clean_claim_rate', label: 'Clean Claim Rate', team: 'Submission', position: 'Agent L1', impact: 0.38, change: 1.9, direction: 'higher_better', unit: '%', current: 96.4, previous: 94.3 },
  { kpi: 'denial_rate', label: 'Denial Rate', team: 'Coding', position: 'Agent L2', impact: 0.29, change: 1.2, direction: 'lower_better', unit: '%', current: 4.1, previous: 4.9 },
  { kpi: 'response_rate', label: 'Response Rate', team: 'Marketing', position: 'Agent L1', impact: 0.21, change: 0.8, direction: 'higher_better', unit: '%', current: 92, previous: 88 },
];

/** Insights workspace drivers + their items (PR #15 `detail` fields). */
export function fixtureDrivers({ weightedGap = false, includeDetail = true }: { weightedGap?: boolean; includeDetail?: boolean } = {}): { drivers: InsightDriver[]; items: InsightItem[] } {
  const drivers = DRIVER_SEEDS.map((seed, index) => ({
    driver: seed.label,
    scope: `${seed.team} · ${seed.position}`,
    impact_points: seed.impact,
    direction: seed.impact < 0 ? 'negative' : 'positive',
    insight_id: `ins-${index}`,
    kpi_direction: seed.direction,
    ...(weightedGap ? { weighted_gap_points: seed.weighted ?? 0, impact_change_points: seed.change ?? 0 } : {}),
  })) as unknown as InsightDriver[];
  const items = DRIVER_SEEDS.map((seed, index) => {
    const raw = seed.current - seed.previous;
    const changeValue = seed.direction === 'lower_better' ? -raw : raw;
    return {
      id: `ins-${index}`,
      team: seed.team,
      kpi_key: seed.kpi,
      detail: includeDetail ? {
        direction: seed.direction, unit: seed.unit, current_value: seed.current, previous_value: seed.previous,
        raw_change: round(raw), change_value: round(changeValue), trend_status: changeValue > 0 ? 'improving' : 'declining',
      } : undefined,
    };
  }) as unknown as InsightItem[];
  return { drivers, items };
}

/** Follow-up actions relative to `today` (overdue, due this week, open, completed in June). */
export function fixtureActions(today: Date, year = 2026): FollowUpAction[] {
  const day = (offset: number) => localIsoDate(new Date(today.getFullYear(), today.getMonth(), today.getDate() + offset));
  return [
    { id: 1, title: 'FCR recovery — QA coaching plan', team: 'Call Center', region: 'UAE', owner: { id: 'u1', name: 'Rania Saleh' }, due_date: day(-6), status: 'Open', follow_up_state: 'overdue' },
    { id: 2, title: 'Payer-mix rejection root-cause review', team: 'Pre-Approvals IP Final', region: 'UAE', owner: { id: 'u2', name: 'Tamer Fouad' }, due_date: day(-4), status: 'In Progress', follow_up_state: 'overdue' },
    { id: 3, title: 'Peak-hour staffing review (AHT)', team: 'Inbound', region: 'EGY', employee_name: null, owner: { id: 'u3', name: 'Hany Mostafa' }, due_date: day(3), status: 'Open', follow_up_state: 'due_soon' },
    { id: 4, title: 'Performance improvement plan', team: 'Inbound', region: 'EGY', employee_name: 'Ahmed Fawzy', owner: { id: 'u3', name: 'Hany Mostafa' }, due_date: day(-1), status: 'Open', follow_up_state: 'overdue' },
    { id: 5, title: 'Re-submission SLA checklist', team: 'Re-Submission', region: 'EGY', owner: { id: 'u4', name: 'Mona Adel' }, due_date: day(4), status: 'In Progress', follow_up_state: 'due_soon' },
    { id: 6, title: 'AHT call-flow coaching', team: 'Inbound', region: 'EGY', employee_name: 'Nour El-Sayed', owner: { id: 'u3', name: 'Hany Mostafa' }, due_date: day(5), status: 'Open', follow_up_state: 'due_soon' },
    { id: 7, title: 'Coding audit sampling', team: 'Coding', region: 'EGY', owner: { id: 'u5', name: 'Sara Nabil' }, due_date: day(20), status: 'Open', follow_up_state: 'on_track' },
    { id: 8, title: 'QA calibration session', team: 'Inbound', region: 'EGY', employee_name: 'Karim Adel', owner: { id: 'u3', name: 'Hany Mostafa' }, due_date: `${year}-06-28`, status: 'Completed', follow_up_state: 'completed', completed_at: `${year}-06-28T10:00:00` },
    { id: 9, title: 'Denial follow-up script', team: 'Coding', region: 'EGY', owner: { id: 'u5', name: 'Sara Nabil' }, due_date: `${year}-06-20`, status: 'Completed', follow_up_state: 'completed', completed_at: `${year}-06-19T10:00:00` },
  ];
}
