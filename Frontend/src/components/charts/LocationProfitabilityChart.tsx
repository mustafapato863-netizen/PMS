import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  LabelList,
} from 'recharts';
import type { LocationSummary } from '../../hooks/usePerformanceData';

interface LocationProfitabilityChartProps {
  data: LocationSummary[];
}

const LocationProfitabilityChart = ({ data }: LocationProfitabilityChartProps) => {
  const worstLocation = data.reduce((prev, current) => (prev.noShowRate > current.noShowRate) ? prev : current);

  return (
    <div className="bg-white rounded-2xl p-5 shadow-sm border border-slate-100 h-full flex flex-col relative overflow-hidden">
      <div className="mb-4">
        <h3 className="text-sm font-bold text-slate-800 uppercase tracking-wide">
          Location Performance & Leakage
        </h3>
        
        {/* Dynamic Alert */}
        <div className="mt-3 mb-2 flex items-center gap-2 bg-red-50 text-red-700 px-3 py-2 rounded-lg border border-red-100 text-[11px] font-semibold">
          <span className="text-red-500">⚠️</span> 
          <span>{worstLocation.location} has the highest no-show rate ({worstLocation.noShowRate.toFixed(1)}%). Focus retention efforts here.</span>
        </div>

        <div className="flex items-center gap-4 mt-2 text-[11px]">
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-sm bg-blue-500" />
            <span className="text-slate-500 font-medium">Booking Volume</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
            <span className="text-slate-500 font-medium">No-Show Rate (%)</span>
          </div>
        </div>
      </div>
      <div className="flex-1">
        <ResponsiveContainer width="100%" height={220}>
          <ComposedChart data={data} margin={{ top: 20, right: 25, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
            <XAxis
              dataKey="location"
              tick={{ fontSize: 11, fill: '#64748b', fontWeight: 600 }}
              axisLine={{ stroke: '#e2e8f0' }}
              tickLine={false}
              label={{ value: 'Branch', position: 'insideBottomRight', offset: -5, fontSize: 10, fill: '#94a3b8' }}
            />
            <YAxis
              yAxisId="left"
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              axisLine={false}
              tickLine={false}
              label={{
                value: 'Booking Volume',
                angle: -90,
                position: 'insideLeft',
                offset: 10,
                fontSize: 10,
                fill: '#94a3b8',
                style: { textAnchor: 'middle' },
              }}
            />
            <YAxis
              yAxisId="right"
              orientation="right"
              domain={[0, 100]}
              tick={{ fontSize: 10, fill: '#94a3b8' }}
              axisLine={false}
              tickLine={false}
              tickFormatter={(v: number) => `${v}`}
              label={{
                value: 'No-Show Rate (%)',
                angle: 90,
                position: 'insideRight',
                offset: 10,
                fontSize: 10,
                fill: '#94a3b8',
                style: { textAnchor: 'middle' },
              }}
            />
            <Tooltip
              contentStyle={{
                borderRadius: '12px',
                border: '1px solid #e2e8f0',
                boxShadow: '0 10px 25px -5px rgba(0,0,0,0.1)',
                padding: '10px 14px',
                fontSize: '12px',
              }}
              formatter={(value, name) => {
                const numericValue = Number(value ?? 0);
                if (name === 'noShowRate') return [`${numericValue}%`, 'No-Show Rate'];
                return [numericValue.toLocaleString(), 'Booking Volume'];
              }}
            />
            <Bar
              yAxisId="left"
              dataKey="bookings"
              name="bookings"
              fill="#3b82f6"
              radius={[4, 4, 0, 0]}
              maxBarSize={45}
            />
            <Line
              yAxisId="right"
              type="monotone"
              dataKey="noShowRate"
              name="noShowRate"
              stroke="#ef4444"
              strokeWidth={2.5}
              dot={{ r: 6, fill: '#ef4444', strokeWidth: 3, stroke: '#fff' }}
            >
              <LabelList
                dataKey="noShowRate"
                position="top"
                formatter={(v) => `${Number(v ?? 0)}%`}
                style={{ fontSize: 11, fontWeight: 700, fill: '#dc2626' }}
              />
            </Line>
            <Legend content={() => null} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default LocationProfitabilityChart;
