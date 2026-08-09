import { Activity, ArrowUpRight, Headphones, PhoneOutgoing } from 'lucide-react';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import { CALL_CENTER_CHANNEL_LABELS, callCenterChannelForTeam, type CallCenterChannelFilter } from '../../types';

interface CallCenterChannelSummaryProps {
  rows: TeamAgentRow[];
  onChannelSelect: (channel: Exclude<CallCenterChannelFilter, 'all'>) => void;
}

const CHANNELS: Exclude<CallCenterChannelFilter, 'all'>[] = ['inbound', 'outbound'];

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

const CallCenterChannelSummary = ({ rows, onChannelSelect }: CallCenterChannelSummaryProps) => (
  <section className="glass-panel rounded-xl p-4 shadow-sm sm:p-6" aria-labelledby="call-center-channel-summary">
    <div className="mb-4">
      <h3 id="call-center-channel-summary" className="heading-3">Channel Summary</h3>
      <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">
        Inbound and Outbound use separate KPI definitions and are not pooled into one score.
      </p>
    </div>
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {CHANNELS.map((channel) => {
        const channelRows = rows.filter((row) => callCenterChannelForTeam(row.raw.identity.team) === channel);
        const average = channelRows.length > 0
          ? channelRows.reduce((sum, row) => sum + row.score, 0) / channelRows.length
          : 0;
        const Icon = CHANNEL_META[channel].icon;
        return (
          <button
            key={channel}
            type="button"
            onClick={() => onChannelSelect(channel)}
            aria-label={`Open ${CALL_CENTER_CHANNEL_LABELS[channel]} channel`}
            className={`group relative overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4 text-left transition-all duration-200 hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 ${CHANNEL_META[channel].glow}`}
          >
            <span className={`pointer-events-none absolute -right-10 -top-10 h-28 w-28 rounded-full opacity-10 blur-2xl transition-opacity duration-200 group-hover:opacity-30 ${CHANNEL_META[channel].accent}`} />
            <div className="flex items-center gap-3">
              <span className={`flex h-10 w-10 items-center justify-center rounded-xl ${CHANNEL_META[channel].tone}`}>
                <Icon size={19} />
              </span>
              <div>
                <h4 className="text-sm font-extrabold text-[var(--text-primary)]">{CALL_CENTER_CHANNEL_LABELS[channel]}</h4>
                <p className="text-xs font-semibold text-[var(--text-muted)]">{channelRows.length} employees</p>
              </div>
            </div>
            <div className="mt-4 flex items-end justify-between gap-3">
              <div>
                <div className="text-2xl font-extrabold text-[var(--text-primary)]">
                  {channelRows.length > 0 ? `${average.toFixed(1)}%` : 'No data'}
                </div>
                <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">Average employee score</p>
              </div>
              <span className="flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border-light)] text-[var(--text-muted)] transition-all duration-200 group-hover:border-current group-hover:text-[var(--text-primary)]" aria-hidden="true">
                <ArrowUpRight size={16} />
              </span>
            </div>
          </button>
        );
      })}
    </div>
  </section>
);

export default CallCenterChannelSummary;
