import { motion } from 'framer-motion';
import { Check, X, Clock, AlertTriangle, TrendingUp } from 'lucide-react';
import type { KpiVsTarget } from '../../hooks/usePerformanceData';
import { formatSecondsToMMSS } from '../../hooks/usePerformanceData';

interface KpiTargetChartProps {
  data: KpiVsTarget[];
}

const kpiIcons = [TrendingUp, Check, Clock, AlertTriangle];
const kpiColors = {
  met: {
    bar: 'bg-emerald-500',
    barBg: 'bg-emerald-100',
    badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    icon: 'text-emerald-500',
  },
  notMet: {
    bar: 'bg-red-500',
    barBg: 'bg-red-100',
    badge: 'bg-red-50 text-red-700 border-red-200',
    icon: 'text-red-500',
  },
};

function formatValue(value: number, unit: string): string {
  if (unit === 'time') return formatSecondsToMMSS(value);
  return `${value.toFixed(1)}%`;
}

function getBarPercent(kpi: KpiVsTarget): number {
  if (kpi.unit === 'time') {
    // For AHT: target is 150s. Show ratio (capped at 100%)
    return Math.min((kpi.actual / (kpi.target * 1.5)) * 100, 100);
  }
  if (kpi.isLowerBetter) {
    // For abandon rate: scale relative to a reasonable max (5%)
    return Math.min((kpi.actual / 5) * 100, 100);
  }
  // For booking/attend rate: scale to 100%
  return Math.min(kpi.actual, 100);
}

function getTargetPosition(kpi: KpiVsTarget): number {
  if (kpi.unit === 'time') {
    return Math.min((kpi.target / (kpi.target * 1.5)) * 100, 100);
  }
  if (kpi.isLowerBetter) {
    return Math.min((kpi.target / 5) * 100, 100);
  }
  return Math.min(kpi.target, 100);
}

const KpiTargetChart = ({ data }: KpiTargetChartProps) => {
  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
      <div className="mb-5">
        <h3 className="text-base font-bold text-slate-800 uppercase tracking-wide">
          KPI Performance vs Target
        </h3>
        <p className="text-xs text-slate-400 mt-0.5">Actual performance compared to strategic targets</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {data.map((kpi, i) => {
          const colors = kpi.isMet ? kpiColors.met : kpiColors.notMet;
          const Icon = kpiIcons[i] || TrendingUp;
          const barPct = getBarPercent(kpi);
          const targetPos = getTargetPosition(kpi);

          return (
            <motion.div
              key={kpi.label}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.3, delay: i * 0.08 }}
              className="p-4 rounded-xl bg-slate-50/50 border border-slate-100"
            >
              {/* Header */}
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2.5">
                  <Icon className={`w-4 h-4 ${colors.icon}`} />
                  <span className="text-sm font-semibold text-slate-700">{kpi.label}</span>
                </div>
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold border ${colors.badge}`}>
                  {kpi.isMet ? <Check className="w-3 h-3" /> : <X className="w-3 h-3" />}
                  {kpi.isMet ? 'On Target' : 'Below Target'}
                </span>
              </div>

              {/* Bar */}
              <div className="relative h-3 rounded-full bg-slate-200 overflow-visible mb-2.5">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${barPct}%` }}
                  transition={{ duration: 0.8, delay: 0.2 + i * 0.1, ease: 'easeOut' }}
                  className={`absolute top-0 left-0 h-full rounded-full ${colors.bar}`}
                />
                {/* Target marker */}
                <div
                  className="absolute top-[-4px] w-0.5 h-[20px] bg-slate-800 rounded-full"
                  style={{ left: `${targetPos}%` }}
                  title={`Target: ${formatValue(kpi.target, kpi.unit)}`}
                >
                  <div className="absolute -top-5 left-1/2 -translate-x-1/2 text-[9px] font-bold text-slate-500 whitespace-nowrap">
                    Target
                  </div>
                </div>
              </div>

              {/* Values */}
              <div className="flex items-center justify-between">
                <span className="text-lg font-black text-slate-800">
                  {formatValue(kpi.actual, kpi.unit)}
                </span>
                <span className="text-xs text-slate-400 font-medium">
                  Target: {formatValue(kpi.target, kpi.unit)}
                </span>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
};

export default KpiTargetChart;
