import { ArrowUpRight, ClipboardCheck } from 'lucide-react';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import type { AgentRecord } from '../../types';
import { egyptRcmTeamLabel, egyptRcmTeamValue, isHossamRecord, isRcmGroupTeam, sameEgyptRcmTeam } from '../../types';
import { isPreApprovalsSubTeam } from '../../features/executive/functions';

interface RcmEgyptTeamSummaryProps {
  rows: TeamAgentRow[];
  onTeamSelect: (team: string) => void;
  allAgents?: AgentRecord[];
  teamScores?: Partial<Record<string, number | null>>;
}

const TONES = [
  {
    tone: 'bg-violet-500/10 text-violet-600 dark:bg-violet-400/15 dark:text-violet-300',
    accent: 'bg-violet-500',
    glow: 'hover:border-violet-300/80 hover:shadow-[0_0_28px_rgba(139,92,246,0.24)] dark:hover:border-violet-400/60',
  },
  {
    tone: 'bg-blue-500/10 text-blue-600 dark:bg-blue-400/15 dark:text-blue-300',
    accent: 'bg-blue-500',
    glow: 'hover:border-blue-300/80 hover:shadow-[0_0_28px_rgba(59,130,246,0.24)] dark:hover:border-blue-400/60',
  },
  {
    tone: 'bg-emerald-500/10 text-emerald-600 dark:bg-emerald-400/15 dark:text-emerald-300',
    accent: 'bg-emerald-500',
    glow: 'hover:border-emerald-300/80 hover:shadow-[0_0_28px_rgba(16,185,129,0.24)] dark:hover:border-emerald-400/60',
  },
  {
    tone: 'bg-amber-500/10 text-amber-600 dark:bg-amber-400/15 dark:text-amber-300',
    accent: 'bg-amber-500',
    glow: 'hover:border-amber-300/80 hover:shadow-[0_0_28px_rgba(245,158,11,0.24)] dark:hover:border-amber-400/60',
  },
];

const RcmEgyptTeamSummary = ({ rows, onTeamSelect, allAgents, teamScores }: RcmEgyptTeamSummaryProps) => {
  const grouped = new Map<string, TeamAgentRow[]>();
  rows.forEach((row) => {
    if (!isRcmGroupTeam(row.raw.identity.team, 'offshore_egy', row.raw.region ?? row.raw.identity.region)) return;
    const stored = egyptRcmTeamValue(row.raw.identity.team || row.team);
    if (!stored || stored.toLowerCase() === 'rcm') return;
    grouped.set(stored, [...(grouped.get(stored) ?? []), row]);
  });
  const teams = [...grouped.entries()].sort(([left], [right]) => egyptRcmTeamLabel(left).localeCompare(egyptRcmTeamLabel(right)));

  return (
    <section className="glass-panel rounded-xl p-4 shadow-sm sm:p-6" aria-labelledby="rcm-egypt-team-summary">
      <div className="mb-4">
        <div className="flex items-center gap-2">
          <ClipboardCheck size={20} className="text-blue-600" />
          <h3 id="rcm-egypt-team-summary" className="heading-3">Egypt RCM Teams</h3>
        </div>
        <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">
          Egypt RCM teams keep their own KPI definitions and scorecards.
        </p>
      </div>
      {teams.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
          {teams.map(([stored, teamRows], index) => {
            const label = egyptRcmTeamLabel(stored);
            const isPreApprovals = stored === 'Pre-Approvals IP' || stored === 'Pre-Approvals IP Offshore' || isPreApprovalsSubTeam(stored);

            let score: number | null = teamScores?.[stored] ?? null;
            if (score === null && isPreApprovals) {
              const hossamRow = teamRows.find(isHossamRecord);
              if (hossamRow && Number.isFinite(hossamRow.score)) {
                score = hossamRow.score;
              } else if (allAgents && allAgents.length > 0) {
                const hossamAgent = allAgents.find((a) => isHossamRecord(a) && (sameEgyptRcmTeam(a.identity.team, stored) || isPreApprovalsSubTeam(a.identity.team)));
                if (hossamAgent) {
                  const s = Number(hossamAgent.evaluation?.score ?? hossamAgent.score);
                  if (Number.isFinite(s)) score = s;
                }
              }
            }

            if (score === null) {
              score = teamRows.length > 0
                ? teamRows.reduce((sum, row) => sum + row.score, 0) / teamRows.length
                : 0;
            }

            const tone = TONES[index % TONES.length];
            return (
              <button
                key={stored}
                type="button"
                onClick={() => onTeamSelect(stored)}
                aria-label={`Open ${label} team`}
                className={`group relative overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4 text-left transition-all duration-200 hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 ${tone.glow}`}
              >
                <span className={`pointer-events-none absolute -right-10 -top-10 h-28 w-28 rounded-full opacity-10 blur-2xl transition-opacity duration-200 group-hover:opacity-30 ${tone.accent}`} />
                <div className="flex items-center gap-3">
                  <span className={`flex h-10 w-10 items-center justify-center rounded-xl ${tone.tone}`}>
                    <ClipboardCheck size={19} />
                  </span>
                  <div>
                    <h4 className="text-sm font-extrabold text-[var(--text-primary)]">{label}</h4>
                    <p className="text-xs font-semibold text-[var(--text-muted)]">{teamRows.length} employees</p>
                  </div>
                </div>
                <div className="mt-4 flex items-end justify-between gap-3">
                  <div>
                    <div className="text-2xl font-extrabold text-[var(--text-primary)]">{score.toFixed(1)}%</div>
                    <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">Team score</p>
                  </div>
                  <span className="flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border-light)] text-[var(--text-muted)] transition-all duration-200 group-hover:border-current group-hover:text-[var(--text-primary)]" aria-hidden="true">
                    <ArrowUpRight size={16} />
                  </span>
                </div>
              </button>
            );
          })}
        </div>
      ) : (
        <p className="rounded-xl border border-dashed border-[var(--border-light)] px-4 py-6 text-sm font-semibold text-[var(--text-secondary)]">
          No Egypt RCM teams have data for the selected filters.
        </p>
      )}
    </section>
  );
};

export default RcmEgyptTeamSummary;
