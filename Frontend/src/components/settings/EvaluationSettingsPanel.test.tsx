import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { EvaluationSettingsPanel } from './EvaluationSettingsPanel';
import { formatSamplePreview, initialReportingPeriod, previewSampleRows, readStoredActuals } from './evaluationSettings';

const roleState = vi.hoisted(() => ({ role: 'Admin' as string }));
const mocks = vi.hoisted(() => ({ fetchWithRole: vi.fn() }));

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({ role: roleState.role, fetchWithRole: mocks.fetchWithRole }),
}));

const scope = {
  id: 'scope-1',
  display_name: 'Coding',
  performance_level: 'Employee',
  position_name: '',
  readiness: 'supported',
  supported: true,
};

const blocked = {
  id: 'scope-2',
  display_name: 'Future Desk',
  performance_level: 'Employee',
  position_name: '',
  readiness: 'blocked',
  block_reason: 'No supported importer is registered for this team and level.',
  history_note: 'Historical direction is not guessed.',
};

const draft = {
  id: 'draft-1',
  status: 'draft',
  notes: 'Draft started from the file baseline.',
  lines: [{ kpi_key: 'QualityErrors', label: 'Quality Errors', weight: 1, direction: 'higher_better', target: 55, target_mode: 'fixed', unit: '%' }],
};

function json(data: unknown, ok = true) {
  return { ok, json: async () => (ok ? { success: true, data } : { detail: data }) };
}

function monthOf(url: string) {
  return /[?&]month=(\d+)/.exec(url)?.[1] ?? '';
}

function periodData(target: number, actuals?: unknown) {
  return {
    versions: [{ ...draft, lines: [{ ...draft.lines[0], target }] }],
    stored_actuals: actuals,
  };
}

function renderPanel(retryMutations = false) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: retryMutations ? 1 : false } },
  });
  const view = render(
    <QueryClientProvider client={client}>
      <EvaluationSettingsPanel />
    </QueryClientProvider>,
  );
  return { ...view, client };
}

beforeEach(() => {
  roleState.role = 'Admin';
  mocks.fetchWithRole.mockClear();
  mocks.fetchWithRole.mockImplementation(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope, blocked] });
    if (href.includes('/periods')) return json({ versions: [draft], stored_actuals: { QualityErrors: 60 } });
    if (href.includes('/preview')) return json({ score: 91.6667, rows: [{ kpi_key: 'QualityErrors', achievement: 55 / 60 }] });
    if (href.includes('/approve')) return json({ ...draft, status: 'approved' });
    if (href.includes('/apply')) return json({ revision_id: 'revision-1' });
    if (href.includes('/drafts') && init?.method === 'POST') {
      const body = JSON.parse(String(init.body));
      return json({
        ...draft,
        id: `draft-${body.month}`,
        notes: 'Copied from the approved previous month.',
        lines: [{ ...draft.lines[0], target: body.month === 8 ? 65 : 70 }],
      });
    }
    return json({ ...draft, lines: draft.lines });
  });
});

afterEach(() => {
  vi.useRealTimers();
  window.history.replaceState(null, '', '/');
});

async function chooseMonth(month: string) {
  fireEvent.change(screen.getByLabelText('Reporting month'), { target: { value: month } });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Copy previous month' })).toBeEnabled());
}

it('starts from the current date or an explicit period instead of a fixed month', async () => {
  expect(initialReportingPeriod('?period=2026-08', new Date(2026, 6, 1))).toEqual({ year: 2026, month: 8 });
  expect(initialReportingPeriod('?year=2025&month=July', new Date(2026, 0, 1))).toEqual({ year: 2025, month: 7 });
  expect(initialReportingPeriod('', new Date(2026, 9, 9))).toEqual({ year: 2026, month: 10 });

  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 9, 9));
  renderPanel();
  expect(await screen.findByLabelText('Reporting month')).toHaveValue('10');
  expect(screen.getByLabelText('Reporting year')).toHaveValue(2026);
});

it('uses a valid period in the URL', async () => {
  window.history.replaceState(null, '', '/?period=2026-08');
  renderPanel();
  expect(await screen.findByLabelText('Reporting month')).toHaveValue('8');
  expect(screen.getByLabelText('Reporting year')).toHaveValue(2026);
});

it('keeps July and August copies independent', async () => {
  const user = userEvent.setup();
  renderPanel();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled());
  await chooseMonth('7');
  await user.click(screen.getByRole('button', { name: 'Copy previous month' }));
  expect(await screen.findByDisplayValue('70')).toBeInTheDocument();
  await chooseMonth('8');
  await user.click(screen.getByRole('button', { name: 'Copy previous month' }));
  expect(await screen.findByDisplayValue('65')).toBeInTheDocument();
  const copies = mocks.fetchWithRole.mock.calls.filter((call) => String(call[0]).includes('/drafts') && call[1]?.method === 'POST');
  expect(copies.map((call) => JSON.parse(String(call[1]?.body)).month)).toEqual([7, 8]);
  await user.click(screen.getByRole('button', { name: 'Approve' }));
  expect(await screen.findByText(/Existing scores were not recalculated/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Apply' }));
  expect(await screen.findByText(/Apply updated this month only/)).toBeInTheDocument();
});

it.each(['Manager', 'Performance Team'])('makes no evaluation request and shows no editors for %s', async (role) => {
  roleState.role = role;
  renderPanel();
  expect(screen.getByText('Evaluation settings are limited to Admin.')).toBeInTheDocument();
  expect(screen.queryByLabelText('Reporting month')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
  expect(screen.queryByRole('spinbutton', { name: 'Reporting year' })).not.toBeInTheDocument();
  await act(async () => { await Promise.resolve(); });
  expect(mocks.fetchWithRole).not.toHaveBeenCalled();
});

it('previews the saved sample actual and does not send the edited target', async () => {
  const user = userEvent.setup();
  renderPanel();
  expect(await screen.findByLabelText('QualityErrors target')).toHaveValue('55');
  expect(screen.getByText(/first stored record only/)).toBeInTheDocument();
  expect(screen.getByText(/not a scope-wide impact/)).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Preview' })).toBeEnabled());
  await user.click(screen.getByRole('button', { name: 'Preview' }));
  expect(await screen.findByText(/QualityErrors achievement 91\.67%/)).toBeInTheDocument();
  expect(screen.getByText(/sample score 91\.6667/)).toBeInTheDocument();
  const previewCall = mocks.fetchWithRole.mock.calls.find((call) => String(call[0]).includes('/preview'));
  const body = JSON.parse(String(previewCall?.[1]?.body));
  expect(body).toEqual({ rows: [{ kpi_key: 'QualityErrors', actual: 60 }] });
  expect(JSON.stringify(body)).not.toContain('workbook_target');

  await user.clear(screen.getByLabelText('QualityErrors target'));
  await user.type(screen.getByLabelText('QualityErrors target'), '40');
  expect(screen.getByText('Save the draft before preview or approval. Unsaved edits are not previewed.')).toBeInTheDocument();
  expect(screen.queryByText(/achievement 91\.67%/)).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Preview' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
  expect(mocks.fetchWithRole.mock.calls.filter((call) => String(call[0]).includes('/preview'))).toHaveLength(1);
});

it('does not preview or invent a score when stored actuals are missing', async () => {
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json(periodData(55, { QualityErrors: { actual: 60 } }));
    return json(draft);
  });
  renderPanel();
  expect(await screen.findByText(/No stored actuals are available/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Preview' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Preview' }));
  expect(mocks.fetchWithRole.mock.calls.some((call) => String(call[0]).includes('/preview'))).toBe(false);
  expect(screen.queryByText(/achievement/)).not.toBeInTheDocument();
  expect(readStoredActuals({ QualityErrors: { actual: 60 } })).toEqual({});
  expect(previewSampleRows([{ ...draft.lines[0] }], {})).toEqual([]);
  expect(formatSamplePreview({})).toMatch(/no scored sample/i);
});

it('ignores a late period response after the selection changes', async () => {
  const pending = new Map<string, (value: unknown) => void>();
  const hold = (month: string) => new Promise((resolve) => { pending.set(month, resolve); });
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json(await hold(monthOf(href)));
    return json(draft);
  });
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 6, 15));
  renderPanel();
  await waitFor(() => expect(pending.has('7')).toBe(true));
  expect(screen.getAllByText('Loading this month…').length).toBeGreaterThan(0);
  expect(screen.queryByLabelText('QualityErrors target')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Reporting month'), { target: { value: '8' } });
  pending.get('8')?.(periodData(80));
  expect(await screen.findByDisplayValue('80')).toBeInTheDocument();
  pending.get('7')?.(periodData(55));
  await act(async () => { await Promise.resolve(); });
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('80');
  expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled();
});

it('does not apply a save for the previous month to the month now on screen', async () => {
  let releaseSave: (value: unknown) => void = () => {};
  mocks.fetchWithRole.mockImplementation(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json(periodData(monthOf(href) === '8' ? 80 : 55, { QualityErrors: 60 }));
    if (init?.method === 'PATCH') {
      return json(await new Promise((resolve) => { releaseSave = resolve; }));
    }
    return json(draft);
  });
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 6, 15));
  renderPanel();
  expect(await screen.findByDisplayValue('55')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  fireEvent.change(screen.getByLabelText('Reporting month'), { target: { value: '8' } });
  expect(await screen.findByDisplayValue('80')).toBeInTheDocument();
  releaseSave({ ...draft, lines: [{ ...draft.lines[0], target: 99 }] });
  await act(async () => { await Promise.resolve(); });
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('80');
  expect(screen.queryByText('Draft saved.')).not.toBeInTheDocument();
  const patches = mocks.fetchWithRole.mock.calls.filter((call) => call[1]?.method === 'PATCH');
  expect(patches).toHaveLength(1);
  expect(String(patches[0][0])).toContain('/drafts/draft-1');
});

it('sends one draft save when the button is activated twice', async () => {
  let releaseSave: (value: unknown) => void = () => {};
  mocks.fetchWithRole.mockImplementation(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json({ versions: [draft] });
    if (init?.method === 'PATCH') return json(await new Promise((resolve) => { releaseSave = resolve; }));
    return json(draft);
  });
  renderPanel();
  const save = await screen.findByRole('button', { name: 'Save draft' });
  await waitFor(() => expect(save).toBeEnabled());
  fireEvent.click(save);
  fireEvent.click(save);
  await waitFor(() => expect(mocks.fetchWithRole.mock.calls.filter((call) => call[1]?.method === 'PATCH')).toHaveLength(1));
  releaseSave(draft);
});

it('does not retry approval when the shared query client would retry a mutation', async () => {
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json({ versions: [draft] });
    if (href.includes('/approve')) return json('Approval failed', false);
    return json(draft);
  });
  renderPanel(true);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Approval failed');
  expect(mocks.fetchWithRole.mock.calls.filter((call) => String(call[0]).includes('/approve'))).toHaveLength(1);
});

it('shows a blocked scope instead of treating it as supported', async () => {
  const user = userEvent.setup();
  renderPanel();
  await screen.findByRole('option', { name: /Future Desk/ });
  await user.selectOptions(screen.getByLabelText('Evaluation scope'), 'scope-2');
  expect(await screen.findByText(/No supported importer/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
});
