import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { compareValues, directionFor, nextSort, sortRows, useTableSort, type SortColumn } from './useTableSort';

type Row = { id: string; name: string | null; score: number | null; active: boolean; when: number | null };

// Received order: a, b, c, d, e, f.
const ROWS: Row[] = [
  { id: 'a', name: 'bravo', score: 10, active: true, when: 300 },
  { id: 'b', name: 'Alpha', score: null, active: false, when: null },
  { id: 'c', name: 'charlie', score: 10, active: true, when: 100 },
  { id: 'd', name: '', score: 2, active: false, when: 200 },
  { id: 'e', name: 'Item 10', score: 30, active: true, when: 200 },
  { id: 'f', name: 'Item 9', score: 4, active: false, when: 400 },
];

const COLUMNS: SortColumn<Row, 'name' | 'score' | 'active' | 'when' | 'unknown'>[] = [
  { key: 'name', value: (row) => row.name },
  { key: 'score', value: (row) => row.score },
  { key: 'active', value: (row) => row.active },
  { key: 'when', value: (row) => row.when },
];

const ids = (rows: Row[]) => rows.map((row) => row.id).join('');

describe('sortRows', () => {
  it('keeps the received order when no sort is active', () => {
    expect(ids(sortRows(ROWS, COLUMNS, null))).toBe('abcdef');
  });

  it('sorts strings case-insensitively, reads numbers inside text by value, and puts an empty name last', () => {
    expect(sortRows(ROWS, COLUMNS, { key: 'name', direction: 'asc' }).map((row) => row.name))
      .toEqual(['Alpha', 'bravo', 'charlie', 'Item 9', 'Item 10', '']);
  });

  it('reverses numbers for a descending sort and keeps null last', () => {
    expect(sortRows(ROWS, COLUMNS, { key: 'score', direction: 'desc' }).map((row) => row.score)).toEqual([30, 10, 10, 4, 2, null]);
  });

  it('keeps null last in an ascending sort too', () => {
    expect(sortRows(ROWS, COLUMNS, { key: 'score', direction: 'asc' }).map((row) => row.score)).toEqual([2, 4, 10, 10, 30, null]);
    expect(sortRows(ROWS, COLUMNS, { key: 'when', direction: 'asc' }).map((row) => row.when)).toEqual([100, 200, 200, 300, 400, null]);
  });

  it('is stable: equal keys keep the received order, ascending and descending', () => {
    // score 10 appears as a then c, so it stays a then c in both directions.
    expect(ids(sortRows(ROWS, COLUMNS, { key: 'score', direction: 'asc' }))).toBe('dfaceb');
    expect(ids(sortRows(ROWS, COLUMNS, { key: 'score', direction: 'desc' }))).toBe('eacfdb');
    // when 200 appears as d then e, so it stays d then e when descending.
    expect(ids(sortRows(ROWS, COLUMNS, { key: 'when', direction: 'desc' }))).toBe('fadecb');
    expect(ids(sortRows(ROWS, COLUMNS, { key: 'when', direction: 'asc' }))).toBe('cdeafb');
  });

  it('orders false before true for a boolean column, keeping ties in received order', () => {
    expect(ids(sortRows(ROWS, COLUMNS, { key: 'active', direction: 'asc' }))).toBe('bdface');
  });

  it('does not change the rows it was given', () => {
    const before = ROWS.map((row) => row.id).join('');
    sortRows(ROWS, COLUMNS, { key: 'name', direction: 'desc' });
    expect(ROWS.map((row) => row.id).join('')).toBe(before);
  });

  it('ignores a sort on a column that does not exist', () => {
    expect(ids(sortRows(ROWS, COLUMNS, { key: 'unknown', direction: 'asc' }))).toBe('abcdef');
  });
});

describe('compareValues', () => {
  it('compares numbers by value, including infinity', () => {
    expect(compareValues(2, 10)).toBeLessThan(0);
    expect(compareValues(Number.POSITIVE_INFINITY, 5)).toBeGreaterThan(0);
    expect(compareValues(Number.POSITIVE_INFINITY, Number.POSITIVE_INFINITY)).toBe(0);
  });

  it('compares strings without regard to case, and reads a number inside text by value', () => {
    expect(compareValues('item 9', 'Item 10')).toBeLessThan(0);
    expect(compareValues('alpha', 'Alpha')).toBe(0);
  });

  it('orders false before true', () => {
    expect(compareValues(false, true)).toBeLessThan(0);
  });
});

describe('nextSort', () => {
  it('starts a new column ascending', () => {
    expect(nextSort(null, 'name')).toEqual({ key: 'name', direction: 'asc' });
    expect(nextSort({ key: 'name', direction: 'desc' }, 'score')).toEqual({ key: 'score', direction: 'asc' });
  });

  it('cycles the same column ascending, descending, then back to the received order', () => {
    const first = nextSort(null, 'name');
    const second = nextSort(first, 'name');
    expect(second).toEqual({ key: 'name', direction: 'desc' });
    expect(nextSort(second, 'name')).toBeNull();
  });

  it('reports the direction for one column only', () => {
    expect(directionFor({ key: 'name', direction: 'asc' }, 'name')).toBe('asc');
    expect(directionFor({ key: 'name', direction: 'asc' }, 'score')).toBeNull();
    expect(directionFor(null, 'name')).toBeNull();
  });
});

describe('useTableSort', () => {
  it('starts in the received order, and sorts after a header toggle', () => {
    const { result } = renderHook(() => useTableSort(ROWS, COLUMNS));
    expect(ids(result.current.rows)).toBe('abcdef');
    act(() => result.current.toggle('score'));
    expect(result.current.sort).toEqual({ key: 'score', direction: 'asc' });
    expect(result.current.rows.map((row) => row.score)).toEqual([2, 4, 10, 10, 30, null]);
  });

  it('toggles through ascending, descending and back to the received order', () => {
    const { result } = renderHook(() => useTableSort(ROWS, COLUMNS));
    act(() => result.current.toggle('name'));
    expect(result.current.sort?.direction).toBe('asc');
    act(() => result.current.toggle('name'));
    expect(result.current.sort?.direction).toBe('desc');
    act(() => result.current.toggle('name'));
    expect(result.current.sort).toBeNull();
    expect(ids(result.current.rows)).toBe('abcdef');
  });

  it('accepts an initial sort', () => {
    const { result } = renderHook(() => useTableSort(ROWS, COLUMNS, { key: 'when', direction: 'desc' }));
    expect(result.current.rows[0].when).toBe(400);
  });
});
