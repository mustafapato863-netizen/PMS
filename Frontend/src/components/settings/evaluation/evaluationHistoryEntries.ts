import type { EvaluationVersion } from '../evaluationSettings';

/** The checksum characters shown by default. The full value is kept for the copy action only. */
export const SHORT_CHECKSUM_LENGTH = 8;

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
};

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
  };
}
