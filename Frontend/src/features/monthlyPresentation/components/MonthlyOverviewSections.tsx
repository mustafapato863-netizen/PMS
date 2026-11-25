import type { ReactNode } from 'react';
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Globe,
  Info,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import type { ExecutiveRegion, ExecutiveTrendPoint } from '../../executive/types';
import { periodFromKey as execPeriodFromKey } from '../../executive/compose';
import { getGradeTone, gradeTokenVar } from '../../../constants/grades';
import { ScoreBar } from '../../../components/executive/v1/ExecPrimitives';
import { formatShare } from '../../../components/executive/v1/execModel';
import { gradeGradientVar } from '../../../components/executive/v1/gradeGradient';
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

  return (
    <span
      data-grade={grade}
      className={`inline-flex items-center justify-center border ${sizeClasses}`}
      style={{
        background: gradeTokenVar(grade, 'badge-bg'),
        color: gradeTokenVar(grade, 'badge-text'),
        borderColor: gradeTokenVar(grade, 'border'),
      }}
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
      aria-label="Monthly Presentation Header"
      className="flex min-w-0 flex-col gap-4 rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs sm:p-5"
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
      className="relative flex h-full w-full scroll-mt-24 flex-col justify-between overflow-hidden rounded-2xl border border-slate-200/70 bg-white p-6 shadow-[0_10px_32px_-18px_rgba(15,23,42,0.28)] transition-shadow duration-300 hover:shadow-[0_16px_40px_-20px_rgba(15,23,42,0.34)] motion-reduce:transition-none"
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
          <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 px-4 py-3">
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
      <div className="mt-5 flex items-start gap-2.5 rounded-xl border border-slate-200/80 bg-slate-50 px-3.5 py-2.5 text-xs leading-relaxed text-slate-600">
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
  previousMonthLabel: string;
  onSelectRegion?: (region: 'EGY' | 'UAE') => void;
}

export function RegionPerformanceShareSection({
  regions,
  previousMonthLabel,
  onSelectRegion,
}: RegionPerformanceShareSectionProps) {
  if (regions.length <= 1) return null;

  const topGapRegion = [...regions]
    .filter((region) => region.gap_share_percent !== null)
    .sort((left, right) => (right.gap_share_percent ?? 0) - (left.gap_share_percent ?? 0))[0];

  return (
    <section
      id="presentation-section-regions"
      data-section-label="Regions"
      aria-labelledby="region-performance-share-heading"
      data-testid="monthly-region-performance-share"
      className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
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
                    background: gradeGradientVar(region.score),
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
            {Math.round(topGapRegion.gap_share_percent ?? 0)}% of the company gap from{' '}
            {Math.round(topGapRegion.headcount_share_percent)}% of evaluated headcount.
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
      className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
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
          const style = GRADE_STYLES[row.grade];
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
                    style={{ width: `${Math.max(row.percentage, 3)}%` }}
                    className={`h-full rounded-full transition-all duration-300 ${style.barFill}`}
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
    <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200/80 bg-slate-50/60 p-3.5 transition-colors hover:bg-slate-50">
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
      className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
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

export function FunctionsOverviewSection({
  functions,
  previousMonthLabel,
  onSelectFunction,
}: FunctionsOverviewSectionProps) {
  const sortedFunctions = [...functions].sort((a, b) => a.score - b.score);

  return (
    <section
      id="presentation-section-functions"
      data-section-label="Functions"
      aria-labelledby="functions-overview-heading"
      className="pms-glass-surface scroll-mt-24 rounded-2xl p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <span className="text-xs font-semibold tracking-wider text-[var(--text-muted)] uppercase">
            Functional Breakdown
          </span>
          <div className="mt-0.5 flex items-center gap-2.5">
            <h2
              id="functions-overview-heading"
              className="text-lg font-bold text-[var(--insights-heading)]"
            >
              Functions Overview
            </h2>
            <span className="rounded-full border border-[var(--pms-glass-stage-border)] bg-[var(--pms-glass-stage-bg)] px-2.5 py-0.5 text-xs font-semibold text-[var(--text-secondary)]">
              {sortedFunctions.length} functions
            </span>
          </div>
        </div>
        <p className="text-xs font-medium text-[var(--text-muted)]">
          Click any function card to open its deep-dive presentation page
        </p>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {sortedFunctions.map((fn) => {
          const tone = getGradeTone(fn.score);
          const formattedGap = `${fn.gap > 0 ? '+' : ''}${fn.gap.toFixed(1)}%`;
          const hasChange = fn.change !== null && fn.change !== undefined;
          const isPositiveChange = (fn.change ?? 0) >= 0;

          return (
            <button
              key={fn.functionName}
              type="button"
              data-testid={`function-card-${fn.slug}`}
              data-grade={fn.grade}
              onClick={() => onSelectFunction(fn)}
              className="pms-glass-surface pms-glass-surface--interactive group relative flex flex-col justify-between overflow-hidden rounded-[18px] p-4 text-left transition-all duration-200 hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent-ring)]"
              style={{
                backgroundImage: `radial-gradient(circle at 95% 6%, color-mix(in srgb, ${tone.gauge} ${fn.hasMajorIssue ? 18 : 14}%, transparent) 0%, transparent 66%), var(--pms-glass-card-bg)`,
                borderColor: `color-mix(in srgb, ${tone.gauge} ${fn.hasMajorIssue ? 42 : 22}%, var(--pms-glass-card-border))`,
                boxShadow: fn.hasMajorIssue
                  ? `0 0 0 1px color-mix(in srgb, ${tone.gauge} 24%, transparent), var(--pms-glass-card-shadow)`
                  : undefined,
              }}
            >
              {/* Smooth Linear-Gradient Top Grade Accent Strip */}
              <span
                aria-hidden="true"
                className="pointer-events-none absolute inset-x-0 top-0 h-[3px]"
                style={{ background: gradeGradientVar(fn.score) }}
              />

              <div className="w-full">
                {/* Highlight Badge for Major Issues */}
                {fn.hasMajorIssue && (
                  <div className="mb-3">
                    <span
                      className="inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[11px] font-bold"
                      style={{
                        background: tone.badgeBg,
                        color: tone.badgeText,
                        borderColor: tone.border,
                      }}
                    >
                      <AlertTriangle className="size-3 shrink-0" aria-hidden="true" />
                      {fn.highlightBadge ?? 'Major issue — deep dive next'}
                    </span>
                  </div>
                )}

                <div className="flex items-start justify-between gap-2">
                  <h3 className="text-base font-bold text-[var(--insights-heading)] transition-colors group-hover:text-[var(--insights-accent-text)]">
                    {fn.functionName}
                  </h3>
                  <GradePill grade={fn.grade} size="sm" />
                </div>

                {/* Frosted Metric Stage matching Executive Summary Function Cards */}
                <div className="pms-glass-stage mt-3 space-y-2.5 rounded-[12px] px-3 py-2.5">
                  <div
                    className="text-3xl font-extrabold leading-none tracking-tight tabular-nums"
                    style={{ color: tone.text }}
                  >
                    {fn.score.toFixed(1)}%
                  </div>

                  <ScoreBar score={fn.score} color={tone.gauge} showThreshold90 />

                  <div className="space-y-1 border-t border-[var(--pms-glass-stage-border)] pt-2 text-xs">
                    <div className="flex items-center justify-between text-[var(--text-secondary)]">
                      <span>Gap to target</span>
                      <span className="font-semibold tabular-nums text-[var(--insights-heading)]">{formattedGap}</span>
                    </div>
                    <div className="flex items-center justify-between text-[var(--text-secondary)]">
                      <span>vs {previousMonthLabel}</span>
                      {hasChange ? (
                        <span
                          className={`font-semibold tabular-nums ${
                            isPositiveChange ? 'text-emerald-700 dark:text-emerald-400' : 'text-red-700 dark:text-rose-400'
                          }`}
                        >
                          {isPositiveChange ? '+' : ''}
                          {fn.change!.toFixed(1)}%
                        </span>
                      ) : (
                        <span className="text-[var(--text-muted)]">No prior baseline</span>
                      )}
                    </div>
                  </div>
                </div>

                {fn.teamsList && (
                  <p className="mt-2.5 line-clamp-1 text-[11px] text-[var(--text-muted)]" title={fn.teamsList}>
                    {fn.teamsList}
                  </p>
                )}
              </div>

              <div className="mt-3.5 flex w-full items-center justify-between border-t border-[var(--pms-glass-stage-border)] pt-2.5 text-[11px] font-medium text-[var(--text-muted)]">
                <span>
                  {fn.teamsCount} {fn.teamsCount === 1 ? 'team' : 'teams'} · {fn.headcount} HC
                </span>
                <span className="inline-flex items-center gap-0.5 font-semibold text-[var(--insights-accent-text)] transition-transform group-hover:translate-x-0.5">
                  Deep dive
                  <ArrowRight className="size-3" aria-hidden="true" />
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

export function TeamsAtRiskSection({ teams, onSelectTeam }: TeamsAtRiskSectionProps) {
  return (
    <section
      id="presentation-section-teams"
      data-section-label="Teams"
      aria-labelledby="teams-at-risk-heading"
      className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
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
          {teams.length} teams flagged
        </span>
      </div>

      {teams.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">No teams in this region are on the risk list.</p>
      ) : (
      <div className="mt-4 overflow-x-auto">
        <table className="w-full border-collapse text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-xs font-semibold tracking-wider text-slate-500 uppercase">
              <th className="py-3 pr-4">Team</th>
              <th className="px-4 py-3">Function</th>
              <th className="px-4 py-3 text-right">Score</th>
              <th className="px-4 py-3 text-center">Grade</th>
              <th className="px-4 py-3 text-right">Gap</th>
              <th className="py-3 pl-4">Why flagged</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {teams.map((row) => {
              const style = GRADE_STYLES[row.grade];
              return (
                <tr
                  key={`${row.functionName}-${row.team}`}
                  className="transition-colors hover:bg-slate-50/80"
                >
                  <td className="py-3 pr-4 font-semibold text-slate-900">
                    {onSelectTeam ? (
                      <button
                        type="button"
                        data-testid={`team-at-risk-${slugifyIdentifier(row.team)}`}
                        onClick={() => onSelectTeam(row)}
                        className="font-semibold text-slate-900 hover:text-blue-700"
                      >
                        {row.team}
                      </button>
                    ) : (
                      row.team
                    )}
                  </td>
                  <td className="px-4 py-3 text-slate-600">{row.functionName}</td>
                  <td className={`px-4 py-3 text-right font-bold ${style.scoreText}`}>
                    {row.score.toFixed(1)}%
                  </td>
                  <td className="px-4 py-3 text-center">
                    <GradePill grade={row.grade} size="sm" />
                  </td>
                  <td className="px-4 py-3 text-right font-semibold text-red-600">
                    {row.gap > 0 ? `+${row.gap.toFixed(1)}%` : `${row.gap.toFixed(1)}%`}
                  </td>
                  <td className="py-3 pl-4">
                    <div className="flex flex-wrap gap-1.5">
                      {row.flags.map((flag) => (
                        <span
                          key={flag}
                          className="inline-flex items-center rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-medium text-slate-700"
                        >
                          {flag}
                        </span>
                      ))}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      )}
    </section>
  );
}
