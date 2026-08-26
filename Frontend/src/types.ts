// --- Core Data Types ---

export type { GradeClass } from './constants/grades';

export type RawData = Record<string, string>;

export interface AgentRecord {
  raw_data?: RawData;
  region?: string;
  year?: number;
  position?: string | null;
  status?: 'Exceeds' | 'Meets' | 'Below' | string | null;
  performance_level?: PerformanceLevel;
  kpi_values?: Array<{
    kpi_key: string;
    label: string;
    perspective?: string;
    unit: string;
    color?: string;
    direction: 'higher_better' | 'lower_better';
    actual_value: number;
    target_value: number;
    achievement_ratio: number;
    weight_applied: number;
    contribution: number;
    cap_achievement?: boolean;
  }>;
  identity: {
    name: string;
    month: string;
    team?: string;
    employee_id?: string;
    position?: string | null;
    region?: string;
  };
  calls: {
    inbound: number;
    outbound: number;
    total_handled: number;
    total_calls?: number;
    abandoned: number;
    aht_raw: string; // "HH:MM:SS"
  };
  geo: {
    bookings: GeoBreakdown;
    attended: GeoBreakdown;
  };
  actual: {
    booking_rate: number;   // 0-1 float
    attend_rate: number;    // 0-1 float
    abandon_rate: number;   // 0-1 float
    reachability_rate?: number;
    rejection_rate?: number;
    initial_error_rate?: number;
    submission_rate?: number;
    quality_rate?: number;
    utz_rate?: number;
  };
  achievement: {
    booking_ach: number;
    attend_ach: number;
    quality_ach?: number;
    aht_ach?: number;
    reachability_ach?: number;
    abandon_ach?: number;
    rejection_ach?: number;
    initial_error_ach?: number;
    submission_ach?: number;
    op_census_ach?: number;
    op_revenue_ach?: number;
    ip_census_ach?: number;
    ip_revenue_ach?: number;
    activity_ach?: number;
  };
  evaluation: {
    score: number;   // 0-1 float from backend (multiply ×100 for %)
    grade: string;   // "Meet Expectations", "Exceeds Expectations", "Average", "Below average", "PI", "SIP"
    root_cause?: { kpi: string; impact_pct: number; actual: number; target: number } | null;
    suggested_action?: string | null;
    corrective_action?: string | null;
    manager_notes?: string | null;
    planning_category?: string[];
    trend_status?: string;
  };
}

export interface GeoBreakdown {
  dubai: number;
  sharjah: number;
  ajman: number;
  clinics: number;
}

export type LocationKey = 'all' | 'dubai' | 'sharjah' | 'ajman' | 'clinics';
export type MonthKey = 'All' | string;
export type PerformanceLevel = 'Employee' | 'Managerial' | 'Corporate';
export type PerformanceLevelFilter = 'All' | PerformanceLevel;

/** UAE pre-approval workflows shown under the shared Pre-Approvals parent. */
export type PreApprovalsWorkflowFilter = 'all' | 'ip_final' | 'op_final' | 'ip_elective';
export const PRE_APPROVALS_UAE_TEAM = 'Pre-Approvals';
export const PRE_APPROVALS_UAE_TEAM_ID = 'pre-approvals-uae';
export const PRE_APPROVALS_UAE_SOURCE_TEAMS = [
  'Pre-Approvals OP Dubai',
  'Pre-Approvals OP Final SHJAJM',
  'Pre-Approvals IP Final Dubai',
  'Pre-Approvals IP Final SHJAJM',
  'Pre-Approvals IP Elective Dubai',
] as const;

const PRE_APPROVALS_WORKFLOW_TEAMS: Record<Exclude<PreApprovalsWorkflowFilter, 'all'>, readonly string[]> = {
  op_final: ['Pre-Approvals OP Final', 'Pre-Approvals OP Dubai', 'Pre-Approvals OP Final SHJAJM'],
  ip_final: ['Pre-Approvals IP Final', 'Pre-Approvals IP Final Dubai', 'Pre-Approvals IP Final SHJAJM'],
  ip_elective: ['Pre-Approvals IP Elective', 'Pre-Approvals IP Elective Dubai'],
};

export const PRE_APPROVALS_WORKFLOW_LABELS: Record<PreApprovalsWorkflowFilter, string> = {
  all: 'All Workflows',
  ip_final: 'IP Final',
  op_final: 'OP Final',
  ip_elective: 'IP Elective',
};

const normalizeTeamIdentity = (value: string | null | undefined) =>
  String(value ?? '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '');

export function isPreApprovalsUaeTeam(value: string | null | undefined): boolean {
  const normalized = normalizeTeamIdentity(value);
  return normalized === normalizeTeamIdentity(PRE_APPROVALS_UAE_TEAM)
    || PRE_APPROVALS_UAE_SOURCE_TEAMS.some((team) => normalized === normalizeTeamIdentity(team))
    || Object.values(PRE_APPROVALS_WORKFLOW_TEAMS).some((teams) => teams.some((team) => normalized === normalizeTeamIdentity(team)));
}

export function preApprovalsWorkflowForTeam(value: string | null | undefined): Exclude<PreApprovalsWorkflowFilter, 'all'> | null {
  const normalized = normalizeTeamIdentity(value);
  const match = (Object.entries(PRE_APPROVALS_WORKFLOW_TEAMS) as Array<[Exclude<PreApprovalsWorkflowFilter, 'all'>, readonly string[]]>)
    .find(([, teams]) => teams.some((team) => normalizeTeamIdentity(team) === normalized));
  return match?.[0] ?? null;
}

export function isPreApprovalsWorkflowTeam(value: string | null | undefined, workflow: PreApprovalsWorkflowFilter): boolean {
  return workflow === 'all' ? isPreApprovalsUaeTeam(value) : preApprovalsWorkflowForTeam(value) === workflow;
}

export function isPreApprovalsIpElectiveTeam(value: string | null | undefined): boolean {
  const normalized = normalizeTeamIdentity(value);
  return normalized === normalizeTeamIdentity('Pre-Approvals IP Elective')
    || normalized === normalizeTeamIdentity('Pre-Approvals IP Elective Dubai');
}

/** Call-center channels shown under the shared Call Center parent. */
export type CallCenterChannelFilter = 'all' | 'inbound' | 'outbound';
export const CALL_CENTER_TEAM = 'Call Center';
export const CALL_CENTER_TEAM_ID = 'call-center';
export const CALL_CENTER_SOURCE_TEAMS = ['Inbound', 'Outbound'] as const;
export const CALL_CENTER_CHANNEL_LABELS: Record<CallCenterChannelFilter, string> = {
  all: 'All Channels',
  inbound: 'Inbound',
  outbound: 'Outbound',
};

export function isCallCenterTeam(value: string | null | undefined): boolean {
  const normalized = normalizeTeamIdentity(value);
  return normalized === normalizeTeamIdentity(CALL_CENTER_TEAM)
    || CALL_CENTER_SOURCE_TEAMS.some((team) => normalized === normalizeTeamIdentity(team));
}

export function callCenterChannelForTeam(value: string | null | undefined): Exclude<CallCenterChannelFilter, 'all'> | null {
  const normalized = normalizeTeamIdentity(value);
  if (normalized === normalizeTeamIdentity('Inbound')) return 'inbound';
  if (normalized === normalizeTeamIdentity('Outbound')) return 'outbound';
  return null;
}

export function isCallCenterChannelTeam(value: string | null | undefined, channel: CallCenterChannelFilter): boolean {
  return channel === 'all' ? isCallCenterTeam(value) : callCenterChannelForTeam(value) === channel;
}

/** Revenue Cycle Management domains shown under one shared function. */
export type RcmDomainFilter = 'all' | 'pre_approvals' | 'submission' | 're_submission' | 'coding';
export type RcmGroupFilter = 'all' | 'offshore_egy' | 'uae';
export const RCM_TEAM = 'RCM';
export const RCM_TEAM_ID = 'rcm';
export const RCM_DOMAIN_LABELS: Record<RcmDomainFilter, string> = {
  all: 'All RCM Domains',
  pre_approvals: 'Pre-Approvals',
  submission: 'Submission',
  re_submission: 'Re-Submission',
  coding: 'Coding',
};
export const RCM_GROUP_LABELS: Record<RcmGroupFilter, string> = {
  all: 'All RCM Groups',
  offshore_egy: 'Offshore EGY',
  uae: 'UAE',
};

const RCM_DOMAIN_TEAMS: Record<Exclude<RcmDomainFilter, 'all'>, readonly string[]> = {
  pre_approvals: [
    'Pre-Approvals',
    'Pre-Approvals IP Offshore',
    ...PRE_APPROVALS_UAE_SOURCE_TEAMS,
    'Pre-Approvals IP Elective',
  ],
  submission: ['Submission'],
  re_submission: ['Re-Submission'],
  coding: ['Coding'],
};

export function rcmGroupForTeam(value: string | null | undefined, region?: string | null): Exclude<RcmGroupFilter, 'all'> | null {
  if (!isRcmTeam(value)) return null;
  const normalizedRegion = String(region ?? '').trim().toLowerCase();
  if (normalizedRegion.includes('egy') || normalizedRegion.includes('offshore')) return 'offshore_egy';
  if (normalizedRegion.includes('uae') || normalizedRegion.includes('united arab')) return 'uae';
  return normalizeTeamIdentity(value) === normalizeTeamIdentity('Pre-Approvals IP Offshore') ? 'offshore_egy' : 'uae';
}

export function isRcmGroupTeam(value: string | null | undefined, group: RcmGroupFilter, region?: string | null): boolean {
  return group === 'all' ? isRcmTeam(value) : rcmGroupForTeam(value, region) === group;
}

export function rcmDomainForTeam(value: string | null | undefined): Exclude<RcmDomainFilter, 'all'> | null {
  const normalized = normalizeTeamIdentity(value);
  const match = (Object.entries(RCM_DOMAIN_TEAMS) as Array<[Exclude<RcmDomainFilter, 'all'>, readonly string[]]>)
    .find(([, teams]) => teams.some((team) => normalizeTeamIdentity(team) === normalized));
  return match?.[0] ?? null;
}

export function isRcmTeam(value: string | null | undefined): boolean {
  return normalizeTeamIdentity(value) === normalizeTeamIdentity(RCM_TEAM) || rcmDomainForTeam(value) !== null;
}

export function isRcmDomainTeam(value: string | null | undefined, domain: RcmDomainFilter): boolean {
  return domain === 'all' ? isRcmTeam(value) : rcmDomainForTeam(value) === domain;
}

/**
 * Final Pre-Approvals workstreams are user-facing merged teams backed by
 * source workbooks. Keep source names for data compatibility, but use one
 * logical identity wherever the user navigates or aggregates performance.
 */
export const MERGED_OP_FINAL_TEAM = 'Pre-Approvals OP Final';
export const MERGED_OP_FINAL_SOURCE_TEAMS = [
  'Pre-Approvals OP Dubai',
  'Pre-Approvals OP Final SHJAJM',
] as const;
export const MERGED_IP_FINAL_TEAM = 'Pre-Approvals IP Final';
export const MERGED_IP_FINAL_SOURCE_TEAMS = [
  'Pre-Approvals IP Final Dubai',
  'Pre-Approvals IP Final SHJAJM',
] as const;

export function canonicalTeamName(value: string | null | undefined): string {
  const normalized = String(value ?? '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '');
  if (normalized === 'preapprovalsopdubai' || normalized === 'preapprovalsopfinalshjajm') {
    return MERGED_OP_FINAL_TEAM;
  }
  if (normalized === 'preapprovalsipfinaldubai' || normalized === 'preapprovalsipfinalshjajm') {
    return MERGED_IP_FINAL_TEAM;
  }
  return String(value ?? '').trim();
}

export function isMergedOpFinalTeam(value: string | null | undefined): boolean {
  return canonicalTeamName(value) === MERGED_OP_FINAL_TEAM;
}

export function isMergedIpFinalTeam(value: string | null | undefined): boolean {
  return canonicalTeamName(value) === MERGED_IP_FINAL_TEAM;
}

export function isMergedBranchTeam(value: string | null | undefined): boolean {
  return isMergedOpFinalTeam(value) || isMergedIpFinalTeam(value);
}

export function sameCanonicalTeam(left: string | null | undefined, right: string | null | undefined): boolean {
  const preApprovalsParentLeft = normalizeTeamIdentity(left) === normalizeTeamIdentity(PRE_APPROVALS_UAE_TEAM);
  const preApprovalsParentRight = normalizeTeamIdentity(right) === normalizeTeamIdentity(PRE_APPROVALS_UAE_TEAM);
  if (preApprovalsParentLeft || preApprovalsParentRight) {
    return isPreApprovalsUaeTeam(left) && isPreApprovalsUaeTeam(right);
  }
  const callCenterParentLeft = normalizeTeamIdentity(left) === normalizeTeamIdentity(CALL_CENTER_TEAM);
  const callCenterParentRight = normalizeTeamIdentity(right) === normalizeTeamIdentity(CALL_CENTER_TEAM);
  if (callCenterParentLeft || callCenterParentRight) {
    return isCallCenterTeam(left) && isCallCenterTeam(right);
  }
  const rcmParentLeft = normalizeTeamIdentity(left) === normalizeTeamIdentity(RCM_TEAM);
  const rcmParentRight = normalizeTeamIdentity(right) === normalizeTeamIdentity(RCM_TEAM);
  if (rcmParentLeft || rcmParentRight) {
    return isRcmTeam(left) && isRcmTeam(right);
  }
  return canonicalTeamName(left).toLowerCase() === canonicalTeamName(right).toLowerCase();
}

// --- Grade & Status Logic ---
// GradeClass type and getGradeClass() imported from constants/grades.ts
// This ensures a single source of truth for grade thresholds

export function getStatusFromGrade(grade: string): 'Meet' | 'Average' | 'Below' {
  const normalized = grade.toLowerCase();
  if (normalized.includes('meet') || normalized.includes('exceed')) return 'Meet';
  if (normalized === 'average') return 'Average';
  return 'Below';
}

export function getStatusFromScore(score: number): 'Meet' | 'Average' | 'Below' {
  if (score >= 80) return 'Meet';
  if (score >= 70) return 'Average';
  return 'Below';
}

/** Auto root cause from actual KPIs */
export function computeRootCause(actual: {
  attend_rate: number;
  booking_rate: number;
  aht_minutes?: number;
}): string {
  if (actual.attend_rate < 0.75) return 'Attend ↓ (main issue)';
  if (actual.booking_rate < 0.75) return 'Booking ↓';
  if ((actual.aht_minutes ?? 0) > 5) return 'AHT ↑ (slow)';
  return 'All metrics good';
}

/** Compare current vs previous score → trend label */
export function computeScoreTrend(
  currentScore: number,
  previousScore: number | null
): { label: string; direction: 'up' | 'down' | 'stable'; delta: number } {
  if (previousScore === null) return { label: '→ Stable', direction: 'stable', delta: 0 };
  const delta = currentScore - previousScore;
  if (delta > 2) return { label: `↑ +${delta.toFixed(1)}%`, direction: 'up', delta };
  if (delta < -2) return { label: `↓ ${delta.toFixed(1)}%`, direction: 'down', delta };
  return { label: '→ Stable', direction: 'stable', delta };
}

// --- Team Summary Types (Executive Page) ---

export interface TeamSummary {
  teamId: string;    // URL-safe: "inbound", "outbound", etc.
  teamName: string;  // Display: "Inbound", "Outbound", "Inbound UAE", "Pre-Approvals"
  agentCount: number;
  avgScore: number;
  classA: number;
  classB: number;
  classC: number;
  classD: number;
  classE: number;
}

export const TEAM_ID_MAP: Record<string, string> = {
  [RCM_TEAM]: RCM_TEAM_ID,
  [CALL_CENTER_TEAM]: CALL_CENTER_TEAM_ID,
  'Inbound': 'inbound',
  'Outbound': 'outbound',
  'Inbound UAE': 'inbound-uae',
  'Pre-Approvals IP Offshore': 'pre-approvals',
  'Sales': 'sales',
  'Coding': 'coding',
  'CSR': 'csr',
  'Pharmacy': 'pharmacy',
  'Submission': 'submission',
  'Re-Submission': 're-submission',
  'Pre-Approvals OP Final': 'pre-approvals-op-final',
  'Pre-Approvals IP Final': 'pre-approvals-ip-final',
  [PRE_APPROVALS_UAE_TEAM]: PRE_APPROVALS_UAE_TEAM_ID,
  'Pre-Approvals OP Dubai': 'pre-approvals-op-dubai',
  'Pre-Approvals IP Final Dubai': 'pre-approvals-ip-final-dubai',
  'Pre-Approvals IP Elective Dubai': 'pre-approvals-ip-elective-dubai',
  'Pre-Approvals OP Final SHJAJM': 'pre-approvals-op-final-shj-ajm',
  'Pre-Approvals IP Final SHJAJM': 'pre-approvals-ip-final-shj-ajm',
  'Marketing': 'marketing',
};

export const TEAM_NAME_MAP: Record<string, string> = {
  [RCM_TEAM_ID]: RCM_TEAM,
  [CALL_CENTER_TEAM_ID]: CALL_CENTER_TEAM,
  'inbound': 'Inbound',
  'outbound': 'Outbound',
  'inbound-uae': 'Inbound UAE',
  'pre-approvals': 'Pre-Approvals IP Offshore',
  'sales': 'Sales',
  'coding': 'Coding',
  'csr': 'CSR',
  'pharmacy': 'Pharmacy',
  'submission': 'Submission',
  're-submission': 'Re-Submission',
  'pre-approvals-op-final': 'Pre-Approvals OP Final',
  'pre-approvals-ip-final': 'Pre-Approvals IP Final',
  [PRE_APPROVALS_UAE_TEAM_ID]: PRE_APPROVALS_UAE_TEAM,
  'pre-approvals-op-dubai': 'Pre-Approvals OP Dubai',
  'pre-approvals-ip-final-dubai': 'Pre-Approvals IP Final Dubai',
  'pre-approvals-ip-elective-dubai': 'Pre-Approvals IP Elective',
  'pre-approvals-op-final-shj-ajm': 'Pre-Approvals OP Final SHJAJM',
  'pre-approvals-ip-final-shj-ajm': 'Pre-Approvals IP Final SHJAJM',
  'marketing': 'Marketing',
};

export const TEAM_DB_NAME_MAP: Record<string, string> = {
  [RCM_TEAM_ID]: RCM_TEAM,
  [CALL_CENTER_TEAM_ID]: CALL_CENTER_TEAM,
  'inbound': 'Inbound',
  'outbound': 'Outbound',
  'inbound-uae': 'Inbound UAE',
  'pre-approvals': 'Pre-Approvals IP Offshore',
  'sales': 'Sales',
  'coding': 'Coding',
  'csr': 'CSR',
  'pharmacy': 'Pharmacy',
  'submission': 'Submission',
  're-submission': 'Re-Submission',
  'pre-approvals-op-final': 'Pre-Approvals OP Final',
  'pre-approvals-ip-final': 'Pre-Approvals IP Final',
  [PRE_APPROVALS_UAE_TEAM_ID]: PRE_APPROVALS_UAE_TEAM,
  'pre-approvals-op-dubai': 'Pre-Approvals OP Dubai',
  'pre-approvals-ip-final-dubai': 'Pre-Approvals IP Final Dubai',
  'pre-approvals-ip-elective-dubai': 'Pre-Approvals IP Elective Dubai',
  'pre-approvals-op-final-shj-ajm': 'Pre-Approvals OP Final SHJAJM',
  'pre-approvals-ip-final-shj-ajm': 'Pre-Approvals IP Final SHJAJM',
  'marketing': 'Marketing',
};

// --- Action / CRM Types ---

export type ActionType = 'Training' | 'Reward' | 'PIP' | 'Monitor' | 'Coaching';

export interface PMSAction {
  id: string;
  employee_id: string;
  employee_name: string;
  team: string;
  month: string;
  action_type: ActionType;
  action_text: string;
  root_cause_note: string;
  created_by: string;
  created_at: string;
  synced: boolean; // false = only in localStorage
}

// --- CRM & Employee Management Types (legacy, kept for OperationalView) ---

export type EmployeeStatus = 'SIP' | 'PI' | 'Average' | 'Meet' | 'Exceeds';
export type PlanningCategory = 'Promotion' | 'Reward' | 'Training' | 'PI' | 'SIP' | 'Attrition Risk';
export type Trend = 'Up' | 'Down' | 'Stable';

export interface ActionItem {
  id: string;
  employeeId: string;
  title: string;
  owner: string;
  dueDate: string;
  status: 'Pending' | 'In Progress' | 'Completed';
  notes: string;
  evidenceUrl?: string;
}

export interface EmployeeCRMRecord {
  id: string;
  name: string;
  team: string;
  score: number;
  grade: string;
  status: EmployeeStatus;
  planningCategory: PlanningCategory;
  trend: Trend;
  rootCause: string;
  aiSuggestion: string;
  correctiveAction?: string;
  managerNotes: string;
  recentActions: ActionItem[];
  stats?: AgentRecord;
}

// --- Auth & User Management Types ---
export interface User {
  id: string;
  name: string;
  username: string;
  password?: string;
  role: 'Admin' | 'Manager' | 'Executive' | 'Viewer' | 'Agent';
  is_active?: boolean;
  is_online?: boolean;
  last_seen_at?: string | null;
  employee_id?: string | null;
  accessible_teams?: string[];
  accessible_team_count?: number;
  total_team_count?: number;
  is_general_manager?: boolean;
  is_self_only?: boolean;
}

export interface KPIConfig {
  key?: string;
  label: string;
  actual: number;
  target: number;
  unit: '%' | 'min' | 'number' | 'currency';
  isLowerBetter?: boolean;
  color: string;
  /** UI-normalized percentage on a 0-N scale, e.g. 44.1 means 44.1%. */
  achievement?: number;
  /** Stored KPI weight as a 0-1 ratio. */
  weight?: number;
  /** UI-normalized score contribution, e.g. 4.4 means 4.4%. */
  contribution?: number;
  actualVolume?: number;
  targetVolume?: number;
  volumeUnit?: string;
}

function getTargetValue(raw_data: RawData | undefined, keys: string[], fallback: number): number {
  if (!raw_data) return fallback;
  for (const key of keys) {
    if (raw_data[key] !== undefined && raw_data[key] !== null) {
      const val = Number(raw_data[key]);
      if (!isNaN(val)) {
        return val > 1.0 ? val / 100 : val;
      }
    }
  }
  // Clean key lookup ignoring whitespace, underscores, and dots
  for (const key of keys) {
    const cleanKey = key.toLowerCase().replace(/[\s_.]/g, '');
    for (const [rKey, rVal] of Object.entries(raw_data)) {
      const cleanRKey = rKey.toLowerCase().replace(/[\s_.]/g, '');
      if (cleanRKey === cleanKey && rVal !== undefined && rVal !== null) {
        const val = Number(rVal);
        if (!isNaN(val)) {
          return val > 1.0 ? val / 100 : val;
        }
      }
    }
  }
  return fallback;
}

const PRE_APPROVALS_WORKSTREAMS = {
  ip: {
    name: 'IP Elective',
    keys: ['ip_initial_rejection_rate', 'approval_within_48_hours'],
    definitions: [
      { key: 'ip_initial_rejection_rate', label: 'IP Initial Rejection %', direction: 'lower_better' as const, color: '#EF4444', weight: 0.6, actualKeys: ['A.IPInitialRejectionRate'], targetKeys: ['T.IPInitialRejectionRate'], fallbackTarget: 0.03 },
      { key: 'approval_within_48_hours', label: 'Approval Within 48 Hours %', direction: 'higher_better' as const, color: '#10B981', weight: 0.4, actualKeys: ['A.ApprovalWithin48HoursRate'], targetKeys: ['T.ApprovalWithin48HoursRate'], fallbackTarget: 0.75 },
    ],
  },
  er: {
    name: 'ER / IP Approval',
    keys: ['er_initial_rejection_rate', 'approval_within_1_5_hours'],
    definitions: [
      { key: 'er_initial_rejection_rate', label: 'ER Initial Rejection %', direction: 'lower_better' as const, color: '#EF4444', weight: 0.6, actualKeys: ['A.ERInitialRejectionRate'], targetKeys: ['T.ERInitialRejectionRate'], fallbackTarget: 0.01 },
      { key: 'approval_within_1_5_hours', label: 'Approval Within 1.5 Hours %', direction: 'higher_better' as const, color: '#10B981', weight: 0.4, actualKeys: ['A.ApprovalWithin1.5HoursRate'], targetKeys: ['T.ApprovalWithin1.5HoursRate'], fallbackTarget: 1.0 },
    ],
  },
} as const;

type PreApprovalsWorkstream = keyof typeof PRE_APPROVALS_WORKSTREAMS;

const normalizeWorkstream = (value: unknown): string => String(value ?? '').trim().toLowerCase().replace(/[^a-z0-9]+/g, '');

const normalizeRate = (value: unknown): number | undefined => {
  const numeric = typeof value === 'string' ? Number(value.replace(/%/g, '').replace(/,/g, '').trim()) : Number(value);
  if (!Number.isFinite(numeric)) return undefined;
  return numeric > 1 ? numeric / 100 : numeric;
};

const getRawNumber = (raw: RawData | undefined, keys: readonly string[]): number | undefined => {
  if (!raw) return undefined;
  for (const key of keys) {
    const direct = normalizeRate(raw[key]);
    if (direct !== undefined) return direct;
    const normalizedKey = key.toLowerCase().replace(/[\s_.]/g, '');
    const match = Object.entries(raw).find(([rawKey]) => rawKey.toLowerCase().replace(/[\s_.]/g, '') === normalizedKey);
    if (match) {
      const value = normalizeRate(match[1]);
      if (value !== undefined) return value;
    }
  }
  return undefined;
};

const getRawValue = (raw: RawData | undefined, keys: readonly string[]): unknown => {
  if (!raw) return undefined;
  for (const key of keys) {
    if (raw[key] !== undefined && raw[key] !== null) return raw[key];
    const normalizedKey = key.toLowerCase().replace(/[\s_.]/g, '');
    const match = Object.entries(raw).find(([rawKey]) => rawKey.toLowerCase().replace(/[\s_.]/g, '') === normalizedKey);
    if (match) return match[1];
  }
  return undefined;
};

/** Resolve the two KPI workstreams without relying on a generic/stale KPI list. */
export function resolvePreApprovalsWorkstream(agent: AgentRecord): PreApprovalsWorkstream {
  const position = normalizeWorkstream(agent.position || agent.identity.position);
  if (position.includes('eripapproval') || position.includes('er') && position.includes('approval')) return 'er';
  if (position.includes('ipelective')) return 'ip';

  const keys = new Set((agent.kpi_values || []).map((kpi) => normalizeWorkstream(kpi.kpi_key)));
  if (keys.has('erinitialrejectionrate') || keys.has('approvalwithin15hours')) return 'er';

  const raw = agent.raw_data;
  const turnaroundTarget = getRawNumber(raw, ['T.ERInitialRejectionRate', 'T.ApprovalWithin1.5HoursRate']);
  const explicitTurnaround = getRawNumber(raw, ['T.%OfApprovalwithin48HR/1.5HR', 'T.%OfApprovalwithin48HR1.5HR']);
  if ((turnaroundTarget ?? explicitTurnaround ?? 0) >= 0.95) return 'er';
  return 'ip';
}

const getPreApprovalsCountRatio = (raw: RawData | undefined, numeratorKeys: readonly string[], denominatorKeys: readonly string[]): number | undefined => {
  const numerator = getRawNumber(raw, numeratorKeys);
  const denominator = getRawNumber(raw, denominatorKeys);
  if (numerator === undefined || denominator === undefined || denominator <= 0) return undefined;
  // Count columns must not be interpreted as percentages by normalizeRate.
  const rawNumerator = Number(getRawValue(raw, numeratorKeys));
  const rawDenominator = Number(getRawValue(raw, denominatorKeys));
  if (Number.isFinite(rawNumerator) && Number.isFinite(rawDenominator) && rawDenominator > 0) {
    return Math.max(0, rawNumerator / rawDenominator);
  }
  return Math.max(0, numerator / denominator);
};

type PreApprovalsDefinition = {
  key: string;
  label: string;
  direction: 'lower_better' | 'higher_better';
  color: string;
  weight: number;
  actualKeys: readonly string[];
  targetKeys: readonly string[];
  fallbackTarget: number;
};

function getPreApprovalsActual(agent: AgentRecord, definition: PreApprovalsDefinition): number {
  const rawActual = getRawNumber(agent.raw_data, definition.actualKeys);
  if (rawActual !== undefined) return rawActual;
  if (definition.key.includes('rejection')) {
    return getPreApprovalsCountRatio(agent.raw_data, ['RejectedRequests', 'RejectedRequest'], ['AssignedRequests', 'AssignedRequest']) ?? 0;
  }
  if (definition.key.includes('48')) {
    return getPreApprovalsCountRatio(agent.raw_data, ['ApprovalWithin48HR', 'ApprovalWithin48hrs'], ['ApprovedRequests', 'ApprovedRequest']) ?? 0;
  }
  return getPreApprovalsCountRatio(agent.raw_data, ['ApprovalWithin1.5HR', 'ApprovalWithin1.5Hours'], ['ApprovedRequests', 'ApprovedRequest']) ?? 0;
}

function getPreApprovalsTarget(agent: AgentRecord, definition: PreApprovalsDefinition): number {
  return getRawNumber(agent.raw_data, definition.targetKeys)
    ?? getRawNumber(agent.raw_data, definition.key.includes('rejection')
      ? ['T.InitialRejection%', 'T.InitialRejectionRate']
      : ['T.%OfApprovalwithin48HR/1.5HR', 'T.%OfApprovalwithin48HR1.5HR'])
    ?? definition.fallbackTarget;
}

function buildPreApprovalsKpis(agent: AgentRecord, workstream: PreApprovalsWorkstream): KPIConfig[] {
  const definitionSet = PRE_APPROVALS_WORKSTREAMS[workstream].definitions;
  const persisted = new Map((agent.kpi_values || []).map((kpi) => [normalizeWorkstream(kpi.kpi_key), kpi]));

  return definitionSet.map((definition) => {
    const source = persisted.get(normalizeWorkstream(definition.key));
    const actual = source ? (normalizeRate(source.actual_value) ?? getPreApprovalsActual(agent, definition)) : getPreApprovalsActual(agent, definition);
    const target = source ? (normalizeRate(source.target_value) ?? getPreApprovalsTarget(agent, definition)) : getPreApprovalsTarget(agent, definition);
    const achievement = definition.direction === 'lower_better'
      ? (actual <= 0 ? 100 : (target / actual) * 100)
      : (target > 0 ? (actual / target) * 100 : 0);
    const safeAchievement = Math.min(Math.max(0, achievement), 100);

    return {
      key: definition.key,
      label: definition.label,
      actual,
      target,
      unit: '%',
      isLowerBetter: definition.direction === 'lower_better',
      color: definition.color,
      achievement: safeAchievement,
      weight: definition.weight,
      // KPI achievement and contribution follow the global 100% cap.
      contribution: (safeAchievement / 100) * definition.weight * 100,
    };
  });
}

/**
 * The Offshore RCM sheet historically persisted KPI values alongside the
 * source counters.  When an upload was reprocessed, those persisted values
 * could remain stale (for example, Error% = 58.7%) even though the row still
 * contained the authoritative counts (ErrosClaims / SubmittedClaims).
 *
 * Keep the employee and team views on the same source of truth: counters win,
 * then explicit source percentages, and only then the legacy persisted KPI.
 */
function isPreApprovalsIpOffshoreTeam(value: string | null | undefined): boolean {
  return normalizeTeamIdentity(value) === normalizeTeamIdentity('Pre-Approvals IP Offshore');
}

function buildPreApprovalsIpOffshoreKpis(agent: AgentRecord): KPIConfig[] {
  const raw = agent.raw_data;
  const persisted = new Map((agent.kpi_values || []).map((kpi) => [normalizeWorkstream(kpi.kpi_key), kpi]));
  const sourceKpi = (key: string) => persisted.get(normalizeWorkstream(key));

  const rejection = sourceKpi('Rejection');
  const initialError = sourceKpi('InitialError');
  const submission = sourceKpi('Submission');

  const rejectionActual = getPreApprovalsCountRatio(
    raw,
    ['RejectedRequests', 'RejectedRequest'],
    ['AssignedRequests', 'AssignedRequest'],
  ) ?? getRawNumber(raw, ['IPInitialRejection%', 'A.IPInitialRejectionRate', 'A.IPInitialRejection%', 'RejectionRate'])
    ?? normalizeRate(rejection?.actual_value)
    ?? 0;
  const errorActual = getPreApprovalsCountRatio(
    raw,
    ['ErrosClaims', 'ErrorsClaims', 'ErrorClaims'],
    ['SubmittedClaims', 'SubmittedClaim'],
  ) ?? getRawNumber(raw, ['Error%', 'A.InitialErrorRate', 'A.InitialError%', 'InitialError%'])
    ?? normalizeRate(initialError?.actual_value)
    ?? 0;
  const submissionActual = getPreApprovalsCountRatio(
    raw,
    ['ApprovalWithin48HR', 'ApprovalWithin48hrs', 'NumberApprovalwithin48hrs'],
    ['ApprovedRequests', 'ApprovedRequest'],
  ) ?? getRawNumber(raw, ['%ofSubmissionWithinDuedate', 'A.SubmissionRate', 'A.Submission%', 'SubmissionRate'])
    ?? normalizeRate(submission?.actual_value)
    ?? 0;

  const rejectionTarget = getRawNumber(raw, [
    'T.IPInitialRejection%', 'T.Rejection%', 'T.InitialRejection%', 'T.Rejection', 'T.InitialRejectionRate', 'T.InitialRejection',
  ]) ?? normalizeRate(rejection?.target_value) ?? 0.03;
  const errorTarget = getRawNumber(raw, [
    'T.InitialError%', 'T.InitialError', 'T.InitialErrorRate', 'T.Error%', 'T.Error',
  ]) ?? normalizeRate(initialError?.target_value) ?? 0.03;
  const submissionTarget = getRawNumber(raw, [
    'T.%ofApprovalwithin48hrs', 'T.%OfApprovalwithin48HR', 'T.%OfApprovalwithin48hrs', 'T.%ofApprovalwithin48HR',
    'T.Submission%', 'T.Submission', 'T.SubmissionRate', 'T.%ofSubmissionWithinDuedate', 'T.%OfSubmissionWithin48HR',
  ]) ?? normalizeRate(submission?.target_value) ?? 0.90;

  const build = (
    source: NonNullable<AgentRecord['kpi_values']>[number] | undefined,
    key: string,
    label: string,
    actual: number,
    target: number,
    isLowerBetter: boolean,
    color: string,
    fallbackWeight: number,
  ): KPIConfig => {
    const safeWeight = Number.isFinite(source?.weight_applied) ? Math.max(0, source!.weight_applied) : fallbackWeight;
    const rawAchievement = isLowerBetter
      ? (actual <= 0 ? 100 : (target / actual) * 100)
      : (target > 0 ? (actual / target) * 100 : 0);
    const achievement = Math.min(Math.max(0, rawAchievement), 100);
    return {
      key,
      label,
      actual,
      target,
      unit: '%',
      isLowerBetter,
      color,
      achievement,
      weight: safeWeight,
      contribution: (achievement / 100) * safeWeight * 100,
    };
  };

  return [
    build(rejection, 'Rejection', 'Rejection Rate', rejectionActual, rejectionTarget, true, '#EF4444', 0.50),
    build(initialError, 'InitialError', 'Initial Error Rate', errorActual, errorTarget, true, '#F59E0B', 0.20),
    build(submission, 'Submission', 'Submission Rate', submissionActual, submissionTarget, false, '#10B981', 0.30),
  ];
}

function getAhtTarget(raw_data: RawData | undefined, fallback: number): number {
  if (!raw_data) return fallback;
  const tAht = raw_data['T.AHT'] ?? raw_data['T.AHTTarget'] ?? raw_data['T.AHT_Target'];
  if (tAht !== undefined && tAht !== null) {
    const val = Number(tAht);
    if (!isNaN(val)) {
      if (val < 1 || (val > 1 && val < 2)) {
        // Excel time fraction
        const mins = (val % 1) * 24 * 60;
        return mins > 0.1 ? mins : fallback;
      } else if (val > 10) {
        // assume seconds
        return val / 60;
      } else {
        return val;
      }
    }
  }
  return fallback;
}

export function getKPIsForAgent(agent: AgentRecord): KPIConfig[] {
  const team = agent.identity.team || 'Inbound';
  const actual = agent.actual || {};
  const raw_data = agent.raw_data || {};

  // Pre-Approvals IP Elective Dubai contains two employee workstreams in one
  // sheet. Older persisted payloads may also contain unrelated `combined_*`
  // KPIs, so scope the profile to the target-pair/workstream before exposing
  // any values to cards, trends, or score calculations.
  if (isPreApprovalsIpElectiveTeam(team)) {
    return buildPreApprovalsKpis(agent, resolvePreApprovalsWorkstream(agent));
  }

  // Offshore rows can carry stale persisted KPI values. Rebuild from the
  // source counters before the generic persisted-value branch is reached.
  if (isPreApprovalsIpOffshoreTeam(team)) {
    return buildPreApprovalsIpOffshoreKpis(agent);
  }

  if (agent.kpi_values?.length) {
    return agent.kpi_values.map((kpi) => ({
      key: kpi.kpi_key,
      label: kpi.label || kpi.kpi_key,
      actual: kpi.actual_value,
      target: kpi.target_value,
      unit: (['%', 'min', 'number', 'currency'].includes(kpi.unit) ? kpi.unit : 'number') as KPIConfig['unit'],
      isLowerBetter: kpi.direction === 'lower_better',
      color: kpi.color || '#3B82F6',
      achievement: Math.min(Math.max(kpi.achievement_ratio, 0), 1) * 100,
      weight: kpi.weight_applied,
      contribution: Math.min(
        Math.max(kpi.contribution, 0),
        Math.max(kpi.weight_applied, 0),
      ) * 100,
    }));
  }

  // Helper to parse AHT to minutes
  let ahtMinutes = 0;
  if (agent.calls && agent.calls.aht_raw) {
    const parts = agent.calls.aht_raw.split(':').map(Number);
    const seconds = (parts[0] || 0) * 3600 + (parts[1] || 0) * 60 + (parts[2] || 0);
    ahtMinutes = seconds / 60;
  }

  // Resolve quality rate and utz rate
  const qualityRate = actual.quality_rate ?? 0;
  const utzRate = actual.utz_rate ?? 0;

  if (team === 'Submission') {
    const targetRejection = getTargetValue(raw_data, ['T.InitialRejectionRate'], 0.04);
    const targetSubmission = getTargetValue(raw_data, ['T.%ofSubmissionWithinDuedate'], 0.85);

    return [
      { label: 'Initial Rejection Rate', actual: actual.rejection_rate ?? 0, target: targetRejection, unit: '%', isLowerBetter: true, color: '#3B82F6' },
      { label: 'Submission Within Due Date', actual: actual.submission_rate ?? 0, target: targetSubmission, unit: '%', color: '#10B981' },
    ];
  }

  if (team === 'Re-Submission') {
    const targetQualityErrors = getTargetValue(raw_data, ['T.QualityErrorsRate'], 0.05);
    const targetRejection = getTargetValue(raw_data, ['T.RejectionRateAfterResubmission'], 0.60);
    const targetTat = getTargetValue(raw_data, ['T.TAT'], 1.0);

    return [
      { label: 'Quality Errors Rate', actual: actual.quality_rate ?? 0, target: targetQualityErrors, unit: '%', isLowerBetter: true, color: '#EF4444' },
      { label: 'Rejection Rate After Re-Submission', actual: actual.rejection_rate ?? 0, target: targetRejection, unit: '%', isLowerBetter: true, color: '#F97316' },
      { label: 'TAT', actual: actual.submission_rate ?? 0, target: targetTat, unit: '%', color: '#2563EB' },
    ];
  }

  if (team === 'Coding') {
    const actualQualityErrors = parseFloat(raw_data['A.QualityErrorsRate']) || 0;
    const targetQualityErrors = parseFloat(raw_data['T.QualityErrorsRate']) || 0;
    const actualRejection = parseFloat(raw_data['A.RejectionRate']) || 0;
    const targetRejection = parseFloat(raw_data['T.RejectionRate']) || 0;
    const actualTAT = parseFloat(raw_data['A.TAT']) || 0;
    const targetTAT = parseFloat(raw_data['T.TAT']) || 0;

    return [
      { label: 'Quality Errors', actual: actualQualityErrors, target: targetQualityErrors, unit: '%', isLowerBetter: true, color: '#EF4444' },
      { label: 'Rejection', actual: actualRejection, target: targetRejection, unit: '%', isLowerBetter: true, color: '#F97316' },
      { label: 'Turnaround Time', actual: actualTAT, target: targetTAT, unit: 'number', isLowerBetter: true, color: '#3B82F6' },
    ];
  }

  if (team === 'CSR') {
    const actualRejection = parseFloat(raw_data['A.CSRRejection%']) || 0;
    const targetRejection = parseFloat(raw_data['T.CSRRejection%']) || 0;
    const actualQueries = parseFloat(raw_data['A.CSRQueries']) || 0;
    const targetQueries = parseFloat(raw_data['T.QueriesTarget']) || 0;
    const actualAttendedCR = parseFloat(raw_data['A.CPTConversion%']) || 0;
    const targetAttendedCR = parseFloat(raw_data['T.AttendedC.R']) || 0;
    const rejectionAch = parseFloat(raw_data['Rejection_Achievement']) || 0;
    const queriesAch = parseFloat(raw_data['Queries_Achievement']) || 0;
    const attendedAch = parseFloat(raw_data['AttendedCR_Achievement']) || 0;

    return [
      { label: 'Rejection', actual: actualRejection, target: targetRejection, unit: '%', isLowerBetter: true, color: '#EF4444', achievement: rejectionAch },
      { label: 'Queries Handled', actual: actualQueries, target: targetQueries, unit: '%', isLowerBetter: true, color: '#10B981', achievement: queriesAch },
      { label: 'Attended CR', actual: actualAttendedCR, target: targetAttendedCR, unit: '%', color: '#8B5CF6', achievement: attendedAch },
    ];
  }

  if (team === 'Pharmacy') {
    const actualWaitingTime = parseFloat(raw_data['A.TotalAvgWaitingTime']) || 0;
    const targetWaitingTime = parseFloat(raw_data['T.TotalWaitingTime']) || 0;
    const actualLeakage = parseFloat(raw_data['A.Leakage%']) || 0;
    const targetLeakage = parseFloat(raw_data['T.Leakage%']) || 0;
    const actualTenderCompliance = parseFloat(raw_data['A.TenderItemCompliance']) || 0;
    const targetTenderCompliance = parseFloat(raw_data['T.TenderItemCompliance']) || 0;
    const actualATV = parseFloat(raw_data['A.ATV']) || 0;
    const targetATV = parseFloat(raw_data['T.ATV']) || 0;
    const rawActualPrescription = parseFloat(raw_data['A.NoofPrescriptionsContribution']) || 0;
    const actualPrescription = rawActualPrescription > 0 && rawActualPrescription <= 1 ? rawActualPrescription * 100 : rawActualPrescription;

    const achVal = parseFloat(raw_data['NoofPrescriptionAch%']) 
      || parseFloat(raw_data['No of Prescription']) 
      || parseFloat(raw_data['NoofPrescription']) 
      || parseFloat(raw_data['Prescription_Achievement']) 
      || 0;
    const normalizedAchVal = achVal > 0 && achVal <= 2 ? achVal * 100 : achVal;

    const dispensed = parseFloat(raw_data['Dispensed Items'] || raw_data['A.DispensedItems'] || raw_data['A.TotalDispensedPrescriptions'] || raw_data['Dispensed Prescriptions']) || 0;
    const prescribed = parseFloat(raw_data['Total Prescribed Items'] || raw_data['Total Prescriped Items'] || raw_data['A.TotalPrescribedItems'] || raw_data['Prescribed Items']) || 0;
    const ratioAch = prescribed > 0 ? (dispensed / prescribed) * 100 : 0;
    
    const targetPrescription = 100;
    const prescriptionAchievement = normalizedAchVal > 0 
      ? normalizedAchVal 
      : (ratioAch > 0 ? ratioAch : (actualPrescription > 0 ? actualPrescription : 85.9));

    return [
      { label: 'Waiting Time', actual: actualWaitingTime, target: targetWaitingTime, unit: 'min', isLowerBetter: true, color: '#EF4444' },
      { label: 'Leakage', actual: actualLeakage, target: targetLeakage, unit: '%', isLowerBetter: true, color: '#F97316' },
      { label: 'Tender Compliance', actual: actualTenderCompliance, target: targetTenderCompliance, unit: '%', color: '#10B981' },
      { label: 'Average Transaction Value', actual: actualATV, target: targetATV, unit: 'currency', color: '#3B82F6' },
      { label: 'Prescription Contribution', actual: actualPrescription, target: targetPrescription, unit: '%', color: '#8B5CF6', achievement: prescriptionAchievement },
    ];
  }

  if (team === 'Outbound') {
    const targetAttend = getTargetValue(raw_data, ['T.Attend', 'T.Attend%', 'T.Attendance', 'T.Attendance%'], 0.55);
    const targetBooking = getTargetValue(raw_data, ['T.Booking', 'T.Booking%'], 0.46);
    const targetQuality = getTargetValue(raw_data, ['T.QualityTarget', 'T.Quality', 'T.Quality%', 'T.QualityScore'], 0.95);
    const targetReachability = getTargetValue(raw_data, ['T.Reachability%', 'T.Reachability'], 0.75);

    return [
      { label: 'Attendance Rate', actual: actual.attend_rate, target: targetAttend, unit: '%', color: '#3B82F6' },
      { label: 'Booking Rate', actual: actual.booking_rate, target: targetBooking, unit: '%', color: '#10B981' },
      { label: 'Quality Score', actual: qualityRate, target: targetQuality, unit: '%', color: '#8B5CF6' },
      { label: 'Reachability', actual: actual.reachability_rate ?? 0, target: targetReachability, unit: '%', color: '#F59E0B' },
    ];
  }

  if (team === 'Inbound UAE') {
    const targetAttend = getTargetValue(raw_data, ['T.Attend', 'T.Attend%', 'T.Attendance', 'T.Attendance%'], 0.75);
    const targetBooking = getTargetValue(raw_data, ['T.Booking', 'T.Booking%'], 0.60);
    const targetAbandon = getTargetValue(raw_data, ['T.Abandon', 'T.AbandonRate', 'T.Abandon%', 'T.AbandonRate%'], 0.01);

    return [
      { label: 'Attendance Rate', actual: actual.attend_rate, target: targetAttend, unit: '%', color: '#3B82F6' },
      { label: 'Booking Rate', actual: actual.booking_rate, target: targetBooking, unit: '%', color: '#10B981' },
      { label: 'Abandon Rate', actual: actual.abandon_rate, target: targetAbandon, unit: '%', isLowerBetter: true, color: '#EF4444' },
    ];
  }

  if (team === 'Pre-Approvals IP Offshore') {
    const targetRejection = getTargetValue(raw_data, ['T.IPInitialRejection%', 'T.Rejection', 'T.RejectionRate', 'T.Rejection%', 'T.InitialRejection%'], 0.03);
    const targetError = getTargetValue(raw_data, ['T.InitialError', 'T.InitialErrorRate', 'T.InitialError%', 'T.Error%', 'Error%'], 0.03);
    const targetSubmission = getTargetValue(raw_data, [
      'T.%ofApprovalwithin48hrs', 'T.%OfApprovalwithin48HR', 'T.%OfApprovalwithin48hrs', 'T.%ofApprovalwithin48HR',
      'T.Submission', 'T.SubmissionRate', 'T.Submission%',
    ], 0.90);

    return [
      { label: 'Rejection Rate', actual: actual.rejection_rate ?? 0, target: targetRejection, unit: '%', isLowerBetter: true, color: '#EF4444' },
      { label: 'Initial Error Rate', actual: actual.initial_error_rate ?? 0, target: targetError, unit: '%', isLowerBetter: true, color: '#F59E0B' },
      { label: 'Submission Rate', actual: actual.submission_rate ?? 0, target: targetSubmission, unit: '%', color: '#10B981' },
    ];
  }

  if (team === 'Sales') {
    // Sales achievement values are raw ratios (e.g. 0.94 = 94%, 1.63 = 163%)
    // Do NOT use getTargetValue which normalizes values > 1.0 by dividing by 100
    const getRawAchievement = (keys: string[]): number => {
      for (const key of keys) {
        if (raw_data[key] !== undefined && raw_data[key] !== null) {
          const val = parseFloat(raw_data[key]);
          if (!isNaN(val)) return val;
        }
      }
      return 0.0;
    };

    const opCensus = getRawAchievement(['OPCensusAch%', 'OPCensusAch']);
    const opRevenue = getRawAchievement(['OPRevenueAch%', 'OPRevenueAch']);
    const ipCensus = getRawAchievement(['IPCensusAch%', 'IPCensusAch']);
    const ipRevenue = getRawAchievement(['IPRevenueAch%', 'IPRevenueAch']);
    const activity = getRawAchievement(['ActivityAch%', 'SalesActivtiesAch%', 'SalesActivitiesAch%', 'ActivityAch']);

    // Actual/Target volume pairs for display
    const aOpCensus = parseFloat(raw_data['A.OPCensus']) || 0;
    const tOpCensus = parseFloat(raw_data['T.OPCensus']) || 0;
    const aOpRevenue = parseFloat(raw_data['A.OPRevenue']) || 0;
    const tOpRevenue = parseFloat(raw_data['T.OPRevenue']) || 0;
    const aIpCensus = parseFloat(raw_data['A.IPCensus']) || 0;
    const tIpCensus = parseFloat(raw_data['T.IPCensus']) || 0;
    const aIpRevenue = parseFloat(raw_data['A.IPRevenue']) || 0;
    const tIpRevenue = parseFloat(raw_data['T.IPRevenue']) || 0;

    const aActivity = (parseFloat(raw_data['A.ClinicActivity/AgentActivity']) || 0) +
      (parseFloat(raw_data['A.CorporateActivity(HealthCheckup)']) || 0) +
      (parseFloat(raw_data['A.CBDTour']) || 0) +
      (parseFloat(raw_data['A.ReqularVisits']) || 0);
    const tActivity = (parseFloat(raw_data['T.ClinicActivity/AgentActivity']) || 0) +
      (parseFloat(raw_data['T.CorporateActivity(HealthCheckup)']) || 0) +
      (parseFloat(raw_data['T.CBDTour']) || 0) +
      (parseFloat(raw_data['T.ReqularVisits']) || 0);

    return [
      { label: 'OP Census Ach', actual: opCensus, target: 1.0, unit: '%', color: '#3B82F6', actualVolume: Math.round(aOpCensus), targetVolume: Math.round(tOpCensus), volumeUnit: 'Census' },
      { label: 'OP Revenue Ach', actual: opRevenue, target: 1.0, unit: '%', color: '#10B981', actualVolume: Math.round(aOpRevenue), targetVolume: Math.round(tOpRevenue), volumeUnit: 'Rev' },
      { label: 'IP Census Ach', actual: ipCensus, target: 1.0, unit: '%', color: '#8B5CF6', actualVolume: Math.round(aIpCensus), targetVolume: Math.round(tIpCensus), volumeUnit: 'Census' },
      { label: 'IP Revenue Ach', actual: ipRevenue, target: 1.0, unit: '%', color: '#F59E0B', actualVolume: Math.round(aIpRevenue), targetVolume: Math.round(tIpRevenue), volumeUnit: 'Rev' },
      { label: 'Activity Score', actual: activity, target: 1.0, unit: '%', color: '#6366F1', actualVolume: Math.round(aActivity), targetVolume: Math.round(tActivity), volumeUnit: 'Activities' },
    ];
  }

  // Default Inbound
  const targetAttend = getTargetValue(raw_data, ['T.Attend', 'T.Attend%', 'T.Attendance', 'T.Attendance%'], 0.75);
  const targetBooking = getTargetValue(raw_data, ['T.Booking', 'T.Booking%'], 0.45);
  const targetAht = getAhtTarget(raw_data, 2.5);
  const targetQuality = getTargetValue(raw_data, ['T.QualityTarget', 'T.Quality', 'T.Quality%', 'T.QualityScore'], 0.95);

  const kpis: KPIConfig[] = [
    { label: 'Attendance Rate', actual: actual.attend_rate, target: targetAttend, unit: '%', color: '#3B82F6' },
    { label: 'Booking Rate', actual: actual.booking_rate, target: targetBooking, unit: '%', color: '#10B981' },
    { label: 'AHT (Handle Time)', actual: ahtMinutes, target: targetAht, unit: 'min', isLowerBetter: true, color: ahtMinutes <= targetAht ? '#10B981' : '#EF4444' },
    { label: 'Quality Score', actual: qualityRate, target: targetQuality, unit: '%', color: '#8B5CF6' },
  ];

  if (utzRate > 0) {
    const targetUtz = getTargetValue(raw_data, ['T.UTZ', 'T.UTZ%', 'T.Utilization', 'T.Utilization%'], 0.85);
    kpis.push({ label: 'UTZ', actual: utzRate, target: targetUtz, unit: '%', color: '#6366F1' });
  } else {
    const targetAbandon = getTargetValue(raw_data, ['T.Abandon', 'T.AbandonRate', 'T.Abandon%', 'T.AbandonRate%'], 0.01);
    kpis.push({ label: 'Abandon Rate', actual: actual.abandon_rate, target: targetAbandon, unit: '%', isLowerBetter: true, color: '#EF4444' });
  }

  return kpis;
}

