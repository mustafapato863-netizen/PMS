import {
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  ShieldCheck,
  Sparkles,
  Users,
} from 'lucide-react';
import type { AiStarterPrompt, AiWatchingAlertItem } from '../../../features/ai/types';

interface AiMorningBriefingHomeProps {
  firstName: string;
  periodLabel: string;
  scopeSummaryLabel: string;
  summaryScore?: number | null;
  summaryScoreChange?: number | null;
  measuredRecords?: number;
  alerts: AiWatchingAlertItem[];
  starterCards: AiStarterPrompt[];
  onSelectPrompt: (prompt: string) => void;
}

const ICON_BY_KEY = {
  alert: AlertTriangle,
  users: Users,
  chart: BarChart3,
  shield: ShieldCheck,
} as const;

export default function AiMorningBriefingHome({
  firstName,
  periodLabel,
  scopeSummaryLabel,
  summaryScore,
  summaryScoreChange,
  measuredRecords = 0,
  alerts,
  starterCards,
  onSelectPrompt,
}: AiMorningBriefingHomeProps) {
  const hasScore = typeof summaryScore === 'number' && !Number.isNaN(summaryScore);
  const hasChange = typeof summaryScoreChange === 'number' && !Number.isNaN(summaryScoreChange);
  const isPositive = (summaryScoreChange ?? 0) >= 0;
  const topAlerts = alerts.slice(0, 2);

  return (
    <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center py-6">
      {/* Greeting Header */}
      <div className="text-center">
        <div className="mx-auto mb-3.5 flex h-12 w-12 items-center justify-center rounded-2xl bg-gradient-to-br from-blue-600 to-indigo-700 text-white shadow-md shadow-blue-600/20">
          <Sparkles size={22} />
        </div>

        <h2 className="text-2xl font-extrabold tracking-tight text-slate-900 sm:text-[26px]">
          Hi {firstName}, how can I help?
        </h2>
        <p className="mx-auto mt-1.5 max-w-lg text-sm leading-relaxed text-slate-500">
          Get instant executive summaries, diagnose KPI bottlenecks, compare branches, or draft
          coaching actions across <span className="font-semibold text-slate-700">{scopeSummaryLabel}</span>.
        </p>
      </div>

      {/* Live Scope Snapshot & Proactive Alerts Banner */}
      {(hasScore || topAlerts.length > 0) && (
        <div
          data-testid="ai-morning-briefing-card"
          className="mt-6 rounded-2xl border border-slate-200/90 bg-slate-50/70 p-4"
        >
          {hasScore && (
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200/70 pb-3">
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
                  Scope Pulse · {periodLabel}
                </span>
                <div className="mt-0.5 flex items-baseline gap-2.5">
                  <span className="text-2xl font-extrabold tabular-nums text-slate-900">
                    {summaryScore!.toFixed(1)}%
                  </span>
                  {hasChange && (
                    <span
                      className={`inline-flex items-center gap-0.5 rounded-md px-2 py-0.5 text-xs font-bold ${
                        isPositive
                          ? 'bg-emerald-100/80 text-emerald-800'
                          : 'bg-rose-100/80 text-rose-800'
                      }`}
                    >
                      {isPositive ? (
                        <ArrowUpRight className="size-3.5" />
                      ) : (
                        <ArrowDownRight className="size-3.5" />
                      )}
                      {isPositive ? '+' : ''}
                      {summaryScoreChange!.toFixed(1)} pts vs prior
                    </span>
                  )}
                  {measuredRecords > 0 && (
                    <span className="text-xs font-medium text-slate-500">
                      · {measuredRecords} evaluated
                    </span>
                  )}
                </div>
              </div>

              <button
                type="button"
                onClick={() => onSelectPrompt('How are we doing overall?')}
                className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-blue-200 bg-white px-3 py-1.5 text-xs font-bold text-blue-700 transition-colors hover:border-blue-400 hover:bg-blue-50"
              >
                <span>Full Executive Summary</span>
                <ArrowRight size={13} />
              </button>
            </div>
          )}

          {topAlerts.length > 0 && (
            <div className={hasScore ? 'mt-3 space-y-2' : 'space-y-2'}>
              <span className="text-xs font-semibold text-slate-500">
                Suggested focus areas right now:
              </span>
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {topAlerts.map((alert) => {
                  const isCritical = alert.severity === 'critical';
                  return (
                    <button
                      key={alert.id}
                      type="button"
                      onClick={() => onSelectPrompt(alert.prompt_to_ask)}
                      className="group flex cursor-pointer items-center justify-between gap-2.5 rounded-xl border border-slate-200/90 bg-white px-3 py-2.5 text-left transition-all hover:border-blue-300 hover:shadow-xs"
                    >
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`h-2 w-2 shrink-0 rounded-full ${
                              isCritical ? 'bg-rose-500' : 'bg-amber-500'
                            }`}
                          />
                          <p className="truncate text-sm font-bold text-slate-900">
                            {alert.title}
                          </p>
                        </div>
                        <p className="mt-0.5 truncate text-xs text-slate-500">{alert.subtitle}</p>
                      </div>
                      <ArrowRight
                        size={14}
                        className="shrink-0 text-slate-400 transition-transform group-hover:translate-x-0.5 group-hover:text-blue-600"
                      />
                    </button>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Guided Starter Workflows */}
      {starterCards.length > 0 && (
        <div className="mt-5">
          <div
            data-testid="ai-starter-suggestions"
            className={`grid w-full grid-cols-1 gap-3 ${
              starterCards.length >= 4 ? 'sm:grid-cols-2' : 'sm:grid-cols-3'
            }`}
          >
            {starterCards.map((item) => {
              const CardIcon = ICON_BY_KEY[item.icon_key] || BarChart3;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => onSelectPrompt(item.prompt)}
                  className="group flex cursor-pointer flex-col justify-between rounded-2xl border border-slate-200/90 bg-white p-4 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-blue-300 hover:shadow-sm"
                >
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-1.5 rounded-md bg-blue-50 px-2 py-0.5 text-xs font-semibold text-blue-700">
                        <CardIcon size={12} aria-hidden="true" />
                        <span>{item.badge || 'Guided Workflow'}</span>
                      </span>
                      <ArrowRight
                        size={14}
                        className="shrink-0 text-slate-400 transition-transform group-hover:translate-x-0.5 group-hover:text-blue-600"
                      />
                    </div>
                    <p className="mt-2.5 line-clamp-2 text-sm font-bold text-slate-900">
                      {item.label}
                    </p>
                  </div>
                  {item.subtitle && (
                    <p
                      dir="auto"
                      className="mt-1 line-clamp-2 text-xs leading-relaxed text-slate-500"
                    >
                      {item.subtitle}
                    </p>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
