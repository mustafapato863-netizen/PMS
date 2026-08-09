import { motion } from 'framer-motion';
import { TrendingUp, TrendingDown } from 'lucide-react';

interface StatCardProps {
  title: string;
  value: string;
  subtitle?: string;
  comparison?: string;
  isPositive?: boolean;
  status?: 'good' | 'bad' | 'neutral';
  icon: React.ReactNode;
  color?: 'blue' | 'emerald' | 'amber' | 'indigo' | 'violet' | 'rose';
  delay?: number;
}

const colorMap: Record<string, { bg: string, text: string, gradient: string }> = {
  blue: { bg: 'bg-blue-50', text: 'text-blue-600', gradient: 'gradient-primary' },
  emerald: { bg: 'bg-emerald-50', text: 'text-emerald-600', gradient: 'gradient-success' },
  amber: { bg: 'bg-amber-50', text: 'text-amber-600', gradient: 'gradient-warning' },
  indigo: { bg: 'bg-indigo-50', text: 'text-indigo-600', gradient: 'bg-gradient-to-br from-indigo-500 to-indigo-700' },
  violet: { bg: 'bg-violet-50', text: 'text-violet-600', gradient: 'gradient-violet' },
  rose: { bg: 'bg-rose-50', text: 'text-rose-600', gradient: 'gradient-danger' },
};

const StatCard = ({ title, value, subtitle, comparison, isPositive, status, icon, color = 'blue', delay = 0 }: StatCardProps) => {
  const c = colorMap[color];
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.25, 0.1, 0.25, 1.0] }}
      className="bg-white p-6 rounded-2xl shadow-sm border border-slate-100/60 hover:-translate-y-1 hover:shadow-xl transition-all duration-300 relative overflow-hidden group"
    >
      <div className={`absolute -right-6 -top-6 w-24 h-24 rounded-full opacity-[0.03] group-hover:opacity-10 transition-opacity duration-500 ${c.gradient}`} />
      
      <div className="flex justify-between items-start mb-4 relative z-10">
        <div className={`p-3 rounded-xl shadow-md ${c.gradient}`}>
          <div className="text-white">
            {icon}
          </div>
        </div>
        {status && (
          <div className={`px-2 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider ${
            status === 'good' ? 'bg-emerald-50 text-emerald-600 border border-emerald-100' : 
            status === 'bad' ? 'bg-red-50 text-red-600 border border-red-100' : 
            'bg-slate-50 text-slate-500 border border-slate-200'
          }`}>
            {status === 'good' ? 'On Target' : status === 'bad' ? 'Below Target' : 'Neutral'}
          </div>
        )}
      </div>
      <div className="relative z-10">
        <p className="text-[11px] font-bold text-slate-400 uppercase tracking-[0.1em] mb-1.5">{title}</p>
        <h3 className="text-3xl font-black text-slate-800 tracking-tight">{value}</h3>
        {subtitle && <p className="text-xs text-slate-500 font-medium mt-1">{subtitle}</p>}
        
        {comparison && (
          <div className="flex items-center gap-1.5 mt-3 pt-3 border-t border-slate-100/60">
            <div className={`flex items-center justify-center p-0.5 rounded-full ${isPositive ? 'bg-emerald-100 text-emerald-600' : 'bg-red-100 text-red-600'}`}>
              {isPositive ? <TrendingUp size={12} strokeWidth={3} /> : <TrendingDown size={12} strokeWidth={3} />}
            </div>
            <span className={`text-[11px] font-bold ${isPositive ? 'text-emerald-600' : 'text-red-600'}`}>
              {comparison}
            </span>
            <span className="text-[11px] font-medium text-slate-400">vs last month</span>
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default StatCard;