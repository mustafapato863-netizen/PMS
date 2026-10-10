/**
 * Rules-editor entry scale.
 * Percentage targets convert only for an explicit percent unit.
 * Every weight is entered as a percent and stored as a fraction.
 * Other target units, including a missing unit, stay on the stored scale.
 */
import type { EvaluationLine } from './evaluationSettings';

const PERCENT_UNITS = new Set(['%', 'percent', 'percentage']);
const COMPLETE_NUMBER = /^[+-]?(?:\d+(?:\.\d+)?|\.\d+)$/;

export type DraftField = 'target' | 'weight';
export type DraftProblem = 'blank' | 'invalid';

export type NumericDrafts = Record<string, { targetText?: string; weightText?: string }>;

export type InputCommitError = {
  kpiKey: string;
  field: DraftField;
  reason: DraftProblem;
  message: string;
};

export function isExplicitPercentUnit(unit: unknown): boolean {
  return typeof unit === 'string' && PERCENT_UNITS.has(unit.trim().toLowerCase());
}

export function targetFieldLabel(unit: unknown): string {
  if (isExplicitPercentUnit(unit)) return 'Target (%)';
  if (typeof unit === 'string' && unit.trim()) return `Target (${unit.trim()})`;
  return 'Target (no unit)';
}

export function targetFieldHelp(unit: unknown): string {
  if (isExplicitPercentUnit(unit)) return 'Enter a percentage. 65 is stored as 0.65.';
  if (typeof unit === 'string' && unit.trim()) return `Enter ${unit.trim()}. The value is stored as entered.`;
  return 'No unit was provided. The value is stored as entered.';
}

export const WEIGHT_FIELD_LABEL = 'Weight (%)';

export const WEIGHT_FIELD_HELP = 'Enter a percentage of this scorecard. 60 is stored as 0.6. Zero remains a diagnostic weight.';

function normalizeDecimalText(text: string): string {
  const negative = text.startsWith('-');
  const unsigned = negative ? text.slice(1) : text;
  const [whole, frac] = unsigned.split('.');
  const trimmedWhole = whole.replace(/^0+(?=\d)/, '') || '0';
  const trimmedFrac = frac?.replace(/0+$/, '');
  const body = trimmedFrac ? `${trimmedWhole}.${trimmedFrac}` : trimmedWhole;
  if (negative && body !== '0') return `-${body}`;
  return body;
}

/** Move the decimal point without using binary multiply/divide on ordinary decimals. */
export function shiftDecimal(value: number, places: number): string {
  if (!Number.isFinite(value) || Object.is(value, -0)) return Object.is(value, -0) || value === 0 ? '0' : '';
  const text = value.toString();
  if (!/^-?\d+(\.\d+)?$/.test(text)) {
    const scaled = places >= 0 ? value * 10 ** places : value / 10 ** -places;
    if (!Number.isFinite(scaled)) return '';
    return Object.is(scaled, -0) ? '0' : scaled.toString();
  }
  const negative = text.startsWith('-');
  const unsigned = negative ? text.slice(1) : text;
  const [whole, frac = ''] = unsigned.split('.');
  const digits = `${whole}${frac}`;
  const wholeLength = whole.length + places;
  let combined: string;
  if (wholeLength >= digits.length) combined = digits + '0'.repeat(wholeLength - digits.length);
  else if (wholeLength > 0) combined = `${digits.slice(0, wholeLength)}.${digits.slice(wholeLength)}`;
  else combined = `0.${'0'.repeat(-wholeLength)}${digits}`;
  return normalizeDecimalText(negative ? `-${combined}` : combined);
}

export function parseCompleteNumber(text: string): { ok: true; value: number } | { ok: false; reason: DraftProblem } {
  const trimmed = text.trim();
  if (!trimmed) return { ok: false, reason: 'blank' };
  if (!COMPLETE_NUMBER.test(trimmed)) return { ok: false, reason: 'invalid' };
  const value = Number(trimmed);
  if (!Number.isFinite(value)) return { ok: false, reason: 'invalid' };
  return { ok: true, value };
}

export function storedTargetToInput(value: number | null, unit: unknown): string {
  if (value == null || !Number.isFinite(value)) return '';
  return isExplicitPercentUnit(unit) ? shiftDecimal(value, 2) : shiftDecimal(value, 0);
}

export function storedWeightToInput(value: number): string {
  if (!Number.isFinite(value)) return '';
  return shiftDecimal(value, 2);
}

function storedTargetNumber(text: string, unit: unknown): number | null {
  const parsed = parseCompleteNumber(text);
  if (!parsed.ok) return null;
  const shifted = isExplicitPercentUnit(unit) ? shiftDecimal(parsed.value, -2) : shiftDecimal(parsed.value, 0);
  const value = Number(shifted);
  return Number.isFinite(value) ? value : null;
}

function storedWeightNumber(text: string): number | null {
  const parsed = parseCompleteNumber(text);
  if (!parsed.ok) return null;
  const value = Number(shiftDecimal(parsed.value, -2));
  return Number.isFinite(value) ? value : null;
}

export function targetDraftUnchanged(line: Pick<EvaluationLine, 'target' | 'unit'>, text: string): boolean {
  if (line.target == null || !Number.isFinite(line.target)) return text.trim() === '';
  if (text.trim() === storedTargetToInput(line.target, line.unit)) return true;
  const next = storedTargetNumber(text, line.unit);
  return next != null && Object.is(next, line.target);
}

export function weightDraftUnchanged(weight: number, text: string): boolean {
  if (!Number.isFinite(weight)) return text.trim() === '';
  if (text.trim() === storedWeightToInput(weight)) return true;
  const next = storedWeightNumber(text);
  return next != null && Object.is(next, weight);
}

export function savedTargetSummary(line: Pick<EvaluationLine, 'target' | 'unit'>): string {
  if (line.target == null || !Number.isFinite(line.target)) return 'empty';
  if (isExplicitPercentUnit(line.unit)) return `${storedTargetToInput(line.target, line.unit)}%`;
  if (typeof line.unit === 'string' && line.unit.trim()) return `${storedTargetToInput(line.target, line.unit)} ${line.unit.trim()}`;
  return `${storedTargetToInput(line.target, line.unit)} (stored value, unit not provided)`;
}

export function savedWeightSummary(weight: number): string {
  if (!Number.isFinite(weight)) return 'the previous stored value';
  return `${storedWeightToInput(weight)}%`;
}

function problemMessage(field: DraftField, reason: DraftProblem, saved: string): string {
  const problem = reason === 'blank' ? 'This entry is blank' : 'This entry is not a finite number';
  return `${problem}. Saved ${field} remains ${saved}.`;
}

export function formatIdentifiedTarget(value: number | null, unit: unknown): string {
  if (value == null || !Number.isFinite(value)) return '—';
  if (isExplicitPercentUnit(unit)) return `${storedTargetToInput(value, unit)}%`;
  if (typeof unit === 'string' && unit.trim()) return `${storedTargetToInput(value, unit)} ${unit.trim()}`;
  return `${storedTargetToInput(value, unit)} (stored value, unit not provided)`;
}

export function inputToStoredTarget(text: string, unit: unknown): { ok: true; value: number } | { ok: false; reason: DraftProblem } {
  const parsed = parseCompleteNumber(text);
  if (!parsed.ok) return parsed;
  const value = storedTargetNumber(text, unit);
  if (value == null) return { ok: false, reason: 'invalid' };
  return { ok: true, value };
}

export function inputToStoredWeight(text: string): { ok: true; value: number } | { ok: false; reason: DraftProblem } {
  const parsed = parseCompleteNumber(text);
  if (!parsed.ok) return parsed;
  const value = storedWeightNumber(text);
  if (value == null) return { ok: false, reason: 'invalid' };
  return { ok: true, value };
}

export function numericDraftsDirty(lines: readonly EvaluationLine[], drafts: NumericDrafts): boolean {
  return lines.some((line) => {
    const draft = drafts[line.kpi_key];
    if (!draft) return false;
    const targetDirty = draft.targetText !== undefined && !targetDraftUnchanged(line, draft.targetText);
    const weightDirty = draft.weightText !== undefined && !weightDraftUnchanged(line.weight, draft.weightText);
    return targetDirty || weightDirty;
  });
}

export function commitLineInputs(
  lines: readonly EvaluationLine[],
  drafts: NumericDrafts,
): { ok: true; lines: EvaluationLine[] } | { ok: false; errors: InputCommitError[] } {
  const errors: InputCommitError[] = [];
  const next = lines.map((line) => {
    const draft = drafts[line.kpi_key];
    if (!draft) return line;
    let target = line.target;
    let weight = line.weight;
    let changed = false;
    if (draft.targetText !== undefined && !targetDraftUnchanged(line, draft.targetText)) {
      const parsed = parseCompleteNumber(draft.targetText);
      const converted = parsed.ok ? storedTargetNumber(draft.targetText, line.unit) : null;
      if (!parsed.ok || converted == null) {
        errors.push({
          kpiKey: line.kpi_key,
          field: 'target',
          reason: parsed.ok ? 'invalid' : parsed.reason,
          message: `${line.label || line.kpi_key} target: ${problemMessage('target', parsed.ok ? 'invalid' : parsed.reason, savedTargetSummary(line))}`,
        });
      } else {
        target = converted;
        changed = true;
      }
    }
    if (draft.weightText !== undefined && !weightDraftUnchanged(line.weight, draft.weightText)) {
      const parsed = parseCompleteNumber(draft.weightText);
      const converted = parsed.ok ? storedWeightNumber(draft.weightText) : null;
      if (!parsed.ok || converted == null) {
        errors.push({
          kpiKey: line.kpi_key,
          field: 'weight',
          reason: parsed.ok ? 'invalid' : parsed.reason,
          message: `${line.label || line.kpi_key} weight: ${problemMessage('weight', parsed.ok ? 'invalid' : parsed.reason, savedWeightSummary(line.weight))}`,
        });
      } else {
        weight = converted;
        changed = true;
      }
    }
    if (!changed) return line;
    return { ...line, target, weight };
  });
  if (errors.length > 0) return { ok: false, errors };
  return { ok: true, lines: next };
}
