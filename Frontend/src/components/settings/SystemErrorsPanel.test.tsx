import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SystemErrorsPanel } from './SystemErrorsPanel';

const { fetchWithRole } = vi.hoisted(() => ({ fetchWithRole: vi.fn() }));

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({ fetchWithRole }),
}));

const CLASSES = ['TimeoutError', 'ValueError', 'KeyError', 'ConnectionError'];
const METHODS = ['GET', 'POST', 'PUT'];

// 30 errors, newest first as the server sends them.
const ERRORS = Array.from({ length: 30 }, (_, index) => ({
  id: `err-${index}`,
  request_id: `REF-${String(index).padStart(3, '0')}`,
  endpoint: `/api/item/${index}`,
  method: METHODS[index % 3],
  error_class: CLASSES[(index * 3) % 4],
  occurred_at: new Date(Date.now() - (index + 1) * 3_600_000).toISOString(),
}));

function json(data: unknown, ok = true) {
  return { ok, status: ok ? 200 : 500, json: async () => (ok ? { success: true, data } : { detail: data }) };
}

function listUrls() {
  return fetchWithRole.mock.calls.map((call) => String(call[0])).filter((url) => url.includes('/api/settings/system-errors?'));
}

beforeEach(() => {
  fetchWithRole.mockReset();
  fetchWithRole.mockImplementation(async (url: string) => {
    if (url.includes('/api/settings/system-errors/err-')) {
      const id = url.split('/').pop();
      const item = ERRORS.find((error) => error.id === id);
      return json({ ...item, error_message: 'Stored message for the selected error', stack_trace: 'Traceback line' });
    }
    return json(ERRORS);
  });
});

/** The rows of the errors table, in display order. */
function tableRows() {
  return within(screen.getByRole('table', { name: 'Recent server errors' })).getAllByRole('row').slice(1);
}

describe('System errors table', () => {
  it('shows the errors as a table with the agreed columns', async () => {
    render(<SystemErrorsPanel />);
    expect(await screen.findByRole('table', { name: 'Recent server errors' })).toBeInTheDocument();
    for (const name of ['Time', 'Error class', 'Method', 'Endpoint']) {
      expect(screen.getByRole('columnheader', { name })).toBeInTheDocument();
    }
    expect(screen.getByRole('columnheader', { name: 'Reference' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Details' })).toBeInTheDocument();
  });

  it('shows 25 rows per page, with the range and the total', async () => {
    render(<SystemErrorsPanel />);
    await screen.findByRole('table', { name: 'Recent server errors' });
    expect(tableRows()).toHaveLength(25);
    expect(screen.getByText('Showing 1–25 of 30')).toBeInTheDocument();
  });

  it('keeps the received order until a header is clicked', async () => {
    render(<SystemErrorsPanel />);
    await screen.findByRole('table', { name: 'Recent server errors' });
    expect(tableRows()[0]).toHaveTextContent('/api/item/0');
    expect(screen.getByRole('columnheader', { name: 'Error class' })).toHaveAttribute('aria-sort', 'none');
  });

  it('sorts the whole list by Error class before paging', async () => {
    const user = userEvent.setup();
    render(<SystemErrorsPanel />);
    await screen.findByRole('table', { name: 'Recent server errors' });
    await user.click(screen.getByRole('button', { name: 'Error class' }));
    expect(screen.getByRole('columnheader', { name: 'Error class' })).toHaveAttribute('aria-sort', 'ascending');
    expect(tableRows()[0]).toHaveTextContent('ConnectionError');
  });

  it('sorts Time newest first when descending, and keeps the absolute time in the title', async () => {
    const user = userEvent.setup();
    render(<SystemErrorsPanel />);
    await screen.findByRole('table', { name: 'Recent server errors' });
    await user.click(screen.getByRole('button', { name: 'Time' }));
    await user.click(screen.getByRole('button', { name: 'Time' }));
    expect(tableRows()[0]).toHaveTextContent('/api/item/0');
    const time = tableRows()[0].querySelector('time');
    expect(time).toHaveAttribute('title');
    expect(time?.textContent).toMatch(/ago|less than|about|over|almost/);
  });

  it('moves to the next page and keeps the sort', async () => {
    const user = userEvent.setup();
    render(<SystemErrorsPanel />);
    await screen.findByRole('table', { name: 'Recent server errors' });
    await user.click(screen.getByRole('button', { name: 'Method' }));
    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('Showing 26–30 of 30')).toBeInTheDocument();
    expect(tableRows()).toHaveLength(5);
  });
});

describe('System errors details and search', () => {
  it('opens the existing details view from the row action', async () => {
    const user = userEvent.setup();
    render(<SystemErrorsPanel />);
    await screen.findByRole('table', { name: 'Recent server errors' });
    await user.click(screen.getByRole('button', { name: `Details for ${ERRORS[0].error_class} at /api/item/0` }));
    expect(await screen.findByText('Stored message for the selected error')).toBeInTheDocument();
    expect(fetchWithRole).toHaveBeenCalledWith(expect.stringContaining('/api/settings/system-errors/err-0'));
    expect(screen.getByRole('button', { name: `Details for ${ERRORS[0].error_class} at /api/item/0` })).toHaveAttribute('aria-pressed', 'true');
  });

  it('keeps the request-id search as the same request, with the same limit', async () => {
    const user = userEvent.setup();
    render(<SystemErrorsPanel />);
    await screen.findByRole('table', { name: 'Recent server errors' });
    expect(String(listUrls()[0])).toMatch(/system-errors\?limit=50$/);
    await user.type(screen.getByRole('textbox', { name: 'Filter by request reference' }), '  REF-007 ');
    await user.click(screen.getByRole('button', { name: 'Search' }));
    await waitFor(() => expect(listUrls().at(-1)).toMatch(/system-errors\?limit=50&request_id=REF-007$/));
  });

  it('clears the search back to the default request', async () => {
    const user = userEvent.setup();
    render(<SystemErrorsPanel />);
    await screen.findByRole('table', { name: 'Recent server errors' });
    await user.type(screen.getByRole('textbox', { name: 'Filter by request reference' }), 'REF-007');
    await user.click(screen.getByRole('button', { name: 'Search' }));
    await user.click(await screen.findByRole('button', { name: 'Clear' }));
    await waitFor(() => expect(listUrls().at(-1)).toMatch(/system-errors\?limit=50$/));
  });

  it('shows the empty message when the search finds nothing', async () => {
    const user = userEvent.setup();
    fetchWithRole.mockImplementation(async () => json([]));
    render(<SystemErrorsPanel />);
    expect(await screen.findByText('No recent server errors')).toBeInTheDocument();
    await user.type(screen.getByRole('textbox', { name: 'Filter by request reference' }), 'REF-999');
    await user.click(screen.getByRole('button', { name: 'Search' }));
    expect(await screen.findByText('No error found for this reference')).toBeInTheDocument();
  });

  it('shows the load error as an alert', async () => {
    fetchWithRole.mockImplementation(async () => json('Could not load system errors.', false));
    render(<SystemErrorsPanel />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not load system errors.');
  });
});
