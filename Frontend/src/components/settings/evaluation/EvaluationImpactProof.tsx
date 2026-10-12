import { formatIdentifiedTarget } from '../evaluationInputUnits';
import type { EvaluationLine } from '../evaluationSettings';
import { FIXED_MISMATCH_NOTE, displayNumber, formatImpactSummary, formatKpiLine, type ImpactProof } from '../monthlyCorrection';

type ImpactComparison = NonNullable<ImpactProof['comparisons']>[number];

export type EvaluationImpactProofProps = {
  proof: ImpactProof;
  lines: readonly EvaluationLine[];
  comparisons: readonly ImpactComparison[];
  comparisonPage: { rows: readonly ImpactComparison[]; page: number; pages: number };
  onPageChange: (page: number) => void;
};

/** The stored impact preview: the summary, fixed-target mismatches, and the paged before and after scores. */
export function EvaluationImpactProof({ proof, lines, comparisons, comparisonPage, onPageChange }: EvaluationImpactProofProps) {
  return (
    <section className="min-w-0 space-y-3" aria-label="Impact proof">
      <p className="text-xs text-[var(--text-secondary)]">{formatImpactSummary(proof)}</p>
      {proof.writes === 0 && <p className="text-xs text-[var(--text-muted)]">Impact preview wrote no scores.</p>}
      {proof.rulesChecksum && <p className="text-xs [overflow-wrap:anywhere] text-[var(--text-muted)]">Rules checksum {proof.rulesChecksum}.</p>}
      {proof.conflicts.length > 0 && <div className="space-y-2">
        <p className="text-xs text-[var(--text-secondary)]">{FIXED_MISMATCH_NOTE}</p>
        <p className="text-xs text-[var(--text-muted)]">Mismatch numbers use the explicit unit on that KPI&apos;s rule. A missing unit stays on the stored scale.</p>
        <div className="min-w-0 overflow-x-auto">
          <table className="w-full min-w-[36rem] text-left text-xs">
            <caption className="mb-2 text-left text-xs font-bold text-[var(--text-secondary)]">Fixed target mismatches</caption>
            <thead>
              <tr>
                <th scope="col" className="px-2 py-1">Record</th>
                <th scope="col" className="px-2 py-1">KPI</th>
                <th scope="col" className="px-2 py-1">Workbook target</th>
                <th scope="col" className="px-2 py-1">Approved fixed target</th>
              </tr>
            </thead>
            <tbody>
              {proof.conflicts.map((conflict) => {
                const rule = lines.find((item) => item.kpi_key === conflict.kpiKey);
                return (
                  <tr key={`${conflict.recordId || 'record'}-${conflict.kpiKey}`}>
                    <td className="px-2 py-1">{conflict.recordId || '—'}</td>
                    <td className="px-2 py-1">{conflict.kpiKey}</td>
                    <td className="px-2 py-1">{formatIdentifiedTarget(conflict.workbookTarget, rule?.unit)}</td>
                    <td className="px-2 py-1">{formatIdentifiedTarget(conflict.approvedTarget, rule?.unit)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>}
      {comparisons.length > 0 && <div className="space-y-2">
        <div className="min-w-0 overflow-x-auto">
          <table className="w-full min-w-[42rem] text-left text-xs">
            <caption className="mb-2 text-left text-xs font-bold text-[var(--text-secondary)]">Before and after scores</caption>
            <thead>
              <tr>
                <th scope="col" className="px-2 py-1">Employee</th>
                <th scope="col" className="px-2 py-1">Before score</th>
                <th scope="col" className="px-2 py-1">After score</th>
                <th scope="col" className="px-2 py-1">Before grade</th>
                <th scope="col" className="px-2 py-1">After grade</th>
              </tr>
            </thead>
            <tbody>
              {comparisonPage.rows.map((row, index) => <tr key={row.recordId || `${row.employeeCode || 'employee'}-${index}`}>
                <th scope="row" className="px-2 py-1 font-semibold">{row.employeeCode || row.employeeId || '—'}
                  {row.kpis.map((kpi) => <span key={kpi.kpiKey} className="mt-1 block font-normal text-[var(--text-muted)]">{formatKpiLine(kpi)}</span>)}
                </th>
                <td className="px-2 py-1">{displayNumber(row.beforeScore)}</td>
                <td className="px-2 py-1">{displayNumber(row.afterScore)}</td>
                <td className="px-2 py-1">{row.beforeGrade || '—'}</td>
                <td className="px-2 py-1">{row.afterGrade || '—'}</td>
              </tr>)}
            </tbody>
          </table>
        </div>
        <p className="text-xs text-[var(--text-muted)]">Page {comparisonPage.page + 1} of {comparisonPage.pages}</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => onPageChange(comparisonPage.page - 1)} disabled={comparisonPage.page === 0} className="rounded-lg border border-[var(--border-light)] px-2 py-1 text-xs font-bold disabled:opacity-50">Previous impact page</button>
          <button type="button" onClick={() => onPageChange(comparisonPage.page + 1)} disabled={comparisonPage.page >= comparisonPage.pages - 1} className="rounded-lg border border-[var(--border-light)] px-2 py-1 text-xs font-bold disabled:opacity-50">Next impact page</button>
        </div>
      </div>}
    </section>
  );
}
