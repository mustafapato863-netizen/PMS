import { lazy, Suspense, useMemo, useState } from 'react';
import { ChevronRight, Info, Minus, TrendingDown, TrendingUp } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { PerformanceLevelFilter, TeamSummary } from '../../types';

const GradeDistributionChart = lazy(() => import('./GradeDistributionChart'));

interface ExecutivePerformancePanelProps {
  classCounts: { A: number; B: number; C: number; D: number; E: number };
  teams: TeamSummary[];
  previousTeams: TeamSummary[];
  currentMonth: string;
  previousMonth: string | null;
  performanceLevel: PerformanceLevelFilter;
}

type DisplayMode = 'headcount' | 'percentage';

const RANK_CLASSES = [
  'bg-red-500 text-white',
  'bg-orange-500 text-white',
  'bg-amber-400 text-white',
  'bg-slate-500 text-white',
  'bg-slate-400 text-white',
];

const ExecutivePerformancePanel = ({
  classCounts,
  teams,
  previousTeams,
  currentMonth,
  previousMonth,
  performanceLevel,
}: ExecutivePerformancePanelProps) => {
  const navigate = useNavigate();
  const [displayMode, setDisplayMode] = useState<DisplayMode>('headcount');

  const previousByTeam = useMemo(
    () => new Map(previousTeams.map((team) => [team.teamId, team])),
    [previousTeams],
  );

  const riskTeams = useMemo(() => {
    return teams
      .map((team) => {
        const affectedEmployees = team.classD + team.classE;
        const percentage = team.agentCount > 0 ? (affectedEmployees / team.agentCount) * 100 : 0;
        const previousTeam = previousByTeam.get(team.teamId);
        const previousAffected = previousTeam ? previousTeam.classD + previousTeam.classE : 0;
        const previousPercentage = previousTeam && previousTeam.agentCount > 0
          ? (previousAffected / previousTeam.agentCount) * 100
          : null;

        return {
          ...team,
          affectedEmployees,
          percentage,
          trend: previousPercentage === null ? null : percentage - previousPercentage,
        };
      })
      .filter((team) => team.affectedEmployees > 0)
      .sort((a, b) => b.percentage - a.percentage || b.affectedEmployees - a.affectedEmployees)
      .slice(0, 5);
  }, [previousByTeam, teams]);

  const openTeam = (teamId: string) => {
    navigate(`/team/${teamId}?month=${encodeURIComponent(currentMonth)}&performance_level=${encodeURIComponent(performanceLevel)}`);
  };

  return (
    <div className="glass-panel flex h-full min-w-0 flex-col rounded-xl p-4 shadow-sm sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="heading-3">Grade Distribution</h3>
            <span title="Distribution uses each team's grading rules. Marketing grades come from its backend calculation; existing teams use their weighted dashboard scores.">
              <Info size={14} className="text-[var(--text-muted)]" />
            </span>
          </div>
          <p className="mt-0.5 text-[11px] font-semibold text-[var(--text-muted)]">All teams combined</p>
        </div>

        <div
          className="grid grid-cols-2 rounded-lg border border-[var(--border-light)] bg-[var(--bg-sunken)] p-1"
          aria-label="Grade distribution display mode"
        >
          {(['headcount', 'percentage'] as DisplayMode[]).map((mode) => (
            <button
              key={mode}
              type="button"
              aria-pressed={displayMode === mode}
              onClick={() => setDisplayMode(mode)}
              className={`rounded-md px-3 py-1.5 text-[11px] font-bold capitalize transition-all ${
                displayMode === mode
                  ? 'bg-[var(--bg-surface)] text-[var(--text-primary)] shadow-sm'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'
              }`}
            >
              {mode}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-2 min-w-0">
        <Suspense
          fallback={
            <div
              className="h-[220px] animate-pulse rounded-lg bg-[var(--bg-sunken)]"
              role="status"
              aria-label="Loading grade distribution"
              aria-busy="true"
            />
          }
        >
          <GradeDistributionChart classCounts={classCounts} displayMode={displayMode} />
        </Suspense>
      </div>

      <section className="mt-4 border-t border-[var(--border-light)] pt-4" aria-labelledby="risk-heading">
        <div className="mb-3">
          <div className="flex items-center gap-2">
            <h4 id="risk-heading" className="text-sm font-extrabold text-[var(--text-primary)]">Where Is the Risk?</h4>
            <span title="Teams ranked by their current percentage of Class D and E employees.">
              <Info size={13} className="text-[var(--text-muted)]" />
            </span>
          </div>
          <p className="text-[10px] font-semibold text-[var(--text-muted)]">Teams with the highest D + E concentration</p>
        </div>

        {riskTeams.length === 0 ? (
          <div className="rounded-xl border border-emerald-500/15 bg-emerald-500/5 px-4 py-5 text-center text-xs font-semibold text-emerald-700 dark:text-emerald-300">
            No employees are currently classified as D or E.
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-[var(--border-light)]">
            <div className="hidden grid-cols-[34px_minmax(130px,1.2fr)_minmax(150px,1fr)_100px_115px_20px] items-center gap-3 bg-[var(--bg-sunken)] px-3 py-2 text-[9px] font-bold uppercase tracking-wider text-[var(--text-muted)] md:grid">
              <span>Rank</span>
              <span>Team</span>
              <span>D + E %</span>
              <span>Affected</span>
              <span>{previousMonth ? `Trend vs ${previousMonth}` : 'Trend'}</span>
              <span />
            </div>

            <div className="divide-y divide-[var(--border-light)]">
              {riskTeams.map((team, index) => {
                const isWorsening = team.trend !== null && team.trend > 0.05;
                const isImproving = team.trend !== null && team.trend < -0.05;
                return (
                  <button
                    key={team.teamId}
                    type="button"
                    onClick={() => openTeam(team.teamId)}
                    className="grid w-full grid-cols-[28px_minmax(0,1fr)_20px] items-center gap-2 px-3 py-3 text-left transition-colors hover:bg-[var(--sidebar-active-bg)] focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500/40 md:grid-cols-[34px_minmax(130px,1.2fr)_minmax(150px,1fr)_100px_115px_20px] md:gap-3 md:py-2.5"
                    aria-label={`Open ${team.teamName} dashboard`}
                  >
                    <span className={`flex h-5 w-5 items-center justify-center rounded-full text-[10px] font-extrabold ${RANK_CLASSES[index] || RANK_CLASSES[RANK_CLASSES.length - 1]}`}>
                      {index + 1}
                    </span>

                    <div className="min-w-0">
                      <div className="truncate text-xs font-bold text-[var(--text-primary)]">{team.teamName}</div>
                      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] font-semibold text-[var(--text-muted)] md:hidden">
                        <span>{team.percentage.toFixed(1)}% D + E</span>
                        <span>{team.affectedEmployees} affected</span>
                        <span className={isWorsening ? 'text-red-600 dark:text-red-400' : isImproving ? 'text-emerald-600 dark:text-emerald-400' : ''}>
                          {team.trend === null ? 'No prior data' : `${team.trend > 0 ? '+' : ''}${team.trend.toFixed(1)}%`}
                        </span>
                      </div>
                    </div>

                    <div className="hidden items-center gap-2 md:flex">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[var(--bg-sunken)]">
                        <div
                          className="h-full rounded-full bg-gradient-to-r from-orange-400 to-red-500"
                          style={{ width: `${Math.min(team.percentage, 100)}%` }}
                        />
                      </div>
                      <span className="w-12 text-right text-xs font-extrabold text-red-600 dark:text-red-400">{team.percentage.toFixed(1)}%</span>
                    </div>

                    <span className="hidden text-xs font-bold text-[var(--text-secondary)] md:block">
                      {team.affectedEmployees} {team.affectedEmployees === 1 ? 'employee' : 'employees'}
                    </span>

                    <span
                      className={`hidden items-center gap-1 text-xs font-bold md:flex ${
                        isWorsening
                          ? 'text-red-600 dark:text-red-400'
                          : isImproving
                            ? 'text-emerald-600 dark:text-emerald-400'
                            : 'text-[var(--text-muted)]'
                      }`}
                      title={team.trend === null ? 'No previous-month team data' : 'Change in D + E percentage'}
                    >
                      {isWorsening ? <TrendingUp size={13} /> : isImproving ? <TrendingDown size={13} /> : <Minus size={13} />}
                      {team.trend === null ? 'No data' : `${Math.abs(team.trend).toFixed(1)}%`}
                    </span>

                    <ChevronRight size={15} className="text-[var(--text-muted)]" />
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </section>
    </div>
  );
};

export default ExecutivePerformancePanel;
