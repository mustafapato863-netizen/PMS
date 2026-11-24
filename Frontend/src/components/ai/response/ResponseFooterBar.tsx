import {
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  RefreshCw,
  ThumbsDown,
  ThumbsUp,
} from 'lucide-react';
import type { FeedbackCategoryType } from '../../../features/ai/types';

interface ResponseFooterBarProps {
  traceId?: string;
  hasExpandableDetails: boolean;
  detailsExpanded: boolean;
  onToggleDetails: () => void;
  showRegenerateAngle: boolean;
  onRegenerateAngle?: () => void;
  showCopyButton: boolean;
  copied: boolean;
  onCopySummary: () => void;
  isSending?: boolean;
  feedback: 'up' | 'down' | null;
  showFlagForm: boolean;
  onToggleFlagForm: () => void;
  flagCategory: FeedbackCategoryType;
  onChangeFlagCategory: (category: FeedbackCategoryType) => void;
  flagReason: string;
  onChangeFlagReason: (reason: string) => void;
  submittingFeedback: boolean;
  feedbackError: boolean;
  onSubmitFeedback: (rating: 'up' | 'down', category?: FeedbackCategoryType, reason?: string) => void;
}

export default function ResponseFooterBar({
  traceId,
  hasExpandableDetails,
  detailsExpanded,
  onToggleDetails,
  showRegenerateAngle,
  onRegenerateAngle,
  showCopyButton,
  copied,
  onCopySummary,
  isSending = false,
  feedback,
  showFlagForm,
  onToggleFlagForm,
  flagCategory,
  onChangeFlagCategory,
  flagReason,
  onChangeFlagReason,
  submittingFeedback,
  feedbackError,
  onSubmitFeedback,
}: ResponseFooterBarProps) {
  const showAnyControls =
    hasExpandableDetails || showRegenerateAngle || showCopyButton || Boolean(traceId);

  if (!showAnyControls) return null;

  return (
    <>
      <div className="mt-3.5 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-2.5">
        <div className="flex flex-wrap items-center gap-2">
          {hasExpandableDetails && (
            <button
              type="button"
              aria-expanded={detailsExpanded}
              onClick={onToggleDetails}
              className="inline-flex cursor-pointer items-center gap-1 rounded-lg px-2 py-1 text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900"
            >
              <span>{detailsExpanded ? 'Hide details' : 'View details'}</span>
              {detailsExpanded ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          {showRegenerateAngle && onRegenerateAngle && (
            <button
              type="button"
              data-testid="ai-regenerate-angle-btn"
              aria-label="Get a different reply angle"
              disabled={isSending}
              onClick={onRegenerateAngle}
              className="inline-flex cursor-pointer items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800 disabled:opacity-50"
            >
              <RefreshCw size={12} />
              <span>Different angle</span>
            </button>
          )}

          {showCopyButton && (
            <button
              type="button"
              data-testid="ai-copy-summary-btn"
              aria-label="Copy summary"
              onClick={onCopySummary}
              className="inline-flex cursor-pointer items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-800"
            >
              {copied ? <Check size={12} className="text-emerald-600" /> : <Copy size={12} />}
              <span>{copied ? 'Copied' : 'Copy'}</span>
            </button>
          )}

          {traceId && (
            <>
              {(showRegenerateAngle || showCopyButton) && (
                <span className="mx-0.5 h-3.5 w-px bg-slate-200" aria-hidden="true" />
              )}
              {feedback === 'up' && (
                <span className="mr-1 text-xs font-semibold text-emerald-600">Feedback saved</span>
              )}
              {feedback === 'down' && (
                <span className="mr-1 text-xs font-semibold text-rose-600">Feedback saved</span>
              )}
              {feedbackError && (
                <span role="alert" className="mr-1 text-xs font-semibold text-rose-600">
                  Could not save feedback. Try again.
                </span>
              )}
              <button
                type="button"
                onClick={() => onSubmitFeedback('up', 'helpful')}
                aria-label="Mark response as useful"
                title="Helpful"
                disabled={submittingFeedback}
                className={`inline-flex cursor-pointer items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${
                  feedback === 'up'
                    ? 'bg-emerald-50 font-semibold text-emerald-700'
                    : 'text-slate-500 hover:bg-emerald-50 hover:text-emerald-700'
                }`}
              >
                <ThumbsUp size={12} />
                <span>Helpful</span>
              </button>
              <button
                type="button"
                onClick={onToggleFlagForm}
                aria-label="Flag response as inaccurate"
                aria-expanded={showFlagForm}
                title="Not helpful"
                disabled={submittingFeedback}
                className={`inline-flex cursor-pointer items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium transition-colors disabled:opacity-50 ${
                  feedback === 'down' || showFlagForm
                    ? 'bg-rose-50 font-semibold text-rose-700'
                    : 'text-slate-500 hover:bg-rose-50 hover:text-rose-700'
                }`}
              >
                <ThumbsDown size={12} />
                <span>Not helpful</span>
              </button>
            </>
          )}
        </div>
      </div>

      {traceId && showFlagForm && (
        <div
          data-testid="ai-feedback-flag-panel"
          className="mt-2.5 rounded-xl border border-rose-200/80 bg-rose-50/40 p-3"
        >
          <p className="text-xs font-bold text-slate-800">
            What went wrong? Select a tag for Admin review:
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {(
              [
                { key: 'wrong_data', label: 'Wrong data' },
                { key: 'incomplete_response', label: 'Missing part' },
                { key: 'incorrect_scope', label: 'Wrong context' },
                { key: 'misunderstood_question', label: 'Misunderstood question' },
                { key: 'lost_context', label: 'Lost context' },
                { key: 'too_long', label: 'Too long' },
              ] as const
            ).map((tag) => {
              const selected = flagCategory === tag.key;
              return (
                <button
                  key={tag.key}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => onChangeFlagCategory(tag.key)}
                  className={`cursor-pointer rounded-full border px-2.5 py-1 text-xs font-semibold transition-colors ${
                    selected
                      ? 'border-rose-500 bg-rose-600 text-white'
                      : 'border-slate-200 bg-white text-slate-700 hover:border-rose-300 hover:text-rose-700'
                  }`}
                >
                  {tag.label}
                </button>
              );
            })}
          </div>
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <input
              type="text"
              value={flagReason}
              onChange={(e) => onChangeFlagReason(e.target.value)}
              maxLength={120}
              aria-label="Optional feedback note"
              placeholder="Optional short note (max 120 chars)"
              className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-800 placeholder:text-slate-400 focus:border-rose-400 focus:outline-none"
            />
            <button
              type="button"
              disabled={submittingFeedback}
              onClick={() => onSubmitFeedback('down', flagCategory, flagReason)}
              className="cursor-pointer rounded-full bg-rose-600 px-3 py-1.5 text-xs font-bold text-white transition-colors hover:bg-rose-700 disabled:opacity-50"
            >
              {submittingFeedback ? 'Sending…' : 'Send feedback'}
            </button>
            <button
              type="button"
              disabled={submittingFeedback}
              onClick={onToggleFlagForm}
              className="cursor-pointer rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100"
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </>
  );
}
