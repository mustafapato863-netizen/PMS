import { useState } from 'react';
import { CheckCircle2, Info, ShieldCheck, Sparkles, X } from 'lucide-react';
import type { AiChatResponsePayload } from '../../../features/ai/types';
import { extractEvaluatedLabel } from './responseFormatting';

interface ResponseContextHeaderProps {
  response: AiChatResponsePayload;
  isPerformanceAnswer: boolean;
  isLiveSynthesis: boolean;
  showScopeBanner: boolean;
}

export default function ResponseContextHeader({
  response,
  isPerformanceAnswer,
  isLiveSynthesis,
  showScopeBanner,
}: ResponseContextHeaderProps) {
  const [showPopover, setShowPopover] = useState(false);

  const contextLabel = response.effective_context_label || response.scope_banner || null;
  const evaluatedLabel = extractEvaluatedLabel(response.citations);
  const showEvaluatedInline =
    Boolean(evaluatedLabel) &&
    (!contextLabel || !contextLabel.toLowerCase().includes('evaluated'));

  if (!isPerformanceAnswer && !showScopeBanner) {
    return null;
  }

  return (
    <div className="relative mb-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
      {isPerformanceAnswer && (
        <div className="relative inline-flex items-center">
          <button
            type="button"
            data-testid="ai-provenance-badge"
            data-provenance-mode={isLiveSynthesis ? 'live-synthesis' : 'rule-verified'}
            aria-expanded={showPopover}
            aria-label="View data verification details"
            onClick={() => setShowPopover((prev) => !prev)}
            className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-emerald-200/80 bg-emerald-50/70 px-2 py-0.5 text-xs font-semibold text-emerald-800 transition-colors hover:border-emerald-300 hover:bg-emerald-100/70"
          >
            <ShieldCheck className="size-3.5 shrink-0 text-emerald-600" aria-hidden="true" />
            <span>Verified PMS Data</span>
            <Info className="size-3 shrink-0 text-emerald-600/80" aria-hidden="true" />
          </button>

          {showPopover && (
            <div
              role="region"
              aria-label="Data verification source"
              data-testid="ai-provenance-popover"
              className="absolute left-0 top-full z-30 mt-1.5 w-72 rounded-xl border border-slate-200 bg-white p-3 text-xs text-slate-700 shadow-lg"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-1.5 font-bold text-slate-900">
                  {isLiveSynthesis ? (
                    <>
                      <Sparkles className="size-3.5 text-indigo-600" />
                      <span>Live AI Synthesis</span>
                    </>
                  ) : (
                    <>
                      <CheckCircle2 className="size-3.5 text-emerald-600" />
                      <span>Rule-Verified Calculation</span>
                    </>
                  )}
                </div>
                <button
                  type="button"
                  aria-label="Close verification details"
                  onClick={() => setShowPopover(false)}
                  className="rounded p-0.5 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
                >
                  <X className="size-3.5" />
                </button>
              </div>
              <p className="mt-1.5 leading-relaxed text-slate-600">
                {isLiveSynthesis
                  ? 'Composed by the AI model and claim-verified against official PMS records within your authorized scope.'
                  : 'Computed directly by the PMS scoring engine from published records within your authorized scope.'}
              </p>
            </div>
          )}
        </div>
      )}

      {showScopeBanner && contextLabel && (
        <>
          {isPerformanceAnswer && (
            <span className="text-slate-300" aria-hidden="true">
              ·
            </span>
          )}
          <span
            data-testid="ai-scope-banner"
            className="font-medium text-slate-500"
          >
            {contextLabel}
          </span>
        </>
      )}

      {isPerformanceAnswer && showEvaluatedInline && evaluatedLabel && (
        <>
          <span className="text-slate-300" aria-hidden="true">
            ·
          </span>
          <span className="font-medium text-slate-500">{evaluatedLabel}</span>
        </>
      )}
    </div>
  );
}
