import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { UploadHistoryItem } from './types';
import { UploadHistory } from './UploadHistory';

// Received order. Coding-June has no uploader and no record count, so it sorts last in those columns.
const ITEMS: UploadHistoryItem[] = [
  { id: 'u1', filename: 'Outbound-July.xlsx', uploaded_at: '2026-07-03T09:00:00Z', uploaded_by: 'Dana', record_count: 120, team_count: 2, teams: ['Outbound'] },
  { id: 'u2', filename: 'Inbound-August.xlsx', uploaded_at: '2026-08-02T09:00:00Z', uploaded_by: 'Omar', record_count: 80, team_count: 1, teams: ['Inbound'] },
  { id: 'u3', filename: 'Coding-June.xlsx', uploaded_at: '2026-06-01T09:00:00Z', uploaded_by: null, record_count: null },
  { id: 'u4', filename: 'Sales-May.xlsx', uploaded_at: '2026-05-10T09:00:00Z', uploaded_by: 'Amal', record_count: 40, team_count: 1, teams: ['Sales'] },
  { id: 'u5', filename: 'CSR-April.xlsx', uploaded_at: '2026-04-15T09:00:00Z', uploaded_by: 'Dana', record_count: 300, team_count: 1, teams: ['CSR'] },
  { id: 'u6', filename: 'Pharmacy-March.xlsx', uploaded_at: '2026-03-20T09:00:00Z', uploaded_by: 'Omar', record_count: 15, team_count: 1, teams: ['Pharmacy'] },
  { id: 'u7', filename: 'Call-Center-Feb.xlsx', uploaded_at: '2026-02-11T09:00:00Z', uploaded_by: 'Amal', record_count: 90, team_count: 1, teams: ['Call Center'] },
  { id: 'u8', filename: 'Pre-Approvals-Jan.xlsx', uploaded_at: '2026-01-09T09:00:00Z', uploaded_by: 'Dana', record_count: 60, team_count: 1, teams: ['Pre-Approvals'] },
];

const RECEIVED_NAMES = ITEMS.map((item) => item.filename);

function renderHistory(overrides: Partial<Parameters<typeof UploadHistory>[0]> = {}) {
  const onDelete = vi.fn();
  const onBatchDelete = vi.fn();
  render(<UploadHistory items={ITEMS} busy={null} onDelete={onDelete} onBatchDelete={onBatchDelete} {...overrides} />);
  return { onDelete, onBatchDelete };
}

/** The filenames in display order. The first row is the header. */
function rowNames() {
  return screen.getAllByRole('row').slice(1).map((row) => row.querySelector('p.font-extrabold')?.textContent ?? '');
}

function checkedNames() {
  return ITEMS.filter((item) => (screen.getByRole('checkbox', { name: `Select ${item.filename}` }) as HTMLInputElement).checked)
    .map((item) => item.id);
}

describe('UploadHistory order and sorting', () => {
  it('keeps the received order until a header is clicked', () => {
    renderHistory();
    expect(rowNames()).toEqual(RECEIVED_NAMES);
    expect(screen.getByRole('columnheader', { name: 'File' })).toHaveAttribute('aria-sort', 'none');
  });

  it('sorts by File ascending, then descending, then back to the received order', async () => {
    const user = userEvent.setup();
    renderHistory();
    await user.click(screen.getByRole('button', { name: 'File' }));
    expect(screen.getByRole('columnheader', { name: 'File' })).toHaveAttribute('aria-sort', 'ascending');
    expect(rowNames()[0]).toBe('Call-Center-Feb.xlsx');
    await user.click(screen.getByRole('button', { name: 'File' }));
    expect(screen.getByRole('columnheader', { name: 'File' })).toHaveAttribute('aria-sort', 'descending');
    expect(rowNames()[0]).toBe('Sales-May.xlsx');
    await user.click(screen.getByRole('button', { name: 'File' }));
    expect(rowNames()).toEqual(RECEIVED_NAMES);
  });

  it('sorts Uploaded by with an empty uploader last in both directions', async () => {
    const user = userEvent.setup();
    renderHistory();
    await user.click(screen.getByRole('button', { name: 'Uploaded by' }));
    expect(rowNames().at(-1)).toBe('Coding-June.xlsx');
    await user.click(screen.getByRole('button', { name: 'Uploaded by' }));
    expect(rowNames().at(-1)).toBe('Coding-June.xlsx');
  });

  it('shows Records only for the employee list', () => {
    renderHistory({ management: true });
    expect(screen.queryByRole('columnheader', { name: 'Records' })).not.toBeInTheDocument();
  });
});

describe('UploadHistory selection', () => {
  it('sorting does not change which uploads are selected', async () => {
    const user = userEvent.setup();
    renderHistory();
    await user.click(screen.getByRole('checkbox', { name: 'Select Coding-June.xlsx' }));
    await user.click(screen.getByRole('checkbox', { name: 'Select Outbound-July.xlsx' }));
    expect(screen.getByText('2 items selected')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Records' }));
    await user.click(screen.getByRole('button', { name: 'Records' }));
    expect(checkedNames()).toEqual(['u1', 'u3']);
    expect(screen.getByText('2 items selected')).toBeInTheDocument();
  });

  it('select-all still selects every row, including when the rows are sorted', async () => {
    const user = userEvent.setup();
    renderHistory();
    await user.click(screen.getByRole('button', { name: 'File' }));
    await user.click(screen.getByRole('checkbox', { name: 'Select all uploads' }));
    expect(screen.getByText('8 items selected')).toBeInTheDocument();
    expect(checkedNames()).toHaveLength(8);
  });

  it('batch delete receives the same items, in their received order, whatever the display order', async () => {
    const user = userEvent.setup();
    const { onBatchDelete } = renderHistory();
    await user.click(screen.getByRole('button', { name: 'File' }));
    await user.click(screen.getByRole('checkbox', { name: 'Select Sales-May.xlsx' }));
    await user.click(screen.getByRole('checkbox', { name: 'Select Inbound-August.xlsx' }));
    await user.click(screen.getByRole('button', { name: 'Delete Selected' }));
    expect(onBatchDelete).toHaveBeenCalledTimes(1);
    const [received, management] = onBatchDelete.mock.calls[0];
    expect(received.map((item: UploadHistoryItem) => item.id)).toEqual(['u2', 'u4']);
    expect(management).toBe(false);
  });

  it('per-row delete passes the item and the list kind, unchanged by sorting', async () => {
    const user = userEvent.setup();
    const { onDelete } = renderHistory({ management: true });
    await user.click(screen.getByRole('button', { name: 'Uploaded' }));
    await user.click(screen.getByRole('button', { name: 'Delete Inbound-August.xlsx' }));
    expect(onDelete).toHaveBeenCalledWith(ITEMS[1], true);
  });
});

describe('UploadHistory states', () => {
  it('shows placeholder rows and no uploads while loading', () => {
    const { container } = render(<UploadHistory items={[]} loading busy={null} onDelete={vi.fn()} />);
    expect(screen.queryByText('No upload history found.')).not.toBeInTheDocument();
    expect(container.querySelector('tbody[aria-hidden="true"]')).not.toBeNull();
    expect(screen.queryByRole('button', { name: /^Delete / })).not.toBeInTheDocument();
  });

  it('says so when there are no uploads', () => {
    renderHistory({ items: [] });
    expect(screen.getByText('No upload history found.')).toBeInTheDocument();
  });

  it('names the table for assistive technology', () => {
    renderHistory({ management: true });
    expect(screen.getByRole('table', { name: 'Management template uploads' })).toBeInTheDocument();
  });
});
