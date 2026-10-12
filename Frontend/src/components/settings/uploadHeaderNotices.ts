export const UNMAPPED_COLUMNS_TITLE = 'Columns not mapped to scoring';
export const UNMAPPED_COLUMNS_DETAIL = 'These columns do not change your scoring rules. Review their names in Excel.';
export const OPTIONAL_COLUMNS_TITLE = 'Optional columns detected';
export const OPTIONAL_COLUMNS_DETAIL = 'These columns are outside the ordinary template. Their names are not added as new scoring rules.';
export const AMBIGUOUS_COLUMNS_TITLE = 'Conflicting target columns';
export const AMBIGUOUS_COLUMNS_DETAIL = 'These column names disagree. Neither value was used as the quality target. Review their names in Excel.';

const NOTICE_LIMIT = 12;
const HEADER_LIMIT = 25;

export type ColumnWarningCode = 'unmapped_columns' | 'optional_columns' | 'ambiguous_alias';

export interface ColumnWarning {
  sheet: string;
  code: ColumnWarningCode;
  headers: string[];
  truncated: boolean;
}

const CODES = new Set<ColumnWarningCode>(['unmapped_columns', 'optional_columns', 'ambiguous_alias']);

export function readColumnWarnings(value: unknown): ColumnWarning[] {
  if (!Array.isArray(value)) return [];
  const notices: ColumnWarning[] = [];
  for (const item of value) {
    if (notices.length >= NOTICE_LIMIT) break;
    if (!item || typeof item !== 'object') continue;
    const record = item as Record<string, unknown>;
    const code = record.code;
    if (typeof code !== 'string' || !CODES.has(code as ColumnWarningCode)) continue;
    const sheet = typeof record.sheet === 'string' && record.sheet.trim() ? record.sheet.slice(0, 120) : 'Sheet';
    const namedHeaders = Array.isArray(record.headers)
      ? record.headers.filter((header): header is string => typeof header === 'string' && header.trim() !== '')
      : [];
    const headers = namedHeaders.slice(0, HEADER_LIMIT);
    if (!headers.length) continue;
    notices.push({
      sheet,
      code: code as ColumnWarningCode,
      headers,
      truncated: record.truncated === true || namedHeaders.length > headers.length,
    });
  }
  return notices;
}
