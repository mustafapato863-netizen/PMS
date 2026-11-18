import type { AiChatResponsePayload, SourceCitationPill } from '../../../features/ai/types';

/**
 * Replaces technical shorthand like "-2.6 pp" with readable manager phrasing "-2.6 pts"
 * while leaving exact numerical values untouched.
 */
export function formatManagerReadableText(text: string): string {
  if (!text) return text;
  return text.replace(/(\d+(?:\.\d+)?)\s*pp\b/g, '$1 pts');
}

/**
 * Extracts evaluated headcount from citations (e.g. "Evaluated · 71" -> "71 evaluated")
 * so it can be displayed once in the quiet header instead of a separate bottom pill.
 */
export function extractEvaluatedLabel(citations: SourceCitationPill[]): string | null {
  const metricPill = citations.find((pill) =>
    /^evaluated\s*·\s*\d+/i.test(pill.label.trim()),
  );
  if (!metricPill) return null;
  const match = metricPill.label.match(/(\d+)/);
  if (!match) return null;
  const count = Number(match[1]);
  return `${count} ${count === 1 ? 'record' : 'evaluated'}`;
}

/**
 * Filters out redundant scope/period/branch/basis pills that are already surfaced
 * in the top context eyebrow or inline basis note, keeping only non-redundant citations
 * inside the collapsible audit details panel.
 */
export function getAuditCitations(
  response: AiChatResponsePayload,
): SourceCitationPill[] {
  return response.citations.filter((pill) => {
    if (pill.category === 'basis' && response.basis_warning) {
      return false;
    }
    return true;
  });
}

/**
 * Expands bare "Month-over-month scoring basis changed" into a plain-English note.
 */
export function formatBasisWarning(warning: string): string {
  const trimmed = warning.trim();
  if (trimmed.toLowerCase() === 'month-over-month scoring basis changed') {
    return 'KPI weights or scoring rules changed compared to last month — interpret month-over-month shifts with care.';
  }
  return formatManagerReadableText(trimmed);
}
