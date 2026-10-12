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
