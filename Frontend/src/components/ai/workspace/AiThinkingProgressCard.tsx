import { useEffect, useState } from 'react';
import { CheckCircle2, Loader2, Sparkles, Square } from 'lucide-react';

const THINKING_STEPS = [
  'Checking your authorized scope & period…',
  'Reading published PMS KPI records…',
  'Verifying figures & building executive summary…',
] as const;

interface AiThinkingProgressCardProps {
  onStop?: () => void;
}

export default function AiThinkingProgressCard({ onStop }: AiThinkingProgressCardProps) {
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setStepIndex((prev) => (prev < THINKING_STEPS.length - 1 ? prev + 1 : prev));
    }, 3200);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="flex items-start gap-3" aria-label="Analyzing workspace data" role="status">
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 text-white shadow-xs">
        <Sparkles size={15} className="animate-pulse" />
      </div>

      <div className="flex-1 rounded-2xl border border-slate-200/90 bg-white p-4 shadow-2xs">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="space-y-1.5">
            {THINKING_STEPS.map((label, idx) => {
              const isDone = idx < stepIndex;
              const isCurrent = idx === stepIndex;
              if (idx > stepIndex) return null;
              return (
                <div
                  key={label}
                  className={`flex items-center gap-2 text-xs ${
                    isCurrent ? 'font-semibold text-slate-800' : 'font-medium text-slate-400'
                  }`}
                >
                  {isDone ? (
                    <CheckCircle2 className="size-3.5 shrink-0 text-emerald-500" />
                  ) : (
                    <Loader2 className="size-3.5 shrink-0 animate-spin text-blue-600" />
                  )}
                  <span>{label}</span>
                </div>
              );
            })}
          </div>

          {onStop && (
            <button
              type="button"
              onClick={onStop}
              aria-label="Stop generating response"
              className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-600 transition-colors hover:border-slate-300 hover:bg-slate-100 hover:text-slate-900"
            >
              <Square size={10} className="fill-current" />
              <span>Stop</span>
            </button>
          )}
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="h-14 animate-pulse rounded-xl bg-slate-50" />
          <div className="h-14 animate-pulse rounded-xl bg-slate-50" />
          <div className="hidden h-14 animate-pulse rounded-xl bg-slate-50 sm:block" />
          <div className="hidden h-14 animate-pulse rounded-xl bg-slate-50 sm:block" />
        </div>
      </div>
    </div>
  );
}
