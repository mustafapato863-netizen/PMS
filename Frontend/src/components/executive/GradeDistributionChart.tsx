import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, LabelList
} from 'recharts';
import { GRADE_PALETTE } from '../../constants/grades';

interface GradeDistributionChartProps {
  classCounts: { A: number; B: number; C: number; D: number; E: number };
  displayMode?: 'headcount' | 'percentage';
}

const GRADE_CONFIG = [
  { key: 'A', label: 'Class A', color: GRADE_PALETTE.A.text, desc: GRADE_PALETTE.A.label },
  { key: 'B', label: 'Class B', color: GRADE_PALETTE.B.text, desc: GRADE_PALETTE.B.label },
  { key: 'C', label: 'Class C', color: GRADE_PALETTE.C.text, desc: GRADE_PALETTE.C.label },
  { key: 'D', label: 'Class D', color: GRADE_PALETTE.D.text, desc: GRADE_PALETTE.D.label },
  { key: 'E', label: 'Class E', color: GRADE_PALETTE.E.text, desc: GRADE_PALETTE.E.label },
];

interface GradeTooltipPayload {
  payload: {
    label: string;
    desc: string;
    color: string;
    count: number;
    percentage: number;
  };
}

const CustomTooltip = ({ active, payload }: { active?: boolean; payload?: GradeTooltipPayload[] }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  return (
    <div className="bg-[var(--bg-surface)] border border-[var(--border-medium)] rounded-xl p-3 shadow-lg text-sm">
      <div className="font-bold text-[var(--text-primary)] mb-1">{d.label}</div>
      <div className="text-[var(--text-secondary)] text-xs mb-2">{d.desc}</div>
      <div className="font-extrabold text-xl" style={{ color: d.color }}>
        {d.count} {d.count === 1 ? 'agent' : 'agents'}
      </div>
      <div className="mt-0.5 text-xs font-semibold text-[var(--text-muted)]">{d.percentage.toFixed(1)}% of headcount</div>
    </div>
  );
};

const GradeDistributionChart = ({ classCounts, displayMode = 'headcount' }: GradeDistributionChartProps) => {
  const total = Object.values(classCounts).reduce((a, b) => a + b, 0);

  const data = GRADE_CONFIG.map((g) => ({
    key: g.key,
    label: g.label,
    desc: g.desc,
    color: g.color,
    count: classCounts[g.key as keyof typeof classCounts],
    percentage: total > 0 ? (classCounts[g.key as keyof typeof classCounts] / total) * 100 : 0,
    value: displayMode === 'headcount'
      ? classCounts[g.key as keyof typeof classCounts]
      : total > 0 ? (classCounts[g.key as keyof typeof classCounts] / total) * 100 : 0,
  }));

  return (
    <div className="min-w-0">
      <ResponsiveContainer width="100%" height={205}>
        <BarChart data={data} barCategoryGap="32%" margin={{ top: 18, right: 8, left: -18, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-light)" vertical={false} />
          <XAxis
            dataKey="key"
            tick={{ fontSize: 12, fontWeight: 800, fill: 'var(--text-secondary)' }}
            tickLine={false}
            axisLine={false}
          />
          <YAxis
            tick={{ fontSize: 10, fill: 'var(--text-muted)' }}
            tickLine={false}
            axisLine={false}
            allowDecimals={displayMode === 'percentage'}
            domain={displayMode === 'percentage' ? [0, 100] : undefined}
            tickFormatter={(value) => displayMode === 'percentage' ? `${value}%` : String(value)}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'var(--glass-highlight)' }} />
          <Bar dataKey="value" radius={[6, 6, 0, 0]}>
            <LabelList
              dataKey="value"
              position="top"
              style={{ fontSize: '11px', fontWeight: 700, fill: 'var(--text-muted)' }}
              formatter={(value) => displayMode === 'percentage' ? `${Number(value ?? 0).toFixed(1)}%` : Number(value ?? 0)}
            />
            {data.map((entry) => (
              <Cell key={entry.key} fill={entry.color} fillOpacity={0.85} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      <div className="grid grid-cols-5 gap-1 px-2">
        {GRADE_CONFIG.map((grade) => (
          <div key={grade.key} className="text-center text-[9px] font-semibold text-[var(--text-muted)] sm:text-[10px]">
            {grade.desc}
          </div>
        ))}
      </div>
    </div>
  );
};

export default GradeDistributionChart;
