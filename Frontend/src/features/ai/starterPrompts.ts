import type { AiStarterPrompt } from './types';

const CALL_CENTER_TEAMS = new Set(['inbound', 'outbound', 'call center', 'support positions']);

export function isCallCenterStarterScope(
  functionName: string | null | undefined,
  team: string | null | undefined,
): boolean {
  const fn = (functionName || '').trim().toLowerCase();
  const teamName = (team || '').trim().toLowerCase();
  return teamName && teamName !== 'all' ? CALL_CENTER_TEAMS.has(teamName) : fn === 'call center';
}

/**
 * Client fallback used before `/api/ai/watching` returns starter prompts.
 * An empty or non-Call-Center scope must not advertise Call Center scenarios.
 * An explicit Call Center scope keeps the operational prompts.
 */
export function buildFallbackStarterPrompts(input: {
  functionName?: string | null;
  team?: string | null;
  branch?: string | null;
  region?: string | null;
}): AiStarterPrompt[] {
  const functionName = input.functionName?.trim() || null;
  const team = input.team && input.team !== 'All' ? input.team : null;
  const callCenter = isCallCenterStarterScope(functionName, team);
  const teamLabel = team || functionName || (callCenter ? 'Call Center' : 'All authorized departments');
  const branch = input.branch && input.branch.toLowerCase() !== 'all' ? input.branch : null;
  const branchLabel = branch ? branch.charAt(0).toUpperCase() + branch.slice(1) : null;
  const scopeSuffix = branchLabel ? ` in ${branchLabel}` : '';

  if (!callCenter) {
    const namedScope = Boolean(team || functionName);
    return [
      {
        id: 'scope-review',
        label: namedScope ? `Review ${teamLabel} performance` : 'Review overall performance',
        subtitle: 'See the published score and key findings for the selected period.',
        badge: 'PERFORMANCE',
        prompt: namedScope ? `Review ${teamLabel} performance${scopeSuffix}` : `Review overall performance${scopeSuffix}`,
        category: 'team',
        icon_key: 'users',
      },
      {
        id: 'team-score-trend',
        label: `Monthly score & 6-month trend (${teamLabel})`,
        subtitle: 'Track weighted score progression and consecutive monthly shifts.',
        badge: 'TREND',
        prompt: `What is ${teamLabel} overall score and 6-month performance trend${scopeSuffix}?`,
        category: 'team',
        icon_key: 'chart',
      },
      {
        id: 'people-root-cause',
        label: `Top negative contributors in ${teamLabel}`,
        subtitle: 'Find the employees driving KPI gaps and coaching opportunities.',
        badge: 'PEOPLE',
        prompt: `Who are the top negative contributors in ${teamLabel}${scopeSuffix} and what happens if we coach the bottom 3?`,
        category: 'people',
        icon_key: 'users',
      },
      {
        id: 'agent-spotlight-trend',
        label: `Top performer in ${teamLabel}`,
        subtitle: 'Spotlight of the top performer with score and trend.',
        badge: 'PEOPLE',
        prompt: `Who is the top performer in ${teamLabel}${scopeSuffix} and what is their score trend?`,
        category: 'people',
        icon_key: 'users',
      },
      {
        id: 'branch-compare',
        label: 'Compare branches',
        subtitle: 'Compare performance across the branches in this scope.',
        badge: 'BRANCH',
        prompt: `Compare branch performance for ${teamLabel}${scopeSuffix} and recommend branch decisions.`,
        category: 'branch',
        icon_key: 'chart',
      },
      {
        id: 'branch-leader-gap',
        label: `Top vs lagging branch (${teamLabel})`,
        subtitle: 'Surface branch-level score spreads and operational volume gaps.',
        badge: 'BRANCH',
        prompt: `Which branch leads and which lags in ${teamLabel}${scopeSuffix}?`,
        category: 'branch',
        icon_key: 'chart',
      },
      {
        id: 'kpi-gaps',
        label: `Largest KPI gaps (${teamLabel})`,
        subtitle: 'Pinpoint weighted KPI misses versus target and recovery priority.',
        badge: 'KPI',
        prompt: `Show the largest KPI gaps against target in ${teamLabel}${scopeSuffix} with recommended actions.`,
        category: 'kpi',
        icon_key: 'chart',
      },
      {
        id: 'kpi-driver-impact',
        label: `KPI weight & score drivers (${teamLabel})`,
        subtitle: 'See which weighted metrics drove this period’s score movement.',
        badge: 'KPI',
        prompt: `Which weighted KPIs drove the latest score change in ${teamLabel}${scopeSuffix}?`,
        category: 'kpi',
        icon_key: 'chart',
      },
      {
        id: 'governance-actions',
        label: 'Pending corrective actions',
        subtitle: 'Review open corrective actions and items with owners and due dates.',
        badge: 'GOVERNANCE',
        prompt: `Summarize open or overdue corrective actions in ${teamLabel} with recommended next steps.`,
        category: 'governance',
        icon_key: 'shield',
      },
      {
        id: 'governance-sla-risk',
        label: `Overdue actions & follow-up risk (${teamLabel})`,
        subtitle: 'Highlight overdue follow-ups and draft priority next steps.',
        badge: 'GOVERNANCE',
        prompt: `Which corrective actions are overdue or due soon in ${teamLabel} and what follow-up is needed?`,
        category: 'governance',
        icon_key: 'shield',
      },
    ];
  }

  const teamNorm = (team || '').trim().toLowerCase();
  const regionNorm = (input.region || '').trim().toLowerCase();
  const isSupportPositions = teamNorm === 'support positions';
  const isEgyScope =
    regionNorm === 'egy' ||
    regionNorm === 'egypt' ||
    teamNorm.includes('egy') ||
    teamNorm.includes('offshore');
  const isUaeBranchCc = !isSupportPositions && !isEgyScope;
  const spotlightTeam = teamLabel === 'Call Center' ? 'Inbound' : teamLabel;
  const kpiScenarioPrimary: AiStarterPrompt =
    teamNorm === 'inbound'
      ? {
          id: 'inbound-kpi-decisions',
          label: 'Inbound KPI Gaps & Queue Decisions',
          subtitle: 'Diagnose Inbound KPI misses against target and prioritize recovery actions.',
          badge: 'DECISIONS',
          prompt: `Diagnose Inbound KPI gaps against target${scopeSuffix} and propose an executive decision playbook.`,
          category: 'kpi',
          icon_key: 'chart',
        }
      : teamNorm === 'support positions'
        ? {
            id: 'support-kpi-decisions',
            label: 'Support Positions KPI Diagnosis',
            subtitle: 'Inspect Support Positions KPI achievement gaps and operational priorities.',
            badge: 'DECISIONS',
            prompt: `Diagnose Support Positions KPI gaps against target${scopeSuffix} and recommend corrective priorities.`,
            category: 'kpi',
            icon_key: 'chart',
          }
        : {
            id: 'outbound-paradox',
            label: 'Outbound Booking vs. Attendance Gap',
            subtitle: 'Diagnose gaps between Booking conversion and patient Attendance with recovery actions.',
            badge: 'DECISIONS',
            prompt:
              'Diagnose Outbound KPIs (Attendance Rate, Reachability, Booking Rate) and propose an executive decision playbook to reduce patient no-shows.',
            category: 'kpi',
            icon_key: 'chart',
          };

  return [
    {
      id: 'team-drop',
      label: 'Which Call Center team dropped most?',
      subtitle: 'Identify the team with the largest performance drop and key KPI drivers.',
      badge: 'TEAM',
      prompt: `Which Call Center team dropped the most this month${scopeSuffix}, what is the main KPI driver, and what decisions do you recommend?`,
      category: 'team',
      icon_key: 'users',
    },
    {
      id: 'team-score-trend',
      label: `Call Center 6-Month Score Trend (${teamLabel})`,
      subtitle: 'Track consecutive monthly performance direction and inflection points.',
      badge: 'TREND',
      prompt: `Show the 6-month performance trend for ${teamLabel}${scopeSuffix} and explain the latest monthly shift.`,
      category: 'team',
      icon_key: 'chart',
    },
    isSupportPositions
      ? {
          id: 'people-root-cause',
          label: 'Top negative contributors in Support Positions',
          subtitle: 'Find employees driving Support KPI gaps and What-If coaching ROI.',
          badge: 'PEOPLE',
          prompt: `Who are the top negative contributors to weighted KPI gaps in Support Positions${scopeSuffix} and what happens if we coach the bottom 3?`,
          category: 'people',
          icon_key: 'users',
        }
      : !isUaeBranchCc
        ? {
            id: 'people-root-cause',
            label: `Top negative contributors in ${teamLabel}`,
            subtitle: 'Find employees driving KPI gaps and What-If coaching ROI.',
            badge: 'PEOPLE',
            prompt: `Who are the top negative contributors in ${teamLabel}${scopeSuffix} and what happens if we coach the bottom 3?`,
            category: 'people',
            icon_key: 'users',
          }
        : {
            id: 'people-root-cause',
            label: 'Who caused the Attendance gap?',
            subtitle: 'Find employees driving the attendance gap and What-If coaching ROI.',
            badge: 'PEOPLE',
            prompt: `Who are the top negative contributors to the Attendance Rate gap in ${teamLabel}${scopeSuffix} and what happens if we coach the bottom 3?`,
            category: 'people',
            icon_key: 'users',
          },
    {
      id: 'agent-spotlight-trend',
      label: 'Best Agent & 6-Month Score Trend',
      subtitle: 'Instant spotlight of the #1 agent with grade, KPIs, and 6-month trend.',
      badge: 'TREND',
      prompt: `Who is the best agent in ${isUaeBranchCc ? spotlightTeam : teamLabel}${scopeSuffix} and his trend?`,
      category: 'people',
      icon_key: 'users',
    },
    isSupportPositions
      ? {
          id: 'branch-compare',
          label: 'Support Positions KPI & SLA Breakdown',
          subtitle: 'Inspect role-level Support KPI attainment and month-over-month score shifts.',
          badge: 'BRANCH',
          prompt: `Show verified KPI score drivers and 6-month trend for Support Positions${scopeSuffix} and recommend operational decisions.`,
          category: 'branch',
          icon_key: 'chart',
        }
      : !isUaeBranchCc
        ? {
            id: 'branch-compare',
            label: 'Compare EGY teams & KPIs',
            subtitle: 'Compare performance, SLA attainment, and score drivers across teams in your scope.',
            badge: 'BRANCH',
            prompt: `Compare team performance and KPI score drivers for ${teamLabel}${scopeSuffix} and recommend operational decisions.`,
            category: 'branch',
            icon_key: 'chart',
          }
        : {
            id: 'branch-compare',
            label: 'Compare Dubai vs Sharjah & Branches',
            subtitle: 'Compare attendance, bookings, and no-shows across all UAE branches.',
            badge: 'BRANCH',
            prompt: `Compare all UAE branches (Dubai, Sharjah, Ajman, Clinics) Attendance and Booking conversion for ${teamLabel} and recommend branch decisions.`,
            category: 'branch',
            icon_key: 'chart',
          },
    isSupportPositions
      ? {
          id: 'branch-booking-volume',
          label: 'Support Positions Role Score Comparison',
          subtitle: 'Compare score distribution across Quality, Workforce, Training, and Team Leads.',
          badge: 'BRANCH',
          prompt: `Compare Support Positions score drivers and role-level performance in the latest period${scopeSuffix}.`,
          category: 'branch',
          icon_key: 'chart',
        }
      : !isUaeBranchCc
        ? {
            id: 'branch-booking-volume',
            label: `Scope Performance Comparison (${teamLabel})`,
            subtitle: 'Compare verified KPI attainment across authorized teams in this scope.',
            badge: 'BRANCH',
            prompt: `Compare verified KPI achievement across authorized teams in ${teamLabel} for the latest period${scopeSuffix}.`,
            category: 'branch',
            icon_key: 'chart',
          }
        : {
            id: 'branch-booking-volume',
            label: `Branch Booking Volume Comparison (${teamLabel})`,
            subtitle: 'Compare verified booking counts across active UAE branches.',
            badge: 'BRANCH',
            prompt: `Compare branch booking volumes for ${spotlightTeam} in the latest period and highlight the leading branch.`,
            category: 'branch',
            icon_key: 'chart',
          },
    kpiScenarioPrimary,
    {
      id: 'kpi-weight-drivers',
      label: `Top KPI Score Drivers (${teamLabel})`,
      subtitle: 'Break down weighted KPI contributions and fastest-win target gaps.',
      badge: 'KPI',
      prompt: `Which KPIs contributed most to ${spotlightTeam} weighted score${scopeSuffix} and where is the biggest target gap?`,
      category: 'kpi',
      icon_key: 'chart',
    },
    {
      id: 'governance-actions',
      label: 'Pending corrective actions & SIP',
      subtitle: 'Review open corrective actions, overdue items, and SIP candidates.',
      badge: 'GOVERNANCE',
      prompt: `Summarize open or overdue corrective actions and SIP/PI risk candidates in ${teamLabel} with recommended next steps.`,
      category: 'governance',
      icon_key: 'shield',
    },
    {
      id: 'governance-overdue-sla',
      label: `Overdue Follow-Ups & Coaching Queue (${teamLabel})`,
      subtitle: 'Surface overdue corrective actions and recommended manager follow-up.',
      badge: 'GOVERNANCE',
      prompt: `List overdue or due-soon corrective actions in ${teamLabel} and prioritize manager follow-up.`,
      category: 'governance',
      icon_key: 'shield',
    },
  ];
}

const SCENARIO_CATEGORY_ORDER: AiStarterPrompt['category'][] = [
  'team',
  'people',
  'branch',
  'kpi',
  'governance',
];

/**
 * Merge server-returned starter prompts with scoped fallback scenarios so every
 * category tab has at least 2 concrete prompts and never renders blank.
 */
export function mergeStarterScenarios(
  serverPrompts: AiStarterPrompt[],
  fallbackPrompts: AiStarterPrompt[],
): AiStarterPrompt[] {
  const merged: AiStarterPrompt[] = [];
  const seenIds = new Set<string>();
  const seenPrompts = new Set<string>();

  const pushUnique = (item: AiStarterPrompt) => {
    const idKey = item.id.trim().toLowerCase();
    const promptKey = item.prompt.trim().toLowerCase();
    if (seenIds.has(idKey) || seenPrompts.has(promptKey)) {
      return;
    }
    seenIds.add(idKey);
    seenPrompts.add(promptKey);
    merged.push(item);
  };

  for (const sp of serverPrompts) {
    pushUnique(sp);
  }

  for (const cat of SCENARIO_CATEGORY_ORDER) {
    let count = merged.filter((p) => p.category === cat).length;
    if (count >= 2) continue;
    for (const fp of fallbackPrompts) {
      if (fp.category !== cat) continue;
      pushUnique(fp);
      count = merged.filter((p) => p.category === cat).length;
      if (count >= 2) break;
    }
  }

  return merged;
}
