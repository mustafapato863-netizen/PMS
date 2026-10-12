import { targetDraftUnchanged, targetFieldHelp, weightDraftUnchanged } from '../evaluationInputUnits';
import type { EvaluationLine } from '../evaluationSettings';

/** The id of the one target help block above the grid. Every target input refers to it. */
export const KPI_TARGET_HELP_ID = 'evaluation-kpi-target-help';

/** The id of the one weight help block above the grid. Every weight input refers to it. */
export const KPI_WEIGHT_HELP_ID = 'evaluation-kpi-weight-help';

export type RowDraft = { targetText?: string; weightText?: string } | undefined;

/** The HTML id fragment for one KPI. Keys can contain characters that are not valid in an id. */
export function fieldKeyFor(kpiKey: string): string {
  return kpiKey.replace(/[^A-Za-z0-9_-]/g, '-');
}

/**
 * True when a row's draft differs from its saved line: target text, weight text, direction or source.
 * Pure: it reads props the grid already has and changes no gate. A row with no saved line cannot differ.
 */
export function isRowEdited(line: EvaluationLine, saved: EvaluationLine | undefined, draft: RowDraft): boolean {
  if (!saved) return false;
  if (draft?.targetText !== undefined && !targetDraftUnchanged(saved, draft.targetText)) return true;
  if (draft?.weightText !== undefined && !weightDraftUnchanged(saved.weight, draft.weightText)) return true;
  return line.direction !== saved.direction || line.target_mode !== saved.target_mode;
}

/** Each distinct target instruction once, in the order the rows first use it. Rows with the same unit share one sentence. */
export function distinctTargetHelp(units: readonly unknown[]): string[] {
  return [...new Set(units.map((unit) => targetFieldHelp(unit)))];
}
