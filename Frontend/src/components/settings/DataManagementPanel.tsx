import { useCallback, useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { AlertCircle, CheckCircle2, Download, FileSpreadsheet, Loader2, Trash2, Upload, X } from 'lucide-react';
import { API_BASE } from '../../config';
import { useUserRole } from '../../context/RoleContext';
import { refreshPerformanceData } from '../../hooks/usePerformanceData';
import OverlayPortal from '../common/OverlayPortal';
import type { ManagementUploadItem, UploadHistoryItem } from './types';
import { refreshManagementData } from './settingsUtils';

type Status = { type: 'success' | 'error'; message: string } | null;

function asArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

function formatDate(value?: string | null) {
  if (!value) return 'Unknown date';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
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

interface HistoryProps {
  items: UploadHistoryItem[];
  management?: boolean;
  loading?: boolean;
  busy: string | null | string[];
  onDelete: (item: UploadHistoryItem, management: boolean) => void;
  onBatchDelete?: (items: UploadHistoryItem[], management: boolean) => void;
}

function UploadHistory({ items, management = false, loading = false, busy, onDelete, onBatchDelete }: HistoryProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const handleSelectAll = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.checked) {
      setSelectedIds(new Set(items.map(i => i.id)));
    } else {
      setSelectedIds(new Set());
    }
  };

  const handleSelectOne = (id: string, checked: boolean) => {
    const next = new Set(selectedIds);
    if (checked) next.add(id);
    else next.delete(id);
    setSelectedIds(next);
  };

  const handleBatchDelete = () => {
    if (!onBatchDelete) return;
    const selectedItems = items.filter(i => selectedIds.has(i.id));
    onBatchDelete(selectedItems, management);
    setSelectedIds(new Set());
  };

  const isBatchDeleting = Array.isArray(busy);

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)]">
      {onBatchDelete && selectedIds.size > 0 && (
        <div className="flex items-center justify-between bg-rose-50/50 px-4 py-2 border-b border-[var(--border-light)] dark:bg-rose-950/20">
          <span className="text-xs font-semibold text-rose-600 dark:text-rose-400">
            {selectedIds.size} item{selectedIds.size > 1 ? 's' : ''} selected
          </span>
          <button
            onClick={handleBatchDelete}
            disabled={isBatchDeleting}
            className="flex items-center gap-2 rounded-lg bg-rose-500 px-3 py-1.5 text-xs font-bold text-white transition-all hover:bg-rose-600 disabled:opacity-60"
          >
            {isBatchDeleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
            Delete Selected
          </button>
        </div>
      )}
      <div className="max-h-72 overflow-auto">
        <table className="w-full min-w-[620px] text-left text-xs">
          <thead className="sticky top-0 bg-[var(--bg-sunken)] text-[10px] uppercase tracking-wider text-[var(--text-muted)] border-b border-[var(--border-light)]">
            <tr>
              {onBatchDelete && (
                <th className="px-4 py-3 w-10">
                  <input 
                    type="checkbox" 
                    className="rounded border-[var(--border-light)] text-blue-600 focus:ring-blue-500"
                    checked={items.length > 0 && selectedIds.size === items.length}
                    onChange={handleSelectAll}
                  />
                </th>
              )}
              <th className="px-4 py-3">File</th>
              <th className="px-4 py-3">Uploaded</th>
              <th className="px-4 py-3">Scope</th>
              {!management && <th className="px-4 py-3">Records</th>}
              <th className="px-4 py-3 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[var(--border-light)]">
            {loading ? (
              [1, 2, 3].map((i) => (
                <tr key={i} className="animate-pulse">
                  {onBatchDelete && <td className="px-4 py-3.5"><div className="h-4 w-4 rounded bg-[var(--border-light)]/60" /></td>}
                  <td className="px-4 py-3.5"><div className="h-3.5 w-44 rounded bg-[var(--border-light)]/60" /></td>
                  <td className="px-4 py-3.5"><div className="h-3.5 w-32 rounded bg-[var(--border-light)]/60" /></td>
                  <td className="px-4 py-3.5"><div className="h-3.5 w-28 rounded bg-[var(--border-light)]/60" /></td>
                  {!management && <td className="px-4 py-3.5"><div className="h-3.5 w-12 rounded bg-[var(--border-light)]/60" /></td>}
                  <td className="px-4 py-3.5 text-right"><div className="ml-auto h-6 w-6 rounded bg-[var(--border-light)]/60" /></td>
                </tr>
              ))
            ) : (
              items.map((item) => {
                const details = item as ManagementUploadItem;
                const isDeleting = busy === item.id || (isBatchDeleting && selectedIds.has(item.id));
                return (
                  <tr key={item.id} className="transition-colors hover:bg-[var(--bg-sunken)]/40">
                    {onBatchDelete && (
                      <td className="px-4 py-3.5">
                        <input 
                          type="checkbox" 
                          className="rounded border-[var(--border-light)] text-blue-600 focus:ring-blue-500"
                          checked={selectedIds.has(item.id)}
                          onChange={(e) => handleSelectOne(item.id, e.target.checked)}
                        />
                      </td>
                    )}
                    <td className="px-4 py-3.5 text-[var(--text-primary)]">
                      <p className="font-extrabold">{item.filename || 'Unnamed file'}</p>
                      {!management && (
                        <p className="mt-0.5 text-[10px] font-semibold text-[var(--text-muted)]">
                          One workbook · {item.team_count || asArray(details.teams).length || 0} teams
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3.5 text-[var(--text-secondary)]">
                      {formatDate(item.uploaded_at)} · <span className="font-semibold">{item.uploaded_by || 'Unknown'}</span>
                    </td>
                    <td className="max-w-[300px] px-4 py-3.5 text-[var(--text-secondary)]">
                      <p className="truncate font-semibold" title={asArray(details.teams).join(', ')}>
                        {asArray(details.teams).join(', ') || 'All teams'}
                      </p>
                      <p className="mt-0.5 truncate text-[10px] text-[var(--text-muted)]" title={asArray(details.periods).join(', ')}>
                        {asArray(details.periods).join(', ') || 'No period detected'}
                      </p>
                    </td>
                    {!management && (
                      <td className="px-4 py-3.5 font-extrabold tabular-nums text-[var(--text-primary)]">
                        {(item.record_count || 0).toLocaleString()}
                      </td>
                    )}
                    <td className="px-4 py-3.5 text-right">
                      <button
                        aria-label={`Delete ${item.filename || 'upload'}`}
                        disabled={Array.isArray(busy) || busy !== null}
                        onClick={() => onDelete(item, management)}
                        className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-rose-500 hover:bg-rose-500/10 disabled:opacity-40 transition-colors"
                      >
                        {isDeleting ? <Loader2 size={15} className="animate-spin text-rose-500" /> : <Trash2 size={14} />}
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
            {!loading && !items.length && (
              <tr>
                <td
                  colSpan={management ? (onBatchDelete ? 5 : 4) : (onBatchDelete ? 6 : 5)}
                  className="px-4 py-10 text-center text-[var(--text-muted)]"
                >
                  <div className="flex flex-col items-center justify-center gap-1.5">
                    <FileSpreadsheet size={24} className="opacity-40 mb-1" />
                    <p className="font-semibold">No upload history found.</p>
                  </div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function DataManagementPanel() {
  const queryClient = useQueryClient();
  const { fetchWithRole } = useUserRole();
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
      if (!response.ok || !result?.success) throw new Error(result?.detail || result?.message || 'Upload failed');
      setEmployeeStatus({
        type: 'success',
        message: `Processed ${result?.data?.records_imported || 0} records across ${asArray(result?.data?.teams).length} team sheets.`,
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
      if (!response.ok || !result?.success) throw new Error(result?.detail || result?.message || 'Upload failed');
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
            disabled={busy !== null}
            className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-xs font-bold text-white shadow-sm transition-all hover:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            {isEmployeeBusy ? (
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
