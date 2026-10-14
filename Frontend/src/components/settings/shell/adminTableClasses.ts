/**
 * Classes shared by every Administration table, so the header, cells and rows look the same everywhere.
 * Sizes are explicit: text-xs is 12px in this theme, and touch targets below lg use min-h-[44px] (the ≤768px floor in index.css matches it).
 */
export const TABLE_CLASS = 'w-full border-collapse text-left text-[13px] text-[var(--text-primary)]';

export const HEAD_CELL_CLASS = 'sticky top-0 z-10 whitespace-nowrap border-b border-[var(--border-light)] bg-[var(--bg-sunken)] px-4 py-3 text-left text-xs font-semibold uppercase tracking-normal text-[var(--text-muted)]';

export const HEAD_BUTTON_CLASS = 'inline-flex min-h-[44px] items-center gap-1.5 rounded-lg px-1 font-semibold uppercase tracking-normal text-[var(--text-muted)] hover:text-[var(--text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary,#00A3E0)] lg:!min-h-[32px]';

/** A body row has a fixed minimum height and a hover state. There is no zebra striping. */
export const BODY_ROW_CLASS = 'transition-colors hover:bg-[var(--bg-sunken)]/60';

export const BODY_CELL_CLASS = 'h-[52px] px-4 py-2.5 align-middle text-[13px] text-[var(--text-secondary)]';
