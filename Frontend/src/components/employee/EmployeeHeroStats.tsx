/**
 * Employee Hero Stats Bar
 *
 * Horizontal at-a-glance summary shown at the top of the employee profile.
 * Gives managers an instant "health check" for any employee: grade, score,
 * rank, stability, and archetype.
 */
import { TrendingUp, TrendingDown, Minus, Trophy, Activity, Sparkles } from 'lucide-react';
import { GRADE_PALETTE, type GradeClass } from '../../constants/grades';
import type { StabilityCategory, PerformanceArchetype } from '../../services/employeeAnalytics';

export interface EmployeeHeroStatsProps {
  grade: GradeClass;
  score: number;
  /** Score from the previous period, used to derive trend direction. */
  previousScore?: number | null;
  /** 1-based rank within the current team & month. */
  rank: number;
  /** Total number of employees in the team that month. */
  totalEmployees: number;
  /** Percentile (0-100) within the team. */
  percentile: number;
  stability: StabilityCategory;
  archetype: PerformanceArchetype;
}

const STABILITY_META: Record<StabilityCategory, { color: string; icon: typeof Activity }> = {
  Stable: { color: 'text-blue-600 dark:text-blue-400', icon: Minus },
  Improving: { color: 'text-emerald-600 dark:text-emerald-400', icon: TrendingUp },
  Volatile: { color: 'text-amber-600 dark:text-amber-400', icon: Activity },
  Declining: { color: 'text-rose-600 dark:text-rose-400', icon: TrendingDown },
};

export function EmployeeHeroStats({
  grade,
  score,
  previousScore,
  rank,
  totalEmployees,
  percentile,
  stability,
  archetype,
}: EmployeeHeroStatsProps) {
  const palette = GRADE_PALETTE[grade];
  const trend =
    previousScore != null && previousScore !== 0
      ? score - previousScore
      : null;

  const StabilityIcon = STABILITY_META[stability].icon;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {/* Grade */}
      <div
        className="flex items-center gap-3 rounded-2xl border p-4"
        style={{
          borderColor: palette.border,
          backgroundColor: palette.background,
        }}
      >
        <span
          className="grid h-11 w-11 shrink-0 place-items-center rounded-xl text-lg font-black"
          style={{ color: palette.text, backgroundColor: `${palette.text}15` }}
        >
          {grade}
        </span>
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-faint)]">
            Grade
          </p>
          <p
            className="truncate text-sm font-extrabold"
            style={{ color: palette.text }}
          >
            {palette.label}
          </p>
        </div>
      </div>

      {/* Score + Trend */}
      <div className="flex items-center gap-3 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400">
          {trend !== null ? (
            trend >= 0 ? <TrendingUp size={20} /> : <TrendingDown size={20} />
          ) : (
            <Minus size={20} />
          )}
        </span>
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-faint)]">
            Score
          </p>
          <p className="text-sm font-extrabold text-[var(--text-primary)]">
            {score.toFixed(1)}%
            {trend !== null && (
              <span
                className={`ml-1.5 text-xs font-bold ${trend >= 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}
              >
                {trend >= 0 ? '↑' : '↓'} {Math.abs(trend).toFixed(1)}
              </span>
            )}
          </p>
        </div>
      </div>

      {/* Rank */}
      <div className="flex items-center gap-3 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-amber-500/10 text-amber-600 dark:text-amber-400">
          <Trophy size={20} />
        </span>
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-faint)]">
            Rank
          </p>
          <p className="text-sm font-extrabold text-[var(--text-primary)]">
            {rank > 0 ? `${rank} of ${totalEmployees}` : 'N/A'}
            <span className="ml-1.5 text-xs font-bold text-[var(--text-muted)]">
              Top {100 - percentile}%
            </span>
          </p>
        </div>
      </div>

      {/* Stability */}
      <div className="flex items-center gap-3 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4">
        <span className={`grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-[var(--bg-sunken)] ${STABILITY_META[stability].color}`}>
          <StabilityIcon size={20} />
        </span>
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-faint)]">
            Stability
          </p>
          <p className={`text-sm font-extrabold ${STABILITY_META[stability].color}`}>
            {stability}
          </p>
        </div>
      </div>

      {/* Archetype */}
      <div className="col-span-2 flex items-center gap-3 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4 sm:col-span-1 lg:col-span-1">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl bg-violet-500/10 text-violet-600 dark:text-violet-400">
          <Sparkles size={20} />
        </span>
        <div className="min-w-0">
          <p className="text-[11px] font-bold uppercase tracking-wide text-[var(--text-faint)]">
            Archetype
          </p>
          <p className="truncate text-sm font-extrabold text-violet-600 dark:text-violet-400">
            {archetype}
          </p>
        </div>
      </div>
    </div>
  );
}
