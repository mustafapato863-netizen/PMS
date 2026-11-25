import type { ReactNode } from 'react';
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Building2,
  Globe,
  Info,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import type { ExecutiveFunction, ExecutiveRegion, ExecutiveTrendPoint } from '../../executive/types';
import { periodFromKey as execPeriodFromKey } from '../../executive/compose';
import { arrow, fmtScore, fmtSigned, scoreTone, toneColor } from '../../executive/format';
import { getGradeTone, gradeTokenVar } from '../../../constants/grades';
import {
  GradePill as ExecGradePill,
  ScoreBar,
  ScoreText,
  StatLabel,
  StatusPill,
  ToneText,
} from '../../../components/executive/v1/ExecPrimitives';
import { FUNCTION_STYLE, formatShare } from '../../../components/executive/v1/execModel';
import { presentationTeamName } from '../../team/countryTeamIdentity';
import { gradeGradientVar } from '../../../components/executive/v1/gradeGradient';
import FunctionTrendChart from '../../../components/executive/v1/FunctionTrendChart';
import ScoreTrendChart from '../../../components/executive/v1/ScoreTrendChart';
import {
  GRADE_STYLES,
  gradeForScore,
  type FunctionOverviewItem,
  type GradeDistributionRow,
  type GradeLetter,
  type MonthlyOverviewData,
  type ScoreDriverItem,
  type TeamAtRiskItem,
  type TrendPoint,
} from '../monthlyOverviewData';
import { slugifyIdentifier } from '../callCenterDeepDiveData';

/* -------------------------------------------------------------------------- */
/*  Shared Grade Badge                                                        */
/* -------------------------------------------------------------------------- */

const GRADE_B_BLUE = {
  text: '#1D4ED8',
  badgeBg: '#EFF6FF',
  badgeText: '#1D4ED8',
  border: '#BFDBFE',
  gauge: '#2563EB',
  gradient: 'linear-gradient(90deg, #93C5FD 0%, #2563EB 100%)',
} as const;

function monthlyGradeGradient(grade: GradeLetter): string {
  return grade === 'B' ? GRADE_B_BLUE.gradient : `var(--pms-grad-grade-${grade.toLowerCase()})`;
}

export function GradePill({
  grade,
  size = 'md',
  prefixGrade = false,
}: {
  grade: GradeLetter;
  size?: 'sm' | 'md' | 'lg';
  prefixGrade?: boolean;
}) {
  const sizeClasses =
    size === 'lg'
      ? 'px-3.5 py-1 text-sm font-bold rounded-xl'
      : size === 'sm'
      ? 'px-2 py-0.5 text-xs font-bold rounded-md'
      : 'px-2.5 py-0.5 text-xs font-bold rounded-lg';

  const isBlueB = grade === 'B';

  return (
    <span
      data-grade={grade}
      className={`inline-flex items-center justify-center border ${sizeClasses}${
        isBlueB ? ' border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-400/45 dark:bg-blue-500/20 dark:text-blue-300' : ''
      }`}
      style={
        isBlueB
          ? undefined
          : {
              background: gradeTokenVar(grade, 'badge-bg'),
              color: gradeTokenVar(grade, 'badge-text'),
              borderColor: gradeTokenVar(grade, 'border'),
            }
      }
    >
      {prefixGrade ? `Grade ${grade}` : grade}
    </span>
  );
}

/* -------------------------------------------------------------------------- */
/*  1. Header Section                                                         */
/* -------------------------------------------------------------------------- */

export interface MonthlyOverviewHeaderProps {
  title: string;
  flowName: string;
  regionName: string;
  branchLabel?: string;
  monthLabel: string;
  regionCode: 'EGY' | 'UAE' | 'ALL';
  pageIndicatorLabel: string;
  toolbar?: ReactNode;
}

export function MonthlyOverviewHeader({
  title,
  flowName,
  regionName,
  branchLabel,
  monthLabel,
  regionCode,
  pageIndicatorLabel,
  toolbar,
}: MonthlyOverviewHeaderProps) {
  return (
    <header
      aria-label="Executive Summary Header"
      className="pms-glass-surface flex min-w-0 flex-col gap-4 rounded-2xl p-4 sm:p-5"
    >
      <div className="flex min-w-0 flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-md bg-slate-100 px-2.5 py-0.5 text-xs font-semibold tracking-wide text-slate-700 uppercase">
            {flowName}
          </span>

          {/* Region Badge */}
          <span
            data-testid="header-region-badge"
            className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-0.5 text-xs font-semibold ${
              regionCode === 'EGY'
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : regionCode === 'ALL'
                  ? 'border-violet-200 bg-violet-50 text-violet-700'
                  : 'border-blue-200 bg-blue-50 text-blue-700'
            }`}
          >
            <span className="size-1.5 rounded-full bg-current" />
            {regionName}
          </span>

          {branchLabel && (
            <span
              data-testid="header-branch-badge"
              className="inline-flex items-center gap-1.5 rounded-full border border-cyan-200 bg-cyan-50 px-3 py-0.5 text-xs font-semibold text-cyan-800"
            >
              <span className="size-1.5 rounded-full bg-current" />
              {branchLabel}
            </span>
          )}

          {/* Page Indicator Badge */}
          <span
            data-testid="header-page-indicator"
            className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-3 py-0.5 text-xs font-semibold text-slate-600"
          >
            {pageIndicatorLabel}
          </span>
        </div>

        <div className="min-w-0 pt-0.5">
          <h1 className="text-2xl font-bold tracking-tight text-balance text-slate-900 sm:text-[28px]">
            {title}
          </h1>
          <p className="mt-1 text-sm font-medium text-slate-500">
            {regionName}
            {branchLabel ? ` · ${branchLabel}` : ''} · {monthLabel}
          </p>
        </div>
      </div>

      {toolbar && (
        <div className="flex w-full min-w-0 max-w-full flex-wrap items-center gap-2">{toolbar}</div>
      )}
    </header>
  );
}

/* -------------------------------------------------------------------------- */
/*  2. Overall Company Performance Card                                       */
/* -------------------------------------------------------------------------- */

export interface OverallCompanyPerformanceProps {
  overall: MonthlyOverviewData['overall'];
  previousMonthLabel: string;
}

export function OverallCompanyPerformanceCard({
  overall,
  previousMonthLabel,
}: OverallCompanyPerformanceProps) {
  const gradeStyle = GRADE_STYLES[overall.grade];
  const isPositiveChange = overall.change >= 0;
  const formattedChange = `${isPositiveChange ? '+' : ''}${overall.change.toFixed(1)}%`;
  const formattedGap = `${overall.gap > 0 ? '+' : ''}${overall.gap.toFixed(1)}%`;

  return (
    <section
      id="presentation-section-score"
      data-section-label="Score"
      aria-labelledby="overall-performance-heading"
      className="pms-glass-surface relative flex h-full w-full scroll-mt-24 flex-col justify-between overflow-hidden rounded-2xl p-6"
    >
      <div>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <span className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
              Executive Snapshot
            </span>
            <h2
              id="overall-performance-heading"
              className="mt-0.5 text-lg font-bold text-slate-900"
            >
              Overall Company Performance
            </h2>
          </div>

          <div className="flex items-center gap-2 text-xs font-medium text-slate-500">
            <span>{overall.functionsCount} Functions</span>
            <span>·</span>
            <span>{overall.teamsCount} Teams</span>
            <span>·</span>
            <span>{overall.employeesCount} Employees</span>
          </div>
        </div>

        {/* Hero Score + Grade Badge + Statement + Movement */}
        <div className="mt-5 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="flex flex-wrap items-baseline gap-3.5">
            <span
              data-testid="overall-score-value"
              className={`text-5xl font-extrabold tracking-tight sm:text-6xl ${gradeStyle.scoreText}`}
            >
              {overall.score.toFixed(1)}%
            </span>
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center gap-2">
                <GradePill grade={overall.grade} size="lg" prefixGrade />
                <span
                  data-testid="overall-movement-badge"
                  className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs font-semibold ${
                    isPositiveChange
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                      : 'border-red-200 bg-red-50 text-red-700'
                  }`}
                >
                  {isPositiveChange ? (
                    <ArrowUpRight className="size-3.5" />
                  ) : (
                    <ArrowDownRight className="size-3.5" />
                  )}
                  {formattedChange} vs {previousMonthLabel}
                </span>
              </div>
              <p
                data-testid="overall-target-statement"
                className="text-sm font-semibold text-slate-700"
              >
                {overall.headline}
              </p>
            </div>
          </div>
        </div>

        {/* Two Small Metrics: Current / Gap */}
        <div className="mt-6 grid grid-cols-2 gap-3">
          <div className="pms-glass-stage rounded-xl px-4 py-3">
            <div className="text-xs font-medium text-slate-500">Current</div>
            <div className="mt-1 text-xl font-bold text-slate-900">
              {overall.score.toFixed(1)}%
            </div>
          </div>

          <div className="rounded-xl border border-amber-200/80 bg-amber-50/50 px-4 py-3">
            <div className="text-xs font-medium text-amber-800">Gap</div>
            <div className="mt-1 text-xl font-bold text-amber-700">{formattedGap}</div>
          </div>
        </div>
      </div>

      {/* Small note about mixed evaluation settings */}
      <div className="pms-glass-stage mt-5 flex items-start gap-2.5 rounded-xl px-3.5 py-2.5 text-xs leading-relaxed text-slate-600">
        <Info className="mt-0.5 size-4 shrink-0 text-slate-400" />
        <span>{overall.evaluationNote}</span>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/*  3. 6-Month Score Trend Card                                               */
/* -------------------------------------------------------------------------- */

export interface SixMonthTrendCardProps {
  trend: TrendPoint[];
  executiveTrend?: ExecutiveTrendPoint[];
}

function toExecutiveTrendPoints(trend: TrendPoint[]): ExecutiveTrendPoint[] {
  return trend.map((point) => {
    const parsed = execPeriodFromKey(point.key);
    return {
      period: parsed ?? {
        year: Number(point.key.slice(0, 4)) || new Date().getFullYear(),
        month: point.month,
        key: point.key || point.month,
      },
      score: Number.isFinite(point.score) ? point.score : null,
      target: Number.isFinite(point.target) ? point.target : 100,
      comparison_score: null,
    };
  });
}

export function SixMonthTrendCard({ trend, executiveTrend }: SixMonthTrendCardProps) {
  const points = executiveTrend ?? toExecutiveTrendPoints(trend);

  return (
    <div
      id="presentation-section-trend"
      data-section-label="Trend"
      data-testid="six-month-score-trend"
      className="flex h-full w-full scroll-mt-24 [&>section]:h-full [&>section]:w-full"
    >
      <ScoreTrendChart
        points={points}
        title="Company Score Trend"
        subtitle="6-month trajectory against 100% target and 90% healthy threshold"
      />
    </div>
  );
}

/* -------------------------------------------------------------------------- */
/*  3b. Region Performance Share Section                                      */
/* -------------------------------------------------------------------------- */

export interface RegionPerformanceShareSectionProps {
  regions: ExecutiveRegion[];
  overallGap?: number | null;
  previousMonthLabel: string;
  onSelectRegion?: (region: 'EGY' | 'UAE') => void;
}

function resolveOverallGap(
  overallGap: number | null | undefined,
  regions: ExecutiveRegion[],
): number | null {
  if (overallGap !== null && overallGap !== undefined && Number.isFinite(overallGap)) {
    return overallGap;
  }
  let weightedScore = 0;
  let totalEmployees = 0;
  for (const region of regions) {
    if (region.score !== null && Number.isFinite(region.score) && region.employees > 0) {
      weightedScore += region.score * region.employees;
      totalEmployees += region.employees;
    }
  }
  if (totalEmployees === 0) return null;
  return Number((weightedScore / totalEmployees - 100).toFixed(1));
}

export function RegionPerformanceShareSection({
  regions,
  overallGap,
  previousMonthLabel,
  onSelectRegion,
}: RegionPerformanceShareSectionProps) {
  if (regions.length <= 1) return null;

  const topGapRegion = [...regions]
    .filter((region) => region.gap_share_percent !== null)
    .sort((left, right) => (right.gap_share_percent ?? 0) - (left.gap_share_percent ?? 0))[0];
  const resolvedOverallGap = resolveOverallGap(overallGap, regions);
  const formattedOverallGap =
    resolvedOverallGap !== null && resolvedOverallGap < 0
      ? `${resolvedOverallGap.toFixed(1)}%`
      : null;

  return (
    <section
      id="presentation-section-regions"
      data-section-label="Regions"
      aria-labelledby="region-performance-share-heading"
      data-testid="monthly-region-performance-share"
      className="pms-glass-surface scroll-mt-24 rounded-2xl p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span
            aria-hidden="true"
            className="inline-flex size-9 shrink-0 items-center justify-center rounded-xl border border-blue-200/80 bg-blue-50 text-blue-700"
          >
            <Globe className="size-4" />
          </span>
          <div>
            <span className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
              Regional Comparison
            </span>
            <h2
              id="region-performance-share-heading"
              className="mt-0.5 text-lg font-bold text-slate-900"
            >
              Region Performance Share
            </h2>
          </div>
        </div>

        <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
          {regions.map((region) => region.region).join(' vs ')} · ranked by share of the gap
        </span>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
        {regions.map((region) => {
          const score = region.score ?? 0;
          const grade = (region.grade as GradeLetter) || gradeForScore(score);
          const gradeStyle = GRADE_STYLES[grade];
          const gap = region.gap;
          const change = region.change;
          const clickable = onSelectRegion && (region.region === 'EGY' || region.region === 'UAE');

          const content = (
            <>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex min-w-0 items-center gap-2">
                  <span
                    className={`shrink-0 rounded-md px-2 py-0.5 text-xs font-bold ${
                      region.region === 'EGY'
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-blue-50 text-blue-700'
                    }`}
                  >
                    {region.region}
                  </span>
                  <span className="truncate text-sm font-bold text-slate-900">
                    {region.label}
                  </span>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                  <span className={`text-xl font-extrabold tabular-nums ${gradeStyle.scoreText}`}>
                    {region.score !== null ? `${region.score.toFixed(1)}%` : '—'}
                  </span>
                  <GradePill grade={grade} size="sm" prefixGrade />
                </div>
              </div>

              <div aria-hidden="true" className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-100">
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${Math.min(100, Math.max(0, score))}%`,
                    background: monthlyGradeGradient(grade),
                  }}
                />
              </div>

              <div className="mt-3 flex flex-wrap items-center justify-between gap-x-3 gap-y-1.5 text-xs">
                <span className="font-medium text-slate-600">
                  {region.employees} {region.employees === 1 ? 'person' : 'people'} · {region.teams_count}{' '}
                  {region.teams_count === 1 ? 'team' : 'teams'}
                  {region.gap_share_percent != null ? ` · ${formatShare(region.gap_share_percent)}% of the gap` : ''}
                  {region.headcount_share_percent != null ? ` · ${Math.round(region.headcount_share_percent)}% of people` : ''}
                </span>

                <div className="flex shrink-0 items-center gap-2.5 font-semibold tabular-nums">
                  {gap !== null && (
                    <span className={gap < 0 ? 'text-amber-700' : 'text-emerald-700'}>
                      {gap >= 0 ? `+${gap.toFixed(1)}%` : `${gap.toFixed(1)}%`} vs 100
                    </span>
                  )}
                  {change !== null && (
                    <span className={change >= 0 ? 'text-emerald-700' : 'text-red-600'}>
                      {change >= 0 ? `↑ +${change.toFixed(1)}%` : `↓ ${change.toFixed(1)}%`} vs {previousMonthLabel}
                    </span>
                  )}
                </div>
              </div>
            </>
          );

          if (clickable) {
            return (
              <button
                key={region.region}
                type="button"
                data-testid={`monthly-region-share-card-${region.region.toLowerCase()}`}
                onClick={() => onSelectRegion(region.region as 'EGY' | 'UAE')}
                className="group flex w-full flex-col rounded-xl border border-slate-200/80 bg-slate-50/60 p-4 text-left transition-all hover:border-blue-300 hover:bg-white hover:shadow-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
              >
                {content}
              </button>
            );
          }

          return (
            <div
              key={region.region}
              data-testid={`monthly-region-share-card-${region.region.toLowerCase()}`}
              className="flex flex-col rounded-xl border border-slate-200/80 bg-slate-50/60 p-4"
            >
              {content}
            </div>
          );
        })}
      </div>

      {topGapRegion && topGapRegion.headcount_share_percent !== null && (
        <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-slate-200/80 bg-slate-50 px-3.5 py-2.5 text-xs leading-relaxed text-slate-600">
          <Info className="mt-0.5 size-4 shrink-0 text-slate-400" />
          <span>
            <strong className="font-semibold text-slate-800">{topGapRegion.region} gap share:</strong>{' '}
            {Math.round(topGapRegion.gap_share_percent ?? 0)}% of the{' '}
            {formattedOverallGap ? (
              <>
                overall <strong className="font-semibold text-slate-800 tabular-nums">{formattedOverallGap}</strong>{' '}
                company gap
              </>
            ) : (
              'company gap'
            )}{' '}
            from {Math.round(topGapRegion.headcount_share_percent)}% of evaluated headcount.
          </span>
        </div>
      )}
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/*  4. Grade Distribution Section                                             */
/* -------------------------------------------------------------------------- */

export interface GradeDistributionSectionProps {
  totalEmployees: number;
  rows: GradeDistributionRow[];
  takeaway: string;
  previousMonthLabel: string;
}

export function GradeDistributionSection({
  totalEmployees,
  rows,
  takeaway,
  previousMonthLabel,
}: GradeDistributionSectionProps) {
  return (
    <section
      id="presentation-section-grades"
      data-section-label="Grades"
      aria-labelledby="grade-distribution-heading"
      className="pms-glass-surface scroll-mt-24 rounded-2xl p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <span className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
            Population Health
          </span>
          <h2
            id="grade-distribution-heading"
            className="mt-0.5 text-lg font-bold text-slate-900"
          >
            Grade Distribution
          </h2>
        </div>

        <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
          Total Evaluated: {totalEmployees} employees
        </span>
      </div>

      {/* Horizontal bars A -> E */}
      <div className="mt-5 space-y-3.5">
        {rows.map((row) => {
          const hasMove = row.change !== 0;
          const isUp = row.change > 0;
          return (
            <div
              key={row.grade}
              data-testid={`grade-row-${row.grade}`}
              className="grid grid-cols-1 items-center gap-2 sm:grid-cols-12 sm:gap-4"
            >
              {/* Grade Label & Threshold */}
              <div className="flex items-center gap-2.5 sm:col-span-3">
                <GradePill grade={row.grade} size="sm" />
                <div className="min-w-0">
                  <div className="truncate text-sm font-semibold text-slate-800">
                    Grade {row.grade}{' '}
                    <span className="font-normal text-slate-500">· {row.label}</span>
                  </div>
                  <div className="text-xs text-slate-400">{row.thresholdLabel}</div>
                </div>
              </div>

              {/* Horizontal Progress Bar */}
              <div className="sm:col-span-6">
                <div className="h-3.5 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    data-testid={`grade-bar-${row.grade}`}
                    style={{
                      width: `${Math.max(row.percentage, 3)}%`,
                      background: monthlyGradeGradient(row.grade),
                    }}
                    className="h-full rounded-full transition-all duration-300"
                  />
                </div>
              </div>

              {/* Headcount + Share % + Movement vs previous month */}
              <div className="flex items-center justify-between gap-3 sm:col-span-3 sm:justify-end">
                <div className="text-right text-sm font-bold text-slate-900">
                  {row.count}{' '}
                  <span className="text-xs font-medium text-slate-500">
                    ({row.percentage.toFixed(1)}%)
                  </span>
                </div>

                <span
                  data-testid={`grade-movement-${row.grade}`}
                  title={`Movement vs ${previousMonthLabel}`}
                  className={`inline-flex min-w-[54px] items-center justify-center gap-0.5 rounded-md border px-2 py-0.5 text-xs font-semibold ${
                    !hasMove
                      ? 'border-slate-200 bg-slate-50 text-slate-500'
                      : isUp
                      ? 'border-slate-200 bg-slate-50 text-slate-700'
                      : 'border-slate-200 bg-slate-50 text-slate-600'
                  }`}
                >
                  {hasMove ? (
                    <>
                      <span
                        className={
                          row.grade === 'D' || row.grade === 'E'
                            ? isUp
                              ? 'text-red-600'
                              : 'text-emerald-600'
                            : isUp
                            ? 'text-emerald-600'
                            : 'text-amber-600'
                        }
                      >
                        {isUp ? '▲' : '▼'}
                      </span>
                      <span>
                        {isUp ? `+${row.change}` : row.change}
                      </span>
                    </>
                  ) : (
                    '—'
                  )}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Takeaway sentence under the bars */}
      <div
        data-testid="grade-distribution-takeaway"
        className="mt-5 flex items-start gap-2.5 rounded-xl border border-blue-200/70 bg-blue-50/50 px-4 py-3 text-sm font-medium text-slate-800"
      >
        <Sparkles className="mt-0.5 size-4 shrink-0 text-blue-600" />
        <p>{takeaway}</p>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/*  5. What Moved the Score vs August                                         */
/* -------------------------------------------------------------------------- */

export interface ScoreDriversSectionProps {
  previousMonthLabel: string;
  negativeDrivers: ScoreDriverItem[];
  positiveDrivers: ScoreDriverItem[];
}

function DriverRow({
  item,
  variant,
}: {
  item: ScoreDriverItem;
  variant: 'negative' | 'positive';
}) {
  const isNegative = variant === 'negative';
  const impactFormatted = `${item.impactPct > 0 ? '+' : ''}${item.impactPct.toFixed(2)}%`;
  const betterText = item.betterDirection === 'lower' ? '↓ lower is better' : '↑ higher is better';

  return (
    <div className="pms-glass-stage flex items-center justify-between gap-3 rounded-xl p-3.5 transition-colors">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-slate-900 text-sm">{item.kpiName}</span>
          <span className="inline-flex items-center rounded-md border border-slate-200 bg-white px-2 py-0.5 text-xs font-medium text-slate-600">
            {betterText}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span className="font-semibold text-slate-700">{item.functionName}</span>
          <span>·</span>
          <span>{item.team}</span>
          <span>·</span>
          <span>Actual: {item.actualValue}</span>
          {item.movementLabel && (
            <>
              <span>·</span>
              <span className="font-medium text-slate-600">{item.movementLabel}</span>
            </>
          )}
        </div>
      </div>

      <div className="shrink-0 text-right">
        <span
          className={`inline-flex items-center rounded-lg border px-2.5 py-1 text-xs font-bold ${
            isNegative
              ? 'border-red-200 bg-red-50 text-red-700'
              : 'border-emerald-200 bg-emerald-50 text-emerald-700'
          }`}
        >
          {impactFormatted}
        </span>
      </div>
    </div>
  );
}

export function ScoreDriversSection({
  previousMonthLabel,
  negativeDrivers,
  positiveDrivers,
}: ScoreDriversSectionProps) {
  return (
    <section
      id="presentation-section-drivers"
      data-section-label="Drivers"
      aria-labelledby="score-drivers-heading"
      className="pms-glass-surface scroll-mt-24 rounded-2xl p-6"
    >
      <div>
        <span className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
          Key Movers
        </span>
        <h2 id="score-drivers-heading" className="mt-0.5 text-lg font-bold text-slate-900">
          What Moved the Score vs {previousMonthLabel}
        </h2>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {/* Column 1: Top Negative Drivers */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-bold text-red-700">
            <TrendingDown className="size-4" />
            <h3>Top Negative Drivers</h3>
          </div>
          <div className="space-y-2.5">
            {negativeDrivers.length === 0 ? (
              <p className="text-sm text-slate-500">No negative drivers in this region.</p>
            ) : (
              negativeDrivers.map((item) => (
                <DriverRow key={item.id} item={item} variant="negative" />
              ))
            )}
          </div>
        </div>

        {/* Column 2: Top Positive Drivers */}
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm font-bold text-emerald-700">
            <TrendingUp className="size-4" />
            <h3>Top Positive Drivers</h3>
          </div>
          <div className="space-y-2.5">
            {positiveDrivers.length === 0 ? (
              <p className="text-sm text-slate-500">No positive drivers in this region.</p>
            ) : (
              positiveDrivers.map((item) => (
                <DriverRow key={item.id} item={item} variant="positive" />
              ))
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/*  6. Functions Overview Section                                             */
/* -------------------------------------------------------------------------- */

export interface FunctionsOverviewSectionProps {
  functions: FunctionOverviewItem[];
  previousMonthLabel: string;
  onSelectFunction: (fn: FunctionOverviewItem) => void;
}

const FALLBACK_FUNCTION_STYLE = {
  icon: Building2,
  bg: 'var(--exec-chip-bg)',
  color: 'var(--insights-accent)',
};

function shortComparisonLabel(previousMonthLabel: string): string {
  const trimmed = previousMonthLabel.trim();
  if (!trimmed || /^previous\b/i.test(trimmed)) return 'vs last';
  const firstWord = trimmed.split(/\s+/)[0] ?? trimmed;
  return `vs ${firstWord.slice(0, 3)}`;
}

export function FunctionsOverviewSection({
  functions,
  previousMonthLabel,
  onSelectFunction,
}: FunctionsOverviewSectionProps) {
  const sortedFunctions = [...functions].sort((a, b) => a.score - b.score);
  const comparison = shortComparisonLabel(previousMonthLabel);
  const hasTrendCharts = sortedFunctions.some((fn) => (fn.trend?.length ?? 0) > 0);

  return (
    <section
      id="presentation-section-functions"
      data-section-label="Functions"
      aria-labelledby="functions-overview-heading"
      className="pms-glass-well scroll-mt-24 rounded-[22px] p-[18px] sm:p-[22px]"
    >
      <div className="flex flex-wrap items-start justify-between gap-[10px]">
        <div className="flex flex-col gap-[3px]">
          <div className="flex flex-wrap items-center gap-[8px]">
            <h2
              id="functions-overview-heading"
              className="text-[17px] font-bold tracking-[-0.015em] text-[var(--insights-heading)]"
            >
              Functions Overview
            </h2>
            <span className="rounded-full bg-[var(--exec-chip-bg)] px-[9px] py-[2px] text-xs font-semibold text-[var(--exec-chip-text)]">
              {sortedFunctions.length} functions
            </span>
          </div>
          <p className="text-[12px] text-[var(--text-muted)]">
            Sorted worst-first so functions needing support stand out immediately · Click any card to drill down
          </p>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-[14px] sm:grid-cols-2 lg:grid-cols-4">
        {sortedFunctions.map((fn) => {
          const tone = getGradeTone(fn.score);
          const isBlueB = fn.grade === 'B';
          const accentGauge = isBlueB ? GRADE_B_BLUE.gauge : tone.gauge;
          const accentGradient = isBlueB ? GRADE_B_BLUE.gradient : gradeGradientVar(fn.score);
          const fnStyle =
            FUNCTION_STYLE[fn.functionName as ExecutiveFunction] ?? FALLBACK_FUNCTION_STYLE;
          const Icon = fnStyle.icon;
          const changeTone = scoreTone(fn.change);
          const trendColor = changeTone === 'neutral' ? fnStyle.color : toneColor(changeTone);
          const showCalloutRow = Boolean(
            fn.isMostImproved ||
              (fn.fallingMonths !== null && fn.fallingMonths !== undefined && fn.fallingMonths >= 2) ||
              (fn.lowestTeam && fn.lowestTeam.score < 85),
          );

          return (
            <button
              key={fn.functionName}
              type="button"
              data-testid={`function-card-${fn.slug}`}
              data-grade={fn.grade}
              onClick={() => onSelectFunction(fn)}
              className="pms-glass-surface pms-glass-surface--interactive group/fcard relative flex h-full min-w-0 flex-col gap-[10px] overflow-hidden rounded-[18px] p-[15px] text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent-ring)]"
              style={{
                backgroundImage: `radial-gradient(circle at 95% 6%, color-mix(in srgb, ${accentGauge} 13%, transparent) 0%, transparent 64%), var(--pms-glass-card-bg)`,
                borderColor: `color-mix(in srgb, ${accentGauge} 20%, var(--pms-glass-card-border))`,
              }}
            >
              {/* Smooth Linear-Gradient Top Grade Accent Strip */}
              <span
                aria-hidden="true"
                className="pointer-events-none absolute inset-x-0 top-0 h-[3px]"
                style={{ background: accentGradient }}
              />

              {/* Zone 1: Function Icon + Title + Soft Grade Pill + Metadata Subtitle */}
              <div className="flex w-full flex-col gap-[4px]">
                <div className="flex items-center justify-between gap-[6px]">
                  <div className="flex min-w-0 items-center gap-[8px]">
                    <span
                      aria-hidden="true"
                      className="flex size-[32px] shrink-0 items-center justify-center rounded-[8px] shadow-2xs"
                      style={{
                        background: fnStyle.bg,
                        border: `1px solid color-mix(in srgb, ${fnStyle.color} 18%, transparent)`,
                      }}
                    >
                      <Icon
                        style={{ color: fnStyle.color, width: 16.5, height: 16.5 }}
                        strokeWidth={1.85}
                      />
                    </span>
                    <h3 className="truncate text-[15px] font-bold leading-[1.2] tracking-[-0.02em] text-[var(--insights-heading)] group-hover/fcard:underline">
                      {presentationTeamName(fn.functionName)}
                    </h3>
                  </div>
                  {isBlueB ? (
                    <span
                      data-grade="B"
                      className="inline-flex shrink-0 items-center rounded-full bg-blue-50 px-[8px] py-[2px] text-[11px] font-semibold leading-normal text-blue-700 dark:bg-blue-500/20 dark:text-blue-300"
                    >
                      Grade B
                    </span>
                  ) : (
                    <ExecGradePill score={fn.score} className="!px-[8px] !py-[2px] !text-[11px]" />
                  )}
                </div>

                <p className="truncate text-[12px] leading-[1.35] text-[var(--text-muted)]">
                  {fn.teamsCount} {fn.teamsCount === 1 ? 'team' : 'teams'} · {fn.headcount}{' '}
                  {fn.headcount === 1 ? 'person' : 'people'}
                  {fn.regions?.length ? ` · ${fn.regions.join(' + ')}` : ''}
                </p>
              </div>

              {/* Zone 2: Frosted Metric Stage (Score + Gap | vs Prev + ScoreBar w/ 90% Marker) */}
              <div className="pms-glass-stage w-full space-y-2 rounded-[12px] px-3 py-2.5">
                <div className="flex items-center justify-between gap-1.5">
                  {isBlueB ? (
                    <span className="text-[23px] font-bold leading-none tracking-[-0.04em] tabular-nums text-blue-700 dark:text-blue-400">
                      {fmtScore(fn.score)}
                    </span>
                  ) : (
                    <ScoreText
                      score={fn.score}
                      className="text-[23px] font-bold leading-none tracking-[-0.04em] tabular-nums"
                    >
                      {fmtScore(fn.score)}
                    </ScoreText>
                  )}

                  <div className="flex items-center gap-2.5">
                    <div className="flex flex-col items-end">
                      <StatLabel>Gap</StatLabel>
                      <ToneText
                        tone={scoreTone(fn.gap)}
                        className="whitespace-nowrap text-[12px] font-bold tabular-nums"
                      >
                        {arrow(fn.gap)} {fmtSigned(fn.gap)}
                      </ToneText>
                    </div>
                    <div className="h-6 w-px bg-[var(--exec-card-border)]" aria-hidden="true" />
                    <div className="flex flex-col items-end">
                      <StatLabel>{comparison}</StatLabel>
                      <ToneText
                        tone={changeTone}
                        className="whitespace-nowrap text-[12px] font-semibold tabular-nums"
                      >
                        {arrow(fn.change)} {fmtSigned(fn.change)}
                      </ToneText>
                    </div>
                  </div>
                </div>

                {isBlueB ? (
                  <div aria-hidden="true" className="relative h-[8px] w-full overflow-hidden rounded-full bg-[var(--insights-track)]">
                    <div
                      className="h-full rounded-full transition-[width] duration-300 ease-out motion-reduce:transition-none"
                      style={{
                        width: `${Math.max(0, Math.min(100, fn.score))}%`,
                        background: GRADE_B_BLUE.gradient,
                      }}
                    />
                    <span
                      className="pointer-events-none absolute top-0 bottom-0 w-[2px] bg-[var(--insights-heading)]/30"
                      style={{ left: '90%' }}
                    />
                  </div>
                ) : (
                  <ScoreBar score={fn.score} color={tone.gauge} showThreshold90 />
                )}
              </div>

              {/* Zone 3: Momentum & Lowest Team Highlight */}
              {showCalloutRow && (
                <div className="flex h-[20px] w-full items-center justify-between gap-1.5 overflow-hidden">
                  <div className="flex shrink-0 items-center">
                    {fn.isMostImproved ? (
                      <StatusPill tone="success" icon={TrendingUp}>
                        Most improved
                      </StatusPill>
                    ) : fn.fallingMonths !== null && fn.fallingMonths !== undefined && fn.fallingMonths >= 2 ? (
                      <StatusPill tone="danger" icon={TrendingDown}>
                        Falling {fn.fallingMonths} mo
                      </StatusPill>
                    ) : null}
                  </div>

                  {fn.lowestTeam && fn.lowestTeam.score < 85 && (
                    <span
                      aria-hidden="true"
                      className="truncate text-xs font-semibold text-amber-700 dark:text-amber-300"
                      title={`Lowest team: ${presentationTeamName(fn.lowestTeam.team)} (${fn.lowestTeam.score.toFixed(1)}%)`}
                    >
                      Low: {presentationTeamName(fn.lowestTeam.team)} ({fn.lowestTeam.score.toFixed(0)}%)
                    </span>
                  )}
                </div>
              )}

              {/* Zone 4: 6-Month Sparkline Chart (matches Executive Summary when live trend exists) */}
              {hasTrendCharts && (
                <div className="w-full">
                  <FunctionTrendChart
                    color={trendColor}
                    title={`${presentationTeamName(fn.functionName)} score`}
                    points={fn.trend ?? []}
                  />
                </div>
              )}

              {/* Zone 5: Uniform Bottom-Aligned Footer */}
              <div className="mt-auto flex w-full items-center justify-between gap-[8px] border-t border-[var(--insights-row-border)] pt-[9px]">
                <p
                  className="min-w-0 flex-1 truncate text-[11.5px] font-medium leading-[1.35] text-[var(--text-secondary)]"
                  title={fn.teamsList || presentationTeamName(fn.functionName)}
                >
                  {fn.teamsList || presentationTeamName(fn.functionName)}
                </p>
                <span
                  className="inline-flex min-h-[28px] shrink-0 items-center justify-center gap-[4px] rounded-[9px] border px-[10px] py-[4px] text-[11.5px] font-bold transition-all duration-200 group-hover/fcard:brightness-95"
                  style={{
                    background: fnStyle.bg,
                    color: fnStyle.color,
                    borderColor: `color-mix(in srgb, ${fnStyle.color} 26%, transparent)`,
                  }}
                >
                  Open
                  <ArrowRight
                    aria-hidden="true"
                    className="size-[12px] transition-transform duration-200 group-hover/fcard:translate-x-0.5"
                  />
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </section>
  );
}

/* -------------------------------------------------------------------------- */
/*  7. Teams at Risk (Summary) Section                                        */
/* -------------------------------------------------------------------------- */

export interface TeamsAtRiskSectionProps {
  teams: TeamAtRiskItem[];
  onSelectTeam?: (team: TeamAtRiskItem) => void;
}

function fallbackStatusLabel(row: TeamAtRiskItem): string | null {
  if (row.statusLabel) return row.statusLabel;
  if (row.grade === 'E' || row.score < 70) return 'Critical <70%';
  if (row.score < 90) return 'Below 90%';
  return row.flags[0] ?? null;
}

export function TeamsAtRiskSection({ teams, onSelectTeam }: TeamsAtRiskSectionProps) {
  const gridCols = onSelectTeam
    ? 'md:grid-cols-[minmax(0,1.45fr)_156px_118px_minmax(0,1.65fr)_132px_114px]'
    : 'md:grid-cols-[minmax(0,1.45fr)_156px_118px_minmax(0,1.65fr)_132px]';

  return (
    <section
      id="presentation-section-teams"
      data-section-label="Teams"
      aria-labelledby="teams-at-risk-heading"
      className="pms-glass-surface scroll-mt-24 rounded-2xl p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <span className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
            Risk Watchlist
          </span>
          <h2 id="teams-at-risk-heading" className="mt-0.5 text-lg font-bold text-slate-900">
            Teams at Risk (Summary)
          </h2>
        </div>
        <span className="rounded-full border border-red-200 bg-red-50 px-3 py-0.5 text-xs font-semibold text-red-700">
          {teams.length} {teams.length === 1 ? 'team' : 'teams'} flagged
        </span>
      </div>

      {teams.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">No teams in this region are on the risk list.</p>
      ) : (
        <div role="table" aria-label="Teams at Risk (Summary)" className="mt-4 flex flex-col gap-2">
          <div
            role="row"
            className={`hidden items-center gap-3 px-4 py-1.5 text-xs font-semibold text-slate-500 md:grid ${gridCols}`}
          >
            <span role="columnheader">Team &amp; Scope</span>
            <span role="columnheader">Score &amp; Grade</span>
            <span role="columnheader">Gap Share</span>
            <span role="columnheader">Primary Bottleneck KPI</span>
            <span role="columnheader">Status</span>
            {onSelectTeam && <span role="columnheader" className="text-right">Action</span>}
          </div>

          {teams.map((row, index) => {
            const lead = index === 0;
            const statusLabel = fallbackStatusLabel(row);
            const scopeMeta = [
              row.functionName,
              row.regions?.length ? row.regions.join(' + ') : null,
              row.employees && row.employees > 0
                ? `${row.employees} ${row.employees === 1 ? 'person' : 'people'}`
                : null,
              row.scoreBasis === 'leader_scorecard' ? 'Leader scorecard' : null,
            ]
              .filter(Boolean)
              .join(' · ');
            const bottleneck = row.bottleneckLabel || '—';

            return (
              <div
                role="row"
                key={`${row.functionName}-${row.team}-${(row.regions ?? []).join('-')}`}
                data-testid="monthly-risk-row"
                className={`flex flex-col gap-2.5 rounded-xl border px-4 py-3 transition-all hover:shadow-xs md:grid md:items-center md:gap-3 ${gridCols} ${
                  lead
                    ? 'border-red-200/80 bg-red-50/40'
                    : 'border-slate-200/80 bg-slate-50/50 hover:border-slate-300/90 hover:bg-white'
                }`}
              >
                {/* Col 1: Team & Scope */}
                <div role="cell" className="flex min-w-0 flex-col gap-0.5">
                  {onSelectTeam ? (
                    <button
                      type="button"
                      data-testid={`team-at-risk-${slugifyIdentifier(row.team)}`}
                      onClick={() => onSelectTeam(row)}
                      className="truncate text-left text-sm font-bold leading-snug text-slate-900 hover:text-blue-700 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
                    >
                      {row.team}
                    </button>
                  ) : (
                    <span className="truncate text-sm font-bold leading-snug text-slate-900">
                      {row.team}
                    </span>
                  )}
                  <span className="truncate text-xs text-slate-500">{scopeMeta}</span>
                </div>

                {/* Col 2: Score & Grade */}
                <div role="cell" className="flex items-center gap-2">
                  <ScoreText score={row.score} className="text-[15px] tabular-nums">
                    {fmtScore(row.score)}
                  </ScoreText>
                  <ExecGradePill score={row.score} className="!px-[8px] !py-[2px]" />
                </div>

                {/* Col 3: Gap Share */}
                <div role="cell" className="text-xs font-semibold tabular-nums text-slate-600">
                  <span className="text-slate-400 md:hidden">Gap Share: </span>
                  {row.gapSharePercent != null && row.gapSharePercent > 0
                    ? `${formatShare(row.gapSharePercent)}% of gap`
                    : `${arrow(row.gap)} ${fmtSigned(row.gap)}`}
                </div>

                {/* Col 4: Primary Bottleneck KPI */}
                <div role="cell" className="min-w-0 text-xs font-medium text-slate-800">
                  <span className="text-slate-400 md:hidden">Bottleneck: </span>
                  <span className="block truncate" title={bottleneck}>
                    {bottleneck}
                  </span>
                </div>

                {/* Col 5: Status */}
                <div role="cell" className="flex flex-wrap items-center gap-1">
                  {statusLabel ? (
                    <StatusPill tone="danger">{statusLabel}</StatusPill>
                  ) : (
                    <span className="text-xs text-slate-400">—</span>
                  )}
                </div>

                {/* Col 6: Action */}
                {onSelectTeam && (
                  <div role="cell" className="flex items-center md:justify-end">
                    <button
                      type="button"
                      onClick={() => onSelectTeam(row)}
                      className="inline-flex items-center gap-1 whitespace-nowrap text-xs font-bold text-blue-700 transition-colors hover:text-blue-800 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40"
                    >
                      Review Team
                      <ArrowRight aria-hidden="true" className="size-3.5" strokeWidth={2.2} />
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
