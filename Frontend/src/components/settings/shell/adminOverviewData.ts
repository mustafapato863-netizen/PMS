/** Pure readers for the three overview sources. Every field is optional, so a malformed row degrades to null or a count of zero. */

/**
 * The endpoint has no time filter. It returns the newest rows ever recorded, so this is the largest
 * page it allows. The System card counts only the rows inside SYSTEM_ERROR_WINDOW_MS.
 */
export const SYSTEM_ERROR_LIMIT = 100;

export const SYSTEM_ERROR_WINDOW_MS = 24 * 60 * 60 * 1000;

/** The clock the System card counts against. Tests replace this export to pin "now". */
export function currentTime(): number {
  return Date.now();
}

type Dict = { [key: string]: unknown };

function isRecord(value: unknown): value is Dict {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

function readCount(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function timestampOf(value: string | null): number | null {
  if (!value) return null;
  const time = Date.parse(value);
  return Number.isNaN(time) ? null : time;
}

/** Rows of a `{ success, data }` payload. Null when the request reported a failure or the shape is wrong. */
export function readRows(payload: unknown): unknown[] | null {
  if (!isRecord(payload) || payload.success === false) return null;
  return Array.isArray(payload.data) ? payload.data : null;
}

/** The newest item by timestamp. Without any timestamp, the first item (the lists arrive newest first). */
function newest<T extends { timestamp: number | null }>(items: T[]): T | null {
  let best: T | null = null;
  for (const item of items) {
    if (item.timestamp === null) continue;
    if (best === null || (best.timestamp !== null && best.timestamp < item.timestamp)) best = item;
  }
  return best ?? items[0] ?? null;
}

export type UploadKind = 'employee' | 'management';

export interface OverviewUpload {
  id: string;
  kind: UploadKind;
  filename: string | null;
  uploadedAt: string | null;
  timestamp: number | null;
  uploadedBy: string | null;
  /** Only the employee list carries a status. Management rows always have null here. */
  status: string | null;
  /** Only the employee list carries a record count. Management rows always have null here. */
  recordCount: number | null;
}

export function parseUploads(rows: unknown[], kind: UploadKind): OverviewUpload[] {
  return rows.filter(isRecord).map((row, index) => {
    const uploadedAt = readText(row.uploaded_at);
    return {
      id: readText(row.id) ?? `${kind}-${index}`,
      kind,
      filename: readText(row.filename),
      uploadedAt,
      timestamp: timestampOf(uploadedAt),
      uploadedBy: readText(row.uploaded_by),
      status: kind === 'employee' ? readText(row.status) : null,
      recordCount: kind === 'employee' ? readCount(row.record_count) : null,
    };
  });
}

export function latestUpload(uploads: OverviewUpload[]): OverviewUpload | null {
  return newest(uploads);
}

const FAILED_UPLOAD_STATUSES = new Set(['failed', 'failure', 'error']);

export function isFailedStatus(status: string | null): boolean {
  return status !== null && FAILED_UPLOAD_STATUSES.has(status.toLowerCase());
}

export interface UserSummary {
  total: number;
  byRole: Array<{ role: string; count: number }>;
  disabled: number;
  mustChangePassword: number;
  needsReassignment: number;
}

/** Same defaults as the user panel: a user without `is_active` counts as active. */
export function summarizeUsers(rows: unknown[]): UserSummary {
  const roles = new Map<string, number>();
  let total = 0;
  let disabled = 0;
  let mustChangePassword = 0;
  let needsReassignment = 0;
  for (const row of rows) {
    if (!isRecord(row)) continue;
    total += 1;
    const role = readText(row.role) ?? 'Unknown role';
    roles.set(role, (roles.get(role) ?? 0) + 1);
    if (row.is_active === false) disabled += 1;
    if (row.must_change_password === true) mustChangePassword += 1;
    if (row.legacy_role_needs_reassignment === true) needsReassignment += 1;
  }
  const byRole = [...roles]
    .map(([role, count]) => ({ role, count }))
    .sort((a, b) => b.count - a.count || a.role.localeCompare(b.role));
  return { total, byRole, disabled, mustChangePassword, needsReassignment };
}

/** The list response has no message text, only the error class, method and endpoint. */
export interface SystemErrorRow {
  occurredAt: string | null;
  timestamp: number | null;
  errorClass: string | null;
  method: string | null;
  endpoint: string | null;
}

export interface SystemErrorSummary {
  /** Errors whose occurred_at is inside the window. A missing or unparseable timestamp is never counted. */
  count: number;
  /**
   * True only when the fetch was full and every fetched row is inside the window, so the true count may be
   * higher. A short page is the complete list, so its count is exact.
   */
  capped: boolean;
  /** The newest error inside the window. */
  latest: SystemErrorRow | null;
  /** The newest error of any age with a usable timestamp, for the "Last error" line when the window is empty. */
  lastError: SystemErrorRow | null;
}

function parseSystemError(row: unknown): SystemErrorRow {
  const record: Dict = isRecord(row) ? row : {};
  const occurredAt = readText(record.occurred_at);
  return {
    occurredAt,
    timestamp: timestampOf(occurredAt),
    errorClass: readText(record.error_class),
    method: readText(record.method),
    endpoint: readText(record.endpoint),
  };
}

/** `now` is passed in so the window is deterministic under test. Timestamps at or after the window start count as inside it. */
export function summarizeSystemErrors(rows: unknown[], now: number, windowMs = SYSTEM_ERROR_WINDOW_MS): SystemErrorSummary {
  const start = now - windowMs;
  const errors = rows.map(parseSystemError);
  const dated = errors.filter((error) => error.timestamp !== null);
  const recent = errors.filter((error) => error.timestamp !== null && error.timestamp >= start);
  const allRecent = errors.length > 0 && recent.length === errors.length;
  return {
    count: recent.length,
    capped: rows.length >= SYSTEM_ERROR_LIMIT && allRecent,
    latest: newest(recent),
    lastError: newest(dated),
  };
}

export type EvaluationAttentionState = 'draft' | 'approved_not_applied';

/** One month that needs action. The link opens Evaluation settings on this scope and month. */
export interface EvaluationAttentionItem {
  scopeId: string;
  scopeName: string;
  performanceLevel: string | null;
  positionName: string;
  year: number;
  month: number;
  monthName: string;
  state: EvaluationAttentionState;
  versionId: string;
  versionNumber: number | null;
}

/**
 * Counts from GET /api/settings/evaluation/overview. A null count means the server could not decide it, so the card
 * shows what is known and does not say nothing is pending. `approvedUnconfirmed` is approved months with no revision on
 * record for their period. It is neutral: it does not raise the tone and is never an attention item.
 */
export interface EvaluationOverview {
  drafts: number;
  approvedNotApplied: number | null;
  approvedUnconfirmed: number | null;
  applied: number | null;
  attention: EvaluationAttentionItem[];
}

function readWholeCount(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value >= 0 ? value : null;
}

function readAttention(row: unknown): EvaluationAttentionItem | null {
  if (!isRecord(row)) return null;
  const state = row.state === 'draft' || row.state === 'approved_not_applied' ? row.state : null;
  const scopeId = readText(row.scope_id);
  const versionId = readText(row.version_id);
  const year = readWholeCount(row.year);
  const month = readWholeCount(row.month);
  const monthName = readText(row.month_name);
  if (!state || !scopeId || !versionId || year === null || month === null || month < 1 || month > 12 || !monthName) return null;
  return {
    scopeId,
    scopeName: readText(row.scope_display_name) ?? 'Scope',
    performanceLevel: readText(row.performance_level),
    positionName: readText(row.position_name) ?? '',
    year,
    month,
    monthName,
    state,
    versionId,
    versionNumber: typeof row.version_number === 'number' && Number.isFinite(row.version_number) ? row.version_number : null,
  };
}

/** Null when the payload is not the overview shape, so the card shows its error state instead of guessing. */
export function readEvaluationOverview(payload: unknown): EvaluationOverview | null {
  if (!isRecord(payload) || payload.success === false || !isRecord(payload.data)) return null;
  const data = payload.data;
  const drafts = readWholeCount(data.drafts);
  if (drafts === null || !Array.isArray(data.attention)) return null;
  return {
    drafts,
    approvedNotApplied: readWholeCount(data.approved_not_applied),
    approvedUnconfirmed: readWholeCount(data.approved_unconfirmed),
    applied: readWholeCount(data.applied),
    attention: data.attention.map(readAttention).filter((item): item is EvaluationAttentionItem => item !== null),
  };
}
