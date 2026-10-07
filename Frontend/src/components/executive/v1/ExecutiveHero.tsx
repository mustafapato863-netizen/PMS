import { Activity, BarChart3, Calendar, ChartNoAxesColumnIncreasing, Layers, Target, TrendingDown, TrendingUp, Upload, Users, type LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { getGradeTone } from '../../../constants/grades';
import type { ExecutiveSummary } from '../../../features/executive/types';
import { arrow, fmtDate, fmtScore, fmtSigned, scoreTone, toneColor } from '../../../features/executive/format';
import { formatPeriod } from '../../../features/executive/compose';
import { Chip, GradePill, StatusPill } from './ExecPrimitives';
import ScoreTrendChart from './ScoreTrendChart';
import { heroHeadline, heroNarrative } from './execModel';

function Stat({ label, value, valueColor, sub, subColor, icon: Icon }: { label: string; value: ReactNode; valueColor: string; sub: ReactNode; subColor?: string; icon: LucideIcon }) {
  return (
    <div className="relative flex min-w-0 flex-col gap-[8px] rounded-[16px] border p-[14px]" style={{ background: `color-mix(in srgb, ${valueColor} 5%, var(--bg-surface))`, borderColor: `color-mix(in srgb, ${valueColor} 10%, var(--exec-card-border))` }}>
      <div className="flex min-h-[30px] items-start justify-between gap-[6px]">
        <span className="text-[10px] font-semibold uppercase leading-[1.5] tracking-[0.5px] text-[var(--text-muted)]">{label}</span>
        <span aria-hidden="true" className="flex size-[28px] shrink-0 items-center justify-center rounded-[9px]" style={{ background: `color-mix(in srgb, ${valueColor} 9%, transparent)`, color: valueColor }}><Icon className="size-[17px]" strokeWidth={1.8} /></span>
      </div>
      <span className="text-[clamp(24px,2.3vw,34px)] font-bold leading-[1.1] tracking-[-0.04em] tabular-nums" style={{ color: valueColor }}>{value}</span>
      <span className="text-[11px] font-medium leading-[1.5]" style={{ color: subColor ?? 'var(--text-muted)' }}>{sub}</span>
    </div>
  );
}

const EYEBROW: Record<ExecutiveSummary['scope']['view'], { label: string; icon: LucideIcon }> = {
  corporate: { label: 'Company performance', icon: Activity },
  managerial: { label: 'Team performance', icon: Users },
  function: { label: 'Function performance', icon: Layers },
};



export default function ExecutiveHero({ summary }: { summary: ExecutiveSummary }) {
  const { hero, period, trend, scope, data_status: status, meta } = summary;
  const tone = getGradeTone(hero.score);
  const eyebrow = EYEBROW[scope.view];
  const EyebrowIcon = eyebrow.icon;
  const narrative = heroNarrative(summary);
  const changeTone = scoreTone(hero.change);
  const previousLabel = period.previous ? `vs ${formatPeriod(period.previous)}` : 'vs last month';
  const comparison = hero.comparison;
  const upload = !meta.unavailable.includes('upload_meta') ? status.last_upload : null;
  const isFunction = scope.view === 'function';
  const statCount = (isFunction ? 3 : 4) + (comparison?.score != null ? 1 : 0);
  const chartTitle = scope.view === 'corporate' ? 'Company score — last 6 months' : scope.view === 'managerial' ? 'Team score — last 6 months' : `${hero.label} score — last 6 months`;

  return (
    <section aria-labelledby="exec-hero-title" className="grid gap-[24px] rounded-[22px] border border-[var(--insights-summary-border)] bg-[var(--insights-summary-bg)] p-[18px] shadow-[var(--insights-summary-shadow)] sm:p-[26px] xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      <div className="flex min-w-0 flex-col gap-[20px]">
        <div className="flex flex-wrap items-center gap-[8px]">
          <span aria-hidden="true" className="flex size-[40px] items-center justify-center rounded-[12px] bg-[var(--insights-accent-tag)]">
            <EyebrowIcon className="size-[23px] text-[var(--insights-accent)]" strokeWidth={1.8} />
          </span>
          <span className="text-[11px] font-bold uppercase tracking-[1px] text-[var(--text-muted)]">{scope.view === 'function' ? `${hero.label} function` : eyebrow.label}</span>
          <GradePill score={hero.score} className="!px-[12px] !py-[5px] !text-[12px]" />
          {scope.view === 'function' && summary.highlights.most_improved?.name === hero.label && <StatusPill tone="success" icon={TrendingUp}>Most improved</StatusPill>}
        </div>
        <h2 id="exec-hero-title" className="text-[clamp(26px,2.6vw,38px)] font-bold leading-[1.22] tracking-[-0.035em] text-[var(--insights-heading)]">{heroHeadline(summary)}</h2>
        {narrative && <p className="text-[14px] leading-[1.7] text-[var(--text-secondary)]">{narrative}</p>}
        <div className={`grid grid-cols-2 gap-[10px] ${statCount === 3 || statCount === 5 ? 'sm:grid-cols-3' : 'sm:grid-cols-4'}`}>
          <Stat icon={ChartNoAxesColumnIncreasing} label={isFunction ? 'Function score' : 'Current'} value={fmtScore(hero.score)} valueColor={tone.text} sub={tone.grade ? `${tone.grade} · ${tone.label}` : 'No grade'} subColor={tone.text} />
          {/* Function view (Figma 48:3): no separate Target tile; the gap names the target. */}
          {!isFunction && (
            <Stat icon={Target} label="Target" value={fmtScore(hero.target, 1)} valueColor="var(--insights-accent-text)" sub={scope.view === 'corporate' ? 'Company-wide' : 'Score target'} />
          )}
          <Stat icon={BarChart3} label="Gap" value={fmtSigned(hero.gap)} valueColor={toneColor(scoreTone(hero.gap))} sub={isFunction ? `vs target ${fmtScore(hero.target, 0)}` : 'score − target'} />
          <Stat
            icon={hero.change !== null && hero.change < 0 ? TrendingDown : TrendingUp}
            label={previousLabel}
            value={fmtSigned(hero.change)}
            valueColor={toneColor(changeTone)}
            sub={hero.previous_score !== null ? `${arrow(hero.change)} ${fmtScore(hero.previous_score)} → ${fmtScore(hero.score)}` : 'No previous month'}
            subColor={toneColor(changeTone)}
          />
          {comparison && comparison.score !== null && (
              <Stat icon={Users}
                label={isFunction ? 'vs Company' : `vs ${comparison.label}`}
                value={fmtSigned(comparison.difference)}
                valueColor={toneColor(scoreTone(comparison.difference))}
                sub={`${comparison.label}: ${fmtScore(comparison.score)}`}
              />
          )}
        </div>
        <div className="mt-auto flex flex-wrap gap-[8px] border-t border-[var(--exec-card-border)] pt-[16px] [&>span]:px-[12px] [&>span]:py-[8px] [&>span]:text-[12px] [&_svg]:size-[15px]">
          <Chip icon={Users}>{hero.employees.toLocaleString('en-US')} employees</Chip>
          {scope.view === 'corporate'
            ? <Chip icon={Layers}>{hero.functions_count} functions · {hero.teams_count} teams</Chip>
            : scope.view === 'function' ? <Chip icon={Layers}>{hero.teams_count} teams</Chip> : null}
          {upload
            ? <Chip icon={Upload}>Data uploaded {fmtDate(upload.uploaded_at)}</Chip>
            : <Chip icon={Calendar}>{formatPeriod(period.effective)} data</Chip>}
        </div>
      </div>
      <ScoreTrendChart points={trend} title={chartTitle} comparisonLabel={comparison?.label ?? null} />
    </section>
  );
}
