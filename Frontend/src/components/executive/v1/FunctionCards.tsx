import { TrendingDown, TrendingUp } from 'lucide-react';
import { FUNCTION_STYLE } from './execModel';
import type { ExecutiveFunction, ExecutiveFunctionCard, ExecutivePeriod } from '../../../features/executive/types';
import { functionSlug } from '../../../features/executive/functions';
import { arrow, fmtScore, fmtSigned, scoreTone } from '../../../features/executive/format';
import { getGradeTone } from '../../../constants/grades';
import { GradePill, ScoreText, SoftLink, Sparkline, StatLabel, StatusPill, ToneText } from './ExecPrimitives';


export function FunctionIcon({ fn, size = 32 }: { fn: ExecutiveFunction; size?: number }) {
  const style = FUNCTION_STYLE[fn];
  const Icon = style.icon;
  return (
    <span aria-hidden="true" className="flex shrink-0 items-center justify-center rounded-[8px]" style={{ background: style.bg, width: size, height: size }}>
      <Icon className="size-[16px]" style={{ color: style.color }} strokeWidth={1.75} />
    </span>
  );
}

function FunctionCard({ card, previous, linkable }: { card: ExecutiveFunctionCard; previous: ExecutivePeriod | null; linkable: boolean }) {
  const tone = getGradeTone(card.score);
  const changeTone = scoreTone(card.change);
  const vsLabel = previous ? `vs ${previous.month.slice(0, 3)}` : 'vs last';
  return (
    <article aria-label={`${card.function} function`} className="flex min-w-0 flex-col gap-[12px] rounded-[12px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-[20px] py-[18px] shadow-[var(--exec-card-shadow)]">
      <div className="flex items-center gap-[10px]">
        <FunctionIcon fn={card.function} />
        <div className="min-w-0">
          <h3 className="truncate text-[15px] font-bold text-[var(--insights-heading)]">{card.function}</h3>
          <p className="truncate text-[11px] text-[var(--text-muted)]">
            {card.teams.length} {card.teams.length === 1 ? 'team' : 'teams'} · {card.employees} people{card.regions.length ? ` · ${card.regions.join(' + ')}` : ''}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-[8px]">
        <ScoreText score={card.score} className="text-[28px]">{fmtScore(card.score)}</ScoreText>
        <GradePill score={card.score} />
        {card.is_most_improved && <StatusPill tone="success" icon={TrendingUp}>Most improved</StatusPill>}
      </div>
      <div className="flex flex-wrap items-end gap-x-[16px] gap-y-[6px]">
        <div className="flex flex-col gap-[2px]">
          <StatLabel>Gap</StatLabel>
          <ToneText tone={card.gap !== null && card.gap < 0 ? 'bad' : 'good'}>{arrow(card.gap)} {fmtSigned(card.gap)}</ToneText>
        </div>
        <div className="flex flex-col gap-[2px]">
          <StatLabel>{vsLabel}</StatLabel>
          <ToneText tone={changeTone}>{arrow(card.change)} {fmtSigned(card.change)}</ToneText>
        </div>
        {card.falling_months !== null && card.falling_months >= 2 && (
          <StatusPill tone="danger" icon={TrendingDown}>Falling {card.falling_months} mo</StatusPill>
        )}
      </div>
      <Sparkline values={card.trend.map((point) => point.score)} label={`${card.function} 6-month trend`} />
      <div className="h-px w-full bg-[var(--insights-row-border)]" />
      <div className="flex items-end justify-between gap-[8px]">
        <p className="min-w-0 text-[11px] leading-[1.4] text-[var(--text-muted)]">{card.teams.join(' · ')}</p>
        {linkable && <SoftLink to={`/function-summary/${functionSlug(card.function)}`} ariaLabel={`View ${card.function} function`}>View function</SoftLink>}
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
      <div className="grid gap-[16px] md:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => <FunctionCard key={card.function} card={card} previous={previous} linkable={linkable} />)}
      </div>
    </section>
  );
}
