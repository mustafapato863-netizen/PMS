import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, Clock, PhoneOff, ChevronDown, ChevronUp } from 'lucide-react';
import type { AgentWithLocation } from '../../hooks/usePerformanceData';

interface OutlierAlertsProps {
  highBookingLowAttend: AgentWithLocation[];
  highAHT: AgentWithLocation[];
  highAbandon: AgentWithLocation[];
}

interface AlertCardProps {
  title: string;
  description: string;
  agents: AgentWithLocation[];
  icon: React.ReactNode;
  color: 'amber' | 'rose' | 'orange';
  renderDetail: (a: AgentWithLocation) => string;
}

const colorStyles = {
  amber: {
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    icon: 'bg-amber-100 text-amber-600',
    badge: 'bg-amber-500',
    title: 'text-amber-800',
    row: 'hover:bg-amber-100/50',
  },
  rose: {
    bg: 'bg-rose-50',
    border: 'border-rose-200',
    icon: 'bg-rose-100 text-rose-600',
    badge: 'bg-rose-500',
    title: 'text-rose-800',
    row: 'hover:bg-rose-100/50',
  },
  orange: {
    bg: 'bg-orange-50',
    border: 'border-orange-200',
    icon: 'bg-orange-100 text-orange-600',
    badge: 'bg-orange-500',
    title: 'text-orange-800',
    row: 'hover:bg-orange-100/50',
  },
};

const AlertCard = ({ title, description, agents, icon, color, renderDetail }: AlertCardProps) => {
  const [expanded, setExpanded] = useState(false);
  const cs = colorStyles[color];
  const count = agents.length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      className={`${cs.bg} border ${cs.border} rounded-2xl p-4 transition-all`}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <div className={`w-9 h-9 rounded-xl ${cs.icon} flex items-center justify-center shrink-0`}>
            {icon}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className={`text-sm font-bold ${cs.title}`}>{title}</h4>
              <span className={`${cs.badge} text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full`}>
                {count}
              </span>
            </div>
            <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">{description}</p>
          </div>
        </div>
        {count > 0 && (
          <button
            onClick={() => setExpanded(!expanded)}
            aria-label={expanded ? 'Collapse' : 'Expand'}
            className="p-1.5 rounded-lg hover:bg-white/60 transition-colors text-slate-400"
          >
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        )}
      </div>

      <AnimatePresence>
        {expanded && count > 0 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-3 space-y-1 max-h-40 overflow-y-auto">
              {agents.slice(0, 10).map((a) => (
                <div
                  key={`${a.identity.name}-${a.identity.month}`}
                  className={`flex items-center justify-between px-3 py-1.5 rounded-lg text-xs ${cs.row} transition-colors`}
                >
                  <span className="font-medium text-slate-700 truncate max-w-[140px]">
                    {a.identity.name}
                  </span>
                  <span className="font-bold text-slate-600 shrink-0 ml-2">
                    {renderDetail(a)}
                  </span>
                </div>
              ))}
              {agents.length > 10 && (
                <p className="text-[10px] text-slate-400 text-center py-1">
                  +{agents.length - 10} more agents
                </p>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

const OutlierAlerts = ({ highBookingLowAttend, highAHT, highAbandon }: OutlierAlertsProps) => {
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <AlertCard
        title="High Booking, Low Attend"
        description="Agents converting calls to bookings but patients not showing up"
        agents={highBookingLowAttend}
        icon={<AlertTriangle size={18} />}
        color="amber"
        renderDetail={(a) =>
          `Book ${(a.actual.booking_rate * 100).toFixed(0)}% / Attend ${(a.actual.attend_rate * 100).toFixed(0)}%`
        }
      />
      <AlertCard
        title="High Handle Time"
        description="Agents exceeding the 2:30 AHT target threshold"
        agents={highAHT}
        icon={<Clock size={18} />}
        color="orange"
        renderDetail={(a) => `AHT: ${a.calls.aht_raw.slice(3)}`}
      />
      <AlertCard
        title="High Abandon Rate"
        description="Agents with abandon rate exceeding 2% threshold"
        agents={highAbandon}
        icon={<PhoneOff size={18} />}
        color="rose"
        renderDetail={(a) =>
          `${(a.actual.abandon_rate * 100).toFixed(1)}% (${a.calls.abandoned} calls)`
        }
      />
    </div>
  );
};

export default OutlierAlerts;
