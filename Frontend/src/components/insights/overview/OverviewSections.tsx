import { useId, useState, type ReactNode } from 'react';
import {
  Activity, Anchor, ArrowDown, ArrowDownRight, ArrowUp, ArrowUpRight, ChevronDown, ChevronRight, Info,
  Globe, Lightbulb, TriangleAlert, User, UserRound, Users,
} from 'lucide-react';
import type { InsightDriver, InsightPeopleContributionAnalysis, InsightScopeSummary } from '../../../features/insights/types';
import kpiOverviewIcon from '../../../assets/insights/kpi-overview.svg';
import moreAnalysisIcon from '../../../assets/insights/more-analysis.svg';
import weightedContributionIcon from '../../../assets/insights/weighted-contribution.svg';
import { GradeBadge, SectionCard, SectionHeader, ShareBar, ViewAllButton } from './InsightsOverviewPrimitives';
import BasisComparisonNote from '../../../features/evaluation/BasisComparisonNote';
import {
  barShare, cleanScope, formatPercent, formatSignedPercent, geographyGap,
  lowPerformingTeams, MORE_ANALYSIS_KEYS, peopleToReview, sparklinePoints, splitDrivers, teamGap, teamsNeedingAttention,
  type MoreAnalysisKey, type TeamSummary,
} from './insightsOverviewModel';

const negativeColor = 'var(--insights-negative)';
const positiveColor = 'var(--insights-positive)';
const scrollX = '[overflow-x:auto]';

/* ── 3 · Key drivers of the gap (Figma 18:138) ─────────────────────────── */

function DriverRow({ driver, max, positive, divided, onSelect }: {
  driver: InsightDriver;
  max: number;
  positive: boolean;
  divided: boolean;
  onSelect: (insightId: string) => void;
}) {
  const color = positive ? positiveColor : negativeColor;
  const scope = cleanScope(driver.scope);
  return (
    <li className={divided ? 'border-t border-[var(--insights-positive-divider)]' : undefined}>
      <button
        type="button"
        onClick={() => onSelect(driver.insight_id)}
        aria-label={`${driver.driver} for ${scope}: ${formatSignedPercent(driver.impact_points)}`}
        className="flex w-full items-center gap-[16px] rounded-[6px] py-[10px] text-left transition hover:bg-[var(--bg-surface)]/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)]"
      >
        <span className="flex w-[250px] min-w-0 max-w-[50%] shrink-0 flex-col gap-[3px] leading-normal">
          <strong className="truncate text-[13px] font-semibold text-[var(--insights-heading)]" title={driver.driver}>{driver.driver}</strong>
          <span className="truncate text-[12px] font-normal text-[var(--text-muted)]" title={scope}>{scope}</span>
        </span>
        <ShareBar percent={barShare(driver.impact_points, max)} color={color} track="var(--insights-bar-track)" />
        <span className="w-[64px] shrink-0 text-right text-[15px] font-bold leading-normal" style={{ color }}>{formatSignedPercent(driver.impact_points)}</span>
      </button>
    </li>
  );
}

function DriverPanel({ tone, drivers, max, onSelect }: {
  tone: 'negative' | 'positive';
  drivers: InsightDriver[];
  max: number;
  onSelect: (insightId: string) => void;
}) {
  const positive = tone === 'positive';
  const title = positive ? 'Top positive drivers' : 'Top negative drivers';
  const DirectionIcon = positive ? ArrowUp : ArrowDown;
  return (
    <div
      className="flex min-w-0 flex-1 flex-col gap-[4px] self-stretch rounded-[10px] border px-[16px] pb-[10px] pt-[14px]"
      style={{
        background: `var(--insights-${tone}-panel-bg)`,
        borderColor: `var(--insights-${tone}-panel-border)`,
      }}
    >
      <div className="flex items-center gap-[10px]">
        <span aria-hidden="true" className="grid size-[28px] place-items-center rounded-[6px]" style={{ background: `var(--insights-${tone}-icon-bg)`, color: positive ? positiveColor : negativeColor }}>
          <DirectionIcon className="size-[16px]" strokeWidth={1.5} />
        </span>
        <h3 className="text-[14px] font-semibold leading-normal" style={{ color: `var(--insights-${tone}-title)` }}>{title}</h3>
      </div>
      {drivers.length ? (
        <ul aria-label={title}>
          {drivers.map((driver, index) => (
            <DriverRow key={driver.id} driver={driver} max={max} positive={positive} divided={positive && index > 0} onSelect={onSelect} />
          ))}
        </ul>
      ) : (
        <p className="py-[10px] text-[12px] text-[var(--text-muted)]">{positive ? 'No measured driver is closing the gap in this scope.' : 'No measured driver is widening the gap in this scope.'}</p>
      )}
    </div>
  );
}

export function KeyDriversSection({ drivers, onSelectDriver, onViewAll }: {
  drivers: InsightDriver[];
  onSelectDriver: (insightId: string) => void;
  onViewAll: () => void;
}) {
  const { negative, positive, maxMagnitude } = splitDrivers(drivers);
  return (
    <SectionCard labelledBy="key-drivers-title" className="gap-[16px] py-[20px]">
      <SectionHeader
        id="key-drivers-title"
        icon={<Activity className="size-[18px]" strokeWidth={1.5} />}
        iconBackground="var(--insights-icon-drivers)"
        title="Key drivers of the gap"
        subtitle="Top factors that are pulling the score down or up."
        action={drivers.length > 0 ? <ViewAllButton label="View all drivers" onClick={onViewAll} controls="more-analysis-weighted" /> : undefined}
      />
      <div className="flex w-full flex-col gap-[16px] lg:flex-row lg:items-start">
        <DriverPanel tone="negative" drivers={negative} max={maxMagnitude} onSelect={onSelectDriver} />
        <DriverPanel tone="positive" drivers={positive} max={maxMagnitude} onSelect={onSelectDriver} />
      </div>
    </SectionCard>
  );
}

/* ── 4a · Geography performance (Figma 18:199) ─────────────────────────── */

const GEOGRAPHY_LIMIT = 2;

export function GeographySection({ summaries, regionFilter, onSelectRegion }: {
  summaries: InsightScopeSummary[];
  regionFilter: string | undefined;
  onSelectRegion: (region: string) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? summaries : summaries.slice(0, GEOGRAPHY_LIMIT);
  const hasMore = summaries.length > GEOGRAPHY_LIMIT;
  const viewAll = regionFilter
    ? <ViewAllButton variant="link" onClick={() => onSelectRegion('')} />
    : hasMore
      ? <ViewAllButton variant="link" label={showAll ? 'Show less' : 'View all'} expanded={showAll} controls="geography-list" onClick={() => setShowAll((value) => !value)} />
      : undefined;
  return (
    <SectionCard labelledBy="geography-title" className="gap-[12px] self-stretch py-[20px]">
      <SectionHeader
        id="geography-title"
        icon={<Globe className="size-[18px]" strokeWidth={1.5} />}
        iconBackground="var(--insights-icon-geography)"
        title="Geography performance"
        subtitle="Performance by region."
        action={viewAll}
      />
      <span aria-hidden="true" className="h-[4px]" />
      {visible.length ? (
        <ul id="geography-list" className="flex flex-col gap-[12px]">
          {visible.map((summary) => {
            const gap = geographyGap(summary);
            const negative = gap !== null && gap < 0;
            const share = summary.gap_contribution_percent;
            return (
              <li key={summary.scope}>
                <button
                  type="button"
                  onClick={() => onSelectRegion(summary.scope)}
                  aria-label={`Focus ${summary.scope}: score ${formatPercent(summary.current_score)}, gap ${formatSignedPercent(gap)}`}
                  className="grid w-full grid-cols-1 items-center gap-[16px] rounded-[10px] border border-[var(--insights-card-border)] bg-[var(--bg-surface)] px-[16px] py-[14px] text-left transition hover:border-[var(--insights-accent-border)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)] sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_104px]"
                >
                  <span className="flex min-w-0 flex-col items-start gap-[4px]">
                    <strong className="text-[13px] font-semibold leading-normal text-[var(--insights-heading)]">{summary.scope}</strong>
                    <span className="flex items-center gap-[8px]">
                      <span className="text-[22px] font-bold leading-normal text-[var(--insights-heading)]">{formatPercent(summary.current_score)}</span>
                      {gap !== null && (negative
                        ? <ArrowDownRight aria-hidden="true" className="size-[14px] text-[var(--insights-negative)]" strokeWidth={1.75} />
                        : <ArrowUpRight aria-hidden="true" className="size-[14px] text-[var(--insights-positive)]" strokeWidth={1.75} />)}
                      <span className="text-[12px] font-semibold leading-normal" style={{ color: negative ? negativeColor : positiveColor }}>{formatSignedPercent(gap)}</span>
                    </span>
                    <GradeBadge score={summary.current_score} />
                  </span>
                  <ShareBar percent={share ?? 0} color={negativeColor} />
                  <span className="min-w-0 text-[12px] font-medium leading-normal text-[var(--insights-negative)] sm:text-right">
                    {share === null ? 'No gap share' : `${share.toFixed(1)}% gap share`}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="py-[12px] text-[13px] text-[var(--text-muted)]">No regional performance is measured for this scope.</p>
      )}
    </SectionCard>
  );
}

/* ── 4b · Teams needing attention (Figma 18:239) ───────────────────────── */

function Sparkline({ previous, current }: { previous: number | null; current: number | null }) {
  const points = sparklinePoints([previous, current]);
  if (!points.length) {
    return <span className="text-[12px] text-[var(--text-muted)]" title="No earlier period to compare">—</span>;
  }
  const color = (current ?? 0) < (previous ?? 0) ? negativeColor : positiveColor;
  const line = points.map((point, index) => `${index ? 'L' : 'M'}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join('');
  const area = `${line}V24H${points[0].x}Z`;
  return (
    <svg width="72" height="26" viewBox="0 0 72 26" fill="none" role="img" aria-label={`Score moved from ${formatPercent(previous)} to ${formatPercent(current)}`}>
      <path d={area} fill={color} fillOpacity={0.12} />
      <path d={line} stroke={color} strokeWidth={1.75} strokeLinejoin="round" />
      {points.slice(1).map((point) => <circle key={point.x} cx={point.x} cy={point.y} r={2} fill={color} />)}
    </svg>
  );
}

const TEAM_LIMIT = 5;

export function TeamsNeedingAttentionSection({ teams, onSelectTeam }: {
  teams: TeamSummary[];
  onSelectTeam: (team: string) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const ranked = teamsNeedingAttention(teams, Number.POSITIVE_INFINITY);
  const visible = showAll ? ranked : ranked.slice(0, TEAM_LIMIT);
  return (
    <SectionCard labelledBy="teams-attention-title" className="gap-[10px] self-stretch pb-[16px] pt-[20px]">
      <SectionHeader
        id="teams-attention-title"
        align="center"
        icon={<Users className="size-[18px]" strokeWidth={1.5} />}
        iconBackground="var(--insights-icon-teams)"
        title="Teams needing attention"
        action={ranked.length > TEAM_LIMIT ? <ViewAllButton variant="link" label={showAll ? 'Show less' : 'View all'} expanded={showAll} controls="teams-attention-list" onClick={() => setShowAll((value) => !value)} /> : undefined}
      />
      {visible.length ? (
        <div className={scrollX}>
          <div className="px-[4px] pb-[8px]"><BasisComparisonNote messages={visible.map((team) => team.basis_context?.message)} /></div>
          <div className="min-w-[460px]">
            <div aria-hidden="true" className="flex items-start gap-[8px] border-b border-[var(--insights-card-border)] px-[4px] pb-[8px] pt-[6px] text-[12px] font-medium leading-normal text-[var(--text-muted)]">
              <span className="min-w-0 flex-1">Team</span>
              <span className="w-[64px] shrink-0">Score</span>
              <span className="w-[132px] shrink-0">Grade</span>
              <span className="w-[64px] shrink-0">Gap</span>
              <span className="w-[72px] shrink-0">Trend</span>
              <span className="w-[16px] shrink-0" />
            </div>
            <ul id="teams-attention-list" aria-label="Teams needing attention">
              {visible.map((team) => {
                const gap = teamGap(team);
                return (
                  <li key={team.team} className="border-b border-[var(--insights-row-border)] last:border-b-0">
                    <button
                      type="button"
                      onClick={() => onSelectTeam(team.team)}
                      aria-label={`Open ${team.team} team analysis: score ${formatPercent(team.current_score)}, gap ${formatSignedPercent(gap)}`}
                      className="flex w-full items-center gap-[8px] px-[4px] py-[7px] text-left transition hover:bg-[var(--insights-chip-bg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--insights-accent)]"
                    >
                      <span className="min-w-0 flex-1 truncate text-[13px] font-semibold leading-normal text-[var(--insights-heading)]">{team.team}</span>
                      <span className="w-[64px] shrink-0 text-[13px] font-semibold leading-normal text-[var(--insights-heading)]">{formatPercent(team.current_score)}</span>
                      <span className="w-[132px] shrink-0"><GradeBadge score={team.current_score} /></span>
                      <span className="w-[64px] shrink-0 text-[13px] font-semibold leading-normal" style={{ color: gap !== null && gap < 0 ? negativeColor : positiveColor }}>{formatSignedPercent(gap)}</span>
                      <span className="flex w-[72px] shrink-0 items-center"><Sparkline previous={team.previous_score} current={team.current_score} /></span>
                      <ChevronRight aria-hidden="true" className="size-[16px] shrink-0 text-[var(--insights-chevron)]" strokeWidth={1.5} />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </div>
      ) : (
        <p className="py-[12px] text-[13px] text-[var(--text-muted)]">No team scores are measured for this scope.</p>
      )}
    </SectionCard>
  );
}

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

/* ── 6 · Recommended actions (Figma 18:451) ────────────────────────────── */

function ActionTile({ icon, iconBackground, title, subtitle, onClick }: {
  icon: ReactNode;
  iconBackground: string;
  title: string;
  subtitle: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex min-w-0 flex-1 items-center gap-[14px] self-stretch rounded-[10px] border border-[var(--insights-action-tile-border)] bg-[var(--bg-surface)] p-[16px] text-left shadow-[var(--insights-action-tile-shadow)] transition hover:-translate-y-px hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)]"
    >
      <span aria-hidden="true" className="grid size-[44px] shrink-0 place-items-center rounded-full" style={{ background: iconBackground }}>{icon}</span>
      <span className="flex min-w-0 flex-1 flex-col gap-[4px] leading-normal">
        <strong className="text-[13px] font-semibold text-[var(--insights-heading)]">{title}</strong>
        <span className="truncate text-[12px] font-normal text-[var(--text-muted)]">{subtitle}</span>
      </span>
      <ChevronRight aria-hidden="true" className="size-[18px] shrink-0 text-[var(--text-secondary)]" strokeWidth={1.5} />
    </button>
  );
}

export function RecommendedActionsSection({ drivers, teams, onOpenDriver, onSelectTeam, onCoach }: {
  drivers: InsightDriver[];
  teams: TeamSummary[];
  onOpenDriver: (insightId: string) => void;
  onSelectTeam: (team: string) => void;
  onCoach: () => void;
}) {
  const leadingGap = splitDrivers(drivers, 1).negative[0];
  const lowTeams = lowPerformingTeams(teams);
  return (
    <section
      aria-labelledby="recommended-actions-title"
      className="flex min-w-0 flex-col gap-[16px] rounded-[12px] border border-[var(--insights-actions-border)] bg-[var(--insights-actions-bg)] px-[24px] py-[20px]"
    >
      <SectionHeader
        id="recommended-actions-title"
        icon={<Lightbulb className="size-[18px]" strokeWidth={1.5} />}
        iconBackground="var(--insights-icon-actions)"
        title="Recommended actions"
        subtitle="Take these actions to improve performance."
      />
      <div className="flex w-full flex-col gap-[16px] lg:flex-row lg:items-stretch">
        {leadingGap && (
          <ActionTile
            icon={<Anchor className="size-[22px] text-[var(--insights-tile-focus-icon)]" strokeWidth={1.75} />}
            iconBackground="var(--insights-tile-focus-bg)"
            title={`Focus on ${leadingGap.driver}`}
            subtitle={`Largest performance gap (${formatSignedPercent(leadingGap.impact_points)})`}
            onClick={() => onOpenDriver(leadingGap.insight_id)}
          />
        )}
        {lowTeams.length > 0 && (
          <ActionTile
            icon={<Users className="size-[22px] text-[var(--insights-tile-teams-icon)]" strokeWidth={1.75} />}
            iconBackground="var(--insights-tile-teams-bg)"
            title="Review low-performing teams"
            subtitle={lowTeams.slice(0, 3).map((team) => team.team).join(', ')}
            onClick={() => onSelectTeam(lowTeams[0].team)}
          />
        )}
        <ActionTile
          icon={<User className="size-[22px] text-[var(--insights-tile-coach-icon)]" strokeWidth={1.75} />}
          iconBackground="var(--insights-tile-coach-bg)"
          title="Coach affected employees"
          subtitle="Share insights and action plans"
          onClick={onCoach}
        />
      </div>
    </section>
  );
}

/* ── 7 · More analysis (optional) (Figma 18:491) ───────────────────────── */

const accordionMeta: Record<MoreAnalysisKey, { title: string; description: string; iconBackground: string; icon: ReactNode }> = {
  kpi: {
    title: 'KPI overview',
    description: 'Total KPIs, status, and category breakdown.',
    iconBackground: 'var(--insights-acc-kpi-bg)',
    icon: <img src={kpiOverviewIcon} alt="" className="block" />,
  },
  role: {
    title: 'Performance by role',
    description: 'Detailed role performance and contributions.',
    iconBackground: 'var(--insights-acc-role-bg)',
    icon: <Users className="size-[18px] text-[var(--insights-acc-role-icon)]" strokeWidth={1.5} />,
  },
  weighted: {
    title: 'Weighted score contribution',
    description: 'How each KPI contributes to the overall score.',
    iconBackground: 'var(--insights-acc-weighted-bg)',
    icon: <img src={weightedContributionIcon} alt="" className="block" />,
  },
  alerts: {
    title: 'Recent critical alerts',
    description: 'Issues that need immediate attention.',
    iconBackground: 'var(--insights-acc-alerts-bg)',
    icon: <TriangleAlert className="size-[18px] text-[var(--insights-acc-alerts-icon)]" strokeWidth={1.5} />,
  },
};

export function MoreAnalysisSection({ open, onToggle, onToggleAll, panels }: {
  open: Record<MoreAnalysisKey, boolean>;
  onToggle: (key: MoreAnalysisKey) => void;
  onToggleAll: (expand: boolean) => void;
  panels: Record<MoreAnalysisKey, ReactNode>;
}) {
  const allOpen = MORE_ANALYSIS_KEYS.every((key) => open[key]);
  return (
    <SectionCard labelledBy="more-analysis-title" tone="muted" className="gap-[14px] py-[20px]">
      <SectionHeader
        id="more-analysis-title"
        align="center"
        icon={<img src={moreAnalysisIcon} alt="" className="block" />}
        iconBackground="var(--insights-icon-more)"
        title="More analysis (optional)"
        subtitle="Explore detailed breakdowns and KPIs."
        subtitleTone="subtle"
        action={(
          <button
            type="button"
            onClick={() => onToggleAll(!allOpen)}
            className="inline-flex shrink-0 items-center gap-[6px] rounded-[6px] pl-[8px] pr-[4px] text-[13px] font-medium leading-normal text-[var(--insights-heading)] hover:text-[var(--insights-accent-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)]"
          >
            {allOpen ? 'Collapse all' : 'Expand all'}
            <ChevronDown aria-hidden="true" className={`size-[18px] transition-transform ${allOpen ? 'rotate-180' : ''}`} strokeWidth={1.5} />
          </button>
        )}
      />
      <div className="flex w-full flex-col gap-[8px]">
        {MORE_ANALYSIS_KEYS.map((key) => {
          const meta = accordionMeta[key];
          const isOpen = open[key];
          const panelId = `more-analysis-${key}`;
          return (
            <div key={key} className="overflow-hidden rounded-[10px] border border-[var(--insights-accordion-border)] bg-[var(--bg-surface)]">
              <h3>
                <button
                  type="button"
                  aria-expanded={isOpen}
                  aria-controls={panelId}
                  onClick={() => onToggle(key)}
                  className="flex w-full items-center gap-[14px] py-[10px] pl-[12px] pr-[16px] text-left transition hover:bg-[var(--insights-chip-bg)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-[var(--insights-accent)]"
                >
                  <span aria-hidden="true" className="grid size-[32px] shrink-0 place-items-center rounded-[8px]" style={{ background: meta.iconBackground }}>{meta.icon}</span>
                  <span className="shrink-0 text-[14px] font-semibold leading-normal text-[var(--insights-heading)]">{meta.title}</span>
                  <span className="min-w-0 flex-1 truncate text-[12px] font-normal leading-normal text-[var(--text-muted)]">{meta.description}</span>
                  <ChevronDown aria-hidden="true" className={`size-[18px] shrink-0 text-[var(--text-secondary)] transition-transform ${isOpen ? 'rotate-180' : ''}`} strokeWidth={1.5} />
                </button>
              </h3>
              {isOpen && (
                <div id={panelId} role="region" aria-label={meta.title} className="border-t border-[var(--insights-accordion-border)]">
                  {panels[key]}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </SectionCard>
  );
}
