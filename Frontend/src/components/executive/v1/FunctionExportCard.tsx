import { Download, FileSpreadsheet, FileText, Lock, Share2 } from 'lucide-react';
import { ExecCard, ExecCardHeader, Footnote } from './ExecPrimitives';

/**
 * Reports & export (Figma 48:3). Exports must contain the selected function
 * only (Mustafa). The backend export endpoints accept `team` but not yet
 * `function=`, so the actions stay disabled with a clear note rather than
 * exporting a team list the backend cannot scope.
 */
export default function FunctionExportCard({ fn, period, functionExportSupported = false, otherFunctions = [] }: {
  fn: string; period: string; functionExportSupported?: boolean; otherFunctions?: string[];
}) {
  const disabledNote = 'Function-limited export needs the backend export to accept function= — disabled until then.';
  const items = [
    { icon: FileText, title: `${fn} monthly summary — ${period}`, sub: 'PDF' },
    { icon: FileSpreadsheet, title: 'Team leaderboard + KPI rollup', sub: 'Excel' },
    { icon: FileSpreadsheet, title: `Employee scores — ${fn} teams`, sub: 'Excel' },
  ];
  return (
    <ExecCard aria-labelledby="fs-export-title" data-testid="function-export">
      <ExecCardHeader
        titleId="fs-export-title"
        icon={Share2}
        iconBg="var(--exec-pos-bg)"
        iconColor="var(--insights-positive)"
        title="Reports & export"
        subtitle={`Function-locked: exports contain ${fn} only`}
        action={<span className="rounded-full bg-[var(--exec-info-bg)] px-[8px] py-[2px] text-[11px] font-semibold text-[var(--exec-info-text)]">{fn}</span>}
      />
      <div className="flex flex-wrap gap-[8px]">
        <button type="button" disabled={!functionExportSupported} title={functionExportSupported ? undefined : disabledNote} className="inline-flex items-center gap-[6px] rounded-[8px] bg-gradient-to-r from-[#0069B4] to-[#00A859] px-[14px] py-[8px] text-[13px] font-semibold text-white disabled:cursor-not-allowed disabled:opacity-50">
          <Download aria-hidden="true" className="size-[14px]" />Export PDF
        </button>
        <button type="button" disabled={!functionExportSupported} title={functionExportSupported ? undefined : disabledNote} className="inline-flex items-center gap-[6px] rounded-[8px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] px-[14px] py-[8px] text-[13px] font-semibold text-[var(--insights-heading)] disabled:cursor-not-allowed disabled:opacity-50">
          <FileSpreadsheet aria-hidden="true" className="size-[14px]" />Export Excel
        </button>
      </div>
      <ul className="flex flex-col">
        {items.map(({ icon: Icon, title, sub }) => (
          <li key={title} className="flex items-center gap-[10px] border-b border-[var(--insights-row-border)] py-[9px] last:border-b-0">
            <Icon aria-hidden="true" className="size-[15px] text-[var(--exec-info-text)]" />
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-[13px] font-semibold text-[var(--insights-heading)]">{title}</span>
              <span className="text-[11px] text-[var(--text-muted)]">{sub}</span>
            </span>
            <Download aria-hidden="true" className="size-[14px] text-[var(--text-muted)] opacity-50" />
          </li>
        ))}
        <li className="flex items-center gap-[10px] py-[9px] opacity-60">
          <Lock aria-hidden="true" className="size-[15px] text-[var(--text-muted)]" />
          <span className="flex min-w-0 flex-1 flex-col">
            <span className="truncate text-[13px] font-semibold text-[var(--text-secondary)]">Company-wide executive report</span>
            <span className="text-[11px] text-[var(--text-muted)]">Admin / GM only</span>
          </span>
          <span className="rounded-full bg-[var(--exec-chip-bg)] px-[8px] py-[2px] text-[10px] font-semibold text-[var(--exec-chip-text)]">Not in your scope</span>
        </li>
      </ul>
      {!functionExportSupported && (
        <p role="note" className="rounded-[8px] bg-[var(--exec-warning-bg)] px-[12px] py-[8px] text-[12px] font-medium text-[var(--exec-warning-text)]">
          Export is disabled: the report export API doesn&apos;t accept a <code>function=</code> filter yet, so it can&apos;t guarantee a {fn}-only file.
        </p>
      )}
      {otherFunctions.length > 0 && (
        <Footnote>Switch to {otherFunctions.join(' or ')} to export that function. Other functions are never included in your exports.</Footnote>
      )}
    </ExecCard>
  );
}
