import { motion } from 'framer-motion';
import { AlertTriangle, CalendarRange, Lock, Database } from 'lucide-react';

interface Period {
  month: string;
  year: number;
}

interface NoDataEmptyStateProps {
  availablePeriods?: Period[];
  selectedMonth?: string;
  selectedYear?: string | number | null;
  dataSource?: string | null;
  errorMessage?: string | null;
  error?: unknown;
  emptyTitle?: string;
  emptyDescription?: string;
  onSelectPeriod?: (month: string, year: number | string) => void;
}

export function NoDataEmptyState({
  availablePeriods = [],
  selectedMonth = 'All',
  selectedYear,
  errorMessage,
  error,
  emptyTitle,
  emptyDescription,
  onSelectPeriod,
}: NoDataEmptyStateProps) {
  // Parse error message if any
  const errStr = error instanceof Error
    ? error.message
    : typeof error === 'string'
    ? error
    : errorMessage || '';

  const isAuthError =
    errStr.toLowerCase().includes('authorized') ||
    errStr.toLowerCase().includes('permission') ||
    errStr.toLowerCase().includes('403');

  // Filter out duplicates and invalid periods
  const uniquePeriods = Array.from(
    new Map(
      availablePeriods
        .filter((p) => p && p.month)
        .map((p) => [`${p.month}-${p.year}`, p])
    ).values()
  );

  const hasOtherPeriods = uniquePeriods.length > 0;
  const isScopedEmpty = Boolean(emptyTitle || emptyDescription);

  return (
    <motion.div
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      className="w-full my-6"
    >
      <div
        className="glass-panel rounded-2xl p-8 border shadow-sm relative overflow-hidden"
        style={{
          background: isAuthError
            ? 'rgba(254, 242, 242, 0.78)' // Light soft red/pink glass
            : hasOtherPeriods && !isScopedEmpty
            ? 'rgba(240, 249, 255, 0.78)' // Light soft blue glass
            : 'rgba(255, 251, 235, 0.78)', // Light soft amber/yellow glass
          backdropFilter: 'blur(16px)',
          WebkitBackdropFilter: 'blur(16px)',
          borderColor: isAuthError
            ? 'rgba(239, 68, 68, 0.18)'
            : hasOtherPeriods && !isScopedEmpty
            ? 'rgba(56, 189, 248, 0.18)'
            : 'rgba(245, 158, 11, 0.18)',
        }}
      >
        <div className="flex flex-col sm:flex-row items-start gap-5">
          {/* Icon Badge */}
          <div
            className="w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 shadow-sm"
            style={{
              background: isAuthError
                ? 'rgba(239, 68, 68, 0.12)'
                : hasOtherPeriods && !isScopedEmpty
                ? 'rgba(14, 165, 233, 0.12)'
                : 'rgba(245, 158, 11, 0.12)',
              color: isAuthError
                ? '#EF4444'
                : hasOtherPeriods && !isScopedEmpty
                ? '#0EA5E9'
                : '#D97706',
            }}
          >
            {isAuthError ? (
              <Lock size={22} className="animate-pulse" />
            ) : hasOtherPeriods && !isScopedEmpty ? (
              <CalendarRange size={22} />
            ) : (
              <Database size={22} />
            )}
          </div>

          {/* Description Area */}
          <div className="space-y-3 flex-1 min-w-0">
            <h3
              className="text-lg font-extrabold tracking-tight"
              style={{
                color: isAuthError
                  ? '#991B1B'
                  : hasOtherPeriods && !isScopedEmpty
                  ? '#0369A1'
                  : '#92400E',
              }}
            >
              {isAuthError
                ? 'Authorization Context Restricted'
                : isScopedEmpty
                ? emptyTitle || 'No Performance Data for Selected Scope'
                : hasOtherPeriods
                ? 'No Performance Data for Selected Month'
                : emptyTitle || 'No Performance Data Found'}
            </h3>

            {isAuthError ? (
              <div className="space-y-2">
                <p className="text-sm font-semibold text-red-800/80 leading-relaxed">
                  One or more selected people are outside the authorized context or you do not have permission to access their scorecard.
                </p>
                <p className="text-xs font-semibold text-slate-500">
                  Try clearing the active employee search filter or switching to a team assigned under your organization hierarchy.
                </p>
              </div>
            ) : isScopedEmpty ? (
              <div className="space-y-2">
                <p className="text-sm font-semibold text-amber-900/80 leading-relaxed">
                  {emptyDescription}
                </p>
              </div>
            ) : hasOtherPeriods ? (
              <div className="space-y-3">
                <p className="text-sm font-semibold text-sky-900/80 leading-relaxed">
                  There are no performance snapshots uploaded for <strong>{selectedMonth}</strong>{selectedYear ? ` ${selectedYear}` : ''}.
                  However, performance records have been found for other months.
                </p>
                
                {/* Available Periods Helper Grid */}
                <div className="space-y-1.5">
                  <span className="text-xs font-bold text-sky-800/60 uppercase tracking-wider">Available periods in database:</span>
                  <div className="flex flex-wrap gap-2 pt-1">
                    {uniquePeriods.map((p) => (
                      <button
                        key={`${p.month}-${p.year}`}
                        onClick={() => onSelectPeriod?.(p.month, p.year)}
                        disabled={!onSelectPeriod}
                        className={`px-3 py-1.5 rounded-xl text-xs font-bold transition-all shadow-sm flex items-center gap-1 ${
                          onSelectPeriod
                            ? 'bg-white/90 border border-sky-200/60 text-sky-700 hover:bg-sky-500 hover:text-white hover:scale-102 hover:shadow cursor-pointer active:scale-98'
                            : 'bg-white/60 border border-sky-100 text-sky-600'
                        }`}
                      >
                        <CalendarRange size={11} />
                        {p.month} {p.year}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-2">
                <p className="text-sm font-semibold text-amber-900/80 leading-relaxed">
                  {emptyDescription || 'No performance snapshots or KPI definitions are available in the database for this team.'}
                </p>
                {!emptyDescription && (
                  <p className="text-xs font-semibold text-slate-500">
                    Please verify that performance files have been uploaded for this team under Settings &gt; Ingestions, or consult the system administrator for the initial configuration.
                  </p>
                )}
              </div>
            )}

            {/* Error detail */}
            {errStr && !isAuthError && (
              <div className="pt-2 mt-2 border-t border-dashed border-slate-200/50 flex items-center gap-2">
                <AlertTriangle size={13} className="text-amber-500" />
                <span className="text-xs font-bold text-slate-500">
                  {`System message: ${errStr}`}
                </span>
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  );
}

export default NoDataEmptyState;
