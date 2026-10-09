const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const PERIOD_KEY = /^(\d{4})-(0[1-9]|1[0-2])$/;

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
};

export type EvaluationPeriodData = {
  versionId: string;
  status: string;
  lines: EvaluationLine[];
  notes: string;
  history: EvaluationVersion[];
  storedActuals: Record<string, number>;
};

export const SAMPLE_PREVIEW_LIMIT = 'Preview uses the saved version and the first stored record only. It is not a scope-wide impact. Full-scope actual rows and original workbook targets are not in the current period response.';

export const SAMPLE_PREVIEW_UNAVAILABLE = 'No stored actuals are available for this month, so preview cannot run. Full-scope actual rows are not in the current period response.';

export const UNSAVED_PREVIEW_NOTE = 'Save the draft before preview or approval. Unsaved edits are not previewed.';

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

/**
 * Period payload stores numeric actuals for the first saved record only.
 * Objects are ignored so a future row shape is not treated as evidence.
 */
export function readStoredActuals(value: unknown): Record<string, number> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {};
  const actuals: Record<string, number> = {};
  Object.entries(value).forEach(([key, raw]) => {
    if (typeof raw === 'number' && Number.isFinite(raw)) actuals[key] = raw;
  });
  return actuals;
}

export function emptyPeriod(): EvaluationPeriodData {
  return { versionId: '', status: '', lines: [], notes: '', history: [], storedActuals: {} };
}

export function toPeriodData(data: unknown): EvaluationPeriodData {
  const body = data && typeof data === 'object' ? data as { versions?: unknown; stored_actuals?: unknown } : {};
  const history = Array.isArray(body.versions) ? body.versions.filter((item): item is EvaluationVersion => Boolean(item) && typeof item === 'object' && typeof (item as EvaluationVersion).id === 'string') : [];
  const open = history.find((item) => item.status === 'draft') || history.find((item) => item.status === 'approved');
  return {
    versionId: open?.id || '',
    status: open?.status || '',
    lines: Array.isArray(open?.lines) ? open.lines.map((line) => ({ ...line })) : [],
    notes: open?.notes || '',
    history,
    storedActuals: readStoredActuals(body.stored_actuals),
  };
}

export function applyVersion(current: EvaluationPeriodData, version: Partial<EvaluationVersion>): EvaluationPeriodData {
  const lines = Array.isArray(version.lines) ? version.lines.map((line) => ({ ...line })) : current.lines;
  const history = version.id
    ? current.history.some((item) => item.id === version.id)
      ? current.history.map((item) => item.id === version.id ? { ...item, ...version, lines } : item)
      : [...current.history, { id: version.id, status: version.status || 'draft', lines, notes: version.notes, month_name: version.month_name }]
    : current.history;
  return {
    ...current,
    versionId: version.id || current.versionId,
    status: version.status || current.status,
    lines,
    notes: version.notes ?? current.notes,
    history,
  };
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

/**
 * Sample actuals only. The edited or saved target is not sent as workbook_target.
 * Original workbook targets are absent from the current period contract.
 */
export function previewSampleRows(lines: EvaluationLine[], actuals: Record<string, number>): Array<{ kpi_key: string; actual: number }> {
  return lines.flatMap((line) => (
    Object.prototype.hasOwnProperty.call(actuals, line.kpi_key)
      ? [{ kpi_key: line.kpi_key, actual: actuals[line.kpi_key] }]
      : []
  ));
}

export function formatSamplePreview(data: { score?: unknown; rows?: unknown }): string {
  const rows = Array.isArray(data.rows) ? data.rows : [];
  const first = rows.find((row): row is { kpi_key?: unknown; achievement?: unknown } => Boolean(row) && typeof row === 'object');
  const achievement = Number(first?.achievement);
  const score = Number(data.score);
  if (!first || typeof first.kpi_key !== 'string' || !Number.isFinite(achievement) || !Number.isFinite(score)) {
    return 'Preview returned no scored sample. This is not a scope-wide result. Full-scope actual rows are not available from the current period response.';
  }
  return `Sample preview for the first stored record, not a scope-wide impact: ${first.kpi_key} achievement ${(achievement * 100).toFixed(2)}%, sample score ${score}. Full-scope actual rows are not included in the current period response.`;
}

export { MONTHS };
