import type { AiStarterPrompt } from './types';

const CALL_CENTER_TEAMS = new Set(['inbound', 'outbound', 'call center', 'support positions']);

export function isCallCenterStarterScope(
  functionName: string | null | undefined,
  team: string | null | undefined,
): boolean {
  const fn = (functionName || '').trim().toLowerCase();
  const teamName = (team || '').trim().toLowerCase();
  return fn === 'call center' || CALL_CENTER_TEAMS.has(teamName);
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
}): AiStarterPrompt[] {
  const functionName = input.functionName?.trim() || null;
  const team = input.team && input.team !== 'All' ? input.team : null;
  const callCenter = isCallCenterStarterScope(functionName, team);
  const teamLabel = team || functionName || (callCenter ? 'Call Center' : 'All authorized departments');
  const branch = input.branch && input.branch.toLowerCase() !== 'all' ? input.branch : null;
  const branchLabel = branch ? branch.charAt(0).toUpperCase() + branch.slice(1) : null;
  const scopeSuffix = branchLabel ? ` in ${branchLabel}` : '';

  if (!callCenter) {
    return [
      {
        id: 'team-drop',
        label: `Which team in ${teamLabel} dropped most?`,
        subtitle: 'Identify the team with the largest performance drop and see key drivers.',
        badge: 'TEAM',
        prompt: `Which team in ${teamLabel} dropped the most this month${scopeSuffix}, what is the main KPI driver, and what decisions do you recommend?`,
        category: 'team',
        icon_key: 'users',
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
        id: 'branch-compare',
        label: 'Compare branches',
        subtitle: 'Compare performance across the branches in this scope.',
        badge: 'BRANCH',
        prompt: `Compare branch performance for ${teamLabel}${scopeSuffix} and recommend branch decisions.`,
        category: 'branch',
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
        id: 'agent-spotlight-trend',
        label: `Top performer in ${teamLabel}`,
        subtitle: 'Spotlight of the top performer with score and trend.',
        badge: 'PEOPLE',
        prompt: `Who is the top performer in ${teamLabel} and what is their score trend?`,
        category: 'people',
        icon_key: 'users',
      },
    ];
  }

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
      id: 'people-root-cause',
      label: 'Who caused the Attendance gap?',
      subtitle: 'Find employees driving the attendance gap and What-If coaching ROI.',
      badge: 'PEOPLE',
      prompt: `Who are the top negative contributors to the Attendance Rate gap in ${teamLabel}${scopeSuffix} and what happens if we coach the bottom 3?`,
      category: 'people',
      icon_key: 'users',
    },
    {
      id: 'branch-compare',
      label: 'Compare Dubai vs Sharjah & Branches',
      subtitle: 'Compare attendance, bookings, and no-shows across all UAE branches.',
      badge: 'BRANCH',
      prompt: `Compare all UAE branches (Dubai, Sharjah, Ajman, Clinics) Attendance and Booking conversion for ${teamLabel} and recommend branch decisions.`,
      category: 'branch',
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
      id: 'agent-spotlight-trend',
      label: 'Best Agent & 6-Month Score Trend',
      subtitle: 'Instant spotlight of the #1 agent with grade, KPIs, and 6-month trend.',
      badge: 'TREND',
      prompt: `Who is the best agent in ${teamLabel === 'Call Center' ? 'Inbound' : teamLabel} and his trend?`,
      category: 'people',
      icon_key: 'users',
    },
    {
      id: 'outbound-paradox',
      label: 'Outbound Booking vs. No-Show',
      subtitle: 'Diagnose why Booking is 100% while Attendance is 56.6% with actions.',
      badge: 'DECISIONS',
      prompt:
        'Diagnose Outbound KPIs (Attendance Rate, Reachability, Booking Rate) and propose an executive decision playbook to reduce patient no-shows.',
      category: 'kpi',
      icon_key: 'chart',
    },
  ];
}
