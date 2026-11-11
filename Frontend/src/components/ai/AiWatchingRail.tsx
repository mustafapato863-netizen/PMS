import { AlertTriangle, ArrowRight, CheckCircle2, Clock, ShieldCheck, Sparkles } from 'lucide-react';
import type { AiGuardrailItem, AiWatchingAlertItem } from '../../features/ai/types';

interface AiWatchingRailProps {
  alerts: AiWatchingAlertItem[];
  guardrails: AiGuardrailItem[];
  isLoading: boolean;
  onSelectAlert: (prompt: string) => void;
}

export default function AiWatchingRail({
  alerts,
  guardrails,
  isLoading,
  onSelectAlert,
}: AiWatchingRailProps) {
  return (
    <aside aria-label="AI live monitoring and guardrails" className="space-y-3">
      {/* Compact AI is watching Card */}
      <div className="rounded-3xl border border-slate-200/80 bg-white/95 p-4 shadow-[0_8px_28px_rgb(15,23,42,0.05)]">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <Sparkles size={15} className="text-blue-600" />
            <h2 className="text-xs font-extrabold tracking-tight text-slate-900">
              AI is watching
            </h2>
          </div>
          <span
            className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[11px] font-bold text-emerald-700"
            aria-label={`${alerts.length} watching ${alerts.length === 1 ? 'alert' : 'alerts'}`}
          >
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" aria-hidden="true" />
            {alerts.length}
          </span>
        </div>

        {isLoading ? (
          <div className="space-y-2" aria-label="Loading live alerts">
            {[0, 1, 2].map((idx) => (
              <div key={idx} className="h-14 animate-pulse rounded-xl bg-slate-100" />
            ))}
          </div>
        ) : alerts.length === 0 ? (
          <p className="rounded-xl border border-slate-200/80 bg-slate-50/70 p-3 text-xs font-medium text-slate-600">
            No critical anomalies detected for the active scope.
          </p>
        ) : (
          <div className="space-y-2">
            {alerts.map((alert, idx) => {
              const isFlaggedCount =
                alert.badge_text?.toLowerCase().includes('flagged') || idx === 2;
              const iconTileClass = isFlaggedCount
                ? 'bg-gradient-to-br from-emerald-500 to-green-600 text-white shadow-xs shadow-emerald-500/20'
                : 'bg-gradient-to-br from-sky-500 to-blue-600 text-white shadow-xs shadow-blue-500/20';
              const badgePillClass = isFlaggedCount
                ? 'bg-emerald-100/90 text-emerald-800'
                : 'bg-sky-100/90 text-sky-800';

              return (
                <button
                  key={alert.id}
                  type="button"
                  onClick={() => onSelectAlert(alert.prompt_to_ask)}
                  className="group flex w-full items-center justify-between gap-2.5 rounded-xl border border-slate-200/80 bg-slate-50/60 p-2.5 text-left transition-all hover:border-blue-300 hover:bg-white hover:shadow-xs"
                >
                  <div className="flex min-w-0 items-start gap-2.5">
                    <div
                      className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${iconTileClass}`}
                    >
                      {isFlaggedCount ? <Clock size={14} /> : <AlertTriangle size={14} />}
                    </div>
                    <div className="min-w-0">
                      {alert.badge_text && (
                        <span
                          className={`mb-0.5 inline-block rounded px-1.5 py-0.5 text-[9px] font-extrabold uppercase tracking-wider ${badgePillClass}`}
                        >
                          {alert.badge_text}
                        </span>
                      )}
                      <p className="line-clamp-1 text-[11px] font-extrabold leading-snug text-slate-900">
                        {alert.title}
                      </p>
                      <p className="truncate text-[10px] font-medium text-slate-500">
                        {alert.subtitle}
                      </p>
                    </div>
                  </div>
                  <ArrowRight
                    size={13}
                    className="shrink-0 text-slate-400 transition-transform group-hover:translate-x-0.5 group-hover:text-blue-600"
                  />
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Compact Guardrails Card */}
      <div className="rounded-3xl border border-slate-200/80 bg-white/95 p-4 shadow-[0_8px_28px_rgb(15,23,42,0.05)]">
        <div className="mb-2.5 flex items-center gap-2 border-b border-slate-100 pb-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-emerald-50 text-emerald-600">
            <ShieldCheck size={14} />
          </div>
          <h2 className="text-xs font-extrabold tracking-tight text-slate-900">Guardrails</h2>
        </div>

        <ul className="space-y-2.5">
          {guardrails.map((g) => (
            <li key={g.label} className="flex items-start gap-2 text-[11px]">
              <CheckCircle2
                size={14}
                className="mt-0.5 shrink-0 text-emerald-500"
                aria-hidden="true"
              />
              <div>
                <p className="font-extrabold text-slate-900">{g.label}</p>
                <p className="leading-snug text-slate-500">{g.description}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
