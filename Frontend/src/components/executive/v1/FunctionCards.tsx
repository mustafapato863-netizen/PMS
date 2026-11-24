import { useMemo, useState } from 'react';
import {
  ArrowDownUp,
  ArrowRight,
  Info,
  LayoutGrid,
  Rows3,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { FUNCTION_STYLE, formatShare } from './execModel';
import type {
  ExecutiveFunction,
  ExecutiveFunctionCard,
  ExecutiveFunctionCohort,
  ExecutivePeriod,
  ExecutiveRangeBlock,
} from '../../../features/executive/types';
import { coveredPeriodLabel, vsLabel } from '../../../features/executive/periodLabels';
import { functionSlug } from '../../../features/executive/functions';
import { arrow, fmtScore, fmtSigned, scoreTone, toneColor } from '../../../features/executive/format';
import { getGradeTone } from '../../../constants/grades';
import { GradePill, ScoreBar, ScoreText, StatLabel, StatusPill, ToneText } from './ExecPrimitives';
import { gradeGradientVar } from './gradeGradient';
import FunctionTrendChart from './FunctionTrendChart';
import BasisComparisonNote from '../../../features/evaluation/BasisComparisonNote';

export function FunctionIcon({ fn, size = 28 }: { fn: ExecutiveFunction; size?: number }) {
  const style = FUNCTION_STYLE[fn];
  const Icon = style.icon;
  return (
    <span
      aria-hidden="true"
      className="flex shrink-0 items-center justify-center rounded-[8px] shadow-2xs"
      style={{
        background: style.bg,
        width: size,
        height: size,
        border: `1px solid color-mix(in srgb, ${style.color} 18%, transparent)`,
      }}
    >
      <Icon style={{ color: style.color, width: size * 0.52, height: size * 0.52 }} strokeWidth={1.85} />
    </span>
  );
}

function FunctionLink({
  cardFunction,
  style,
}: {
  cardFunction: ExecutiveFunction;
  style: (typeof FUNCTION_STYLE)[ExecutiveFunction];
}) {
  const [searchParams] = useSearchParams();
  const next = new URLSearchParams();
  for (const key of ['period', 'from', 'to', 'region', 'branch', 'level']) {
    const val = searchParams.get(key);
    if (val && val !== 'All' && val !== 'all') next.set(key, val);
  }
  const query = next.toString();
  const functionHref = `/function-summary/${functionSlug(cardFunction)}${query ? `?${query}` : ''}`;

  return (
    <Link
      to={functionHref}
      aria-label={`View ${cardFunction} function`}
      className="group/btn inline-flex min-h-[28px] shrink-0 items-center justify-center gap-[4px] rounded-[9px] border px-[10px] py-[4px] text-[11.5px] font-bold transition-all duration-200 hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)] motion-reduce:transition-none"
      style={{
        background: style.bg,
        color: style.color,
        borderColor: `color-mix(in srgb, ${style.color} 26%, transparent)`,
      }}
    >
      Open
      <ArrowRight
        aria-hidden="true"
        className="size-[12px] transition-transform duration-200 group-hover/btn:translate-x-0.5"
      />
    </Link>
  );
}

function CohortTile({ label, cohort }: { label: string; cohort: ExecutiveFunctionCohort }) {
  const tone = getGradeTone(cohort.score);
  const names = cohort.teams.slice(0, 3).join(' · ');
  const extra = cohort.teams.length > 3 ? ` · +${cohort.teams.length - 3}` : '';
  return (
    <div
      role="group"
      aria-label={label}
      className="flex min-w-0 flex-col gap-[5px] rounded-[10px] border border-[var(--exec-card-border)] bg-[var(--exec-tile-bg)] p-[8px]"
    >
      <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {label}
      </span>
      <div className="flex flex-wrap items-end gap-[6px]">
        <ScoreText
          score={cohort.score}
          className="text-[20px] font-bold leading-none tracking-[-0.03em] tabular-nums"
        >
          {fmtScore(cohort.score)}
        </ScoreText>
        <GradePill score={cohort.score} />
      </div>
      <ScoreBar score={cohort.score} color={tone.gauge} />
      <p className="text-[11px] leading-[1.4] text-[var(--text-secondary)]">
        {cohort.employees} {cohort.employees === 1 ? 'person' : 'people'}
        {names ? ` · ${names}${extra}` : ''}
      </p>
      <ToneText tone={scoreTone(cohort.gap)} className="text-[12px] font-semibold tabular-nums">
        {arrow(cohort.gap)} {fmtSigned(cohort.gap)} vs 100
      </ToneText>
    </div>
  );
}

export function FunctionCohorts({
  cohorts,
  columns = false,
}: {
  cohorts: NonNullable<ExecutiveFunctionCard['cohorts']>;
  columns?: boolean;
}) {
  return (
    <div data-testid="function-cohorts" className={`grid gap-[6px] ${columns ? 'sm:grid-cols-2' : ''}`}>
      <CohortTile label="Employees" cohort={cohorts.employees} />
      <CohortTile label="Supportive positions" cohort={cohorts.support} />
    </div>
  );
}

function FunctionCard({
  card,
  previous,
  range,
  linkable,
  markStart,
  featured,
  showCohorts,
  classic,
  onSelectFunction,
  onSelectTeam,
}: {
  card: ExecutiveFunctionCard;
  previous: ExecutivePeriod | null;
  range: ExecutiveRangeBlock | null;
  linkable: boolean;
  markStart: boolean;
  featured: boolean;
  showCohorts: boolean;
  /** Company page: icon, score, gap, trend, and the tinted View function button. */
  classic: boolean;
  onSelectFunction?: (fn: ExecutiveFunction) => void;
  onSelectTeam?: (team: string, fn: ExecutiveFunction) => void;
}) {
  const tone = getGradeTone(card.score);
  const style = FUNCTION_STYLE[card.function];
  const changeTone = scoreTone(card.change);
  const trendColor = changeTone === 'neutral' ? style.color : toneColor(changeTone);
  const comparison = vsLabel(previous, range, 'vs last');
  const showTeamButtons = Boolean(onSelectTeam);
  const showTeamDump = !showTeamButtons && !featured && !(showCohorts && card.cohorts);

  return (
    <article
      aria-label={`${card.function} function`}
      className="pms-glass-surface pms-glass-surface--interactive group/fcard relative flex h-full min-w-0 flex-col gap-[10px] overflow-hidden rounded-[18px] p-[15px]"
      style={{
        backgroundImage: `radial-gradient(circle at 95% 6%, color-mix(in srgb, ${tone.gauge} 13%, transparent) 0%, transparent 64%), var(--pms-glass-card-bg)`,
        borderColor: `color-mix(in srgb, ${tone.gauge} 20%, var(--pms-glass-card-border))`,
      }}
    >
      {/* Smooth Linear-Gradient Top Grade Accent Strip */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-[3px]"
        style={{ background: gradeGradientVar(card.score) }}
      />

      {/* Zone 1: Card Header + Top-Right Grade Pill (Full-width subtitle never truncates) */}
      <div className="flex flex-col gap-[4px]">
        <div className="flex items-center justify-between gap-[6px]">
          <div className="flex min-w-0 items-center gap-[8px]">
            <FunctionIcon fn={card.function} size={32} />
            {onSelectFunction ? (
              <button
                type="button"
                className="truncate text-left text-[15px] font-bold leading-[1.2] tracking-[-0.02em] text-[var(--insights-heading)] hover:underline"
                aria-label={`Open ${card.function}`}
                onClick={() => onSelectFunction(card.function)}
              >
                {card.function}
              </button>
            ) : (
              <h3 className="truncate text-[15px] font-bold leading-[1.2] tracking-[-0.02em] text-[var(--insights-heading)]">
                {card.function}
              </h3>
            )}
          </div>
          <GradePill score={card.score} className="!px-[8px] !py-[2px] !text-[11px]" />
        </div>

        <p className="truncate text-[12px] leading-[1.35] text-[var(--text-muted)]">
          {card.teams.length} {card.teams.length === 1 ? 'team' : 'teams'} · {card.employees}{' '}
          {card.employees === 1 ? 'person' : 'people'}
          {card.regions.length ? ` · ${card.regions.join(' + ')}` : ''}
        </p>
      </div>

      {markStart && card.score !== null && (
        <span className="inline-flex w-fit rounded-full bg-[var(--exec-neg-bg)] px-[8px] py-[2px] text-[11px] font-bold uppercase tracking-[0.08em] text-[var(--insights-negative)]">
          Start here
        </span>
      )}

      {/* Zone 2: Frosted Metric Stage (Score + GAP | VS MAY + Smooth Gradient Score Bar w/ 90% Marker) */}
      <div className="pms-glass-stage space-y-2 rounded-[12px] px-3 py-2.5">
        <div className="flex items-center justify-between gap-1.5">
          <div className="flex flex-col">
            <ScoreText
              score={card.score}
              className="text-[23px] font-bold leading-none tracking-[-0.04em] tabular-nums"
            >
              {fmtScore(card.score)}
            </ScoreText>
            {card.score !== null && !classic && (
              <span className="mt-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
                People average
              </span>
            )}
          </div>

          <div className="flex items-center gap-2.5">
            <div className="flex flex-col items-end">
              <StatLabel>{classic ? 'Gap' : 'vs 100'}</StatLabel>
              <ToneText
                tone={scoreTone(card.gap)}
                className="whitespace-nowrap text-[12px] font-bold tabular-nums"
              >
                {arrow(card.gap)} {fmtSigned(card.gap)}
              </ToneText>
            </div>
            <div className="h-6 w-px bg-[var(--exec-card-border)]" aria-hidden="true" />
            <div className="flex flex-col items-end">
              <StatLabel>{comparison}</StatLabel>
              <ToneText
                tone={changeTone}
                className="whitespace-nowrap text-[12px] font-semibold tabular-nums"
              >
                {arrow(card.change)} {fmtSigned(card.change)}
              </ToneText>
            </div>
          </div>
        </div>

        <ScoreBar score={card.score} color={tone.gauge} showThreshold90 />
      </div>

      {!classic && card.lowest_team && (
        <p className="truncate text-[11px] leading-[1.4] text-[var(--text-secondary)]">
          Lowest team · {card.lowest_team.team} at {card.lowest_team.score.toFixed(1)}%
          {card.lowest_team.score_basis === 'leader_scorecard' ? ' · Leader scorecard' : ''}
          {card.lowest_team.kpi ? ` · ${card.lowest_team.kpi}` : ''}
        </p>
      )}

      {showCohorts && card.cohorts && <FunctionCohorts cohorts={card.cohorts} />}

      {/* Zone 3: Momentum & Trajectory Header (only shown when card has a callout badge or gap share) */}
      {(card.is_most_improved || (card.falling_months !== null && card.falling_months >= 2) || (!classic && card.gap_share_percent != null && card.gap_share_percent > 0) || (classic && card.lowest_team && card.lowest_team.score < 85)) && (
        <div className="flex h-[20px] items-center justify-between gap-1.5 overflow-hidden">
          <div className="flex shrink-0 items-center">
            {card.is_most_improved ? (
              <StatusPill tone="success" icon={TrendingUp}>
                Most improved
              </StatusPill>
            ) : card.falling_months !== null && card.falling_months >= 2 ? (
              <StatusPill tone="danger" icon={TrendingDown}>
                Falling {card.falling_months} mo
              </StatusPill>
            ) : null}
          </div>

          {!classic && card.gap_share_percent != null && card.gap_share_percent > 0 ? (
            <span className="shrink-0 text-xs font-semibold text-[var(--insights-heading)]">
              {formatShare(card.gap_share_percent)}% of the gap
            </span>
          ) : classic && card.lowest_team && card.lowest_team.score < 85 ? (
            <span
              aria-hidden="true"
              className="truncate text-xs font-semibold text-amber-700 dark:text-amber-300"
              title={`Lowest team: ${card.lowest_team.team} (${card.lowest_team.score.toFixed(1)}%)`}
            >
              Low: {card.lowest_team.team} ({card.lowest_team.score.toFixed(0)}%)
            </span>
          ) : null}
        </div>
      )}

      {/* Zone 4: Fixed-Height 6-Month Sparkline Chart */}
      <FunctionTrendChart color={trendColor} title={`${card.function} score`} points={card.trend} />

      {/* Zone 5: Uniform Bottom-Aligned Footer (Figma split: teams/status on left, Open → pill on right) */}
      {showTeamButtons || showTeamDump || (linkable && !onSelectFunction) ? (
        <div className="mt-auto flex flex-col gap-[7px] border-t border-[var(--insights-row-border)] pt-[9px]">
          {showTeamButtons && onSelectTeam ? (
            <div className="flex flex-wrap gap-[5px]">
              {card.teams.map((team) => (
                <button
                  key={team}
                  type="button"
                  className="rounded-full border border-[var(--exec-card-border)] bg-[var(--exec-tile-bg)] px-[7px] py-[2px] text-[11px] font-semibold text-[var(--insights-heading)] hover:underline"
                  onClick={() => onSelectTeam(team, card.function)}
                >
                  {team}
                </button>
              ))}
            </div>
          ) : (
            <div className="flex items-center justify-between gap-[8px]">
              {showTeamDump ? (
                <p
                  className="min-w-0 flex-1 truncate text-[11.5px] font-medium leading-[1.35] text-[var(--text-secondary)]"
                  title={card.teams.join(' · ')}
                >
                  {card.teams.join(' · ')}
                </p>
              ) : (
                <span className="min-w-0 flex-1" />
              )}
              {linkable && !onSelectFunction && (
                <FunctionLink cardFunction={card.function} style={style} />
              )}
            </div>
          )}
        </div>
      ) : null}
      <span className="sr-only">{tone.label}</span>
    </article>
  );
}

type FunctionSortMode = 'default' | 'lowest' | 'highest' | 'momentum';
type FunctionFilterMode = 'all' | 'attention' | 'healthy';

export default function FunctionCards({
  cards,
  previous,
  range = null,
  linkable,
  featured = false,
  showCohorts = false,
  classic = false,
  note = null,
  count,
  onSelectFunction,
  onSelectTeam,
}: {
  cards: ExecutiveFunctionCard[];
  previous: ExecutivePeriod | null;
  range?: ExecutiveRangeBlock | null;
  linkable: boolean;
  /** Corporate page: equal cards. The start band already shows the first function. */
  featured?: boolean;
  /** Employees and supportive positions, when the card has both. Off for the presentation deck. */
  showCohorts?: boolean;
  /** Company summary: the chart card, without the start label or the share lines. */
  classic?: boolean;
  note?: string | null;
  /** Full function count when one function is shown in the start band instead of this grid. */
  count?: number;
  /** Stay on the current page: open this function instead of Function Summary. */
  onSelectFunction?: (fn: ExecutiveFunction) => void;
  onSelectTeam?: (team: string, fn: ExecutiveFunction) => void;
}) {
  const [sortMode, setSortMode] = useState<FunctionSortMode>('lowest');
  const [filterMode, setFilterMode] = useState<FunctionFilterMode>('all');
  const [expandedGrid, setExpandedGrid] = useState(false);

  const noted = cards.filter((card) => card.basis_context?.message);
  const sharedBasis =
    noted.length === cards.length && new Set(noted.map((card) => card.basis_context?.message)).size === 1;

  const attentionCount = useMemo(
    () => cards.filter((c) => c.score !== null && c.score < 90).length,
    [cards],
  );
  const healthyCount = useMemo(
    () => cards.filter((c) => c.score !== null && c.score >= 90).length,
    [cards],
  );

  const displayedCards = useMemo(() => {
    let list = [...cards];
    if (filterMode === 'attention') {
      list = list.filter((c) => c.score !== null && c.score < 90);
    } else if (filterMode === 'healthy') {
      list = list.filter((c) => c.score !== null && c.score >= 90);
    }

    if (sortMode === 'lowest') {
      list.sort((a, b) => (a.score ?? 999) - (b.score ?? 999));
    } else if (sortMode === 'highest') {
      list.sort((a, b) => (b.score ?? -1) - (a.score ?? -1));
    } else if (sortMode === 'momentum') {
      list.sort((a, b) => (a.change ?? 999) - (b.change ?? 999));
    }
    return list;
  }, [cards, filterMode, sortMode]);

  return (
    <section aria-labelledby="exec-functions-title" className="pms-glass-well flex flex-col gap-[16px] rounded-[22px] p-[18px] sm:p-[22px]">
      <div className="flex flex-wrap items-start justify-between gap-[10px]">
        <div className="flex flex-col gap-[3px]">
          <div className="flex flex-wrap items-center gap-[8px]">
            <h2 id="exec-functions-title" className="text-[17px] font-bold tracking-[-0.015em] text-[var(--insights-heading)]">
              Functions Overview
            </h2>
            {cards.length <= 2 && (
              <span className="rounded-full bg-[var(--exec-chip-bg)] px-[9px] py-[2px] text-xs font-semibold text-[var(--exec-chip-text)]">
                {count ?? cards.length} functions
              </span>
            )}
            {range && <span className="text-[12px] text-[var(--text-muted)]">{coveredPeriodLabel(null, range)}</span>}
          </div>
          <p className="text-[12px] text-[var(--text-muted)]">
            Sorted worst-first so functions needing support stand out immediately{linkable ? ' · Click any card to drill down' : ''}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {cards.length > 2 && (
            <div className="flex flex-wrap items-center gap-1.5">
              {/* Filter Pills (Figma 90% threshold pills) */}
              <div className="pms-glass-stage inline-flex items-center rounded-full p-0.5">
                <button
                  type="button"
                  onClick={() => setFilterMode('all')}
                  className={`rounded-full px-3 py-1 text-[11.5px] font-bold transition-colors ${
                    filterMode === 'all'
                      ? 'bg-[var(--insights-accent-soft)] text-[var(--insights-accent-text)]'
                      : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  All ({cards.length})
                </button>
                {attentionCount > 0 && (
                  <button
                    type="button"
                    onClick={() => setFilterMode('attention')}
                    className={`rounded-full px-3 py-1 text-[11.5px] font-bold transition-colors ${
                      filterMode === 'attention'
                        ? 'bg-rose-500/12 text-rose-700 dark:text-rose-300'
                        : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                    }`}
                  >
                    Below 90% ({attentionCount})
                  </button>
                )}
                {healthyCount > 0 && (
                  <button
                    type="button"
                    onClick={() => setFilterMode('healthy')}
                    className={`rounded-full px-3 py-1 text-[11.5px] font-bold transition-colors ${
                      filterMode === 'healthy'
                        ? 'bg-emerald-500/12 text-emerald-700 dark:text-emerald-300'
                        : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                    }`}
                  >
                    On Track ≥90% ({healthyCount})
                  </button>
                )}
              </div>

              {/* Sort Pills */}
              <div className="pms-glass-stage inline-flex items-center gap-1 rounded-full px-2 py-0.5">
                <ArrowDownUp size={11} className="text-[var(--text-muted)]" aria-hidden="true" />
                {(['lowest', 'highest', 'momentum', 'default'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setSortMode(mode)}
                    className={`rounded-full px-2 py-0.5 text-[11px] font-semibold transition-colors ${
                      sortMode === mode
                        ? 'bg-[var(--bg-surface)] text-[var(--insights-heading)] shadow-2xs'
                        : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                    }`}
                  >
                    {mode === 'lowest'
                      ? 'Worst first'
                      : mode === 'highest'
                        ? 'Best first'
                        : mode === 'momentum'
                          ? 'Drop'
                          : 'Gap share'}
                  </button>
                ))}
              </div>

              {/* Grid Density Switcher */}
              <button
                type="button"
                onClick={() => setExpandedGrid((prev) => !prev)}
                title={expandedGrid ? 'Switch to 4-column Figma grid' : 'Switch to 3-column wide grid'}
                className="pms-glass-stage inline-flex min-h-7 items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold text-[var(--text-secondary)] transition-colors hover:text-[var(--insights-heading)]"
              >
                {expandedGrid ? <Rows3 size={11} aria-hidden="true" /> : <LayoutGrid size={11} aria-hidden="true" />}
                <span>{expandedGrid ? '4-Col Grid' : '3-Col Grid'}</span>
              </button>
            </div>
          )}

          {featured && note ? (
            <span className="text-[12px] text-[var(--text-muted)]">{note}</span>
          ) : onSelectFunction ? (
            <span className="text-[12px] text-[var(--text-muted)]">
              Choose a function or a team to review it here
            </span>
          ) : null}
        </div>
      </div>

      {sharedBasis && <BasisComparisonNote messages={noted.map((card) => card.basis_context?.message)} />}

      <div
        className={
          expandedGrid
            ? 'grid grid-cols-1 gap-[14px] md:grid-cols-2 xl:grid-cols-3'
            : 'grid grid-cols-1 gap-[14px] sm:grid-cols-2 lg:grid-cols-4'
        }
      >
        {displayedCards.map((card, index) => (
          <FunctionCard
            key={card.function}
            card={card}
            previous={previous}
            range={range}
            linkable={linkable}
            markStart={!classic && !featured && index === 0}
            featured={featured}
            showCohorts={showCohorts}
            classic={classic}
            onSelectFunction={onSelectFunction}
            onSelectTeam={onSelectTeam}
          />
        ))}
      </div>

      {!sharedBasis && noted.length > 0 && (
        <details className="group/basis-footer rounded-[10px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-3 py-1.5">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-[11px] font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)]">
            <span className="inline-flex items-center gap-1.5">
              <Info size={12} className="shrink-0 text-[var(--insights-accent)]" aria-hidden="true" />
              <span>Scoring basis & comparison notes ({noted.length} functions)</span>
            </span>
            <span className="text-[11px] font-semibold text-[var(--insights-accent)] group-open/basis-footer:hidden">
              Show details
            </span>
            <span className="hidden text-[11px] font-semibold text-[var(--insights-accent)] group-open/basis-footer:inline">
              Hide details
            </span>
          </summary>
          <div className="mt-1.5 border-t border-[var(--exec-card-border)] pt-1.5">
            <BasisComparisonNote messages={noted.map((card) => card.basis_context?.message)} />
          </div>
        </details>
      )}
    </section>
  );
}
