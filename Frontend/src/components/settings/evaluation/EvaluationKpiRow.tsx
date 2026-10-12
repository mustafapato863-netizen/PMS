import { PencilLine } from 'lucide-react';
import {
  UNSUPPORTED_FORMULA_NOTE,
  lineFormulaSupported,
  lockedDirectionLabel,
  type EvaluationLine,
} from '../evaluationSettings';
import {
  isExplicitPercentUnit,
  savedTargetSummary,
  savedWeightSummary,
  storedTargetToInput,
  storedWeightToInput,
} from '../evaluationInputUnits';
import { KPI_TARGET_HELP_ID, KPI_WEIGHT_HELP_ID, fieldKeyFor, isRowEdited, type RowDraft } from './evaluationKpiRows';

/**
 * The column tracks, shared by the header row and every KPI row so the values line up. Below lg the same grid holds
 * two columns, which makes each row a stacked card.
 */
export const KPI_COLUMNS = 'lg:grid-cols-[minmax(0,2fr)_minmax(0,1.1fr)_minmax(0,0.9fr)_minmax(0,1fr)_minmax(0,0.8fr)]';

const CONTROL = `h-[44px] w-full min-w-0 rounded-lg border border-[var(--border-light)] bg-transparent px-2 text-[14px] text-[var(--text-primary)] normal-case lg:h-[36px] disabled:cursor-not-allowed focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary,#00A3E0)]`;
const FIELD_CAPTION = 'mb-1 block text-[12px] font-bold text-[var(--text-muted)] lg:hidden';
const TRACK_BUTTON = '!min-h-[44px] w-fit rounded-lg border border-[var(--border-light)] px-3 text-[12px] font-semibold text-[var(--text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary,#00A3E0)] disabled:cursor-not-allowed disabled:opacity-50 lg:!min-h-[32px]';

export type ProblemMessage = { message: string };

export type EvaluationKpiRowProps = {
  line: EvaluationLine;
  /** The saved line for this KPI, or undefined when none is loaded. */
  saved: EvaluationLine | undefined;
  draft: RowDraft;
  busy: boolean;
  approved: boolean;
  directionOwned: boolean;
  targetProblem: ProblemMessage | undefined;
  weightProblem: ProblemMessage | undefined;
  onEditText: (key: string, field: 'targetText' | 'weightText', value: string) => void;
  onUpdateLine: (key: string, patch: Partial<EvaluationLine>) => void;
};

/**
 * One KPI: indicator, target, weight, direction and source. It is a named group, and every control is disabled under
 * the same condition the old fieldset used: a request is in flight, the month is approved, or the formula is unsupported.
 */
export function EvaluationKpiRow({
  line, saved, draft, busy, approved, directionOwned, targetProblem, weightProblem, onEditText, onUpdateLine,
}: EvaluationKpiRowProps) {
  const supported = lineFormulaSupported(line);
  const locked = busy || approved || !supported;
  const savedLine = saved ?? line;
  const label = line.label || line.kpi_key;
  const fieldKey = fieldKeyFor(line.kpi_key);
  const nameId = `evaluation-kpi-${fieldKey}-name`;
  const targetSavedId = `evaluation-kpi-${fieldKey}-target-saved`;
  const weightSavedId = `evaluation-kpi-${fieldKey}-weight-saved`;
  const targetValue = draft?.targetText !== undefined ? draft.targetText : storedTargetToInput(savedLine.target, savedLine.unit);
  const weightValue = draft?.weightText !== undefined ? draft.weightText : storedWeightToInput(savedLine.weight);
  const tracking = weightValue.trim() !== '' && Number(weightValue) === 0;
  const edited = isRowEdited(line, saved, draft);
  const unitSuffix = isExplicitPercentUnit(savedLine.unit)
    ? '%'
    : typeof savedLine.unit === 'string' && savedLine.unit.trim()
      ? savedLine.unit.trim()
      : 'as stored';

  return (
    <div
      role="group"
      aria-labelledby={nameId}
      data-edited={edited ? 'true' : undefined}
      className={`grid min-w-0 grid-cols-2 gap-3 rounded-2xl border border-[var(--border-light)] p-3 lg:items-center lg:gap-4 lg:rounded-none lg:border-x-0 lg:border-t-0 lg:px-3 lg:py-2 ${KPI_COLUMNS} ${locked ? 'opacity-60' : ''}`}
    >
      <div className="col-span-2 flex min-w-0 flex-col gap-1.5 lg:col-span-1">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
          <span id={nameId} className="text-[14px] font-bold text-[var(--text-primary)]">{label}</span>
          <span className="rounded-full bg-[var(--bg-sunken)] px-2 py-0.5 text-[12px] font-semibold text-[var(--text-secondary)]">{tracking ? 'Tracking only' : 'Included in score'}</span>
          {edited && <span className="inline-flex items-center gap-1 text-[12px] font-semibold text-blue-700 dark:text-blue-300"><PencilLine size={12} aria-hidden="true" />Edited</span>}
        </div>
        {tracking
          ? <span className="text-[12px] text-[var(--text-muted)]">Enter a weight above 0% to include in the score.</span>
          : <button type="button" disabled={locked} onClick={() => onEditText(line.kpi_key, 'weightText', '0')} className={TRACK_BUTTON}>Track {label} only</button>}
        {!supported && <p role="status" className="text-[12px] text-amber-800 dark:text-amber-300">{UNSUPPORTED_FORMULA_NOTE}</p>}
      </div>

      <div className="min-w-0">
        <span className={FIELD_CAPTION}>Target</span>
        <div className="flex min-w-0 items-center gap-2">
          <input
            aria-label={`${line.kpi_key} target`}
            aria-describedby={`${KPI_TARGET_HELP_ID} ${targetSavedId}`}
            aria-invalid={targetProblem ? true : undefined}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            spellCheck={false}
            value={targetValue}
            disabled={locked}
            onChange={(event) => onEditText(line.kpi_key, 'targetText', event.target.value)}
            className={CONTROL}
          />
          <span className="shrink-0 text-[12px] font-bold text-[var(--text-secondary)]">{unitSuffix}</span>
        </div>
        <span id={targetSavedId} className="mt-1 block text-[12px] text-[var(--text-muted)]">Saved target: {savedTargetSummary(savedLine)}.</span>
        {targetProblem && <span role="status" className="mt-1 block text-[12px] font-semibold text-amber-800 dark:text-amber-300">{targetProblem.message}</span>}
      </div>

      <div className="min-w-0">
        <span className={FIELD_CAPTION}>Weight</span>
        <div className="flex min-w-0 items-center gap-2">
          <input
            aria-label={`${line.kpi_key} weight`}
            aria-describedby={`${KPI_WEIGHT_HELP_ID} ${weightSavedId}`}
            aria-invalid={weightProblem ? true : undefined}
            type="text"
            inputMode="decimal"
            autoComplete="off"
            spellCheck={false}
            value={weightValue}
            disabled={locked}
            onChange={(event) => onEditText(line.kpi_key, 'weightText', event.target.value)}
            className={CONTROL}
          />
          <span className="shrink-0 text-[12px] font-bold text-[var(--text-secondary)]">%</span>
        </div>
        <span id={weightSavedId} className="mt-1 block text-[12px] text-[var(--text-muted)]">Saved weight: {savedWeightSummary(savedLine.weight)}.</span>
        {weightProblem && <span role="status" className="mt-1 block text-[12px] font-semibold text-amber-800 dark:text-amber-300">{weightProblem.message}</span>}
      </div>

      <div className="min-w-0">
        <span className={FIELD_CAPTION}>Direction</span>
        {supported && !directionOwned ? (
          <select aria-label={`${line.kpi_key} direction`} value={line.direction} disabled={locked} onChange={(event) => onUpdateLine(line.kpi_key, { direction: event.target.value })} className={CONTROL}>
            <option value="higher_better">Higher is better</option>
            <option value="lower_better">Lower is better</option>
          </select>
        ) : <input aria-label={`${line.kpi_key} direction`} value={directionOwned ? (line.row_selection === 'utz_or_abandon' ? 'Uploaded row' : lockedDirectionLabel(line.direction)) : line.direction} readOnly disabled={locked} className={CONTROL} />}
        {directionOwned && line.row_selection === 'utz_or_abandon' && <span className="mt-1 block text-[12px] text-[var(--text-muted)]">This indicator follows the uploaded row: UTZ when that cell is present, otherwise Abandon.</span>}
      </div>

      <div className="min-w-0">
        <span className={FIELD_CAPTION}>Source</span>
        {supported ? (
          <select aria-label={`${line.kpi_key} source`} value={line.target_mode} disabled={locked} onChange={(event) => onUpdateLine(line.kpi_key, { target_mode: event.target.value })} className={CONTROL}>
            <option value="workbook">Workbook</option>
            <option value="fixed">Fixed</option>
          </select>
        ) : <input aria-label={`${line.kpi_key} source`} value={line.target_mode} readOnly disabled={locked} className={CONTROL} />}
      </div>
    </div>
  );
}
