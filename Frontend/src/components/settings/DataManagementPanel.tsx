import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { AlertCircle, CheckCircle2, Download, FileSpreadsheet, Loader2, Trash2, Upload, X } from 'lucide-react';
import { API_BASE } from '../../config';
import { useUserRole } from '../../context/RoleContext';
import { useUploadJob } from '../../context/uploadJobState';
import { refreshPerformanceData } from '../../hooks/usePerformanceData';
import OverlayPortal from '../common/OverlayPortal';
import type { ManagementUploadItem, UploadHistoryItem } from './types';
import { refreshManagementData } from './settingsUtils';
import { UploadColumnNotices } from './UploadColumnNotices';
import { UploadHistory } from './UploadHistory';
import { asArray } from './uploadFormat';
import { readColumnWarnings, type ColumnWarning } from './uploadHeaderNotices';

type Status = { type: 'success' | 'error'; message: string; columnWarnings?: ColumnWarning[] } | null;

function readableUploadError(value: unknown, fallback: string): string {
  if (typeof value === 'string' && value.trim()) return value;
  if (!value || typeof value !== 'object') return fallback;

  const record = value as Record<string, unknown>;
  if (typeof record.message === 'string' && record.message.trim()) return record.message;
  if (typeof record.detail === 'string' && record.detail.trim()) return record.detail;
  if (Array.isArray(record.errors)) {
    const messages = record.errors
      .map((item) => {
        if (typeof item === 'string') return item;
        if (item && typeof item === 'object' && typeof (item as Record<string, unknown>).msg === 'string') {
          return (item as Record<string, unknown>).msg as string;
        }
        return null;
      })
      .filter((item): item is string => Boolean(item));
    if (messages.length) return messages.join(' · ');
  }
  return fallback;
}

function columnWarningsFrom(value: unknown): ColumnWarning[] {
  if (!value || typeof value !== 'object') return [];
  return readColumnWarnings((value as { column_warnings?: unknown }).column_warnings);
}

function StatusBanner({ status }: { status: Status }) {
  if (!status) return null;
  return (
    <div
      role="status"
      className={`flex items-center gap-2 rounded-xl border px-3.5 py-2.5 text-xs font-semibold ${
        status.type === 'success'
          ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
          : 'border-red-500/20 bg-red-500/10 text-red-600 dark:text-red-400'
      }`}
    >
      {status.type === 'success' ? <CheckCircle2 size={16} className="shrink-0" /> : <AlertCircle size={16} className="shrink-0" />}
      {status.message}
    </div>
  );
}

function ProcessingBanner({ busyType }: { busyType: 'employee' | 'management' }) {
  const isEmployee = busyType === 'employee';
  return (
    <div
      role="status"
      className={`flex items-center gap-3 rounded-2xl border px-4 py-3 text-xs font-semibold shadow-sm animate-pulse ${
        isEmployee
          ? 'border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400'
          : 'border-purple-500/30 bg-purple-500/10 text-purple-600 dark:text-purple-400'
      }`}
    >
      <Loader2 size={18} className={`animate-spin shrink-0 ${isEmployee ? 'text-blue-500' : 'text-purple-500'}`} />
      <div>
        <p className="font-extrabold text-xs">
          {isEmployee ? 'Processing Excel File & Recalculating Metrics…' : 'Processing Management Template…'}
        </p>
        <p className="text-[11px] opacity-80 mt-0.5">
          {isEmployee
            ? 'Parsing team sheets, calculating employee weighted scores, and syncing database records.'
            : 'Updating balanced scorecard configurations and team performance targets.'}
        </p>
      </div>
    </div>
  );
}

function DeleteConfirmModal({
  filename,
  management,
  busy,
  onCancel,
  onConfirm,
}: {
  filename: string;
  management: boolean;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <OverlayPortal>
      <div
        className="fixed inset-0 z-[9999] flex items-center justify-center bg-slate-950/50 p-4 backdrop-blur-sm animate-in fade-in zoom-in-95 duration-150"
        onMouseDown={(e) => {
          if (e.target === e.currentTarget) onCancel();
        }}
      >
        <div
          role="alertdialog"
          aria-modal="true"
          aria-labelledby="delete-confirm-title"
          aria-describedby="delete-confirm-desc"
          className="w-full max-w-md overflow-hidden rounded-3xl border border-rose-500/20 bg-[var(--bg-surface)] shadow-2xl"
        >
          <div className="flex items-start gap-4 p-6">
            <span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-rose-500/10 text-rose-600">
              <Trash2 size={22} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-[10px] font-extrabold uppercase tracking-widest text-rose-600 dark:text-rose-400">
                    Confirm Deletion
                  </p>
                  <h3 id="delete-confirm-title" className="mt-1 text-lg font-black text-[var(--text-primary)] leading-snug break-words">
                    Delete “{filename}”?
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={onCancel}
                  aria-label="Close dialog"
                  className="rounded-lg p-1 text-[var(--text-muted)] hover:bg-[var(--bg-sunken)] hover:text-[var(--text-primary)] transition-colors"
                >
                  <X size={18} />
                </button>
              </div>
              <p id="delete-confirm-desc" className="mt-3 text-xs leading-relaxed text-[var(--text-muted)]">
                This action cannot be undone. This {management ? 'management template' : 'employee PMS data'} file and its calculated records will be permanently removed.
              </p>
            </div>
          </div>
          <div className="flex items-center justify-end gap-2.5 border-t border-[var(--border-light)] bg-[var(--bg-sunken)]/50 px-6 py-4">
            <button
              type="button"
              autoFocus
              onClick={onCancel}
              className="min-h-10 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-4 text-xs font-extrabold text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)] transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={onConfirm}
              className="inline-flex min-h-10 items-center gap-2 rounded-xl bg-rose-600 px-5 text-xs font-extrabold text-white shadow-lg shadow-rose-600/20 hover:bg-rose-700 disabled:opacity-50 transition-colors"
            >
              {busy ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
              Delete file
            </button>
          </div>
        </div>
      </div>
    </OverlayPortal>
  );
}

export function DataManagementPanel() {
  const queryClient = useQueryClient();
  const { fetchWithRole } = useUserRole();
  const { activeJobId, trackJob } = useUploadJob();
  const employeeInput = useRef<HTMLInputElement>(null);
  const managementInput = useRef<HTMLInputElement>(null);
  const [uploads, setUploads] = useState<UploadHistoryItem[]>([]);
  const [managementUploads, setManagementUploads] = useState<ManagementUploadItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<'employee' | 'management' | string | null>(null);
  const [employeeStatus, setEmployeeStatus] = useState<Status>(null);
  const [managementStatus, setManagementStatus] = useState<Status>(null);
  const [pendingDelete, setPendingDelete] = useState<{ item: UploadHistoryItem; management: boolean } | null>(null);

  const loadUploads = useCallback(async () => {
    const [employeeResponse, managementResponse] = await Promise.all([
      fetchWithRole(`${API_BASE}/api/uploads/`),
      fetchWithRole(`${API_BASE}/api/team-management/management-kpi-config/uploads`),
    ]);
    if (employeeResponse.ok) {
      const result = await employeeResponse.json();
      setUploads(Array.isArray(result?.data) ? result.data : []);
    }
    if (managementResponse.ok) {
      const result = await managementResponse.json();
      setManagementUploads(Array.isArray(result?.data) ? result.data : []);
    }
  }, [fetchWithRole]);

  useEffect(() => {
    let active = true;
    void Promise.resolve()
      .then(loadUploads)
      .catch((error) => console.error('Failed to load upload history', error))
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [loadUploads]);

  const validateExcel = (file: File, setStatus: (status: Status) => void) => {
    if (/\.(xlsx|xls)$/i.test(file.name)) return true;
    setStatus({ type: 'error', message: 'Invalid file type. Please upload an Excel file (.xlsx or .xls).' });
    return false;
  };

  const uploadEmployeeData = async (file: File) => {
    if (!validateExcel(file, setEmployeeStatus)) return;
    setBusy('employee');
    setEmployeeStatus(null);
    try {
      const body = new FormData();
      body.append('file', file);
      const response = await fetchWithRole(`${API_BASE}/api/uploads/pms`, { method: 'POST', body });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result?.success) {
        const detail = result?.detail;
        const message = readableUploadError(detail ?? result?.message, 'Upload failed');
        const columnWarnings = columnWarningsFrom(detail && typeof detail === 'object' ? (detail as { report?: unknown }).report : undefined);
        if (columnWarnings.length) {
          setEmployeeStatus({ type: 'error', message, columnWarnings });
          return;
        }
        throw new Error(message);
      }
      const uploadData = result?.data as Record<string, unknown> | undefined;
      const jobId = typeof uploadData?.job_id === 'string' ? uploadData.job_id : null;
      if (jobId) {
        trackJob(jobId);
        return;
      }
      setEmployeeStatus({
        type: 'success',
        message: `Processed ${Number(uploadData?.records_imported || 0)} records across ${asArray(uploadData?.teams).length} team sheets.`,
        columnWarnings: readColumnWarnings(uploadData?.column_warnings),
      });
      refreshPerformanceData();
      await loadUploads();
    } catch (error) {
      setEmployeeStatus({ type: 'error', message: error instanceof Error ? error.message : 'Upload failed' });
    } finally {
      setBusy(null);
    }
  };

  const uploadManagementData = async (file: File) => {
    if (!validateExcel(file, setManagementStatus)) return;
    setBusy('management');
    setManagementStatus(null);
    try {
      const body = new FormData();
      body.append('file', file);
      const response = await fetchWithRole(`${API_BASE}/api/performance/balanced-scorecard/template/upload`, { method: 'POST', body });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result?.success) {
        throw new Error(readableUploadError(result?.detail ?? result?.message, 'Upload failed'));
      }
      const teams = asArray(result?.data?.teams);
      const periods = asArray(result?.data?.periods);
      setManagementStatus({
        type: 'success',
        message: `Management template uploaded for ${teams.join(', ') || 'template teams'}${periods[0] ? ` (${periods[0]})` : ''}.`,
      });
      await refreshManagementData(queryClient, loadUploads);
    } catch (error) {
      setManagementStatus({ type: 'error', message: error instanceof Error ? error.message : 'Upload failed' });
    } finally {
      setBusy(null);
      if (managementInput.current) managementInput.current.value = '';
    }
  };

  const downloadManagementTemplate = async () => {
    try {
      const response = await fetchWithRole(`${API_BASE}/api/performance/balanced-scorecard/template/download`);
      if (!response.ok) throw new Error('Failed to download template');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = 'Template_Management.xlsx';
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      setManagementStatus({ type: 'error', message: error instanceof Error ? error.message : 'Download failed' });
    }
  };

  const handleDeleteRequest = (item: UploadHistoryItem, management = false) => {
    setPendingDelete({ item, management });
  };

  const confirmDeleteUpload = async () => {
    if (!pendingDelete) return;
    const { item, management } = pendingDelete;
    const filename = item.filename || 'this upload';
    setBusy(item.id);
    try {
      const endpoint = management
        ? `${API_BASE}/api/team-management/management-kpi-config/uploads/${item.id}`
        : `${API_BASE}/api/uploads/${item.id}`;
      const response = await fetchWithRole(endpoint, { method: 'DELETE' });
      const result = await response.json().catch(() => ({}));
      if (!response.ok || !result?.success) throw new Error(result?.detail || result?.message || 'Delete failed');
      if (management) {
        setManagementStatus({ type: 'success', message: `Deleted management upload "${filename}".` });
        await refreshManagementData(queryClient, loadUploads);
      } else {
        setEmployeeStatus({ type: 'success', message: `Deleted "${filename}" and refreshed performance data.` });
        refreshPerformanceData();
        await loadUploads();
      }
    } catch (error) {
      const status = { type: 'error' as const, message: error instanceof Error ? error.message : 'Delete failed' };
      if (management) setManagementStatus(status);
      else setEmployeeStatus(status);
    } finally {
      setBusy(null);
      setPendingDelete(null);
    }
  };

  const isEmployeeBusy = busy === 'employee';
  const isManagementBusy = busy === 'management';

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-xl font-black text-[var(--text-primary)]">Data Management</h2>
        <p className="mt-1 text-xs text-[var(--text-muted)]">Upload employee PMS data and management scorecard templates independently.</p>
      </header>

      <section className="glass-panel space-y-4 rounded-3xl p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-black text-[var(--text-primary)]">
              <FileSpreadsheet size={17} className="text-blue-500" /> Employee PMS uploads
            </h3>
            <p className="mt-1 text-xs text-[var(--text-muted)]">Excel trend sheets used by employee dashboards.</p>
          </div>
          <button
            onClick={() => employeeInput.current?.click()}
            disabled={busy !== null || activeJobId !== null}
            className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-bold text-white shadow-sm transition-all hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isEmployeeBusy || activeJobId ? (
              <>
                <Loader2 size={15} className="animate-spin" /> {activeJobId ? 'Processing in background…' : 'Processing…'}
              </>
            ) : (
              <>
                <Upload size={15} /> Upload Excel
              </>
            )}
          </button>
        </div>
        <input
          ref={employeeInput}
          type="file"
          accept=".xlsx,.xls"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) uploadEmployeeData(file);
            event.target.value = '';
          }}
        />
        {isEmployeeBusy && <ProcessingBanner busyType="employee" />}
        <StatusBanner status={employeeStatus} />
        <UploadColumnNotices warnings={employeeStatus?.columnWarnings ?? []} />
        <UploadHistory items={uploads} loading={loading} busy={busy} onDelete={handleDeleteRequest} />
      </section>

      <section className="glass-panel space-y-4 rounded-3xl p-6 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-black text-[var(--text-primary)]">
              <FileSpreadsheet size={17} className="text-purple-500" /> Management template uploads
            </h3>
            <p className="mt-1 text-xs text-[var(--text-muted)]">Balanced scorecard configuration and snapshots.</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={downloadManagementTemplate}
              disabled={busy !== null}
              className="flex items-center gap-2 rounded-xl border border-[var(--border-light)] px-4 py-2.5 text-xs font-bold text-[var(--text-secondary)] hover:bg-[var(--bg-sunken)] disabled:opacity-60"
            >
              <Download size={15} /> Template
            </button>
            <button
              onClick={() => managementInput.current?.click()}
              disabled={busy !== null}
              className="flex items-center gap-2 rounded-xl bg-purple-600 px-4 py-2.5 text-xs font-bold text-white shadow-sm transition-all hover:bg-purple-700 disabled:opacity-60 disabled:cursor-not-allowed"
            >
              {isManagementBusy ? (
                <>
                  <Loader2 size={15} className="animate-spin" /> Processing…
                </>
              ) : (
                <>
                  <Upload size={15} /> Upload Excel
                </>
              )}
            </button>
          </div>
        </div>
        <input
          ref={managementInput}
          type="file"
          accept=".xlsx,.xls"
          className="hidden"
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) uploadManagementData(file);
          }}
        />
        {isManagementBusy && <ProcessingBanner busyType="management" />}
        <StatusBanner status={managementStatus} />
        <UploadHistory items={managementUploads} management loading={loading} busy={busy} onDelete={handleDeleteRequest} />
      </section>

      {pendingDelete && (
        <DeleteConfirmModal
          filename={pendingDelete.item.filename || 'this upload'}
          management={pendingDelete.management}
          busy={busy === pendingDelete.item.id}
          onCancel={() => setPendingDelete(null)}
          onConfirm={confirmDeleteUpload}
        />
      )}
    </div>
  );
}
