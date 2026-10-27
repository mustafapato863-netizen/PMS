import type { ReactNode } from 'react';
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Info,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from 'lucide-react';
import {
  GRADE_STYLES,
  type FunctionOverviewItem,
  type GradeDistributionRow,
  type GradeLetter,
  type MonthlyOverviewData,
  type ScoreDriverItem,
  type TeamAtRiskItem,
  type TrendPoint,
} from '../monthlyOverviewData';
import { slugifyIdentifier } from '../callCenterDeepDiveData';
import { LineChart } from '../../../components/balanced-scorecard/LineChart';

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
  const style = GRADE_STYLES[grade];
  const sizeClasses =
    size === 'lg'
      ? 'px-3.5 py-1 text-sm font-bold rounded-xl'
      : size === 'sm'
      ? 'px-2 py-0.5 text-xs font-bold rounded-md'
      : 'px-2.5 py-0.5 text-xs font-bold rounded-lg';

  return (
    <span
      className={`inline-flex items-center justify-center border ${style.badgeBg} ${style.badgeText} ${style.badgeBorder} ${sizeClasses}`}
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
  monthLabel: string;
  regionCode: 'EGY' | 'UAE';
  pageIndicatorLabel: string;
  toolbar?: ReactNode;
}

export function MonthlyOverviewHeader({
  title,
  flowName,
  regionName,
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
                : 'border-blue-200 bg-blue-50 text-blue-700'
            }`}
          >
            <span className="size-1.5 rounded-full bg-current" />
            {regionName}
          </span>

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
            {regionName} · {monthLabel}
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
      className="relative flex scroll-mt-24 flex-col justify-between overflow-hidden rounded-2xl border border-slate-200/70 bg-white p-6 shadow-[0_10px_32px_-18px_rgba(15,23,42,0.28)] transition-shadow duration-300 hover:shadow-[0_16px_40px_-20px_rgba(15,23,42,0.34)] motion-reduce:transition-none"
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

        {/* Three Small Metrics: Current / Target / Gap */}
        <div className="mt-6 grid grid-cols-3 gap-3">
          <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 px-4 py-3">
            <div className="text-xs font-medium text-slate-500">Current</div>
            <div className="mt-1 text-xl font-bold text-slate-900">
              {overall.score.toFixed(1)}%
            </div>
          </div>

          <div className="rounded-xl border border-slate-200/80 bg-slate-50/70 px-4 py-3">
            <div className="text-xs font-medium text-slate-500">Target</div>
            <div className="mt-1 text-xl font-bold text-slate-900">
              {overall.target.toFixed(1)}%
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
}

export function SixMonthTrendCard({ trend }: SixMonthTrendCardProps) {
  const firstScore = trend[0]?.score ?? 0;
  const lastPoint = trend[trend.length - 1];
  const lastScore = lastPoint?.score ?? 0;
  const sixMonthDelta = Number((lastScore - firstScore).toFixed(1));
  const target = trend.find((point) => Number.isFinite(point.target))?.target ?? lastPoint?.target ?? 100;
  const history = trend.map((point) => {
    const keyed = /^(\d{4})-(\d{2})$/.exec(point.key);
    return {
      // Numeric month keeps the chart's UTC label on the bound period. A name like "Apr"
      // is parsed as local midnight and can shift a month in positive offsets.
      month: keyed ? String(Number(keyed[2])) : point.month,
      year: keyed ? Number(keyed[1]) : Number(point.key.slice(0, 4)) || 0,
      score: point.score,
    };
  });
  const targetLabel = Number.isInteger(target) ? target.toFixed(0) : target.toFixed(1);

  return (
    <section
      id="presentation-section-trend"
      data-section-label="Trend"
      aria-labelledby="six-month-trend-heading"
      data-testid="six-month-score-trend"
      className="flex scroll-mt-24 flex-col justify-between rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <span className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
            Trajectory
          </span>
          <h2 id="six-month-trend-heading" className="mt-0.5 text-lg font-bold text-slate-900">
            6-Month Score Trend
          </h2>
        </div>

        <div className="flex items-center gap-3 text-xs font-medium text-slate-500">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-0.5 w-4 border-t-2 border-dashed border-emerald-600" />
            Target {targetLabel}%
          </span>
          <span className="rounded-md bg-emerald-50 px-2 py-0.5 font-semibold text-emerald-700">
            {sixMonthDelta >= 0 ? `+${sixMonthDelta}%` : `${sixMonthDelta}%`} since{' '}
            {trend[0]?.month}
          </span>
        </div>
      </div>

      <div className="mt-4" data-testid="overview-trend-chart">
        <LineChart history={history} targetValue={target} height={176} showTarget />
      </div>

      <p className="mt-3 text-xs text-slate-500">
        {trend[0]?.month} {firstScore.toFixed(1)}% to {lastPoint?.month} {lastScore.toFixed(1)}%.
      </p>
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
          <span className="inline-flex items-center rounded-md border border-slate-200 bg-white px-2 py-0.5 text-[11px] font-medium text-slate-600">
            {betterText}
          </span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span className="font-semibold text-slate-700">{item.functionName}</span>
          <span>·</span>
          <span>{item.team}</span>
          <span>·</span>
          <span>Actual: {item.actualValue}</span>
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
      className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <span className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
            Functional Breakdown
          </span>
          <div className="mt-0.5 flex items-center gap-2.5">
            <h2
              id="functions-overview-heading"
              className="text-lg font-bold text-slate-900"
            >
              Functions Overview
            </h2>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-semibold text-slate-600">
              {sortedFunctions.length} functions
            </span>
          </div>
        </div>
        <p className="text-xs font-medium text-slate-500">
          Click any function card to open its deep-dive presentation page
        </p>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {sortedFunctions.map((fn) => {
          const style = GRADE_STYLES[fn.grade];
          const formattedGap = `${fn.gap > 0 ? '+' : ''}${fn.gap.toFixed(1)}%`;
          const hasChange = fn.change !== null && fn.change !== undefined;
          const isPositiveChange = (fn.change ?? 0) >= 0;

          return (
            <button
              key={fn.functionName}
              type="button"
              data-testid={`function-card-${fn.slug}`}
              onClick={() => onSelectFunction(fn)}
              className={`group flex flex-col justify-between rounded-2xl border p-4 text-left transition-all duration-200 hover:-translate-y-0.5 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                fn.hasMajorIssue
                  ? 'border-orange-300 bg-orange-50/25 ring-2 ring-orange-200/80'
                  : 'border-slate-200/90 bg-white hover:border-slate-300'
              }`}
            >
              <div>
                {/* Highlight Badge for Major Issues */}
                {fn.hasMajorIssue && (
                  <div className="mb-3">
                    <span className="inline-flex items-center gap-1 rounded-full border border-orange-300 bg-orange-100/90 px-2.5 py-0.5 text-[11px] font-bold text-orange-800">
                      <AlertTriangle className="size-3 shrink-0" />
                      {fn.highlightBadge ?? 'Major issue — deep dive next'}
                    </span>
                  </div>
                )}

                <div className="flex items-start justify-between gap-2">
                  <h3 className="text-base font-bold text-slate-900 group-hover:text-blue-600">
                    {fn.functionName}
                  </h3>
                  <GradePill grade={fn.grade} size="sm" />
                </div>

                <div className={`mt-3 text-3xl font-extrabold tracking-tight ${style.scoreText}`}>
                  {fn.score.toFixed(1)}%
                </div>

                <div className="mt-3 space-y-1 border-t border-slate-100 pt-2.5 text-xs">
                  <div className="flex items-center justify-between text-slate-600">
                    <span>Gap to target</span>
                    <span className="font-semibold text-slate-800">{formattedGap}</span>
                  </div>
                  <div className="flex items-center justify-between text-slate-600">
                    <span>vs {previousMonthLabel}</span>
                    {hasChange ? (
                      <span
                        className={`font-semibold ${
                          isPositiveChange ? 'text-emerald-700' : 'text-red-700'
                        }`}
                      >
                        {isPositiveChange ? '+' : ''}
                        {fn.change!.toFixed(1)}%
                      </span>
                    ) : (
                      <span className="text-slate-400">No prior baseline</span>
                    )}
                  </div>
                </div>

                {fn.teamsList && (
                  <p className="mt-2.5 line-clamp-1 text-[11px] text-slate-400" title={fn.teamsList}>
                    {fn.teamsList}
                  </p>
                )}
              </div>

              <div className="mt-3.5 flex items-center justify-between border-t border-slate-100 pt-2.5 text-[11px] font-medium text-slate-500">
                <span>
                  {fn.teamsCount} {fn.teamsCount === 1 ? 'team' : 'teams'} · {fn.headcount} HC
                </span>
                <span className="inline-flex items-center gap-0.5 font-semibold text-blue-600 group-hover:translate-x-0.5 transition-transform">
                  Deep dive
                  <ArrowRight className="size-3" />
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
