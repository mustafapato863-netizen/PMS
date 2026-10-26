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
import FunctionTrendChart from './FunctionTrendChart';
import BasisComparisonNote from '../../../features/evaluation/BasisComparisonNote';

export function FunctionIcon({ fn, size = 30 }: { fn: ExecutiveFunction; size?: number }) {
  const style = FUNCTION_STYLE[fn];
  const Icon = style.icon;
  return (
    <span
      aria-hidden="true"
      className="flex shrink-0 items-center justify-center rounded-[9px] shadow-2xs"
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
      className="group/btn inline-flex min-h-[34px] w-full items-center justify-center gap-[6px] rounded-[9px] border px-[10px] py-[6px] text-[12px] font-bold transition-all duration-200 hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)] motion-reduce:transition-none"
      style={{
        background: style.bg,
        color: style.color,
        borderColor: `color-mix(in srgb, ${style.color} 28%, transparent)`,
      }}
    >
      View function
      <ArrowRight
        aria-hidden="true"
        className="size-[13px] transition-transform duration-200 group-hover/btn:translate-x-0.5"
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
  showBasis,
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
  showBasis: boolean;
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
  const hasStatusPills =
    card.is_most_improved ||
    (card.falling_months !== null && card.falling_months >= 2) ||
    (classic && card.lowest_team && card.lowest_team.score < 85);

  return (
    <article
      aria-label={`${card.function} function`}
      className="group/fcard relative flex h-full min-w-0 flex-col gap-[7px] overflow-hidden rounded-[14px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-[12px] shadow-[var(--exec-card-shadow)] transition-all duration-200 hover:border-[var(--border-medium)]"
    >
      {/* Top Grade Accent Strip */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-[2.5px]"
        style={{ background: tone.gauge }}
      />

      {/* Card Header */}
      <div className="flex items-start justify-between gap-[8px]">
        <div className="flex min-w-0 items-center gap-[8px]">
          <FunctionIcon fn={card.function} size={30} />
          <div className="min-w-0">
            {onSelectFunction ? (
              <button
                type="button"
                className="truncate text-left text-[15px] font-bold leading-[1.25] tracking-[-0.02em] text-[var(--insights-heading)] hover:underline"
                aria-label={`Open ${card.function}`}
                onClick={() => onSelectFunction(card.function)}
              >
                {card.function}
              </button>
            ) : (
              <h3 className="truncate text-[15px] font-bold leading-[1.25] tracking-[-0.02em] text-[var(--insights-heading)]">
                {card.function}
              </h3>
            )}
            <p className="mt-[1px] truncate text-[11px] leading-[1.3] text-[var(--text-muted)]">
              {card.teams.length} {card.teams.length === 1 ? 'team' : 'teams'} · {card.employees} people
              {card.regions.length ? ` · ${card.regions.join(' + ')}` : ''}
            </p>
          </div>
        </div>
      </div>

      {markStart && card.score !== null && (
        <span className="text-[10px] font-bold uppercase tracking-[0.12em] text-[var(--insights-negative)]">
          Start here
        </span>
      )}

      {/* Primary Score + Grade + Progress Bar */}
      <div className="space-y-1.5">
        <div className="flex flex-wrap items-center justify-between gap-[6px]">
          <div className="flex flex-wrap items-end gap-[6px]">
            <ScoreText
              score={card.score}
              className="text-[24px] font-bold leading-none tracking-[-0.04em] tabular-nums"
            >
              {fmtScore(card.score)}
            </ScoreText>
            <GradePill score={card.score} className="!px-[8px] !py-[2px] !text-[11px]" />
            {card.score !== null && !classic && (
              <span className="pb-[2px] text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                People average
              </span>
            )}
          </div>
        </div>
        <ScoreBar score={card.score} color={tone.gauge} />
      </div>

      {!classic && card.gap_share_percent != null && card.gap_share_percent > 0 && (
        <p className="text-[12px] font-semibold text-[var(--insights-heading)]">
          {formatShare(card.gap_share_percent)}% of the gap
        </p>
      )}
      {!classic && card.lowest_team && (
        <p className="text-[11px] leading-[1.4] text-[var(--text-secondary)]">
          Lowest team · {card.lowest_team.team} at {card.lowest_team.score.toFixed(1)}%
          {card.lowest_team.score_basis === 'leader_scorecard' ? ' · Leader scorecard' : ''}
          {card.lowest_team.kpi ? ` · ${card.lowest_team.kpi}` : ''}
        </p>
      )}

      {showCohorts && card.cohorts && <FunctionCohorts cohorts={card.cohorts} />}

      {/* Ultra-Compact Single-Line Gap & Period Delta Strip */}
      <div className="flex items-center justify-between gap-2 rounded-[8px] border border-[var(--exec-card-border)] bg-[var(--exec-tile-bg)]/50 px-2.5 py-1">
        <div className="flex items-baseline gap-1.5">
          <StatLabel>{classic ? 'Gap' : 'vs 100'}</StatLabel>
          <ToneText tone={scoreTone(card.gap)} className="text-[13px] font-bold tabular-nums">
            {arrow(card.gap)} {fmtSigned(card.gap)}
          </ToneText>
        </div>
        <div className="flex items-baseline gap-1.5 border-l border-[var(--exec-card-border)] pl-2">
          <StatLabel>{comparison}</StatLabel>
          <ToneText tone={changeTone} className="text-[12px] font-semibold tabular-nums">
            {arrow(card.change)} {fmtSigned(card.change)}
          </ToneText>
        </div>
      </div>

      {/* Momentum & Lowest Team Status Pills */}
      {hasStatusPills && (
        <div className="flex flex-wrap items-center gap-[5px]">
          {card.is_most_improved && (
            <StatusPill tone="success" icon={TrendingUp}>
              Most improved
            </StatusPill>
          )}
          {card.falling_months !== null && card.falling_months >= 2 && (
            <StatusPill tone="danger" icon={TrendingDown}>
              Falling {card.falling_months} mo
            </StatusPill>
          )}
          {classic && card.lowest_team && card.lowest_team.score < 85 && (
            <span
              aria-hidden="true"
              className="inline-flex items-center gap-1 truncate rounded-full bg-amber-500/10 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-300"
            >
              Focus: {card.lowest_team.team} ({card.lowest_team.score.toFixed(0)}%)
            </span>
          )}
        </div>
      )}

      {/* Compact 6-Month Sparkline Chart */}
      <FunctionTrendChart color={trendColor} title={`${card.function} score`} points={card.trend} />

      {/* Bottom-Aligned Footer: Teams + Compact Basis Note + View Function CTA */}
      {showTeamButtons || showTeamDump || (linkable && !onSelectFunction) || showBasis ? (
        <div className="mt-auto flex flex-col gap-[6px] border-t border-[var(--insights-row-border)] pt-[7px]">
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
          ) : showTeamDump ? (
            <p
              className="truncate min-w-0 text-[11px] leading-[1.35] text-[var(--text-secondary)]"
              title={card.teams.join(' · ')}
            >
              {card.teams.join(' · ')}
            </p>
          ) : null}

          {showBasis && card.basis_context?.message && (
            <details className="group/basis rounded-md border border-[var(--exec-card-border)] bg-[var(--exec-tile-bg)]/50 px-2 py-1">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-1 text-[10.5px] font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)]">
                <span className="inline-flex items-center gap-1 truncate">
                  <Info size={11} className="shrink-0 text-[var(--insights-accent)]" aria-hidden="true" />
                  <span className="truncate">Basis note</span>
                </span>
                <span className="text-[10px] font-semibold text-[var(--insights-accent)] group-open/basis:hidden">
                  Show
                </span>
                <span className="hidden text-[10px] font-semibold text-[var(--insights-accent)] group-open/basis:inline">
                  Hide
                </span>
              </summary>
              <div className="mt-1 border-t border-[var(--exec-card-border)] pt-1">
                <BasisComparisonNote messages={[card.basis_context?.message]} />
              </div>
            </details>
          )}

          {linkable && !onSelectFunction && (
            <FunctionLink cardFunction={card.function} style={style} />
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
  // Default to compact single-row layout so all 6 functions sit in 1 row on desktop
  const [expandedGrid, setExpandedGrid] = useState(false);

  const noted = cards.filter((card) => card.basis_context?.message);
  const sharedBasis =
    noted.length === cards.length && new Set(noted.map((card) => card.basis_context?.message)).size === 1;

  const attentionCount = useMemo(
    () => cards.filter((c) => c.score !== null && c.score < 85).length,
    [cards],
  );
  const healthyCount = useMemo(
    () => cards.filter((c) => c.score !== null && c.score >= 85).length,
    [cards],
  );

  const displayedCards = useMemo(() => {
    let list = [...cards];
    if (filterMode === 'attention') {
      list = list.filter((c) => c.score !== null && c.score < 85);
    } else if (filterMode === 'healthy') {
      list = list.filter((c) => c.score !== null && c.score >= 85);
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
    <section aria-labelledby="exec-functions-title" className="flex flex-col gap-[10px]">
      <div className="flex flex-wrap items-center justify-between gap-[8px]">
        <div className="flex flex-wrap items-center gap-[8px]">
          <h2 id="exec-functions-title" className="text-[16px] font-bold text-[var(--insights-heading)]">
            Functions
          </h2>
          <span className="rounded-full bg-[var(--exec-chip-bg)] px-[8px] py-[2px] text-xs font-semibold text-[var(--exec-chip-text)]">
            {count ?? cards.length} functions
          </span>
          {range && <span className="text-[12px] text-[var(--text-muted)]">{coveredPeriodLabel(null, range)}</span>}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {cards.length > 2 && (
            <div className="flex flex-wrap items-center gap-1.5">
              {/* Filter Pills */}
              <div className="inline-flex items-center rounded-xl border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-0.5">
                <button
                  type="button"
                  onClick={() => setFilterMode('all')}
                  className={`rounded-lg px-2 py-0.5 text-[11px] font-semibold transition-colors ${
                    filterMode === 'all'
                      ? 'bg-[var(--exec-tile-bg)] text-[var(--insights-heading)]'
                      : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  All ({cards.length})
                </button>
                {attentionCount > 0 && (
                  <button
                    type="button"
                    onClick={() => setFilterMode('attention')}
                    className={`rounded-lg px-2 py-0.5 text-[11px] font-semibold transition-colors ${
                      filterMode === 'attention'
                        ? 'bg-rose-500/10 text-rose-600 dark:text-rose-400'
                        : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                    }`}
                  >
                    Below 85% ({attentionCount})
                  </button>
                )}
                {healthyCount > 0 && (
                  <button
                    type="button"
                    onClick={() => setFilterMode('healthy')}
                    className={`rounded-lg px-2 py-0.5 text-[11px] font-semibold transition-colors ${
                      filterMode === 'healthy'
                        ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                        : 'text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                    }`}
                  >
                    On Track ({healthyCount})
                  </button>
                )}
              </div>

              {/* Sort Pills */}
              <div className="inline-flex items-center gap-1 rounded-xl border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-1.5 py-0.5">
                <ArrowDownUp size={11} className="text-[var(--text-muted)]" aria-hidden="true" />
                {(['lowest', 'highest', 'momentum', 'default'] as const).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    onClick={() => setSortMode(mode)}
                    className={`rounded-lg px-1.5 py-0.5 text-[11px] font-semibold transition-colors ${
                      sortMode === mode
                        ? 'bg-[var(--exec-tile-bg)] text-[var(--insights-heading)]'
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
                title={expandedGrid ? 'Switch to compact single-row view' : 'Expand to 3-column grid'}
                className="inline-flex min-h-6 items-center gap-1 rounded-xl border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-2 py-0.5 text-[11px] font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--exec-tile-bg)] hover:text-[var(--insights-heading)]"
              >
                {expandedGrid ? <Rows3 size={11} aria-hidden="true" /> : <LayoutGrid size={11} aria-hidden="true" />}
                <span>{expandedGrid ? '1-Row Compact' : '3-Col Grid'}</span>
              </button>
            </div>
          )}

          {featured ? (
            <span className="text-[12px] text-[var(--text-muted)]">{note ?? 'Ranked by share of the gap'}</span>
          ) : onSelectFunction ? (
            <span className="text-[12px] text-[var(--text-muted)]">
              Choose a function or a team to review it here
            </span>
          ) : linkable ? (
            <span className="text-[12px] text-[var(--text-muted)]">
              Click a function to open its Function Summary →
            </span>
          ) : null}
        </div>
      </div>

      {sharedBasis && <BasisComparisonNote messages={noted.map((card) => card.basis_context?.message)} />}

      <div
        className={
          expandedGrid
            ? 'grid grid-cols-1 gap-[12px] md:grid-cols-2 xl:grid-cols-3'
            : 'grid grid-cols-[repeat(auto-fit,minmax(min(100%,205px),1fr))] gap-[10px]'
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
            showBasis={!sharedBasis && Boolean(card.basis_context?.message)}
            showCohorts={showCohorts}
            classic={classic}
            onSelectFunction={onSelectFunction}
            onSelectTeam={onSelectTeam}
          />
        ))}
      </div>
    </section>
  );
}
