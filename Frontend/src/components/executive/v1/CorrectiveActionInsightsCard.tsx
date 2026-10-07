import { useId, useState } from 'react';
import {
  Activity, Award, BookOpenCheck, CalendarDays, ChartNoAxesCombined,
  ClipboardCheck, ClipboardList, Clock3, Eye, FileCheck2, Headset, Megaphone,
  MessageSquareText, Phone, Pill, Send, ShieldAlert, ShieldCheck,
  TriangleAlert, UserCheck, Users, type LucideIcon,
} from 'lucide-react';
import { actionAnalyticsStats } from '../../../features/executive/actionAnalytics';
import type { ExecutiveCorrectiveActions, ExecutivePeriod } from '../../../features/executive/types';
import { ExecCard, ExecCardHeader, Footnote, SoftEmpty } from './ExecPrimitives';

type Accent = 'blue' | 'violet' | 'amber' | 'green' | 'rose' | 'teal';

const ACCENTS: Record<Accent, { icon: string; surface: string }> = {
  blue: { icon: 'text-sky-700 dark:text-sky-300', surface: 'bg-sky-100 dark:bg-sky-900/40' },
  violet: { icon: 'text-violet-700 dark:text-violet-300', surface: 'bg-violet-100 dark:bg-violet-900/40' },
  amber: { icon: 'text-amber-700 dark:text-amber-300', surface: 'bg-amber-100 dark:bg-amber-900/40' },
  green: { icon: 'text-emerald-700 dark:text-emerald-300', surface: 'bg-emerald-100 dark:bg-emerald-900/40' },
  rose: { icon: 'text-rose-700 dark:text-rose-300', surface: 'bg-rose-100 dark:bg-rose-900/40' },
  teal: { icon: 'text-teal-700 dark:text-teal-300', surface: 'bg-teal-100 dark:bg-teal-900/40' },
};

const ACTION_VISUALS: Record<string, { icon: LucideIcon; accent: Accent }> = {
  training: { icon: BookOpenCheck, accent: 'blue' },
  reward: { icon: Award, accent: 'green' },
  pip: { icon: TriangleAlert, accent: 'rose' },
  monitor: { icon: Eye, accent: 'amber' },
  coaching: { icon: MessageSquareText, accent: 'violet' },
};

function teamIcon(label: string): LucideIcon {
  const team = label.toLowerCase();
  if (/inbound|call center|csr|customer service/.test(team)) return Headset;
  if (/outbound|sales/.test(team)) return Phone;
  if (/pre.?approv|pharmacy/.test(team)) return team.includes('pharmacy') ? Pill : ShieldCheck;
  if (/coding|rcm|submission/.test(team)) return FileCheck2;
  if (/marketing|content/.test(team)) return Megaphone;
  return Users;
}

function kpiIcon(label: string): LucideIcon {
  const kpi = label.toLowerCase();
  if (/aht|handle time|turnaround|waiting time/.test(kpi)) return Clock3;
  if (/booking|attendance|attended/.test(kpi)) return CalendarDays;
  if (/quality|reject|denial|error|compliance/.test(kpi)) return ShieldAlert;
  if (/submission|reachability/.test(kpi)) return Send;
  if (/prescription|pharmacy/.test(kpi)) return Pill;
  if (/queries|response rate|activity/.test(kpi)) return Activity;
  return ChartNoAxesCombined;
}

function actionIcon(label: string): LucideIcon {
  return ACTION_VISUALS[label.toLowerCase()]?.icon ?? ClipboardList;
}

function accentForAction(label: string): Accent {
  return ACTION_VISUALS[label.toLowerCase()]?.accent ?? 'blue';
}

function RankedActions({ title, rows, total, empty, testId }: {
  title: string; rows: Array<{ label: string; count: number }>; total: number; empty: string; testId: string;
}) {
  return (
    <section aria-label={title} className="min-w-0">
      <h3 className="mb-[14px] flex items-center gap-[7px] text-[12px] font-semibold text-[var(--insights-heading)]">
        <span aria-hidden="true" className="flex size-[24px] items-center justify-center rounded-[7px] bg-[var(--insights-accent-soft)] text-[var(--insights-accent-text)]">
          {testId === 'action-type-rank' ? <ClipboardCheck className="size-[14px]" /> : testId === 'action-team-rank' ? <Users className="size-[14px]" /> : <Activity className="size-[14px]" />}
        </span>
        {title}
      </h3>
      {rows.length ? <ol className="flex flex-col gap-[13px]">
        {rows.map((row, index) => {
          const Icon = testId === 'action-type-rank' ? actionIcon(row.label) : testId === 'action-team-rank' ? teamIcon(row.label) : kpiIcon(row.label);
          const accent: Accent = testId === 'action-type-rank' ? accentForAction(row.label) : testId === 'action-team-rank' ? 'teal' : 'blue';
          return (
            <li key={row.label} className="flex items-start gap-[9px]" data-testid={testId}>
              <span aria-hidden="true" className="flex size-[21px] shrink-0 items-center justify-center rounded-full bg-[var(--bg-sunken)] text-[10px] font-bold text-[var(--text-secondary)]">{index + 1}</span>
              <span aria-hidden="true" data-testid="ranked-row-icon" data-icon-for={row.label} className={`flex size-[28px] shrink-0 items-center justify-center rounded-[8px] ${ACCENTS[accent].surface} ${ACCENTS[accent].icon}`}>
                <Icon className="size-[15px]" strokeWidth={1.8} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="mb-[7px] flex items-start justify-between gap-[8px] text-[12px]">
                  <span className="font-medium text-[var(--text-primary)]">{row.label}</span>
                  <span className="shrink-0 rounded-full bg-[var(--bg-sunken)] px-[7px] py-[2px] text-[10px] font-semibold tabular-nums text-[var(--text-secondary)]">{row.count} {row.count === 1 ? 'action' : 'actions'}</span>
                </div>
                <div aria-hidden="true" className="h-[5px] overflow-hidden rounded-full bg-[var(--bg-sunken)]">
                  <div className="h-full rounded-full bg-[var(--insights-accent)] transition-[width] duration-200 ease-out motion-reduce:transition-none" style={{ width: `${total ? row.count / total * 100 : 0}%` }} />
                </div>
              </div>
            </li>
          );
        })}
      </ol> : <p className="text-[12px] text-[var(--text-muted)]">{empty}</p>}
    </section>
  );
}

/** Read-only decision patterns for summary pages. Operational follow-up stays in its own workspace. */
export default function CorrectiveActionInsightsCard({ data, effective, scopeLabel }: {
  data: ExecutiveCorrectiveActions | null; effective: ExecutivePeriod | null; scopeLabel: string;
}) {
  const titleId = useId();
  const selectId = useId();
  const [selectedTeam, setSelectedTeam] = useState('');
  const actions = data?.analytics?.actions ?? [];
  const teams = [...new Set(actions.map((action) => action.team).filter((team): team is string => Boolean(team)))].sort();
  const effectiveTeam = teams.includes(selectedTeam) ? selectedTeam : '';
  const visible = effectiveTeam ? actions.filter((action) => action.team === effectiveTeam) : actions;
  const stats = actionAnalyticsStats(visible);
  const period = effective ? `${effective.month} ${effective.year}` : 'Selected period';
  const metricCards: Array<{ label: string; count: number; icon: LucideIcon; accent: Accent }> = [
    { label: 'Actions this month', count: stats.total, icon: ClipboardList, accent: 'blue' },
    { label: 'Employees actioned', count: stats.employees, icon: UserCheck, accent: 'green' },
    { label: 'Teams with actions', count: stats.teams.filter((team) => team.label !== 'Unassigned team').length, icon: Users, accent: 'violet' },
  ];
  return (
    <ExecCard aria-labelledby={titleId} data-testid="corrective-action-insights">
      <ExecCardHeader titleId={titleId} icon={ShieldCheck} iconBg="var(--exec-info-bg)" iconColor="var(--exec-info-text)"
        title="Corrective actions" subtitle={`${scopeLabel} · ${period} · Decision patterns`} />
      {!data?.analytics ? <SoftEmpty>Action analysis isn't available for this view yet.</SoftEmpty> : <>
        <div className="grid gap-[10px] sm:grid-cols-3">
          {metricCards.map(({ label, count, icon: Icon, accent }) => (
            <div key={label} className="flex min-w-0 items-center gap-[10px] rounded-[10px] border border-[var(--exec-card-border)] bg-[var(--exec-tile-bg)] px-[12px] py-[10px]">
              <span aria-hidden="true" className={`flex size-[34px] shrink-0 items-center justify-center rounded-[9px] ${ACCENTS[accent].surface} ${ACCENTS[accent].icon}`}>
                <Icon className="size-[17px]" strokeWidth={1.8} />
              </span>
              <div className="min-w-0">
                <p className="text-[11px] leading-[1.3] text-[var(--text-muted)]">{label}</p>
                <p className="mt-[3px] text-[23px] font-bold leading-none tabular-nums text-[var(--insights-heading)]">{count}</p>
              </div>
            </div>
          ))}
        </div>
        <div className="flex flex-col gap-[6px] sm:items-start">
          <label htmlFor={selectId} className="flex items-center gap-[6px] text-[11px] font-semibold text-[var(--text-secondary)]">
            <Users aria-hidden="true" className="size-[13px] text-[var(--insights-accent-text)]" />Filter actions by team
          </label>
          <select id={selectId} value={effectiveTeam} onChange={(event) => setSelectedTeam(event.target.value)}
            className="min-h-[40px] w-full max-w-[320px] rounded-[8px] border border-[var(--border-medium)] bg-[var(--bg-surface)] px-[10px] py-[8px] text-[12px] text-[var(--text-primary)] transition-colors hover:border-[var(--insights-accent-border)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent-ring)]">
            <option value="">All teams in this scope</option>
            {teams.map((team) => <option key={team} value={team}>{team}</option>)}
          </select>
        </div>
        {stats.total ? <div className="grid gap-[24px] border-t border-[var(--insights-row-border)] pt-[16px] md:grid-cols-3">
          <RankedActions title="Most common action types" rows={stats.types} total={stats.total} empty="No action types recorded." testId="action-type-rank" />
          <RankedActions title="Teams with the most actions" rows={stats.teams} total={stats.total} empty="No teams recorded." testId="action-team-rank" />
          <RankedActions title={effectiveTeam ? `Most repeated KPIs · ${effectiveTeam}` : 'Most repeated KPIs'} rows={stats.kpis.slice(0, 5)} total={stats.total}
            empty="No KPI mentions or linked KPIs recorded for these actions." testId="action-kpi-rank" />
        </div> : <SoftEmpty>No corrective actions recorded for {period} in this scope.</SoftEmpty>}
        <Footnote>
          Counts include all action statuses for the selected performance month. Each KPI counts once per action; an action may mention more than one KPI.
          {stats.withoutKpi > 0 && ` ${stats.withoutKpi} ${stats.withoutKpi === 1 ? 'action has' : 'actions have'} no recorded KPI.`}
          {(data.analytics.unassigned_period ?? 0) > 0 && ` ${data.analytics.unassigned_period} undated actions are excluded from monthly analysis.`}
        </Footnote>
      </>}
    </ExecCard>
  );
}
