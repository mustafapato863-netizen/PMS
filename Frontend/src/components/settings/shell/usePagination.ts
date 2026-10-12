import { useMemo, useState } from 'react';

export type PageSlice<T> = {
  rows: T[];
  /** The 1-based page shown. */
  page: number;
  pageCount: number;
  /** The 1-based position of the first and last row on this page. Both are 0 when there are no rows. */
  from: number;
  to: number;
  total: number;
};

/** Pure: one page of rows. A page outside the range falls back to page 1. */
export function paginate<T>(rows: readonly T[], pageSize: number, requestedPage: number): PageSlice<T> {
  const total = rows.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const page = requestedPage >= 1 && requestedPage <= pageCount ? requestedPage : 1;
  const start = (page - 1) * pageSize;
  const pageRows = rows.slice(start, start + pageSize);
  return { rows: pageRows, page, pageCount, from: total === 0 ? 0 : start + 1, to: start + pageRows.length, total };
}

/**
 * Pagination with the page kept in state. A change to `resetKey` (a search, a filter or a sort) returns to page 1, and so
 * does a row set that shrinks below the current page, which the state records as soon as it happens.
 */
export function usePagination<T>(rows: readonly T[], pageSize: number, resetKey: string) {
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const [state, setState] = useState({ key: resetKey, page: 1 });

  // React's pattern for state that depends on props: adjust during render, so the next render already sees page 1.
  if (state.key !== resetKey || state.page > pageCount) {
    setState({ key: resetKey, page: 1 });
  }

  const requested = state.key === resetKey && state.page <= pageCount ? state.page : 1;
  const slice = useMemo(() => paginate(rows, pageSize, requested), [rows, pageSize, requested]);

  const goTo = (page: number) => setState({ key: resetKey, page: Math.min(Math.max(1, page), pageCount) });

  return { ...slice, goTo };
}
