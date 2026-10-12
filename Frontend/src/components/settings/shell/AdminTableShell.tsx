import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';
import { BODY_CELL_CLASS, BODY_ROW_CLASS, TABLE_CLASS } from './adminTableClasses';

export type AdminTableShellProps = {
  /** Names the table for assistive technology. */
  tableLabel: string;
  /** Optional controls above the table, such as search and filters. */
  toolbar?: ReactNode;
  /** Optional controls below the table, such as pagination. */
  footer?: ReactNode;
  /** A maximum height for the body. The header stays visible while it scrolls. */
  maxHeightClass?: string;
  /** The table's minimum width. Narrower screens scroll horizontally inside the shell, never the page. */
  minWidthClass: string;
  /** The table's thead and tbody. */
  children: ReactNode;
  /** Set while the rows are loading, so assistive technology knows the table is changing. */
  busy?: boolean;
};

/**
 * One container for every Administration table: optional toolbar, a scroll area that scrolls both ways inside itself,
 * the table, and an optional footer.
 */
export function AdminTableShell({ tableLabel, toolbar, footer, maxHeightClass = '', minWidthClass, children, busy = false }: AdminTableShellProps) {
  return (
    <div className="min-w-0 overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)]">
      {toolbar && <div className="border-b border-[var(--border-light)] p-4">{toolbar}</div>}
      <div className={`min-w-0 overflow-auto overscroll-x-contain ${maxHeightClass}`} aria-busy={busy || undefined}>
        <table aria-label={tableLabel} className={`${TABLE_CLASS} ${minWidthClass}`}>
          {children}
        </table>
      </div>
      {footer && <div className="border-t border-[var(--border-light)]">{footer}</div>}
    </div>
  );
}

/** Placeholder rows while a table loads. They are decorative: the loading text is announced by the panel. */
export function TableSkeletonRows({ columns, rows = 3 }: { columns: number; rows?: number }) {
  return (
    <tbody aria-hidden="true" className="animate-pulse motion-reduce:animate-none">
      {Array.from({ length: rows }, (_, row) => (
        <tr key={row} className={BODY_ROW_CLASS}>
          {Array.from({ length: columns }, (_, column) => (
            <td key={column} className={BODY_CELL_CLASS}>
              <div className="h-3.5 w-3/4 rounded bg-[var(--border-light)]/60" />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}

/** A single row that says a table has nothing to show. */
export function TableEmptyRow({ colSpan, icon: Icon, message }: { colSpan: number; icon: LucideIcon; message: string }) {
  return (
    <tr>
      <td colSpan={colSpan} className="px-4 py-10 text-center text-[13px] text-[var(--text-muted)]">
        <div className="flex flex-col items-center justify-center gap-2">
          <Icon size={24} aria-hidden="true" className="opacity-50" />
          <p className="font-semibold">{message}</p>
        </div>
      </td>
    </tr>
  );
}
