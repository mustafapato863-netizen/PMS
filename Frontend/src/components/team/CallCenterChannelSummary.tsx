import {
  Activity,
  ArrowRight,
  CheckCircle2,
  Headphones,
  PhoneOutgoing,
  Target,
  Users,
} from 'lucide-react';
import type { TeamKpiAnalysis } from '../../features/team/teamKpiAnalysis';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import { CALL_CENTER_CHANNEL_LABELS, callCenterChannelForTeam, type CallCenterChannelFilter } from '../../types';

type CallCenterChannel = Exclude<CallCenterChannelFilter, 'all'>;

interface ChannelKpiAnalysis {
  channel: CallCenterChannel;
  analyses: TeamKpiAnalysis[];
}

interface CallCenterChannelSummaryProps {
  rows: TeamAgentRow[];
  onChannelSelect: (channel: Exclude<CallCenterChannelFilter, 'all'>) => void;
  channelKpiAnalysis?: ChannelKpiAnalysis[];
}

const CHANNELS: CallCenterChannel[] = ['inbound', 'outbound'];

const CHANNEL_META: Record<Exclude<CallCenterChannelFilter, 'all'>, {
  icon: typeof Activity;
  tone: string;
  accent: string;
  glow: string;
}> = {
  inbound: {
    icon: Headphones,
    tone: 'bg-cyan-500/10 text-cyan-600 dark:bg-cyan-400/15 dark:text-cyan-300',
    accent: 'bg-cyan-500',
    glow: 'hover:border-cyan-300/80 hover:shadow-[0_0_28px_rgba(6,182,212,0.24)] dark:hover:border-cyan-400/60 dark:hover:shadow-[0_0_34px_rgba(34,211,238,0.25)]',
  },
  outbound: {
    icon: PhoneOutgoing,
    tone: 'bg-indigo-500/10 text-indigo-600 dark:bg-indigo-400/15 dark:text-indigo-300',
    accent: 'bg-indigo-500',
    glow: 'hover:border-indigo-300/80 hover:shadow-[0_0_28px_rgba(99,102,241,0.24)] dark:hover:border-indigo-400/60 dark:hover:shadow-[0_0_34px_rgba(129,140,248,0.25)]',
  },
};

type ChannelSnapshot = {
  channel: Exclude<CallCenterChannelFilter, 'all'>;
  count: number;
  score: number | null;
};

const getSignal = (score: number | null) => {
  if (score === null) return {
    label: 'No data',
    tone: 'border-[var(--border-light)] bg-[var(--bg-sunken)] text-[var(--text-muted)]',
  };
  if (score >= 90) return {
    label: 'Strong',
    tone: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300',
  };
  if (score >= 80) return {
    label: 'On track',
    tone: 'border-blue-500/20 bg-blue-500/10 text-blue-700 dark:text-blue-300',
  };
  return {
    label: 'Needs attention',
    tone: 'border-rose-500/20 bg-rose-500/10 text-rose-700 dark:text-rose-300',
  };
};

const formatKpiValue = (value: number, unit: TeamKpiAnalysis['unit']) => {
  if (unit === '%') return `${(value * 100).toFixed(1)}%`;
  if (unit === 'min') return `${value.toFixed(1)} min`;
  if (unit === 'currency') return `AED ${value.toFixed(1)}`;
  return value.toFixed(1);
};

const CallCenterChannelSummary = ({ rows, onChannelSelect, channelKpiAnalysis = [] }: CallCenterChannelSummaryProps) => {
  const snapshots: ChannelSnapshot[] = CHANNELS.map((channel) => {
    const channelRows = rows.filter((row) => callCenterChannelForTeam(row.raw.identity.team) === channel);
    return {
      channel,
      count: channelRows.length,
      score: channelRows.length > 0
        ? channelRows.reduce((sum, row) => sum + row.score, 0) / channelRows.length
        : null,
    };
  });

  const scoredSnapshots = snapshots.filter((snapshot): snapshot is ChannelSnapshot & { score: number } => snapshot.score !== null);
  const leadChannel = scoredSnapshots.length > 0
    ? scoredSnapshots.reduce((best, snapshot) => snapshot.score > best.score ? snapshot : best)
    : null;
  const focusChannel = scoredSnapshots.length > 0
    ? scoredSnapshots.reduce((lowest, snapshot) => snapshot.score < lowest.score ? snapshot : lowest)
    : null;
  const scoreSpread = leadChannel && focusChannel ? leadChannel.score - focusChannel.score : null;
  const totalEmployees = snapshots.reduce((sum, snapshot) => sum + snapshot.count, 0);
  const channelsAreClose = scoreSpread !== null && scoreSpread < 1;
  const overallScore = rows.length > 0
    ? rows.reduce((sum, row) => sum + row.score, 0) / rows.length
    : null;
  const impactingEmployees = overallScore === null
    ? []
    : rows
      .filter((row) => row.score < overallScore)
      .sort((left, right) => left.score - right.score)
      .slice(0, 3);
  const primaryDrag = channelKpiAnalysis
    .flatMap(({ channel, analyses }) => analyses.map((analysis) => ({ channel, analysis })))
    .filter(({ analysis }) => !analysis.targetMet)
    .sort((left, right) => (right.analysis.gapPoints ?? 0) - (left.analysis.gapPoints ?? 0))[0] ?? null;
  const overallSignal = getSignal(overallScore);

  const focusLabel = focusChannel ? CALL_CENTER_CHANNEL_LABELS[focusChannel.channel] : 'a channel';
  const focusSignal = focusChannel ? getSignal(focusChannel.score) : getSignal(null);
  const decisionDetail = primaryDrag
    ? `${CALL_CENTER_CHANNEL_LABELS[primaryDrag.channel]} · ${primaryDrag.analysis.label} is ${formatKpiValue(primaryDrag.analysis.actual, primaryDrag.analysis.unit)} against ${formatKpiValue(primaryDrag.analysis.target, primaryDrag.analysis.unit)}.`
    : focusChannel && leadChannel && focusChannel.channel !== leadChannel.channel
      ? `${focusLabel} trails ${CALL_CENTER_CHANNEL_LABELS[leadChannel.channel]} by ${scoreSpread?.toFixed(1)}%. Review its KPI board next.`
      : 'Inbound and Outbound remain separate by design. Open a channel to inspect its KPI board.';
  const actionChannel = primaryDrag?.channel ?? focusChannel?.channel;

  return (
    <section className="glass-panel rounded-xl p-4 shadow-sm sm:p-6" aria-labelledby="call-center-overview">
      <div className="flex flex-col gap-4 border-b border-[var(--border-light)] pb-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-blue-500/10 text-blue-600 dark:bg-blue-400/15 dark:text-blue-300">
            <Target size={19} />
          </span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[10px] font-extrabold uppercase tracking-[0.1em] text-blue-600 dark:text-blue-300">Decision overview</p>
              <span className="rounded-full border border-[var(--border-light)] bg-[var(--bg-sunken)] px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wide text-[var(--text-muted)]">No pooled KPI score</span>
            </div>
            <h3 id="call-center-overview" className="mt-1 heading-3">Call Center Overview</h3>
            <p className="mt-1 max-w-3xl text-xs font-medium leading-5 text-[var(--text-secondary)]">
              Compare channel health first, then open the channel that needs the next KPI-level review.
            </p>
          </div>
        </div>
        <div className="flex w-fit shrink-0 items-center gap-3 text-[10px] font-extrabold text-[var(--text-secondary)]">
          <span className="flex items-center gap-1.5"><Users size={13} className="text-blue-500" />{totalEmployees} employees</span>
          <span className="h-3 w-px bg-[var(--border-light)]" aria-hidden="true" />
          <span>2 channels</span>
        </div>
      </div>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <article className="rounded-2xl border border-blue-500/20 bg-blue-500/[0.045] p-4">
          <div className="flex items-center justify-between gap-3">
            <p className="text-[10px] font-extrabold uppercase tracking-[0.08em] text-blue-700 dark:text-blue-300">Department performance</p>
            <span className={`rounded-full border px-2 py-1 text-[9px] font-extrabold uppercase tracking-wide ${overallSignal.tone}`}>{overallSignal.label}</span>
          </div>
          <p className="mt-3 text-3xl font-extrabold tracking-tight text-[var(--text-primary)]">{overallScore === null ? '—' : `${overallScore.toFixed(1)}%`}</p>
          <p className="mt-1 text-[11px] font-medium leading-4 text-[var(--text-secondary)]">Overall employee score: average across {totalEmployees} active employees; channel KPI definitions stay separate.</p>
        </article>

        <article className={`rounded-2xl border p-4 ${primaryDrag ? 'border-amber-500/25 bg-amber-500/[0.06]' : 'border-emerald-500/20 bg-emerald-500/[0.05]'}`}>
          <p className={`text-[10px] font-extrabold uppercase tracking-[0.08em] ${primaryDrag ? 'text-amber-700 dark:text-amber-300' : 'text-emerald-700 dark:text-emerald-300'}`}>Measured KPI drag</p>
          <p className="mt-3 truncate text-base font-extrabold text-[var(--text-primary)]" title={primaryDrag ? `${CALL_CENTER_CHANNEL_LABELS[primaryDrag.channel]} · ${primaryDrag.analysis.label}` : undefined}>
            {primaryDrag ? `${CALL_CENTER_CHANNEL_LABELS[primaryDrag.channel]} · ${primaryDrag.analysis.label}` : 'No measured drag'}
          </p>
          <p className="mt-1 text-[11px] font-medium leading-4 text-[var(--text-secondary)]">
            {primaryDrag
              ? `Actual ${formatKpiValue(primaryDrag.analysis.actual, primaryDrag.analysis.unit)} / Target ${formatKpiValue(primaryDrag.analysis.target, primaryDrag.analysis.unit)}`
              : 'All available channel KPIs are at target or awaiting data.'}
          </p>
        </article>

        <article className="rounded-2xl border border-rose-500/20 bg-rose-500/[0.045] p-4">
          <p className="text-[10px] font-extrabold uppercase tracking-[0.08em] text-rose-700 dark:text-rose-300">Employees affecting average</p>
          <p className="mt-3 text-2xl font-extrabold tracking-tight text-[var(--text-primary)]">{impactingEmployees.length} priority employees</p>
          <p className="mt-1 text-[11px] font-medium leading-4 text-[var(--text-secondary)]">Lowest score gaps versus the department average; this is mathematical influence, not a root-cause claim.</p>
        </article>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.45fr)_minmax(280px,0.75fr)]">
        <div className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/35 p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Activity size={16} className="text-indigo-500" />
              <h4 className="text-sm font-extrabold text-[var(--text-primary)]">Channel comparison</h4>
            </div>
            <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">Average score</span>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {snapshots.map((snapshot) => {
              const meta = CHANNEL_META[snapshot.channel];
              const Icon = meta.icon;
              const signal = getSignal(snapshot.score);
              const isFocus = focusChannel?.channel === snapshot.channel && !channelsAreClose;
              return (
                <button
                  key={snapshot.channel}
                  type="button"
                  onClick={() => onChannelSelect(snapshot.channel)}
                  aria-label={`Open ${CALL_CENTER_CHANNEL_LABELS[snapshot.channel]} channel`}
                  className={`group relative overflow-hidden rounded-xl border bg-[var(--bg-surface)] p-4 text-left transition-all duration-200 hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 ${isFocus ? 'border-amber-400/60 shadow-[0_0_0_2px_rgba(245,158,11,0.08)]' : 'border-[var(--border-light)]'} ${meta.glow}`}
                >
                  <span className={`pointer-events-none absolute -right-10 -top-10 h-24 w-24 rounded-full opacity-10 blur-2xl transition-opacity duration-200 group-hover:opacity-30 ${meta.accent}`} />
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-2.5">
                      <span className={`flex h-9 w-9 items-center justify-center rounded-lg ${meta.tone}`}>
                        <Icon size={17} />
                      </span>
                      <div>
                        <h5 className="text-sm font-extrabold text-[var(--text-primary)]">{CALL_CENTER_CHANNEL_LABELS[snapshot.channel]}</h5>
                        <p className="mt-0.5 text-[11px] font-semibold text-[var(--text-muted)]">{snapshot.count} employees</p>
                      </div>
                    </div>
                    <span className={`rounded-full border px-2 py-1 text-[9px] font-extrabold uppercase tracking-wide ${signal.tone}`}>{signal.label}</span>
                  </div>
                  <div className="mt-4 flex items-end justify-between gap-3">
                    <div>
                      <p className="text-2xl font-extrabold tracking-tight text-[var(--text-primary)]">{snapshot.score === null ? 'No data' : `${snapshot.score.toFixed(1)}%`}</p>
                      <p className="mt-1 text-[11px] font-medium text-[var(--text-secondary)]">Average employee score</p>
                    </div>
                    <span className="flex h-8 w-8 items-center justify-center rounded-full border border-[var(--border-light)] text-[var(--text-muted)] transition-colors duration-200 group-hover:border-current group-hover:text-[var(--text-primary)]" aria-hidden="true">
                      <ArrowRight size={15} />
                    </span>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="mt-5 border-t border-[var(--border-light)] pt-4">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <h4 className="text-sm font-extrabold text-[var(--text-primary)]">Employees affecting the average</h4>
                <p className="mt-1 text-[11px] font-medium text-[var(--text-secondary)]">The largest negative score gaps in the current department view.</p>
              </div>
              <span className="text-[10px] font-extrabold uppercase tracking-[0.08em] text-[var(--text-muted)]">Priority review</span>
            </div>
            {impactingEmployees.length === 0 ? (
              <div className="mt-3 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.06] px-3 py-3 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                No employee is currently below the department average.
              </div>
            ) : (
              <div className="mt-3 grid gap-2 md:grid-cols-3">
                {impactingEmployees.map((row) => {
                  const employeeChannel = callCenterChannelForTeam(row.raw.identity.team);
                  const scoreGap = overallScore === null ? 0 : overallScore - row.score;
                  return (
                    <button
                      key={row.id}
                      type="button"
                      onClick={() => employeeChannel && onChannelSelect(employeeChannel)}
                      disabled={!employeeChannel}
                      className="rounded-xl border border-rose-500/15 bg-[var(--bg-surface)] p-3 text-left transition-colors hover:border-rose-300/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:cursor-default disabled:hover:border-rose-500/15"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="min-w-0 truncate text-xs font-extrabold text-[var(--text-primary)]" title={row.name}>{row.name}</span>
                        <span className="shrink-0 text-xs font-extrabold text-rose-600 dark:text-rose-300">{row.score.toFixed(1)}%</span>
                      </div>
                      <div className="mt-2 flex items-center justify-between gap-2 text-[10px] font-semibold text-[var(--text-muted)]">
                        <span>{employeeChannel ? CALL_CENTER_CHANNEL_LABELS[employeeChannel] : 'Call Center'}</span>
                        <span>−{scoreGap.toFixed(1)}% vs avg</span>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <aside className="flex flex-col justify-between rounded-2xl border border-blue-500/20 bg-blue-500/[0.045] p-4">
          <div>
            <div className="flex items-center gap-2">
              <CheckCircle2 size={16} className="text-blue-600 dark:text-blue-300" />
              <p className="text-[10px] font-extrabold uppercase tracking-[0.1em] text-blue-700 dark:text-blue-300">Next decision</p>
            </div>
            <h4 className="mt-3 text-lg font-extrabold text-[var(--text-primary)]">{primaryDrag ? 'Fix measured KPI drag' : `Review ${focusLabel}`}</h4>
            <p className="mt-1 text-xs font-medium leading-5 text-[var(--text-secondary)]">{decisionDetail}</p>
          </div>
          <div className="mt-5 grid grid-cols-2 gap-2">
            <div className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)]/80 p-3">
              <p className="text-[9px] font-extrabold uppercase tracking-wide text-[var(--text-muted)]">Channel gap</p>
              <p className="mt-1 text-base font-extrabold text-[var(--text-primary)]">{scoreSpread === null ? '—' : `${scoreSpread.toFixed(1)}%`}</p>
            </div>
            <div className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)]/80 p-3">
              <p className="text-[9px] font-extrabold uppercase tracking-wide text-[var(--text-muted)]">Signal</p>
              <p className="mt-1 truncate text-base font-extrabold text-[var(--text-primary)]">{focusSignal.label}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => actionChannel && onChannelSelect(actionChannel)}
            disabled={!actionChannel}
            className="mt-4 inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-extrabold text-white shadow-sm transition-colors duration-200 hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Open {actionChannel ? `${CALL_CENTER_CHANNEL_LABELS[actionChannel]} KPI board` : 'channel'}
            <ArrowRight size={15} />
          </button>
        </aside>
      </div>
    </section>
  );
};

export default CallCenterChannelSummary;
