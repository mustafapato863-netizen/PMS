import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DataManagementPanel } from './DataManagementPanel';

const { fetchWithRole } = vi.hoisted(() => ({ fetchWithRole: vi.fn() }));

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({ fetchWithRole }),
}));

vi.mock('../../context/uploadJobState', () => ({
  useUploadJob: () => ({ activeJobId: null, trackJob: vi.fn() }),
}));

vi.mock('../../hooks/usePerformanceData', () => ({
  refreshPerformanceData: vi.fn(),
}));

const MANAGEMENT = [
  { id: 'm1', filename: 'Scorecard-June.xlsx', uploaded_at: '2026-06-05T09:00:00Z', uploaded_by: 'Omar', teams: ['Outbound'], periods: ['June'] },
  { id: 'm2', filename: 'Scorecard-May.xlsx', uploaded_at: '2026-05-06T09:00:00Z', uploaded_by: 'Dana', teams: ['Inbound'], periods: ['May'] },
];

/** Both batches have removed rows in the results, so only failed_ids can say that one was not removed. */
const RESULTS = [
  { upload_batch_id: 'm1', config_rows_deleted: 3, snapshot_rows_deleted: 1, history_rows_deleted: 0 },
  { upload_batch_id: 'm2', config_rows_deleted: 2, snapshot_rows_deleted: 0, history_rows_deleted: 0 },
];

let batchBody: Record<string, unknown>;

beforeEach(() => {
  fetchWithRole.mockReset();
  fetchWithRole.mockImplementation(async (url: string) => {
    const path = String(url);
    if (path.endsWith('/management-kpi-config/uploads/batch-delete')) {
      return { ok: true, status: 200, json: async () => batchBody };
    }
    if (path.endsWith('/management-kpi-config/uploads')) {
      return { ok: true, status: 200, json: async () => ({ success: true, data: MANAGEMENT }) };
    }
    return { ok: true, status: 200, json: async () => ({ success: true, data: [] }) };
  });
});

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  return render(<DataManagementPanel />, { wrapper });
}

async function deleteBothManagementBatches() {
  const user = userEvent.setup();
  renderPanel();
  const table = await screen.findByRole('table', { name: 'Management template uploads' });
  const section = table.closest('section') as HTMLElement;
  await user.click(within(table).getByRole('checkbox', { name: 'Select all uploads' }));
  await user.click(within(section).getByRole('button', { name: 'Delete Selected' }));
  await user.click(within(screen.getByRole('alertdialog')).getByRole('button', { name: 'Delete 2 uploads' }));
  return screen.findByRole('status');
}

describe('DataManagementPanel with failed_ids from the server', () => {
  it('trusts failed_ids over the results: a batch named there is not removed', async () => {
    batchBody = { success: true, data: RESULTS, failed_ids: ['m2'], message: 'Deleted 1 of 2 management upload batches. 1 could not be deleted.' };

    const notice = await deleteBothManagementBatches();

    expect(notice).toHaveTextContent('Deleted 1 of 2 management uploads. 1 not deleted: “Scorecard-May.xlsx”.');
    expect(notice).toHaveAttribute('role', 'status');
  });

  it('reports a full success when failed_ids is present and empty', async () => {
    batchBody = { success: true, data: RESULTS, failed_ids: [], message: 'Deleted 2 of 2 management upload batches.' };

    const notice = await deleteBothManagementBatches();

    expect(notice).toHaveTextContent('Deleted 2 management uploads.');
  });
});
