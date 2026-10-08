import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiFetch } from '../../../lib/apiClient';
import { composeExecutiveSummary, type ExecRecord } from '../../../features/executive/compose';
import EmployeesBelowTargetCard from './EmployeesBelowTargetCard';

vi.mock('../../../lib/apiClient', () => ({ apiFetch: vi.fn() }));

const mockedApiFetch = vi.mocked(apiFetch);

function serverRecord(index: number, performanceLevel = 'Managerial') {
  return {
    employee_id: `server-${index}`,
    employee_name: `Server Person ${index}`,
    team: 'Coding',
    region: 'UAE',
    performance_level: performanceLevel,
    position: 'Manager',
    score: 70 + index,
  };
}

function testSummary(performanceLevel = 'Managerial') {
  const period = { key: '2026-08', month: 'August', year: 2026 };
  const records: ExecRecord[] = [
    { employeeId: 'summary-only', name: 'Summary Person', team: 'Coding', region: 'UAE', position: 'Manager', level: performanceLevel, branches: ['dubai'], score: 88, period, kpis: [] },
  ];
  return composeExecutiveSummary({
    view: 'function',
    functionName: 'RCM',
    role: 'Admin',
    records,
    filters: { region: 'UAE', branch: 'dubai', performanceLevel },
    today: new Date(2026, 8, 1),
  });
}

function renderCard(summary = testSummary(), client = new QueryClient({ defaultOptions: { queries: { retry: false } } })) {
  const content = (value: typeof summary) => (
    <QueryClientProvider client={client}>
      <MemoryRouter><EmployeesBelowTargetCard summary={value} /></MemoryRouter>
    </QueryClientProvider>
  );
  return { ...render(content(summary)), client, content };
}

describe('EmployeesBelowTargetCard', () => {
  beforeEach(() => {
    mockedApiFetch.mockReset();
    mockedApiFetch.mockImplementation(async (endpoint) => {
      const params = new URL(String(endpoint), 'http://localhost').searchParams;
      const cursor = params.get('cursor');
      return {
        success: true,
        data: {
          items: cursor ? [serverRecord(8)] : Array.from({ length: 8 }, (_, index) => serverRecord(index)),
          page_size: 8,
          next_cursor: cursor ? null : 'next-page-cursor',
          has_more: !cursor,
          total: 9,
        },
      };
    });
  });

  it('caches all bounded batches on first load and switches eight-row pages without requests or loading flashes', async () => {
    renderCard();
    const card = screen.getByRole('region', { name: 'Employees below 90%' });

    expect(await within(card).findByText('Server Person 0')).toBeInTheDocument();
    expect(within(card).getAllByRole('link')).toHaveLength(8);
    expect(within(card).queryByText('Summary Person')).not.toBeInTheDocument();
    expect(within(card).getByText(/9 people in the selected scope/)).toBeInTheDocument();
    expect(within(card).getByText(/Showing 1–8 of 9 · Page 1 of 2/)).toBeInTheDocument();
    expect(within(card).getByRole('link', { name: /Server Person 0/ })).toHaveAttribute(
      'href',
      '/employee/server-0?month=August&year=2026&performance_level=Managerial',
    );

    const requestedUrl = new URL(String(mockedApiFetch.mock.calls[0][0]), 'http://localhost');
    expect(requestedUrl.searchParams.get('period')).toBe('2026-08');
    expect(requestedUrl.searchParams.get('team')).toBe('RCM');
    expect(requestedUrl.searchParams.get('region')).toBe('UAE');
    expect(requestedUrl.searchParams.get('branch')).toBe('dubai');
    expect(requestedUrl.searchParams.get('performance_level')).toBe('Managerial');
    expect(requestedUrl.searchParams.get('score_lt')).toBe('90');
    expect(requestedUrl.searchParams.get('page_size')).toBe('100');
    expect(requestedUrl.searchParams.get('include_total')).toBe('false');
    expect(requestedUrl.searchParams.get('sort')).toBe('score_asc');
    expect(mockedApiFetch).toHaveBeenCalledTimes(2);
    expect(new URL(String(mockedApiFetch.mock.calls[1][0]), 'http://localhost').searchParams.get('cursor')).toBe('next-page-cursor');

    fireEvent.click(within(card).getByRole('button', { name: 'Next page' }));
    expect(await within(card).findByText('Server Person 8')).toBeInTheDocument();
    expect(within(card).getAllByRole('link')).toHaveLength(1);
    expect(within(card).queryByRole('status')).not.toBeInTheDocument();
    expect(mockedApiFetch).toHaveBeenCalledTimes(2);
    expect(within(card).getByText(/Showing 9–9 of 9 · Page 2 of 2/)).toBeInTheDocument();

    fireEvent.click(within(card).getByRole('button', { name: 'Previous page' }));
    expect(await within(card).findByText('Server Person 0')).toBeInTheDocument();
    expect(within(card).getAllByRole('link')).toHaveLength(8);
    expect(within(card).queryByRole('status')).not.toBeInTheDocument();
    expect(mockedApiFetch).toHaveBeenCalledTimes(2);
  });

  it('reuses the full cached roster when the card is reopened', async () => {
    const { client, unmount } = renderCard();
    expect(await screen.findByText('Server Person 0')).toBeInTheDocument();
    unmount();
    renderCard(testSummary(), client);

    expect(screen.getByText('Server Person 0')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(screen.getByText('Server Person 8')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    expect(mockedApiFetch).toHaveBeenCalledTimes(2);
  });

  it('isolates filters, resets the page, and reuses the original scope cache when filters are cleared', async () => {
    const summary = testSummary();
    const { rerender, content } = renderCard(summary);
    expect(await screen.findByText('Server Person 0')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    expect(screen.getByText('Server Person 8')).toBeInTheDocument();

    mockedApiFetch.mockImplementationOnce(async () => ({
      success: true,
      data: { items: [{ ...serverRecord(0), employee_name: 'Sharjah Person' }], page_size: 100, next_cursor: null, has_more: false, total: null },
    }));
    rerender(content({ ...summary, scope: { ...summary.scope, branch: 'sharjah' } }));
    expect(screen.queryByText('Server Person 8')).not.toBeInTheDocument();
    expect(await screen.findByText('Sharjah Person')).toBeInTheDocument();
    expect(new URL(String(mockedApiFetch.mock.calls[2][0]), 'http://localhost').searchParams.get('branch')).toBe('sharjah');

    rerender(content(summary));
    expect(screen.getByText('Server Person 0')).toBeInTheDocument();
    expect(screen.queryByText('Sharjah Person')).not.toBeInTheDocument();
    expect(screen.getByText(/Page 1 of 2/)).toBeInTheDocument();
    expect(mockedApiFetch).toHaveBeenCalledTimes(3);
  });

  it('keeps cached rows visible during performance invalidation and clamps the page after the roster shrinks', async () => {
    const { client } = renderCard();
    expect(await screen.findByText('Server Person 0')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    const refreshed = {
      success: true,
      data: { items: [serverRecord(0)], page_size: 100, next_cursor: null, has_more: false, total: null },
    };
    let finishRefresh: (value: typeof refreshed) => void = () => {};
    mockedApiFetch.mockReturnValueOnce(new Promise<typeof refreshed>((resolve) => { finishRefresh = resolve; }));
    act(() => { void client.invalidateQueries({ queryKey: ['performance'] }); });

    expect(screen.getByText('Server Person 8')).toBeInTheDocument();
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    await act(async () => { finishRefresh(refreshed); });
    expect(await screen.findByText('Server Person 0')).toBeInTheDocument();
    expect(screen.getByText(/1 person in the selected scope/)).toBeInTheDocument();
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
  });

  it('reports a failed later batch instead of showing an incomplete cached roster', async () => {
    mockedApiFetch.mockImplementationOnce(async () => ({
      success: true,
      data: { items: [serverRecord(0)], page_size: 100, next_cursor: 'later', has_more: true, total: null },
    }));
    mockedApiFetch.mockRejectedValueOnce(new Error('Roster request failed'));
    renderCard();

    expect(await screen.findByRole('alert')).toHaveTextContent('Roster request failed');
    expect(screen.queryByText(/0 people in the selected scope/)).not.toBeInTheDocument();
    expect(screen.getByText(/Employee list unavailable/)).toBeInTheDocument();
    expect(screen.queryByText('Server Person 0')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByText('Server Person 0')).toBeInTheDocument();
    expect(screen.getByText(/9 people in the selected scope/)).toBeInTheDocument();
  });

  it('opens a Corporate-level person in their own BSC while preserving the selected branch', async () => {
    mockedApiFetch.mockImplementationOnce(async () => ({
      success: true,
      data: {
        items: [serverRecord(0, 'Corporate')],
        page_size: 8,
        next_cursor: null,
        has_more: false,
        total: 1,
      },
    }));

    renderCard(testSummary('Corporate'));

    expect(await screen.findByText('Server Person 0')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Server Person 0/ })).toHaveAttribute(
      'href',
      '/team/coding?performance_level=Corporate&month=August&year=2026&employee_ids=server-0&branch=dubai',
    );
    expect(screen.getByText(/Corporate-level names open their BSC/)).toBeInTheDocument();
  });
});
