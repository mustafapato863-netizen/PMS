import { Building2, Globe2 } from 'lucide-react';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import type { RcmGroupFilter } from '../../types';
import { RCM_GROUP_LABELS, rcmGroupForTeam } from '../../types';

interface RcmGroupSummaryProps {
  rows: TeamAgentRow[];
  onGroupSelect: (group: RcmGroupFilter) => void;
}

const GROUPS: Array<{ key: Exclude<RcmGroupFilter, 'all'>; icon: typeof Building2; tone: string }> = [
  { key: 'offshore_egy', icon: Globe2, tone: 'from-blue-500 via-cyan-500 to-emerald-400' },
  { key: 'uae', icon: Building2, tone: 'from-violet-500 via-fuchsia-500 to-orange-400' },
];

export default function RcmGroupSummary({ rows, onGroupSelect }: RcmGroupSummaryProps) {
  const availableGroups = GROUPS.map((group) => ({
    ...group,
    groupRows: rows.filter((row) => rcmGroupForTeam(row.raw.identity.team, row.raw.region ?? row.raw.identity.region) === group.key),
  })).filter(({ groupRows }) => groupRows.length > 0);

  return (
    <section className="rounded-3xl border border-slate-200/80 bg-white/90 p-5 shadow-sm dark:border-slate-700 dark:bg-slate-900/80" aria-labelledby="rcm-group-summary-title">
      <div className="mb-5">
        <h2 id="rcm-group-summary-title" className="text-xl font-extrabold text-slate-900 dark:text-white">RCM Operating Groups</h2>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">Egypt offshore and UAE teams stay separated while sharing one RCM entry point.</p>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {availableGroups.length > 0 ? availableGroups.map(({ key, icon: Icon, tone, groupRows }) => {
          const average = groupRows.reduce((total, row) => total + row.score, 0) / groupRows.length;
          return (
            <button
              key={key}
              type="button"
              onClick={() => onGroupSelect(key)}
              className="group relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 dark:border-slate-700 dark:bg-slate-900"
              aria-label={`Open ${RCM_GROUP_LABELS[key]} group`}
            >
              <div className={`pointer-events-none absolute -right-10 -top-12 h-36 w-36 rounded-full bg-gradient-to-br ${tone} opacity-20 blur-2xl transition group-hover:opacity-40`} />
              <div className="relative flex items-start justify-between">
                <span className={`rounded-xl bg-gradient-to-br ${tone} p-3 text-white shadow-lg`}><Icon size={20} /></span>
                <span className="text-xs font-bold uppercase tracking-wider text-slate-400">Open group →</span>
              </div>
              <h3 className="relative mt-5 text-lg font-extrabold text-slate-900 dark:text-white">{RCM_GROUP_LABELS[key]}</h3>
              <div className="relative mt-1 flex items-end justify-between gap-4">
                <div>
                  <p className="text-3xl font-black text-slate-900 dark:text-white">{average.toFixed(1)}%</p>
                  <p className="text-sm text-slate-500">Average employee score</p>
                </div>
                <p className="text-sm font-bold text-slate-500">{groupRows.length} employees</p>
              </div>
            </button>
          );
        }) : (
          <p className="rounded-xl border border-dashed border-slate-200 px-4 py-6 text-sm font-semibold text-slate-500 dark:border-slate-700 dark:text-slate-400">
            No RCM groups have data for the selected filters.
          </p>
        )}
      </div>
    </section>
  );
}
