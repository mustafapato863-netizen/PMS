const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const PERIOD_KEY = /^(\d{4})-(0[1-9]|1[0-2])$/;
const SUPPORTED_DIRECTIONS = new Set(['higher_better', 'lower_better']);
const SUPPORTED_TARGET_MODES = new Set(['workbook', 'fixed']);

export type EvaluationLine = {
  kpi_key: string;
  label?: string;
  weight: number;
  direction: string;
  target: number | null;
  target_mode: 'workbook' | 'fixed' | string;
  unit?: string;
};

export type EvaluationVersion = {
  id: string;
  status: string;
  lines: EvaluationLine[];
  notes?: string | null;
  month_name?: string;
  version_number?: number | null;
  checksum?: string | null;
  source_version_id?: string | null;
  source_checksum?: string | null;
};

export type EvaluationRevision = {
  id: string;
  versionId: string;
  status: string;
  createdAt: string;
  affectedCount: number | null;
  canRollback: boolean;
};

export type PeriodScope = {
  id?: string;
  readiness: string;
  block_reason?: string | null;
  history_note?: string | null;
  display_name?: string;
  performance_level?: string;
  position_name?: string;
};

export type EvaluationPeriodData = {
  versionId: string;
  status: string;
  lines: EvaluationLine[];
  notes: string;
  history: EvaluationVersion[];
  scope: PeriodScope | null;
  revisions: EvaluationRevision[];
  sourceVersionId: string;
  sourceChecksum: string;
  versionNumber: number | null;
  checksum: string;
};

export const UNSAVED_PREVIEW_NOTE = 'Save the draft before impact preview or approval. Unsaved edits are not previewed.';

export const UNSUPPORTED_FORMULA_NOTE = 'This formula is blocked in this release. Only higher-is-better and lower-is-better directions, with a workbook or fixed target, can be edited.';

export const READ_ONLY_APPROVED_NOTE = 'This approved version is read-only. Revise this month to edit a new draft. The approved version stays in history.';

/** Current date, unless the URL has a valid period or an explicit year and month. */
export function initialReportingPeriod(search: string, today = new Date()): { year: number; month: number } {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  const exact = PERIOD_KEY.exec(params.get('period')?.trim() || '');
  if (exact) return { year: Number(exact[1]), month: Number(exact[2]) };
  const year = Number(params.get('year'));
  const monthToken = params.get('month')?.trim() || '';
  const namedMonth = MONTHS.findIndex((name) => name.toLowerCase() === monthToken.toLowerCase());
  const monthNumber = /^\d+$/.test(monthToken) ? Number(monthToken) : namedMonth + 1;
  if (year >= 2000 && year <= 2100 && monthNumber >= 1 && monthNumber <= 12) {
    return { year, month: monthNumber };
  }
  return { year: today.getFullYear(), month: today.getMonth() + 1 };
}

export function lineFormulaSupported(line: Pick<EvaluationLine, 'direction' | 'target_mode'>): boolean {
  return SUPPORTED_DIRECTIONS.has(line.direction) && SUPPORTED_TARGET_MODES.has(line.target_mode);
}

export function emptyPeriod(): EvaluationPeriodData {
  return {
    versionId: '',
    status: '',
    lines: [],
    notes: '',
    history: [],
    scope: null,
    revisions: [],
    sourceVersionId: '',
    sourceChecksum: '',
    versionNumber: null,
    checksum: '',
  };
}

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function readLine(value: unknown): EvaluationLine | null {
  if (!value || typeof value !== 'object') return null;
  const line = value as EvaluationLine;
  if (typeof line.kpi_key !== 'string' || !line.kpi_key) return null;
  const target = finiteNumber(line.target);
  return {
    ...line,
    kpi_key: line.kpi_key,
    label: typeof line.label === 'string' ? line.label : line.kpi_key,
    weight: finiteNumber(line.weight) ?? line.weight,
    direction: typeof line.direction === 'string' ? line.direction : '',
    target: target === null && line.target != null ? null : target,
    target_mode: typeof line.target_mode === 'string' ? line.target_mode : 'workbook',
  };
}

function readVersion(value: unknown): EvaluationVersion | null {
  if (!value || typeof value !== 'object') return null;
  const item = value as EvaluationVersion;
  if (typeof item.id !== 'string' || !item.id) return null;
  return {
    id: item.id,
    status: typeof item.status === 'string' ? item.status : '',
    lines: Array.isArray(item.lines) ? item.lines.flatMap((line) => {
      const parsed = readLine(line);
      return parsed ? [parsed] : [];
    }) : [],
    notes: typeof item.notes === 'string' ? item.notes : null,
    month_name: typeof item.month_name === 'string' ? item.month_name : undefined,
    version_number: finiteNumber(item.version_number),
    checksum: typeof item.checksum === 'string' ? item.checksum : null,
    source_version_id: typeof item.source_version_id === 'string' ? item.source_version_id : null,
    source_checksum: typeof item.source_checksum === 'string' ? item.source_checksum : null,
  };
}

/** Draft wins. Otherwise the last approved row in payload order is the open version. */
export function selectOpenVersion(history: EvaluationVersion[]): EvaluationVersion | undefined {
  const draft = history.find((item) => item.status === 'draft');
  if (draft) return draft;
  const approved = history.filter((item) => item.status === 'approved');
  return approved[approved.length - 1] ?? history[history.length - 1];
}

function readScope(value: unknown): PeriodScope | null {
  if (!value || typeof value !== 'object') return null;
  const scope = value as PeriodScope;
  if (typeof scope.readiness !== 'string' || !scope.readiness) return null;
  return {
    id: typeof scope.id === 'string' ? scope.id : undefined,
    readiness: scope.readiness,
    block_reason: typeof scope.block_reason === 'string' ? scope.block_reason : scope.block_reason ?? null,
    history_note: typeof scope.history_note === 'string' ? scope.history_note : scope.history_note ?? null,
    display_name: typeof scope.display_name === 'string' ? scope.display_name : undefined,
    performance_level: typeof scope.performance_level === 'string' ? scope.performance_level : undefined,
    position_name: typeof scope.position_name === 'string' ? scope.position_name : undefined,
  };
}

function readRevision(value: unknown): EvaluationRevision | null {
  if (!value || typeof value !== 'object') return null;
  const item = value as { id?: unknown; version_id?: unknown; status?: unknown; created_at?: unknown; affected_count?: unknown; can_rollback?: unknown };
  if (typeof item.id !== 'string' || !item.id) return null;
  return {
    id: item.id,
    versionId: typeof item.version_id === 'string' ? item.version_id : '',
    status: typeof item.status === 'string' ? item.status : '',
    createdAt: typeof item.created_at === 'string' ? item.created_at : '',
    affectedCount: finiteNumber(item.affected_count),
    canRollback: item.can_rollback === true,
  };
}

export function readRevisions(value: unknown): EvaluationRevision[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const parsed = readRevision(item);
    return parsed ? [parsed] : [];
  });
}

function periodFromVersion(version: EvaluationVersion | undefined, history: EvaluationVersion[], scope: PeriodScope | null, revisions: EvaluationRevision[]): EvaluationPeriodData {
  return {
    versionId: version?.id || '',
    status: version?.status || '',
    lines: version?.lines.map((line) => ({ ...line })) || [],
    notes: version?.notes || '',
    history,
    scope,
    revisions,
    sourceVersionId: version?.source_version_id || '',
    sourceChecksum: version?.source_checksum || '',
    versionNumber: version?.version_number ?? null,
    checksum: version?.checksum || '',
  };
}

export function toPeriodData(data: unknown): EvaluationPeriodData {
  const body = data && typeof data === 'object' ? data as { versions?: unknown; scope?: unknown; revisions?: unknown } : {};
  const history = Array.isArray(body.versions) ? body.versions.flatMap((item) => {
    const parsed = readVersion(item);
    return parsed ? [parsed] : [];
  }) : [];
  return periodFromVersion(selectOpenVersion(history), history, readScope(body.scope), readRevisions(body.revisions));
}

export function applyVersion(current: EvaluationPeriodData, version: Partial<EvaluationVersion>): EvaluationPeriodData {
  const lines = Array.isArray(version.lines) ? version.lines.flatMap((line) => {
    const parsed = readLine(line);
    return parsed ? [parsed] : [];
  }) : current.lines;
  const nextVersion: EvaluationVersion = {
    id: version.id || current.versionId,
    status: version.status || current.status,
    lines,
    notes: version.notes ?? current.notes,
    month_name: version.month_name,
    version_number: version.version_number ?? current.versionNumber,
    checksum: version.checksum ?? current.checksum,
    source_version_id: version.source_version_id ?? current.sourceVersionId,
    source_checksum: version.source_checksum ?? current.sourceChecksum,
  };
  const history = nextVersion.id
    ? current.history.some((item) => item.id === nextVersion.id)
      ? current.history.map((item) => item.id === nextVersion.id ? { ...item, ...nextVersion, lines } : item)
      : [...current.history, nextVersion]
    : current.history;
  return periodFromVersion(nextVersion.id ? nextVersion : selectOpenVersion(history), history, current.scope, current.revisions);
}

export function lineSignature(lines: EvaluationLine[]): string {
  return JSON.stringify(lines.map((line) => ({
    kpi_key: line.kpi_key,
    weight: line.weight,
    direction: line.direction,
    target: line.target,
    target_mode: line.target_mode,
  })));
}

export function versionLabel(item: EvaluationVersion, monthName: string): string {
  const parts = [
    item.version_number != null ? `Version ${item.version_number}` : 'Version',
    item.month_name || monthName,
    item.status || 'unknown',
  ];
  if (item.checksum) parts.push(`checksum ${item.checksum}`);
  if (item.source_version_id) parts.push(`from ${item.source_version_id}`);
  if (item.source_checksum) parts.push(`source checksum ${item.source_checksum}`);
  return parts.join(' · ');
}

export function revisionLabel(item: EvaluationRevision): string {
  const parts = [`Revision ${item.id}`, item.status || 'status not provided'];
  if (item.versionId) parts.push(`version ${item.versionId}`);
  if (item.affectedCount != null) parts.push(`${item.affectedCount} records`);
  if (item.createdAt) parts.push(item.createdAt);
  return parts.join(' · ');
}

export function monthHasApprovedVersion(period: EvaluationPeriodData | undefined): boolean {
  return Boolean(period && (period.status === 'approved' || period.history.some((item) => item.status === 'approved')));
}

export { MONTHS };
