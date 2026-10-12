import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { refreshPerformanceData } from '../../hooks/usePerformanceData';
import { RateLimitError } from '../../lib/rateLimit';
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

interface Row {
  id: string;
  filename: string;
  uploaded_at: string;
  uploaded_by: string;
  record_count?: number;
  team_count?: number;
  teams?: string[];
  periods?: string[];
}

type BatchReply = { status: number; body: unknown } | Error;

const EMPLOYEE_NAMES = ['Outbound-July.xlsx', 'Inbound-August.xlsx', 'Sales-May.xlsx'];
const MANAGEMENT_NAMES = ['Scorecard-June.xlsx', 'Scorecard-May.xlsx'];

let employeeRows: Row[];
let managementRows: Row[];
let batchCalls: Array<{ url: string; body: { upload_ids: string[] } }>;
let getCounts: { employee: number; management: number };
let batchReply: (url: string, body: { upload_ids: string[] }) => Promise<BatchReply>;

function rowsFrom(names: string[], prefix: string): Row[] {
  return names.map((filename, index) => ({
    id: `${prefix}${index + 1}`,
    filename,
    uploaded_at: `2026-0${index + 1}-10T09:00:00Z`,
    uploaded_by: 'Dana',
    record_count: 10 * (index + 1),
    team_count: 1,
    teams: ['Outbound'],
    periods: ['July'],
  }));
}

function jsonResponse(status: number, body: unknown) {
  return { ok: status < 400, status, json: async () => body };
}

beforeEach(() => {
  employeeRows = rowsFrom(EMPLOYEE_NAMES, 'e');
  managementRows = rowsFrom(MANAGEMENT_NAMES, 'm');
  batchCalls = [];
  getCounts = { employee: 0, management: 0 };
  batchReply = async () => ({ status: 200, body: { success: true, data: {} } });
  fetchWithRole.mockReset();
  vi.mocked(refreshPerformanceData).mockClear();
  fetchWithRole.mockImplementation(async (url: string, init?: RequestInit) => {
    const path = String(url);
    if (path.endsWith('/api/uploads/batch-delete')) {
      const body = JSON.parse(String(init?.body)) as { upload_ids: string[] };
      batchCalls.push({ url: path, body });
      const reply = await batchReply(path, body);
      if (reply instanceof Error) throw reply;
      return jsonResponse(reply.status, reply.body);
    }
    if (path.endsWith('/management-kpi-config/uploads/batch-delete')) {
      const body = JSON.parse(String(init?.body)) as { upload_ids: string[] };
      batchCalls.push({ url: path, body });
      const reply = await batchReply(path, body);
      if (reply instanceof Error) throw reply;
      return jsonResponse(reply.status, reply.body);
    }
    if (path.endsWith('/api/uploads/')) {
      getCounts.employee += 1;
      return jsonResponse(200, { success: true, data: employeeRows });
    }
    if (path.endsWith('/management-kpi-config/uploads')) {
      getCounts.management += 1;
      return jsonResponse(200, { success: true, data: managementRows });
    }
    return jsonResponse(200, { success: true, data: [] });
  });
});

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<DataManagementPanel />, { wrapper });
}

/** The table for one list, and the section that holds its toolbar and Delete Selected button. */
function list(name: 'Employee PMS uploads' | 'Management template uploads') {
  const table = screen.getByRole('table', { name });
  const section = table.closest('section') as HTMLElement;
  return { table, section };
}

async function selectNamed(user: ReturnType<typeof userEvent.setup>, table: HTMLElement, names: string[]) {
  for (const name of names) {
    await user.click(within(table).getByRole('checkbox', { name: `Select ${name}` }));
  }
}

async function openConfirmation(user: ReturnType<typeof userEvent.setup>, section: HTMLElement) {
  await user.click(within(section).getByRole('button', { name: 'Delete Selected' }));
  return screen.getByRole('alertdialog');
}

describe('DataManagementPanel batch delete', () => {
  it('sends the selected employee ids, in list order, to the employee batch endpoint', async () => {
    const user = userEvent.setup();
    renderPanel();
    const { table, section } = list('Employee PMS uploads');
    await screen.findByRole('checkbox', { name: 'Select Outbound-July.xlsx' });
    await selectNamed(user, table, ['Sales-May.xlsx', 'Outbound-July.xlsx']);

    await openConfirmation(user, section);
    await user.click(screen.getByRole('button', { name: 'Delete 2 uploads' }));

    await waitFor(() => expect(batchCalls).toHaveLength(1));
    expect(batchCalls[0]).toEqual({ url: expect.stringMatching(/\/api\/uploads\/batch-delete$/), body: { upload_ids: ['e1', 'e3'] } });
    expect(fetchWithRole).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/uploads\/batch-delete$/),
      expect.objectContaining({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ upload_ids: ['e1', 'e3'] }) }),
    );
  });

  it('sends the selected management ids to the management batch endpoint', async () => {
    const user = userEvent.setup();
    renderPanel();
    const { table, section } = list('Management template uploads');
    await screen.findByRole('checkbox', { name: 'Select Scorecard-May.xlsx' });
    await selectNamed(user, table, ['Scorecard-June.xlsx', 'Scorecard-May.xlsx']);

    await openConfirmation(user, section);
    await user.click(screen.getByRole('button', { name: 'Delete 2 uploads' }));

    await waitFor(() => expect(batchCalls).toHaveLength(1));
    expect(batchCalls[0]).toEqual({
      url: expect.stringMatching(/\/team-management\/management-kpi-config\/uploads\/batch-delete$/),
      body: { upload_ids: ['m1', 'm2'] },
    });
  });

  it('asks first, names the files, and sends nothing when the user keeps them', async () => {
    const user = userEvent.setup();
    renderPanel();
    const { table, section } = list('Employee PMS uploads');
    await screen.findByRole('checkbox', { name: 'Select Outbound-July.xlsx' });
    await selectNamed(user, table, ['Outbound-July.xlsx', 'Inbound-August.xlsx']);

    const dialog = await openConfirmation(user, section);
    expect(dialog).toHaveTextContent('Delete 2 employee uploads?');
    expect(dialog).toHaveTextContent('The records imported from these files are removed. This cannot be undone.');
    expect(within(dialog).getByText('Outbound-July.xlsx')).toBeInTheDocument();
    expect(within(dialog).getByText('Inbound-August.xlsx')).toBeInTheDocument();
    expect(batchCalls).toHaveLength(0);

    await user.click(within(dialog).getByRole('button', { name: 'Keep uploads' }));

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(batchCalls).toHaveLength(0);
    expect(within(section).getByText('2 items selected')).toBeInTheDocument();
  });

  it('lists five file names and then how many more', async () => {
    const user = userEvent.setup();
    employeeRows = rowsFrom(['A-1.xlsx', 'A-2.xlsx', 'A-3.xlsx', 'A-4.xlsx', 'A-5.xlsx', 'A-6.xlsx', 'A-7.xlsx'], 'e');
    renderPanel();
    const { table, section } = list('Employee PMS uploads');
    await screen.findByRole('checkbox', { name: 'Select A-1.xlsx' });
    await user.click(within(table).getByRole('checkbox', { name: 'Select all uploads' }));

    const dialog = await openConfirmation(user, section);
    expect(dialog).toHaveTextContent('Delete 7 employee uploads?');
    expect(within(dialog).getByText('A-5.xlsx')).toBeInTheDocument();
    expect(within(dialog).queryByText('A-6.xlsx')).not.toBeInTheDocument();
    expect(within(dialog).getByText('and 2 more')).toBeInTheDocument();
  });

  it('blocks more than 100 selected uploads before any request, and keeps the selection', async () => {
    const user = userEvent.setup();
    employeeRows = rowsFrom(Array.from({ length: 101 }, (_, index) => `Bulk-${index + 1}.xlsx`), 'e');
    renderPanel();
    const { table, section } = list('Employee PMS uploads');
    await screen.findByRole('checkbox', { name: 'Select Bulk-1.xlsx' });
    await user.click(within(table).getByRole('checkbox', { name: 'Select all uploads' }));
    await user.click(within(section).getByRole('button', { name: 'Delete Selected' }));

    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(batchCalls).toHaveLength(0);
    expect(screen.getByRole('status')).toHaveTextContent(
      'Batch delete takes up to 100 uploads at a time. You selected 101. Clear some selections, then delete again.',
    );
    expect(within(section).getByText('101 items selected')).toBeInTheDocument();
    // Rendering 101 rows and selecting them all takes several seconds under a full parallel run. The budget is this test's only.
  }, 15_000);

  it('disables the selection, the delete buttons and a second submit while the request runs', async () => {
    const user = userEvent.setup();
    let finish: () => void = () => undefined;
    batchReply = () => new Promise((resolve) => {
      finish = () => resolve({ status: 200, body: { success: true, data: { missing_ids: [] } } });
    });
    renderPanel();
    const { table, section } = list('Employee PMS uploads');
    await screen.findByRole('checkbox', { name: 'Select Outbound-July.xlsx' });
    await selectNamed(user, table, ['Outbound-July.xlsx', 'Sales-May.xlsx']);
    const dialog = await openConfirmation(user, section);

    await user.click(within(dialog).getByRole('button', { name: 'Delete 2 uploads' }));

    await waitFor(() => expect(batchCalls).toHaveLength(1));
    expect(within(section).getByRole('button', { name: 'Delete Selected' })).toBeDisabled();
    expect(within(table).getByRole('checkbox', { name: 'Select all uploads' })).toBeDisabled();
    expect(within(table).getByRole('checkbox', { name: 'Select Outbound-July.xlsx' })).toBeDisabled();
    expect(within(table).getByRole('button', { name: 'Delete Outbound-July.xlsx' })).toBeDisabled();
    expect(within(table).getByRole('button', { name: 'Delete Sales-May.xlsx' })).toBeDisabled();
    expect(within(dialog).getByRole('button', { name: 'Delete 2 uploads' })).toBeDisabled();
    expect(within(section).getByText('Deleting 2 selected uploads')).toBeInTheDocument();

    finish();
    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    expect(batchCalls).toHaveLength(1);
  });

  it('shows a full-success notice with the count, clears the selection and reloads both lists', async () => {
    const user = userEvent.setup();
    renderPanel();
    const { table, section } = list('Employee PMS uploads');
    await screen.findByRole('checkbox', { name: 'Select Outbound-July.xlsx' });
    await selectNamed(user, table, ['Outbound-July.xlsx', 'Inbound-August.xlsx']);
    const before = { ...getCounts };
    batchReply = async () => {
      employeeRows = employeeRows.filter((row) => row.id === 'e3');
      return { status: 200, body: { success: true, data: { requested: 2, uploads_deleted: 2, performance_deleted: 4, missing_ids: [] } } };
    };

    const dialog = await openConfirmation(user, section);
    await user.click(within(dialog).getByRole('button', { name: 'Delete 2 uploads' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Deleted 2 uploads and refreshed performance data.');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(within(section).queryByText(/items selected/)).not.toBeInTheDocument();
    expect(within(section).queryByRole('button', { name: 'Delete Selected' })).not.toBeInTheDocument();
    expect(refreshPerformanceData).toHaveBeenCalled();
    expect(getCounts.employee).toBeGreaterThan(before.employee);
    expect(getCounts.management).toBeGreaterThan(before.management);
    await waitFor(() => expect(within(table).queryByRole('checkbox', { name: 'Select Outbound-July.xlsx' })).not.toBeInTheDocument());
  });

  it('reports a management success in its own words and reloads the management list', async () => {
    const user = userEvent.setup();
    renderPanel();
    const { table, section } = list('Management template uploads');
    await screen.findByRole('checkbox', { name: 'Select Scorecard-June.xlsx' });
    await selectNamed(user, table, ['Scorecard-June.xlsx']);
    const before = getCounts.management;
    batchReply = async () => {
      managementRows = [];
      return {
        status: 200,
        body: { success: true, data: [{ upload_batch_id: 'm1', config_rows_deleted: 3, snapshot_rows_deleted: 1, history_rows_deleted: 0 }] },
      };
    };

    const dialog = await openConfirmation(user, section);
    await user.click(within(dialog).getByRole('button', { name: 'Delete 1 upload' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Deleted 1 management upload.');
    expect(getCounts.management).toBeGreaterThan(before);
  });

  it('says how many were deleted and how many were not when the employee endpoint reports missing ids', async () => {
    const user = userEvent.setup();
    renderPanel();
    const { table, section } = list('Employee PMS uploads');
    await screen.findByRole('checkbox', { name: 'Select Outbound-July.xlsx' });
    await selectNamed(user, table, ['Outbound-July.xlsx', 'Inbound-August.xlsx']);
    batchReply = async () => ({
      status: 200,
      body: { success: true, data: { requested: 2, uploads_deleted: 1, performance_deleted: 2, missing_ids: ['e2'] } },
    });

    const dialog = await openConfirmation(user, section);
    await user.click(within(dialog).getByRole('button', { name: 'Delete 2 uploads' }));

    const notice = await screen.findByRole('status');
    expect(notice).toHaveTextContent('Deleted 1 of 2 uploads and refreshed performance data. 1 not deleted: “Inbound-August.xlsx”.');
    expect(notice).not.toHaveTextContent(/^Deleted 2 /);
    expect(refreshPerformanceData).toHaveBeenCalled();
  });

  it('says how many were deleted and how many were not when only some management batches were removed', async () => {
    const user = userEvent.setup();
    renderPanel();
    const { table, section } = list('Management template uploads');
    await screen.findByRole('checkbox', { name: 'Select Scorecard-June.xlsx' });
    await selectNamed(user, table, ['Scorecard-June.xlsx', 'Scorecard-May.xlsx']);
    batchReply = async () => ({
      status: 200,
      body: { success: true, data: [{ upload_batch_id: 'm1', config_rows_deleted: 2, snapshot_rows_deleted: 0, history_rows_deleted: 0 }] },
    });

    const dialog = await openConfirmation(user, section);
    await user.click(within(dialog).getByRole('button', { name: 'Delete 2 uploads' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Deleted 1 of 2 management uploads. 1 not deleted: “Scorecard-May.xlsx”.');
  });

  it('shows a management batch that removed nothing as a failure, not a success', async () => {
    const user = userEvent.setup();
    renderPanel();
    const { table, section } = list('Management template uploads');
    await screen.findByRole('checkbox', { name: 'Select Scorecard-June.xlsx' });
    await selectNamed(user, table, ['Scorecard-June.xlsx', 'Scorecard-May.xlsx']);
    batchReply = async () => ({ status: 200, body: { success: true, data: [] } });

    const dialog = await openConfirmation(user, section);
    await user.click(within(dialog).getByRole('button', { name: 'Delete 2 uploads' }));

    expect(await screen.findByRole('status')).toHaveTextContent(
      'None of the 2 management uploads were deleted: “Scorecard-June.xlsx”, “Scorecard-May.xlsx”.',
    );
  });

  it('shows the server message on failure, deletes nothing locally, and still reloads', async () => {
    const user = userEvent.setup();
    renderPanel();
    const { table, section } = list('Employee PMS uploads');
    await screen.findByRole('checkbox', { name: 'Select Outbound-July.xlsx' });
    await selectNamed(user, table, ['Outbound-July.xlsx']);
    const before = getCounts.employee;
    batchReply = async () => ({
      status: 500,
      body: { success: false, detail: 'Failed to batch delete uploads. Check the server logs using the request ID.' },
    });

    const dialog = await openConfirmation(user, section);
    await user.click(within(dialog).getByRole('button', { name: 'Delete 1 upload' }));

    expect(await screen.findByRole('status')).toHaveTextContent('Failed to batch delete uploads. Check the server logs using the request ID.');
    expect(getCounts.employee).toBeGreaterThan(before);
    expect(within(table).getByRole('button', { name: 'Delete Outbound-July.xlsx' })).toBeInTheDocument();
    expect(within(table).getByRole('button', { name: 'Delete Inbound-August.xlsx' })).toBeInTheDocument();
  });

  it('shows no message for a rate-limited batch, and clears the notice of the one before it', async () => {
    const user = userEvent.setup();
    renderPanel();
    const { table, section } = list('Employee PMS uploads');
    await screen.findByRole('checkbox', { name: 'Select Outbound-July.xlsx' });
    await selectNamed(user, table, ['Outbound-July.xlsx']);
    batchReply = async () => ({ status: 500, body: { success: false, detail: 'Failed to batch delete uploads.' } });
    await user.click(within(await openConfirmation(user, section)).getByRole('button', { name: 'Delete 1 upload' }));
    expect(await screen.findByRole('status')).toHaveTextContent('Failed to batch delete uploads.');

    // The failed batch cleared the selection, so the next one is chosen again.
    await selectNamed(user, table, ['Outbound-July.xlsx', 'Inbound-August.xlsx']);
    batchReply = async () => new RateLimitError(7);
    await user.click(within(await openConfirmation(user, section)).getByRole('button', { name: 'Delete 2 uploads' }));

    await waitFor(() => expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument());
    await waitFor(() => expect(batchCalls).toHaveLength(2));
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });

  it('returns focus to Delete Selected when the user keeps the uploads', async () => {
    const user = userEvent.setup();
    renderPanel();
    const { table, section } = list('Employee PMS uploads');
    await screen.findByRole('checkbox', { name: 'Select Outbound-July.xlsx' });
    await selectNamed(user, table, ['Outbound-July.xlsx']);
    const dialog = await openConfirmation(user, section);

    await user.click(within(dialog).getByRole('button', { name: 'Keep uploads' }));

    expect(within(section).getByRole('button', { name: 'Delete Selected' })).toHaveFocus();
  });

  it('moves focus to the list select-all control once a batch finishes', async () => {
    const user = userEvent.setup();
    renderPanel();
    const { table, section } = list('Employee PMS uploads');
    await screen.findByRole('checkbox', { name: 'Select Outbound-July.xlsx' });
    await selectNamed(user, table, ['Outbound-July.xlsx']);
    const dialog = await openConfirmation(user, section);

    await user.click(within(dialog).getByRole('button', { name: 'Delete 1 upload' }));

    await screen.findByRole('status');
    // Focus moves after the lists have reloaded, so the notice can appear first.
    await waitFor(() => expect(within(table).getByRole('checkbox', { name: 'Select all uploads' })).toHaveFocus());
  });
});
