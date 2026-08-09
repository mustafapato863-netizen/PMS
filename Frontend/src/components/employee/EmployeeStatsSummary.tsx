import React from 'react';
import { Trophy, TrendingUp, TrendingDown, BarChart3, Activity, Target, Shield, Zap, AlertCircle, Minus } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import type { StabilityCategory, PerformanceArchetype } from '../../services/employeeAnalytics';
import { motion } from 'framer-motion';

interface EmployeeStatsSummaryProps {
  score: number;
  rank: number;
  totalEmployees: number;
  percentile: number;
  bestMonth?: string;
  bestScore?: number;
  avgLast6?: number;
  consecutiveGrades?: number;
  gradeDistribution: { A: number; B: number; C: number; D: number; E: number };
  stability: StabilityCategory;
  consistencyScore: number;
  archetype: PerformanceArchetype;
}

interface StatCardProps {
  title: string;
  value: React.ReactNode;
  subtext?: React.ReactNode;
  icon: LucideIcon;
  colorClass: string;
  delay: number;
}

const StatCard = ({ title, value, subtext, icon: Icon, colorClass, delay }: StatCardProps) => (
  <motion.div 
    initial={{ opacity: 0, y: 10 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.3, delay }}
    className="bg-[var(--bg-surface-elevated)] p-5 rounded-2xl border border-[var(--border-light)] shadow-sm flex flex-col justify-between min-w-[160px] flex-1 md:flex-none relative overflow-hidden group hover:shadow-md transition-all duration-300"
  >
    <div className="flex justify-between items-start mb-2">
      <p className="text-[11px] sm:text-[12px] text-[var(--text-muted)] font-extrabold uppercase tracking-wider leading-tight">{title}</p>
      <div className={`p-2 rounded-lg ${colorClass} bg-opacity-10 backdrop-blur-md`}>
        <Icon className={`w-4 h-4 ${colorClass.replace('bg-', 'text-').replace('10', '')}`} />
      </div>
    </div>
    
    <div>
      <h4 className="text-[28px] font-black text-[var(--text-primary)] tracking-tight leading-none mb-1">{value}</h4>
      {subtext && <span className="text-[11px] text-[var(--text-muted)] font-bold">{subtext}</span>}
    </div>
    
    <div className={`absolute -right-4 -bottom-4 w-16 h-16 rounded-full opacity-0 group-hover:opacity-5 transition-opacity duration-300 blur-xl ${colorClass}`} />
  </motion.div>
);

export const EmployeeStatsSummary: React.FC<EmployeeStatsSummaryProps> = ({
  rank, totalEmployees, percentile, bestMonth, bestScore, avgLast6,
  consecutiveGrades, gradeDistribution, stability, consistencyScore, archetype
}) => {
  
  const getStabilityBadge = () => {
    let icon = <TrendingUp className="w-3.5 h-3.5" />;
    let colorClass = "text-emerald-600 bg-emerald-500/10 border-emerald-500/20 dark:text-emerald-400 dark:bg-emerald-500/20";
    const text = stability;
    
    if (stability === 'Declining') {
      icon = <TrendingDown className="w-3.5 h-3.5" />;
      colorClass = "text-rose-600 bg-rose-500/10 border-rose-500/20 dark:text-rose-400 dark:bg-rose-500/20";
    } else if (stability === 'Volatile') {
      icon = <AlertCircle className="w-3.5 h-3.5" />;
      colorClass = "text-amber-600 bg-amber-500/10 border-amber-500/20 dark:text-amber-400 dark:bg-amber-500/20";
    } else if (stability === 'Stable') {
      icon = <Minus className="w-3.5 h-3.5" />;
      colorClass = "text-blue-600 bg-blue-500/10 border-blue-500/20 dark:text-blue-400 dark:bg-blue-500/20";
    }
    
    return (
      <div className={`flex items-center gap-1.5 text-[11px] font-extrabold px-2.5 py-1 rounded-full border ${colorClass}`}>
        {icon}
        <span className="uppercase tracking-wider">{text}</span>
      </div>
    );
  };

  return (
    <div className="flex flex-col gap-4">
      {/* Archetype & Standing Hero Card */}
      <div className="bg-gradient-to-br from-blue-600/90 via-indigo-600/85 to-indigo-800/95 rounded-2xl p-6 text-white shadow-lg relative overflow-hidden border border-white/10 backdrop-blur-md">
        <div className="absolute top-0 right-0 p-4 opacity-15 pointer-events-none">
          <Shield className="w-24 h-24" />
        </div>
        <div className="relative z-10 flex justify-between items-center gap-4">
          {/* Left Side */}
          <div className="space-y-3">
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/10 backdrop-blur-md text-[11px] font-extrabold uppercase tracking-widest border border-white/10 shadow-sm text-yellow-300">
              <Zap className="w-3.5 h-3.5 fill-yellow-300 text-yellow-300" />
              {archetype}
            </div>
            <div>
              <h3 className="text-[28px] font-black tracking-tight leading-none mb-1.5">
                Rank #{rank} <span className="text-[16px] font-semibold text-white/60">/ {totalEmployees}</span>
              </h3>
              <p className="text-[12px] font-bold text-blue-200 uppercase tracking-wider">
                Top {percentile}% of Team
              </p>
            </div>
          </div>
          
          {/* Right Side */}
          <div className="text-right flex flex-col items-end gap-1">
            <div className="text-[11px] font-extrabold text-white/50 uppercase tracking-wider">Consistency</div>
            <div className="text-[28px] font-black leading-none mb-1.5">{consistencyScore}<span className="text-[14px] text-white/40 font-semibold">/100</span></div>
            {getStabilityBadge()}
          </div>
        </div>
      </div>

      {/* Grid Stats / Mini Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <StatCard 
          title="Personal Peak" 
          value={bestScore !== undefined ? `${bestScore.toFixed(1)}%` : '-'}
          subtext={bestMonth || 'No history'}
          icon={Trophy} 
          colorClass="bg-amber-600 text-amber-600"
          delay={0.1}
        />
        <StatCard 
          title="6M Avg Score" 
          value={avgLast6 !== undefined ? `${avgLast6.toFixed(1)}%` : '-'}
          subtext="Last 6 available months"
          icon={Activity} 
          colorClass="bg-blue-600 text-blue-600"
          delay={0.2}
        />
        <StatCard 
          title="Consistent A's" 
          value={`${consecutiveGrades || 0}`} 
          subtext="Months"
          icon={Target} 
          colorClass="bg-emerald-600 text-emerald-600"
          delay={0.3}
        />
      </div>

      {/* Grade Distribution */}
      <motion.div 
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3, delay: 0.4 }}
        className="bg-[var(--bg-surface)] p-4 rounded-xl border border-[var(--border-light)]"
      >
        <div className="text-xs text-[var(--text-secondary)] font-bold mb-4 uppercase tracking-wider flex items-center gap-2">
          <BarChart3 className="w-3.5 h-3.5" /> Grade History
        </div>
        <div className="flex justify-between items-center h-12 px-2">
          {['A', 'B', 'C', 'D', 'E'].map(grade => {
            const count = gradeDistribution[grade as keyof typeof gradeDistribution] || 0;
            const height = count > 0 ? Math.max(20, (count / 6) * 100) : 4; // Max 6 months assumption for scaling
            
            let color = 'bg-slate-200';
            if (grade === 'A') color = 'bg-emerald-400';
            if (grade === 'B') color = 'bg-blue-400';
            if (grade === 'C') color = 'bg-amber-400';
            if (grade === 'D' || grade === 'E') color = 'bg-rose-400';

            return (
              <div key={grade} className="flex flex-col items-center justify-end h-full group relative flex-1">
                <div className="w-8 rounded-sm overflow-hidden" style={{ height: '100%' }}>
                  <div className={`w-full h-full rounded-sm ${color} ${count === 0 ? 'opacity-20' : ''}`}
                    style={{ transform: `scaleY(${height / 100})`, transformOrigin: 'bottom', transition: 'transform 0.3s' }} />
                </div>
                <div className="absolute -top-6 bg-black text-white text-[10px] px-1.5 py-0.5 rounded opacity-0 group-hover:opacity-100 transition-opacity">
                  {count} {count === 1 ? 'Month' : 'Months'}
                </div>
                <span className="text-[11px] font-bold text-[var(--text-muted)] mt-1.5">{grade}</span>
              </div>
            );
          })}
        </div>
      </motion.div>
    </div>
  );
};
