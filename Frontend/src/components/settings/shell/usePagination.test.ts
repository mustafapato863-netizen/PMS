import { act, renderHook } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { paginate, usePagination } from './usePagination';

const ROWS = Array.from({ length: 60 }, (_, index) => index + 1);

describe('paginate', () => {
  it('returns the first page with the range it covers', () => {
    expect(paginate(ROWS, 25, 1)).toMatchObject({ page: 1, pageCount: 3, from: 1, to: 25, total: 60 });
    expect(paginate(ROWS, 25, 1).rows).toHaveLength(25);
  });

  it('returns a partial last page', () => {
    const last = paginate(ROWS, 25, 3);
    expect(last).toMatchObject({ page: 3, from: 51, to: 60, total: 60 });
    expect(last.rows[0]).toBe(51);
    expect(last.rows).toHaveLength(10);
  });

  it('falls back to page 1 for a page out of range', () => {
    expect(paginate(ROWS, 25, 9).page).toBe(1);
    expect(paginate(ROWS, 25, 0).page).toBe(1);
  });

  it('reports no range and one page for no rows', () => {
    expect(paginate([], 25, 1)).toMatchObject({ page: 1, pageCount: 1, from: 0, to: 0, total: 0, rows: [] });
  });
});

describe('usePagination', () => {
  it('moves between pages with goTo and clamps to the range', () => {
    const { result } = renderHook(() => usePagination(ROWS, 25, 'all'));
    act(() => result.current.goTo(2));
    expect(result.current.page).toBe(2);
    expect(result.current.rows[0]).toBe(26);
    act(() => result.current.goTo(99));
    expect(result.current.page).toBe(3);
    act(() => result.current.goTo(0));
    expect(result.current.page).toBe(1);
  });

  it('returns to page 1 when the reset key changes, such as a search or a filter', () => {
    const { result, rerender } = renderHook(({ resetKey }) => usePagination(ROWS, 25, resetKey), {
      initialProps: { resetKey: 'all' },
    });
    act(() => result.current.goTo(3));
    expect(result.current.page).toBe(3);
    rerender({ resetKey: 'search:ann' });
    expect(result.current.page).toBe(1);
  });

  it('returns to page 1 when the rows shrink below the current page, and stays there when they grow back', () => {
    const { result, rerender } = renderHook(({ rows }) => usePagination(rows, 25, 'all'), {
      initialProps: { rows: ROWS },
    });
    act(() => result.current.goTo(3));
    rerender({ rows: ROWS.slice(0, 20) });
    expect(result.current.page).toBe(1);
    rerender({ rows: ROWS });
    expect(result.current.page).toBe(1);
  });
});
