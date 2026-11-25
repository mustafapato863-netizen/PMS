import { gradeGradientVar } from '../../../components/executive/v1/gradeGradient';

export interface KpiAchievementCellProps {
  label: string;
  actualFormatted: string;
  targetFormatted?: string;
  /** Column header target; when the person's own target differs, both actual and personal target are shown. */
  columnTargetFormatted?: string;
  achievementPct: number | null;
  metTarget: boolean | null;
}

/**
 * Displays a KPI achievement % pill with a smooth grade-gradient achievement bar
 * directly underneath (0–100%), plus the underlying actual (and personal target
 * when it differs from the column target).
 */
export function KpiAchievementCell({
  label,
  actualFormatted,
  targetFormatted,
  columnTargetFormatted,
  achievementPct,
  metTarget,
}: KpiAchievementCellProps) {
  const isMeasured =
    actualFormatted !== '—' &&
    metTarget !== null &&
    achievementPct !== null &&
    Number.isFinite(achievementPct);

  const clampedPct = isMeasured ? Math.max(0, Math.min(100, achievementPct)) : 0;
  const achFormatted = isMeasured ? `${Math.max(0, achievementPct).toFixed(1)}%` : '—';
  const barFill = isMeasured
    ? metTarget
      ? 'var(--pms-grad-grade-a)'
      : gradeGradientVar(clampedPct)
    : undefined;

  const badgeTone = !isMeasured
    ? 'bg-slate-100 text-slate-500'
    : metTarget || achievementPct >= 90
      ? 'bg-emerald-50 text-emerald-700'
      : achievementPct < 70
        ? 'bg-rose-50 text-rose-700'
        : 'bg-amber-50 text-amber-800';

  const normalizePctText = (value: string): string => {
    const match = /^(-?\d+(?:\.\d+)?)%$/.exec(value.trim());
    return match ? `${Number(match[1]).toFixed(1)}%` : value.trim();
  };
  const hasDistinctPersonalTarget = Boolean(
    isMeasured &&
      targetFormatted &&
      targetFormatted !== '—' &&
      columnTargetFormatted &&
      normalizePctText(targetFormatted) !== normalizePctText(columnTargetFormatted),
  );
  const actualDuplicatesAch =
    !hasDistinctPersonalTarget &&
    normalizePctText(actualFormatted) === normalizePctText(achFormatted);
  const actualSubtext = !isMeasured || actualDuplicatesAch
    ? null
    : hasDistinctPersonalTarget
      ? `${actualFormatted} / ${targetFormatted}`
      : actualFormatted;

  const tooltip = isMeasured
    ? `${label}: ${achFormatted} achievement (Actual ${actualFormatted}${targetFormatted ? ` vs Target ${targetFormatted}` : ''})`
    : `${label}: Not measured`;

  return (
    <div className="inline-flex min-w-[84px] flex-col items-end gap-1" title={tooltip}>
      <span
        data-testid="kpi-ach-value"
        className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-bold tabular-nums ${badgeTone}`}
      >
        {achFormatted}
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
      {actualSubtext && (
        <span
          data-testid="kpi-actual-subtext"
          className="whitespace-nowrap text-xs font-medium text-slate-500 tabular-nums"
        >
          {actualSubtext}
        </span>
      )}
    </div>
  );
}
