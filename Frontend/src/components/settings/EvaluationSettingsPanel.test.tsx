import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { EvaluationSettingsPanel } from './EvaluationSettingsPanel';
import { initialReportingPeriod } from './evaluationSettings';

const roleState = vi.hoisted(() => ({ role: 'Admin' as string }));
const mocks = vi.hoisted(() => ({ fetchWithRole: vi.fn() }));
const performanceRefresh = vi.hoisted(() => vi.fn());

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({ role: roleState.role, fetchWithRole: mocks.fetchWithRole }),
}));
vi.mock('../../hooks/usePerformanceData', () => ({
  refreshPerformanceData: performanceRefresh,
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

const line = {
  kpi_key: 'QualityErrors',
  label: 'Quality Errors',
  weight: 1,
  direction: 'higher_better',
  target: 55,
  target_mode: 'fixed',
  unit: '%',
};

const draft = {
  id: 'draft-1',
  status: 'draft',
  version_number: 3,
  checksum: 'sum-draft',
  notes: 'Draft started from the file baseline.',
  lines: [line],
};

function json(data: unknown, ok = true) {
  return { ok, json: async () => (ok ? { success: true, data } : { detail: data }) };
}

function monthOf(url: string) {
  return /[?&]month=(\d+)/.exec(url)?.[1] ?? '';
}

function periodData(target: number, extra: Record<string, unknown> = {}) {
  return {
    versions: [{ ...draft, lines: [{ ...line, target }] }],
    ...extra,
  };
}

function comparison(code: string, score = 80) {
  return {
    record_id: `rec-${code}`,
    employee_id: `emp-${code}`,
    employee_code: code,
    before_score: score,
    after_score: score + 1,
    before_grade: 'C',
    after_grade: 'B',
    kpis: [{ kpi_key: 'QualityErrors', actual: 60, workbook_target: 50, applied_target: 40, weight: 1, before_achievement: 0.4, after_achievement: 0.5, before_contribution: 0.4, after_contribution: 0.5 }],
  };
}

function impactProof(overrides: Record<string, unknown> = {}) {
  return {
    version_id: 'draft-1',
    scope_id: 'scope-1',
    year: 2026,
    month: 10,
    writes: 0,
    config_validated: true,
    zero_affected: false,
    affected_count: 1,
    scored_employees: 1,
    changed_count: 1,
    unchanged_count: 0,
    conflicts: [],
    missing_evidence: [],
    comparisons: [comparison('E001')],
    rules_checksum: 'rules-1',
    source_fingerprint: 'finger-1',
    proof_stored: true,
    satisfies_approval_gate: true,
    ...overrides,
  };
}

function calls(part: string, method?: string) {
  return mocks.fetchWithRole.mock.calls.filter((call) => String(call[0]).includes(part) && (method == null || call[1]?.method === method));
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
  performanceRefresh.mockClear();
  mocks.fetchWithRole.mockClear();
  mocks.fetchWithRole.mockImplementation(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope, blocked] });
    if (href.includes('/periods')) return json({ versions: [draft] });
    if (href.includes('/impact-preview')) return json(impactProof());
    if (href.includes('/approve')) return json({ ...draft, status: 'approved' });
    if (href.includes('/apply')) return json({ revision_id: 'revision-1', applied_count: 1 });
    if (href.includes('/drafts') && init?.method === 'POST') {
      const body = JSON.parse(String(init.body));
      return json({
        ...draft,
        id: `draft-${body.month}`,
        notes: 'Copied from the approved previous month.',
        lines: [{ ...line, target: body.month === 8 ? 65 : 70 }],
      });
    }
    return json(draft);
  });
});

afterEach(() => {
  vi.useRealTimers();
  window.history.replaceState(null, '', '/');
});

function october() {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 9, 9));
}

it('starts from the current date or an explicit period instead of a fixed month', async () => {
  expect(initialReportingPeriod('?period=2026-08', new Date(2026, 6, 1))).toEqual({ year: 2026, month: 8 });
  expect(initialReportingPeriod('?year=2025&month=July', new Date(2026, 0, 1))).toEqual({ year: 2025, month: 7 });
  expect(initialReportingPeriod('', new Date(2026, 9, 9))).toEqual({ year: 2026, month: 10 });

  october();
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

it('revises the selected approved month, saves, proves impact, approves without applying, then applies and rolls back', async () => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 6, 15));
  const approved = {
    id: 'approved-july',
    status: 'approved',
    version_number: 2,
    checksum: 'sum-approved',
    lines: [{ ...line, target: 55 }],
  };
  const revised = {
    id: 'draft-july',
    status: 'draft',
    version_number: 3,
    checksum: 'sum-draft',
    source_version_id: 'approved-july',
    source_checksum: 'sum-approved',
    lines: [{ ...line, target: 55 }],
  };
  const state = {
    versions: [approved] as Array<Record<string, unknown>>,
    revisions: [] as Array<Record<string, unknown>>,
  };
  mocks.fetchWithRole.mockImplementation(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json({ versions: state.versions, revisions: state.revisions });
    if (href.includes('/revise')) {
      state.versions = [approved, revised];
      return json({ ...revised, resumed: false });
    }
    if (init?.method === 'PATCH') {
      const body = JSON.parse(String(init.body || '{}'));
      revised.lines = body.lines;
      revised.checksum = 'sum-saved';
      state.versions = [approved, revised];
      return json(revised);
    }
    if (href.includes('/impact-preview')) {
      return json(impactProof({
        version_id: 'draft-july',
        month: 7,
        affected_count: 2,
        scored_employees: 2,
        changed_count: 1,
        unchanged_count: 1,
        conflicts: [{ record_id: 'rec-1', kpi_key: 'QualityErrors', workbook_target: 60, approved_target: 55 }],
        comparisons: [comparison('E001', 70), comparison('E002', 81)],
      }));
    }
    if (href.includes('/approve')) {
      revised.status = 'approved';
      revised.checksum = 'sum-approved-new';
      state.versions = [approved, revised];
      return json(revised);
    }
    if (href.includes('/evaluation/apply')) {
      state.revisions = [{ id: 'revision-1', version_id: 'draft-july', status: 'active', created_at: '2026-07-20T00:00:00Z', affected_count: 2, can_rollback: true }];
      return json({ revision_id: 'revision-1', applied_count: 2, version_id: 'draft-july' });
    }
    if (href.includes('/rollback')) {
      state.revisions = [{ id: 'revision-1', version_id: 'draft-july', status: 'rolled_back', created_at: '2026-07-20T00:00:00Z', affected_count: 2, can_rollback: false }];
      return json({ revision_id: 'revision-1', status: 'rolled_back', restored_basis: [{ record_id: 'rec-1' }], restored_revision_id: null });
    }
    return json(draft);
  });

  const { client } = renderPanel();
  expect(await screen.findByLabelText('QualityErrors target')).toBeDisabled();
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('55');
  expect(screen.queryByRole('button', { name: 'New draft' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Copy previous month' })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Revise this month' }));
  expect(await screen.findByText(/Revision draft opened for this month/)).toBeInTheDocument();
  expect(screen.getAllByText(/Source version approved-july/).length).toBeGreaterThan(0);
  expect(screen.getByText(/Version 2/)).toBeInTheDocument();
  const reviseCall = calls('/revise', 'POST')[0];
  expect(String(reviseCall[0])).toContain('/versions/approved-july/revise');
  expect(reviseCall[1]?.body).toBeUndefined();
  expect(calls('/drafts', 'POST')).toHaveLength(0);

  const target = screen.getByLabelText('QualityErrors target');
  expect(target).toBeEnabled();
  expect(target).toHaveValue('55');
  fireEvent.change(target, { target: { value: '40' } });
  expect(screen.getByRole('button', { name: 'Impact preview' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await waitFor(() => expect(calls('/drafts/draft-july', 'PATCH')).toHaveLength(1));
  const saved = JSON.parse(String(calls('/drafts/draft-july', 'PATCH')[0][1]?.body));
  expect(saved.weight_only).toBeUndefined();
  expect(saved.lines[0]).toMatchObject({ target: 40, weight: 1, direction: 'higher_better', target_mode: 'fixed' });
  expect(await screen.findByText('Draft saved.')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Impact preview' }));
  expect(await screen.findByText(/2 stored records, 2 scored, 1 changed, 1 unchanged/)).toBeInTheDocument();
  const mismatches = screen.getByRole('table', { name: 'Fixed target mismatches' });
  expect(within(mismatches).getByText('60')).toBeInTheDocument();
  expect(within(mismatches).getByText('55')).toBeInTheDocument();
  expect(screen.getByText(/new upload is still blocked/i)).toBeInTheDocument();
  expect(screen.getByRole('table', { name: 'Before and after scores' }).closest('div')).toHaveClass('overflow-x-auto');
  expect(screen.getByText('E001')).toBeInTheDocument();
  const impactCall = calls('/impact-preview', 'POST')[0];
  expect(impactCall[1]?.body).toBeUndefined();
  expect(calls('/preview').filter((call) => /\/preview$/.test(String(call[0])))).toHaveLength(0);

  await waitFor(() => expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
  expect(await screen.findByText(/Existing scores were not recalculated/)).toBeInTheDocument();
  expect(calls('/evaluation/apply', 'POST')).toHaveLength(0);
  expect(performanceRefresh).not.toHaveBeenCalled();

  client.setQueryData(['performance', 'catalog', 'sess'], { periods: [] });
  client.setQueryData(['performance', 'bounded-records', 'kept'], { score: 79.82, target: 0.65 });
  client.setQueryData(['performance', 'summary', 'sess'], { total: 1 });
  client.setQueryData(['team-configs'], []);
  client.setQueryData(['kpi-weights'], []);
  client.setQueryData(['balanced-scorecard'], { ok: true });
  client.setQueryData(['reports', 'list'], []);
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
  expect(await screen.findByText('Apply recorded revision revision-1 for 2 stored records.')).toBeInTheDocument();
  const applyCall = calls('/evaluation/apply', 'POST')[0];
  expect(JSON.parse(String(applyCall[1]?.body))).toEqual({ scope_id: 'scope-1', year: 2026, month: 7 });
  expect(await screen.findByRole('button', { name: 'Rollback' })).toBeInTheDocument();
  expect(performanceRefresh).toHaveBeenCalledTimes(1);
  expect(invalidate.mock.calls.map((call) => call[0]?.queryKey)).toEqual(expect.arrayContaining([
    ['evaluation-settings', 'period', 'scope-1', 2026, 7],
    ['performance'],
    ['executive', 'summary'],
    ['reports', 'center'],
    ['insights', 'workspace'],
    ['team-config'],
    ['team-configs'],
    ['kpi-weights'],
    ['balanced-scorecard'],
  ]));
  expect(client.getQueryState(['reports', 'list'])?.isInvalidated).not.toBe(true);
  expect(client.getQueryState(['performance', 'bounded-records', 'kept'])?.isInvalidated).toBe(true);

  fireEvent.click(screen.getByRole('button', { name: 'Rollback' }));
  expect(screen.getByRole('group', { name: 'Rollback confirmation' })).toHaveTextContent(/restores the saved before-apply values/i);
  fireEvent.click(screen.getByRole('button', { name: 'Keep current records' }));
  expect(calls('/rollback', 'POST')).toHaveLength(0);
  expect(screen.getByText(/Revision revision-1/)).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Rollback' }));
  fireEvent.click(screen.getByRole('button', { name: 'Restore saved values' }));
  expect(await screen.findByText(/No older approved version was reactivated/)).toBeInTheDocument();
  expect(performanceRefresh).toHaveBeenCalledTimes(2);
  const rollbackCall = calls('/rollback', 'POST')[0];
  expect(String(rollbackCall[0])).toContain('/revisions/revision-1/rollback');
  expect(rollbackCall[1]?.body).toBeUndefined();
  expect(await screen.findByText(/rolled_back/)).toBeInTheDocument();
  expect(screen.getByText(/Version 2/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Rollback' })).not.toBeInTheDocument();
});

it('does not preview unsaved edits and clears a previous proof', async () => {
  october();
  const user = userEvent.setup();
  renderPanel();
  expect(await screen.findByLabelText('QualityErrors target')).toHaveValue('55');
  await waitFor(() => expect(screen.getByRole('button', { name: 'Impact preview' })).toBeEnabled());
  await user.click(screen.getByRole('button', { name: 'Impact preview' }));
  expect(await screen.findByText('E001')).toBeInTheDocument();
  await user.clear(screen.getByLabelText('QualityErrors target'));
  await user.type(screen.getByLabelText('QualityErrors target'), '40');
  expect(screen.getByText('Save the draft before impact preview or approval. Unsaved edits are not previewed.')).toBeInTheDocument();
  expect(screen.queryByText('E001')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Impact preview' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Impact preview' }));
  expect(calls('/impact-preview', 'POST')).toHaveLength(1);
});

it('describes a zero-record validation without inventing an employee score', async () => {
  october();
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json(periodData(55));
    if (href.includes('/impact-preview')) {
      return json(impactProof({
        zero_affected: true,
        affected_count: 0,
        scored_employees: 0,
        changed_count: 0,
        unchanged_count: 0,
        comparisons: [],
        conflicts: [],
      }));
    }
    return json(draft);
  });
  renderPanel();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Impact preview' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Impact preview' }));
  expect(await screen.findByText(/not an employee impact/)).toBeInTheDocument();
  expect(screen.queryByRole('table', { name: 'Before and after scores' })).not.toBeInTheDocument();
  expect(screen.queryByText(/sample score/i)).not.toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled());
});

it('pages nine stored employees eight at a time', async () => {
  october();
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json(periodData(55));
    if (href.includes('/impact-preview')) {
      return json(impactProof({
        affected_count: 9,
        scored_employees: 9,
        changed_count: 9,
        unchanged_count: 0,
        comparisons: Array.from({ length: 9 }, (_, index) => comparison(`E${String(index + 1).padStart(2, '0')}`)),
      }));
    }
    return json(draft);
  });
  renderPanel();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Impact preview' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Impact preview' }));
  expect(await screen.findByText('E01')).toBeInTheDocument();
  expect(screen.queryByText('E09')).not.toBeInTheDocument();
  expect(screen.getByText('Page 1 of 2')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Next impact page' }));
  expect(screen.getByText('E09')).toBeInTheDocument();
  expect(screen.queryByText('E01')).not.toBeInTheDocument();
});

it('clears proof and keeps the target when approval reports a stale preview', async () => {
  october();
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json(periodData(55));
    if (href.includes('/impact-preview')) return json(impactProof());
    if (href.includes('/approve')) return json({ message: 'Impact preview is stale because the rules changed.', code: 'stale_preview' }, false);
    return json(draft);
  });
  renderPanel();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Impact preview' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Impact preview' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('stale_preview');
  expect(screen.queryByText('E001')).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('55');
  expect(calls('/approve', 'POST')).toHaveLength(1);
  expect(calls('/evaluation/apply', 'POST')).toHaveLength(0);
});

it('resumes an existing draft unchanged and does not overwrite it on a 409', async () => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 6, 15));
  let resumed = false;
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) {
      return json({
        versions: resumed
          ? [
            { id: 'approved-july', status: 'approved', version_number: 2, checksum: 'sum-approved', lines: [{ ...line, target: 55 }] },
            { id: 'draft-july', status: 'draft', version_number: 3, checksum: 'sum-draft', source_version_id: 'approved-july', source_checksum: 'sum-approved', lines: [{ ...line, target: 70 }] },
          ]
          : [{ id: 'approved-july', status: 'approved', version_number: 2, checksum: 'sum-approved', lines: [{ ...line, target: 55 }] }],
      });
    }
    if (href.includes('/revise')) {
      resumed = true;
      return json({
        id: 'draft-july',
        status: 'draft',
        version_number: 3,
        checksum: 'sum-draft',
        source_version_id: 'approved-july',
        source_checksum: 'sum-approved',
        resumed: true,
        lines: [{ ...line, target: 70 }],
      });
    }
    return json(draft);
  });
  const view = renderPanel();
  expect(await screen.findByLabelText('QualityErrors target')).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Revise this month' }));
  expect(await screen.findByText(/Existing draft resumed unchanged/)).toBeInTheDocument();
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('70');
  expect(screen.getByText(/Version 2/)).toBeInTheDocument();
  view.unmount();

  resumed = false;
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json({ versions: [{ id: 'approved-july', status: 'approved', version_number: 2, checksum: 'sum-approved', lines: [{ ...line, target: 55 }] }] });
    if (href.includes('/revise')) return json({ message: 'A draft already exists for this month and was not overwritten.', code: 'draft_exists' }, false);
    return json(draft);
  });
  renderPanel();
  expect(await screen.findByLabelText('QualityErrors target')).toHaveValue('55');
  fireEvent.click(screen.getByRole('button', { name: 'Revise this month' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('draft_exists');
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('55');
  expect(screen.getByLabelText('QualityErrors target')).toBeDisabled();
  expect(screen.getAllByText(/Version 2/).length).toBe(1);
});

it('shows a blocked formula and a period scope that overrides the catalog', async () => {
  october();
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods') && href.includes('month=10')) {
      return json({
        versions: [{ ...draft, lines: [{ ...line, direction: 'custom_index', target_mode: 'formula' }] }],
      });
    }
    return json(draft);
  });
  const view = renderPanel();
  expect(await screen.findByLabelText('QualityErrors direction')).toHaveValue('custom_index');
  expect(screen.getAllByText(/This formula is blocked in this release/)).toHaveLength(2);
  expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  expect(mocks.fetchWithRole.mock.calls.filter((call) => call[1]?.method === 'PATCH')).toHaveLength(0);
  view.unmount();

  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) {
      return json({
        versions: [draft],
        scope: { readiness: 'blocked', block_reason: 'Period scope is outside the supported rollout.', history_note: 'Not every template is supported.' },
      });
    }
    return json(draft);
  });
  renderPanel();
  expect(await screen.findByText(/Period scope is outside the supported rollout/)).toBeInTheDocument();
  expect(screen.getByText(/Not every template is supported/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Impact preview' })).not.toBeInTheDocument();
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

it('does not apply a save or a late impact for the previous month to the month now on screen', async () => {
  let releaseSave: (value: { lines?: Array<{ target?: number }> }) => void = () => {};
  let releaseImpact: (value: unknown) => void = () => {};
  let julyTarget = 55;
  mocks.fetchWithRole.mockImplementation(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json(periodData(monthOf(href) === '8' ? 80 : julyTarget));
    if (href.includes('/impact-preview')) return json(await new Promise((resolve) => { releaseImpact = resolve; }));
    if (init?.method === 'PATCH') {
      return json(await new Promise((resolve) => {
        releaseSave = (value) => {
          julyTarget = value.lines?.[0]?.target ?? julyTarget;
          resolve(value);
        };
      }));
    }
    return json(draft);
  });
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 6, 15));
  const { client } = renderPanel();
  expect(await screen.findByDisplayValue('55')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  fireEvent.change(screen.getByLabelText('Reporting month'), { target: { value: '8' } });
  expect(await screen.findByDisplayValue('80')).toBeInTheDocument();
  releaseSave({ ...draft, lines: [{ ...line, target: 99 }] });
  await act(async () => { await Promise.resolve(); });
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('80');
  expect(screen.queryByText('Draft saved.')).not.toBeInTheDocument();
  expect(calls('/drafts/draft-1', 'PATCH')).toHaveLength(1);

  fireEvent.change(screen.getByLabelText('Reporting month'), { target: { value: '7' } });
  expect(await screen.findByDisplayValue('99')).toBeInTheDocument();
  const invalidate = vi.spyOn(client, 'invalidateQueries');
  fireEvent.click(screen.getByRole('button', { name: 'Impact preview' }));
  await waitFor(() => expect(calls('/impact-preview', 'POST')).toHaveLength(1));
  fireEvent.change(screen.getByLabelText('Reporting month'), { target: { value: '8' } });
  expect(await screen.findByDisplayValue('80')).toBeInTheDocument();
  releaseImpact(impactProof({ version_id: 'draft-1', month: 7, comparisons: [comparison('EJULY')] }));
  await act(async () => { await Promise.resolve(); });
  expect(screen.queryByText('EJULY')).not.toBeInTheDocument();
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('80');
  expect(invalidate).not.toHaveBeenCalled();
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
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled());
  const save = screen.getByRole('button', { name: 'Save draft' });
  fireEvent.click(save);
  fireEvent.click(save);
  await waitFor(() => expect(mocks.fetchWithRole.mock.calls.filter((call) => call[1]?.method === 'PATCH')).toHaveLength(1));
  releaseSave(draft);
});

it('sends one apply and one rollback when the confirmation is activated twice', async () => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 6, 15));
  let releaseApply: () => void = () => {};
  let releaseRollback: () => void = () => {};
  const approved = { ...draft, id: 'approved-july', status: 'approved', version_number: 4, checksum: 'sum-approved' };
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) {
      return json({
        versions: [approved],
        revisions: [{ id: 'revision-9', version_id: 'approved-july', status: 'active', affected_count: 2, can_rollback: true }],
      });
    }
    if (href.includes('/evaluation/apply')) return json(await new Promise((resolve) => { releaseApply = () => resolve({ revision_id: 'revision-9', applied_count: 2 }); }));
    if (href.includes('/rollback')) return json(await new Promise((resolve) => { releaseRollback = () => resolve({ revision_id: 'revision-9', status: 'rolled_back', restored_basis: [], restored_revision_id: null }); }));
    return json(approved);
  });
  renderPanel();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Apply' })).toBeEnabled());
  const applyButton = screen.getByRole('button', { name: 'Apply' });
  fireEvent.click(applyButton);
  fireEvent.click(applyButton);
  await waitFor(() => expect(calls('/evaluation/apply', 'POST')).toHaveLength(1));
  releaseApply();
  fireEvent.click(await screen.findByRole('button', { name: 'Rollback' }));
  const restore = screen.getByRole('button', { name: 'Restore saved values' });
  fireEvent.click(restore);
  fireEvent.click(restore);
  await waitFor(() => expect(calls('/rollback', 'POST')).toHaveLength(1));
  expect(calls('/rollback', 'POST')[0][1]?.body).toBeUndefined();
  releaseRollback();
});

it('keeps history and the target when rollback reports evidence_changed', async () => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 6, 15));
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) {
      return json({
        versions: [{ ...draft, id: 'approved-july', status: 'approved', version_number: 4, checksum: 'sum-approved' }],
        revisions: [{ id: 'revision-9', version_id: 'approved-july', status: 'active', affected_count: 2, can_rollback: true }],
      });
    }
    if (href.includes('/rollback')) return json({ message: 'Stored evidence no longer matches the applied snapshot. Rollback made no changes.', code: 'evidence_changed' }, false);
    return json(draft);
  });
  renderPanel();
  expect(await screen.findByText(/Revision revision-9 · active · version approved-july · 2 records/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Rollback' }));
  fireEvent.click(screen.getByRole('button', { name: 'Restore saved values' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('evidence_changed');
  expect(screen.getByText(/records and history were left untouched/)).toBeInTheDocument();
  expect(screen.getByText(/Revision revision-9 · active/)).toBeInTheDocument();
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('55');
  expect(calls('/rollback', 'POST')).toHaveLength(1);
});

it('does not retry approval when the shared query client would retry a mutation', async () => {
  october();
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json({ versions: [draft] });
    if (href.includes('/impact-preview')) return json(impactProof());
    if (href.includes('/approve')) return json('Approval failed', false);
    return json(draft);
  });
  renderPanel(true);
  await waitFor(() => expect(screen.getByRole('button', { name: 'Impact preview' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Impact preview' }));
  await waitFor(() => expect(screen.getByRole('button', { name: 'Approve' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Approve' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Approval failed');
  expect(calls('/approve', 'POST')).toHaveLength(1);
  expect(performanceRefresh).not.toHaveBeenCalled();
});

it('does not refresh committed performance data when apply fails', async () => {
  october();
  const approved = { ...draft, id: 'approved-oct', status: 'approved', version_number: 2, checksum: 'sum-approved' };
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json({ versions: [approved], revisions: [] });
    if (href.includes('/evaluation/apply')) return json('Apply failed', false);
    return json(approved);
  });
  const { client } = renderPanel();
  client.setQueryData(['performance', 'bounded-records', 'kept'], { score: 79.82, target: 0.65 });
  expect(await screen.findByRole('button', { name: 'Apply' })).toBeEnabled();
  fireEvent.click(screen.getByRole('button', { name: 'Apply' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Apply failed');
  expect(performanceRefresh).not.toHaveBeenCalled();
  expect(client.getQueryData(['performance', 'bounded-records', 'kept'])).toEqual({ score: 79.82, target: 0.65 });
  expect(client.getQueryState(['performance', 'bounded-records', 'kept'])?.isInvalidated).not.toBe(true);
});

it('shows a blocked scope instead of treating it as supported', async () => {
  const user = userEvent.setup();
  renderPanel();
  await screen.findByRole('option', { name: /Future Desk/ });
  await user.selectOptions(screen.getByLabelText('Evaluation scope'), 'scope-2');
  expect(await screen.findByText(/No supported importer/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
});
