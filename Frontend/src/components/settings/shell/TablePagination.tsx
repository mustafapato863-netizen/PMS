export type TablePaginationProps = {
  page: number;
  pageCount: number;
  from: number;
  to: number;
  total: number;
  onPageChange: (page: number) => void;
  /** Names the pagination landmark, for example "Users pages". */
  label: string;
};

const BUTTON_CLASS = 'min-h-[44px] rounded-lg border border-[var(--border-light)] px-3 text-xs font-bold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary,#00A3E0)] disabled:cursor-not-allowed disabled:opacity-50 lg:!min-h-[32px]';

/** Previous and Next, with the range shown. It renders nothing when all rows fit on one page. */
export function TablePagination({ page, pageCount, from, to, total, onPageChange, label }: TablePaginationProps) {
  if (pageCount <= 1) return null;
  return (
    <nav aria-label={label} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <p className="text-xs text-[var(--text-secondary)]">Showing {from}–{to} of {total}</p>
      <div className="flex items-center gap-2">
        <button type="button" onClick={() => onPageChange(page - 1)} disabled={page <= 1} className={BUTTON_CLASS}>Previous</button>
        <span className="text-xs text-[var(--text-muted)]">Page {page} of {pageCount}</span>
        <button type="button" onClick={() => onPageChange(page + 1)} disabled={page >= pageCount} className={BUTTON_CLASS}>Next</button>
      </div>
    </nav>
  );
}
