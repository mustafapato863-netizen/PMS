import { useId, useState } from 'react';
import { ChevronRight, Info, UserRound } from 'lucide-react';
import type { InsightPeopleContributionAnalysis } from '../../../features/insights/types';
import { GradeBadge, SectionCard, SectionHeader, ViewAllButton } from './InsightsOverviewPrimitives';
import { peopleToReview } from './insightsOverviewModel';

/* ── 5 · People to review (Figma 18:371) ───────────────────────────────── */

const PEOPLE_LIMIT = 3;

/**
 * Role: the position when the employee has one. The backend writes "All positions" when there is none, so the
 * performance level is shown instead. A dash only when both are missing.
 */
const roleLabel = (position: string | null | undefined, level: string | null | undefined): string => {
  if (position && position !== 'All positions') return position;
  return level && level.trim() ? level : '—';
};

/** Points, with a true minus sign: one decimal from 1 point, two decimals below it ("−1.9 pts", "−0.42 pts"). */
const formatPoints = (points: number | null | undefined): string => {
  if (points === null || points === undefined) return '—';
  const magnitude = Math.abs(points);
  const sign = points < 0 ? '−' : '';
  return `${sign}${magnitude.toFixed(magnitude < 1 ? 2 : 1)} pts`;
};

/**
 * The person's own loss on their score, derived from the row: weighted impact × employees measured. The row's
 * impact is (earned − KPI weight) ÷ employees measured, so the product is earned − weight. The impact is
 * rounded to two decimals in the payload, so this is exact to about 0.005 points per employee measured.
 */
const ownScoreLoss = (weightedImpact: number | null | undefined, employeesMeasured: number): number | null => (
  weightedImpact === null || weightedImpact === undefined || employeesMeasured <= 0 ? null : Math.round(weightedImpact * employeesMeasured * 10) / 10
);

const effectExplanation = (kpiLabel: string | null): string => (
  `Points this person's ${kpiLabel ?? 'KPI'} shortfall takes off the team's average score. KPI weight minus what they earned, shared across the employees measured.`
);

/** A keyboard and touch control (not hover-only) that shows what the effect column means. */
function EffectInfo({ kpiLabel }: { kpiLabel: string | null }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <span className="relative inline-flex shrink-0">
      <button
        type="button"
        aria-label={`What "Effect on team score" means${kpiLabel ? ` for ${kpiLabel}` : ''}`}
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => { if (event.key === 'Escape') setOpen(false); }}
        className="inline-flex size-[20px] items-center justify-center rounded-full border border-[var(--insights-card-border)] text-[var(--text-secondary)] hover:bg-[var(--insights-chip-bg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)]"
      >
        <Info aria-hidden="true" className="size-[12px]" strokeWidth={2} />
      </button>
      {open && (
        <span id={panelId} role="note" className="absolute right-0 top-[26px] z-10 w-[260px] rounded-[8px] border border-[var(--insights-card-border)] bg-[var(--bg-surface)] p-[10px] text-left text-[12px] font-normal leading-normal text-[var(--text-secondary)] shadow-md">
          {effectExplanation(kpiLabel)}
        </span>
      )}
    </span>
  );
}

/** The employee's stored performance score for the period, one decimal. A dash when none is stored. */
const formatScore = (score: number | null | undefined): string => (score === null || score === undefined ? '—' : `${score.toFixed(1)}%`);

export function PeopleToReviewSection({ analysis, onOpenEmployee, fullAnalysisOpen = false, onOpenFullAnalysis, onBackToOverview }: {
  analysis: InsightPeopleContributionAnalysis | null | undefined;
  onOpenEmployee: (employeeId: string, performanceLevel: string) => void;
  /** The page is showing the full KPI analysis for this section's KPI. */
  fullAnalysisOpen?: boolean;
  /** Opens the full KPI analysis for the leading KPI (sets the page's KPI filter). */
  onOpenFullAnalysis?: () => void;
  /** Clears the KPI filter: the page returns to the overview. */
  onBackToOverview?: () => void;
}) {
  // "View all" expands this list in place and becomes "Show less"; it never changes the page filters.
  const [showAll, setShowAll] = useState(false);
  const all = peopleToReview(analysis, Number.POSITIVE_INFINITY);
  const visible = showAll ? all : all.slice(0, PEOPLE_LIMIT);
  const kpiLabel = analysis?.kpi_label ?? null;
  const employeesMeasured = analysis?.total_employees ?? 0;
  const viewAll = all.length > PEOPLE_LIMIT
    ? <ViewAllButton variant="link" label={showAll ? 'Show less' : 'View all'} expanded={showAll} controls="people-review-list" onClick={() => setShowAll((value) => !value)} />
    : undefined;
  return (
    <SectionCard labelledBy="people-review-title" className="gap-[14px] pb-[12px] pt-[20px]">
      <SectionHeader
        id="people-review-title"
        icon={<UserRound className="size-[18px]" strokeWidth={1.5} />}
        iconBackground="var(--insights-icon-people)"
        title="People to review"
        subtitle={kpiLabel ? `People pulling the team score down most on ${kpiLabel}` : 'People pulling the team score down most'}
        action={viewAll}
      />
      {visible.length ? (
        <div>
          {/* Columns from md up. Below md each row wraps into lines, so nothing scrolls sideways at 390px. */}
          <div className="hidden items-start gap-[12px] border-b border-[var(--insights-card-border)] px-[8px] pb-[8px] pt-[6px] text-[12px] font-medium leading-normal text-[var(--text-muted)] md:flex">
            <span className="w-[150px] shrink-0">Team</span>
            <span className="w-[200px] shrink-0">Employee</span>
            <span className="min-w-0 flex-1">Role</span>
            <span className="w-[96px] shrink-0 text-right">Score</span>
            <span className="w-[120px] shrink-0">Grade</span>
            <span className="flex w-[150px] shrink-0 items-center justify-end gap-[4px]">
              <span>Effect on team score</span>
              <EffectInfo kpiLabel={kpiLabel} />
            </span>
            <span className="w-[16px] shrink-0" />
          </div>
          <ul id="people-review-list" aria-label="People to review">
            {visible.map((person) => (
              <li key={`${person.team}-${person.employee_id}-${person.performance_level}-${person.position}`} className="border-b border-[var(--insights-row-border)] last:border-b-0">
                <button
                  type="button"
                  onClick={() => onOpenEmployee(person.employee_id, person.performance_level)}
                  aria-label={`Open ${person.employee_name}: effect on team score ${formatPoints(person.weighted_impact)}${ownScoreLoss(person.weighted_impact, employeesMeasured) !== null ? `, ${formatPoints(ownScoreLoss(person.weighted_impact, employeesMeasured))} on their own score` : ''}`}
                  className="flex w-full flex-wrap items-center gap-x-[12px] gap-y-[6px] px-[8px] py-[10px] text-left transition hover:bg-[var(--insights-chip-bg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--insights-accent)] md:flex-nowrap"
                >
                  <span className="w-full truncate text-[12px] leading-normal text-[var(--text-secondary)] md:w-[150px] md:shrink-0 md:text-[13px]">{person.team}</span>
                  <span className="min-w-0 flex-1 truncate text-[13px] font-semibold leading-normal text-[var(--insights-heading)] md:w-[200px] md:flex-none">{person.employee_name}</span>
                  <span className="w-full truncate text-[12px] leading-normal text-[var(--text-secondary)] md:w-auto md:min-w-0 md:flex-1 md:text-[13px]">{roleLabel(person.position, person.performance_level)}</span>
                  <span className="shrink-0 text-[13px] font-semibold leading-normal tabular-nums text-[var(--insights-heading)] md:w-[96px] md:text-right"><span className="md:hidden">Score </span>{formatScore(person.performance_score)}</span>
                  <span className="shrink-0 md:w-[120px]"><GradeBadge score={person.performance_score} /></span>
                  <span className="shrink-0 text-[13px] font-bold leading-normal text-[var(--insights-negative)] md:w-[150px] md:text-right"><span className="md:hidden">Effect </span>{formatPoints(person.weighted_impact)}</span>
                  <ChevronRight aria-hidden="true" className="size-[16px] shrink-0 text-[var(--insights-chevron)]" strokeWidth={1.5} />
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : (
        <p className="px-[8px] py-[12px] text-[13px] text-[var(--text-muted)]">No negative employee contributors were measured for the leading KPI.</p>
      )}
      {(onOpenFullAnalysis || fullAnalysisOpen) && kpiLabel && (
        <div className="flex flex-wrap items-center justify-between gap-[8px] border-t border-[var(--insights-row-border)] px-[8px] pt-[10px]">
          <span className="text-[12px] text-[var(--text-muted)]">{fullAnalysisOpen ? `Showing the full ${kpiLabel} analysis below.` : 'Every employee measured on this KPI, with the full breakdown.'}</span>
          {fullAnalysisOpen
            ? <button type="button" onClick={onBackToOverview} className="text-[12px] font-semibold text-[var(--insights-accent-text)] underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)]">Back to overview</button>
            : <button type="button" onClick={onOpenFullAnalysis} className="text-[12px] font-semibold text-[var(--insights-accent-text)] underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)]">Full {kpiLabel} analysis</button>}
        </div>
      )}
    </SectionCard>
  );
}
