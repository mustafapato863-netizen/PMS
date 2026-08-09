import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import type { LocationSummary } from '../../hooks/usePerformanceData';

interface LocationBarChartProps {
  data: LocationSummary[];
}

const LocationBarChart = ({ data }: LocationBarChartProps) => {
  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
      <div className="mb-6">
        <h3 className="text-lg font-bold text-slate-800">Bookings vs Attended by Location</h3>
        <p className="text-sm text-slate-500 mt-0.5">
          Comparison of total bookings and attended cases per location
        </p>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }} barGap={4}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
          <XAxis
            dataKey="location"
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
              String(name),
            ]}
            cursor={{ fill: 'rgba(59, 130, 246, 0.04)' }}
          />
          <Legend
            iconType="circle"
            wrapperStyle={{ fontSize: '12px', paddingTop: '16px' }}
          />
          <Bar
            dataKey="bookings"
            name="Bookings"
            fill="#3b82f6"
            radius={[6, 6, 0, 0]}
            maxBarSize={50}
          />
          <Bar
            dataKey="attended"
            name="Attended"
            fill="#10b981"
            radius={[6, 6, 0, 0]}
            maxBarSize={50}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default LocationBarChart;
