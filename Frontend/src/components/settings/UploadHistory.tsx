import { useState, type ChangeEvent } from 'react';
import { FileSpreadsheet, Loader2, Trash2 } from 'lucide-react';
import type { ManagementUploadItem, UploadHistoryItem } from './types';
import { asArray, formatDate } from './uploadFormat';
import { AdminTableShell, TableEmptyRow, TableSkeletonRows } from './shell/AdminTableShell';
import { BODY_CELL_CLASS, BODY_ROW_CLASS, HEAD_CELL_CLASS } from './shell/adminTableClasses';
import { SortableHeaderCell } from './shell/SortableHeaderCell';
import { directionFor, useTableSort, type SortColumn } from './shell/useTableSort';

export interface UploadHistoryProps {
  items: UploadHistoryItem[];
  management?: boolean;
  loading?: boolean;
  busy: string | null | string[];
  onDelete: (item: UploadHistoryItem, management: boolean) => void;
  onBatchDelete?: (items: UploadHistoryItem[], management: boolean) => void;
}

type UploadSortKey = 'filename' | 'uploadedAt' | 'uploadedBy' | 'records';

interface Selection {
  /** The list the ids were chosen from. A reload hands over a new list, which drops the selection. */
  items: UploadHistoryItem[];
  ids: Set<string>;
}

const NO_SELECTION: ReadonlySet<string> = new Set();

function timestamp(value?: string | null): number | null {
  if (!value) return null;
  const time = Date.parse(value);
  return Number.isNaN(time) ? null : time;
}

/** The sortable columns. Scope has no sort, because a scope is a list of teams rather than one value. */
const UPLOAD_SORT_COLUMNS: SortColumn<UploadHistoryItem, UploadSortKey>[] = [
  { key: 'filename', value: (item) => item.filename ?? null },
  { key: 'uploadedAt', value: (item) => timestamp(item.uploaded_at) },
  { key: 'uploadedBy', value: (item) => item.uploaded_by ?? null },
  { key: 'records', value: (item) => item.record_count ?? null },
];

/**
 * One list of uploads with row selection and batch delete. Sorting changes only the display order. Selection, select-all
 * and batch delete read `items` exactly as they arrive, so sorting never changes which uploads are selected or deleted.
 */
export function UploadHistory({ items, management = false, loading = false, busy, onDelete, onBatchDelete }: UploadHistoryProps) {
  const [selection, setSelection] = useState<Selection>({ items, ids: new Set() });
  const [wasBatchDeleting, setWasBatchDeleting] = useState(false);
  const { rows: sortedItems, sort, toggle } = useTableSort(items, UPLOAD_SORT_COLUMNS);

  const batchIds = Array.isArray(busy) ? busy : [];
  const isBatchDeleting = Array.isArray(busy);
  // A batch request spends its selection when it finishes. This adjusts during render, the way React suggests for state that
  // resets with a change, so the rows keep their selection until the request is over.
  if (wasBatchDeleting !== isBatchDeleting) {
    setWasBatchDeleting(isBatchDeleting);
    if (!isBatchDeleting) setSelection({ items, ids: new Set() });
  }
  // While a batch runs, its ids stay selected even if a reload has replaced the list.
  const selectedIds = isBatchDeleting || selection.items === items ? selection.ids : NO_SELECTION;
  const setSelectedIds = (ids: Set<string>) => setSelection({ items, ids });

  const handleSelectAll = (e: ChangeEvent<HTMLInputElement>) => {
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
  };

  const columnCount = (onBatchDelete ? 1 : 0) + 4 + (management ? 0 : 1) + 1;
  const selectedCount = selectedIds.size;
  const countText = `${selectedCount} item${selectedCount > 1 ? 's' : ''}`;
  const selectionStatus = isBatchDeleting
    ? `Deleting ${batchIds.length} selected upload${batchIds.length > 1 ? 's' : ''}`
    : selectedCount > 0 ? `${countText} selected for deletion` : '';

  const selectionBar = onBatchDelete && selectedCount > 0 ? (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <span className="text-xs font-semibold text-rose-600 dark:text-rose-400">
        {countText} selected
      </span>
      <button
        onClick={handleBatchDelete}
        disabled={busy !== null}
        className="flex min-h-[44px] items-center gap-2 rounded-lg bg-rose-500 px-3 text-xs font-bold text-white transition-all hover:bg-rose-600 disabled:opacity-60 lg:!min-h-[32px]"
      >
        {isBatchDeleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
        Delete Selected
      </button>
    </div>
  ) : undefined;

  return (
    <>
      {onBatchDelete && <p aria-live="polite" className="sr-only">{selectionStatus}</p>}
      <AdminTableShell
        tableLabel={management ? 'Management template uploads' : 'Employee PMS uploads'}
        toolbar={selectionBar}
        busy={loading}
        maxHeightClass="max-h-80"
        minWidthClass="min-w-[700px]"
      >
        <thead>
          <tr>
            {onBatchDelete && (
              <th scope="col" className={`${HEAD_CELL_CLASS} w-10`}>
                <input
                  type="checkbox"
                  aria-label="Select all uploads"
                  disabled={busy !== null}
                  className="rounded border-[var(--border-light)] text-blue-600 focus:ring-blue-500"
                  checked={items.length > 0 && selectedCount === items.length}
                  onChange={handleSelectAll}
                />
              </th>
            )}
            <SortableHeaderCell label="File" direction={directionFor(sort, 'filename')} onSort={() => toggle('filename')} />
            <SortableHeaderCell label="Uploaded" direction={directionFor(sort, 'uploadedAt')} onSort={() => toggle('uploadedAt')} />
            <SortableHeaderCell label="Uploaded by" direction={directionFor(sort, 'uploadedBy')} onSort={() => toggle('uploadedBy')} />
            <th scope="col" className={HEAD_CELL_CLASS}>Scope</th>
            {!management && <SortableHeaderCell label="Records" direction={directionFor(sort, 'records')} onSort={() => toggle('records')} />}
            <th scope="col" className={`${HEAD_CELL_CLASS} text-right`}>Action</th>
          </tr>
        </thead>
        {loading ? (
          <TableSkeletonRows columns={columnCount} />
        ) : (
          <tbody className="divide-y divide-[var(--border-light)]">
            {sortedItems.map((item) => {
              const details = item as ManagementUploadItem;
              const isDeleting = busy === item.id || batchIds.includes(item.id);
              const teams = asArray(details.teams);
              const periods = asArray(details.periods);
              const name = item.filename || 'upload';
              return (
                <tr key={item.id} className={BODY_ROW_CLASS}>
                  {onBatchDelete && (
                    <td className={`${BODY_CELL_CLASS} w-10`}>
                      <input
                        type="checkbox"
                        aria-label={`Select ${name}`}
                        disabled={busy !== null}
                        className="rounded border-[var(--border-light)] text-blue-600 focus:ring-blue-500"
                        checked={selectedIds.has(item.id)}
                        onChange={(e) => handleSelectOne(item.id, e.target.checked)}
                      />
                    </td>
                  )}
                  <td className={`${BODY_CELL_CLASS} text-[var(--text-primary)]`}>
                    <p className="font-extrabold">{item.filename || 'Unnamed file'}</p>
                    {!management && (
                      <p className="mt-0.5 text-xs font-semibold text-[var(--text-muted)]">
                        One workbook · {item.team_count || teams.length || 0} teams
                      </p>
                    )}
                  </td>
                  <td className={BODY_CELL_CLASS}>{formatDate(item.uploaded_at)}</td>
                  <td className={BODY_CELL_CLASS}>
                    <span className="font-semibold">{item.uploaded_by || 'Unknown'}</span>
                  </td>
                  <td className={`${BODY_CELL_CLASS} max-w-[260px]`}>
                    <p className="truncate font-semibold" title={teams.join(', ')}>{teams.join(', ') || 'All teams'}</p>
                    <p className="mt-0.5 truncate text-xs text-[var(--text-muted)]" title={periods.join(', ')}>
                      {periods.join(', ') || 'No period detected'}
                    </p>
                  </td>
                  {!management && (
                    <td className={`${BODY_CELL_CLASS} font-extrabold tabular-nums text-[var(--text-primary)]`}>
                      {(item.record_count || 0).toLocaleString()}
                    </td>
                  )}
                  <td className={`${BODY_CELL_CLASS} text-right`}>
                    <button
                      aria-label={`Delete ${name}`}
                      disabled={Array.isArray(busy) || busy !== null}
                      onClick={() => onDelete(item, management)}
                      className="inline-flex min-h-[44px] !min-w-[44px] items-center justify-center rounded-lg text-rose-500 hover:bg-rose-500/10 disabled:opacity-40 transition-colors lg:!min-h-[32px] lg:!min-w-[32px]"
                    >
                      {isDeleting ? <Loader2 size={15} className="animate-spin text-rose-500" /> : <Trash2 size={14} />}
                    </button>
                  </td>
                </tr>
              );
            })}
            {!items.length && <TableEmptyRow colSpan={columnCount} icon={FileSpreadsheet} message="No upload history found." />}
          </tbody>
        )}
      </AdminTableShell>
    </>
  );
}
