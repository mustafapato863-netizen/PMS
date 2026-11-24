import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import {
  Activity,
  AlertTriangle,
  BarChart3,
  Calendar,
  ChartNoAxesColumnIncreasing,
  CheckCircle2,
  HelpCircle,
  Layers,
  TrendingDown,
  TrendingUp,
  Upload,
  Users,
  X,
  type LucideIcon,
} from 'lucide-react';
import { getGradeTone } from '../../../constants/grades';
import type { ExecutiveSummary } from '../../../features/executive/types';
import { arrow, fmtDate, fmtScore, fmtSigned, scoreTone, toneColor } from '../../../features/executive/format';
import { formatPeriod } from '../../../features/executive/compose';
import { comparisonName, coveredPeriodLabel } from '../../../features/executive/periodLabels';
import { Chip, GradePill, StatusPill } from './ExecPrimitives';
import { gradeGradientVar } from './gradeGradient';
import ScoreTrendChart from './ScoreTrendChart';
import { heroHeadline, heroNarrative, heroStatusLabel } from './execModel';

function Stat({ label, value, valueColor, sub, subColor, icon: Icon, barScore, barGradient }: { label: string; value: ReactNode; valueColor: string; sub: ReactNode; subColor?: string; icon: LucideIcon; barScore?: number | null; barGradient?: string }) {
  return (
    <div
      className="pms-glass-stage relative flex min-w-0 flex-col gap-[8px] overflow-hidden rounded-[16px] p-[15px] transition-shadow hover:shadow-md"
      style={{
        backgroundImage: `radial-gradient(circle at 100% 0%, color-mix(in srgb, ${valueColor} 10%, transparent) 0%, transparent 65%), var(--pms-glass-stage-bg)`,
        borderColor: `color-mix(in srgb, ${valueColor} 16%, var(--pms-glass-card-border))`,
      }}
    >
      <div className="flex min-h-[28px] items-start justify-between gap-[6px]">
        <span className="text-xs font-semibold leading-[1.4] text-[var(--text-muted)]">{label}</span>
        <span aria-hidden="true" className="flex size-[30px] shrink-0 items-center justify-center rounded-[10px] border border-white/60 dark:border-white/10" style={{ background: `color-mix(in srgb, ${valueColor} 10%, transparent)`, color: valueColor }}><Icon className="size-[16px]" strokeWidth={1.85} /></span>
      </div>
      <span className="text-display-hero font-bold leading-[1.1] tracking-[-0.04em] tabular-nums" style={{ color: valueColor }}>{value}</span>
      {barScore != null && (
        <div aria-hidden="true" className="h-[6px] w-full overflow-hidden rounded-full bg-[var(--insights-track)]">
          <div className="h-full rounded-full" style={{ width: `${Math.max(4, Math.min(100, barScore))}%`, background: barGradient ?? valueColor }} />
        </div>
      )}
      <span className="text-xs font-medium leading-[1.45]" style={{ color: subColor ?? 'var(--text-muted)' }}>{sub}</span>
    </div>
  );
}

const EYEBROW: Record<ExecutiveSummary['scope']['view'], { label: string; icon: LucideIcon }> = {
  corporate: { label: 'Company performance', icon: Activity },
  managerial: { label: 'Team performance', icon: Users },
  function: { label: 'Function performance', icon: Layers },
};

export default function ExecutiveHero({ summary, includeDecision = true }: { summary: ExecutiveSummary; includeDecision?: boolean }) {
  const { hero, period, trend, scope, data_status: status, meta } = summary;
  const [isHelpOpen, setIsHelpOpen] = useState(false);
  const helpRef = useRef<HTMLDivElement>(null);
  const helpBtnRef = useRef<HTMLButtonElement>(null);
  const helpDialogId = useId();

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

  const tone = getGradeTone(hero.score);
  const eyebrow = EYEBROW[scope.view];
  const EyebrowIcon = eyebrow.icon;
  const narrative = heroNarrative(summary, { includeDecision });
  const statusLabel = hero.score === null ? null : heroStatusLabel(hero.score, hero.gap);
  const statusTone = statusLabel === 'On target' ? 'success' : statusLabel === 'Below threshold' ? 'danger' : 'warning';
  const changeTone = scoreTone(hero.change);
  const previousLabel = period.range
    ? (period.previous ? `vs ${comparisonName(period.previous, period.range)}` : 'vs no earlier range')
    : (period.previous ? `vs ${formatPeriod(period.previous)}` : 'vs last month');
  const comparison = hero.comparison;
  const upload = !meta.unavailable.includes('upload_meta') ? status.last_upload : null;
  const isFunction = scope.view === 'function';
  const statCount = 3 + (comparison?.score != null ? 1 : 0);
  const chartTitle = scope.view === 'corporate' ? 'Company score — last 6 months' : scope.view === 'managerial' ? 'Team score — last 6 months' : `${hero.label} score — last 6 months`;

  const scoredTeams = summary.teams.filter((t) => t.score !== null);
  const atRiskTeamsCount = scoredTeams.filter((t) => (t.score ?? 0) < 90).length;
  const healthyTeamsCount = scoredTeams.filter((t) => (t.score ?? 0) >= 90).length;

  return (
    <section aria-labelledby="exec-hero-title" className="pms-glass-surface grid gap-[24px] rounded-[22px] p-[18px] sm:p-[26px] xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      <div className="flex min-w-0 flex-col gap-[20px]">
        <div className="flex flex-wrap items-center justify-between gap-[8px]">
          <div className="flex flex-wrap items-center gap-[8px]">
            <span aria-hidden="true" className="flex size-[40px] items-center justify-center rounded-[12px] bg-[var(--insights-accent-tag)]">
              <EyebrowIcon className="size-[23px] text-[var(--insights-accent)]" strokeWidth={1.8} />
            </span>
            <span className="text-xs font-semibold text-[var(--text-muted)]">{scope.view === 'function' ? `${hero.label} function` : eyebrow.label}</span>
            <GradePill score={hero.score} className="!px-[12px] !py-[5px] !text-[12px]" />
            {statusLabel && (
              <StatusPill tone={statusTone} icon={statusTone === 'success' ? CheckCircle2 : AlertTriangle}>{statusLabel}</StatusPill>
            )}
            {scope.view === 'function' && summary.highlights.most_improved?.name === hero.label && <StatusPill tone="success" icon={TrendingUp}>Most improved</StatusPill>}
          </div>

          {/* Quick Help & Executive Decision Guide */}
          <div className="relative">
            <button
              ref={helpBtnRef}
              type="button"
              onClick={() => setIsHelpOpen((prev) => !prev)}
              aria-expanded={isHelpOpen}
              aria-controls={isHelpOpen ? helpDialogId : undefined}
              aria-haspopup="dialog"
              aria-label="Quick help and executive guide"
              className="inline-flex items-center gap-[6px] rounded-[10px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-[10px] py-[6px] text-xs font-semibold text-[var(--text-secondary)] transition hover:border-[var(--insights-accent-border)] hover:text-[var(--insights-heading)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)]"
            >
              <HelpCircle className="size-[14px] text-[var(--insights-accent)]" aria-hidden="true" />
              <span>Quick Help</span>
            </button>

            {isHelpOpen && (
              <div
                ref={helpRef}
                id={helpDialogId}
                role="dialog"
                aria-label="Quick help and executive guide"
                className="absolute right-0 top-full z-40 mt-[8px] w-[min(340px,calc(100vw-2rem))] max-w-[calc(100vw-2rem)] rounded-[14px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-[16px] text-left shadow-xl sm:w-[min(390px,calc(100vw-2rem))]"
              >
                <div className="flex items-center justify-between border-b border-[var(--exec-card-border)] pb-[10px]">
                  <span className="flex items-center gap-[6px] text-[14px] font-bold text-[var(--insights-heading)]">
                    <HelpCircle className="size-[16px] text-[var(--insights-accent)]" aria-hidden="true" />
                    Executive Summary Guide
                  </span>
                  <button
                    type="button"
                    onClick={() => setIsHelpOpen(false)}
                    aria-label="Close executive guide"
                    className="min-h-[44px] min-w-[44px] rounded-[6px] p-[10px] text-[var(--text-muted)] hover:bg-[var(--exec-chip-bg)] hover:text-[var(--text-primary)]"
                  >
                    <X className="size-[15px]" aria-hidden="true" />
                  </button>
                </div>

                <div className="mt-[12px] flex flex-col gap-[12px] text-xs leading-relaxed text-[var(--text-secondary)]">
                  <div>
                    <strong className="block font-bold text-[var(--insights-heading)]">
                      1. What is happening?
                    </strong>
                    <p className="mt-[4px]">
                      The company number is the average of employee scores. Each person counts once. Each person's score is their weighted KPIs, capped at 100%. A leader scorecard is labeled when a team row uses one.
                    </p>
                    <div className="mt-[6px] grid grid-cols-2 gap-[4px] rounded-[8px] bg-[var(--exec-tile-bg)] p-[8px] text-xs">
                      <span><strong>Grade A:</strong> 95% – 100%</span>
                      <span><strong>Grade B:</strong> 90% – 94.9%</span>
                      <span><strong>Grade C:</strong> 80% – 89.9%</span>
                      <span><strong>Grade D:</strong> 70% – 79.9%</span>
                      <span className="col-span-2"><strong>Grade E:</strong> Below 70% (Critical intervention)</span>
                    </div>
                  </div>

                  <div>
                    <strong className="block font-bold text-[var(--insights-heading)]">
                      2. Why does it matter?
                    </strong>
                    <p className="mt-[4px]">
                      <strong>Gap</strong> on the headline is the score minus 100. A score of 90% or more is still short of that target when the gap is negative. Each function card shows that score, its gap, the change since last month, and the six-month trend. Regions are ranked by their share of the gap: missing points times people. Teams at risk are ranked from the worst score first. A team under <strong>90%</strong> is listed, with the KPI that missed.
                    </p>
                  </div>

                  <div>
                    <strong className="block font-bold text-[var(--insights-heading)]">
                      3. What action should you take?
                    </strong>
                    <ul className="mt-[4px] list-disc space-y-[3px] pl-[16px] text-xs">
                      <li>Open a function card to see its summary. Start with the lowest score.</li>
                      <li>Red drivers are weight × gap to target. Green drivers are the change since last month.</li>
                      <li>Use <em>Teams at risk</em>, starting with the lowest-scoring team, then confirm a corrective action.</li>
                    </ul>
                  </div>
                </div>

                <div className="mt-[12px] border-t border-[var(--exec-card-border)] pt-[10px] text-right">
                  <button
                    type="button"
                    onClick={() => setIsHelpOpen(false)}
                    className="rounded-[8px] bg-[var(--insights-accent)] px-[12px] py-[6px] text-xs font-semibold text-white transition hover:opacity-90"
                  >
                    Got it
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        <h2 id="exec-hero-title" className="text-[clamp(22px,2vw,28px)] font-bold leading-[1.22] tracking-[-0.035em] text-[var(--insights-heading)]">{heroHeadline(summary)}</h2>
        {narrative && <p className="text-[14px] leading-[1.7] text-[var(--text-secondary)]">{narrative}</p>}
        <div className={`grid grid-cols-2 gap-[10px] ${statCount === 3 || statCount === 5 ? 'sm:grid-cols-3' : 'sm:grid-cols-4'}`}>
          <Stat icon={ChartNoAxesColumnIncreasing} label={hero.score_basis === 'leader_scorecard' ? 'Leader scorecard' : hero.score_basis === 'team_scorecard' ? 'Team score' : 'People average'} value={fmtScore(hero.score)} valueColor={tone.text} sub={tone.grade ? `${tone.grade} · ${tone.label}` : 'No grade'} subColor={tone.text} barScore={hero.score} barGradient={gradeGradientVar(hero.score)} />
          <Stat icon={BarChart3} label="Gap" value={fmtSigned(hero.gap)} valueColor={toneColor(scoreTone(hero.gap))} sub={`vs target ${fmtScore(hero.target, 0)}`} barScore={hero.score} barGradient={hero.gap !== null && hero.gap < 0 ? 'var(--pms-grad-grade-e)' : 'var(--pms-grad-grade-a)'} />
          <Stat
            icon={hero.change !== null && hero.change < 0 ? TrendingDown : TrendingUp}
            label={previousLabel}
            value={fmtSigned(hero.change)}
            valueColor={toneColor(changeTone)}
            sub={hero.previous_score !== null ? `${arrow(hero.change)} ${fmtScore(hero.previous_score)} → ${fmtScore(hero.score)}` : (period.range ? 'No earlier range to compare' : 'No previous month')}
            subColor={toneColor(changeTone)}
            barScore={hero.change !== null ? Math.min(100, Math.max(18, 50 + hero.change * 5)) : null}
            barGradient={changeTone === 'bad' ? 'var(--pms-grad-grade-e)' : changeTone === 'good' ? 'var(--pms-grad-grade-a)' : 'var(--pms-grad-accent)'}
          />
          {comparison && comparison.score !== null && (
              <Stat icon={Users}
                label={isFunction ? 'vs Company' : `vs ${comparison.label}`}
                value={fmtSigned(comparison.difference)}
                valueColor={toneColor(scoreTone(comparison.difference))}
                sub={`${comparison.label}: ${fmtScore(comparison.score)}`}
                barScore={comparison.score}
                barGradient={scoreTone(comparison.difference) === 'bad' ? 'var(--pms-grad-grade-d)' : 'var(--pms-grad-grade-a)'}
              />
          )}
        </div>
        <div className="mt-auto flex flex-wrap gap-[8px] border-t border-[var(--exec-card-border)] pt-[16px] [&>span]:px-[12px] [&>span]:py-[8px] [&>span]:text-[12px] [&_svg]:size-[15px]">
          <Chip icon={Users}>{hero.employees.toLocaleString('en-US')} employees</Chip>
          {scope.view === 'corporate'
            ? <Chip icon={Layers}>{hero.functions_count} functions · {hero.teams_count} teams</Chip>
            : scope.view === 'function' ? <Chip icon={Layers}>{hero.teams_count} teams</Chip> : null}
          {scope.view !== 'managerial' && scoredTeams.length > 0 && (
            <Chip icon={CheckCircle2}>
              {healthyTeamsCount} of {scoredTeams.length} teams ≥90%
            </Chip>
          )}
          {scope.view !== 'managerial' && atRiskTeamsCount > 0 && (
            <Chip icon={AlertTriangle}>
              {atRiskTeamsCount} {atRiskTeamsCount === 1 ? 'team' : 'teams'} at risk (&lt;90%)
            </Chip>
          )}
          {upload
            ? <Chip icon={Upload}>Data uploaded {fmtDate(upload.uploaded_at)}</Chip>
            : <Chip icon={Calendar}>{coveredPeriodLabel(period.effective, period.range)} data</Chip>}
        </div>
      </div>
      <ScoreTrendChart points={trend} title={chartTitle} comparisonLabel={comparison?.label ?? null} />
    </section>
  );
}
