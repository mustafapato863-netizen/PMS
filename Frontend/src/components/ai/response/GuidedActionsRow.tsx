import { Link } from 'react-router-dom';
import { ArrowRight, ExternalLink, Sparkles } from 'lucide-react';
import type { AiChatResponsePayload, DeepLinkCta } from '../../../features/ai/types';

interface GuidedActionsRowProps {
  response: AiChatResponsePayload;
  isPerformanceAnswer: boolean;
  primarySourceLink: DeepLinkCta | null;
  isSending?: boolean;
  onSelectPrompt?: (prompt: string, choiceId?: string) => void;
}

export default function GuidedActionsRow({
  response,
  isPerformanceAnswer,
  primarySourceLink,
  isSending = false,
  onSelectPrompt,
}: GuidedActionsRowProps) {
  // Non-performance modes (greeting, capabilities_help, page_help, navigation, off_topic)
  if (!isPerformanceAnswer && response.outcome !== 'clarification') {
    if (response.suggested_followups.length === 0 && !primarySourceLink) {
      return null;
    }
    return (
      <div
        data-testid="ai-next-step-chips"
        className="mt-3 flex flex-wrap items-center gap-2"
      >
        {response.suggested_followups.map((followup) => (
          <button
            key={followup}
            type="button"
            disabled={isSending}
            onClick={() => onSelectPrompt?.(followup)}
            className="inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-1.5 text-left text-xs font-semibold text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50/70 hover:text-blue-700 disabled:opacity-50"
          >
            <span>{followup}</span>
            <ArrowRight size={13} className="shrink-0 text-blue-600" />
          </button>
        ))}
        {primarySourceLink && (
          <Link
            to={primarySourceLink.route}
            data-testid="ai-primary-source-link"
            className="inline-flex min-h-9 items-center gap-1.5 rounded-xl border border-sky-200 bg-sky-50/80 px-3 py-1.5 text-xs font-bold text-blue-700 transition-colors hover:bg-blue-600 hover:text-white"
          >
            <span>{primarySourceLink.label}</span>
          </Link>
        )}
      </div>
    );
  }

  // Analytical performance answer next steps
  const primaryFollowup = response.suggested_followups[0];
  if (!primaryFollowup && !primarySourceLink) {
    return null;
  }

  return (
    <div className="mt-3.5 flex flex-wrap items-center gap-2">
      {primaryFollowup && (
        <button
          type="button"
          data-testid="ai-primary-drilldown"
          disabled={isSending}
          onClick={() => onSelectPrompt?.(primaryFollowup)}
          className="group inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-xl border border-blue-200/90 bg-blue-50/60 px-3 py-1.5 text-left text-xs font-bold text-blue-800 transition-all hover:border-blue-400 hover:bg-blue-100/70 disabled:opacity-50"
        >
          <Sparkles size={13} className="shrink-0 text-blue-600" aria-hidden="true" />
          <span>{primaryFollowup}</span>
          <ArrowRight
            size={13}
            className="shrink-0 text-blue-600 transition-transform group-hover:translate-x-0.5"
            aria-hidden="true"
          />
        </button>
      )}

      {primarySourceLink && (
        <Link
          to={primarySourceLink.route}
          data-testid="ai-primary-source-link"
          className="inline-flex min-h-9 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 transition-colors hover:border-blue-300 hover:bg-slate-50 hover:text-blue-700"
        >
          <span>{primarySourceLink.label}</span>
          <ExternalLink size={12} className="shrink-0 text-slate-400" aria-hidden="true" />
        </Link>
      )}
    </div>
  );
}
