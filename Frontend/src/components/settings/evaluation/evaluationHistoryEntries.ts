import { formatDistanceToNow } from 'date-fns';
import type { EvaluationVersion } from '../evaluationSettings';

/** The checksum characters shown by default. The full value is kept for the copy action only. */
export const SHORT_CHECKSUM_LENGTH = 8;

/** A who-and-when line such as "Created 3 days ago by Ruth". The absolute time is the tooltip. */
export type PersonLine = {
  text: string;
  title: string | null;
};

export type VersionEntry = {
  /** "Version 2", or "Version" when the number is not known. */
  title: string;
  /** Month and status on one line, for example "July · approved". */
  detail: string;
  status: string;
  /** The full checksum, trimmed. Used by the copy action and never shown in full by default. */
  checksum: string | null;
  shortChecksum: string | null;
  sourceVersionId: string | null;
  /** Null when neither the time nor the name is known, so nothing is shown as "unknown". */
  created: PersonLine | null;
  /** Null for a version that was never approved, and when neither the time nor the approver is known. */
  approved: PersonLine | null;
};

function validTime(value: string | null | undefined): Date | null {
  if (typeof value !== 'string' || !value.trim()) return null;
  const time = new Date(value.trim());
  return Number.isNaN(time.getTime()) ? null : time;
}

/**
 * "Created 3 days ago by Ruth". A part that is missing is left out of the sentence, never shown as unknown.
 * The absolute time is returned for the tooltip.
 */
export function personLine(verb: 'Created' | 'Approved', at: string | null | undefined, by: string | null | undefined): PersonLine | null {
  const time = validTime(at);
  const name = typeof by === 'string' && by.trim() ? by.trim() : null;
  if (!time && !name) return null;
  const when = time ? formatDistanceToNow(time, { addSuffix: true }) : null;
  return {
    text: [verb, when, name ? `by ${name}` : null].filter(Boolean).join(' '),
    title: time ? time.toLocaleString() : null,
  };
}

/**
 * The timeline view of one saved version. It reads the same fields as versionLabel but keeps the checksum out of the
 * visible text. versionLabel stays exported and unchanged for other callers.
 */
export function versionEntry(item: EvaluationVersion, monthName: string): VersionEntry {
  const status = item.status || 'unknown';
  const checksum = typeof item.checksum === 'string' && item.checksum.trim() ? item.checksum.trim() : null;
  return {
    title: item.version_number != null ? `Version ${item.version_number}` : 'Version',
    detail: [item.month_name || monthName, status].filter(Boolean).join(' · '),
    status,
    checksum,
    shortChecksum: checksum ? checksum.slice(0, SHORT_CHECKSUM_LENGTH) : null,
    sourceVersionId: item.source_version_id || null,
    created: personLine('Created', item.created_at, item.created_by),
    approved: personLine('Approved', item.approved_at, item.approved_by),
  };
}
