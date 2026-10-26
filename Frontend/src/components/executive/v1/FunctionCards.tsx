import { ArrowRight, TrendingDown, TrendingUp } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import { FUNCTION_STYLE, formatShare } from './execModel';
import type { ExecutiveFunction, ExecutiveFunctionCard, ExecutiveFunctionCohort, ExecutivePeriod, ExecutiveRangeBlock } from '../../../features/executive/types';
import { coveredPeriodLabel, vsLabel } from '../../../features/executive/periodLabels';
import { functionSlug } from '../../../features/executive/functions';
import { arrow, fmtScore, fmtSigned, scoreTone, toneColor } from '../../../features/executive/format';
import { getGradeTone } from '../../../constants/grades';
import { GradePill, ScoreBar, ScoreText, StatLabel, StatusPill, ToneText } from './ExecPrimitives';
import FunctionTrendChart from './FunctionTrendChart';
import BasisComparisonNote from '../../../features/evaluation/BasisComparisonNote';


export function FunctionIcon({ fn, size = 32 }: { fn: ExecutiveFunction; size?: number }) {
  const style = FUNCTION_STYLE[fn];
  const Icon = style.icon;
  return (
    <span aria-hidden="true" className="flex shrink-0 items-center justify-center rounded-[8px]" style={{ background: style.bg, width: size, height: size }}>
      <Icon style={{ color: style.color, width: size * 0.52, height: size * 0.52 }} strokeWidth={1.75} />
    </span>
  );
}

function FunctionLink({ cardFunction, style }: { cardFunction: ExecutiveFunction; style: (typeof FUNCTION_STYLE)[ExecutiveFunction] }) {
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
      className="inline-flex min-h-[44px] w-full items-center justify-center gap-[8px] rounded-[10px] border px-[12px] py-[8px] text-[13px] font-bold transition-[filter] hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)] motion-reduce:transition-none"
      style={{ background: style.bg, color: style.color, borderColor: `color-mix(in srgb, ${style.color} 25%, transparent)` }}
    >
      View function <ArrowRight aria-hidden="true" className="size-[16px]" />
    </Link>
  );
}

function CohortTile({ label, cohort }: { label: string; cohort: ExecutiveFunctionCohort }) {
  const tone = getGradeTone(cohort.score);
  const names = cohort.teams.slice(0, 3).join(' · ');
  const extra = cohort.teams.length > 3 ? ` · +${cohort.teams.length - 3}` : '';
  return (
    <div role="group" aria-label={label} className="flex min-w-0 flex-col gap-[6px] rounded-[12px] border border-[var(--exec-card-border)] bg-[var(--exec-tile-bg)] p-[10px]">
      <span className="text-[11px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)]">{label}</span>
      <div className="flex flex-wrap items-end gap-[6px]">
        <ScoreText score={cohort.score} className="text-[22px] font-bold leading-none tracking-[-0.03em] tabular-nums">{fmtScore(cohort.score)}</ScoreText>
        <GradePill score={cohort.score} />
      </div>
      <ScoreBar score={cohort.score} color={tone.gauge} />
      <p className="text-xs leading-[1.5] text-[var(--text-secondary)]">
        {cohort.employees} {cohort.employees === 1 ? 'person' : 'people'}{names ? ` · ${names}${extra}` : ''}
      </p>
      <ToneText tone={scoreTone(cohort.gap)} className="text-[13px] font-semibold tabular-nums">{arrow(cohort.gap)} {fmtSigned(cohort.gap)} vs 100</ToneText>
    </div>
  );
}

export function FunctionCohorts({ cohorts, columns = false }: { cohorts: NonNullable<ExecutiveFunctionCard['cohorts']>; columns?: boolean }) {
  return (
    <div data-testid="function-cohorts" className={`grid gap-[8px] ${columns ? 'sm:grid-cols-2' : ''}`}>
      <CohortTile label="Employees" cohort={cohorts.employees} />
      <CohortTile label="Supportive positions" cohort={cohorts.support} />
    </div>
  );
}

function FunctionCard({ card, previous, range, linkable, markStart, featured, showBasis, showCohorts, classic, onSelectFunction, onSelectTeam }: {
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
  return (
    <article
      aria-label={`${card.function} function`}
      className="flex min-w-0 flex-col gap-[12px] rounded-[16px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-[16px] shadow-[var(--exec-card-shadow)]"
    >
      <div className="flex items-center gap-[10px]">
        <FunctionIcon fn={card.function} size={40} />
        <div className="min-w-0">
          {onSelectFunction ? (
            <button type="button" className="text-left text-[17px] font-bold leading-[1.3] tracking-[-0.025em] text-[var(--insights-heading)] hover:underline" aria-label={`Open ${card.function}`} onClick={() => onSelectFunction(card.function)}>{card.function}</button>
          ) : (
            <h3 className="text-[17px] font-bold leading-[1.3] tracking-[-0.025em] text-[var(--insights-heading)]">{card.function}</h3>
          )}
          <p className="mt-[2px] text-xs leading-[1.5] text-[var(--text-muted)]">
            {card.teams.length} {card.teams.length === 1 ? 'team' : 'teams'} · {card.employees} people{card.regions.length ? ` · ${card.regions.join(' + ')}` : ''}
          </p>
        </div>
      </div>
      {markStart && card.score !== null && (
        <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--insights-negative)]">Start here</span>
      )}
      <div className="flex flex-wrap items-end gap-[8px]">
        <ScoreText score={card.score} className="text-display-tile tracking-[-0.045em] tabular-nums">{fmtScore(card.score)}</ScoreText>
        <GradePill score={card.score} className="!px-[10px] !py-[4px]" />
        {card.score !== null && !classic && <span className="pb-[4px] text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">People average</span>}
      </div>
      {featured && <ScoreBar score={card.score} color={tone.gauge} />}
      {!classic && card.gap_share_percent != null && card.gap_share_percent > 0 && (
        <p className="text-[13px] font-semibold text-[var(--insights-heading)]">{formatShare(card.gap_share_percent)}% of the gap</p>
      )}
      {!classic && card.lowest_team && (
        <p className="text-xs leading-[1.5] text-[var(--text-secondary)]">
          Lowest team · {card.lowest_team.team} at {card.lowest_team.score.toFixed(1)}%
          {card.lowest_team.score_basis === 'leader_scorecard' ? ' · Leader scorecard' : ''}
          {card.lowest_team.kpi ? ` · ${card.lowest_team.kpi}` : ''}
        </p>
      )}
      {showCohorts && card.cohorts && <FunctionCohorts cohorts={card.cohorts} />}
      <div className="flex flex-wrap items-end gap-x-[16px] gap-y-[6px]">
        <div className="flex flex-col gap-[2px]">
          <StatLabel>{classic ? 'Gap' : 'vs 100'}</StatLabel>
          <ToneText tone={scoreTone(card.gap)} className="text-[18px] font-bold tabular-nums">{arrow(card.gap)} {fmtSigned(card.gap)}</ToneText>
        </div>
        <div className="flex flex-col gap-[2px]">
          <StatLabel>{comparison}</StatLabel>
          <ToneText tone={changeTone} className="text-[14px] font-semibold tabular-nums">{arrow(card.change)} {fmtSigned(card.change)}</ToneText>
        </div>
      </div>
      <div className="flex min-h-[18px] flex-wrap items-center gap-[6px]">
        {card.is_most_improved && <StatusPill tone="success" icon={TrendingUp}>Most improved</StatusPill>}
        {card.falling_months !== null && card.falling_months >= 2 && (
          <StatusPill tone="danger" icon={TrendingDown}>Falling {card.falling_months} mo</StatusPill>
        )}
      </div>
      <FunctionTrendChart color={trendColor} title={`${card.function} score`} points={card.trend} />
      {showTeamButtons || showTeamDump || (linkable && !onSelectFunction) || showBasis ? (
        <div className="mt-auto flex flex-col gap-[10px] border-t border-[var(--insights-row-border)] pt-[10px]">
          {showTeamButtons && onSelectTeam ? (
            <div className="flex flex-wrap gap-[6px]">
              {card.teams.map((team) => (
                <button key={team} type="button" className="rounded-full border border-[var(--exec-card-border)] bg-[var(--exec-tile-bg)] px-[8px] py-[3px] text-xs font-semibold text-[var(--insights-heading)] hover:underline" onClick={() => onSelectTeam(team, card.function)}>{team}</button>
              ))}
            </div>
          ) : showTeamDump ? <p className="min-w-0 text-xs leading-[1.6] text-[var(--text-secondary)]">{card.teams.join(' · ')}</p> : null}
          {linkable && !onSelectFunction && <FunctionLink cardFunction={card.function} style={style} />}
          {showBasis && <BasisComparisonNote messages={[card.basis_context?.message]} />}
        </div>
      ) : null}
      <span className="sr-only">{tone.label}</span>
    </article>
  );
}

export default function FunctionCards({ cards, previous, range = null, linkable, featured = false, showCohorts = false, classic = false, note = null, count, onSelectFunction, onSelectTeam }: {
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
  const noted = cards.filter((card) => card.basis_context?.message);
  const sharedBasis = noted.length === cards.length && new Set(noted.map((card) => card.basis_context?.message)).size === 1;
  return (
    <section aria-labelledby="exec-functions-title" className="flex flex-col gap-[12px]">
      <div className="flex flex-wrap items-center justify-between gap-[8px]">
        <div className="flex items-center gap-[8px]">
          <h2 id="exec-functions-title" className="text-[17px] font-bold text-[var(--insights-heading)]">Functions</h2>
          <span className="rounded-full bg-[var(--exec-chip-bg)] px-[8px] py-[2px] text-xs font-semibold text-[var(--exec-chip-text)]">{count ?? cards.length} functions</span>
          {range && <span className="text-[12px] text-[var(--text-muted)]">{coveredPeriodLabel(null, range)}</span>}
        </div>
        {featured
          ? <span className="text-[12px] text-[var(--text-muted)]">{note ?? 'Ranked by share of the gap'}</span>
          : onSelectFunction ? <span className="text-[12px] text-[var(--text-muted)]">Choose a function or a team to review it here</span> : linkable ? <span className="text-[12px] text-[var(--text-muted)]">Click a function to open its Function Summary →</span> : null}
      </div>
      {sharedBasis && <BasisComparisonNote messages={noted.map((card) => card.basis_context?.message)} />}
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,260px),1fr))] gap-[12px]">
        {cards.map((card, index) => (
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
