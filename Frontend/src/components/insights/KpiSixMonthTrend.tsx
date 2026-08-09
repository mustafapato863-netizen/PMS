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

function displayValue(value: number | null, unit: string | null) {
  if (value === null) return null;
  return unit === '%' && Math.abs(value) <= 1 ? value * 100 : value;
}

function formatDisplayValue(value: number | null, unit: string | null) {
  if (value === null) return 'No data';
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}${unit === '%' ? '%' : unit ? ` ${unit}` : ''}`;
}

export default function KpiSixMonthTrend({ trend }: { trend: InsightKpiTrend }) {
  const data = trend.points.map((point) => ({
    period: `${point.period.month.slice(0, 3)} ${String(point.period.year).slice(-2)}`,
    actual: displayValue(point.actual_value, trend.unit),
    target: displayValue(point.target_value, trend.unit),
    records: point.measured_records,
  }));
  const measuredMonths = trend.points.filter((point) => point.actual_value !== null).length;

  return (
    <section className="border-t border-[var(--border-light)] px-5 pb-6 pt-5 md:px-7" aria-labelledby="selected-kpi-trend-title">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-blue-500/10 text-blue-600"><Activity size={16} /></span>
          <div>
            <h3 id="selected-kpi-trend-title" className="text-sm font-extrabold text-[var(--text-primary)]">6-Month KPI Trend</h3>
            <p className="text-xs font-semibold text-[var(--text-muted)]">{trend.kpi_label} · Actual vs target</p>
          </div>
        </div>
        <span className="rounded-full bg-[var(--bg-sunken)] px-3 py-1 text-[10px] font-bold text-[var(--text-muted)]">
          {measuredMonths} of 6 months measured
        </span>
      </div>

      {measuredMonths ? (
        <div className="mt-4 h-[250px] w-full" aria-label={`${trend.kpi_label} six month actual and target trend`}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 12, right: 12, left: 0, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--border-light)" strokeDasharray="4 4" />
              <XAxis dataKey="period" axisLine={false} tickLine={false} tick={{ fill: 'var(--text-muted)', fontSize: 10, fontWeight: 600 }} />
              <YAxis
                axisLine={false}
                tickLine={false}
                reversed={trend.direction === 'lower_better'}
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
                  const records = payload?.[0]?.payload?.records ?? 0;
                  return `${label} · ${records} measured record${records === 1 ? '' : 's'}`;
                }}
              />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 11, fontWeight: 700 }} formatter={(value) => value === 'actual' ? 'Actual' : 'Target'} />
              <Line type="monotone" dataKey="actual" name="actual" stroke="#2563eb" strokeWidth={3} connectNulls={false} dot={{ r: 4, fill: '#2563eb', strokeWidth: 2, stroke: 'var(--bg-surface)' }} activeDot={{ r: 6 }} />
              <Line type="monotone" dataKey="target" name="target" stroke="#f59e0b" strokeWidth={2} strokeDasharray="6 5" connectNulls={false} dot={{ r: 3, fill: '#f59e0b', strokeWidth: 1, stroke: 'var(--bg-surface)' }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <div className="mt-4 flex min-h-[180px] items-center justify-center gap-2 rounded-xl border border-dashed border-[var(--border-light)] text-sm font-semibold text-[var(--text-muted)]">
          <CircleAlert size={16} /> No measured history is available for this KPI.
        </div>
      )}
    </section>
  );
}
