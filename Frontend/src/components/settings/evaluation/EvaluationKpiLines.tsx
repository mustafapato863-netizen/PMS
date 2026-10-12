import {
  UNSUPPORTED_FORMULA_NOTE,
  lineFormulaSupported,
  lockedDirectionLabel,
  type EvaluationLine,
} from '../evaluationSettings';
import {
  WEIGHT_FIELD_HELP,
  WEIGHT_FIELD_LABEL,
  isExplicitPercentUnit,
  savedTargetSummary,
  savedWeightSummary,
  storedTargetToInput,
  storedWeightToInput,
  targetFieldHelp,
  targetFieldLabel,
  type NumericDrafts,
} from '../evaluationInputUnits';

export type DraftProblem = { kpiKey: string; field: string; message: string };

export type EvaluationKpiLinesProps = {
  lines: EvaluationLine[];
  referenceLines: EvaluationLine[];
  textDrafts: NumericDrafts;
  draftProblems: DraftProblem[];
  totalWeight: number;
  inputBlocked: boolean;
  weightTotalInvalid: boolean;
  periodLoading: boolean;
  blocked: boolean;
  busy: boolean;
  approved: boolean;
  directionOwned: boolean;
  onEditText: (key: string, field: 'targetText' | 'weightText', value: string) => void;
  onUpdateLine: (key: string, patch: Partial<EvaluationLine>) => void;
};

const FIELD_LABEL = 'text-xs font-bold text-[var(--text-muted)]';
const CONTROL = 'mt-1 w-full rounded-lg border border-[var(--border-light)] bg-transparent px-2 py-2 text-sm';

/** The total weight check and one fieldset per KPI line: target, weight, direction and source. */
export function EvaluationKpiLines(props: EvaluationKpiLinesProps) {
  const {
    lines, referenceLines, textDrafts, draftProblems, totalWeight, inputBlocked, weightTotalInvalid,
    periodLoading, blocked, busy, approved, directionOwned, onEditText, onUpdateLine,
  } = props;
  return (
    <div className="min-w-0 space-y-3">
      {!periodLoading && !blocked && lines.length > 0 && <div role="status" className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs text-[var(--text-secondary)]">
        <p className="font-bold">{inputBlocked || !Number.isFinite(totalWeight) ? 'Total weight: check the weight fields' : `Total weight: ${Number((totalWeight * 100).toFixed(2))}%`}</p>
        <p>{weightTotalInvalid || inputBlocked ? 'Set the scored indicators to a total of 100% before saving. Other weights are not changed automatically.' : 'Weights are ready to save. Tracking-only indicators do not contribute to the score.'}</p>
      </div>}
      {periodLoading && <p className="text-xs text-[var(--text-muted)]">Loading this month…</p>}
      {!periodLoading && !blocked && lines.map((line) => {
        const supported = lineFormulaSupported(line);
        const locked = busy || approved || !supported;
        const savedLine = referenceLines.find((item) => item.kpi_key === line.kpi_key) ?? line;
        const entry = textDrafts[line.kpi_key];
        const targetValue = entry?.targetText !== undefined ? entry.targetText : storedTargetToInput(savedLine.target, savedLine.unit);
        const weightValue = entry?.weightText !== undefined ? entry.weightText : storedWeightToInput(savedLine.weight);
        const targetProblem = draftProblems.find((item) => item.kpiKey === line.kpi_key && item.field === 'target');
        const weightProblem = draftProblems.find((item) => item.kpiKey === line.kpi_key && item.field === 'weight');
        const unitSuffix = isExplicitPercentUnit(savedLine.unit)
          ? '%'
          : typeof savedLine.unit === 'string' && savedLine.unit.trim()
            ? savedLine.unit.trim()
            : 'as stored';
        const fieldKey = line.kpi_key.replace(/[^A-Za-z0-9_-]/g, '-');
        return (
          <fieldset key={line.kpi_key} disabled={locked} className="min-w-0 rounded-2xl border border-[var(--border-light)] p-3 disabled:opacity-60">
            <legend className="px-1 text-xs font-black text-[var(--text-primary)]">{line.label || line.kpi_key}</legend>
            <div className="mb-3 flex flex-wrap items-center justify-between gap-2 text-xs">
              <span className="rounded-full bg-[var(--bg-sunken)] px-2 py-1 font-semibold">{weightValue.trim() !== '' && Number(weightValue) === 0 ? 'Tracking only' : 'Included in score'}</span>
              {weightValue.trim() !== '' && Number(weightValue) === 0
                ? <span className="text-[var(--text-muted)]">Enter a weight above 0% to include in the score.</span>
                : <button type="button" onClick={() => onEditText(line.kpi_key, 'weightText', '0')} className="rounded-lg border border-[var(--border-light)] px-3 py-2 font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50">Track {line.label || line.kpi_key} only</button>}
            </div>
            {!supported && <p role="status" className="mb-2 text-xs text-amber-800">{UNSUPPORTED_FORMULA_NOTE}</p>}
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <label className={FIELD_LABEL}>
                <span className="uppercase tracking-wide">{targetFieldLabel(savedLine.unit)}</span>
                <span className="mt-1 flex items-center gap-2">
                  <input aria-label={`${line.kpi_key} target`} aria-describedby={`${fieldKey}-target-help`} aria-invalid={targetProblem ? true : undefined} type="text" inputMode="decimal" autoComplete="off" spellCheck={false} value={targetValue} onChange={(event) => onEditText(line.kpi_key, 'targetText', event.target.value)} className="w-full rounded-lg border border-[var(--border-light)] bg-transparent px-2 py-2 text-sm normal-case" />
                  <span className="shrink-0 text-xs font-bold normal-case">{unitSuffix}</span>
                </span>
                <span id={`${fieldKey}-target-help`} className="mt-1 block font-normal normal-case tracking-normal">{targetFieldHelp(savedLine.unit)} Saved target: {savedTargetSummary(savedLine)}.</span>
                {targetProblem && <span role="status" className="mt-1 block font-semibold normal-case tracking-normal text-amber-800">{targetProblem.message}</span>}
              </label>
              <label className={FIELD_LABEL}>
                <span className="uppercase tracking-wide">{WEIGHT_FIELD_LABEL}</span>
                <span className="mt-1 flex items-center gap-2">
                  <input aria-label={`${line.kpi_key} weight`} aria-describedby={`${fieldKey}-weight-help`} aria-invalid={weightProblem ? true : undefined} type="text" inputMode="decimal" autoComplete="off" spellCheck={false} value={weightValue} onChange={(event) => onEditText(line.kpi_key, 'weightText', event.target.value)} className="w-full rounded-lg border border-[var(--border-light)] bg-transparent px-2 py-2 text-sm normal-case" />
                  <span className="shrink-0 text-xs font-bold normal-case">%</span>
                </span>
                <span id={`${fieldKey}-weight-help`} className="mt-1 block font-normal normal-case tracking-normal">{WEIGHT_FIELD_HELP} Saved weight: {savedWeightSummary(savedLine.weight)}.</span>
                {weightProblem && <span role="status" className="mt-1 block font-semibold normal-case tracking-normal text-amber-800">{weightProblem.message}</span>}
              </label>
              <label className="text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]">Direction
                {supported && !directionOwned ? (
                  <select aria-label={`${line.kpi_key} direction`} value={line.direction} onChange={(event) => onUpdateLine(line.kpi_key, { direction: event.target.value })} className={CONTROL}>
                    <option value="higher_better">Higher is better</option>
                    <option value="lower_better">Lower is better</option>
                  </select>
                ) : <input aria-label={`${line.kpi_key} direction`} value={directionOwned ? (line.row_selection === 'utz_or_abandon' ? 'Uploaded row' : lockedDirectionLabel(line.direction)) : line.direction} readOnly className={CONTROL} />}
                {directionOwned && line.row_selection === 'utz_or_abandon' && <span className="mt-1 block font-normal normal-case tracking-normal text-[var(--text-muted)]">This indicator follows the uploaded row: UTZ when that cell is present, otherwise Abandon.</span>}
              </label>
              <label className="text-xs font-bold uppercase tracking-wide text-[var(--text-muted)]">Source
                {supported ? (
                  <select aria-label={`${line.kpi_key} source`} value={line.target_mode} onChange={(event) => onUpdateLine(line.kpi_key, { target_mode: event.target.value })} className={CONTROL}>
                    <option value="workbook">Workbook</option>
                    <option value="fixed">Fixed</option>
                  </select>
                ) : <input aria-label={`${line.kpi_key} source`} value={line.target_mode} readOnly className={CONTROL} />}
              </label>
            </div>
          </fieldset>
        );
      })}
    </div>
  );
}
