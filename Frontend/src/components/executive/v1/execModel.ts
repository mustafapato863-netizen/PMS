/** Non-component helpers for the Executive v1 cards (kept apart for React fast refresh). */
import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, BarChart3, CheckCircle2, Clock, FileText, Users, type LucideIcon } from 'lucide-react';
import type { GradeClass } from '../../../constants/grades';
import type { ExecutiveActionItem, ExecutiveDriver, ExecutiveFunction, ExecutiveKpiRow, ExecutiveSummary, ExecutiveTeam, ExecutiveTeamFlag } from '../../../features/executive/types';
import { isAtRisk, formatPeriod } from '../../../features/executive/compose';
import { fmtSigned, kpiGapDelta, type Tone } from '../../../features/executive/format';

type Metric = ExecutiveSummary['meta']['driver_metric'];
const HEALTHY: GradeClass[] = ['A', 'B'];

export function driverImpact(driver: ExecutiveDriver, side: 'negative' | 'positive', metric: Metric): number | null {
  if (side === 'negative') return metric === 'weighted_gap' ? driver.weighted_gap_points ?? null : driver.impact_points;
  return driver.impact_change_points ?? driver.impact_points;
}

export function useElementWidth<T extends HTMLElement>(fallback: number) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver((entries) => {
      const next = Math.round(entries[0]?.contentRect.width ?? 0);
      if (next > 0) setWidth(next);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

export function heroHeadline(summary: ExecutiveSummary): string {
  const { hero, period, scope } = summary;
  if (hero.story?.headline) return hero.story.headline;
  const when = formatPeriod(period.effective);
  const subject = scope.view === 'corporate' ? `${when} company performance` : `${hero.label} in ${when}`;
  if (hero.gap === null) return `${subject}: no score yet.`;
  const position = Math.abs(hero.gap) < 0.05 ? 'is on target' : `is ${Math.abs(hero.gap).toFixed(1)}% ${hero.gap < 0 ? 'below' : 'above'} target`;
  if (scope.view !== 'corporate' && hero.change !== null && period.previous && Math.abs(hero.change) >= 0.05) {
    const vs = `${Math.abs(hero.change).toFixed(1)}% vs ${period.previous.month.slice(0, 3)}`;
    if (scope.view === 'managerial') return `${hero.label} ${position} and ${hero.change < 0 ? 'slipped' : 'improved'} ${vs}.`;
    const connector = (hero.gap < 0) === (hero.change < 0) ? 'and' : 'but';
    return `${hero.label} ${position} ${connector} ${hero.change < 0 ? 'down' : 'up'} ${vs}.`;
  }
  return `${subject} ${position}.`;
}

export function heroNarrative(summary: ExecutiveSummary): string | null {
  const story = summary.hero.story;
  const parts: string[] = [];
  const drag = story?.biggest_drag;
  if (drag?.function && summary.scope.view === 'corporate') {
    parts.push(drag.kpi_label
      ? `${drag.function} is the biggest drag — start with ${drag.kpi_label}${drag.team ? ` in ${drag.team}` : ''}.`
      : `${drag.function} is the biggest drag.`);
  } else if (drag?.kpi_label) {
    parts.push(`Biggest drag: ${drag.kpi_label}${drag.team && summary.scope.view !== 'managerial' ? ` in ${drag.team}` : ''}.`);
  }
  const comparison = summary.hero.comparison;
  if (summary.scope.view !== 'corporate' && comparison?.score != null && comparison.difference != null) {
    parts.unshift(Math.abs(comparison.difference) < 0.05
      ? `In line with the ${comparison.label}.`
      : `${Math.abs(comparison.difference).toFixed(1)}% ${comparison.difference > 0 ? 'above' : 'below'} the ${comparison.label}.`);
  }
  // Function view without driver analysis: name the leading and the lagging team.
  if (summary.scope.view === 'function' && !drag?.kpi_label) {
    const ranked = summary.teams.filter((team) => team.score !== null).sort((l, r) => (r.score ?? 0) - (l.score ?? 0));
    const leader = ranked[0];
    const laggard = ranked.length > 1 ? ranked[ranked.length - 1] : null;
    if (leader) {
      parts.push(laggard
        ? `${leader.team} leads at ${(leader.score ?? 0).toFixed(1)}%; ${laggard.team}${laggard.flag_detail ? ` (${laggard.flag_detail.kpi_label})` : ''} is holding the function back.`
        : `${leader.team} is at ${(leader.score ?? 0).toFixed(1)}%.`);
    }
  }
  if (story?.most_improved && story.most_improved.change > 0 && summary.scope.view === 'corporate') {
    parts.push(`${story.most_improved.function} is the most improved function (${fmtSigned(story.most_improved.change)}).`);
  }
  return parts.length ? parts.join(' ') : null;
}

export const FUNCTION_STYLE: Record<ExecutiveFunction, { icon: LucideIcon; bg: string; color: string }> = {
  'Call Center': { icon: Users, bg: 'var(--exec-function-call-center)', color: 'var(--insights-accent)' },
  RCM: { icon: FileText, bg: 'var(--exec-function-rcm)', color: 'var(--exec-info-text)' },
  'Pre-Approvals': { icon: CheckCircle2, bg: 'var(--exec-function-pre-approvals)', color: 'var(--insights-positive)' },
  Marketing: { icon: BarChart3, bg: 'var(--exec-function-marketing)', color: 'var(--exec-comparison-line)' },
};

export function movementTone(grade: GradeClass, movement: number): 'good' | 'bad' | 'neutral' {
  if (!movement || grade === 'C') return 'neutral';
  const up = movement > 0;
  return HEALTHY.includes(grade) === up ? 'good' : 'bad';
}

export function gapTone(row: Pick<ExecutiveKpiRow, 'gap_value' | 'raw_gap' | 'kpi_direction'>): Tone {
  const gap = kpiGapDelta(row);
  if (gap === null) return 'neutral';
  return gap >= 0 ? 'good' : 'bad';
}

export const FLAG_LABEL: Record<ExecutiveTeamFlag, string> = {
  grade_e: 'Grade E',
  grade_d: 'Grade D',
  falling_2_months: 'Falling 2 mo',
  lowest_in_function: 'Lowest in function',
  kpi_worsening_2_months: 'KPI worsening 2 mo',
  below_function_avg: 'Below function avg',
};

export const FLAG_ORDER: ExecutiveTeamFlag[] = ['grade_e', 'grade_d', 'falling_2_months', 'lowest_in_function', 'kpi_worsening_2_months', 'below_function_avg'];

export function atRiskTeams(teams: ExecutiveTeam[], limit = 4) {
  return teams.filter(isAtRisk).sort((l, r) => (l.score ?? 0) - (r.score ?? 0)).slice(0, limit);
}

export function actionStatus(action: ExecutiveActionItem): { label: string; tone: 'danger' | 'warning' | 'info' | 'neutral'; icon?: LucideIcon } {
  if (action.follow_up_state === 'overdue') return { label: 'Overdue', tone: 'danger', icon: AlertTriangle };
  if (action.follow_up_state === 'due_this_week') return { label: 'Due this week', tone: 'warning', icon: Clock };
  if (action.status === 'In Progress') return { label: 'In progress', tone: 'info' };
  return { label: action.status || 'Open', tone: 'neutral' };
}
