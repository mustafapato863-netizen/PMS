import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  Line,
  LabelList,
} from 'recharts';
import type { CumulativeMonthPoint } from '../../hooks/usePerformanceData';

interface GrowthTrendChartProps {
  data: CumulativeMonthPoint[];
}

const CustomLabel = (props: { x?: number; y?: number; value?: number }) => {
  const { x = 0, y = 0, value = 0 } = props;
  return (
    <text x={x} y={y - 14} textAnchor="middle" fill="#1e293b" fontSize={13} fontWeight={700}>
      {value.toLocaleString()}
    </text>
  );
};

const GrowthTrendChart = ({ data }: GrowthTrendChartProps) => {
  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
      <div className="flex items-center justify-between mb-5">
        <div>
          <h3 className="text-base font-bold text-slate-800 uppercase tracking-wide">
            Monthly Attended vs Target (75%)
          </h3>
        </div>
        <div className="flex items-center gap-5 text-xs">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded-full bg-blue-500" />
            <span className="text-slate-600 font-medium">Attended Census</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-0.5 bg-red-500" style={{ borderTop: '2px dashed #ef4444', background: 'none' }} />
            <span className="text-slate-600 font-medium">75% Target</span>
          </div>
        </div>
      </div>
      <ResponsiveContainer width="100%" height={340}>
        <AreaChart data={data} margin={{ top: 30, right: 30, left: 10, bottom: 10 }}>
          <defs>
            <linearGradient id="gradientShowUp" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.35} />
              <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.04} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 12, fill: '#64748b', fontWeight: 600 }}
            axisLine={{ stroke: '#e2e8f0' }}
            tickLine={false}
            label={{ value: 'Branch', position: 'insideBottomRight', offset: -5, fontSize: 11, fill: '#94a3b8' }}
          />
          <YAxis
            tick={{ fontSize: 11, fill: '#94a3b8' }}
            axisLine={false}
            tickLine={false}
            tickFormatter={(v: number) => v.toLocaleString()}
            label={{
              value: 'Number of Attended Patients',
              angle: -90,
              position: 'insideLeft',
              offset: 0,
              fontSize: 11,
              fill: '#94a3b8',
              style: { textAnchor: 'middle' },
            }}
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
              name === 'attended' ? 'Attended Census' : 'Strategic Target',
            ]}
          />
          <Area
            type="monotone"
            dataKey="attended"
            stroke="#3b82f6"
            strokeWidth={3}
            fill="url(#gradientShowUp)"
            dot={{ r: 6, fill: '#3b82f6', strokeWidth: 3, stroke: '#fff' }}
            activeDot={{ r: 8, stroke: '#3b82f6', strokeWidth: 2, fill: '#fff' }}
          >
            <LabelList dataKey="attended" content={<CustomLabel />} />
          </Area>
          <Line
            type="monotone"
            dataKey="target"
            stroke="#ef4444"
            strokeWidth={2.5}
            strokeDasharray="8 5"
            dot={{ r: 5, fill: '#ef4444', strokeWidth: 3, stroke: '#fff' }}
          >
            <LabelList dataKey="target" content={(props) => {
              const { x = 0, y = 0, value = 0 } = props;
              return (
                <text x={x} y={Number(y) - 14} textAnchor="middle" fill="#ef4444" fontSize={12} fontWeight={600}>
                  {Number(value).toLocaleString()}
                </text>
              );
            }} />
          </Line>
          <Legend content={() => null} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
};

export default GrowthTrendChart;
