import { useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, Download, FileJson, Loader2, ShieldCheck, Upload } from 'lucide-react';
import { API_BASE } from '../../config';
import { useUserRole } from '../../context/RoleContext';

type Status = { type: 'success' | 'error'; message: string } | null;

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

export function CorrectiveActionDataPanel() {
  const { fetchWithRole } = useUserRole();
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState<'download' | 'upload' | null>(null);
  const [status, setStatus] = useState<Status>(null);

  const downloadFile = async () => {
    setBusy('download');
    setStatus(null);
    try {
      const response = await fetchWithRole(`${API_BASE}/api/settings/corrective-actions/export`);
      if (!response.ok) throw new Error(await errorMessage(response, 'Could not download corrective actions'));
      const blob = await response.blob();
      const contentDisposition = response.headers.get('content-disposition') || '';
      const filename = contentDisposition.match(/filename="?([^";]+)"?/i)?.[1] || 'pms-corrective-actions.json';
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = filename;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
      setStatus({ type: 'success', message: 'Corrective action history downloaded as a portable JSON file.' });
    } catch (error) {
      setStatus({ type: 'error', message: error instanceof Error ? error.message : 'Could not download corrective actions' });
    } finally {
      setBusy(null);
    }
  };

  const uploadFile = async (file: File) => {
    if (!file.name.toLowerCase().endsWith('.json')) {
      setStatus({ type: 'error', message: 'Please choose a corrective action JSON file.' });
      return;
    }
    setBusy('upload');
    setStatus(null);
    try {
      const body = new FormData();
      body.append('file', file);
      const response = await fetchWithRole(`${API_BASE}/api/settings/corrective-actions/import`, { method: 'POST', body });
      if (!response.ok) throw new Error(await errorMessage(response, 'Could not import corrective actions'));
      const result = await response.json();
      const created = Number(result?.data?.created || 0);
      const updated = Number(result?.data?.updated || 0);
      setStatus({ type: 'success', message: `Imported ${created + updated} actions (${created} new, ${updated} updated).` });
    } catch (error) {
      setStatus({ type: 'error', message: error instanceof Error ? error.message : 'Could not import corrective actions' });
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-xl font-black text-[var(--text-primary)]">Corrective Action Data</h2>
        <p className="mt-1 text-xs text-[var(--text-muted)]">Move action history between databases without rebuilding it manually.</p>
      </header>

      <section className="glass-panel space-y-5 rounded-3xl p-6 shadow-sm">
        <div className="flex items-start gap-3 rounded-2xl border border-blue-500/15 bg-blue-500/5 p-4">
          <ShieldCheck size={20} className="mt-0.5 shrink-0 text-blue-600 dark:text-blue-400" />
          <div>
            <h3 className="text-sm font-black text-[var(--text-primary)]">Portable JSON backup</h3>
            <p className="mt-1 text-xs leading-relaxed text-[var(--text-secondary)]">
              The file includes active and archived actions, notes, statuses, owners, due dates and timestamps. Employees are matched by HR ID and teams by their stable name when imported.
            </p>
          </div>
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <article className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5">
            <div className="flex items-center gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400"><Download size={19} /></span>
              <div>
                <h3 className="text-sm font-black text-[var(--text-primary)]">Download backup</h3>
                <p className="mt-0.5 text-xs text-[var(--text-muted)]">Export all corrective actions to JSON.</p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => void downloadFile()}
              disabled={busy !== null}
              className="mt-5 inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-xs font-extrabold text-white shadow-sm transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy === 'download' ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
              {busy === 'download' ? 'Preparing JSON…' : 'Download JSON'}
            </button>
          </article>

          <article className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5">
            <div className="flex items-center gap-3">
              <span className="grid h-10 w-10 place-items-center rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"><Upload size={19} /></span>
              <div>
                <h3 className="text-sm font-black text-[var(--text-primary)]">Restore from backup</h3>
                <p className="mt-0.5 text-xs text-[var(--text-muted)]">Import a JSON file into this database.</p>
              </div>
            </div>
            <input
              ref={inputRef}
              type="file"
              accept="application/json,.json"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void uploadFile(file);
                event.target.value = '';
              }}
            />
            <button
              type="button"
              onClick={() => inputRef.current?.click()}
              disabled={busy !== null}
              className="mt-5 inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-xl border border-emerald-500/25 bg-emerald-500/10 px-4 text-xs font-extrabold text-emerald-700 transition-colors hover:bg-emerald-500/15 dark:text-emerald-300 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {busy === 'upload' ? <Loader2 size={15} className="animate-spin" /> : <FileJson size={15} />}
              {busy === 'upload' ? 'Restoring actions…' : 'Upload JSON'}
            </button>
          </article>
        </div>

        <StatusBanner status={status} />
        <p className="text-[11px] leading-relaxed text-[var(--text-muted)]">
          Import is an upsert: matching action IDs are updated and new actions are added. No existing action is deleted. Make sure the destination database already contains the related employees and teams.
        </p>
      </section>
    </div>
  );
}

