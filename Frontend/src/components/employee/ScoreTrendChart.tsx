import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ReferenceLine, Legend } from 'recharts';

interface ScoreTrendChartProps {
  data: Array<{ month: string; score: number; benchmarkScore?: number; isPeak?: boolean }>;
  targetScore?: number;
  benchmarkName?: string;
  mode?: 'actuals' | 'team_avg' | 'team_best' | 'personal_best';
}

interface TooltipEntry {
  value: number;
  color: string;
  dataKey: string;
  name: string;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string;
}

interface CustomDotProps {
  cx?: number;
  cy?: number;
  payload?: { isPeak?: boolean };
}

const CustomTooltip = ({ active, payload, label }: CustomTooltipProps) => {
  if (!active || !payload?.length) return null;
  
  return (
    <div className="bg-[var(--bg-surface-elevated)] border border-[var(--border-medium)] rounded-2xl px-4 py-3 shadow-xl text-sm min-w-[160px] backdrop-blur-md">
      <div className="text-[11px] text-[var(--text-muted)] font-extrabold uppercase tracking-widest mb-2 border-b border-[var(--border-light)] pb-1.5">{label}</div>
      {payload.map((entry, index) => {
        const score = entry.value;
        let color = entry.color;
        if (entry.dataKey === 'score') {
          color = score >= 90 ? 'var(--color-exceeds)' : score >= 80 ? 'var(--color-meet)' : score >= 70 ? 'var(--color-average)' : 'var(--color-sip)';
        }
        
        return (
          <div key={index} className="flex justify-between items-center py-0.5">
            <span className="text-xs font-semibold text-[var(--text-secondary)] flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: entry.color }} />
              {entry.name}:
            </span>
            <span className="font-mono font-black text-sm ml-4" style={{ color }}>
              {score.toFixed(1)}%
            </span>
          </div>
        );
      })}
    </div>
  );
};

const CustomDot = (props: CustomDotProps) => {
  const { cx, cy, payload } = props;
  if (cx == null || cy == null) return null;
  if (payload?.isPeak) {
    return (
      <g>
        <circle cx={cx} cy={cy} r={10} fill="var(--bg-surface)" stroke="#F59E0B" strokeWidth={2} />
        <text x={cx} y={cy} dy={3.5} textAnchor="middle" fontSize="10">🏆</text>
      </g>
    );
  }
  return <circle cx={cx} cy={cy} r={4} fill="var(--color-meet)" stroke="var(--bg-surface)" strokeWidth={2} />;
};

const ScoreTrendChart = ({ data, targetScore = 80, benchmarkName = 'Benchmark' }: ScoreTrendChartProps) => {
  if (!data || !data.length) {
    return (
      <div className="h-40 flex items-center justify-center text-[var(--text-muted)] text-sm font-medium">
        No historical data available.
      </div>
    );
  }

  const hasBenchmark = data.some(d => d.benchmarkScore !== undefined);

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" vertical={false} />
        <XAxis
          dataKey="month"
          tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
          axisLine={false}
          tickLine={false}
          padding={{ left: 10, right: 10 }}
        />
        <YAxis
          tick={{ fontSize: 11, fill: 'var(--text-muted)' }}
          axisLine={false}
          tickLine={false}
          domain={[0, (dataMax: number) => Math.max(100, Math.ceil(dataMax / 10) * 10)]}
        />
        <Tooltip content={<CustomTooltip />} />
        
        {hasBenchmark && (
          <Legend 
            verticalAlign="top" 
            height={36}
            iconType="circle"
            wrapperStyle={{ fontSize: '11px', fontWeight: 500 }}
          />
        )}

        <ReferenceLine
          y={targetScore}
          stroke="var(--color-meet)"
          strokeDasharray="4 4"
          strokeOpacity={0.4}
          label={{ value: `Target Threshold (${targetScore}%)`, position: 'insideTopLeft', fontSize: 10, fill: 'var(--color-meet)', fontWeight: 600, dy: -8 }}
        />

        {hasBenchmark && (
          <Line
            name={benchmarkName}
            type="monotone"
            dataKey="benchmarkScore"
            stroke="#8b5cf6"
            strokeWidth={2}
            strokeDasharray="5 5"
            dot={{ fill: '#8b5cf6', r: 3, strokeWidth: 1, stroke: 'var(--bg-surface)' }}
            activeDot={{ r: 5, stroke: '#8b5cf6', strokeWidth: 2 }}
          />
        )}

        <Line
          name="Actual Score"
          type="monotone"
          dataKey="score"
          stroke="var(--color-meet)"
          strokeWidth={3}
          dot={<CustomDot />}
          activeDot={{ r: 6, stroke: 'var(--color-meet)', strokeWidth: 2 }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
};

export default ScoreTrendChart;
