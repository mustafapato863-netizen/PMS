import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { Activity, AlertCircle, Clock3, Loader2, RefreshCw, Search, ShieldCheck, X } from 'lucide-react';
import { API_BASE } from '../../config';
import { useUserRole } from '../../context/RoleContext';
import { AdminTableShell } from './shell/AdminTableShell';
import { BODY_CELL_CLASS, BODY_ROW_CLASS, HEAD_CELL_CLASS } from './shell/adminTableClasses';
import { SortableHeaderCell } from './shell/SortableHeaderCell';
import { TablePagination } from './shell/TablePagination';
import { usePagination } from './shell/usePagination';
import { directionFor, useTableSort, type SortColumn } from './shell/useTableSort';

const ERRORS_PER_PAGE = 25;

type ErrorSortKey = 'time' | 'errorClass' | 'method' | 'endpoint';

/** The sortable columns. Reference and Details are not sortable. */
const SYSTEM_ERROR_SORT_COLUMNS: SortColumn<SystemError, ErrorSortKey>[] = [
  { key: 'time', value: (item) => timestampOf(item.occurred_at) },
  { key: 'errorClass', value: (item) => item.error_class },
  { key: 'method', value: (item) => item.method },
  { key: 'endpoint', value: (item) => item.endpoint },
];

function timestampOf(value: string | null): number | null {
  if (!value) return null;
  const time = Date.parse(value);
  return Number.isNaN(time) ? null : time;
}

/** How long ago, read from the time; the absolute time is shown in the cell's title. */
function relativeTime(value: string | null) {
  if (!value) return 'Time unavailable';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : formatDistanceToNow(date, { addSuffix: true });
}

type SystemError = {
  id: string;
  request_id: string | null;
  endpoint: string;
  method: string;
  error_class: string;
  occurred_at: string | null;
  error_message?: string | null;
  stack_trace?: string | null;
};

type ApiResult<T> = { success: boolean; message?: string; detail?: string; data?: T };

function formatDate(value: string | null) {
  if (!value) return 'Time unavailable';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

async function readError(response: Response, fallback: string) {
  const result = await response.json().catch(() => ({}));
  return typeof result?.detail === 'string' ? result.detail
    : typeof result?.message === 'string' ? result.message
      : fallback;
}

export function SystemErrorsPanel() {
  const { fetchWithRole } = useUserRole();
  const [errors, setErrors] = useState<SystemError[]>([]);
  const [selectedError, setSelectedError] = useState<SystemError | null>(null);
  const [requestIdInput, setRequestIdInput] = useState('');
  const [requestIdFilter, setRequestIdFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [loadingDetails, setLoadingDetails] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fetchErrors = useCallback(async (filter = ''): Promise<SystemError[]> => {
    const query = new URLSearchParams({ limit: '50' });
    if (filter.trim()) query.set('request_id', filter.trim());
    const response = await fetchWithRole(`${API_BASE}/api/settings/system-errors?${query}`);
    if (!response.ok) throw new Error(await readError(response, 'Could not load system errors.'));
    const result = await response.json() as ApiResult<SystemError[]>;
    return result.data || [];
  }, [fetchWithRole]);

  useEffect(() => {
    let active = true;

    const loadInitialErrors = async () => {
      try {
        const result = await fetchErrors();
        if (active) setErrors(result);
      } catch (error) {
        if (active) {
          setErrorMessage(error instanceof Error ? error.message : 'Could not load system errors.');
          setErrors([]);
        }
      } finally {
        if (active) setLoading(false);
      }
    };

    void loadInitialErrors();
    return () => { active = false; };
  }, [fetchErrors]);

  const loadErrors = useCallback(async (filter = '') => {
    setLoading(true);
    setErrorMessage(null);
    setSelectedError(null);
    try {
      setErrors(await fetchErrors(filter));
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Could not load system errors.');
      setErrors([]);
    } finally {
      setLoading(false);
    }
  }, [fetchErrors]);

  const openDetails = async (item: SystemError) => {
    setSelectedError(item);
    setLoadingDetails(true);
    setErrorMessage(null);
    try {
      const response = await fetchWithRole(`${API_BASE}/api/settings/system-errors/${item.id}`);
      if (!response.ok) throw new Error(await readError(response, 'Could not load error details.'));
      const result = await response.json() as ApiResult<SystemError>;
      setSelectedError(result.data || item);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Could not load error details.');
    } finally {
      setLoadingDetails(false);
    }
  };

  const applyFilter = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const filter = requestIdInput.trim();
    setRequestIdFilter(filter);
    void loadErrors(filter);
  };

  const { rows: sortedErrors, sort, toggle } = useTableSort(errors, SYSTEM_ERROR_SORT_COLUMNS);
  const pagination = usePagination(sortedErrors, ERRORS_PER_PAGE, `${requestIdFilter}|${sort?.key ?? ''}|${sort?.direction ?? ''}`);

  const renderErrorRow = (item: SystemError) => {
    const selected = selectedError?.id === item.id;
    return (
      <tr key={item.id} className={`${BODY_ROW_CLASS} ${selected ? 'bg-blue-500/[0.06]' : ''}`}>
        <td className={BODY_CELL_CLASS}>
          <time dateTime={item.occurred_at ?? undefined} title={formatDate(item.occurred_at)} className="inline-flex items-center gap-1.5 whitespace-nowrap">
            <Clock3 size={12} aria-hidden="true" />
            {relativeTime(item.occurred_at)}
          </time>
        </td>
        <td className={`${BODY_CELL_CLASS} font-extrabold text-[var(--text-primary)]`}>{item.error_class}</td>
        <td className={BODY_CELL_CLASS}>
          <span className="rounded-md bg-[var(--bg-sunken)] px-1.5 py-0.5 font-mono text-[12px] font-bold text-[var(--text-secondary)]">{item.method}</span>
        </td>
        <td className={`${BODY_CELL_CLASS} max-w-[200px]`}>
          <span className="block truncate font-mono text-[12px]" title={item.endpoint}>{item.endpoint}</span>
        </td>
        <td className={BODY_CELL_CLASS}>
          {item.request_id
            ? <span className="block max-w-[120px] truncate font-mono text-[12px]" title={item.request_id}>{item.request_id}</span>
            : <span className="text-[var(--text-muted)]">—</span>}
        </td>
        <td className={`${BODY_CELL_CLASS} text-right`}>
          <button
            type="button"
            aria-pressed={selected}
            aria-label={`Details for ${item.error_class} at ${item.endpoint}`}
            onClick={() => void openDetails(item)}
            className="!min-h-[44px] rounded-lg border border-[var(--border-light)] px-3 text-[12px] font-bold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary,#00A3E0)] lg:!min-h-[32px]"
          >
            Details
          </button>
        </td>
      </tr>
    );
  };

  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-black text-[var(--text-primary)]">System errors</h2>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-[var(--text-muted)]">
            Review recent server failures and search by the reference shown when a save fails. Full diagnostic traces are available only to Admins.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void loadErrors(requestIdFilter)}
          disabled={loading}
          className="inline-flex min-h-10 items-center gap-2 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3.5 text-xs font-bold text-[var(--text-secondary)] transition hover:bg-[var(--bg-sunken)] disabled:opacity-60"
        >
          {loading ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />}
          Refresh
        </button>
      </header>

      <section className="glass-panel space-y-4 rounded-3xl p-4 shadow-sm sm:p-5">
        <form onSubmit={applyFilter} className="flex flex-col gap-2 sm:flex-row">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Filter by request reference</span>
            <Search size={16} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
            <input
              value={requestIdInput}
              onChange={(event) => setRequestIdInput(event.target.value)}
              placeholder="Paste a Reference ID to find its error"
              className="min-h-10 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] pl-9 pr-3 text-xs text-[var(--text-primary)] outline-none transition placeholder:text-[var(--text-muted)] focus:border-blue-500/50 focus:ring-2 focus:ring-blue-500/10"
            />
          </label>
          <button type="submit" className="inline-flex min-h-10 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-xs font-extrabold text-white transition hover:bg-blue-700">
            <Search size={14} /> Search
          </button>
          {requestIdFilter && (
            <button
              type="button"
              onClick={() => {
                setRequestIdInput('');
                setRequestIdFilter('');
                void loadErrors();
              }}
              className="inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-[var(--border-light)] px-3 text-xs font-bold text-[var(--text-secondary)] hover:bg-[var(--bg-sunken)]"
            >
              <X size={14} /> Clear
            </button>
          )}
        </form>

        {errorMessage && (
          <div role="alert" className="flex items-start gap-2.5 rounded-xl border border-rose-300 bg-rose-50 px-3.5 py-3 text-xs text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.85fr)]">
          <div className="min-w-0 space-y-2" aria-busy={loading}>
            {loading ? (
              <div role="status" className="flex min-h-36 items-center justify-center gap-2 text-xs font-semibold text-[var(--text-muted)]">
                <Loader2 size={17} className="animate-spin" /> Loading server errors…
              </div>
            ) : errors.length === 0 ? (
              <div className="flex min-h-36 flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--border-light)] px-5 text-center">
                <ShieldCheck size={22} className="text-emerald-500" />
                <p className="mt-2 text-sm font-bold text-[var(--text-primary)]">{requestIdFilter ? 'No error found for this reference' : 'No recent server errors'}</p>
                <p className="mt-1 max-w-sm text-[12px] leading-relaxed text-[var(--text-muted)]">
                  {requestIdFilter ? 'Check the reference and try again.' : 'New server failures will appear here with a reference you can search.'}
                </p>
              </div>
            ) : (
              <AdminTableShell
                tableLabel="Recent server errors"
                maxHeightClass="max-h-[560px]"
                minWidthClass="min-w-[720px]"
                footer={<TablePagination page={pagination.page} pageCount={pagination.pageCount} from={pagination.from} to={pagination.to} total={pagination.total} onPageChange={pagination.goTo} label="Server error pages" />}
              >
                <thead>
                  <tr>
                    <SortableHeaderCell label="Time" direction={directionFor(sort, 'time')} onSort={() => toggle('time')} />
                    <SortableHeaderCell label="Error class" direction={directionFor(sort, 'errorClass')} onSort={() => toggle('errorClass')} />
                    <SortableHeaderCell label="Method" direction={directionFor(sort, 'method')} onSort={() => toggle('method')} />
                    <SortableHeaderCell label="Endpoint" direction={directionFor(sort, 'endpoint')} onSort={() => toggle('endpoint')} />
                    <th scope="col" className={HEAD_CELL_CLASS}>Reference</th>
                    <th scope="col" className={`${HEAD_CELL_CLASS} text-right`}>Details</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-light)]">
                  {pagination.rows.map((item) => renderErrorRow(item))}
                </tbody>
              </AdminTableShell>
            )}
          </div>

          <aside className="min-h-48 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4" aria-label="Error details">
            {selectedError ? (
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[10px] font-black uppercase tracking-wider text-rose-600 dark:text-rose-300">Admin diagnostics</p>
                    <h3 className="mt-1 break-all text-sm font-black text-[var(--text-primary)]">{selectedError.error_class}</h3>
                  </div>
                  {loadingDetails && <Loader2 size={16} className="animate-spin text-blue-500" />}
                </div>
                {selectedError.request_id && (
                  <p className="break-all rounded-lg bg-[var(--bg-sunken)] px-2.5 py-2 font-mono text-[10px] text-[var(--text-secondary)]">
                    Reference: {selectedError.request_id}
                  </p>
                )}
                {selectedError.error_message && (
                  <div>
                    <p className="mb-1 text-[10px] font-extrabold uppercase tracking-wider text-[var(--text-muted)]">Message</p>
                    <p className="break-words rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] p-3 text-xs leading-relaxed text-[var(--text-primary)]">{selectedError.error_message}</p>
                  </div>
                )}
                {selectedError.stack_trace && (
                  <details className="group">
                    <summary className="flex min-h-9 cursor-pointer list-none items-center gap-2 text-xs font-bold text-blue-600 hover:text-blue-700 dark:text-blue-400">
                      <Activity size={14} /> Technical trace
                    </summary>
                    <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-slate-950 p-3 text-[10px] leading-relaxed text-slate-100">{selectedError.stack_trace}</pre>
                  </details>
                )}
              </div>
            ) : (
              <div className="flex h-full min-h-40 flex-col items-center justify-center text-center">
                <Activity size={22} className="text-blue-500/70" />
                <p className="mt-2 text-xs font-bold text-[var(--text-primary)]">Select an error to inspect it</p>
                <p className="mt-1 max-w-xs text-[11px] leading-relaxed text-[var(--text-muted)]">The technical trace is loaded on demand and visible only in this Admin workspace.</p>
              </div>
            )}
          </aside>
        </div>
      </section>
    </div>
  );
}
