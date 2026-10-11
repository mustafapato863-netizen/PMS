import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DataManagementPanel } from './DataManagementPanel';

const { fetchWithRole, trackJob } = vi.hoisted(() => ({
  fetchWithRole: vi.fn(),
  trackJob: vi.fn(),
}));

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({ fetchWithRole }),
}));

vi.mock('../../context/uploadJobState', () => ({
  useUploadJob: () => ({ activeJobId: null, trackJob }),
}));

vi.mock('../../hooks/usePerformanceData', () => ({
  refreshPerformanceData: vi.fn(),
}));

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return render(<DataManagementPanel />, { wrapper });
}

function historyResponse() {
  return { ok: true, json: async () => ({ success: true, data: [] }) };
}

describe('DataManagementPanel upload notices', () => {
  beforeEach(() => {
    fetchWithRole.mockReset();
    trackJob.mockReset();
    fetchWithRole.mockImplementation(async (url: string) => {
      if (String(url).includes('/api/uploads/pms')) {
        return {
          ok: true,
          json: async () => ({
            success: true,
            data: {
              records_imported: 2,
              teams: ['Outbound'],
              warnings: [{ code: 'duplicate_employee_month', message: 'One row was kept.' }],
              column_warnings: [
                {
                  sheet: 'Outbound',
                  code: 'unmapped_columns',
                  headers: ['Side Note', '<img src=x onerror=alert(1)>'],
                  truncated: false,
                },
              ],
            },
          }),
        };
      }
      return historyResponse();
    });
  });

  it('shows bounded header names as text after a synchronous upload', async () => {
    const user = userEvent.setup();
    const { container } = renderPanel();
    const input = container.querySelector('input[type="file"]');
    expect(input).not.toBeNull();
    await user.upload(input as HTMLInputElement, new File(['sheet'], 'ordinary.xlsx'));

    expect(await screen.findByText('Processed 2 records across 1 team sheets.')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Columns not mapped to scoring' })).toBeInTheDocument();
    expect(screen.getByText('These columns do not change your scoring rules. Review their names in Excel.')).toBeInTheDocument();
    expect(screen.getByText('Outbound: Side Note')).toBeInTheDocument();
    expect(screen.getByText('Outbound: <img src=x onerror=alert(1)>')).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
    expect(trackJob).not.toHaveBeenCalled();
  });

  it('shows the same notice when a target conflict returns a report', async () => {
    fetchWithRole.mockImplementation(async (url: string) => {
      if (String(url).includes('/api/uploads/pms')) {
        return {
          ok: false,
          json: async () => ({
            success: false,
            detail: {
              message: "Outbound columns 'T.Quality%' and 'T.Quality Target' both contain values that do not match. Neither value was used as the quality target.",
              report: {
                column_warnings: [
                  {
                    sheet: 'Outbound',
                    code: 'ambiguous_alias',
                    headers: ['T.Quality%', 'T.Quality Target'],
                    truncated: false,
                  },
                ],
              },
            },
          }),
        };
      }
      return historyResponse();
    });
    const user = userEvent.setup();
    const { container } = renderPanel();
    await user.upload(container.querySelector('input[type="file"]') as HTMLInputElement, new File(['sheet'], 'ordinary.xlsx'));

    expect(await screen.findByRole('status')).toHaveTextContent('Neither value was used as the quality target.');
    expect(screen.getByRole('heading', { name: 'Conflicting target columns' })).toBeInTheDocument();
    expect(screen.getByText('These column names disagree. Neither value was used as the quality target. Review their names in Excel.')).toBeInTheDocument();
    expect(screen.getByText('Outbound: T.Quality Target')).toBeInTheDocument();
  });

  it('tracks a background job without treating the queue response as a finished sheet notice', async () => {
    fetchWithRole.mockImplementation(async (url: string) => {
      if (String(url).includes('/api/uploads/pms')) {
        return {
          ok: true,
          json: async () => ({ success: true, data: { job_id: 'job-1', status: 'queued' } }),
        };
      }
      return historyResponse();
    });
    const user = userEvent.setup();
    const { container } = renderPanel();
    await user.upload(container.querySelector('input[type="file"]') as HTMLInputElement, new File(['sheet'], 'ordinary.xlsx'));

    await waitFor(() => expect(trackJob).toHaveBeenCalledWith('job-1'));
    expect(screen.queryByText(/Processed/)).not.toBeInTheDocument();
  });
});
