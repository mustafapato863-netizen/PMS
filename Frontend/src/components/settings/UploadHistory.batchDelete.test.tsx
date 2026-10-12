import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { UploadHistoryItem } from './types';
import { UploadHistory } from './UploadHistory';

const ITEMS: UploadHistoryItem[] = [
  { id: 'u1', filename: 'Outbound-July.xlsx', uploaded_at: '2026-07-03T09:00:00Z', uploaded_by: 'Dana', record_count: 120, team_count: 1, teams: ['Outbound'] },
  { id: 'u2', filename: 'Inbound-August.xlsx', uploaded_at: '2026-08-02T09:00:00Z', uploaded_by: 'Omar', record_count: 80, team_count: 1, teams: ['Inbound'] },
  { id: 'u3', filename: 'Sales-May.xlsx', uploaded_at: '2026-05-10T09:00:00Z', uploaded_by: 'Amal', record_count: 40, team_count: 1, teams: ['Sales'] },
];

type Busy = string | null | string[];

function renderHistory(busy: Busy, items: UploadHistoryItem[] = ITEMS) {
  const onDelete = vi.fn();
  const onBatchDelete = vi.fn();
  const view = render(<UploadHistory items={items} busy={busy} onDelete={onDelete} onBatchDelete={onBatchDelete} />);
  const table = screen.getByRole('table', { name: 'Employee PMS uploads' });
  return { ...view, table, onDelete, onBatchDelete };
}

function spinners(table: HTMLElement) {
  return table.querySelectorAll('svg.animate-spin');
}

describe('UploadHistory batch delete', () => {
  it('keeps the selection while a batch runs and reads the count through a live region', async () => {
    const user = userEvent.setup();
    const { table, onBatchDelete } = renderHistory(null);
    await user.click(within(table).getByRole('checkbox', { name: 'Select Outbound-July.xlsx' }));
    await user.click(within(table).getByRole('checkbox', { name: 'Select Sales-May.xlsx' }));
    expect(screen.getByText('2 items selected for deletion')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Delete Selected' }));
    expect(onBatchDelete).toHaveBeenCalledTimes(1);
    expect(screen.getByText('2 items selected')).toBeInTheDocument();
  });

  it('marks the rows it is deleting and disables selection and every delete control while a batch runs', () => {
    const { table } = renderHistory(['u1', 'u3']);

    expect(spinners(table)).toHaveLength(2);
    expect(within(table).getByRole('button', { name: 'Delete Outbound-July.xlsx' })).toBeDisabled();
    expect(within(table).getByRole('button', { name: 'Delete Inbound-August.xlsx' })).toBeDisabled();
    expect(within(table).getByRole('checkbox', { name: 'Select all uploads' })).toBeDisabled();
    expect(within(table).getByRole('checkbox', { name: 'Select Sales-May.xlsx' })).toBeDisabled();
  });

  it('disables Delete Selected while a batch runs and announces the deleting count', async () => {
    const user = userEvent.setup();
    const { table, rerender, onDelete, onBatchDelete } = renderHistory(null);
    await user.click(within(table).getByRole('checkbox', { name: 'Select Outbound-July.xlsx' }));
    await user.click(within(table).getByRole('checkbox', { name: 'Select Inbound-August.xlsx' }));

    rerender(<UploadHistory items={ITEMS} busy={['u1', 'u2']} onDelete={onDelete} onBatchDelete={onBatchDelete} />);

    expect(screen.getByRole('button', { name: 'Delete Selected' })).toBeDisabled();
    expect(screen.getByText('Deleting 2 selected uploads')).toBeInTheDocument();
  });

  it('clears the selection once the batch finishes', async () => {
    const user = userEvent.setup();
    const { table, rerender, onDelete, onBatchDelete } = renderHistory(null);
    await user.click(within(table).getByRole('checkbox', { name: 'Select Outbound-July.xlsx' }));
    rerender(<UploadHistory items={ITEMS} busy={['u1']} onDelete={onDelete} onBatchDelete={onBatchDelete} />);

    rerender(<UploadHistory items={ITEMS} busy={null} onDelete={onDelete} onBatchDelete={onBatchDelete} />);

    expect(screen.queryByRole('button', { name: 'Delete Selected' })).not.toBeInTheDocument();
    expect(within(table).getByRole('checkbox', { name: 'Select Outbound-July.xlsx' })).not.toBeChecked();
  });

  it('drops the selection when the list reloads, so an id that no longer exists is never selected', async () => {
    const user = userEvent.setup();
    const { table, rerender, onDelete, onBatchDelete } = renderHistory(null);
    await user.click(within(table).getByRole('checkbox', { name: 'Select Outbound-July.xlsx' }));
    expect(screen.getByText('1 item selected')).toBeInTheDocument();

    const reloaded = ITEMS.filter((item) => item.id !== 'u1');
    rerender(<UploadHistory items={reloaded} busy={null} onDelete={onDelete} onBatchDelete={onBatchDelete} />);

    expect(screen.queryByRole('button', { name: 'Delete Selected' })).not.toBeInTheDocument();
    expect(screen.queryByText('1 item selected')).not.toBeInTheDocument();
    expect(within(table).queryByRole('checkbox', { name: 'Select Outbound-July.xlsx' })).not.toBeInTheDocument();
  });

  it('keeps a selection on the same list when the list is only re-rendered', async () => {
    const user = userEvent.setup();
    const { table, rerender, onDelete, onBatchDelete } = renderHistory(null);
    await user.click(within(table).getByRole('checkbox', { name: 'Select Sales-May.xlsx' }));

    rerender(<UploadHistory items={ITEMS} busy={null} onDelete={onDelete} onBatchDelete={onBatchDelete} />);

    expect(screen.getByText('1 item selected')).toBeInTheDocument();
  });

  it('shows no selection controls and no live region without a batch handler', () => {
    render(<UploadHistory items={ITEMS} busy={null} onDelete={vi.fn()} />);
    const table = screen.getByRole('table', { name: 'Employee PMS uploads' });

    expect(within(table).queryByRole('checkbox')).not.toBeInTheDocument();
    expect(document.querySelector('[aria-live]')).toBeNull();
  });
});
