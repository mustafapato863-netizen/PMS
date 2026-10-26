import { ArrowRight } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import type { ExecutiveFunction, ExecutiveSummary } from '../../../features/executive/types';
import { arrow, fmtScore, fmtSigned, scoreTone, toneColor } from '../../../features/executive/format';
import { functionSlug } from '../../../features/executive/functions';
import { vsLabel } from '../../../features/executive/periodLabels';
import { getGradeTone } from '../../../constants/grades';
import { GradePill, ScoreBar, ScoreText, StatLabel, ToneText } from './ExecPrimitives';
import FunctionTrendChart from './FunctionTrendChart';
import { FunctionCohorts, FunctionIcon } from './FunctionCards';
import { FUNCTION_STYLE, formatShare, heroDecision } from './execModel';

function functionHref(cardFunction: ExecutiveFunction, searchParams: URLSearchParams): string {
  const next = new URLSearchParams();
  for (const key of ['period', 'from', 'to', 'region', 'branch', 'level']) {
    const value = searchParams.get(key);
    if (value && value !== 'All' && value !== 'all') next.set(key, value);
  }
  const query = next.toString();
  return `/function-summary/${functionSlug(cardFunction)}${query ? `?${query}` : ''}`;
}

/** Corporate decision strip. Owns the "Start with" sentence so the hero does not repeat it. */
export default function StartHereBand({ summary, linkable }: { summary: ExecutiveSummary; linkable: boolean }) {
  const [searchParams] = useSearchParams();
  const decision = heroDecision(summary);
  const drag = summary.hero.story?.biggest_drag;
  if (!decision || !drag?.function) return null;
  const card = summary.functions.find((item) => item.function === drag.function) ?? null;
  const score = card?.score ?? drag.score ?? null;
  const tone = getGradeTone(score);
  const share = card?.gap_share_percent ?? drag.share_percent ?? null;
  const gap = card?.gap ?? (score === null ? null : Math.round((score - 100) * 10) / 10);
  const kpi = drag.kpi_label
    ? `${drag.kpi_label}${drag.team ? ` · ${drag.team}` : ''}`
    : drag.cause;
  const lowest = card?.lowest_team ?? null;
  const comparison = vsLabel(summary.period.previous, summary.period.range, 'vs last');
  const changeTone = scoreTone(card?.change);
  const trendColor = card ? (changeTone === 'neutral' ? FUNCTION_STYLE[card.function].color : toneColor(changeTone)) : 'transparent';

  return (
    <section
      aria-labelledby="exec-start-title"
      data-testid="exec-start-here"
      className="grid gap-[18px] rounded-[22px] border border-[var(--insights-summary-border)] bg-[var(--bg-surface)] p-[18px] shadow-[var(--exec-card-shadow)] sm:p-[22px] lg:grid-cols-[minmax(0,1.4fr)_minmax(220px,300px)]"
      style={{ borderLeftWidth: 4, borderLeftColor: tone.gauge }}
    >
      <div className="flex min-w-0 flex-col gap-[12px]">
        <div className="flex items-center gap-[10px]">
          {card && <FunctionIcon fn={card.function} size={40} />}
          <div className="min-w-0">
            <span className="text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--insights-negative)]">Start here</span>
            <h2 id="exec-start-title" className="text-[22px] font-bold leading-[1.2] tracking-[-0.03em] text-[var(--insights-heading)]">{drag.function}</h2>
          </div>
        </div>
        <p className="text-[15px] leading-[1.6] text-[var(--text-secondary)]">{decision}</p>
        {kpi && <p className="text-[13px] font-semibold leading-[1.5] text-[var(--insights-heading)]">{kpi}</p>}
        {lowest && (
          <p className="text-[13px] leading-[1.5] text-[var(--text-secondary)]">
            Lowest team · {lowest.team} at {lowest.score.toFixed(1)}%
            {lowest.score_basis === 'leader_scorecard' ? ' · Leader scorecard' : ''}
            {lowest.kpi ? ` · ${lowest.kpi}` : ''}
          </p>
        )}
      </div>
      <div className="flex flex-col justify-between gap-[12px] rounded-[16px] border border-[var(--exec-card-border)] bg-[var(--exec-tile-bg)] p-[14px]">
        <div className="flex flex-wrap items-end gap-[8px]">
          <ScoreText score={score} className="text-[36px] font-bold leading-none tracking-[-0.04em] tabular-nums">{fmtScore(score)}</ScoreText>
          <GradePill score={score} />
          {score !== null && <span className="pb-[2px] text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">People average</span>}
        </div>
        <ScoreBar score={score} color={tone.gauge} />
        {share != null && share > 0 && (
          <p className="text-[18px] font-bold leading-tight text-[var(--insights-heading)]">{formatShare(share)}% of the gap</p>
        )}
        <div className="flex flex-wrap gap-x-[16px] gap-y-[6px]">
          <div className="flex flex-col gap-[2px]">
            <StatLabel>vs 100</StatLabel>
            <ToneText tone={scoreTone(gap)} className="text-[16px] font-bold tabular-nums">{arrow(gap)} {fmtSigned(gap)}</ToneText>
          </div>
          <div className="flex flex-col gap-[2px]">
            <StatLabel>{comparison}</StatLabel>
            <ToneText tone={changeTone} className="text-[16px] font-bold tabular-nums">{arrow(card?.change)} {fmtSigned(card?.change)}</ToneText>
          </div>
        </div>
        {linkable && card && (
          <Link
            to={functionHref(card.function, searchParams)}
            aria-label={`Review ${card.function} summary`}
            className="inline-flex min-h-[44px] items-center justify-center gap-[8px] rounded-[10px] bg-[var(--insights-accent)] px-[12px] text-[13px] font-bold text-white transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent-ring)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-surface)]"
          >
            Review {card.function} <ArrowRight aria-hidden="true" className="size-[16px]" />
          </Link>
        )}
      </div>
      {card?.cohorts && (
        <div className="lg:col-span-2">
          <FunctionCohorts cohorts={card.cohorts} columns />
        </div>
      )}
      {card && (
        <div className="lg:col-span-2">
          <FunctionTrendChart color={trendColor} title={`${card.function} score`} points={card.trend} />
        </div>
      )}
    </section>
  );
}
