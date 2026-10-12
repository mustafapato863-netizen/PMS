import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AdminOverview } from './AdminOverview';

const mocks = vi.hoisted(() => ({ fetchWithRole: vi.fn() }));
const clock = vi.hoisted(() => ({ now: Date.parse('2026-10-12T12:00:00Z') }));

vi.mock('../../../context/RoleContext', () => ({
  useUserRole: () => ({ role: 'Admin', fetchWithRole: mocks.fetchWithRole }),
}));

// Pins "now" for the 24-hour window. Every other export is the real module.
vi.mock('./adminOverviewData', async (importOriginal) => ({
  ...(await importOriginal<typeof import('./adminOverviewData')>()),
  currentTime: () => clock.now,
}));

type Route = 'uploads' | 'management' | 'users' | 'errors';
type Reply = () => Promise<Response> | Response;

let replies: Record<Route, Reply>;

function json(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as unknown as Response;
}

function routeOf(url: string): Route | null {
  if (url.includes('management-kpi-config/uploads')) return 'management';
  if (url.endsWith('/api/uploads/')) return 'uploads';
  if (url.endsWith('/api/users/')) return 'users';
  if (url.includes('/api/settings/system-errors')) return 'errors';
  return null;
}

const ok = (data: unknown): Reply => () => json({ success: true, data });
const failing: Reply = () => json({ success: false, message: 'Request failed' }, 500);
const hanging: Reply = () => new Promise<Response>(() => {});

/** Every area empty and healthy, unless a test overrides it. */
function defaultReplies(): Record<Route, Reply> {
  return { uploads: ok([]), management: ok([]), users: ok([]), errors: ok([]) };
}

function setReplies(overrides: Partial<Record<Route, Reply>>) {
  replies = { ...defaultReplies(), ...overrides };
}

const hoursAgo = (hours: number) => new Date(clock.now - hours * 3_600_000).toISOString();
const daysAgo = (days: number) => hoursAgo(days * 24);

function renderOverview() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <AdminOverview />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function card(title: string) {
  return screen.getByRole('heading', { level: 3, name: title }).closest('article') as HTMLElement;
}

function requestedUrls() {
  return mocks.fetchWithRole.mock.calls.map((call) => String(call[0]));
}

beforeEach(() => {
  mocks.fetchWithRole.mockReset();
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const route = routeOf(String(url));
    if (!route) throw new Error(`Unexpected request: ${url}`);
    return replies[route]();
  });
  setReplies({});
});

describe('AdminOverview navigation', () => {
  it('shows one navigation card for each of the four areas', () => {
    renderOverview();
    const list = screen.getByRole('region', { name: 'Areas' }).querySelector('ul');
    expect(list).not.toBeNull();
    const cards = within(list as HTMLElement).getAllByRole('article');
    expect(cards).toHaveLength(4);
    for (const title of ['Data', 'Evaluation', 'Access', 'System']) {
      expect(screen.getByRole('heading', { level: 3, name: title })).toBeInTheDocument();
    }
  });

  it('links each card to its section with a named action', async () => {
    renderOverview();
    const expected: Array<[string, string]> = [
      ['Open data uploads', '/settings/data'],
      ['Open evaluation settings', '/settings/evaluation'],
      ['Manage users', '/settings/users'],
      ['Review system errors', '/settings/system-errors'],
    ];
    for (const [name, href] of expected) {
      expect(screen.getByRole('link', { name })).toHaveAttribute('href', href);
    }
    await screen.findByText('Nothing needs attention.');
  });

  it('says what each area manages', async () => {
    renderOverview();
    expect(screen.getByText(/workbooks, and back up or restore corrective action records/)).toBeInTheDocument();
    expect(screen.getByText(/monthly targets, weights and direction/)).toBeInTheDocument();
    expect(screen.getByText(/user accounts, their roles/)).toBeInTheDocument();
    expect(screen.getByText(/recent server failures/)).toBeInTheDocument();
    await screen.findByText('Nothing needs attention.');
  });
});

describe('AdminOverview populated cards', () => {
  it('shows the latest upload with its date, uploader, status and record count', async () => {
    const uploadedAt = daysAgo(2);
    setReplies({
      uploads: ok([{ id: 'u1', filename: 'PMS_Jan.xlsx', uploaded_at: uploadedAt, uploaded_by: 'Sara', status: 'success', record_count: 1234 }]),
    });
    renderOverview();
    const data = card('Data');
    const when = await within(data).findByText(/Uploaded .* ago/);
    expect(when.closest('time')).toHaveAttribute('title', new Date(uploadedAt).toLocaleString());
    expect(within(data).getByText('PMS_Jan.xlsx · by Sara')).toBeInTheDocument();
    expect(within(data).getByText('Status success')).toBeInTheDocument();
    expect(within(data).getByText(`${(1234).toLocaleString()} records`)).toBeInTheDocument();
    expect(within(data).getByText('Info')).toBeInTheDocument();
  });

  it('uses the most recent upload across the employee and management lists', async () => {
    setReplies({
      uploads: ok([{ id: 'e1', filename: 'Employees.xlsx', uploaded_at: daysAgo(9), uploaded_by: 'Sara', status: 'success', record_count: 10 }]),
      management: ok([{ id: 'm1', filename: 'Template.xlsx', uploaded_at: daysAgo(1), uploaded_by: 'Omar', teams: ['Coding'] }]),
    });
    renderOverview();
    const data = card('Data');
    expect(await within(data).findByText('Template.xlsx · by Omar')).toBeInTheDocument();
    expect(within(data).queryByText('Status success')).not.toBeInTheDocument();
    expect(within(data).queryByText(/records$/)).not.toBeInTheDocument();
  });

  it('shows the access breakdown and the counts that need attention', async () => {
    setReplies({
      users: ok([
        { id: '1', role: 'Admin', is_active: true },
        { id: '2', role: 'Manager', is_active: false, must_change_password: true },
        { id: '3', role: 'Manager', is_active: true, legacy_role_needs_reassignment: true },
      ]),
    });
    renderOverview();
    const access = card('Access');
    expect(await within(access).findByText('3 users')).toBeInTheDocument();
    expect(within(access).getByText('Manager').closest('li')).toHaveTextContent('2 Manager');
    expect(within(access).getByText('Admin').closest('li')).toHaveTextContent('1 Admin');
    expect(within(access).getByText('1 disabled · 1 must change password')).toBeInTheDocument();
    expect(within(access).getByText('1 need a role reassignment')).toBeInTheDocument();
    expect(within(access).getByText('Warning')).toBeInTheDocument();
  });

  it('shows the latest server error with its short description and full text in a tooltip', async () => {
    const occurredAt = daysAgo(0);
    setReplies({
      errors: ok([{ id: 'x1', request_id: 'r1', endpoint: '/api/reports/export', method: 'GET', error_class: 'TimeoutError', occurred_at: occurredAt }]),
    });
    renderOverview();
    const system = card('System');
    expect(await within(system).findByText('1 server error in the last 24 hours')).toBeInTheDocument();
    expect(within(system).queryByText(/recorded errors/)).not.toBeInTheDocument();
    const message = within(system).getByText('TimeoutError · GET /api/reports/export');
    expect(message).toHaveAttribute('title', 'TimeoutError · GET /api/reports/export');
    expect(within(system).getByText(/Latest /).closest('time')).toHaveAttribute('title', new Date(occurredAt).toLocaleString());
    expect(within(system).getByText('Warning')).toBeInTheDocument();
  });

  it('reports N+ only when the page is full and every fetched row is inside the window', async () => {
    setReplies({
      errors: ok(Array.from({ length: 100 }, (_, index) => ({ id: `e${index}`, endpoint: '/api/x', method: 'GET', error_class: 'ValueError', occurred_at: hoursAgo(1) }))),
    });
    renderOverview();
    expect(await within(card('System')).findByText('100+ server errors in the last 24 hours')).toBeInTheDocument();
  });

  it('counts only the errors inside the last 24 hours when old and recent errors are mixed', async () => {
    setReplies({
      errors: ok([
        { id: 'r1', endpoint: '/api/a', method: 'GET', error_class: 'ValueError', occurred_at: hoursAgo(1) },
        { id: 'r2', endpoint: '/api/b', method: 'POST', error_class: 'KeyError', occurred_at: hoursAgo(23) },
        { id: 'o1', endpoint: '/api/c', method: 'GET', error_class: 'OSError', occurred_at: daysAgo(5) },
      ]),
    });
    renderOverview();
    const system = card('System');
    expect(await within(system).findByText('2 server errors in the last 24 hours')).toBeInTheDocument();
    expect(within(system).getByText('ValueError · GET /api/a')).toBeInTheDocument();
  });

  it('ignores rows with a missing or unparseable timestamp instead of counting or crashing', async () => {
    setReplies({
      errors: ok([
        { id: 'bad1', endpoint: '/api/a', method: 'GET', error_class: 'Broken', occurred_at: 'not a date' },
        { id: 'bad2', endpoint: '/api/b', method: 'GET', error_class: 'Missing' },
        null,
        { id: 'good', endpoint: '/api/c', method: 'POST', error_class: 'KeyError', occurred_at: hoursAgo(2) },
      ]),
    });
    renderOverview();
    expect(await within(card('System')).findByText('1 server error in the last 24 hours')).toBeInTheDocument();
  });

  it('shows a green zero state when there are no server errors', async () => {
    renderOverview();
    const system = card('System');
    expect(await within(system).findByText('No server errors in the last 24 hours')).toBeInTheDocument();
    expect(within(system).getByText('Good')).toBeInTheDocument();
  });

  it('stays good and raises no attention item when the only errors are older than 24 hours', async () => {
    const olderAt = daysAgo(3);
    setReplies({
      errors: ok([{ id: 'old', endpoint: '/api/old', method: 'GET', error_class: 'TimeoutError', occurred_at: olderAt }]),
    });
    renderOverview();
    const system = card('System');
    expect(await within(system).findByText('No server errors in the last 24 hours')).toBeInTheDocument();
    expect(within(system).getByText('Good')).toBeInTheDocument();
    expect(within(system).getByText(/^Last error /).closest('time')).toHaveAttribute('title', new Date(olderAt).toLocaleString());
    expect(within(system).queryByText('Warning')).not.toBeInTheDocument();
    const section = screen.getByRole('region', { name: 'Needs attention' });
    expect(await within(section).findByText('Nothing needs attention.')).toBeInTheDocument();
    expect(within(section).queryByRole('link', { name: 'Go to system errors' })).not.toBeInTheDocument();
  });
});

describe('AdminOverview empty states', () => {
  it('shows empty wording, not an error, when there are no uploads', async () => {
    renderOverview();
    const data = card('Data');
    expect(await within(data).findByText('No uploads yet')).toBeInTheDocument();
    expect(within(data).queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows empty wording when there are no user accounts', async () => {
    renderOverview();
    const access = card('Access');
    expect(await within(access).findByText('No user accounts')).toBeInTheDocument();
    expect(within(access).queryByRole('alert')).not.toBeInTheDocument();
  });
});

describe('AdminOverview loading, errors and Retry', () => {
  it('shows a loading skeleton on each card while its request is pending', async () => {
    setReplies({ uploads: hanging, management: hanging, users: hanging, errors: hanging });
    renderOverview();
    for (const title of ['Data', 'Access', 'System']) {
      expect(screen.getByRole('status', { name: `Loading ${title}` })).toBeInTheDocument();
    }
    expect(card('Evaluation')).not.toHaveAttribute('aria-busy', 'true');
    expect(screen.getByText('Checking areas…')).toBeInTheDocument();
  });

  it('shows an inline error with Retry, and Retry issues a new request that recovers', async () => {
    const user = userEvent.setup();
    let userCalls = 0;
    setReplies({
      users: () => {
        userCalls += 1;
        return userCalls === 1 ? failing() : json({ success: true, data: [{ id: '1', role: 'Admin', is_active: true }] });
      },
    });
    renderOverview();
    const access = card('Access');
    expect(await within(access).findByText('Could not load this area.')).toBeInTheDocument();
    expect(within(access).getByRole('alert')).toBeInTheDocument();
    expect(within(card('Data')).getByText('No uploads yet')).toBeInTheDocument();

    await user.click(within(access).getByRole('button', { name: 'Retry Access' }));
    expect(await within(access).findByText('1 user')).toBeInTheDocument();
    expect(userCalls).toBe(2);
    expect(requestedUrls().filter((url) => url.endsWith('/api/users/'))).toHaveLength(2);
  });

  it('keeps the other cards rendered when one request fails', async () => {
    setReplies({
      uploads: ok([{ id: 'u1', filename: 'PMS.xlsx', uploaded_at: daysAgo(3), uploaded_by: 'Sara', status: 'success', record_count: 5 }]),
      users: ok([{ id: '1', role: 'Admin', is_active: true }]),
      errors: failing,
    });
    renderOverview();
    expect(await within(card('Data')).findByText('PMS.xlsx · by Sara')).toBeInTheDocument();
    expect(await within(card('Access')).findByText('1 user')).toBeInTheDocument();
    const system = card('System');
    expect(await within(system).findByText('Could not load this area.')).toBeInTheDocument();
    expect(within(system).getByRole('button', { name: 'Retry System' })).toBeInTheDocument();
    expect(await screen.findByText('Could not check System. Use Retry on the card above.')).toBeInTheDocument();
  });
});

describe('AdminOverview needs attention', () => {
  it('lists a failed latest upload and links to data uploads', async () => {
    setReplies({
      uploads: ok([{ id: 'u1', filename: 'Bad.xlsx', uploaded_at: daysAgo(1), uploaded_by: 'Sara', status: 'failed', record_count: 0 }]),
    });
    renderOverview();
    expect(await within(card('Data')).findByText('Latest upload failed')).toBeInTheDocument();
    expect(within(card('Data')).getByText('Attention')).toBeInTheDocument();
    const section = screen.getByRole('region', { name: 'Needs attention' });
    expect(await within(section).findByText('Latest upload failed: Bad.xlsx.')).toBeInTheDocument();
    expect(within(section).getByRole('link', { name: 'Go to data uploads' })).toHaveAttribute('href', '/settings/data');
    expect(screen.queryByText('Nothing needs attention.')).not.toBeInTheDocument();
  });

  it('lists present server errors and users needing a reassignment, each with its link', async () => {
    setReplies({
      errors: ok([
        { id: 'e1', endpoint: '/api/a', method: 'GET', error_class: 'ValueError', occurred_at: hoursAgo(1) },
        { id: 'e2', endpoint: '/api/b', method: 'POST', error_class: 'KeyError', occurred_at: hoursAgo(2) },
        { id: 'e3', endpoint: '/api/c', method: 'GET', error_class: 'OSError', occurred_at: hoursAgo(3) },
      ]),
      users: ok([{ id: '1', role: 'Manager', is_active: true, legacy_role_needs_reassignment: true }]),
    });
    renderOverview();
    const section = screen.getByRole('region', { name: 'Needs attention' });
    expect(await within(section).findByText('3 server errors in the last 24 hours.')).toBeInTheDocument();
    expect(within(section).getByRole('link', { name: 'Go to system errors' })).toHaveAttribute('href', '/settings/system-errors');
    expect(within(section).getByText('1 user needs a role reassignment.')).toBeInTheDocument();
    expect(within(section).getByRole('link', { name: 'Go to users' })).toHaveAttribute('href', '/settings/users');
  });

  it('says nothing needs attention when every area is clear', async () => {
    renderOverview();
    const section = screen.getByRole('region', { name: 'Needs attention' });
    expect(await within(section).findByText('Nothing needs attention.')).toBeInTheDocument();
    expect(within(section).queryByRole('link')).not.toBeInTheDocument();
  });

  it('does not claim nothing needs attention while an area could not be checked', async () => {
    setReplies({ errors: failing });
    renderOverview();
    const section = screen.getByRole('region', { name: 'Needs attention' });
    expect(await within(section).findByText('Could not check System. Use Retry on the card above.')).toBeInTheDocument();
    expect(within(section).queryByText('Nothing needs attention.')).not.toBeInTheDocument();
  });
});

describe('AdminOverview malformed payloads', () => {
  it('degrades malformed rows without throwing', async () => {
    setReplies({
      users: ok([null, 'x', { role: 42, is_active: 'no' }]),
    });
    renderOverview();
    const access = card('Access');
    expect(await within(access).findByText('1 user')).toBeInTheDocument();
    expect(within(access).getByText('Unknown role').closest('li')).toHaveTextContent('1 Unknown role');
    expect(within(access).getByText('0 disabled · 0 must change password')).toBeInTheDocument();
  });

  it('shows the error state, not a crash, when the payload shape is wrong', async () => {
    setReplies({
      uploads: () => json({ success: true, data: 'not a list' }),
      errors: () => json({ success: true, data: null }),
    });
    renderOverview();
    expect(await within(card('Data')).findByText('Could not load this area.')).toBeInTheDocument();
    expect(await within(card('System')).findByText('Could not load this area.')).toBeInTheDocument();
    expect(await within(card('Access')).findByText('No user accounts')).toBeInTheDocument();
  });
});

describe('AdminOverview requests', () => {
  it('makes no request to any evaluation endpoint', async () => {
    setReplies({
      uploads: ok([{ id: 'u1', filename: 'PMS.xlsx', uploaded_at: daysAgo(1), uploaded_by: 'Sara', status: 'success' }]),
      users: ok([{ id: '1', role: 'Admin', is_active: true }]),
      errors: ok([{ id: 'e1', endpoint: '/api/a', method: 'GET', error_class: 'ValueError', occurred_at: daysAgo(0) }]),
    });
    renderOverview();
    await waitFor(() => expect(screen.getByText('1 server error in the last 24 hours')).toBeInTheDocument());
    expect(requestedUrls().filter((url) => url.includes('evaluation'))).toHaveLength(0);
    expect(requestedUrls()).toEqual(expect.arrayContaining([
      expect.stringContaining('/api/uploads/'),
      expect.stringContaining('/api/team-management/management-kpi-config/uploads'),
      expect.stringContaining('/api/users/'),
      expect.stringContaining('/api/settings/system-errors?limit=100'),
    ]));
  });
});
