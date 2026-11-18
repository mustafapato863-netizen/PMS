import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowRight,
  ChevronDown,
  ChevronUp,
  Compass,
  HelpCircle,
  Lightbulb,
  Sparkles,
} from 'lucide-react';
import type {
  AiChatResponsePayload,
  FeedbackCategoryType,
} from '../../features/ai/types';
import { apiFetch } from '../../lib/apiClient';
import ExecutiveKpiStrip from './response/ExecutiveKpiStrip';
import GuidedActionsRow from './response/GuidedActionsRow';
import InlineActionProposalCard from './response/InlineActionProposalCard';
import ResponseContextHeader from './response/ResponseContextHeader';
import ResponseFooterBar from './response/ResponseFooterBar';
import VisualEvidenceCard from './response/VisualEvidenceCard';
import {
  formatBasisWarning,
  formatManagerReadableText,
  getAuditCitations,
} from './response/responseFormatting';

export interface AiResponseCardProps {
  response: AiChatResponsePayload;
  onSelectPrompt?: (prompt: string, choiceId?: string) => void;
  onRegenerateAngle?: (nextSeed: number) => void;
  variationSeed?: number;
  isSending?: boolean;
  compact?: boolean;
  canCreateAction?: boolean;
  isFallbackData?: boolean;
  onActionSaved?: () => void;
}

export default function AiResponseCard({
  response,
  onSelectPrompt,
  onRegenerateAngle,
  variationSeed = 0,
  isSending = false,
  compact = false,
  canCreateAction = true,
  isFallbackData = false,
  onActionSaved,
}: AiResponseCardProps) {
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);
  const [showFlagForm, setShowFlagForm] = useState(false);
  const [flagCategory, setFlagCategory] = useState<FeedbackCategoryType>('wrong_data');
  const [flagReason, setFlagReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [feedbackError, setFeedbackError] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);

  const primaryCards = response.visual_cards.filter((c) => c.card_type !== 'decision_playbook');
  const playbookCards = response.visual_cards.filter((c) => c.card_type === 'decision_playbook');
  const totalDecisionsCount = playbookCards.reduce(
    (acc, c) => acc + (c.decisions?.length ?? 0),
    0,
  );

  // Show the #1 most informative visual card directly above the fold;
  // secondary visual cards & decision playbooks sit cleanly in progressive disclosure.
  const leadVisualCard = primaryCards[0] ?? null;
  const secondaryVisualCards = primaryCards.slice(1);

  const [showPlaybook, setShowPlaybook] = useState<boolean>(primaryCards.length === 0);
  const [detailsOverride, setDetailsOverride] = useState<{
    traceId: string;
    answerDetail: AiChatResponsePayload['answer_detail'];
    expanded: boolean;
  } | null>(null);

  const detailsExpanded =
    detailsOverride?.traceId === (response.trace_id ?? '') &&
    detailsOverride.answerDetail === response.answer_detail
      ? detailsOverride.expanded
      : response.answer_detail !== 'brief';

  const primarySourceLink = response.primary_source_link || response.deep_links[0] || null;
  const secondaryDeepLinks = primarySourceLink
    ? response.deep_links.filter((d) => d.route !== primarySourceLink.route)
    : response.deep_links;
  const detailBullets = response.detail_bullets ?? [];
  const auditCitations = getAuditCitations(response);

  const hasExpandableDetails =
    primaryCards.length > 0 ||
    playbookCards.length > 0 ||
    secondaryDeepLinks.length > 0 ||
    detailBullets.length > 0 ||
    auditCitations.length > 0;

  // Brief answers must already be complete in headline + narrative_bullets;
  // never slice narrative_bullets by index.
  const visibleBullets = response.narrative_bullets;

  const handleFeedback = async (
    rating: 'up' | 'down',
    category?: FeedbackCategoryType,
    reason?: string,
  ) => {
    if (submitting) return;
    setSubmitting(true);
    setFeedbackError(false);
    try {
      await apiFetch('/api/ai/feedback', {
        method: 'POST',
        body: JSON.stringify({
          trace_id: response.trace_id,
          rating,
          category: category || (rating === 'up' ? 'helpful' : flagCategory),
          ...(reason?.trim() ? { reason: reason.trim() } : {}),
        }),
      });
      setFeedback(rating);
      if (rating === 'down') {
        setShowFlagForm(false);
      } else {
        setShowFlagForm(false);
      }
    } catch {
      setFeedbackError(true);
    } finally {
      setSubmitting(false);
    }
  };

  const handleCopySummary = async () => {
    const lines = [response.headline, ...response.narrative_bullets.map((b) => `- ${b}`)].filter(
      Boolean,
    );
    const text = lines.join('\n');
    setCopyError(false);
    try {
      if (typeof navigator === 'undefined' || typeof navigator.clipboard?.writeText !== 'function') {
        throw new Error('Clipboard API unavailable');
      }
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // In insecure contexts or when clipboard permission is denied, never claim success.
      setCopied(false);
      setCopyError(true);
    }
  };

  const isLiveSynthesis =
    (response.provider_used === 'cloudflare' || response.provider_used === 'gemini') &&
    response.answer_source !== 'fallback' &&
    response.answer_source !== 'deterministic';
  const capabilityMode = response.capability_mode ?? 'performance_query';
  const isPerformanceAnswer =
    capabilityMode === 'performance_query' && response.outcome === 'answer';
  const showScopeBanner = Boolean(
    (response.effective_context_label || response.scope_banner) &&
      capabilityMode !== 'greeting' &&
      capabilityMode !== 'off_topic',
  );
  const showCopyButton =
    response.outcome === 'answer' &&
    capabilityMode !== 'greeting' &&
    capabilityMode !== 'off_topic';

  return (
    <div className={compact ? 'block' : 'flex items-start gap-3'}>
      {/* Assistant Avatar Badge (full workspace view) */}
      {!compact && (
        <div
          className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-700 text-white shadow-xs"
          aria-hidden="true"
        >
          <Sparkles size={15} />
        </div>
      )}

      {/* Main Executive Response Card */}
      <div
        className={`min-w-0 flex-1 rounded-2xl border border-slate-200/90 bg-white ${
          compact ? 'p-3.5 shadow-2xs' : 'p-4 sm:p-5 shadow-[0_4px_20px_rgb(15,23,42,0.04)]'
        }`}
      >
        {/* 0. Single Quiet Context Eyebrow + Verification Popover */}
        <ResponseContextHeader
          response={response}
          isPerformanceAnswer={isPerformanceAnswer}
          isLiveSynthesis={isLiveSynthesis}
          showScopeBanner={showScopeBanner}
        />

        {/* 1. WHAT IS HAPPENING — Plain-English Headline + Always-Visible KPI Strip */}
        <p
          dir="auto"
          data-testid={compact ? 'contextual-assistant-direct-answer' : undefined}
          className={`font-bold leading-relaxed text-slate-900 ${
            compact ? 'text-sm' : 'text-[15px] sm:text-base'
          }`}
        >
          {formatManagerReadableText(response.headline)}
        </p>

        <ExecutiveKpiStrip tiles={response.summary_tiles ?? []} compact={compact} />

            <div className="flex flex-wrap items-center gap-1.5">
              {isPerformanceAnswer && onRegenerateAngle && (
                <button
                  type="button"
                  data-testid="ai-regenerate-angle-btn"
                  aria-label="Get a different reply angle"
                  disabled={isSending}
                  onClick={() => onRegenerateAngle((variationSeed ?? 0) + 1)}
                  className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-xs font-bold text-slate-700 transition-colors hover:border-blue-400 hover:text-blue-600 disabled:opacity-50"
                >
                  <RefreshCw size={12} />
                  <span>Different angle</span>
                </button>
              )}
              {showCopyButton && (
                <button
                  type="button"
                  data-testid="ai-copy-summary-btn"
                  aria-label={copied ? 'Summary copied' : 'Copy summary'}
                  onClick={() => void handleCopySummary()}
                  className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-xs font-bold text-slate-700 transition-colors hover:border-blue-400 hover:text-blue-600"
                >
                  {copied ? <Check size={12} className="text-emerald-600" /> : <Copy size={12} />}
                  <span>{copied ? 'Copied' : 'Copy'}</span>
                </button>
              )}
              {copyError && (
                <span role="status" className="text-xs font-medium text-amber-700">
                  Copy unavailable. Select the text to copy manually.
                </span>
              )}
              {copied && (
                <span role="status" className="sr-only">Summary copied to clipboard.</span>
              )}
              {hasExpandableDetails && (
                <button
                  type="button"
                  aria-expanded={detailsExpanded}
                  onClick={() =>
                    setDetailsOverride({
                      traceId: response.trace_id ?? '',
                      answerDetail: response.answer_detail,
                      expanded: !detailsExpanded,
                    })
                  }
                  className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-xs font-extrabold text-slate-700 transition-colors hover:border-blue-400 hover:text-blue-600"
                >
                  <span>{detailsExpanded ? 'Hide details' : 'View details'}</span>
                  {detailsExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                </button>
              )}
            </div>
          </div>
        )}

        {/* Supporting Takeaway Bullets (primary driver in Brief mode; all bullets in Details mode) */}
        {visibleBullets.length > 0 && (
          <ul
            dir="auto"
            data-testid={compact ? 'contextual-assistant-bullets' : undefined}
            className="mt-3 space-y-1.5 rounded-xl border border-slate-200/75 bg-slate-50/60 px-3.5 py-2.5 text-sm leading-relaxed text-slate-700"
          >
            {visibleBullets.map((bullet, idx) => (
              <li key={idx} className="flex items-start gap-2">
                <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-600" />
                <span>{formatManagerReadableText(bullet)}</span>
              </li>
            ))}
          </ul>
        )}

        {/* Primary Visual Card (Always visible above the fold — Top 5 items inline) */}
        {leadVisualCard && <VisualEvidenceCard card={leadVisualCard} />}

        {/* Page Help Card (when capability_mode === 'page_help') */}
        {response.page_help && (
          <div className="mt-3 space-y-1.5 rounded-xl border border-slate-200 bg-slate-50/60 p-3.5">
            <div className="flex items-center gap-1.5 text-sm font-bold text-slate-900">
              <HelpCircle className="size-4 text-blue-600" />
              <span>{response.page_help.page_title}</span>
            </div>
            <p className="text-sm leading-relaxed text-slate-600">
              {response.page_help.summary}
            </p>
            {response.page_help.metric_explanation && (
              <p className="text-xs font-semibold text-blue-700">
                {response.page_help.metric_explanation}
              </p>
            )}
          </div>
        )}

        {/* Navigation Targets (when capability_mode === 'navigation') */}
        {response.navigation_targets && response.navigation_targets.length > 0 && (
          <div className="mt-3 space-y-2">
            {response.navigation_targets.map((nav) => (
              <Link
                key={nav.route}
                to={nav.route}
                className="flex items-center justify-between gap-2 rounded-xl border border-blue-200 bg-blue-50/60 px-3.5 py-2.5 text-sm font-semibold text-blue-800 transition-colors hover:bg-blue-100/80"
              >
                <span className="flex items-center gap-2">
                  <Compass className="size-4 shrink-0 text-blue-600" />
                  <span>{nav.label}</span>
                </span>
                <ArrowRight className="size-4 shrink-0" />
              </Link>
            ))}
          </div>
        )}

        {/* Interactive Clarification Choices */}
        {response.outcome === 'clarification' && response.clarification && (
          <div className="mt-3 rounded-xl border border-sky-200 bg-sky-50/60 p-3.5">
            <p className="text-sm font-bold text-slate-900">
              {response.clarification.question}
            </p>
            {response.clarification.choices.length > 0 && (
              <div className="mt-2.5 flex flex-wrap gap-2">
                {response.clarification.choices.map((choice) => (
                  <button
                    key={choice.id}
                    type="button"
                    data-testid={`ai-clarification-choice-${choice.id}`}
                    onClick={() => onSelectPrompt?.(choice.prompt_to_send || choice.label, choice.id)}
                    className="inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-xl border border-sky-300 bg-white px-3 py-1.5 text-xs font-bold text-blue-700 transition-all hover:bg-blue-600 hover:text-white"
                  >
                    <span>{choice.label}</span>
                    <ArrowRight size={12} />
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Single Plain-English Basis Note (Deduplicated) */}
        {response.basis_warning && (
          <div className="mt-3 flex items-start gap-2 rounded-xl border border-amber-200/80 bg-amber-50/70 px-3 py-2 text-xs font-medium text-amber-900">
            <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-600" />
            <span>{formatBasisWarning(response.basis_warning)}</span>
          </div>
        )}

        {/* Inline Corrective Action Proposal & Review Form */}
        {response.action_proposal && (
          <InlineActionProposalCard
            proposal={response.action_proposal}
            traceId={response.trace_id}
            canCreateAction={canCreateAction}
            isFallbackData={isFallbackData}
            onActionSaved={onActionSaved}
          />
        )}

        {/* 3. WHAT ACTION TO TAKE — Guided Next Steps Row */}
        <GuidedActionsRow
          response={response}
          isPerformanceAnswer={isPerformanceAnswer}
          primarySourceLink={primarySourceLink}
          isSending={isSending}
          onSelectPrompt={onSelectPrompt}
        />

        {/* Progressive Disclosure Details Region (Supporting Evidence, Playbook & Audit Citations) */}
        {detailsExpanded && (
          <div className="mt-3.5 space-y-3 border-t border-slate-100 pt-3">
            {detailBullets.length > 0 && (
              <div
                data-testid="ai-detail-bullets"
                className="rounded-xl border border-slate-200/80 bg-slate-50/70 px-3.5 py-2.5"
              >
                <p className="mb-1 text-xs font-semibold text-slate-500">Supporting Evidence</p>
                <ul
                  dir="auto"
                  className="space-y-1 text-xs font-medium leading-relaxed text-slate-600"
                >
                  {detailBullets.map((bullet, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" />
                      <span>{formatManagerReadableText(bullet)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {secondaryVisualCards.map((card, index) => (
              <VisualEvidenceCard key={`${card.card_type}-${index}`} card={card} />
            ))}

            {playbookCards.length > 0 && (
              <div>
                {primaryCards.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setShowPlaybook((prev) => !prev)}
                    className="inline-flex cursor-pointer items-center gap-1.5 rounded-xl border border-sky-200 bg-sky-50/80 px-3 py-1.5 text-xs font-bold text-blue-700 transition-all hover:border-blue-400 hover:bg-blue-600 hover:text-white"
                  >
                    <Lightbulb size={13} />
                    <span>
                      {showPlaybook
                        ? 'Hide Recommended Decisions'
                        : `View Recommended Decisions (${totalDecisionsCount})`}
                    </span>
                    {showPlaybook ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  </button>
                )}
                {showPlaybook &&
                  playbookCards.map((card, index) => (
                    <VisualEvidenceCard key={`playbook-${index}`} card={card} />
                  ))}
              </div>
            )}

            {secondaryDeepLinks.length > 0 && (
              <div className="flex flex-wrap items-center gap-2">
                {secondaryDeepLinks.map((cta) => (
                  <Link
                    key={cta.route}
                    to={cta.route}
                    className="inline-flex items-center gap-1 rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-semibold text-blue-700 transition-colors hover:border-blue-300 hover:bg-blue-50"
                  >
                    <span>{cta.label}</span>
                  </Link>
                ))}
              </div>
            )}

            {auditCitations.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 pt-1">
                <span className="text-xs font-semibold text-slate-400">Audit scope:</span>
                {auditCitations.map((pill) => (
                  <span
                    key={pill.label}
                    className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ${
                      pill.warning
                        ? 'border border-amber-200 bg-amber-50 text-amber-800'
                        : 'border border-slate-200/80 bg-slate-50 text-slate-600'
                    }`}
                  >
                    {pill.label}
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Quiet Bottom Utility & Feedback Bar */}
        <ResponseFooterBar
          traceId={response.trace_id}
          hasExpandableDetails={hasExpandableDetails}
          detailsExpanded={detailsExpanded}
          onToggleDetails={() =>
            setDetailsOverride({
              traceId: response.trace_id ?? '',
              answerDetail: response.answer_detail,
              expanded: !detailsExpanded,
            })
          }
          showRegenerateAngle={isPerformanceAnswer && Boolean(onRegenerateAngle)}
          onRegenerateAngle={
            onRegenerateAngle ? () => onRegenerateAngle((variationSeed ?? 0) + 1) : undefined
          }
          showCopyButton={showCopyButton}
          copied={copied}
          onCopySummary={() => void handleCopySummary()}
          isSending={isSending}
          feedback={feedback}
          showFlagForm={showFlagForm}
          onToggleFlagForm={() => setShowFlagForm((prev) => !prev)}
          flagCategory={flagCategory}
          onChangeFlagCategory={setFlagCategory}
          flagReason={flagReason}
          onChangeFlagReason={setFlagReason}
          submittingFeedback={submitting}
          feedbackError={feedbackError}
          onSubmitFeedback={(rating, category, reason) => void handleFeedback(rating, category, reason)}
        />
      </div>
    </div>
  );
}
