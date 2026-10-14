import { AlertTriangle } from 'lucide-react';
import type { InsightExecutiveStory, InsightItem, InsightKpiDiagnosisRow } from '../../../features/insights/types';

/** One compact row: score and change, KPIs below target, and critical alerts only when there are any. */
export default function InsightsSummaryStrip({
  story,
  rows,
  criticalInsights,
  onOpenInsight,
}: {
  story: InsightExecutiveStory | null | undefined;
  rows: InsightKpiDiagnosisRow[];
  criticalInsights: InsightItem[];
  onOpenInsight: (insight: InsightItem) => void;
}) {
  const score = story?.current_score ?? null;
  const change = story?.score_change ?? null;
  const scored = rows.filter((row) => row.status !== null);
  const below = scored.filter((row) => row.status !== 'on_track').length;
  const first = criticalInsights[0];

  return (
    <section aria-label="Summary" className="flex flex-wrap items-center gap-x-[24px] gap-y-[10px] rounded-[12px] border border-[var(--insights-card-border)] bg-[var(--bg-surface)] px-[20px] py-[14px]">
      <div className="flex items-baseline gap-[10px]">
        <span className="text-[12px] font-semibold text-[var(--text-muted)]">Team score</span>
        <strong className="text-[24px] font-bold tabular-nums text-[var(--insights-heading)]">
          {score === null ? 'N/A' : `${score.toFixed(1)}%`}
        </strong>
        {change === null ? (
          <span className="text-[13px] text-[var(--text-muted)]">No previous month</span>
        ) : (
          <span className={`text-[13px] font-semibold tabular-nums ${change < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
            {change > 0 ? '+' : change < 0 ? '−' : ''}{Math.abs(change).toFixed(1)} pts vs previous month
          </span>
        )}
      </div>
      <p className="text-[13px] text-[var(--text-secondary)]">
        <strong className="font-semibold tabular-nums text-[var(--text-primary)]">{below}</strong> of {scored.length} KPIs below target
      </p>
      {criticalInsights.length > 0 && first && (
        <button
          type="button"
          onClick={() => onOpenInsight(first)}
          className="inline-flex items-center gap-[6px] rounded-full border border-rose-500/25 bg-rose-500/10 px-[10px] py-[4px] text-[12px] font-semibold text-rose-700 hover:border-rose-500/40 dark:text-rose-300"
        >
          <AlertTriangle size={13} aria-hidden="true" />
          {criticalInsights.length} critical {criticalInsights.length === 1 ? 'alert' : 'alerts'}: {first.title}
        </button>
      )}
      {story?.basis_context?.message && (
        <p className="w-full text-[12px] text-[var(--text-muted)]">{story.basis_context.message}</p>
      )}
    </section>
  );
}
