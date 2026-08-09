import { TrendingUp, TrendingDown, AlertTriangle, Lightbulb } from 'lucide-react';
import type { LocationSummary } from '../../hooks/usePerformanceData';

interface ExecutiveInsightsProps {
  locationSummaries: LocationSummary[];
  noShowRate: number;
}

const ExecutiveInsights = ({ locationSummaries, noShowRate }: ExecutiveInsightsProps) => {

  // Find worst location by no-show
  const sortedByNoShow = [...locationSummaries].sort((a, b) => b.noShowRate - a.noShowRate);
  const worstLocation = sortedByNoShow[0];

  // Potential additional visits if no-show reduced to 20%
  const totalBookings = locationSummaries.reduce((s, l) => s + l.bookings, 0);
  const targetNoShow = 0.20;
  const additionalVisits =
    noShowRate > targetNoShow
      ? Math.round(totalBookings * (noShowRate - targetNoShow))
      : 0;

  return (
    <div className="bg-slate-900 rounded-2xl p-6 shadow-sm border border-slate-800 h-full flex flex-col">
      <h3 className="text-sm font-extrabold text-white uppercase tracking-wider mb-5 flex items-center gap-2">
        <Lightbulb className="w-5 h-5 text-amber-400" />
        Actionable Executive Insights
      </h3>
      <div className="space-y-5 flex-1 overflow-y-auto pr-2 custom-scrollbar">
        
        {/* Insight 1: Value Leakage */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="w-4 h-4 text-red-400" />
            <h4 className="text-sm font-bold text-red-400">Issue: High Overall No-Show Rate ({(noShowRate * 100).toFixed(1)}%)</h4>
          </div>
          <div className="space-y-2 text-xs">
            <p><span className="text-slate-400 font-semibold">Root Cause:</span> <span className="text-slate-200">Lack of proactive 24h appointment confirmations and zero-penalty cancellation culture.</span></p>
            <p><span className="text-slate-400 font-semibold">Clear Action:</span> <span className="text-blue-300 font-medium">Implement automated WhatsApp/SMS confirmation workflow with a mandatory "Confirm/Cancel" reply 24 hours prior.</span></p>
            <p><span className="text-slate-400 font-semibold">Expected Impact:</span> <span className="text-emerald-400 font-bold">Recover ~{additionalVisits.toLocaleString()} lost visits annually.</span></p>
          </div>
        </div>

        {/* Insight 2: Location Performance */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingDown className="w-4 h-4 text-amber-400" />
            <h4 className="text-sm font-bold text-amber-400">Issue: {worstLocation?.location} Underperformance</h4>
          </div>
          <div className="space-y-2 text-xs">
            <p><span className="text-slate-400 font-semibold">Root Cause:</span> <span className="text-slate-200">{worstLocation?.location} has the highest no-show rate ({worstLocation?.noShowRate.toFixed(1)}%). Potential issues with local patient demographic engagement or clinic accessibility.</span></p>
            <p><span className="text-slate-400 font-semibold">Clear Action:</span> <span className="text-blue-300 font-medium">Deploy a targeted call campaign for {worstLocation?.location} patients 48h before appointments and offer telehealth alternatives.</span></p>
            <p><span className="text-slate-400 font-semibold">Expected Impact:</span> <span className="text-emerald-400 font-bold">Drop no-show rate by 10-15% in the worst performing branch.</span></p>
          </div>
        </div>

        {/* Insight 3: Agent AHT & Conversion */}
        <div className="bg-white/5 border border-white/10 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <TrendingUp className="w-4 h-4 text-emerald-400" />
            <h4 className="text-sm font-bold text-emerald-400">Opportunity: Booking Conversion Optimization</h4>
          </div>
          <div className="space-y-2 text-xs">
            <p><span className="text-slate-400 font-semibold">Root Cause:</span> <span className="text-slate-200">Top agents are closing bookings efficiently, but bottom quartile agents struggle to convert inquiries to appointments.</span></p>
            <p><span className="text-slate-400 font-semibold">Clear Action:</span> <span className="text-blue-300 font-medium">Pair bottom 3 agents with top 3 agents for peer-shadowing specifically focusing on objection handling.</span></p>
            <p><span className="text-slate-400 font-semibold">Expected Impact:</span> <span className="text-emerald-400 font-bold">+5% bump in overall booking conversion.</span></p>
          </div>
        </div>

      </div>
    </div>
  );
};

export default ExecutiveInsights;
