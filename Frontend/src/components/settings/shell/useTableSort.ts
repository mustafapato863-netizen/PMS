import { useCallback, useMemo, useState } from 'react';

export type SortDirection = 'asc' | 'desc';

/** The active sort, or null for the order the rows were received in. */
export type SortState<K extends string> = { key: K; direction: SortDirection } | null;

export type SortValue = string | number | boolean | null | undefined;

/** One sortable column. `value` returns the key for a row. Null, undefined and empty values always sort last. */
export type SortColumn<T, K extends string> = {
  key: K;
  value: (row: T) => SortValue;
};

function isEmpty(value: SortValue): value is null | undefined | '' {
  return value === null || value === undefined || value === '' || (typeof value === 'number' && Number.isNaN(value));
}

/** Compares two non-empty values. Numbers compare by value, and text compares case-insensitively with digits read as numbers. */
export function compareValues(a: SortValue, b: SortValue): number {
  if (typeof a === 'number' && typeof b === 'number') return a < b ? -1 : a > b ? 1 : 0;
  if (typeof a === 'boolean' && typeof b === 'boolean') return Number(a) - Number(b);
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
}

/**
 * Returns a sorted copy of the rows. The sort is stable: rows with equal keys keep the order they arrived in, in either
 * direction. Empty values are placed last whichever direction is chosen. With no active sort the rows keep their order.
 */
export function sortRows<T, K extends string>(rows: readonly T[], columns: readonly SortColumn<T, K>[], sort: SortState<K>): T[] {
  const column = sort ? columns.find((item) => item.key === sort.key) : undefined;
  if (!sort || !column) return [...rows];
  const direction = sort.direction === 'asc' ? 1 : -1;
  return rows
    .map((row, index) => ({ row, index, value: column.value(row) }))
    .sort((a, b) => {
      const aEmpty = isEmpty(a.value);
      const bEmpty = isEmpty(b.value);
      if (aEmpty || bEmpty) {
        if (aEmpty && bEmpty) return a.index - b.index;
        return aEmpty ? 1 : -1;
      }
      return compareValues(a.value, b.value) * direction || a.index - b.index;
    })
    .map((item) => item.row);
}

/**
 * A header click moves through three states: ascending, descending, then back to the received order. Clicking a
 * different column starts that column ascending.
 */
export function nextSort<K extends string>(current: SortState<K>, key: K): SortState<K> {
  if (!current || current.key !== key) return { key, direction: 'asc' };
  if (current.direction === 'asc') return { key, direction: 'desc' };
  return null;
}

/** The aria-sort value for a direction. */
export function ariaSortFor(direction: SortDirection | null): 'ascending' | 'descending' | 'none' {
  if (direction === 'asc') return 'ascending';
  if (direction === 'desc') return 'descending';
  return 'none';
}

/** The direction for one column, or null when another column is sorted or none is. */
export function directionFor<K extends string>(sort: SortState<K>, key: K): SortDirection | null {
  return sort && sort.key === key ? sort.direction : null;
}

/** Sorts rows client-side. Callers keep their own column list; a module-level list keeps the memo stable. */
export function useTableSort<T, K extends string>(rows: readonly T[], columns: readonly SortColumn<T, K>[], initial: SortState<K> = null) {
  const [sort, setSort] = useState<SortState<K>>(initial);
  const sortedRows = useMemo(() => sortRows(rows, columns, sort), [rows, columns, sort]);
  const toggle = useCallback((key: K) => setSort((current) => nextSort(current, key)), []);
  return { rows: sortedRows, sort, toggle, setSort };
}
