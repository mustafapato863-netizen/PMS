import {
  AlertTriangle,
  ArrowUpRight,
  BriefcaseBusiness,
  ChartNoAxesCombined,
  ChevronRight,
  CircleAlert,
  Lightbulb,
  Target,
  TrendingUp,
  Users,
} from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { GRADE_PALETTE } from '../../constants/grades';
import { buildMarketingInsights } from '../../features/marketing/marketingAnalytics';
import type {
  MarketingAnalytics,
  MarketingInsight,
  MarketingPositionSummary,
  MarketingTeamConfig,
} from '../../features/marketing/types';
import KpiCard from '../common/KpiCard';
import MoMIndicator from '../common/MoMIndicator';

interface MarketingOverviewProps {
  analytics: MarketingAnalytics;
  config: MarketingTeamConfig;
  selectedPosition?: string;
  onOpenPosition: (position: string) => void;
}

const panelClass = 'rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5 shadow-sm';

const getPositionStatus = (
  summary: MarketingPositionSummary,
  config: MarketingTeamConfig,
) => {
  if (summary.dataStatus === 'No Uploaded Data') {
    return { label: 'No Data', tone: 'bg-slate-500/10 text-[var(--text-muted)] border-slate-500/15' };
  }
  if (summary.dataStatus === 'No Results for Filters') {
    return { label: 'No Results', tone: 'bg-amber-500/10 text-amber-700 border-amber-500/20 dark:text-amber-300' };
  }
  if (summary.classDECount > 0 || (summary.averageScore ?? 0) < config.grade_thresholds.C) {
    return { label: 'At Risk', tone: 'bg-rose-500/10 text-rose-600 border-rose-500/20 dark:text-rose-400' };
  }
  return { label: 'On Track', tone: 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:text-emerald-400' };
};

const insightTone = {
  critical: {
    icon: CircleAlert,
    iconClass: 'text-rose-600 dark:text-rose-400',
    container: 'border-rose-500/15 bg-rose-500/[0.055]',
  },
  warning: {
    icon: AlertTriangle,
    iconClass: 'text-amber-600 dark:text-amber-400',
    container: 'border-amber-500/15 bg-amber-500/[0.055]',
  },
  positive: {
    icon: TrendingUp,
    iconClass: 'text-emerald-600 dark:text-emerald-400',
    container: 'border-emerald-500/15 bg-emerald-500/[0.055]',
  },
  neutral: {
    icon: Lightbulb,
    iconClass: 'text-violet-600 dark:text-violet-400',
    container: 'border-violet-500/15 bg-violet-500/[0.055]',
  },
} as const;

const MarketingOverview = ({
  analytics,
  config,
  selectedPosition,
  onOpenPosition,
}: MarketingOverviewProps) => {
  const visiblePositions = analytics.positionSummaries.filter(
    (summary) => !selectedPosition || summary.position === selectedPosition,
  );
  const gradeData = Object.entries(analytics.gradeDistribution).map(([grade, value]) => ({
    name: `Grade ${grade}`,
    grade,
    value,
    color: GRADE_PALETTE[grade as keyof typeof GRADE_PALETTE].text,
  }));
  const gradeTotal = gradeData.reduce((total, item) => total + item.value, 0);
  const performanceData = visiblePositions
    .filter((position) => position.averageScore !== null)
    .map((position) => ({
      position: position.position,
      score: position.averageScore,
      atRisk: position.classDECount > 0 || (position.averageScore ?? 0) < config.grade_thresholds.C,
    }))
    .sort((left, right) => (right.score ?? 0) - (left.score ?? 0));
  const attention = visiblePositions
    .filter((position) => (
      position.dataStatus === 'Active'
      && (position.classDECount > 0 || (position.averageScore ?? 0) < config.grade_thresholds.C)
    ))
    .sort((left, right) => (
      right.classDECount - left.classDECount
      || (left.averageScore ?? 0) - (right.averageScore ?? 0)
    ));
  const insights = buildMarketingInsights(
    { ...analytics, positionSummaries: visiblePositions },
    config.grade_thresholds,
  );
  const headlineInsight = insights[0];
  const HeadlineIcon = insightTone[headlineInsight.tone].icon;
  const scopedPositionCount = selectedPosition ? 1 : config.available_positions.length;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3 rounded-xl border border-violet-500/15 bg-violet-500/[0.045] px-4 py-3">
        <HeadlineIcon size={18} className={`shrink-0 ${insightTone[headlineInsight.tone].iconClass}`} />
        <p className="text-sm font-semibold text-[var(--text-secondary)]">
          <span className="font-extrabold text-[var(--text-primary)]">{headlineInsight.title}</span>{' '}
          {headlineInsight.detail}
        </p>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard
          label="Active Employees"
          value={String(analytics.employeeCount)}
          icon={<Users size={18} />}
          trendDelta={analytics.employeeDelta ?? undefined}
          accent="border-l-violet-500"
          variant="flat"
        />
        <KpiCard
          label="Positions With Data"
          value={`${analytics.positionsWithData} / ${scopedPositionCount}`}
          icon={<BriefcaseBusiness size={18} />}
          trendDelta={analytics.positionCountDelta ?? undefined}
          accent="border-l-blue-500"
          variant="flat"
        />
        <KpiCard
          label="Marketing Average"
          value={`${analytics.averageScore.toFixed(1)}%`}
          icon={<ChartNoAxesCombined size={18} />}
          trendDelta={analytics.scoreDelta ?? undefined}
          accent="border-l-emerald-500"
          variant="flat"
        />
        <KpiCard
          label="Employees Below Target"
          value={String(analytics.belowTargetCount)}
          icon={<CircleAlert size={18} />}
          trendDelta={analytics.belowTargetDelta ?? undefined}
          lowerTrendIsBetter
          showStableTrend
          accent="border-l-orange-500"
          variant="flat"
        />
      </div>

      <section aria-labelledby="marketing-positions-heading">
        <div className="mb-3">
          <h3 id="marketing-positions-heading" className="heading-3">Position Overview</h3>
          <p className="mt-1 text-xs font-medium text-[var(--text-muted)]">
            Performance summary by position for the selected filters.
          </p>
        </div>
        <div className={`grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3 ${
          visiblePositions.length >= 5 ? 'xl:grid-cols-4 2xl:grid-cols-5' : 'xl:grid-cols-4'
        }`}>
          {visiblePositions.map((summary) => {
            const status = getPositionStatus(summary, config);
            const noData = summary.dataStatus !== 'Active';
            return (
              <article
                key={summary.position}
                className={`flex min-h-[240px] flex-col rounded-2xl border bg-[var(--bg-surface)] p-4 shadow-sm transition ${
                  noData
                    ? 'border-[var(--border-light)] opacity-60'
                    : status.label === 'At Risk'
                      ? 'border-rose-500/25'
                      : 'border-emerald-500/20'
                }`}
              >
                <div>
                  <h4 className="truncate text-sm font-extrabold text-[var(--text-primary)]" title={summary.position}>
                    {summary.position}
                  </h4>
                  <span className={`mt-2 inline-flex rounded-full border px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wide ${status.tone}`}>
                    {status.label}
                  </span>
                </div>

                <div className="mt-4 flex items-center gap-2">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-violet-500/10 text-violet-600 dark:text-violet-400">
                    <BriefcaseBusiness size={18} />
                  </span>
                  <div className="grid flex-1 grid-cols-3 gap-1.5">
                    <PositionMetric label="Employees" value={String(summary.employeeCount)} />
                    <PositionMetric label="KPIs" value={String(summary.kpiCount)} />
                    <PositionMetric label="Score" value={summary.averageScore === null ? '—' : `${summary.averageScore.toFixed(1)}%`} />
                  </div>
                </div>

                <div className="mt-4 flex-1 border-t border-[var(--border-light)] pt-3">
                  <p className="text-[9px] font-bold uppercase tracking-wide text-[var(--text-muted)]">Weakest KPI</p>
                  <div className="mt-1 flex items-center justify-between gap-2">
                    <span className="min-w-0 truncate text-xs font-extrabold text-[var(--text-primary)]">
                      {summary.weakestKpi?.label || '—'}
                    </span>
                    <MoMIndicator delta={summary.scoreDelta} showStable />
                  </div>
                </div>

                <button
                  type="button"
                  onClick={() => onOpenPosition(summary.position)}
                  className="mt-3 flex min-h-10 w-full items-center justify-center gap-2 rounded-lg border border-violet-500/25 px-3 py-2 text-xs font-extrabold text-violet-700 transition hover:bg-violet-600 hover:text-white focus:outline-none focus:ring-2 focus:ring-violet-500/30 dark:text-violet-300"
                >
                  Open Position <ArrowUpRight size={14} />
                </button>
              </article>
            );
          })}
        </div>
      </section>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <section className={`${panelClass} xl:col-span-5`} aria-labelledby="performance-position-title">
          <PanelTitle icon={<Target size={16} className="text-violet-600" />} id="performance-position-title">
            Performance by Position
          </PanelTitle>
          {performanceData.length ? (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={performanceData} layout="vertical" margin={{ left: 30, right: 25, top: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
                <YAxis type="category" dataKey="position" width={135} tick={{ fontSize: 10, fill: 'var(--text-secondary)' }} axisLine={false} tickLine={false} />
                <Tooltip formatter={(value) => [`${Number(value).toFixed(1)}%`, 'Average score']} />
                <Bar dataKey="score" radius={[0, 6, 6, 0]} barSize={17}>
                  {performanceData.map((entry) => (
                    <Cell key={entry.position} fill={entry.atRisk ? '#EF4444' : '#7C3AED'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <ChartEmpty message="No position results for the selected filters." />}
        </section>

        <section className={`${panelClass} xl:col-span-3`} aria-labelledby="grade-distribution-title">
          <PanelTitle id="grade-distribution-title">Marketing Grade Distribution</PanelTitle>
          {analytics.currentRecords.length ? (
            <div className="grid items-center gap-2 sm:grid-cols-[1fr_auto] xl:grid-cols-1">
              <div className="relative h-[170px]">
                <ResponsiveContainer width="100%" height={170} minWidth={0}>
                  <PieChart>
                    <Pie data={gradeData} dataKey="value" nameKey="name" innerRadius={48} outerRadius={70} paddingAngle={2}>
                      {gradeData.map((entry) => <Cell key={entry.grade} fill={entry.color} />)}
                    </Pie>
                    <Tooltip formatter={(value) => [`${Number(value)} employees`, 'Count']} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-2xl font-extrabold text-[var(--text-primary)]">{gradeTotal}</span>
                  <span className="text-[10px] font-semibold text-[var(--text-muted)]">Employees</span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-x-4 gap-y-2 xl:grid-cols-1">
                {gradeData.map((grade) => (
                  <div key={grade.grade} className="flex items-center justify-between gap-3 text-[11px] font-semibold">
                    <span className="flex items-center gap-2 text-[var(--text-secondary)]">
                      <span className="h-2 w-2 rounded-full" style={{ backgroundColor: grade.color }} />
                      {grade.name}
                    </span>
                    <span className="text-[var(--text-primary)]">
                      {gradeTotal ? `${((grade.value / gradeTotal) * 100).toFixed(0)}%` : '0%'} ({grade.value})
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : <ChartEmpty message="No grade data for this period." compact />}
        </section>

        <section className={`${panelClass} xl:col-span-4`} aria-labelledby="attention-title">
          <PanelTitle icon={<AlertTriangle size={16} className="text-amber-600" />} id="attention-title">
            Positions Requiring Attention
          </PanelTitle>
          <div className="mt-2 divide-y divide-[var(--border-light)]">
            {attention.length ? attention.slice(0, 4).map((position, index) => (
              <button
                key={position.position}
                type="button"
                onClick={() => onOpenPosition(position.position)}
                className="flex min-h-16 w-full items-center gap-3 py-3 text-left transition hover:bg-[var(--bg-sunken)]/50"
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-amber-500/10 text-xs font-extrabold text-amber-700 dark:text-amber-300">
                  {index + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-extrabold text-[var(--text-primary)]">{position.position}</span>
                  <span className="mt-1 block truncate text-[10px] font-medium text-[var(--text-muted)]">
                    Weakest KPI: {position.weakestKpi?.label || 'Not available'}
                  </span>
                </span>
                <span className="text-right">
                  <span className="block text-sm font-extrabold text-[var(--text-primary)]">{position.averageScore?.toFixed(1)}%</span>
                  <MoMIndicator delta={position.scoreDelta} showStable />
                </span>
              </button>
            )) : <ChartEmpty message="No active position currently requires attention." compact />}
          </div>
        </section>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-12">
        <section className={`${panelClass} xl:col-span-7`} aria-labelledby="marketing-trend-title">
          <PanelTitle id="marketing-trend-title">Marketing Score Trend</PanelTitle>
          {analytics.trend.some((point) => point.employeeCount > 0) ? (
            <ResponsiveContainer width="100%" height={250}>
              <LineChart data={analytics.trend} margin={{ top: 20, right: 15, left: -15 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" vertical={false} />
                <XAxis dataKey="period" tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
                <YAxis domain={[0, 100]} tick={{ fontSize: 10, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
                <Tooltip formatter={(value) => [`${Number(value).toFixed(1)}%`, 'Average score']} />
                <Line type="monotone" dataKey="score" stroke="#7C3AED" strokeWidth={2.5} dot={{ r: 3.5, fill: '#7C3AED' }} activeDot={{ r: 5 }} />
              </LineChart>
            </ResponsiveContainer>
          ) : <ChartEmpty message="Trend appears after performance data is uploaded." />}
        </section>

        <section className={`${panelClass} xl:col-span-5`} aria-labelledby="key-insights-title">
          <PanelTitle icon={<Target size={16} className="text-violet-600" />} id="key-insights-title">
            Key Insights & Next Steps
          </PanelTitle>
          <div className="mt-3 space-y-2.5">
            {insights.slice(0, 3).map((insight) => (
              <InsightRow key={insight.id} insight={insight} onOpenPosition={onOpenPosition} />
            ))}
          </div>
        </section>
      </div>
    </div>
  );
};

const PositionMetric = ({ label, value }: { label: string; value: string }) => (
  <div className="flex min-w-0 flex-col items-center justify-center rounded-xl border border-[var(--border-light)]/50 bg-[var(--bg-sunken)]/60 px-1 py-1.5 text-center">
    <span className="truncate max-w-full text-[9px] font-extrabold uppercase tracking-tight text-[var(--text-muted)]">{label}</span>
    <span className="mt-0.5 whitespace-nowrap text-xs font-black text-[var(--text-primary)] tabular-nums">{value}</span>
  </div>
);

const PanelTitle = ({
  id,
  icon,
  children,
}: {
  id: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) => (
  <div className="mb-3 flex items-center gap-2">
    {icon}
    <h3 id={id} className="text-sm font-extrabold text-[var(--text-primary)]">{children}</h3>
  </div>
);

const InsightRow = ({
  insight,
  onOpenPosition,
}: {
  insight: MarketingInsight;
  onOpenPosition: (position: string) => void;
}) => {
  const style = insightTone[insight.tone];
  const Icon = style.icon;
  return (
    <button
      type="button"
      disabled={!insight.position}
      onClick={() => insight.position && onOpenPosition(insight.position)}
      className={`flex min-h-16 w-full items-center gap-3 rounded-xl border p-3 text-left ${style.container} ${
        insight.position ? 'transition hover:-translate-y-0.5' : 'cursor-default'
      }`}
    >
      <Icon size={17} className={`shrink-0 ${style.iconClass}`} />
      <span className="min-w-0 flex-1">
        <span className="block text-xs font-extrabold text-[var(--text-primary)]">{insight.title}</span>
        <span className="mt-1 block text-[10px] font-medium leading-4 text-[var(--text-muted)]">{insight.detail}</span>
      </span>
      {insight.position && <ChevronRight size={15} className="shrink-0 text-[var(--text-muted)]" />}
    </button>
  );
};

const ChartEmpty = ({ message, compact = false }: { message: string; compact?: boolean }) => (
  <div className={`flex items-center justify-center rounded-xl border border-dashed border-[var(--border-medium)] bg-[var(--bg-sunken)]/30 px-5 text-center text-xs font-semibold text-[var(--text-muted)] ${compact ? 'min-h-32' : 'min-h-[235px]'}`}>
    {message}
  </div>
);

export default MarketingOverview;
