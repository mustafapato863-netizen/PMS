import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TablePagination } from './TablePagination';

function renderPagination(overrides: Partial<Parameters<typeof TablePagination>[0]> = {}) {
  const onPageChange = vi.fn();
  render(<TablePagination page={1} pageCount={3} from={1} to={25} total={60} onPageChange={onPageChange} label="Users pages" {...overrides} />);
  return { onPageChange };
}

describe('TablePagination', () => {
  it('shows the range and the total', () => {
    renderPagination();
    expect(screen.getByText('Showing 1–25 of 60')).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Users pages' })).toBeInTheDocument();
  });

  it('renders nothing when all rows fit on one page', () => {
    renderPagination({ pageCount: 1, from: 1, to: 7, total: 7 });
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    expect(screen.queryByText(/Showing/)).not.toBeInTheDocument();
  });

  it('disables Previous on the first page and Next on the last', () => {
    const { onPageChange } = renderPagination();
    expect(screen.getByRole('button', { name: 'Previous' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it('disables Next on the last page and moves back with Previous', () => {
    const { onPageChange } = renderPagination({ page: 3, from: 51, to: 60 });
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Previous' }));
    expect(onPageChange).toHaveBeenCalledWith(2);
  });

  it('shows the current page of the total', () => {
    renderPagination({ page: 2, from: 26, to: 50 });
    expect(screen.getByText('Page 2 of 3')).toBeInTheDocument();
  });
});
