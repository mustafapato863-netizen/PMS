import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
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

function renderCard(summary = testSummary()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter><EmployeesBelowTargetCard summary={summary} /></MemoryRouter>
    </QueryClientProvider>,
  );
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

  it('requests and renders eight scoped employees at a time, with working cursor navigation', async () => {
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
    expect(requestedUrl.searchParams.get('page_size')).toBe('8');
    expect(requestedUrl.searchParams.get('sort')).toBe('score_asc');

    fireEvent.click(within(card).getByRole('button', { name: 'Next page' }));
    expect(await within(card).findByText('Server Person 8')).toBeInTheDocument();
    expect(within(card).getAllByRole('link')).toHaveLength(1);
    expect(within(card).getByText(/Showing 9–9 of 9 · Page 2 of 2/)).toBeInTheDocument();

    fireEvent.click(within(card).getByRole('button', { name: 'Previous page' }));
    expect(await within(card).findByText('Server Person 0')).toBeInTheDocument();
    expect(within(card).getAllByRole('link')).toHaveLength(8);
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
