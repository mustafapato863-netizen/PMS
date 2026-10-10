import { ArrowRight, TrendingDown, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import { FUNCTION_STYLE } from './execModel';
import type { ExecutiveFunction, ExecutiveFunctionCard, ExecutivePeriod } from '../../../features/executive/types';
import { functionSlug } from '../../../features/executive/functions';
import { arrow, fmtScore, fmtSigned, scoreTone, toneColor } from '../../../features/executive/format';
import { getGradeTone } from '../../../constants/grades';
import { GradePill, ScoreText, StatLabel, StatusPill, ToneText } from './ExecPrimitives';
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

function FunctionCard({ card, previous, linkable }: { card: ExecutiveFunctionCard; previous: ExecutivePeriod | null; linkable: boolean }) {
  const tone = getGradeTone(card.score);
  const style = FUNCTION_STYLE[card.function];
  const changeTone = scoreTone(card.change);
  const trendColor = changeTone === 'neutral' ? style.color : toneColor(changeTone);
  const vsLabel = previous ? `vs ${previous.month.slice(0, 3)}` : 'vs last';
  return (
    <article aria-label={`${card.function} function`} className="flex min-w-0 flex-col gap-[12px] rounded-[16px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-[16px] shadow-[var(--exec-card-shadow)]">
      <div className="flex items-center gap-[10px]">
        <FunctionIcon fn={card.function} size={40} />
        <div className="min-w-0">
          <h3 className="text-[17px] font-bold leading-[1.3] tracking-[-0.025em] text-[var(--insights-heading)]">{card.function}</h3>
          <p className="mt-[2px] text-[11px] leading-[1.5] text-[var(--text-muted)]">
            {card.teams.length} {card.teams.length === 1 ? 'team' : 'teams'} · {card.employees} people{card.regions.length ? ` · ${card.regions.join(' + ')}` : ''}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-[8px]">
        <ScoreText score={card.score} className="text-[34px] tracking-[-0.045em] tabular-nums">{fmtScore(card.score)}</ScoreText>
        <GradePill score={card.score} className="!px-[10px] !py-[4px]" />
      </div>
      <div className="flex flex-wrap items-end gap-x-[16px] gap-y-[6px]">
        <div className="flex flex-col gap-[2px]">
          <StatLabel>Gap</StatLabel>
          <ToneText tone={scoreTone(card.gap)} className="text-[18px] font-bold tabular-nums">{arrow(card.gap)} {fmtSigned(card.gap)}</ToneText>
        </div>
        <div className="flex flex-col gap-[2px]">
          <StatLabel>{vsLabel}</StatLabel>
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
      <div className="mt-auto flex flex-col gap-[10px] border-t border-[var(--insights-row-border)] pt-[10px]">
        <p className="min-w-0 text-[11px] leading-[1.6] text-[var(--text-secondary)]">{card.teams.join(' · ')}</p>
        {linkable && <Link to={`/function-summary/${functionSlug(card.function)}`} aria-label={`View ${card.function} function`} className="inline-flex min-h-[44px] items-center justify-center gap-[8px] rounded-[10px] border px-[12px] py-[8px] text-[13px] font-bold transition-[filter] hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)] motion-reduce:transition-none" style={{ background: style.bg, color: style.color, borderColor: `color-mix(in srgb, ${style.color} 25%, transparent)` }}>View function <ArrowRight aria-hidden="true" className="size-[16px]" /></Link>}
      </div>
      <span className="sr-only">{tone.label}</span>
    </article>
  );
}

export default function FunctionCards({ cards, previous, linkable }: { cards: ExecutiveFunctionCard[]; previous: ExecutivePeriod | null; linkable: boolean }) {
  return (
    <section aria-labelledby="exec-functions-title" className="flex flex-col gap-[12px]">
      <div className="flex flex-wrap items-center justify-between gap-[8px]">
        <div className="flex items-center gap-[8px]">
          <h2 id="exec-functions-title" className="text-[17px] font-bold text-[var(--insights-heading)]">Functions</h2>
          <span className="rounded-full bg-[var(--exec-chip-bg)] px-[8px] py-[2px] text-[11px] font-semibold text-[var(--exec-chip-text)]">{cards.length} functions</span>
        </div>
        {linkable && <span className="text-[12px] text-[var(--text-muted)]">Click a function to open its Function Summary →</span>}
      </div>
      <BasisComparisonNote messages={cards.map((card) => card.basis_context?.message)} />
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,260px),1fr))] gap-[12px]">
        {cards.map((card) => <FunctionCard key={card.function} card={card} previous={previous} linkable={linkable} />)}
      </div>
    </section>
  );
}
