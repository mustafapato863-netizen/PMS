import { motion } from 'framer-motion';
import { Phone, CalendarCheck, UserCheck, ArrowRight, TrendingDown } from 'lucide-react';
import type { FunnelData } from '../../hooks/usePerformanceData';

interface ConversionFunnelProps {
  data: FunnelData;
}

const steps = [
  {
    key: 'calls' as const,
    label: 'Total Calls Handled',
    icon: Phone,
    gradient: 'from-blue-500 to-blue-700',
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    border: 'border-blue-100',
  },
  {
    key: 'bookings' as const,
    label: 'Total Bookings',
    icon: CalendarCheck,
    gradient: 'from-amber-500 to-amber-700',
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-100',
  },
  {
    key: 'attended' as const,
    label: 'Patients Attended',
    icon: UserCheck,
    gradient: 'from-emerald-500 to-emerald-700',
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-100',
  },
];

const ConversionFunnel = ({ data }: ConversionFunnelProps) => {
  const rates = [
    null,
    { rate: data.callToBookingRate, dropoff: 1 - data.callToBookingRate },
    { rate: data.bookingToAttendRate, dropoff: 1 - data.bookingToAttendRate },
  ];

  const values: Record<string, number> = {
    calls: data.calls,
    bookings: data.bookings,
    attended: data.attended,
  };

  const maxVal = Math.max(data.calls, 1);

  return (
    <div className="bg-white rounded-2xl p-6 shadow-sm border border-slate-100">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-base font-bold text-slate-800 uppercase tracking-wide">
            Conversion Funnel
          </h3>
          <p className="text-xs text-slate-400 mt-0.5">Calls → Bookings → Patient Show-Up</p>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <TrendingDown className="w-3.5 h-3.5" />
          <span>
            Overall: {((data.attended / Math.max(data.calls, 1)) * 100).toFixed(1)}% end-to-end
          </span>
        </div>
      </div>

      <div className="flex flex-col lg:flex-row items-center lg:items-stretch gap-3 lg:gap-3">
        {steps.map((step, i) => (
          <div key={step.key} className="flex flex-col lg:flex-row items-center gap-3 w-full lg:flex-1">
            {/* Conversion arrow between steps */}
            {i > 0 && rates[i] && (
              <div className="flex flex-col items-center gap-1 shrink-0 w-full lg:w-16 py-2 lg:py-0">
                <ArrowRight className="hidden lg:block w-5 h-5 text-slate-300" />
                {/* Mobile Arrow */}
                <svg className="lg:hidden w-5 h-5 text-slate-300 rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
                <span className="text-[11px] font-bold text-emerald-600">
                  {(rates[i]!.rate * 100).toFixed(1)}%
                </span>
                <span className="text-[9px] text-red-400 font-semibold">
                  -{(rates[i]!.dropoff * 100).toFixed(1)}%
                </span>
              </div>
            )}

            {/* Step card */}
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              transition={{ duration: 0.35, delay: i * 0.1 }}
              className={`w-full lg:flex-1 ${step.bg} border ${step.border} rounded-2xl p-5 relative overflow-hidden flex flex-col justify-center min-h-[110px]`}
            >
              {/* Background bar showing proportion */}
              <div
                className={`absolute bottom-0 left-0 h-1 bg-gradient-to-r ${step.gradient} rounded-b-2xl`}
                style={{ transform: `scaleX(${values[step.key] / maxVal})`, transformOrigin: 'left', transition: 'transform 0.7s', width: '100%' }}
              />

              <div className="flex items-center gap-3 mb-3">
                <div className={`w-9 h-9 rounded-xl bg-gradient-to-br ${step.gradient} flex items-center justify-center shadow-md shrink-0`}>
                  <step.icon className="w-4.5 h-4.5 text-white" />
                </div>
                <p className={`text-[11px] font-bold ${step.text} uppercase tracking-wider`}>
                  {step.label}
                </p>
              </div>
              <p className="text-3xl font-black text-slate-800 tracking-tight">
                {values[step.key].toLocaleString()}
              </p>
            </motion.div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default ConversionFunnel;
