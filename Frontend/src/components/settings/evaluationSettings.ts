const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const PERIOD_KEY = /^(\d{4})-(0[1-9]|1[0-2])$/;
const SUPPORTED_DIRECTIONS = new Set(['higher_better', 'lower_better']);
const SUPPORTED_TARGET_MODES = new Set(['workbook', 'fixed']);

export type EvaluationContract = 'operational_upload' | 'reference_workbook';

export type EvaluationLine = {
  kpi_key: string;
  label?: string;
  weight: number;
  direction: string;
  target: number | null;
  target_mode: 'workbook' | 'fixed' | string;
  unit?: string;
  row_selection?: string;
};

export type RevisionChoice = {
  available: boolean;
  contract: string;
  code: string | null;
  message: string;
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
  contract?: EvaluationContract | null;
  revisionChoice?: RevisionChoice | null;
  /** Who and when. Optional: an older server omits them, and a missing value is left out of the history. */
  created_at?: string | null;
  approved_at?: string | null;
  created_by?: string | null;
  approved_by?: string | null;
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
  contract: EvaluationContract | null;
  revisionChoice: RevisionChoice | null;
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
    contract: null,
    revisionChoice: null,
  };
}

export function contractLabel(contract: string | null | undefined): string {
  if (contract === 'operational_upload') return 'Original upload';
  if (contract === 'reference_workbook') return 'Reference workbook';
  return '';
}

export function lockedDirectionLabel(direction: string): string {
  if (direction === 'higher_better') return 'Higher is better';
  if (direction === 'lower_better') return 'Lower is better';
  return direction;
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
    row_selection: typeof line.row_selection === 'string' && line.row_selection ? line.row_selection : undefined,
  };
}

function readContract(value: unknown): EvaluationContract | null {
  return value === 'operational_upload' || value === 'reference_workbook' ? value : null;
}

function readRevisionChoice(value: unknown): RevisionChoice | null {
  if (!value || typeof value !== 'object') return null;
  const item = value as { available?: unknown; contract?: unknown; code?: unknown; message?: unknown };
  if (typeof item.available !== 'boolean' || typeof item.message !== 'string' || !item.message.trim()) return null;
  return {
    available: item.available,
    contract: typeof item.contract === 'string' ? item.contract : '',
    code: typeof item.code === 'string' && item.code ? item.code : null,
    message: item.message,
  };
}

function readVersion(value: unknown): EvaluationVersion | null {
  if (!value || typeof value !== 'object') return null;
  const item = value as EvaluationVersion & { revision_choice?: unknown };
  if (typeof item.id !== 'string' || !item.id) return null;
  const parsed: EvaluationVersion = {
    id: item.id,
    status: typeof item.status === 'string' ? item.status : '',
    lines: Array.isArray(item.lines) ? item.lines.flatMap((line) => {
      const parsedLine = readLine(line);
      return parsedLine ? [parsedLine] : [];
    }) : [],
    notes: typeof item.notes === 'string' ? item.notes : null,
    month_name: typeof item.month_name === 'string' ? item.month_name : undefined,
    version_number: finiteNumber(item.version_number),
    checksum: typeof item.checksum === 'string' ? item.checksum : null,
    source_version_id: typeof item.source_version_id === 'string' ? item.source_version_id : null,
    source_checksum: typeof item.source_checksum === 'string' ? item.source_checksum : null,
  };
  if ('contract' in item) parsed.contract = readContract(item.contract);
  if ('revision_choice' in item || 'revisionChoice' in item) {
    parsed.revisionChoice = readRevisionChoice(item.revision_choice ?? item.revisionChoice);
  }
  const who = item as { created_at?: unknown; approved_at?: unknown; created_by?: unknown; approved_by?: unknown };
  if ('created_at' in who) parsed.created_at = readText(who.created_at);
  if ('approved_at' in who) parsed.approved_at = readText(who.approved_at);
  if ('created_by' in who) parsed.created_by = readText(who.created_by);
  if ('approved_by' in who) parsed.approved_by = readText(who.approved_by);
  return parsed;
}

function readText(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

/** Keep contract fields only when this payload actually carried them. */
export function versionFromPayload(data: unknown): Partial<EvaluationVersion> {
  const parsed = readVersion(data);
  if (!parsed || !data || typeof data !== 'object') return {};
  const raw = data as { contract?: unknown; revision_choice?: unknown; revisionChoice?: unknown };
  if (!('contract' in raw)) delete parsed.contract;
  if (!('revision_choice' in raw) && !('revisionChoice' in raw)) delete parsed.revisionChoice;
  return parsed;
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
    contract: version?.contract ?? null,
    revisionChoice: version?.revisionChoice ?? null,
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
    contract: 'contract' in version ? readContract(version.contract) : current.contract,
    revisionChoice: 'revisionChoice' in version ? version.revisionChoice ?? null : current.revisionChoice,
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
