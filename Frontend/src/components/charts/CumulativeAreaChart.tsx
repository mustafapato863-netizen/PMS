import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import type { MonthSummary } from '../../hooks/usePerformanceData';

interface CumulativeAreaChartProps {
  data: MonthSummary[];
}

const targetPerMonth = 0.75; // 75% attend target

const CumulativeAreaChart = ({ data }: CumulativeAreaChartProps) => {
  const chartData = data.map((d) => ({
    month: d.month,
    attended: d.totalAttended,
    bookings: d.totalBookings,
    target: Math.round(d.totalBookings * targetPerMonth),
  }));

  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
      <div className="mb-6">
        <h3 className="text-lg font-bold text-slate-800">Cumulative Attended vs Target</h3>
        <p className="text-sm text-slate-500 mt-0.5">
          Monthly attended cases against the 75% attendance target
        </p>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <AreaChart data={chartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id="gradientAttended" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="gradientBookings" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#10b981" stopOpacity={0.2} />
              <stop offset="100%" stopColor="#10b981" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 12, fill: '#94a3b8' }}
            axisLine={{ stroke: '#e2e8f0' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 12, fill: '#94a3b8' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => `${(v / 1000).toFixed(1)}K`}
          />
          <Tooltip
            contentStyle={{
              borderRadius: '12px',
              border: '1px solid #e2e8f0',
              boxShadow: '0 10px 25px -5px rgba(0,0,0,0.1)',
              padding: '12px 16px',
            }}
            formatter={(value, name) => [
              Number(value ?? 0).toLocaleString(),
              String(name).charAt(0).toUpperCase() + String(name).slice(1),
            ]}
          />
          <Legend
            iconType="circle"
            wrapperStyle={{ fontSize: '12px', paddingTop: '16px' }}
          />
          <Area
            type="monotone"
            dataKey="attended"
            stroke="#3b82f6"
            strokeWidth={2.5}
            fill="url(#gradientAttended)"
            name="Attended"
            dot={{ r: 5, fill: '#3b82f6', strokeWidth: 2, stroke: '#fff' }}
            activeDot={{ r: 7, stroke: '#3b82f6', strokeWidth: 2, fill: '#fff' }}
          />
          <Area
            type="monotone"
            dataKey="target"
            stroke="#f59e0b"
            strokeWidth={2}
            strokeDasharray="6 4"
            fill="none"
            name="Target (75%)"
            dot={{ r: 4, fill: '#f59e0b', strokeWidth: 2, stroke: '#fff' }}
          />
          <ReferenceLine y={0} stroke="#e2e8f0" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};

export default CumulativeAreaChart;
