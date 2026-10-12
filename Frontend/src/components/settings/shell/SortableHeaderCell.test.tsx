import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SortableHeaderCell } from './SortableHeaderCell';
import { ariaSortFor } from './useTableSort';

function renderHeader(direction: 'asc' | 'desc' | null, onSort = vi.fn()) {
  render(
    <table>
      <thead>
        <tr>
          <SortableHeaderCell label="Username" direction={direction} onSort={onSort} />
        </tr>
      </thead>
    </table>,
  );
  return { onSort };
}

describe('SortableHeaderCell', () => {
  it('is a column header with a button named by the column label', () => {
    renderHeader(null);
    const header = screen.getByRole('columnheader', { name: 'Username' });
    expect(header.tagName).toBe('TH');
    expect(header).toHaveAttribute('scope', 'col');
    expect(screen.getByRole('button', { name: 'Username' })).toBeInTheDocument();
  });

  it('reports aria-sort as none, ascending or descending', () => {
    renderHeader(null);
    expect(screen.getByRole('columnheader', { name: 'Username' })).toHaveAttribute('aria-sort', 'none');
  });

  it('reports ascending and descending as aria-sort values', () => {
    const { unmount } = render(<table><thead><tr><SortableHeaderCell label="Name" direction="asc" onSort={vi.fn()} /></tr></thead></table>);
    expect(screen.getByRole('columnheader', { name: 'Name' })).toHaveAttribute('aria-sort', 'ascending');
    unmount();
    render(<table><thead><tr><SortableHeaderCell label="Name" direction="desc" onSort={vi.fn()} /></tr></thead></table>);
    expect(screen.getByRole('columnheader', { name: 'Name' })).toHaveAttribute('aria-sort', 'descending');
  });

  it('calls onSort when the button is pressed', () => {
    const { onSort } = renderHeader(null);
    fireEvent.click(screen.getByRole('button', { name: 'Username' }));
    expect(onSort).toHaveBeenCalledTimes(1);
  });

  it('marks the icon as decorative, so the name comes from the label alone', () => {
    renderHeader('asc');
    const button = screen.getByRole('button', { name: 'Username' });
    expect(button.querySelector('svg')).toHaveAttribute('aria-hidden', 'true');
  });

  it('maps a direction to its aria-sort value', () => {
    expect(ariaSortFor('asc')).toBe('ascending');
    expect(ariaSortFor('desc')).toBe('descending');
    expect(ariaSortFor(null)).toBe('none');
  });
});
