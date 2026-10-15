import { useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, DatabaseBackup, Download, FileJson, Loader2, SearchCheck, ShieldCheck, Upload } from 'lucide-react';
import { API_BASE } from '../../config';
import { useUserRole } from '../../context/RoleContext';

type Policy = 'skip' | 'replace';
type Status = { type: 'success' | 'error'; message: string } | null;
type TableCounts = { incoming: number; new: number; existing_ids: number; skipped: number; replaced: number };
type Conflict = { table: string; reason: string };
export type SnapshotReport = {
  dry_run: boolean;
  committed: boolean;
  importable: boolean;
  policy: Policy;
  database_revision: string | null;
  snapshot_revision: string | null;
  tables: Record<string, TableCounts>;
  totals?: TableCounts;
  blocking_conflicts: Conflict[];
  blocking_conflict_count: number;
  user_references?: { matched: number; cleared: Record<string, number>; missing_accounts: string[] };
};

const SNAPSHOT_API = `${API_BASE}/api/settings/data-snapshot`;

const POLICIES: Array<{ value: Policy; label: string; detail: string }> = [
  { value: 'skip', label: 'Skip existing ids', detail: 'Rows whose id is already here are left as they are.' },
  { value: 'replace', label: 'Replace existing ids', detail: 'Rows whose id is already here are overwritten by the file.' },
];

function StatusBanner({ status }: { status: Status }) {
  if (!status) return null;
  return (
    <div
      role="status"
      className={`flex items-start gap-2 rounded-xl border px-3.5 py-2.5 text-xs font-semibold ${
        status.type === 'success'
          ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
          : 'border-red-500/20 bg-red-500/10 text-red-600 dark:text-red-400'
      }`}
    >
      {status.type === 'success' ? <CheckCircle2 size={16} className="mt-0.5 shrink-0" /> : <AlertCircle size={16} className="mt-0.5 shrink-0" />}
      <span>{status.message}</span>
    </div>
  );
}

async function errorMessage(response: Response, fallback: string) {
  const result = await response.json().catch(() => ({}));
  return result?.detail || result?.message || fallback;
}

function CheckResult({ report }: { report: SnapshotReport }) {
  const rows = Object.entries(report.tables).filter(([, counts]) => counts.incoming > 0);
  const missing = report.user_references?.missing_accounts ?? [];
  const cleared = Object.entries(report.user_references?.cleared ?? {});
  return (
    <div className="space-y-3 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4" aria-label="Snapshot check">
      <p className={`text-xs font-black ${report.importable ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}`}>
        {report.importable
          ? `Ready to import: ${report.totals?.new ?? 0} new rows, ${report.totals?.existing_ids ?? 0} existing ids (${report.policy === 'skip' ? 'skipped' : 'replaced'}).`
          : `${report.blocking_conflict_count} conflict(s) block this import. Nothing can be saved until they are resolved.`}
      </p>
      {report.blocking_conflicts.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-xs text-[var(--text-secondary)]">
          {report.blocking_conflicts.map((conflict, index) => (
            <li key={`${conflict.table}-${index}`}><span className="font-bold">{conflict.table}</span>: {conflict.reason}</li>
          ))}
        </ul>
      )}
      {missing.length > 0 && (
        <p className="text-xs text-[var(--text-secondary)]">Accounts named in the file but not found here: {missing.join(', ')}.</p>
      )}
      {cleared.length > 0 && (
        <p className="text-xs text-[var(--text-secondary)]">
          Optional user references that will be left empty: {cleared.map(([column, count]) => `${column} (${count})`).join(', ')}.
        </p>
      )}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="text-[var(--text-muted)]">
              <tr>
                <th scope="col" className="py-1 pr-3 font-bold">Table</th>
                <th scope="col" className="py-1 pr-3 text-right font-bold">In file</th>
                <th scope="col" className="py-1 pr-3 text-right font-bold">New</th>
                <th scope="col" className="py-1 pr-3 text-right font-bold">Existing ids</th>
              </tr>
            </thead>
            <tbody className="text-[var(--text-primary)]">
              {rows.map(([table, counts]) => (
                <tr key={table} className="border-t border-[var(--border-light)]">
                  <td className="py-1 pr-3 font-semibold">{table}</td>
                  <td className="py-1 pr-3 text-right tabular-nums">{counts.incoming}</td>
                  <td className="py-1 pr-3 text-right tabular-nums">{counts.new}</td>
                  <td className="py-1 pr-3 text-right tabular-nums">{counts.existing_ids}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export function DataSnapshotPanel() {
  const { fetchWithRole } = useUserRole();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<'download' | 'check' | 'import' | null>(null);
  const [status, setStatus] = useState<Status>(null);
  const [file, setFile] = useState<File | null>(null);
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [report, setReport] = useState<SnapshotReport | null>(null);

  const downloadSnapshot = async () => {
    setBusy('download');
    setStatus(null);
    try {
      const response = await fetchWithRole(`${SNAPSHOT_API}/export`);
      if (!response.ok) throw new Error(await errorMessage(response, 'Could not download the snapshot'));
      const blob = await response.blob();
      const contentDisposition = response.headers.get('content-disposition') || '';
      const filename = contentDisposition.match(/filename="?([^";]+)"?/i)?.[1] || 'pms-data-snapshot.json';
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      setStatus({ type: 'success', message: 'Snapshot downloaded. Keep the file private and delete it when you are done.' });
    } catch (error) {
      setStatus({ type: 'error', message: error instanceof Error ? error.message : 'Could not download the snapshot' });
    } finally {
      setBusy(null);
    }
  };

  const send = async (step: 'import/dry-run' | 'import', chosenFile: File, chosenPolicy: Policy) => {
    const body = new FormData();
    body.append('file', chosenFile);
    const response = await fetchWithRole(`${SNAPSHOT_API}/${step}?policy=${chosenPolicy}`, { method: 'POST', body });
    if (!response.ok) throw new Error(await errorMessage(response, step === 'import' ? 'The import failed. Nothing was saved.' : 'Could not check the snapshot'));
    const result = await response.json();
    return result.data as SnapshotReport;
  };

  const checkSnapshot = async () => {
    if (!file || !policy) return;
    setBusy('check');
    setStatus(null);
    setReport(null);
    try {
      setReport(await send('import/dry-run', file, policy));
    } catch (error) {
      setStatus({ type: 'error', message: error instanceof Error ? error.message : 'Could not check the snapshot' });
    } finally {
      setBusy(null);
    }
  };

  const importSnapshot = async () => {
    if (!file || !policy || !report?.importable) return;
    const confirmed = window.confirm(
      `Import ${file.name} into this database? Existing ids will be ${policy === 'skip' ? 'skipped' : 'replaced'}. This is saved in one step and cannot be undone from here.`,
    );
    if (!confirmed) return;
    setBusy('import');
    setStatus(null);
    try {
      const committed = await send('import', file, policy);
      setReport(null);
      setFile(null);
      setStatus({
        type: 'success',
        message: `Imported ${committed.totals?.new ?? 0} new rows; ${committed.totals?.replaced ?? 0} replaced, ${committed.totals?.skipped ?? 0} skipped.`,
      });
    } catch (error) {
      setStatus({ type: 'error', message: error instanceof Error ? error.message : 'The import failed. Nothing was saved.' });
    } finally {
      setBusy(null);
    }
  };

  const chooseFile = (chosen: File) => {
    setReport(null);
    setStatus(null);
    if (!chosen.name.toLowerCase().endsWith('.json')) {
      setFile(null);
      setStatus({ type: 'error', message: 'Please choose a data snapshot JSON file.' });
      return;
    }
    setFile(chosen);
  };

  return (
    <section className="glass-panel mt-6 space-y-5 rounded-3xl p-6 shadow-sm" aria-labelledby="data-snapshot-title">
      <header className="flex items-start gap-3">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400"><DatabaseBackup size={19} /></span>
        <div>
          <h2 id="data-snapshot-title" className="text-lg font-black text-[var(--text-primary)]">Data snapshot</h2>
          <p className="mt-1 text-xs text-[var(--text-muted)]">Copy the business data to another environment, or bring it in from one.</p>
        </div>
      </header>

      <div className="flex items-start gap-3 rounded-2xl border border-blue-500/15 bg-blue-500/5 p-4">
        <ShieldCheck size={20} className="mt-0.5 shrink-0 text-blue-600 dark:text-blue-400" />
        <p className="text-xs leading-relaxed text-[var(--text-secondary)]">
          The file holds teams, employees, performance records, evaluation settings, plans and actions. It never holds passwords, sessions or account
          details: users are named by username only, and an import matches them to the accounts that already exist here. The file is not stored on
          the server. To move a whole database, including accounts, follow the database move runbook.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <article className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5">
          <h3 className="text-sm font-black text-[var(--text-primary)]">Download snapshot</h3>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">Every download is recorded in the audit log.</p>
          <button
            type="button"
            onClick={() => void downloadSnapshot()}
            disabled={busy !== null}
            className="mt-5 inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-xs font-extrabold text-white shadow-sm transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy === 'download' ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
            {busy === 'download' ? 'Preparing snapshot…' : 'Download snapshot'}
          </button>
        </article>

        <article className="space-y-4 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5">
          <div>
            <h3 className="text-sm font-black text-[var(--text-primary)]">Import snapshot</h3>
            <p className="mt-0.5 text-xs text-[var(--text-muted)]">Check the file first. Nothing is saved until you import.</p>
          </div>
          <input
            ref={inputRef}
            type="file"
            accept="application/json,.json"
            className="hidden"
            onChange={(event) => {
              const chosen = event.target.files?.[0];
              if (chosen) chooseFile(chosen);
              event.target.value = '';
            }}
          />
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            disabled={busy !== null}
            className="inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-xl border border-[var(--border-light)] px-4 text-xs font-extrabold text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-sunken)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <FileJson size={15} />
            {file ? file.name : 'Choose snapshot file'}
          </button>

          <fieldset className="space-y-2">
            <legend className="text-xs font-bold text-[var(--text-primary)]">When an id already exists here</legend>
            {POLICIES.map((option) => (
              <label key={option.value} className="flex cursor-pointer items-start gap-2 text-xs text-[var(--text-secondary)]">
                <input
                  type="radio"
                  name="snapshot-policy"
                  value={option.value}
                  checked={policy === option.value}
                  onChange={() => {
                    setPolicy(option.value);
                    setReport(null);
                  }}
                  className="mt-0.5"
                />
                <span><span className="font-bold text-[var(--text-primary)]">{option.label}.</span> {option.detail}</span>
              </label>
            ))}
          </fieldset>

          <div className="grid gap-2 sm:grid-cols-2">
            <button
              type="button"
              onClick={() => void checkSnapshot()}
              disabled={busy !== null || !file || !policy}
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-blue-500/25 bg-blue-500/10 px-4 text-xs font-extrabold text-blue-700 transition-colors hover:bg-blue-500/15 dark:text-blue-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy === 'check' ? <Loader2 size={15} className="animate-spin" /> : <SearchCheck size={15} />}
              {busy === 'check' ? 'Checking…' : 'Check file'}
            </button>
            <button
              type="button"
              onClick={() => void importSnapshot()}
              disabled={busy !== null || !report?.importable}
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-xl bg-emerald-600 px-4 text-xs font-extrabold text-white shadow-sm transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy === 'import' ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
              {busy === 'import' ? 'Importing…' : 'Import'}
            </button>
          </div>
        </article>
      </div>

      {report && <CheckResult report={report} />}
      <StatusBanner status={status} />
    </section>
  );
}
