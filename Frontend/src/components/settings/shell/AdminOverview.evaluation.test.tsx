import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AdminOverview } from './AdminOverview';

const mocks = vi.hoisted(() => ({ fetchWithRole: vi.fn() }));

vi.mock('../../../context/RoleContext', () => ({
  useUserRole: () => ({ role: 'Admin', fetchWithRole: mocks.fetchWithRole }),
}));

type Reply = () => Promise<Response> | Response;

let evaluationReply: Reply;

function json(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as unknown as Response;
}

const emptyList = () => json({ success: true, data: [] });
const hanging: Reply = () => new Promise<Response>(() => {});

beforeEach(() => {
  mocks.fetchWithRole.mockReset();
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const text = String(url);
    if (text.includes('/api/settings/evaluation/overview')) return evaluationReply();
    if (text.includes('management-kpi-config/uploads') || text.endsWith('/api/uploads/') || text.endsWith('/api/users/') || text.includes('/api/settings/system-errors')) {
      return emptyList();
    }
    throw new Error(`Unexpected request: ${url}`);
  });
  evaluationReply = () => json({ success: true, data: { drafts: 0, approved_not_applied: 0, applied: 0, attention: [], generated_at: '2026-10-13T08:00:00+00:00' } });
});

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

function evaluationCard() {
  return screen.getByRole('heading', { level: 3, name: 'Evaluation' }).closest('article') as HTMLElement;
}

const overviewBody = (data: Record<string, unknown>) => ({ success: true, data: { attention: [], generated_at: '2026-10-13T08:00:00+00:00', ...data } });

describe('AdminOverview Evaluation card', () => {
  it('says how many drafts are waiting, with the other counts, and warns', async () => {
    evaluationReply = () => json(overviewBody({ drafts: 2, approved_not_applied: 3, applied: 4 }));
    renderOverview();

    const card = evaluationCard();
    expect(await within(card).findByText('2 drafts waiting')).toBeInTheDocument();
    expect(within(card).getByText('3 approved, not applied · 4 applied')).toBeInTheDocument();
    expect(within(card).getByText('Warning')).toBeInTheDocument();
  });

  it('says approved months are not applied when no draft is waiting', async () => {
    evaluationReply = () => json(overviewBody({ drafts: 0, approved_not_applied: 2, applied: 1 }));
    renderOverview();

    const card = evaluationCard();
    expect(await within(card).findByText('2 approved, not applied')).toBeInTheDocument();
    expect(within(card).getByText('1 applied')).toBeInTheDocument();
    expect(within(card).getByText('Warning')).toBeInTheDocument();
  });

  it('says nothing is waiting, and is good, when every approved month is applied', async () => {
    evaluationReply = () => json(overviewBody({ drafts: 0, approved_not_applied: 0, applied: 5 }));
    renderOverview();

    const card = evaluationCard();
    expect(await within(card).findByText('Nothing waiting')).toBeInTheDocument();
    expect(within(card).getByText('5 applied')).toBeInTheDocument();
    expect(within(card).getByText('Good')).toBeInTheDocument();
  });

  it('shows an empty state when there are no monthly versions at all', async () => {
    renderOverview();

    const card = evaluationCard();
    expect(await within(card).findByText('No evaluation months yet')).toBeInTheDocument();
    expect(within(card).getByText('Open evaluation settings to start a month.')).toBeInTheDocument();
  });

  it('never implies nothing is pending when the approved count is unknown', async () => {
    evaluationReply = () => json(overviewBody({ drafts: 0, approved_not_applied: null, applied: null }));
    renderOverview();

    const card = evaluationCard();
    expect(await within(card).findByText('No drafts waiting')).toBeInTheDocument();
    expect(within(card).getByText('Approved months could not be checked')).toBeInTheDocument();
    expect(within(card).queryByText('Nothing waiting')).not.toBeInTheDocument();
    expect(within(card).getByText('Info')).toBeInTheDocument();
  });

  it('keeps the known draft count when the approved count is unknown', async () => {
    evaluationReply = () => json(overviewBody({ drafts: 1, approved_not_applied: null, applied: null }));
    renderOverview();

    const card = evaluationCard();
    expect(await within(card).findByText('1 draft waiting')).toBeInTheDocument();
    expect(within(card).getByText('Approved months could not be checked')).toBeInTheDocument();
  });

  it('shows a loading state while its own request is pending', () => {
    evaluationReply = hanging;
    renderOverview();
    expect(evaluationCard()).toHaveAttribute('aria-busy', 'true');
  });

  it('shows an error with Retry for its own request, and Retry recovers', async () => {
    const user = userEvent.setup();
    let calls = 0;
    evaluationReply = () => {
      calls += 1;
      return calls === 1 ? json({ success: false, message: 'Request failed' }, 500) : json(overviewBody({ drafts: 1, approved_not_applied: 0, applied: 0 }));
    };
    renderOverview();

    const card = evaluationCard();
    expect(await within(card).findByText('Could not load this area.')).toBeInTheDocument();
    expect(await screen.findByText('Could not check Evaluation. Use Retry on the card above.')).toBeInTheDocument();

    await user.click(within(card).getByRole('button', { name: 'Retry Evaluation' }));
    expect(await within(card).findByText('1 draft waiting')).toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it('rejects a payload of the wrong shape as an error rather than guessing', async () => {
    evaluationReply = () => json({ success: true, data: { drafts: 'two', attention: [] } });
    renderOverview();
    expect(await within(evaluationCard()).findByText('Could not load this area.')).toBeInTheDocument();
  });
});

describe('AdminOverview Needs attention for evaluation months', () => {
  it('lists a waiting draft and an approved-not-applied month, each linked to that scope and period', async () => {
    evaluationReply = () => json(overviewBody({
      drafts: 1,
      approved_not_applied: 1,
      applied: 0,
      attention: [
        {
          scope_id: 'scope-coding', scope_display_name: 'Coding', performance_level: 'Employee', position_name: '',
          year: 2026, month: 8, month_name: 'August', state: 'draft', version_id: 'v-aug', version_number: 3,
        },
        {
          scope_id: 'scope-pharmacy', scope_display_name: 'Pharmacy', performance_level: 'Managerial', position_name: 'Lead',
          year: 2026, month: 6, month_name: 'June', state: 'approved_not_applied', version_id: 'v-jun', version_number: 1,
        },
      ],
    }));
    renderOverview();

    expect(await screen.findByText('Draft for Coding · Employee · August 2026 is waiting for approval.')).toBeInTheDocument();
    expect(screen.getByText('Pharmacy · Managerial · Lead · June 2026 is approved but not applied.')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open draft' })).toHaveAttribute('href', '/settings/evaluation?scope=scope-coding&year=2026&month=8');
    expect(screen.getByRole('link', { name: 'Open to apply' })).toHaveAttribute('href', '/settings/evaluation?scope=scope-pharmacy&year=2026&month=6');
    expect(screen.queryByText('Nothing needs attention.')).not.toBeInTheDocument();
  });

  it('ignores an attention row with an unknown state', async () => {
    evaluationReply = () => json(overviewBody({
      drafts: 0, approved_not_applied: 0, applied: 0,
      attention: [{ scope_id: 'x', version_id: 'v', year: 2026, month: 1, month_name: 'January', state: 'superseded' }],
    }));
    renderOverview();
    expect(await screen.findByText('Nothing needs attention.')).toBeInTheDocument();
  });

  it('says Evaluation could not be checked when its request fails, rather than reporting nothing needs attention', async () => {
    evaluationReply = () => json({ success: false, message: 'Request failed' }, 500);
    renderOverview();
    expect(await screen.findByText('Could not check Evaluation. Use Retry on the card above.')).toBeInTheDocument();
    expect(screen.queryByText('Nothing needs attention.')).not.toBeInTheDocument();
  });
});

describe('AdminOverview evaluation request', () => {
  it('requests the overview once, with the admin session', async () => {
    renderOverview();
    await waitFor(() => expect(screen.getByText('Nothing needs attention.')).toBeInTheDocument());
    const urls = mocks.fetchWithRole.mock.calls.map((call) => String(call[0]));
    expect(urls.filter((url) => url.includes('/api/settings/evaluation/overview'))).toHaveLength(1);
  });
});

describe('AdminOverview unconfirmed approved months', () => {
  it('mentions them in neutral wording and keeps the card good when nothing is waiting', async () => {
    evaluationReply = () => json(overviewBody({ drafts: 0, approved_not_applied: 0, approved_unconfirmed: 2, applied: 1 }));
    renderOverview();

    const card = evaluationCard();
    expect(await within(card).findByText('Nothing waiting')).toBeInTheDocument();
    expect(within(card).getByText('2 approved with no apply on record · 1 applied')).toBeInTheDocument();
    expect(within(card).getByText('Good')).toBeInTheDocument();
    expect(await screen.findByText('Nothing needs attention.')).toBeInTheDocument();
  });

  it('does not raise the tone for unconfirmed months alongside a waiting draft', async () => {
    evaluationReply = () => json(overviewBody({ drafts: 1, approved_not_applied: 0, approved_unconfirmed: 3, applied: 0 }));
    renderOverview();

    const card = evaluationCard();
    expect(await within(card).findByText('1 draft waiting')).toBeInTheDocument();
    expect(within(card).getByText('3 approved with no apply on record · 0 applied')).toBeInTheDocument();
    expect(within(card).getByText('Warning')).toBeInTheDocument();
  });

  it('shows the empty state only when there are no monthly versions of any kind', async () => {
    evaluationReply = () => json(overviewBody({ drafts: 0, approved_not_applied: 0, approved_unconfirmed: 1, applied: 0 }));
    renderOverview();

    const card = evaluationCard();
    expect(await within(card).findByText('Nothing waiting')).toBeInTheDocument();
    expect(within(card).queryByText('No evaluation months yet')).not.toBeInTheDocument();
  });

  it('never lists an unconfirmed month under Needs attention', async () => {
    evaluationReply = () => json(overviewBody({ drafts: 0, approved_not_applied: 0, approved_unconfirmed: 4, applied: 0, attention: [] }));
    renderOverview();

    expect(await screen.findByText('Nothing needs attention.')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open to apply' })).not.toBeInTheDocument();
  });
});
