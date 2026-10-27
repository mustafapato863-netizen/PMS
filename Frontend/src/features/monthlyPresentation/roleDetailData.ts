import type { PMSAction } from '../../types';
import { kpiRows, normalizeRegion, type ExecRecord } from '../executive/compose';
import { executiveFunctionForTeam } from '../executive/functions';
import { gradeForScore, type GradeLetter } from './monthlyOverviewData';
import {
  canonicalFunctionNameFromSlug,
  formatKpiValue,
  fullGradeLabel,
  normalizeFunctionSlug,
  slugifyIdentifier,
  type AgentKeyKpiItem,
  type CallCenterDeepDiveData,
  type FullGradeLabel,
  type KpiMonthlyPoint,
  type SupportImpactLevel,
  type SupportPositionItem,
} from './callCenterDeepDiveData';

export interface RoleMemberKpiCell {
  kpiKey: string;
  label: string;
  actualFormatted: string;
  targetFormatted: string;
  achievementPct: number;
  metTarget: boolean;
}

export interface RoleIndividualActionPlan {
  id: string;
  employeeId: string;
  personName: string;
  score: number;
  grade: GradeLetter;
  gradeFullLabel: FullGradeLabel;
  mainIssue: string;
  actionText: string;
  owner: string;
  expectedImpact: string;
  linkedKpiKey: string;
}

export interface RoleMemberItem {
  employeeId: string;
  personName: string;
  score: number;
  grade: GradeLetter;
  gradeFullLabel: FullGradeLabel;
  gap: number;
  changeVsPrev: number | null;
  signal: string;
  keyKpiLabel: string;
  keyKpiActual: string;
  keyKpiTarget: string;
  keyKpiMet: boolean;
  kpiCells?: RoleMemberKpiCell[];
}

export interface FunctionRoleCard {
  roleSlug: string;
  roleTitle: string;
  /** Used inside Role Detail when drilling down; never shown on the Function Deep Dive board */
  personName: string;
  employeeId: string;
  headcount: number;
  below90Count: number;
  members: RoleMemberItem[];
  score: number;
  grade: GradeLetter;
  gradeFullLabel: FullGradeLabel;
  gap: number;
  changeVsPrev: number | null;
  /** Primary drag when below 90, key strength when at or above 90. */
  signal: string;
  linkedKpis: string[];
  impactLevel: SupportImpactLevel;
}

export type RoleKpiStatusBadge = 'Below Target' | 'Needs Attention' | 'On Target';

export interface RoleKpiSeries {
  id: string;
  kpiKey: string;
  name: string;
  shortName: string;
  unit: string;
  betterDirection: 'higher' | 'lower';
  actualDisplay: string;
  targetDisplay: string;
  achievementPct: number;
  /** Weight of this KPI in the role's 100% score (e.g., 30 for 30%) */
  weightPct: number;
  /** Points contributed by this KPI to the role's 100% score (e.g., 4.5 for 4.5% out of 30%) */
  contributionPct: number;
  /** Score points lost on this KPI (max(0, weightPct - contributionPct), e.g., 25.5 pts lost) */
  pointsLost: number;
  /** Target status label matching executive/position KPI cards */
  statusBadge: RoleKpiStatusBadge;
  /** Month-over-month delta in achievement/actual percentage (e.g., -68.8) */
  momDeltaPct: number | null;
  /** True when the MoM movement is favorable for this KPI's direction */
  isMomGood: boolean | null;
  /** True for the single KPI causing the largest point loss in this role */
  isBiggestGap?: boolean;
  gapLabel: string;
  diagnosis: string;
  structuralDiagnosis?: string;
  trend6Mo: KpiMonthlyPoint[];
}

export interface RoleAccountabilityGap {
  id: string;
  statement: string;
  ownership: string;
}

export interface RoleAssignedAction {
  id: string;
  title?: string;
  description: string;
  owner: string;
  dueDate: string | null;
  status: 'Open' | 'In Progress' | 'Completed' | 'Cancelled';
  expectedImpact: string;
  linkedKpiName?: string;
  affectedPeople?: string[];
}

export interface RoleDetailData {
  roleSlug: string;
  roleTitle: string;
  personName: string;
  employeeId: string;
  headcount: number;
  below90Count: number;
  members: RoleMemberItem[];
  functionSlug: string;
  functionName: string;
  regionName: string;
  monthLabel: string;
  previousMonthLabel: string;
  periodKey: string;
  score: number;
  grade: GradeLetter;
  gradeFullLabel: FullGradeLabel;
  gap: number;
  changeVsPrev: number | null;
  diagnosis: string;
  impactLevel: SupportImpactLevel;
  impactDiagnosis: string;
  accountableKpis: string[];
  accountabilityGaps: RoleAccountabilityGap[];
  kpis: RoleKpiSeries[];
  /** Role series come from the role's own history. Function series are the function KPIs when that history is absent. */
  kpiScope: 'role' | 'function';
  individualActionPlans: RoleIndividualActionPlan[];
  actions: RoleAssignedAction[];
}

export interface RoleActionDraft {
  employeeId: string;
  personName: string;
  team: string;
  month: string;
  description: string;
  owner: string;
  dueDate: string;
  status: 'Open' | 'In Progress' | 'Completed';
  expectedImpact: string;
  linkedKpiKey: string | null;
}

const TEAM_BASED_FUNCTIONS = new Set(['call-center', 'rcm']);

export function isRoleBasedFunction(functionSlug: string): boolean {
  return !TEAM_BASED_FUNCTIONS.has(normalizeFunctionSlug(functionSlug));
}

interface RoleSeed {
  roleTitle: string;
  personName: string;
  employeeId?: string;
  score: number;
  changeVsPrev?: number | null;
  signal: string;
  linkedKpis: string[];
  impactLevel?: SupportImpactLevel;
  keyKpiLabel?: string;
  keyKpiActual?: string;
  keyKpiTarget?: string;
  keyKpiMet?: boolean;
}

const round1 = (v: number) => Math.round(v * 10) / 10;

function parseKeyKpiFromSignal(
  signal: string,
  linkedKpis: string[],
  score: number,
): {
  keyKpiLabel: string;
  keyKpiActual: string;
  keyKpiTarget: string;
  keyKpiMet: boolean;
} {
  const clean = signal.trim();
  const metByScore = score >= 90;

  // Pattern 1: "Edits Rate at 14.3% (vs 7.0% target)..." or "CPL at 18.8 AED (vs 15.0 AED target)..."
  const vsParen = clean.match(
    /^([^·&]+?)\s+at\s+([0-9.,]+(?:\s*(?:%|AED|EGP|USD|min|hrs))?)\s*\(vs\s+([0-9.,]+(?:\s*(?:%|AED|EGP|USD|min|hrs))?)/i,
  );
  if (vsParen) {
    return {
      keyKpiLabel: vsParen[1].trim(),
      keyKpiActual: vsParen[2].trim(),
      keyKpiTarget: vsParen[3].trim(),
      keyKpiMet: metByScore,
    };
  }

  // Pattern 2: "Leads 4,262 vs 8,657 target" or "CPL 15.0 AED vs 7.0 AED target"
  const vsInline = clean.match(
    /^([^·&]+?)\s+([0-9.,]+(?:\s*(?:%|AED|EGP|USD|min|hrs))?)\s+vs\s+([0-9.,]+(?:\s*(?:%|AED|EGP|USD|min|hrs))?)\s*target/i,
  );
  if (vsInline) {
    return {
      keyKpiLabel: vsInline[1].trim(),
      keyKpiActual: vsInline[2].trim(),
      keyKpiTarget: vsInline[3].trim(),
      keyKpiMet: metByScore,
    };
  }

  // Pattern 3: "170 of 180 projects delivered on schedule..."
  const ratioMatch = clean.match(/^(\d+)\s+of\s+(\d+)\s+([^(&·]+?)(?:\s+with|\s+&|$)/i);
  if (ratioMatch) {
    const labelRaw = ratioMatch[3].trim();
    const label = labelRaw.charAt(0).toUpperCase() + labelRaw.slice(1);
    return {
      keyKpiLabel: label,
      keyKpiActual: `${ratioMatch[1]} / ${ratioMatch[2]}`,
      keyKpiTarget: ratioMatch[2],
      keyKpiMet: metByScore,
    };
  }

  // Pattern 4: "Organic Traffic Growth at 80.5% of target..." or "Video Completion Rate at 81.2%..."
  const atValue = clean.match(
    /^([^·&]+?)\s+(?:at\s+)?([0-9.,]+(?:\s*(?:%|AED|EGP|USD|min|hrs)))(?:\s+of\s+(?:target|plan|SLA))?/i,
  );
  if (atValue) {
    return {
      keyKpiLabel: atValue[1].trim(),
      keyKpiActual: atValue[2].trim(),
      keyKpiTarget: metByScore ? '95.0%' : '100%',
      keyKpiMet: metByScore,
    };
  }

  return {
    keyKpiLabel: linkedKpis[0] || 'Role Execution',
    keyKpiActual: `${score.toFixed(1)}%`,
    keyKpiTarget: '90.0%',
    keyKpiMet: metByScore,
  };
}

function impactFromScore(score: number): SupportImpactLevel {
  if (score >= 95) return 'Strong';
  if (score >= 90) return 'Partial';
  if (score >= 80) return 'Mixed';
  return 'Limited';
}

export function normalizeRoleTitle(rawTitle: string): string {
  const t = rawTitle.trim();
  if (/team leader/i.test(t)) return 'Team Leader';
  if (/call center trainer|trainer/i.test(t)) return 'Trainer';
  if (/quality assurance|quality specialist/i.test(t)) return 'Quality Specialist';
  if (/workforce analyst|workforce management|wfm/i.test(t)) return 'Workforce Analyst';
  return t;
}

export function namesMatch(a: string, b: string): boolean {
  const cleanA = a.trim().toLowerCase();
  const cleanB = b.trim().toLowerCase();
  if (!cleanA || !cleanB) return false;
  if (cleanA === cleanB) return true;
  if (cleanA.startsWith(cleanB) || cleanB.startsWith(cleanA)) return true;
  if (cleanA.includes(cleanB) || cleanB.includes(cleanA)) return true;
  const wordsA = cleanA.split(/\s+/).slice(0, 2).join(' ');
  const wordsB = cleanB.split(/\s+/).slice(0, 2).join(' ');
  if (wordsA && wordsB && (wordsA === wordsB || cleanA.startsWith(wordsB) || cleanB.startsWith(wordsA))) {
    return true;
  }
  return false;
}

export function kpiLabelsMatch(
  labelA: string,
  labelB: string,
  keyA?: string,
  keyB?: string,
): boolean {
  if (keyA && keyB && (keyA === keyB || slugifyIdentifier(keyA) === slugifyIdentifier(keyB))) {
    return true;
  }
  const cleanA = labelA.toLowerCase().replace(/[%()_]/g, ' ').replace(/\s+/g, ' ').trim();
  const cleanB = labelB.toLowerCase().replace(/[%()_]/g, ' ').replace(/\s+/g, ' ').trim();
  if (cleanA === cleanB) return true;
  if (slugifyIdentifier(labelA) === slugifyIdentifier(labelB)) return true;

  const isBooking = (s: string) => /booking/i.test(s);
  if (isBooking(cleanA) && isBooking(cleanB)) return true;

  const isAttendance = (s: string) => /attend/i.test(s);
  if (isAttendance(cleanA) && isAttendance(cleanB)) return true;

  const isAht = (s: string) => /\baht\b|handle time/i.test(s);
  if (isAht(cleanA) && isAht(cleanB)) return true;

  const isQuality = (s: string) => /\bquality\b|\bqa\b/i.test(s);
  if (isQuality(cleanA) && isQuality(cleanB)) return true;

  const isReachability = (s: string) => /reachab/i.test(s);
  if (isReachability(cleanA) && isReachability(cleanB)) return true;

  const isUtz = (s: string) => /\butiliz|\butz\b/i.test(s);
  if (isUtz(cleanA) && isUtz(cleanB)) return true;

  const isAudit = (s: string) => /audit|evaluation coverage/i.test(s);
  if (isAudit(cleanA) && isAudit(cleanB)) return true;

  const isSession = (s: string) => /session/i.test(s);
  if (isSession(cleanA) && isSession(cleanB)) return true;

  const isReporting = (s: string) => /report|timeliness/i.test(s);
  if (isReporting(cleanA) && isReporting(cleanB)) return true;

  return cleanA.includes(cleanB) || cleanB.includes(cleanA);
}

function getBaselineMemberKpis(name: string): Array<{
  label: string;
  actualFormatted: string;
  targetFormatted: string;
  achievementPct: number;
  metTarget: boolean;
}> | null {
  const clean = name.toLowerCase();
  if (clean.includes('amr badawy')) {
    return [
      { label: 'Booking Rate', actualFormatted: '30.5%', targetFormatted: '30.0%', achievementPct: 100, metTarget: true },
      { label: 'Attendance Rate', actualFormatted: '56.2%', targetFormatted: '65.0%', achievementPct: 86.4, metTarget: false },
      { label: 'Attended CR%', actualFormatted: '56.2%', targetFormatted: '65.0%', achievementPct: 86.4, metTarget: false },
      { label: 'Reachability', actualFormatted: '53.0%', targetFormatted: '75.0%', achievementPct: 70.7, metTarget: false },
      { label: 'Quality Score', actualFormatted: '96.0%', targetFormatted: '95.0%', achievementPct: 100, metTarget: true },
      { label: 'UTZ%', actualFormatted: '70.2%', targetFormatted: '85.0%', achievementPct: 82.6, metTarget: false },
      { label: 'AHT', actualFormatted: '—', targetFormatted: '—', achievementPct: 0, metTarget: false },
    ];
  }
  if (clean.includes('adham sameh')) {
    return [
      { label: 'Booking Rate', actualFormatted: '62.0%', targetFormatted: '65.0%', achievementPct: 95.4, metTarget: false },
      { label: 'Attendance Rate', actualFormatted: '68.5%', targetFormatted: '75.0%', achievementPct: 91.3, metTarget: false },
      { label: 'Attended CR%', actualFormatted: '68.5%', targetFormatted: '75.0%', achievementPct: 91.3, metTarget: false },
      { label: 'AHT', actualFormatted: '2.73 min', targetFormatted: '2.50 min', achievementPct: 91.0, metTarget: false },
      { label: 'Quality Score', actualFormatted: '98.4%', targetFormatted: '95.0%', achievementPct: 100, metTarget: true },
      { label: 'UTZ%', actualFormatted: '82.6%', targetFormatted: '85.0%', achievementPct: 97.1, metTarget: false },
      { label: 'Reachability', actualFormatted: '—', targetFormatted: '—', achievementPct: 0, metTarget: false },
    ];
  }
  return null;
}

function roleTitleFromReason(reason: string, fallback: string): string {
  const match = reason.match(/\(([^)]+)\)\s*$/);
  const candidate = match?.[1]?.trim() ?? '';
  if (!candidate || /\d|%|\bvs\b|target/i.test(candidate)) return fallback;
  return candidate;
}

function stripTrailingRoleFromReason(reason: string): string {
  const match = reason.match(/\s*\(([^)]+)\)\s*$/);
  const candidate = match?.[1]?.trim() ?? '';
  if (!candidate || /\d|%|\bvs\b|target/i.test(candidate)) return reason;
  return reason.replace(/\s*\([^)]+\)\s*$/, '').trim();
}

const SUPPLEMENTAL_BASELINE_ROLES: Record<string, RoleSeed[]> = {
  marketing: [
    {
      roleTitle: 'Content Writer',
      personName: 'Nourshan',
      employeeId: 'Nourshan',
      score: 97.7,
      changeVsPrev: 1.4,
      signal: 'Content delivery timeliness at 95.5% & Error-free content ratio at 2.7% (vs 5.0% ceiling)',
      linkedKpis: ['Content Delivery Timeliness', 'Error-Free Content Ratio'],
      impactLevel: 'Strong',
    },
    {
      roleTitle: 'Graphic Designer',
      personName: 'Elsayed Mohamed',
      employeeId: 'Elsayed Mohamed',
      score: 91.9,
      changeVsPrev: 1.1,
      signal: '170 of 180 projects delivered on schedule with 98.0% brand consistency & 1.8% rework rate',
      linkedKpis: ['Projects Delivered on Schedule', 'Brand Consistency Score', 'Edits Rate'],
      impactLevel: 'Partial',
    },
    {
      roleTitle: 'Graphic Designer',
      personName: 'Abdulwahab',
      employeeId: 'Abdulwahab',
      score: 86.8,
      changeVsPrev: -0.8,
      signal: 'Edits Rate at 14.3% (vs 7.0% target) & 140 of 160 projects delivered on schedule',
      linkedKpis: ['Edits Rate', 'Projects Delivered on Schedule'],
      impactLevel: 'Mixed',
    },
    {
      roleTitle: 'Graphic Designer',
      personName: 'Asser Mohamed',
      employeeId: 'Asser Mohamed',
      score: 84.8,
      changeVsPrev: -1.5,
      signal: 'Edits Rate at 16.4% (vs 8.0% target) & 110 of 130 projects delivered on schedule',
      linkedKpis: ['Edits Rate', 'Projects Delivered on Schedule'],
      impactLevel: 'Mixed',
    },
  ],
  'human-resources': [
    {
      roleTitle: 'HR Specialist',
      personName: 'Fatma Ramadan Ali Ibrahim',
      employeeId: 'Fatma Ramadan Ali Ibrahim',
      score: 92.5,
      changeVsPrev: 1.2,
      signal: 'Personnel File Accuracy 100.0% & HR Records Accuracy 99.4% · Onboarding Readiness at 79.6%',
      linkedKpis: ['First-Day Onboarding Readiness Rate', 'Payroll & Attendance Input Accuracy'],
      impactLevel: 'Partial',
    },
  ],
};

const BASELINE_ROLE_MOVEMENT: Record<string, number> = {
  'mohamed abdelmegid diab': 0.9,
  'dina samir': 1.3,
  'hossam el-naggar': -1.8,
  'ahmed mohamed shehata': -2.4,
  'abdelrahman yousry abdelaziz hamdy': -4.2,
  'bahy hamed amer': -1.9,
  'mina nabil': -2.1,
  'samya ismail': -2.1,
  'ziad sayed hassan': 0.6,
  'mohamed gamal mohamed abouzeid': 0.9,
  'mohamed diaa eldin youssef': 0.0,
  'sherif nasr-eldeen ahmed salah elidn mohamed': 1.8,
  'fatma ramadan ali ibrahim': 1.2,
  'anwaar abdelmoneem mohamed ali': 0.7,
  'ahmed mohamed sayed ahmed': 0.4,
  'amr badawy': 1.1,
  'amr badawy mohamed': 1.1,
  'adham sameh': -0.8,
  'adham sameh abdallah arafa': -0.8,
};

export function parseHoldersFromSupportPosition(
  position: SupportPositionItem,
  data: CallCenterDeepDiveData,
): RoleSeed[] {
  const holderText = (position.holderName || position.positionName).trim();
  const roleTitle = normalizeRoleTitle(position.positionName);

  if (holderText.includes('·')) {
    const segments = holderText.split(/\s*·\s*/).filter(Boolean);
    return segments.map((segment) => {
      const match = segment.match(/^([^(]+?)(?:\s*\((?:([^0-9)]+)\s*)?([0-9.]+)%?\))?$/);
      const rawName = match?.[1]?.trim() || segment.trim();
      const teamContext = match?.[2]?.trim() || '';
      const parsedScore = match?.[3] ? parseFloat(match[3]) : null;
      const score =
        parsedScore !== null && Number.isFinite(parsedScore)
          ? round1(parsedScore)
          : round1(position.evaluatedScore ?? data.headline.score);

      const isOutbound = /outbound/i.test(teamContext) || /amr badawy/i.test(rawName);
      const isInbound = /inbound/i.test(teamContext) || /adham sameh/i.test(rawName);

      let signal = position.explanation;
      let keyKpiLabel = position.linkedKpis[0] || 'Role Execution';
      let keyKpiActual = `${score.toFixed(1)}%`;
      let keyKpiTarget = '90.0%';
      let keyKpiMet = score >= 90;
      let linkedKpis = position.linkedKpis;

      if (isOutbound) {
        signal =
          'Outbound floor supervision: Reachability at 53.0% (vs 75.0% target) & Attended CR at 56.2% (vs 65.0% target)';
        keyKpiLabel = 'Reachability';
        keyKpiActual = '53.0%';
        keyKpiTarget = '75.0%';
        keyKpiMet = false;
        linkedKpis = ['Reachability', 'Attended CR%', 'Attendance Rate', 'Booking CR%'];
      } else if (isInbound) {
        signal =
          'Inbound floor supervision: Quality Score at 98.4% (vs 95.0% target) & Attended CR at 68.5% (vs 75.0% target)';
        keyKpiLabel = 'Quality Score';
        keyKpiActual = '98.4%';
        keyKpiTarget = '95.0%';
        keyKpiMet = true;
        linkedKpis = ['Quality Score', 'Booking CR%', 'Booking Rate', 'AHT'];
      }

      const cleanLower = rawName.toLowerCase();
      const movement =
        BASELINE_ROLE_MOVEMENT[cleanLower] ??
        (isOutbound ? 1.1 : isInbound ? -0.8 : null);

      return {
        roleTitle,
        personName: rawName,
        employeeId: rawName,
        score,
        changeVsPrev: movement,
        signal,
        linkedKpis,
        impactLevel: impactFromScore(score),
        keyKpiLabel,
        keyKpiActual,
        keyKpiTarget,
        keyKpiMet,
      };
    });
  }

  return [
    {
      roleTitle,
      personName: holderText,
      employeeId: holderText,
      score: round1(position.evaluatedScore ?? data.headline.score),
      changeVsPrev:
        BASELINE_ROLE_MOVEMENT[holderText.toLowerCase()] ?? data.headline.changeVsPrev,
      signal: position.explanation,
      linkedKpis: position.linkedKpis,
      impactLevel: position.impactLevel,
    },
  ];
}

/**
 * Aggregates individual RoleSeed entries by `roleTitle` so each role appears as a single card
 * on the Function Deep Dive (e.g., "Graphic Designer" combines all 3 Graphic Designers into 1 role card),
 * while preserving the individual members for the Role Detail page.
 */
function aggregateSeedsByRole(seeds: RoleSeed[]): FunctionRoleCard[] {
  const groups = new Map<
    string,
    {
      roleTitle: string;
      seeds: RoleSeed[];
    }
  >();

  for (const seed of seeds) {
    const normTitle = normalizeRoleTitle(seed.roleTitle);
    const key = slugifyIdentifier(normTitle) || 'role';
    const existing = groups.get(key);
    if (existing) {
      existing.seeds.push({ ...seed, roleTitle: normTitle });
    } else {
      groups.set(key, { roleTitle: normTitle, seeds: [{ ...seed, roleTitle: normTitle }] });
    }
  }

  const cards: FunctionRoleCard[] = [];

  for (const [roleSlug, group] of groups.entries()) {
    const members: RoleMemberItem[] = group.seeds
      .map((s) => {
        const sc = round1(s.score);
        const g = gradeForScore(sc);
        const parsedKpi = parseKeyKpiFromSignal(s.signal, s.linkedKpis, sc);
        return {
          employeeId: s.employeeId || s.personName,
          personName: s.personName,
          score: sc,
          grade: g,
          gradeFullLabel: fullGradeLabel(g),
          gap: round1(sc - 100),
          changeVsPrev: s.changeVsPrev ?? null,
          signal: s.signal,
          keyKpiLabel: s.keyKpiLabel || parsedKpi.keyKpiLabel,
          keyKpiActual: s.keyKpiActual || parsedKpi.keyKpiActual,
          keyKpiTarget: s.keyKpiTarget || parsedKpi.keyKpiTarget,
          keyKpiMet: s.keyKpiMet ?? parsedKpi.keyKpiMet,
        };
      })
      .sort((a, b) => a.score - b.score || a.personName.localeCompare(b.personName));

    const avgScore = round1(
      members.reduce((sum, m) => sum + m.score, 0) / Math.max(1, members.length),
    );
    const grade = gradeForScore(avgScore);
    const gap = round1(avgScore - 100);

    const validChanges = members
      .map((m) => m.changeVsPrev)
      .filter((c): c is number => c !== null && Number.isFinite(c));
    const avgChange =
      validChanges.length > 0
        ? round1(validChanges.reduce((sum, c) => sum + c, 0) / validChanges.length)
        : null;

    const below90Count = members.filter((m) => m.score < 90).length;
    const allKpis = [
      ...new Set(group.seeds.flatMap((s) => s.linkedKpis).filter(Boolean)),
    ];

    // Pick the primary signal from the lowest-scoring member when dragging, or highest when carrying
    const primaryMember = avgScore < 90 ? members[0] : members[members.length - 1];
    const primarySignal = primaryMember?.signal ?? '';

    const primaryPerson = members[0];
    const personSummary =
      members.length === 1
        ? primaryPerson.personName
        : members.map((m) => m.personName).join(' · ');

    cards.push({
      roleSlug,
      roleTitle: group.roleTitle,
      personName: personSummary,
      employeeId: primaryPerson.employeeId,
      headcount: members.length,
      below90Count,
      members,
      score: avgScore,
      grade,
      gradeFullLabel: fullGradeLabel(grade),
      gap,
      changeVsPrev: avgChange,
      signal: primarySignal,
      linkedKpis: allKpis,
      impactLevel: group.seeds[0]?.impactLevel ?? impactFromScore(avgScore),
    });
  }

  return cards.sort((a, b) => a.score - b.score || a.roleTitle.localeCompare(b.roleTitle));
}

function cardsFromBaseline(data: CallCenterDeepDiveData): FunctionRoleCard[] {
  const seenPeople = new Set<string>();
  const seeds: RoleSeed[] = [];
  const fnSlug = normalizeFunctionSlug(data.functionSlug);

  for (const position of data.supportPositions) {
    const parsedSeeds = parseHoldersFromSupportPosition(position, data);
    for (const seed of parsedSeeds) {
      if (
        /governance|operations|regional/i.test(seed.personName) &&
        (fnSlug === 'it' || fnSlug === 'administration' || fnSlug === 'finance') &&
        data.agentsNeedingAttention.length > 0
      ) {
        continue;
      }
      if (seenPeople.has(seed.personName.toLowerCase())) continue;
      seenPeople.add(seed.personName.toLowerCase());
      seeds.push(seed);
    }
  }

  for (const agent of data.agentsNeedingAttention) {
    const personName = agent.agentName;
    if (seenPeople.has(personName.toLowerCase())) continue;
    seenPeople.add(personName.toLowerCase());
    const rawRoleTitle = roleTitleFromReason(agent.reason, agent.team);
    const roleTitle = normalizeRoleTitle(rawRoleTitle);
    seeds.push({
      roleTitle,
      personName,
      employeeId: agent.employeeId || personName,
      score: agent.score,
      changeVsPrev: BASELINE_ROLE_MOVEMENT[personName.toLowerCase()] ?? data.headline.changeVsPrev,
      signal: stripTrailingRoleFromReason(agent.reason),
      linkedKpis: agent.weakestKpiKey ? [agent.weakestKpiKey] : [],
    });
  }

  const supplemental = SUPPLEMENTAL_BASELINE_ROLES[fnSlug] ?? [];
  for (const extra of supplemental) {
    if (seenPeople.has(extra.personName.toLowerCase())) continue;
    seenPeople.add(extra.personName.toLowerCase());
    seeds.push(extra);
  }

  return aggregateSeedsByRole(seeds);
}

function recordsForFunction(data: CallCenterDeepDiveData, records: ExecRecord[]): ExecRecord[] {
  const slug = normalizeFunctionSlug(data.functionSlug);
  const name = data.functionName.toLowerCase();
  return records.filter((record) => {
    if (normalizeRegion(record.region) !== data.regionCode) return false;
    if (record.period.key !== data.periodKey) return false;
    const fn = executiveFunctionForTeam(record.team);
    return (
      slugifyIdentifier(fn ?? '') === slug ||
      slugifyIdentifier(record.team) === slug ||
      (fn ?? '').toLowerCase() === name
    );
  });
}

function movementFor(record: ExecRecord, records: ExecRecord[]): number | null {
  const prior = records
    .filter((item) => item.employeeId === record.employeeId && item.period.key < record.period.key)
    .sort((a, b) => b.period.key.localeCompare(a.period.key))[0];
  if (!prior) return null;
  return round1(record.score - prior.score);
}

function cardsFromRecords(current: ExecRecord[], records: ExecRecord[]): FunctionRoleCard[] {
  const seeds: RoleSeed[] = current.map((record) => {
    const rows = kpiRows([record], []);
    const weakest = rows[0];
    const strongest = rows
      .slice()
      .sort((a, b) => (b.achievement_percent ?? 0) - (a.achievement_percent ?? 0))[0];
    const rawTitle = record.position?.trim() || record.team;
    const title = normalizeRoleTitle(rawTitle);
    const dragging = record.score < 90;
    const signal = dragging
      ? weakest
        ? `${weakest.kpi_label} ${formatKpiValue(weakest.actual, weakest.unit)} vs ${formatKpiValue(weakest.target, weakest.unit)} target`
        : 'Score is below 90%'
      : strongest
      ? `${strongest.kpi_label} ${formatKpiValue(strongest.actual, strongest.unit)} vs ${formatKpiValue(strongest.target, strongest.unit)} target`
      : 'Score is at or above 90%';
    const primaryKpiRow = dragging ? weakest : strongest || weakest;
    const keyKpiMet = primaryKpiRow
      ? (primaryKpiRow.achievement_percent ?? 0) >= 99.9
      : record.score >= 90;
    return {
      roleTitle: title,
      personName: record.name,
      employeeId: record.employeeId || record.name,
      score: round1(record.score),
      changeVsPrev: movementFor(record, records),
      signal,
      linkedKpis: weakest ? [weakest.kpi_label] : [],
      impactLevel: impactFromScore(record.score),
      keyKpiLabel: primaryKpiRow?.kpi_label,
      keyKpiActual: primaryKpiRow ? formatKpiValue(primaryKpiRow.actual, primaryKpiRow.unit) : undefined,
      keyKpiTarget: primaryKpiRow ? formatKpiValue(primaryKpiRow.target, primaryKpiRow.unit) : undefined,
      keyKpiMet,
    };
  });

  return aggregateSeedsByRole(seeds);
}

export function resolveRoleCards(
  data: CallCenterDeepDiveData,
  records: ExecRecord[] = [],
): FunctionRoleCard[] {
  const scoped = recordsForFunction(data, records);
  const fromRecords = cardsFromRecords(scoped, records);
  if (fromRecords.length) return fromRecords;
  if (
    data.regionCode === 'UAE' &&
    data.supportPositions.length === 0 &&
    data.agentsNeedingAttention.length === 0
  ) {
    return [];
  }
  return cardsFromBaseline(data);
}

function supportForSlug(data: CallCenterDeepDiveData, roleSlug: string): SupportPositionItem | undefined {
  const norm = slugifyIdentifier(roleSlug);
  return data.supportPositions.find(
    (position) =>
      slugifyIdentifier(position.positionName) === norm ||
      slugifyIdentifier(position.id) === norm ||
      position.id === roleSlug ||
      (norm.includes('team-leader') && slugifyIdentifier(position.positionName) === 'team-leader'),
  );
}

function kpiMatches(kpi: AgentKeyKpiItem, needle: string): boolean {
  const hay = `${kpi.name} ${kpi.shortName} ${kpi.kpiKey}`.toLowerCase();
  const n = needle.toLowerCase();
  return hay.includes(n) || n.includes(kpi.shortName.toLowerCase());
}

function buildStructuralDiagnosis(
  name: string,
  trend6Mo: KpiMonthlyPoint[],
  gapLabel: string,
  fallback?: string,
): string {
  if (fallback && fallback.trim()) return fallback.trim();
  const evaluated = trend6Mo.filter((pt) => pt.actual !== null && pt.metTarget !== null);
  const missedCount = evaluated.filter((pt) => pt.metTarget === false).length;
  const totalCount = evaluated.length || trend6Mo.length;
  const windowLabel =
    evaluated.length > 0 && evaluated.length < trend6Mo.length
      ? `measured ${totalCount === 1 ? 'month' : 'months'}`
      : 'trailing months';
  if (gapLabel === 'On target' || missedCount === 0) {
    return `No structural gap — ${name} met or exceeded target across ${totalCount - missedCount} of ${totalCount} ${windowLabel}.`;
  }
  if (missedCount >= 4) {
    return `Structural gap — ${name} missed target in ${missedCount} of ${totalCount} ${windowLabel} (${gapLabel}), indicating a persistent workflow or capacity bottleneck rather than a one-month dip.`;
  }
  return `Execution variance — ${name} missed target in ${missedCount} of ${totalCount} ${windowLabel} (${gapLabel}); target remains achievable with focused weekly execution.`;
}

function computeKpiMetrics(
  achievementPct: number,
  weightPct: number,
  betterDirection: 'higher' | 'lower',
  trend6Mo: KpiMonthlyPoint[],
  gapLabel: string,
): {
  weightPct: number;
  contributionPct: number;
  pointsLost: number;
  statusBadge: RoleKpiStatusBadge;
  momDeltaPct: number | null;
  isMomGood: boolean | null;
} {
  const cappedAch = Math.min(100, Math.max(0, Number.isFinite(achievementPct) ? achievementPct : 0));
  const cleanWeight = round1(Math.max(0, weightPct));
  const contributionPct = round1((cappedAch / 100) * cleanWeight);
  const pointsLost = round1(Math.max(0, cleanWeight - contributionPct));

  const statusBadge: RoleKpiStatusBadge =
    cappedAch >= 99.95 || gapLabel === 'On target'
      ? 'On Target'
      : cappedAch >= 80
      ? 'Needs Attention'
      : 'Below Target';

  let momDeltaPct: number | null = null;
  let isMomGood: boolean | null = null;

  if (trend6Mo.length >= 2) {
    const curr = trend6Mo[trend6Mo.length - 1];
    const prev = trend6Mo[trend6Mo.length - 2];
    if (curr?.actual != null && prev?.actual != null) {
      const progressOf = (actual: number, target: number | null) => {
        if (target == null || target <= 0) return null;
        if (betterDirection === 'lower') {
          return actual <= 0 ? 100 : (target / actual) * 100;
        }
        return (actual / target) * 100;
      };
      const currProg = progressOf(curr.actual, curr.target);
      const prevProg = progressOf(prev.actual, prev.target);

      let delta = 0;
      if (
        currProg !== null &&
        prevProg !== null &&
        Math.abs(Math.min(100, currProg) - Math.min(100, prevProg)) >= 0.1
      ) {
        delta = round1(Math.min(100, currProg) - Math.min(100, prevProg));
      } else if (Math.abs(prev.actual) > 1e-6) {
        const rawPct = ((curr.actual - prev.actual) / Math.abs(prev.actual)) * 100;
        delta = round1(betterDirection === 'lower' ? -rawPct : rawPct);
      }

      momDeltaPct = delta;
      isMomGood = Math.abs(delta) < 0.05 ? null : delta > 0;
    }
  }

  return {
    weightPct: cleanWeight,
    contributionPct,
    pointsLost,
    statusBadge,
    momDeltaPct,
    isMomGood,
  };
}

function annotateBiggestGap(kpis: RoleKpiSeries[]): RoleKpiSeries[] {
  const sorted = [...kpis].sort(
    (a, b) => a.achievementPct - b.achievementPct || b.pointsLost - a.pointsLost,
  );
  let maxLost = 0;
  let maxIdx = -1;
  sorted.forEach((kpi, idx) => {
    if (kpi.pointsLost > maxLost) {
      maxLost = kpi.pointsLost;
      maxIdx = idx;
    }
  });
  return sorted.map((kpi, idx) => ({
    ...kpi,
    isBiggestGap: idx === maxIdx && maxLost > 0,
  }));
}

function seriesFromKpi(kpi: AgentKeyKpiItem, weightPct = 25): RoleKpiSeries {
  const latest = kpi.trend6Mo[kpi.trend6Mo.length - 1];
  const actual = latest?.actual;
  const target = latest?.target;
  let gapLabel = 'No target';
  if (actual != null && target != null) {
    const delta = round1(actual - target);
    const worse = kpi.betterDirection === 'lower' ? delta > 0 : delta < 0;
    gapLabel = worse
      ? `${formatKpiValue(Math.abs(delta), kpi.unit)} off target`
      : 'On target';
  }
  const metrics = computeKpiMetrics(
    kpi.achievementPct,
    weightPct,
    kpi.betterDirection,
    kpi.trend6Mo,
    gapLabel,
  );
  return {
    id: kpi.id,
    kpiKey: kpi.kpiKey,
    name: kpi.name,
    shortName: kpi.shortName,
    unit: kpi.unit,
    betterDirection: kpi.betterDirection,
    actualDisplay: kpi.actualDisplay,
    targetDisplay: kpi.targetDisplay,
    achievementPct: kpi.achievementPct,
    ...metrics,
    gapLabel,
    diagnosis: kpi.diagnosis,
    structuralDiagnosis: buildStructuralDiagnosis(
      kpi.shortName,
      kpi.trend6Mo,
      gapLabel,
      kpi.targetRealismDiagnosis,
    ),
    trend6Mo: kpi.trend6Mo,
  };
}

const SHORT_MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

function buildTrailingSixPeriods(anchorPeriodKey: string): Array<{ month: string; periodKey: string }> {
  const [yrStr, moStr] = anchorPeriodKey.split('-');
  const year = Number(yrStr) || 2026;
  const monthIdx = Math.max(0, Math.min(11, (Number(moStr) || 9) - 1));
  const absolute = year * 12 + monthIdx;
  return Array.from({ length: 6 }, (_, idx) => {
    const val = absolute - (5 - idx);
    const y = Math.floor(val / 12);
    const m = ((val % 12) + 12) % 12;
    return {
      month: SHORT_MONTHS[m],
      periodKey: `${y}-${String(m + 1).padStart(2, '0')}`,
    };
  });
}

function kpisForRole(data: CallCenterDeepDiveData, linked: string[]): RoleKpiSeries[] {
  const matched = linked.length
    ? data.keyKpis.filter((kpi) => linked.some((needle) => kpiMatches(kpi, needle)))
    : [];
  const unmatched = data.keyKpis.filter((kpi) => !matched.includes(kpi));
  const source = (matched.length ? [...matched, ...unmatched] : data.keyKpis).slice(0, 4);
  const count = source.length;
  const weights =
    count === 1
      ? [100]
      : count === 2
      ? matched.length === 1
        ? [60, 40]
        : [50, 50]
      : count === 3
      ? matched.length === 1
        ? [40, 30, 30]
        : [34, 33, 33]
      : matched.length === 1
      ? [40, 20, 20, 20]
      : matched.length === 2
      ? [35, 35, 15, 15]
      : [30, 30, 20, 20];

  return annotateBiggestGap(
    source.map((kpi, idx) => seriesFromKpi(kpi, weights[idx] ?? round1(100 / Math.max(1, count)))),
  );
}

function gapsFor(
  card: FunctionRoleCard,
  roleTitle: string,
  functionName: string,
  signal: string,
  kpis: RoleKpiSeries[],
): RoleAccountabilityGap[] {
  const holders =
    card.members.length > 1
      ? `${roleTitle} (${card.members.map((m) => m.personName).join(', ')})`
      : `${card.personName} (${roleTitle})`;
  const ownership = `Accountable owner: ${holders} · ${functionName}`;
  const fromKpis = kpis.flatMap((kpi) => {
    const latest = kpi.trend6Mo[kpi.trend6Mo.length - 1];
    if (latest?.metTarget !== false) return [];
    return [
      {
        id: `gap-${kpi.id}`,
        statement: `${kpi.shortName}: ${kpi.actualDisplay} actual vs ${kpi.targetDisplay} target (${kpi.gapLabel})`,
        ownership,
      },
    ];
  });
  if (fromKpis.length) return fromKpis;
  if (signal) {
    return [{ id: 'gap-signal', statement: signal, ownership }];
  }
  return [
    {
      id: 'gap-clear',
      statement: 'All owned KPIs are meeting or exceeding monthly targets.',
      ownership,
    },
  ];
}

function actionStatus(value: string | null | undefined): RoleAssignedAction['status'] {
  if (value === 'In Progress' || value === 'Completed' || value === 'Open' || value === 'Cancelled') return value;
  return 'Open';
}

function noteFields(note: string | null | undefined): {
  owner?: string;
  status?: RoleAssignedAction['status'];
  expectedImpact?: string;
} {
  if (!note) return {};
  const owner = note.match(/Owner:\s*([^.]*)\./)?.[1]?.trim();
  const status = note.match(/Status:\s*([^.]*)\./)?.[1]?.trim();
  const expectedImpact = note.match(/Expected impact:\s*([^.]*)\./)?.[1]?.trim();
  return {
    owner: owner || undefined,
    status: status ? actionStatus(status) : undefined,
    expectedImpact: expectedImpact || undefined,
  };
}

function seriesFromHistory(history: ExecRecord[], anchorPeriodKey: string): RoleKpiSeries[] {
  const periodMap = new Map<string, ExecRecord[]>();
  for (const record of history) {
    const existing = periodMap.get(record.period.key);
    if (existing) {
      existing.push(record);
    } else {
      periodMap.set(record.period.key, [record]);
    }
  }
  const sortedKeys = [...periodMap.keys()].sort();
  const latestKey = sortedKeys[sortedKeys.length - 1];
  if (!latestKey) return [];
  const prevKey = sortedKeys.length >= 2 ? sortedKeys[sortedKeys.length - 2] : undefined;
  const latestRecords = periodMap.get(latestKey) ?? [];
  const prevRecords = prevKey ? (periodMap.get(prevKey) ?? []) : [];
  const latestRows = kpiRows(latestRecords, prevRecords).slice(0, 6);
  if (!latestRows.length) return [];

  const sixSlots = buildTrailingSixPeriods(anchorPeriodKey || latestKey);
  const rawWeights = latestRows.map((row) =>
    row.weight !== null && Number.isFinite(row.weight) && row.weight > 0
      ? row.weight <= 1
        ? row.weight * 100
        : row.weight
      : 0,
  );
  const totalRawWeight = rawWeights.reduce((sum, w) => sum + w, 0);
  const defaultWeight = round1(100 / Math.max(1, latestRows.length));

  const series = latestRows.map((row, rowIdx) => {
    const betterDirection: RoleKpiSeries['betterDirection'] = String(row.kpi_direction ?? '')
      .toLowerCase()
      .startsWith('lower')
      ? 'lower'
      : 'higher';
    const unit = row.unit || '%';
    const rowLabelSlug = slugifyIdentifier(row.kpi_label);

    const rawSlots = sixSlots.map((slot) => {
      const slotRecords = periodMap.get(slot.periodKey) ?? [];
      const slotRows = slotRecords.length ? kpiRows(slotRecords, []) : [];
      const point = slotRows.find(
        (item) =>
          item.kpi_key === row.kpi_key ||
          slugifyIdentifier(item.kpi_label) === rowLabelSlug ||
          item.kpi_label.trim().toLowerCase() === row.kpi_label.trim().toLowerCase(),
      );
      return {
        month: slot.month,
        periodKey: slot.periodKey,
        actual: point?.actual ?? null,
        target: point?.target ?? null,
      };
    });

    // Ensure the latest slot has the current row's actual & target
    const lastIdx = rawSlots.length - 1;
    if (rawSlots[lastIdx].actual === null && row.actual !== null) {
      rawSlots[lastIdx].actual = row.actual;
    }
    if (rawSlots[lastIdx].target === null && row.target !== null) {
      rawSlots[lastIdx].target = row.target;
    }

    const trend6Mo: KpiMonthlyPoint[] = rawSlots.map((slot) => {
      const actual = slot.actual;
      const target = actual !== null ? (slot.target ?? row.target) : slot.target;
      const metTarget =
        actual == null || target == null
          ? null
          : betterDirection === 'lower'
          ? actual <= target + 1e-6
          : actual >= target - 1e-6;
      return {
        month: slot.month,
        periodKey: slot.periodKey,
        actual,
        target,
        actualFormatted: formatKpiValue(actual, unit),
        targetFormatted: formatKpiValue(target, unit),
        metTarget,
      };
    });

    const last = trend6Mo[trend6Mo.length - 1];
    const actual = last?.actual ?? null;
    const target = last?.target ?? null;
    let gapLabel = 'No target';
    if (actual != null && target != null) {
      const delta = round1(actual - target);
      const worse = betterDirection === 'lower' ? delta > 0 : delta < 0;
      gapLabel = worse ? `${formatKpiValue(Math.abs(delta), unit)} off target` : 'On target';
    }
    const resolvedWeight =
      totalRawWeight > 0 && rawWeights[rowIdx] > 0 ? rawWeights[rowIdx] : defaultWeight;
    const metrics = computeKpiMetrics(
      row.achievement_percent ?? 0,
      resolvedWeight,
      betterDirection,
      trend6Mo,
      gapLabel,
    );
    const diagnosis =
      gapLabel === 'On target'
        ? `${row.kpi_label} achieved ${formatKpiValue(actual, unit)} against the ${formatKpiValue(target, unit)} target (${(row.achievement_percent ?? 100).toFixed(1)}% achievement · ${metrics.contributionPct.toFixed(1)}% of ${Math.round(metrics.weightPct)}% weight).`
        : `${row.kpi_label} stood at ${formatKpiValue(actual, unit)} vs the ${formatKpiValue(target, unit)} target (${gapLabel}, ${(row.achievement_percent ?? 0).toFixed(1)}% achievement · −${metrics.pointsLost.toFixed(1)} pts on role score).`;
    return {
      id: row.kpi_key,
      kpiKey: row.kpi_key,
      name: row.kpi_label,
      shortName: row.kpi_label,
      unit,
      betterDirection,
      actualDisplay: formatKpiValue(actual, unit),
      targetDisplay: formatKpiValue(target, unit),
      achievementPct: row.achievement_percent ?? 0,
      ...metrics,
      gapLabel,
      diagnosis,
      structuralDiagnosis: buildStructuralDiagnosis(row.kpi_label, trend6Mo, gapLabel),
      trend6Mo,
    };
  });

  return annotateBiggestGap(series);
}

function historyForPerson(records: ExecRecord[], card: FunctionRoleCard, periodKey: string): ExecRecord[] {
  const memberIds = new Set(card.members.map((m) => m.employeeId.toLowerCase()));
  const memberNames = new Set(card.members.map((m) => m.personName.toLowerCase()));
  return records
    .filter((record) => {
      if (record.period.key > periodKey) return false;
      const sameId = Boolean(record.employeeId) && memberIds.has(record.employeeId.toLowerCase());
      const sameName =
        memberNames.has(record.name.toLowerCase()) ||
        card.members.some((m) => namesMatch(record.name, m.personName));
      return sameId || sameName;
    })
    .sort((a, b) => a.period.key.localeCompare(b.period.key));
}

function actionsForRole(
  data: CallCenterDeepDiveData,
  card: FunctionRoleCard,
  stored: PMSAction[],
  kpis: RoleKpiSeries[],
): RoleAssignedAction[] {
  const month = data.monthLabel.split(' ')[0] || '';
  const memberNames = new Set(card.members.map((m) => m.personName.toLowerCase()));
  const memberIds = new Set(card.members.map((m) => m.employeeId.toLowerCase()));
  const lowMembers = card.members.filter((m) => m.score < 90).map((m) => m.personName);
  const defaultAffectedPeople =
    lowMembers.length > 0 ? lowMembers : card.members.map((m) => m.personName);
  const offTargetKpis = kpis.filter((k) => k.gapLabel !== 'On target');
  const defaultLinkedKpi =
    offTargetKpis[0]?.shortName || kpis[0]?.shortName || card.linkedKpis[0] || 'Role Execution';

  const fromStore = stored
    .filter((action) => {
      const name = (action.employee_name || '').toLowerCase();
      const empId = (action.employee_id || '').toLowerCase();
      const team = (action.team || '').toLowerCase();
      const sameMonth = !action.month || !month || action.month === month;
      return (
        sameMonth &&
        (memberNames.has(name) ||
          memberIds.has(empId) ||
          card.members.some((m) => namesMatch(action.employee_name || '', m.personName)) ||
          name === card.personName.toLowerCase() ||
          team === card.roleTitle.toLowerCase())
      );
    })
    .map((action) => {
      const parsed = noteFields(action.root_cause_note);
      const matchedKpi = action.linked_kpi_key
        ? kpis.find((k) => k.kpiKey === action.linked_kpi_key || k.id === action.linked_kpi_key)
        : undefined;
      const matchedMember = card.members.find(
        (m) =>
          m.personName.toLowerCase() === (action.employee_name || '').toLowerCase() ||
          m.employeeId.toLowerCase() === (action.employee_id || '').toLowerCase() ||
          namesMatch(action.employee_name || '', m.personName),
      );
      return {
        id: action.id,
        title: `${card.roleTitle} Intervention`,
        description: action.action_text,
        owner: parsed.owner || action.owner?.name || card.roleTitle,
        dueDate: action.due_date ?? null,
        status: parsed.status || actionStatus(action.status),
        expectedImpact:
          parsed.expectedImpact ||
          action.root_cause_note ||
          'Expected impact recorded with the action',
        linkedKpiName: matchedKpi?.shortName || defaultLinkedKpi,
        affectedPeople: matchedMember ? [matchedMember.personName] : defaultAffectedPeople,
      };
    });

  const planned = data.actionsByPosition.items
    .filter((item) => {
      const sameRole = item.owningPosition.toLowerCase() === card.roleTitle.toLowerCase();
      const matchesKpi = card.linkedKpis.some(
        (kpi) =>
          item.targetScope.toLowerCase().includes(kpi.toLowerCase()) ||
          item.actionTitle.toLowerCase().includes(kpi.toLowerCase()),
      );
      return sameRole || matchesKpi;
    })
    .map((item) => ({
      id: item.id,
      title: item.actionTitle,
      description: `Target KPI scope: ${item.targetScope} — ${item.expectedKpiOutcome}`,
      owner: item.owningPosition,
      dueDate: '2026-10-18',
      status: 'Open' as const,
      expectedImpact: `+${item.expectedImpactPct.toFixed(1)}% expected lift`,
      linkedKpiName: item.targetScope || defaultLinkedKpi,
      affectedPeople: defaultAffectedPeople,
    }));

  const combined = [...fromStore, ...planned];
  if (combined.length < 2 && card.score < 90) {
    const firstKpi = offTargetKpis[0];
    const secondKpi = offTargetKpis[1];

    if (combined.length === 0) {
      const primaryName = firstKpi?.shortName || card.linkedKpis[0] || 'Primary KPI';
      combined.push({
        id: `role-baseline-action-1-${card.roleSlug}`,
        title: `Close ${primaryName} gap in ${card.roleTitle}`,
        description: firstKpi
          ? `Move ${firstKpi.shortName} from ${firstKpi.actualDisplay} toward the ${firstKpi.targetDisplay} target via weekly pacing checkpoints and root-cause coaching.`
          : `Address ${card.signal} through weekly milestone reviews and pre-delivery QA checks.`,
        owner: card.roleTitle,
        dueDate: '2026-10-18',
        status: 'In Progress' as const,
        expectedImpact: `+${Math.min(6.0, Math.max(2.0, round1((90 - card.score) * 0.3))).toFixed(1)}% role score lift`,
        linkedKpiName: primaryName,
        affectedPeople: defaultAffectedPeople,
      });
    }

    if (combined.length === 1 && (secondKpi || card.members.length > 1)) {
      const secondaryName = secondKpi?.shortName || 'Execution Consistency';
      combined.push({
        id: `role-baseline-action-2-${card.roleSlug}`,
        title: `Standardize ${secondaryName} workflow across ${card.roleTitle}`,
        description: secondKpi
          ? `Rebalance campaign/workload allocation to close the ${secondKpi.gapLabel} variance on ${secondKpi.shortName} (${secondKpi.actualDisplay} vs ${secondKpi.targetDisplay}).`
          : `Align quality benchmarks across all ${card.headcount} members in ${card.roleTitle} to bring scores above the 90% threshold.`,
        owner: card.roleTitle,
        dueDate: '2026-10-25',
        status: 'Open' as const,
        expectedImpact: `+${Math.min(4.5, Math.max(1.5, round1((90 - card.score) * 0.2))).toFixed(1)}% role score lift`,
        linkedKpiName: secondaryName,
        affectedPeople: defaultAffectedPeople,
      });
    }
  }

  const seen = new Set<string>();
  return combined.filter((item) => {
    if (seen.has(item.id)) return false;
    seen.add(item.id);
    return true;
  });
}

function buildRoleExecutiveDiagnosis(
  roleTitle: string,
  card: FunctionRoleCard,
  functionName: string,
  kpis: RoleKpiSeries[],
  supportExplanation?: string,
): string {
  if (supportExplanation && supportExplanation.length > 45) {
    return supportExplanation;
  }
  const offTarget = kpis.filter((k) => k.gapLabel !== 'On target');
  if (card.headcount > 1) {
    const distinctSignals = [...new Set(card.members.map((m) => m.signal).filter(Boolean))];
    if (card.score < 90) {
      const gapSummary =
        offTarget.length >= 2
          ? `${offTarget[0].shortName} (${offTarget[0].actualDisplay} vs ${offTarget[0].targetDisplay}) and ${offTarget[1].shortName} (${offTarget[1].actualDisplay} vs ${offTarget[1].targetDisplay})`
          : distinctSignals.slice(0, 2).join(' and ') || card.signal;
      return `${roleTitle} averages ${card.score.toFixed(1)}% (${card.gradeFullLabel}) across ${card.headcount} people in this role (${card.below90Count} below 90%) — performance is primarily pulled down by ${gapSummary}.`;
    }
    return `${roleTitle} averages ${card.score.toFixed(1)}% (${card.gradeFullLabel}) across ${card.headcount} people in this role, sustaining ${functionName} benchmark stability.`;
  }

  if (card.score < 90) {
    const primaryGap =
      offTarget.length >= 2
        ? `${offTarget[0].shortName} (${offTarget[0].actualDisplay} vs ${offTarget[0].targetDisplay}) and ${offTarget[1].shortName} (${offTarget[1].actualDisplay} vs ${offTarget[1].targetDisplay})`
        : card.signal;
    return `Evaluated at ${card.score.toFixed(1)}% (${card.gradeFullLabel}) — primary drag on ${functionName} is ${primaryGap}.`;
  }

  return `Delivering ${card.score.toFixed(1)}% (${card.gradeFullLabel}) benchmark execution — ${card.signal}.`;
}

export function buildRoleDetail(
  data: CallCenterDeepDiveData,
  roleSlug: string,
  actions: PMSAction[] = [],
  records: ExecRecord[] = [],
): RoleDetailData {
  const slug = slugifyIdentifier(roleSlug) || roleSlug;
  const cards = resolveRoleCards(data, records);
  const support = supportForSlug(data, slug);

  const supportCardRaw = support
    ? aggregateSeedsByRole(parseHoldersFromSupportPosition(support, data))[0]
    : null;
  const supportCard =
    supportCardRaw && support?.evaluatedScore != null
      ? {
          ...supportCardRaw,
          score: round1(support.evaluatedScore),
          grade: gradeForScore(round1(support.evaluatedScore)),
          gradeFullLabel: fullGradeLabel(gradeForScore(round1(support.evaluatedScore))),
          gap: round1(round1(support.evaluatedScore) - 100),
        }
      : supportCardRaw;

  const normSlug = slugifyIdentifier(roleSlug);
  const card =
    cards.find((item) => item.roleSlug === slug) ||
    cards.find((item) => slugifyIdentifier(item.roleTitle) === slug) ||
    cards.find((item) => slugifyIdentifier(normalizeRoleTitle(item.roleTitle)) === slug) ||
    cards.find((item) => item.roleSlug === normSlug) ||
    cards.find((item) => slugifyIdentifier(normalizeRoleTitle(item.roleTitle)) === normSlug) ||
    cards.find((item) => item.members.some((m) => slugifyIdentifier(m.personName) === slug)) ||
    cards.find((item) => item.members.some((m) => namesMatch(m.personName, roleSlug))) ||
    supportCard;

  const roleTitle = card?.roleTitle || support?.positionName || canonicalFunctionNameFromSlug(slug);
  const personName = card?.personName || support?.holderName || roleTitle;
  const score = support?.evaluatedScore != null ? round1(support.evaluatedScore) : (card?.score ?? data.headline.score);
  const grade = gradeForScore(score);
  const linked = card?.linkedKpis || support?.linkedKpis || [];

  const resolvedCard: FunctionRoleCard = card
    ? {
        ...card,
        score,
        grade,
        gradeFullLabel: fullGradeLabel(grade),
        gap: round1(score - 100),
      }
    : {
        roleSlug: slug,
        roleTitle,
        personName,
        employeeId: personName,
        headcount: 1,
        below90Count: score < 90 ? 1 : 0,
        members: [
          {
            employeeId: personName,
            personName,
            score,
            grade,
            gradeFullLabel: fullGradeLabel(grade),
            gap: round1(score - 100),
            changeVsPrev: null,
            signal: `${roleTitle} is scored at ${score.toFixed(1)}% inside ${data.functionName}.`,
            keyKpiLabel: linked[0] || 'Role Execution',
            keyKpiActual: `${score.toFixed(1)}%`,
            keyKpiTarget: '90.0%',
            keyKpiMet: score >= 90,
          },
        ],
        score,
        grade,
        gradeFullLabel: fullGradeLabel(grade),
        gap: round1(score - 100),
        changeVsPrev: null,
        signal: `${roleTitle} is scored at ${score.toFixed(1)}% inside ${data.functionName}.`,
        linkedKpis: linked,
        impactLevel: impactFromScore(score),
      };

  const personal = seriesFromHistory(
    historyForPerson(records, resolvedCard, data.periodKey),
    data.periodKey,
  );
  const functionKpis = kpisForRole(data, linked);
  const kpis = personal.length > 0 ? personal : functionKpis;
  const kpiScope: RoleDetailData['kpiScope'] = personal.length > 0 ? 'role' : 'function';
  const primaryRoleKpi = kpis[0];
  const tableKpis = kpis.slice(0, 4);

  const enrichedMembers: RoleMemberItem[] = resolvedCard.members.map((m) => {
    const baseMember =
      m.keyKpiLabel === 'Role Execution' && primaryRoleKpi
        ? {
            ...m,
            keyKpiLabel: primaryRoleKpi.shortName,
            keyKpiActual: primaryRoleKpi.actualDisplay,
            keyKpiTarget: primaryRoleKpi.targetDisplay,
            keyKpiMet: primaryRoleKpi.gapLabel === 'On target',
          }
        : m;

    const memberRecord = records.find(
      (rec) =>
        rec.period.key === data.periodKey &&
        (rec.employeeId.toLowerCase() === baseMember.employeeId.toLowerCase() ||
          rec.name.toLowerCase() === baseMember.personName.toLowerCase() ||
          namesMatch(rec.name, baseMember.personName)),
    );
    const memberKpiRows = memberRecord ? kpiRows([memberRecord], []) : [];
    const baselineKpis = getBaselineMemberKpis(baseMember.personName);

    const kpiCells: RoleMemberKpiCell[] = tableKpis.map((kpi, idx) => {
      const matchedRow = memberKpiRows.find(
        (r) =>
          r.kpi_key === kpi.kpiKey ||
          kpiLabelsMatch(r.kpi_label, kpi.shortName, r.kpi_key, kpi.kpiKey) ||
          kpiLabelsMatch(r.kpi_label, kpi.name, r.kpi_key, kpi.kpiKey),
      );
      if (matchedRow) {
        const ach = matchedRow.achievement_percent ?? kpi.achievementPct;
        const targetStr =
          matchedRow.target != null
            ? formatKpiValue(matchedRow.target, matchedRow.unit || kpi.unit)
            : kpi.targetDisplay;
        return {
          kpiKey: kpi.kpiKey,
          label: kpi.shortName,
          actualFormatted: formatKpiValue(matchedRow.actual, matchedRow.unit || kpi.unit),
          targetFormatted: targetStr,
          achievementPct: ach,
          metTarget: ach >= 99.9,
        };
      }

      if (baselineKpis) {
        const matchedBaseline = baselineKpis.find(
          (b) =>
            kpiLabelsMatch(b.label, kpi.shortName, undefined, kpi.kpiKey) ||
            kpiLabelsMatch(b.label, kpi.name, undefined, kpi.kpiKey),
        );
        if (matchedBaseline) {
          return {
            kpiKey: kpi.kpiKey,
            label: kpi.shortName,
            actualFormatted: matchedBaseline.actualFormatted,
            targetFormatted: matchedBaseline.targetFormatted || kpi.targetDisplay,
            achievementPct: matchedBaseline.achievementPct,
            metTarget: matchedBaseline.metTarget,
          };
        }
      }

      if (memberRecord) {
        return {
          kpiKey: kpi.kpiKey,
          label: kpi.shortName,
          actualFormatted: '—',
          targetFormatted: kpi.targetDisplay,
          achievementPct: 0,
          metTarget: false,
        };
      }

      const labelLower = kpi.shortName.toLowerCase();
      const memberKeyLower = baseMember.keyKpiLabel.toLowerCase();
      if (
        labelLower.includes(memberKeyLower) ||
        memberKeyLower.includes(labelLower)
      ) {
        return {
          kpiKey: kpi.kpiKey,
          label: kpi.shortName,
          actualFormatted: baseMember.keyKpiActual,
          targetFormatted: kpi.targetDisplay,
          achievementPct: baseMember.keyKpiMet ? 100 : Math.min(95, Math.max(45, baseMember.score - 3)),
          metTarget: baseMember.keyKpiMet,
        };
      }

      const latestPt = kpi.trend6Mo[kpi.trend6Mo.length - 1];
      const roleScore = Math.max(40, resolvedCard.score || 85);
      const ratio = Math.max(0.78, Math.min(1.18, baseMember.score / roleScore));
      if (latestPt?.actual != null) {
        const scaledActual =
          kpi.betterDirection === 'lower'
            ? round1(latestPt.actual / ratio)
            : round1(latestPt.actual * ratio);
        const scaledAch = round1(Math.min(100, Math.max(20, kpi.achievementPct * ratio)));
        const met =
          latestPt.target != null
            ? kpi.betterDirection === 'lower'
              ? scaledActual <= latestPt.target + 1e-6
              : scaledActual >= latestPt.target - 1e-6
            : scaledAch >= 99.5;
        return {
          kpiKey: kpi.kpiKey,
          label: kpi.shortName,
          actualFormatted: formatKpiValue(scaledActual, kpi.unit),
          targetFormatted: kpi.targetDisplay,
          achievementPct: scaledAch,
          metTarget: met,
        };
      }

      return {
        kpiKey: kpi.kpiKey,
        label: kpi.shortName,
        actualFormatted: idx === 0 ? baseMember.keyKpiActual : kpi.actualDisplay,
        targetFormatted: kpi.targetDisplay,
        achievementPct: kpi.achievementPct,
        metTarget: kpi.gapLabel === 'On target',
      };
    });

    return {
      ...baseMember,
      kpiCells,
    };
  });

  const individualActionPlans: RoleIndividualActionPlan[] = enrichedMembers.map((member) => {
    const storedForMember = actions.find(
      (a) =>
        (a.employee_id || '').toLowerCase() === member.employeeId.toLowerCase() ||
        (a.employee_name || '').toLowerCase() === member.personName.toLowerCase() ||
        namesMatch(a.employee_name || '', member.personName),
    );
    const parsed = noteFields(storedForMember?.root_cause_note);
    const missedCells = (member.kpiCells ?? []).filter((c) => !c.metTarget && c.actualFormatted !== '—');
    const mainIssue =
      member.signal ||
      (missedCells.length > 0
        ? missedCells
            .slice(0, 2)
            .map(
              (c) =>
                `${c.label} at ${c.actualFormatted} (vs ${c.targetFormatted} target, ${c.achievementPct.toFixed(1)}% achievement)`,
            )
            .join(' & ')
        : `${member.keyKpiLabel} at ${member.keyKpiActual} (vs ${member.keyKpiTarget} target)`);

    const defaultActionText =
      member.score < 90
        ? `Conduct weekly 1-on-1 coaching with ${member.personName} on ${member.keyKpiLabel} (${member.keyKpiActual} vs ${member.keyKpiTarget} target), audit root-cause bottlenecks, and track daily pacing checkpoints through ${data.monthLabel}.`
        : `Sustain ${member.personName}'s benchmark execution (${member.score.toFixed(1)}%) and pair as peer reviewer on ${member.keyKpiLabel} workflows across ${roleTitle}.`;

    const empLift = Math.max(2.0, round1((92 - Math.min(90, member.score)) * 0.55));
    const roleLift = Math.max(0.4, round1(empLift / Math.max(1, resolvedCard.headcount)));

    return {
      id: `ind-role-${resolvedCard.roleSlug}-${slugifyIdentifier(member.employeeId)}`,
      employeeId: member.employeeId,
      personName: member.personName,
      score: member.score,
      grade: member.grade,
      gradeFullLabel: member.gradeFullLabel,
      mainIssue,
      actionText: storedForMember?.action_text || defaultActionText,
      owner: parsed.owner || storedForMember?.owner?.name || `${roleTitle} Lead`,
      expectedImpact:
        parsed.expectedImpact ||
        `+${empLift.toFixed(1)}% employee score (+${roleLift.toFixed(1)}% role lift)`,
      linkedKpiKey:
        storedForMember?.linked_kpi_key ||
        missedCells[0]?.kpiKey ||
        primaryRoleKpi?.kpiKey ||
        'role-kpi',
    };
  });

  const impactLevel = support?.impactLevel || card?.impactLevel || impactFromScore(score);
  const diagnosis = buildRoleExecutiveDiagnosis(
    roleTitle,
    resolvedCard,
    data.functionName,
    kpis,
    support?.explanation,
  );

  return {
    roleSlug: resolvedCard.roleSlug,
    roleTitle,
    personName: resolvedCard.personName,
    employeeId: resolvedCard.employeeId,
    headcount: resolvedCard.headcount,
    below90Count: resolvedCard.below90Count,
    members: enrichedMembers,
    functionSlug: data.functionSlug,
    functionName: data.functionName,
    regionName: data.regionName,
    monthLabel: data.monthLabel,
    previousMonthLabel: data.previousMonthLabel,
    periodKey: data.periodKey,
    score,
    grade,
    gradeFullLabel: fullGradeLabel(grade),
    gap: round1(score - 100),
    changeVsPrev: resolvedCard.changeVsPrev,
    diagnosis,
    impactLevel,
    impactDiagnosis: support?.evidenceStat || card?.signal || diagnosis,
    accountableKpis: kpis.length ? kpis.map((kpi) => kpi.shortName) : linked,
    accountabilityGaps: gapsFor(
      resolvedCard,
      roleTitle,
      data.functionName,
      resolvedCard.signal,
      kpis,
    ),
    kpis,
    kpiScope,
    individualActionPlans,
    actions: actionsForRole(data, resolvedCard, actions, kpis),
  };
}
