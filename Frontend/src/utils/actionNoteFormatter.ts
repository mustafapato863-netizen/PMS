const ACTION_META_PREFIX = '__pms_meta__:';

export interface ParsedActionRootCauseMeta {
  mainIssue: string;
  owner: string;
  expectedImpact: string;
  isEncoded: boolean;
}

/**
 * Parses an encoded `__pms_meta__:` root-cause note into its structured parts.
 * Falls back safely to `{ mainIssue: trimmedRaw, owner: '', expectedImpact: '', isEncoded: false }`
 * for plain strings, empty strings, or malformed JSON.
 */
export function parseActionRootCauseMeta(raw?: string | null): ParsedActionRootCauseMeta {
  const trimmed = (raw ?? '').trim();
  if (!trimmed) {
    return { mainIssue: '', owner: '', expectedImpact: '', isEncoded: false };
  }

  if (!trimmed.startsWith(ACTION_META_PREFIX)) {
    return { mainIssue: trimmed, owner: '', expectedImpact: '', isEncoded: false };
  }

  const jsonPart = trimmed.slice(ACTION_META_PREFIX.length).trim();
  try {
    const parsed = JSON.parse(jsonPart) as unknown;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return { mainIssue: trimmed, owner: '', expectedImpact: '', isEncoded: false };
    }

    const record = parsed as Record<string, unknown>;
    const mainIssue =
      typeof record.main_issue === 'string'
        ? record.main_issue.trim()
        : typeof record.mainIssue === 'string'
          ? record.mainIssue.trim()
          : '';
    const owner = typeof record.owner === 'string' ? record.owner.trim() : '';
    const expectedImpact =
      typeof record.expected_impact === 'string'
        ? record.expected_impact.trim()
        : typeof record.expectedImpact === 'string'
          ? record.expectedImpact.trim()
          : '';

    return {
      mainIssue,
      owner,
      expectedImpact,
      isEncoded: true,
    };
  } catch {
    return { mainIssue: trimmed, owner: '', expectedImpact: '', isEncoded: false };
  }
}

/**
 * Formats an action's root-cause note for human-readable display.
 * Plain notes are returned unchanged; encoded `__pms_meta__:` notes are
 * formatted as `"<mainIssue> · Owner: <owner> · Expected impact: <expectedImpact>"`.
 */
export function formatActionRootCauseNote(raw?: string | null): string {
  const trimmed = (raw ?? '').trim();
  if (!trimmed) return '';

  const parsed = parseActionRootCauseMeta(trimmed);
  if (!parsed.isEncoded) {
    return raw ?? '';
  }

  return [
    parsed.mainIssue,
    parsed.owner ? `Owner: ${parsed.owner}` : '',
    parsed.expectedImpact ? `Expected impact: ${parsed.expectedImpact}` : '',
  ]
    .filter(Boolean)
    .join(' · ');
}
