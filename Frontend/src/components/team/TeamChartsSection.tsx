import { BarChart2, LineChart as LineChartIcon } from 'lucide-react';
import {
  PieChart, Pie, Cell, Tooltip as RechartsTooltip, ResponsiveContainer, Legend,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
} from 'recharts';

interface ChartPoint {
  month: string;
  score: number;
}

interface PiePoint {
  name: string;
  value: number;
  color: string;
}

interface TeamChartsSectionProps {
  pieData: PiePoint[];
  trendData: ChartPoint[];
}

const TeamChartsSection = ({ pieData, trendData }: TeamChartsSectionProps) => {
  const trendTitle = trendData.length === 0
    ? 'Trend Unavailable'
    : trendData.length === 1
      ? `${trendData[0].month} Only`
      : trendData.length < 6
        ? `Score Trend — ${trendData.length} Available Periods`
        : 'Score Trend — Last 6 Months';
  return (
    <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
      {/* Grade Distribution Pie */}
      <div className="glass-panel rounded-xl p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-4">
          <BarChart2 size={16} className="text-indigo-500" />
          <h3 className="heading-3 text-base">Grade Distribution</h3>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie data={pieData} cx="50%" cy="50%" innerRadius={55} outerRadius={85} paddingAngle={3} dataKey="value">
              {pieData.map((entry) => (
                <Cell key={entry.name} fill={entry.color} />
              ))}
            </Pie>
            <RechartsTooltip 
              formatter={(val, name) => [`${Number(val ?? 0)} agents`, String(name)]}
              contentStyle={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-medium)', borderRadius: '0.75rem', color: 'var(--text-primary)' }}
            />
            <Legend iconType="circle" iconSize={10} wrapperStyle={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Trend Line Chart */}
      <div className="glass-panel rounded-xl p-6 shadow-sm">
        <div className="flex items-center gap-2 mb-4">
          <LineChartIcon size={16} className="text-blue-500" />
          <h3 className="heading-3 text-base">{trendTitle}</h3>
        </div>
        <ResponsiveContainer width="100%" height={220}>
          <LineChart data={trendData} margin={{ top: 5, right: 8, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
            <YAxis tick={{ fontSize: 11, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} domain={[0, 100]} />
            <RechartsTooltip 
              formatter={(v) => [`${Number(v ?? 0).toFixed(1)}%`, 'Avg Score']}
              contentStyle={{ backgroundColor: 'var(--bg-surface)', borderColor: 'var(--border-medium)', borderRadius: '0.75rem', color: 'var(--text-primary)' }}
            />
            <Line
              type="monotone" dataKey="score" stroke="#3B82F6" strokeWidth={2.5}
              dot={{ fill: '#3B82F6', r: 4 }} activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default TeamChartsSection;
