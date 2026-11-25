import { gradeGradientVar } from '../../../components/executive/v1/gradeGradient';

export interface KpiAchievementCellProps {
  label: string;
  actualFormatted: string;
  targetFormatted?: string;
  achievementPct: number | null;
  metTarget: boolean | null;
}

/**
 * Displays a KPI actual value pill with a smooth grade-gradient achievement bar
 * directly underneath showing achievement vs target (0–100%).
 */
export function KpiAchievementCell({
  label,
  actualFormatted,
  targetFormatted,
  achievementPct,
  metTarget,
}: KpiAchievementCellProps) {
  const isMeasured =
    actualFormatted !== '—' &&
    metTarget !== null &&
    achievementPct !== null &&
    Number.isFinite(achievementPct);

  const clampedPct = isMeasured ? Math.max(0, Math.min(100, achievementPct)) : 0;
  const roundedPct = isMeasured ? Math.round(achievementPct) : 0;
  const barFill = isMeasured
    ? metTarget
      ? 'var(--pms-grad-grade-a)'
      : gradeGradientVar(clampedPct)
    : undefined;

  const badgeTone = !isMeasured
    ? 'bg-slate-100 text-slate-500'
    : metTarget
      ? 'bg-emerald-50 text-emerald-700'
      : achievementPct < 75
        ? 'bg-rose-50 text-rose-700'
        : 'bg-amber-50 text-amber-800';

  const tooltip = isMeasured
    ? `${roundedPct}% of target (${actualFormatted}${targetFormatted ? ` vs ${targetFormatted}` : ''})`
    : `${label}: Not measured`;

  return (
    <div className="inline-flex min-w-[78px] flex-col items-end gap-1.5" title={tooltip}>
      <span
        className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-bold tabular-nums ${badgeTone}`}
      >
        {actualFormatted}
      </span>
      {isMeasured && (
        <div
          role="progressbar"
          aria-label={`${label} achievement vs target`}
          aria-valuenow={Math.round(clampedPct)}
          aria-valuemin={0}
          aria-valuemax={100}
          data-testid="kpi-ach-bar"
          className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--insights-track,rgba(148,163,184,0.22))]"
        >
          <div
            data-testid="kpi-ach-bar-fill"
            className="h-full rounded-full transition-[width] duration-300 ease-out motion-reduce:transition-none"
            style={{
              width: `${clampedPct}%`,
              minWidth: clampedPct > 0 ? '4px' : undefined,
              background: barFill,
            }}
          />
        </div>
      )}
    </div>
  );
}
