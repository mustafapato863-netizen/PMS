import { Activity, CircleAlert } from 'lucide-react';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { InsightKpiTrend } from '../../features/insights/types';
import type { KpiStatus } from './overview/insightsOverviewModel';
import { kpiTrendRows } from './kpiTrendRows';

const STATUS_COLOR: Record<KpiStatus, string> = {
  on_track: '#059669',
  at_risk: '#d97706',
  critical: '#e11d48',
};
const STATUS_LABEL: Record<KpiStatus, string> = {
  on_track: 'On track',
  at_risk: 'At risk',
  critical: 'Critical',
};

function formatDisplayValue(value: number | null, unit: string | null) {
  if (value === null) return 'No data';
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${unit === '%' ? '%' : unit ? ` ${unit}` : ''}`;
}

export default function KpiSixMonthTrend({ trend }: { trend: InsightKpiTrend }) {
  const data = kpiTrendRows(trend);
  const lowerBetter = trend.direction === 'lower_better';
  const measuredMonths = trend.points.filter((point) => point.actual_value !== null).length;

  return (
    <section className="border-t border-[var(--border-light)] px-5 pb-6 pt-5 md:px-7" aria-labelledby="selected-kpi-trend-title">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-blue-500/10 text-blue-600"><Activity size={16} /></span>
          <div>
            <h3 id="selected-kpi-trend-title" className="text-sm font-extrabold text-[var(--text-primary)]">6-Month KPI Trend</h3>
            <p className="text-xs font-semibold text-[var(--text-muted)]">
              {trend.kpi_label} · Actual vs target
              {/* The Y axis is reversed for lower-is-better KPIs so "up" always reads as better. */}
              {lowerBetter && <span data-testid="kpi-trend-direction" className="ml-1 text-[var(--text-faint)]">· Lower is better (axis reversed)</span>}
            </p>
          </div>
        </div>
        <span className="rounded-full bg-[var(--bg-sunken)] px-3 py-1 text-[10px] font-bold text-[var(--text-muted)]">
          {measuredMonths} of 6 months measured
        </span>
      </div>

      {measuredMonths ? (
        <div className="mt-4 h-[225px] min-h-[225px] min-w-0 w-full" aria-label={`${trend.kpi_label} six month actual and target trend`}>
          <ResponsiveContainer width="100%" height={250} minWidth={0} minHeight={250}>
            <LineChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--border-light)" strokeDasharray="4 4" />
              <XAxis dataKey="period" axisLine={false} tickLine={false} tick={{ fill: 'var(--text-muted)', fontSize: 10, fontWeight: 600 }} />
              <YAxis
                axisLine={false}
                tickLine={false}
                reversed={lowerBetter}
                width={46}
                tick={{ fill: 'var(--text-muted)', fontSize: 10 }}
                tickFormatter={(value) => `${value}${trend.unit === '%' ? '%' : ''}`}
              />
              <Tooltip
                contentStyle={{
                  border: '1px solid var(--border-light)',
                  borderRadius: 12,
                  background: 'var(--bg-surface)',
                  color: 'var(--text-primary)',
                  fontSize: 12,
                }}
                formatter={(value, name) => [
                  formatDisplayValue(typeof value === 'number' ? value : null, trend.unit),
                  name === 'actual' ? 'Actual' : 'Target',
                ]}
                labelFormatter={(label, payload) => {
                  const row = payload?.[0]?.payload as ReturnType<typeof kpiTrendRows>[number] | undefined;
                  const records = row?.records ?? 0;
                  const status = row?.status ? ` · ${STATUS_LABEL[row.status]}${row.achievement !== null ? ` (${row.achievement.toFixed(0)}% of target)` : ''}` : '';
                  return `${label} · ${records} measured record${records === 1 ? '' : 's'}${status}`;
                }}
              />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 11, fontWeight: 700 }} formatter={(value) => value === 'actual' ? 'Actual' : 'Target'} />
              <Line type="monotone" dataKey="actual" name="actual" stroke="#2563eb" strokeWidth={3} connectNulls={false} dot={(props: { cx?: number; cy?: number; index?: number; payload?: { status: KpiStatus | null } }) => {
                  // Dot colour = per-point status (on track / at risk / critical), consistent with the axis direction.
                  if (props.cx === undefined || props.cy === undefined || props.payload?.status === undefined) return <g key={props.index} />;
                  const fill = props.payload.status ? STATUS_COLOR[props.payload.status] : '#2563eb';
                  return <circle key={props.index} cx={props.cx} cy={props.cy} r={4} fill={fill} strokeWidth={2} stroke="var(--bg-surface)" data-status={props.payload.status ?? 'unknown'} />;
                }} activeDot={{ r: 6 }} />
              <Line type="monotone" dataKey="target" name="target" stroke="#f59e0b" strokeWidth={2} strokeDasharray="6 5" connectNulls={false} dot={{ r: 3, fill: '#f59e0b', strokeWidth: 1, stroke: 'var(--bg-surface)' }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="mt-4 flex min-h-[162px] items-center justify-center gap-2 rounded-xl border border-dashed border-[var(--border-light)] text-sm font-semibold text-[var(--text-muted)]">
          <CircleAlert size={16} /> No measured history is available for this KPI.
        </div>
      )}
    </section>
  );
}
