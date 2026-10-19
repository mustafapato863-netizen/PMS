import { useEffect, useId, useRef, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  HelpCircle,
  Layers,
  Target,
  TrendingDown,
  TrendingUp,
  X,
} from 'lucide-react';
import type {
  InsightExecutiveStory,
  InsightItem,
  InsightKpiDiagnosisRow,
  InsightsWorkspace,
} from '../../../features/insights/types';
import { getGradeClassOrNull, GRADE_PALETTE } from '../../../constants/grades';

export interface InsightsSummaryStripProps {
  story: InsightExecutiveStory | null | undefined;
  rows: InsightKpiDiagnosisRow[];
  criticalInsights: InsightItem[];
  summary?: InsightsWorkspace['summary'];
  onOpenInsight: (insight: InsightItem) => void;
}

/**
 * High-Level Performance & Breakdown Summary for the Insights Workspace.
 *
 * Provides executive KPI cards (Team Score, Target Gap, Analyzed KPIs),
 * a visual KPI health distribution bar (On Track, At Risk, Critical),
 * and an interactive Quick Help popover in the header explaining metrics,
 * thresholds, and recommended actions.
 */
export default function InsightsSummaryStrip({
  story,
  rows,
  criticalInsights,
  summary,
  onOpenInsight,
}: InsightsSummaryStripProps) {
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const helpRef = useRef<HTMLDivElement>(null);
  const helpBtnRef = useRef<HTMLButtonElement>(null);
  const helpDialogId = useId();

  // Close Quick Help on Escape key or outside click
  useEffect(() => {
    if (!isHelpOpen) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsHelpOpen(false);
        helpBtnRef.current?.focus();
      }
    };
    const handleClickOutside = (event: MouseEvent) => {
      if (
        helpRef.current &&
        !helpRef.current.contains(event.target as Node) &&
        helpBtnRef.current &&
        !helpBtnRef.current.contains(event.target as Node)
      ) {
        setIsHelpOpen(false);
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isHelpOpen]);

  // High-level Performance Metrics
  const score = story?.current_score ?? null;
  const target = story?.target_score ?? 100;
  const change = story?.score_change ?? null;
  const gap = story?.gap_points ?? (score !== null ? Math.round((score - target) * 10) / 10 : null);
  const grade = getGradeClassOrNull(score);
  const gradePalette = grade ? GRADE_PALETTE[grade] : null;

  // Breakdown Calculations
  const scored = rows.filter((row) => row.status !== null);
  const totalScored = scored.length;
  const onTrackCount = scored.filter((row) => row.status === 'on_track').length;
  const atRiskCount = scored.filter((row) => row.status === 'at_risk').length;
  const criticalCount = scored.filter((row) => row.status === 'critical').length;
  const below = scored.filter((row) => row.status !== 'on_track').length;

  const onTrackPct = totalScored > 0 ? (onTrackCount / totalScored) * 100 : 0;
  const atRiskPct = totalScored > 0 ? (atRiskCount / totalScored) * 100 : 0;
  const criticalPct = totalScored > 0 ? (criticalCount / totalScored) * 100 : 0;

  const first = criticalInsights[0];

  return (
    <section
      aria-label="Summary"
      className="relative flex flex-col gap-4 rounded-2xl border border-[var(--insights-card-border)] bg-[var(--bg-surface)] p-5 shadow-sm transition-all sm:p-6"
    >
      {/* ── Section Header with Quick Help ── */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--insights-card-border)] pb-3">
        <div className="min-w-0">
          <h2 className="text-base font-bold text-[var(--insights-heading)] sm:text-lg">
            Performance & Breakdown Summary
          </h2>
          <p className="mt-0.5 text-xs text-[var(--text-muted)] sm:text-sm">
            High-level authorized performance indicators, target gap, and KPI health status
          </p>
        </div>

        {/* Quick Help Trigger */}
        <div className="relative">
          <button
            ref={helpBtnRef}
            type="button"
            onClick={() => setIsHelpOpen((prev) => !prev)}
            aria-expanded={isHelpOpen}
            aria-controls={isHelpOpen ? helpDialogId : undefined}
            aria-haspopup="dialog"
            aria-label="Quick help and metric guide"
            className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--insights-card-border)] bg-[var(--insights-chip-bg)] px-2.5 py-1.5 text-xs font-semibold text-[var(--text-secondary)] transition hover:border-[var(--insights-accent-border)] hover:text-[var(--insights-heading)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)]"
          >
            <HelpCircle size={14} className="text-[var(--insights-accent)]" aria-hidden="true" />
            <span>Quick Help</span>
          </button>

          {/* Quick Help Popover Dialog */}
          {isHelpOpen && (
            <div
              ref={helpRef}
              id={helpDialogId}
              role="dialog"
              aria-modal="true"
              aria-label="Quick help and metric guide"
              className="absolute right-0 top-full z-40 mt-2 w-[340px] rounded-xl border border-[var(--insights-card-border)] bg-[var(--bg-surface)] p-4 text-left shadow-xl sm:w-[380px]"
            >
              <div className="flex items-center justify-between border-b border-[var(--insights-card-border)] pb-2.5">
                <span className="flex items-center gap-1.5 text-sm font-bold text-[var(--insights-heading)]">
                  <HelpCircle size={16} className="text-[var(--insights-accent)]" />
                  Metric Guide & Quick Help
                </span>
                <button
                  type="button"
                  onClick={() => setIsHelpOpen(false)}
                  aria-label="Close guide"
                  className="rounded-md p-1 text-[var(--text-muted)] hover:bg-[var(--insights-chip-bg)] hover:text-[var(--text-primary)]"
                >
                  <X size={15} />
                </button>
              </div>

              <div className="mt-3 flex flex-col gap-3 text-xs leading-relaxed text-[var(--text-secondary)]">
                {/* 1. What is happening? */}
                <div>
                  <strong className="block font-bold text-[var(--insights-heading)]">
                    1. What is happening?
                  </strong>
                  <p className="mt-1">
                    <span className="font-semibold text-[var(--text-primary)]">Team Score</span> is the
                    canonical weighted roll-up of authorized KPI actuals against their targets for the
                    selected period and scope.
                  </p>
                  <div className="mt-1.5 flex flex-col gap-1 pl-1 text-[11px]">
                    <div className="flex items-center gap-1.5">
                      <span className="size-2 rounded-full bg-emerald-500" />
                      <span><strong>On Track (≥100%)</strong>: Meeting or beating benchmark</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="size-2 rounded-full bg-amber-500" />
                      <span><strong>At Risk (70%–99.9%)</strong>: Narrow margin, mild drag</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="size-2 rounded-full bg-rose-500" />
                      <span><strong>Critical (&lt;70%)</strong>: Major shortfall requiring intervention</span>
                    </div>
                  </div>
                </div>

                {/* 2. Why does it matter? */}
                <div>
                  <strong className="block font-bold text-[var(--insights-heading)]">
                    2. Why does it matter?
                  </strong>
                  <p className="mt-1">
                    KPIs carry assigned weights in the overall score. Underperforming high-weight metrics
                    or employee cohorts pull down the entire group average.
                  </p>
                </div>

                {/* 3. What action should you take? */}
                <div>
                  <strong className="block font-bold text-[var(--insights-heading)]">
                    3. What action should you take?
                  </strong>
                  <ul className="mt-1 list-disc pl-4 text-[11px] space-y-0.5">
                    <li>Inspect Critical and At-Risk rows in the <em>KPI diagnosis</em> table below.</li>
                    <li>Check <em>People to review</em> to see specific team members below target.</li>
                    <li>Create corrective follow-up actions directly from the <em>Actions</em> section.</li>
                  </ul>
                </div>
              </div>

              <div className="mt-3 border-t border-[var(--insights-card-border)] pt-2.5 text-right">
                <button
                  type="button"
                  onClick={() => setIsHelpOpen(false)}
                  className="rounded-lg bg-[var(--insights-accent)] px-3 py-1.5 text-xs font-semibold text-white transition hover:opacity-90"
                >
                  Got it
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── High-Level Performance KPI Cards Grid ── */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {/* Card 1: Team Score */}
        <div className="flex flex-col justify-between rounded-xl border border-[var(--insights-card-border)] bg-[var(--bg-raised)] p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs font-semibold text-[var(--text-muted)]">
              <Activity size={14} className="text-blue-500" aria-hidden="true" />
              <span>Team score</span>
            </span>
            {grade && gradePalette && (
              <span
                className="inline-flex items-center rounded-md px-2 py-0.5 text-[11px] font-bold"
                style={{
                  backgroundColor: gradePalette.background,
                  color: gradePalette.text,
                  border: `1px solid ${gradePalette.border}`,
                }}
              >
                Grade {grade}
              </span>
            )}
          </div>
          <div className="my-2 flex items-baseline gap-2">
            <strong className="text-[28px] font-bold tabular-nums text-[var(--insights-heading)]">
              {score === null ? 'N/A' : `${score.toFixed(1)}%`}
            </strong>
          </div>
          <div>
            {change === null ? (
              <span className="text-[13px] text-[var(--text-muted)]">No previous month</span>
            ) : (
              <span
                className={`inline-flex items-center gap-1 text-[13px] font-semibold tabular-nums ${
                  change < 0
                    ? 'text-rose-600 dark:text-rose-400'
                    : 'text-emerald-600 dark:text-emerald-400'
                }`}
              >
                {change >= 0 ? (
                  <TrendingUp size={14} aria-hidden="true" />
                ) : (
                  <TrendingDown size={14} aria-hidden="true" />
                )}
                {change > 0 ? '+' : change < 0 ? '−' : ''}
                {Math.abs(change).toFixed(1)} pts vs previous month
              </span>
            )}
          </div>
        </div>

        {/* Card 2: Target & Gap */}
        <div className="flex flex-col justify-between rounded-xl border border-[var(--insights-card-border)] bg-[var(--bg-raised)] p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs font-semibold text-[var(--text-muted)]">
              <Target size={14} className="text-indigo-500" aria-hidden="true" />
              <span>Target Benchmark</span>
            </span>
            <span className="text-[11px] font-medium text-[var(--text-muted)]">
              Goal: {target.toFixed(1)}%
            </span>
          </div>
          <div className="my-2 flex items-baseline gap-2">
            <strong className="text-[28px] font-bold tabular-nums text-[var(--insights-heading)]">
              {target.toFixed(1)}%
            </strong>
          </div>
          <div className="text-[13px] font-medium">
            {gap !== null ? (
              <span
                className={`font-semibold tabular-nums ${
                  gap >= 0
                    ? 'text-emerald-600 dark:text-emerald-400'
                    : 'text-rose-600 dark:text-rose-400'
                }`}
              >
                {gap >= 0
                  ? `+${gap.toFixed(1)} pts ahead of target`
                  : `−${Math.abs(gap).toFixed(1)} pts to target`}
              </span>
            ) : (
              <span className="text-[var(--text-muted)]">Benchmark: 100.0%</span>
            )}
          </div>
        </div>

        {/* Card 3: Analyzed KPIs & Scope Health */}
        <div className="flex flex-col justify-between rounded-xl border border-[var(--insights-card-border)] bg-[var(--bg-raised)] p-4 shadow-sm sm:col-span-2 lg:col-span-1">
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs font-semibold text-[var(--text-muted)]">
              <Layers size={14} className="text-teal-500" aria-hidden="true" />
              <span>Analyzed KPIs</span>
            </span>
            {summary?.coverage_percent !== null && summary?.coverage_percent !== undefined && (
              <span className="text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                {summary.coverage_percent}% coverage
              </span>
            )}
          </div>
          <div className="my-2 flex items-baseline gap-2">
            <strong className="text-[28px] font-bold tabular-nums text-[var(--insights-heading)]">
              {scored.length} KPIs
            </strong>
          </div>
          <p className="text-[13px] text-[var(--text-secondary)]">
            <strong className="font-semibold tabular-nums text-[var(--text-primary)]">{below}</strong> of{' '}
            {scored.length} KPIs below target
          </p>
        </div>
      </div>

      {/* ── Breakdown Summary: KPI Health Distribution Bar ── */}
      <div className="flex flex-col gap-2.5 rounded-xl border border-[var(--insights-card-border)] bg-[var(--bg-raised)] p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-xs font-bold uppercase tracking-wider text-[var(--text-secondary)]">
            KPI Health Distribution
          </span>
          <div className="flex flex-wrap items-center gap-3 text-xs">
            <span className="flex items-center gap-1.5 font-medium text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 size={13} aria-hidden="true" />
              <span>{onTrackCount} on track ({onTrackPct.toFixed(0)}%)</span>
            </span>
            <span className="flex items-center gap-1.5 font-medium text-amber-600 dark:text-amber-400">
              <span className="size-2 rounded-full bg-amber-500" aria-hidden="true" />
              <span>{atRiskCount} at risk ({atRiskPct.toFixed(0)}%)</span>
            </span>
            <span className="flex items-center gap-1.5 font-medium text-rose-600 dark:text-rose-400">
              <span className="size-2 rounded-full bg-rose-500" aria-hidden="true" />
              <span>{criticalCount} critical ({criticalPct.toFixed(0)}%)</span>
            </span>
          </div>
        </div>

        {/* Segmented Distribution Bar */}
        <div
          className="relative flex h-2.5 w-full overflow-hidden rounded-full bg-[var(--insights-bar-track,rgba(0,0,0,0.06))]"
          role="progressbar"
          aria-label="KPI health breakdown"
          aria-valuenow={Math.round(onTrackPct)}
          aria-valuemin={0}
          aria-valuemax={100}
        >
          {totalScored > 0 ? (
            <>
              {onTrackPct > 0 && (
                <div
                  style={{ width: `${onTrackPct}%` }}
                  title={`On Track: ${onTrackCount} (${onTrackPct.toFixed(1)}%)`}
                  className="bg-emerald-500 transition-all duration-300"
                />
              )}
              {atRiskPct > 0 && (
                <div
                  style={{ width: `${atRiskPct}%` }}
                  title={`At Risk: ${atRiskCount} (${atRiskPct.toFixed(1)}%)`}
                  className="bg-amber-500 transition-all duration-300"
                />
              )}
              {criticalPct > 0 && (
                <div
                  style={{ width: `${criticalPct}%` }}
                  title={`Critical: ${criticalCount} (${criticalPct.toFixed(1)}%)`}
                  className="bg-rose-500 transition-all duration-300"
                />
              )}
            </>
          ) : (
            <div className="w-full bg-[var(--text-muted)] opacity-20" />
          )}
        </div>
      </div>

      {/* ── Critical Alerts Action Strip ── */}
      {criticalInsights.length > 0 && first && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-rose-500/25 bg-rose-500/10 px-4 py-3">
          <button
            type="button"
            onClick={() => onOpenInsight(first)}
            className="inline-flex items-center gap-2 text-left text-[13px] font-semibold text-rose-700 transition hover:underline dark:text-rose-300"
          >
            <AlertTriangle size={15} className="shrink-0 text-rose-600 dark:text-rose-400" aria-hidden="true" />
            <span>
              {criticalInsights.length} critical {criticalInsights.length === 1 ? 'alert' : 'alerts'}: {first.title}
            </span>
          </button>
          <button
            type="button"
            onClick={() => onOpenInsight(first)}
            className="inline-flex items-center gap-1 rounded-lg border border-rose-500/30 bg-rose-500/15 px-3 py-1 text-xs font-bold text-rose-700 transition hover:bg-rose-500/25 dark:text-rose-200"
          >
            <span>View Details</span>
            <ArrowRight size={13} aria-hidden="true" />
          </button>
        </div>
      )}

      {/* ── Story Basis Context Message ── */}
      {story?.basis_context?.message && (
        <p className="w-full text-[12px] text-[var(--text-muted)]">{story.basis_context.message}</p>
      )}
    </section>
  );
}
