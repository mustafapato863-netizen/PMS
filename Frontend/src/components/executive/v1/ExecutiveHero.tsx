import { useEffect, useId, useRef, useState, type ReactNode } from 'react';
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  BarChart3,
  Calendar,
  ChartNoAxesColumnIncreasing,
  CheckCircle2,
  HelpCircle,
  Layers,
  Sparkles,
  Target,
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

function TopKpiCard({
  label,
  value,
  inlineBadge,
  inlineBadgeColor,
  valueColor,
  tintColor,
  sub,
  subColor,
  icon: Icon,
  barScore,
  barGradient,
}: {
  label: string;
  value: ReactNode;
  inlineBadge?: ReactNode;
  inlineBadgeColor?: string;
  valueColor: string;
  tintColor?: string;
  sub: ReactNode;
  subColor?: string;
  icon: LucideIcon;
  barScore?: number | null;
  barGradient?: string;
}) {
  const glow = tintColor ?? valueColor;
  return (
    <div
      className="pms-glass-surface pms-glass-surface--interactive relative flex min-w-0 flex-col justify-between gap-[10px] overflow-hidden rounded-[18px] p-[18px]"
      style={{
        backgroundImage: `radial-gradient(circle at 92% 10%, color-mix(in srgb, ${glow} 13%, transparent) 0%, transparent 66%), var(--pms-glass-card-bg)`,
        borderColor: `color-mix(in srgb, ${glow} 18%, var(--pms-glass-card-border))`,
      }}
    >
      <div className="flex items-center justify-between gap-[8px]">
        <span className="text-[12.5px] font-semibold text-[var(--text-secondary)]">{label}</span>
        <span
          aria-hidden="true"
          className="flex size-[30px] shrink-0 items-center justify-center rounded-[10px] border border-white/60 dark:border-white/10"
          style={{
            background: `color-mix(in srgb, ${glow} 12%, transparent)`,
            color: glow,
          }}
        >
          <Icon className="size-[15px]" strokeWidth={2} />
        </span>
      </div>

      <div className="flex flex-wrap items-baseline gap-x-[10px] gap-y-[2px]">
        <span
          className="text-[30px] font-extrabold leading-[1.08] tracking-[-0.035em] tabular-nums"
          style={{ color: valueColor }}
        >
          {value}
        </span>
        {inlineBadge && (
          <span
            className="text-[12px] font-bold leading-snug"
            style={{ color: inlineBadgeColor ?? valueColor }}
          >
            {inlineBadge}
          </span>
        )}
      </div>

      {barScore != null && (
        <div aria-hidden="true" className="h-[6px] w-full overflow-hidden rounded-full bg-[var(--insights-track)]">
          <div
            className="h-full rounded-full transition-[width] duration-500"
            style={{ width: `${Math.max(5, Math.min(100, barScore))}%`, background: barGradient ?? valueColor }}
          />
        </div>
      )}

      <span className="truncate text-[12px] font-medium leading-[1.4]" style={{ color: subColor ?? 'var(--text-muted)' }}>
        {sub}
      </span>
    </div>
  );
}

const EYEBROW: Record<ExecutiveSummary['scope']['view'], { label: string; icon: LucideIcon }> = {
  corporate: { label: 'Executive Takeaway', icon: Activity },
  managerial: { label: 'Team Performance Brief', icon: Users },
  function: { label: 'Function Performance Brief', icon: Layers },
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
    ? (period.previous ? `vs ${comparisonName(period.previous, period.range)}` : 'vs earlier range')
    : (period.previous ? `vs ${formatPeriod(period.previous)}` : 'vs last month');
  const comparison = hero.comparison;
  const upload = !meta.unavailable.includes('upload_meta') ? status.last_upload : null;
  const isFunction = scope.view === 'function';
  const chartTitle = scope.view === 'corporate'
    ? 'Company Score Trend'
    : scope.view === 'managerial'
      ? 'Team Score Trend'
      : `${hero.label} vs Company Average`;
  const chartSubtitle = scope.view === 'function' && comparison?.score != null
    ? `6-month trajectory (${fmtScore(hero.score)}) vs ${comparison.label} (${fmtScore(comparison.score)})`
    : '6-month trajectory against 100% target and 90% healthy threshold';

  const scoredTeams = summary.teams.filter((t) => t.score !== null);
  const atRiskTeamsCount = scoredTeams.filter((t) => (t.score ?? 0) < 90).length;
  const healthyTeamsCount = scoredTeams.filter((t) => (t.score ?? 0) >= 90).length;
  const healthyRatio = scoredTeams.length > 0 ? (healthyTeamsCount / scoredTeams.length) * 100 : 0;

  // Build Figma's 3 structured takeaway insights from real summary data
  const sortedFunctions = [...summary.functions]
    .filter((f) => f.score !== null)
    .sort((a, b) => (a.score ?? 999) - (b.score ?? 999));
  const lowestFn = sortedFunctions[0] ?? null;
  const secondLowestFn = sortedFunctions[1] ?? null;
  const sortedTeams = [...scoredTeams].sort((a, b) => (a.score ?? 999) - (b.score ?? 999));
  const lowestTeam = sortedTeams[0] ?? null;
  const topImprovedFn = [...summary.functions]
    .filter((f) => f.change !== null && f.change > 0)
    .sort((a, b) => (b.change ?? -999) - (a.change ?? -999))[0] ?? null;
  const highestTeam = sortedTeams.length > 0 ? sortedTeams[sortedTeams.length - 1] : null;
  const topNegDrivers = summary.drivers.negative.slice(0, 2);
  const topRegionGap = [...summary.regions]
    .filter((r) => r.gap_share_percent !== null)
    .sort((a, b) => (b.gap_share_percent ?? 0) - (a.gap_share_percent ?? 0))[0] ?? null;

  const takeaways: Array<{ kind: 'drag' | 'bright' | 'action'; title: string; detail: string }> = [];

  if (scope.view === 'corporate' && lowestFn) {
    const secondPart = secondLowestFn && (secondLowestFn.score ?? 100) < 90
      ? ` & ${secondLowestFn.function}`
      : '';
    const shareText = lowestFn.gap_share_percent != null
      ? ` — ${lowestFn.function} (${fmtScore(lowestFn.score)}) accounts for ${Math.round(lowestFn.gap_share_percent)}% of the gap.`
      : ` — ${lowestFn.function} is lowest at ${fmtScore(lowestFn.score)}.`;
    takeaways.push({
      kind: 'drag',
      title: `Biggest Drag — ${lowestFn.function}${secondPart}`,
      detail: `${lowestFn.function} (${fmtScore(lowestFn.score)})${secondPart && secondLowestFn ? ` and ${secondLowestFn.function} (${fmtScore(secondLowestFn.score)})` : ''} lead the shortfall${shareText.includes('accounts') ? ` (${Math.round(lowestFn.gap_share_percent ?? 0)}% gap share)` : ''}.`,
    });
  } else if (lowestTeam && (lowestTeam.score ?? 100) < 90) {
    takeaways.push({
      kind: 'drag',
      title: `Primary Bottleneck — ${lowestTeam.team}`,
      detail: `${lowestTeam.team} (${fmtScore(lowestTeam.score)}) holds the widest shortfall below the 90% threshold${lowestTeam.flag_detail?.text ? ` · ${lowestTeam.flag_detail.text}` : ''}.`,
    });
  }

  if (scope.view === 'corporate' && topImprovedFn) {
    takeaways.push({
      kind: 'bright',
      title: `Bright Spot — ${topImprovedFn.function}`,
      detail: `${topImprovedFn.function} rose ${fmtSigned(topImprovedFn.change)} to ${fmtScore(topImprovedFn.score)}${healthyTeamsCount > 0 ? `, with ${healthyTeamsCount} of ${scoredTeams.length} teams on track (≥90%).` : '.'}`,
    });
  } else if (highestTeam && (highestTeam.score ?? 0) >= 90) {
    takeaways.push({
      kind: 'bright',
      title: `Leading Performance — ${highestTeam.team}`,
      detail: `${highestTeam.team} achieved ${fmtScore(highestTeam.score)}${highestTeam.change != null && highestTeam.change > 0 ? ` (${fmtSigned(highestTeam.change)} momentum)` : ''}.`,
    });
  }

  if (topNegDrivers.length > 0) {
    const kpiNames = topNegDrivers.map((d) => `${d.kpi_label}${d.team ? ` (${d.team})` : ''}`).join(' and ');
    takeaways.push({
      kind: 'action',
      title: 'Recommended Action',
      detail: `Prioritize coaching and corrective follow-up on ${kpiNames} to recover the largest weighted gap.`,
    });
  } else if (atRiskTeamsCount > 0) {
    takeaways.push({
      kind: 'action',
      title: 'Recommended Action',
      detail: `Review the ${atRiskTeamsCount} ${atRiskTeamsCount === 1 ? 'team' : 'teams'} below 90% and assign tracked corrective plans.`,
    });
  }

  const jumpToAtRisk = () => {
    const el = document.getElementById('exec-risk-section');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  return (
    <section aria-labelledby="exec-hero-title" className="flex flex-col gap-[16px]">
      {/* ROW 1 — Figma 4-Column Frosted Pastel-Gradient KPI Strip */}
      <div className="grid grid-cols-1 gap-[14px] sm:grid-cols-2 xl:grid-cols-4">
        <TopKpiCard
          icon={ChartNoAxesColumnIncreasing}
          label={hero.score_basis === 'leader_scorecard' ? 'Leader scorecard' : hero.score_basis === 'team_scorecard' ? 'Team score' : 'People average'}
          value={fmtScore(hero.score)}
          inlineBadge={tone.grade ? `Grade ${tone.grade} · ${tone.label}` : 'No grade'}
          inlineBadgeColor={tone.text}
          valueColor={tone.text}
          tintColor={tone.gauge}
          sub={`Weighted average across ${hero.employees.toLocaleString('en-US')} employees`}
          barScore={hero.score}
          barGradient={gradeGradientVar(hero.score)}
        />

        <TopKpiCard
          icon={Target}
          label="Gap"
          value={fmtSigned(hero.gap)}
          inlineBadge={`vs target ${fmtScore(hero.target, 0)}`}
          inlineBadgeColor={toneColor(scoreTone(hero.gap))}
          valueColor={toneColor(scoreTone(hero.gap))}
          tintColor={hero.gap !== null && hero.gap < 0 ? 'var(--pms-grade-e-solid)' : 'var(--pms-grade-a-solid)'}
          sub={
            topRegionGap && summary.regions.length > 1
              ? `${topRegionGap.region} accounts for ${Math.round(topRegionGap.gap_share_percent ?? 0)}% of total gap`
              : hero.score !== null && hero.score >= 90
                ? 'Above 90% healthy threshold'
                : 'Shortfall against 100% benchmark'
          }
          barScore={hero.score}
          barGradient={hero.gap !== null && hero.gap < 0 ? 'var(--pms-grad-grade-e)' : 'var(--pms-grad-grade-a)'}
        />

        <TopKpiCard
          icon={hero.change !== null && hero.change < 0 ? TrendingDown : TrendingUp}
          label={previousLabel}
          value={fmtSigned(hero.change)}
          inlineBadge={
            hero.change === null
              ? undefined
              : hero.change > 0.2
                ? '↑ Improving'
                : hero.change < -0.2
                  ? '↓ Declining'
                  : '↑ Steady'
          }
          inlineBadgeColor={toneColor(changeTone)}
          valueColor={toneColor(changeTone)}
          tintColor={changeTone === 'bad' ? 'var(--pms-grade-e-solid)' : changeTone === 'good' ? 'var(--pms-grade-a-solid)' : 'var(--insights-accent)'}
          sub={
            hero.previous_score !== null
              ? `${arrow(hero.change)} ${fmtScore(hero.previous_score)} → ${fmtScore(hero.score)}`
              : period.range
                ? 'No earlier range to compare'
                : 'No previous month to compare'
          }
          subColor={toneColor(changeTone)}
          barScore={hero.change !== null ? Math.min(100, Math.max(20, 55 + hero.change * 5)) : 50}
          barGradient={changeTone === 'bad' ? 'var(--pms-grad-grade-e)' : changeTone === 'good' ? 'var(--pms-grad-grade-a)' : 'var(--pms-grad-accent)'}
        />

        {comparison && comparison.score !== null ? (
          <TopKpiCard
            icon={BarChart3}
            label={isFunction ? 'vs Company' : `vs ${comparison.label}`}
            value={fmtSigned(comparison.difference)}
            inlineBadge={
              comparison.difference !== null && comparison.difference >= 0
                ? 'Above benchmark'
                : 'Below benchmark'
            }
            inlineBadgeColor={toneColor(scoreTone(comparison.difference))}
            valueColor={toneColor(scoreTone(comparison.difference))}
            tintColor={scoreTone(comparison.difference) === 'bad' ? 'var(--pms-grade-d-solid)' : 'var(--pms-grade-a-solid)'}
            sub={`${comparison.label}: ${fmtScore(comparison.score)}`}
            barScore={comparison.score}
            barGradient={scoreTone(comparison.difference) === 'bad' ? 'var(--pms-grad-grade-d)' : 'var(--pms-grad-grade-a)'}
          />
        ) : (
          <TopKpiCard
            icon={Users}
            label="Teams Health"
            value={atRiskTeamsCount > 0 ? `${atRiskTeamsCount} At Risk` : 'All On Track'}
            inlineBadge={scoredTeams.length > 0 ? `${healthyTeamsCount} On Track ≥90%` : undefined}
            inlineBadgeColor="var(--pms-grade-a-text)"
            valueColor={atRiskTeamsCount > 0 ? 'var(--pms-grade-c-text)' : 'var(--pms-grade-a-text)'}
            tintColor={atRiskTeamsCount > 0 ? 'var(--pms-grade-c-solid)' : 'var(--pms-grade-a-solid)'}
            sub={
              scoredTeams.length > 0
                ? `${atRiskTeamsCount} of ${scoredTeams.length} teams scored under 90% threshold`
                : `${hero.functions_count} functions · ${hero.teams_count} teams`
            }
            barScore={scoredTeams.length > 0 ? Math.max(12, healthyRatio) : 100}
            barGradient={atRiskTeamsCount > 0 ? 'var(--pms-grad-grade-c)' : 'var(--pms-grad-grade-a)'}
          />
        )}
      </div>

      {/* ROW 2 — Figma 2-Column Split: Left = Executive Takeaway Card | Right = Company Score Trend Card */}
      <div className="grid gap-[16px] xl:grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)]">
        <div className="pms-glass-surface flex min-w-0 flex-col justify-between gap-[16px] rounded-[20px] p-[20px] sm:p-[22px]">
          <div className="flex flex-col gap-[14px]">
            <div className="flex flex-wrap items-center justify-between gap-[8px]">
              <div className="flex flex-wrap items-center gap-[8px]">
                <span aria-hidden="true" className="flex size-[34px] items-center justify-center rounded-[10px] border border-white/60 bg-[var(--insights-accent-tag)] dark:border-white/10">
                  <EyebrowIcon className="size-[18px] text-[var(--insights-accent)]" strokeWidth={1.9} />
                </span>
                <span className="text-[15px] font-bold text-[var(--insights-heading)]">
                  {scope.view === 'function' ? `${hero.label} Performance Brief` : eyebrow.label}
                </span>
                <GradePill score={hero.score} className="!px-[10px] !py-[3px] !text-[11px]" />
                {statusLabel && (
                  <StatusPill tone={statusTone} icon={statusTone === 'success' ? CheckCircle2 : AlertTriangle}>{statusLabel}</StatusPill>
                )}
              </div>

              {/* Quick Help & Executive Decision Guide */}
              <div className="relative flex items-center gap-[8px]">
                {takeaways.length > 0 && (
                  <span className="hidden rounded-full bg-[var(--exec-chip-bg)] px-[9px] py-[3px] text-[11px] font-semibold text-[var(--text-muted)] sm:inline-flex">
                    {takeaways.length} Key Insights
                  </span>
                )}
                <button
                  ref={helpBtnRef}
                  type="button"
                  onClick={() => setIsHelpOpen((prev) => !prev)}
                  aria-expanded={isHelpOpen}
                  aria-controls={isHelpOpen ? helpDialogId : undefined}
                  aria-haspopup="dialog"
                  aria-label="Quick help and executive guide"
                  className="inline-flex items-center gap-[5px] rounded-[10px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-[9px] py-[5px] text-xs font-semibold text-[var(--text-secondary)] transition hover:border-[var(--insights-accent-border)] hover:text-[var(--insights-heading)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)]"
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
                          The company number is the average of employee scores. Each person counts once. Each person&apos;s score is their weighted KPIs, capped at 100%. A leader scorecard is labeled when a team row uses one.
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
                          <li>Open a function card to see its summary, focusing on the lowest score first.</li>
                          <li>Red drivers are weight × gap to target. Green drivers are the change since last month.</li>
                          <li>Use <em>Teams at risk</em>, beginning with the lowest-scoring team, then confirm a corrective action.</li>
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

            <h2 id="exec-hero-title" className="text-[clamp(18px,1.55vw,22px)] font-bold leading-[1.28] tracking-[-0.025em] text-[var(--insights-heading)]">
              {heroHeadline(summary)}
            </h2>

            {narrative && (
              <p className="text-[13px] leading-[1.6] text-[var(--text-secondary)]">{narrative}</p>
            )}

            {/* Figma 3 Key Insights List */}
            {takeaways.length > 0 && (
              <ul className="flex flex-col gap-[10px]">
                {takeaways.map((item) => {
                  const Icon = item.kind === 'drag' ? AlertTriangle : item.kind === 'bright' ? TrendingUp : Sparkles;
                  const iconBg = item.kind === 'drag'
                    ? 'var(--exec-neg-bg)'
                    : item.kind === 'bright'
                      ? 'var(--exec-pos-bg)'
                      : 'var(--exec-info-bg)';
                  const iconColor = item.kind === 'drag'
                    ? 'var(--insights-negative)'
                    : item.kind === 'bright'
                      ? 'var(--insights-positive)'
                      : 'var(--insights-accent)';
                  return (
                    <li
                      key={item.title}
                      className="pms-glass-stage flex items-start gap-[10px] rounded-[12px] px-[12px] py-[10px]"
                    >
                      <span
                        aria-hidden="true"
                        className="mt-[1px] flex size-[26px] shrink-0 items-center justify-center rounded-[8px]"
                        style={{ background: iconBg, color: iconColor }}
                      >
                        <Icon className="size-[14px]" strokeWidth={2} />
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="text-[12.5px] font-bold leading-snug text-[var(--insights-heading)]">{item.title}</p>
                        <p className="mt-[2px] text-[12px] leading-[1.45] text-[var(--text-secondary)]">{item.detail}</p>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          <div className="flex flex-col gap-[10px] border-t border-[var(--exec-card-border)] pt-[12px]">
            {scope.view === 'corporate' && atRiskTeamsCount > 0 && (
              <button
                type="button"
                onClick={jumpToAtRisk}
                className="inline-flex min-h-[38px] w-full items-center justify-center gap-[6px] rounded-[12px] border border-[var(--insights-accent-border)] px-[14px] text-[12.5px] font-bold text-[var(--insights-accent-text)] transition-all hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)]"
                style={{ background: 'var(--pms-grad-panel-info)' }}
              >
                Jump to {atRiskTeamsCount} At-Risk {atRiskTeamsCount === 1 ? 'Team' : 'Teams'}
                <ArrowRight className="size-[14px]" aria-hidden="true" />
              </button>
            )}
            <div className="flex flex-wrap gap-[6px]">
              <Chip icon={Users}>{hero.employees.toLocaleString('en-US')} employees</Chip>
              {scope.view === 'corporate'
                ? <Chip icon={Layers}>{hero.functions_count} functions · {hero.teams_count} teams</Chip>
                : scope.view === 'function' ? <Chip icon={Layers}>{hero.teams_count} teams</Chip> : null}
              {upload
                ? <Chip icon={Upload}>Data uploaded {fmtDate(upload.uploaded_at)}</Chip>
                : <Chip icon={Calendar}>{coveredPeriodLabel(period.effective, period.range)} data</Chip>}
            </div>
          </div>
        </div>

        <ScoreTrendChart
          points={trend}
          title={chartTitle}
          subtitle={chartSubtitle}
          comparisonLabel={comparison?.label ?? null}
        />
      </div>
    </section>
  );
}
