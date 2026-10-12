import { CircleCheck, TriangleAlert } from 'lucide-react';
import { AdminSection } from '../shell/AdminSection';
import { WEIGHT_FIELD_HELP, type NumericDrafts } from '../evaluationInputUnits';
import type { EvaluationLine } from '../evaluationSettings';
import { EvaluationKpiRow, KPI_COLUMNS } from './EvaluationKpiRow';
import { KPI_TARGET_HELP_ID, KPI_WEIGHT_HELP_ID, distinctTargetHelp } from './evaluationKpiRows';

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

/** The instructions, once, above the grid. Each input refers to them, so a row never repeats them on screen. */
function KpiHelp({ targets }: { targets: readonly string[] }) {
  return (
    <div className="rounded-xl bg-[var(--bg-sunken)] px-3 py-2 text-[12px] text-[var(--text-secondary)]">
      <p><span className="font-bold text-[var(--text-primary)]">Target:</span> <span id={KPI_TARGET_HELP_ID}>{targets.join(' ')}</span></p>
      <p><span className="font-bold text-[var(--text-primary)]">Weight:</span> <span id={KPI_WEIGHT_HELP_ID}>{WEIGHT_FIELD_HELP}</span></p>
    </div>
  );
}

/** Three placeholder rows while the month loads. They are decorative, and the loading text is announced instead. */
function KpiSkeleton() {
  return (
    <div aria-hidden="true" className="space-y-2">
      {[0, 1, 2].map((item) => <div key={item} className="h-16 animate-pulse rounded-xl bg-[var(--bg-sunken)] motion-reduce:animate-none" />)}
    </div>
  );
}

/** The indicator editor: the total weight summary, the instructions, and one row per KPI. */
export function EvaluationKpiLines(props: EvaluationKpiLinesProps) {
  const {
    lines, referenceLines, textDrafts, draftProblems, totalWeight, inputBlocked, weightTotalInvalid,
    periodLoading, blocked, busy, approved, directionOwned, onEditText, onUpdateLine,
  } = props;
  if (blocked && !periodLoading) return null;
  const ready = !periodLoading && !blocked;
  const weightReady = !(weightTotalInvalid || inputBlocked);
  const targetHelp = distinctTargetHelp(lines.map((line) => (referenceLines.find((item) => item.kpi_key === line.kpi_key) ?? line).unit));
  return (
    <AdminSection title="Indicators">
      {ready && lines.length > 0 && <div role="status" className={`flex flex-wrap items-center justify-between gap-2 rounded-xl border px-3 py-2 text-[12px] ${weightReady ? 'border-emerald-500/20 bg-emerald-500/5' : 'border-amber-500/30 bg-amber-500/10'}`}>
        <div className="flex min-w-0 items-center gap-2">
          {weightReady
            ? <CircleCheck size={16} aria-hidden="true" className="shrink-0 text-emerald-600 dark:text-emerald-400" />
            : <TriangleAlert size={16} aria-hidden="true" className="shrink-0 text-amber-700 dark:text-amber-300" />}
          <p className="font-bold text-[var(--text-primary)]">{inputBlocked || !Number.isFinite(totalWeight) ? 'Total weight: check the weight fields' : `Total weight: ${Number((totalWeight * 100).toFixed(2))}%`}</p>
          <span className={`rounded-full border px-2 py-0.5 font-bold ${weightReady ? 'border-emerald-500/30 text-emerald-700 dark:text-emerald-300' : 'border-amber-500/40 text-amber-800 dark:text-amber-300'}`}>{weightReady ? 'Valid' : 'Needs attention'}</span>
        </div>
        <p className={weightReady ? 'text-[var(--text-secondary)]' : 'font-semibold text-amber-800 dark:text-amber-300'}>{weightReady ? 'Weights are ready to save. Tracking-only indicators do not contribute to the score.' : 'Set the scored indicators to a total of 100% before saving. Other weights are not changed automatically.'}</p>
      </div>}
      {periodLoading && <>
        <p className="text-[12px] text-[var(--text-muted)]">Loading this month…</p>
        <KpiSkeleton />
      </>}
      {ready && lines.length === 0 && <p className="text-[12px] text-[var(--text-secondary)]">This month has no indicators to edit.</p>}
      {ready && lines.length > 0 && <>
        <KpiHelp targets={targetHelp} />
        <div className="min-w-0">
          <div className={`hidden gap-4 border-b border-[var(--border-light)] px-3 py-2 text-[12px] font-bold text-[var(--text-muted)] lg:grid ${KPI_COLUMNS}`}>
            <span>Indicator</span>
            <span>Target</span>
            <span>Weight</span>
            <span>Direction</span>
            <span>Source</span>
          </div>
          <div className="space-y-3 lg:space-y-0">
            {lines.map((line) => {
              const targetProblem = draftProblems.find((item) => item.kpiKey === line.kpi_key && item.field === 'target');
              const weightProblem = draftProblems.find((item) => item.kpiKey === line.kpi_key && item.field === 'weight');
              return (
                <EvaluationKpiRow
                  key={line.kpi_key}
                  line={line}
                  saved={referenceLines.find((item) => item.kpi_key === line.kpi_key)}
                  draft={textDrafts[line.kpi_key]}
                  busy={busy}
                  approved={approved}
                  directionOwned={directionOwned}
                  targetProblem={targetProblem}
                  weightProblem={weightProblem}
                  onEditText={onEditText}
                  onUpdateLine={onUpdateLine}
                />
              );
            })}
          </div>
        </div>
      </>}
    </AdminSection>
  );
}
