import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';

import { EvaluationSettingsPanel } from './EvaluationSettingsPanel';
import { initialReportingPeriod } from './evaluationSettings';
import { periodQueryKey } from './monthlyCorrection';

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
  target: 0.55,
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
        lines: [{ ...line, target: body.month === 8 ? 0.65 : 0.7 }],
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
  expect(screen.queryByLabelText('QualityErrors target')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('QualityErrors weight')).not.toBeInTheDocument();
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
    lines: [{ ...line, target: 0.55 }],
  };
  const revised = {
    id: 'draft-july',
    status: 'draft',
    version_number: 3,
    checksum: 'sum-draft',
    source_version_id: 'approved-july',
    source_checksum: 'sum-approved',
    lines: [{ ...line, target: 0.55 }],
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
        conflicts: [{ record_id: 'rec-1', kpi_key: 'QualityErrors', workbook_target: 0.6, approved_target: 0.55 }],
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
  expect(screen.getByLabelText('QualityErrors weight')).toBeDisabled();
  expect(screen.getByLabelText('QualityErrors weight')).toHaveValue('100');
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
  expect(saved.expected_checksum).toBe('sum-draft');
  expect(saved.lines[0]).toMatchObject({ target: 0.4, weight: 1, direction: 'higher_better', target_mode: 'fixed' });
  expect(await screen.findByText('Draft saved.')).toBeInTheDocument();

  fireEvent.click(screen.getByRole('button', { name: 'Impact preview' }));
  expect(await screen.findByText(/2 stored records, 2 scored, 1 changed, 1 unchanged/)).toBeInTheDocument();
  const mismatches = screen.getByRole('table', { name: 'Fixed target mismatches' });
  expect(within(mismatches).getByText('60%')).toBeInTheDocument();
  expect(within(mismatches).getByText('55%')).toBeInTheDocument();
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
    if (href.includes('/periods')) return json(periodData(0.55));
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
    if (href.includes('/periods')) return json(periodData(0.55));
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
    if (href.includes('/periods')) return json(periodData(0.55));
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
            { id: 'approved-july', status: 'approved', version_number: 2, checksum: 'sum-approved', lines: [{ ...line, target: 0.55 }] },
            { id: 'draft-july', status: 'draft', version_number: 3, checksum: 'sum-draft', source_version_id: 'approved-july', source_checksum: 'sum-approved', lines: [{ ...line, target: 0.7 }] },
          ]
          : [{ id: 'approved-july', status: 'approved', version_number: 2, checksum: 'sum-approved', lines: [{ ...line, target: 0.55 }] }],
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
        lines: [{ ...line, target: 0.7 }],
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
    if (href.includes('/periods')) return json({ versions: [{ id: 'approved-july', status: 'approved', version_number: 2, checksum: 'sum-approved', lines: [{ ...line, target: 0.55 }] }] });
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
  pending.get('8')?.(periodData(0.8));
  expect(await screen.findByDisplayValue('80')).toBeInTheDocument();
  pending.get('7')?.(periodData(0.55));
  await act(async () => { await Promise.resolve(); });
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('80');
  expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled();
});

it('does not apply a save or a late impact for the previous month to the month now on screen', async () => {
  let releaseSave: (value: { lines?: Array<{ target?: number }> }) => void = () => {};
  let releaseImpact: (value: unknown) => void = () => {};
  let julyTarget = 0.55;
  mocks.fetchWithRole.mockImplementation(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json(periodData(monthOf(href) === '8' ? 0.8 : julyTarget));
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
  releaseSave({ ...draft, lines: [{ ...line, target: 0.99 }] });
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

it('labels the selected scope with the exact month admission, not the current catalog default', async () => {
  window.history.replaceState(null, '', '/settings?period=2026-08');
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [{ ...scope, readiness: 'blocked' }] });
    if (href.includes('/periods')) return json({
      versions: [draft],
      scope: { ...scope, readiness: monthOf(href) === '8' ? 'supported' : 'blocked', block_reason: 'This exact month is not admitted.' },
    });
    return json(draft);
  });
  renderPanel();
  expect(await screen.findByLabelText('QualityErrors target')).toBeEnabled();
  expect(screen.getByRole('option', { name: 'Coding · Employee' })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Reporting month'), { target: { value: '9' } });
  expect(await screen.findByText(/This exact month is not admitted/)).toBeInTheDocument();
  expect(screen.getByRole('option', { name: 'Coding · Employee · blocked' })).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save draft' })).not.toBeInTheDocument();
});

it('saves explicit percents as fractions and leaves other units and untouched precision unchanged', async () => {
  october();
  const preciseWeight = 0.1 + 0.2;
  const hours = { kpi_key: 'HandleTime', label: 'Handle time', weight: 0, direction: 'lower_better', target: 2.5, target_mode: 'fixed', unit: 'hours' };
  const count = { kpi_key: 'Calls', label: 'Rework percentage', weight: 0.6, direction: 'higher_better', target: 65, target_mode: 'fixed', unit: 'count' };
  const unknown = { kpi_key: 'Mystery', label: 'Mystery', weight: preciseWeight, direction: 'higher_better', target: 65, target_mode: 'fixed' };
  const workbook = { kpi_key: 'Quality', label: 'Quality', weight: 0.5, direction: 'higher_better', target: null, target_mode: 'workbook', unit: '%' };
  mocks.fetchWithRole.mockImplementation(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json({ versions: [{ ...draft, lines: [{ ...line, target: 0.65, weight: 1, target_mode: 'workbook' }, hours, count, unknown, workbook] }] });
    if (init?.method === 'PATCH') return json({ ...draft, lines: JSON.parse(String(init.body)).lines });
    return json(draft);
  });
  renderPanel();
  expect(await screen.findByLabelText('QualityErrors target')).toHaveValue('65');
  expect(screen.getByLabelText('QualityErrors weight')).toHaveValue('100');
  expect(screen.getByLabelText('HandleTime target')).toHaveValue('2.5');
  expect(screen.getByLabelText('HandleTime weight')).toHaveValue('0');
  expect(screen.getByLabelText('Calls target')).toHaveValue('65');
  expect(screen.getByLabelText('Calls weight')).toHaveValue('60');
  expect(screen.getByLabelText('Mystery target')).toHaveValue('65');
  expect(screen.getByText(/No unit was provided/)).toBeInTheDocument();
  expect(screen.getByLabelText('Quality target')).toHaveValue('');
  expect(screen.getByText(/Saved target: empty/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('QualityErrors target'), { target: { value: '70' } });
  expect(screen.getByLabelText('QualityErrors source')).toHaveValue('fixed');
  fireEvent.change(screen.getByLabelText('Calls weight'), { target: { value: '50' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await waitFor(() => expect(calls('/drafts/draft-1', 'PATCH')).toHaveLength(1));
  const saved = JSON.parse(String(calls('/drafts/draft-1', 'PATCH')[0][1]?.body));
  expect(saved.expected_checksum).toBe('sum-draft');
  const byKey = Object.fromEntries(saved.lines.map((item: { kpi_key: string }) => [item.kpi_key, item]));
  expect(byKey.QualityErrors).toMatchObject({ target: 0.7, weight: 1, target_mode: 'fixed' });
  expect(byKey.HandleTime).toMatchObject({ target: 2.5, weight: 0, unit: 'hours' });
  expect(byKey.Calls).toMatchObject({ target: 65, weight: 0.5, unit: 'count' });
  expect(byKey.Mystery.target).toBe(65);
  expect(byKey.Mystery.weight).toBe(preciseWeight);
  expect(byKey.Quality.target).toBeNull();
  expect(byKey.Quality).toMatchObject({ target_mode: 'workbook', weight: 0.5 });
});

it('does not save a blank or unfinished percent, and keeps the stored value visible', async () => {
  october();
  renderPanel();
  const target = await screen.findByLabelText('QualityErrors target');
  expect(target).toHaveValue('55');
  fireEvent.change(target, { target: { value: '' } });
  expect(target).toHaveValue('');
  expect(screen.getByText(/Saved target remains 55%/)).toBeInTheDocument();
  expect(screen.getByText(/Saved target: 55%/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  expect(calls('/drafts/draft-1', 'PATCH')).toHaveLength(0);
  fireEvent.change(screen.getByLabelText('QualityErrors target'), { target: { value: '0.' } });
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('0.');
  expect(screen.getByText(/not a finite number/)).toBeInTheDocument();
  expect(screen.getByText(/Saved target remains 55%/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  expect(calls('/drafts/draft-1', 'PATCH')).toHaveLength(0);
  fireEvent.change(screen.getByLabelText('QualityErrors target'), { target: { value: '0.1' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await waitFor(() => expect(calls('/drafts/draft-1', 'PATCH')).toHaveLength(1));
  const saved = JSON.parse(String(calls('/drafts/draft-1', 'PATCH')[0][1]?.body));
  expect(saved.expected_checksum).toBe('sum-draft');
  expect(saved.lines[0]).toMatchObject({ target: 0.001, weight: 1 });
});

it('discards an unfinished target when the reporting period changes', async () => {
  october();
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json(periodData(monthOf(href) === '8' ? 0.8 : 0.55));
    return json(draft);
  });
  renderPanel();
  expect(await screen.findByLabelText('QualityErrors target')).toHaveValue('55');
  fireEvent.change(screen.getByLabelText('QualityErrors target'), { target: { value: '0.' } });
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('0.');
  fireEvent.change(screen.getByLabelText('Reporting month'), { target: { value: '8' } });
  expect(await screen.findByLabelText('QualityErrors target')).toHaveValue('80');
  expect(screen.queryByDisplayValue('0.')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Reporting month'), { target: { value: '10' } });
  expect(await screen.findByLabelText('QualityErrors target')).toHaveValue('55');
  expect(screen.queryByDisplayValue('0.')).not.toBeInTheDocument();
});

it('scales conflict values only for a rule with an explicit percent unit', async () => {
  october();
  const hours = { kpi_key: 'HandleTime', label: 'Handle time', weight: 0, direction: 'lower_better', target: 2.5, target_mode: 'fixed', unit: 'hours' };
  const unknown = { kpi_key: 'Mystery', label: 'Mystery', weight: 0, direction: 'higher_better', target: 65, target_mode: 'fixed' };
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json({ versions: [{ ...draft, lines: [{ ...line, target: 0.55 }, hours, unknown] }] });
    if (href.includes('/impact-preview')) {
      return json(impactProof({
        conflicts: [
          { record_id: 'rec-1', kpi_key: 'QualityErrors', workbook_target: 0.6, approved_target: 0.55 },
          { record_id: 'rec-2', kpi_key: 'HandleTime', workbook_target: 2.5, approved_target: 3 },
          { record_id: 'rec-3', kpi_key: 'Mystery', workbook_target: 65, approved_target: 70 },
          { record_id: 'rec-4', kpi_key: 'Unlisted', workbook_target: 65, approved_target: 0.65 },
        ],
      }));
    }
    return json(draft);
  });
  renderPanel();
  await waitFor(() => expect(screen.getByRole('button', { name: 'Impact preview' })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: 'Impact preview' }));
  const mismatches = await screen.findByRole('table', { name: 'Fixed target mismatches' });
  expect(within(mismatches).getByText('60%')).toBeInTheDocument();
  expect(within(mismatches).getByText('55%')).toBeInTheDocument();
  expect(within(mismatches).getByText('2.5 hours')).toBeInTheDocument();
  expect(within(mismatches).getByText('3 hours')).toBeInTheDocument();
  expect(within(mismatches).getAllByText('65 (stored value, unit not provided)')).toHaveLength(2);
  expect(within(mismatches).getByText('70 (stored value, unit not provided)')).toBeInTheDocument();
  expect(within(mismatches).getByText('0.65 (stored value, unit not provided)')).toBeInTheDocument();
  expect(within(mismatches).queryByText('6500%')).not.toBeInTheDocument();
  expect(within(mismatches).queryByText('250%')).not.toBeInTheDocument();
});

it('keeps the captured checksum and percent scale when a refresh arrives during a dirty edit', async () => {
  october();
  let refreshed = false;
  mocks.fetchWithRole.mockImplementation(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) {
      if (refreshed) {
        return json({ versions: [{ ...draft, checksum: 'sum-refreshed', lines: [{ ...line, unit: 'hours', target: 9, weight: 0.25, direction: 'higher_better' }] }] });
      }
      return json({ versions: [{ ...draft, lines: [{ ...line, target: 0.55, weight: 1 }] }] });
    }
    if (init?.method === 'PATCH') {
      return json({ message: 'This draft changed after you opened it. Reload the draft before saving; no changes were made.', code: 'stale_draft' }, false);
    }
    return json(draft);
  });
  const { client } = renderPanel();
  const target = await screen.findByLabelText('QualityErrors target');
  fireEvent.change(screen.getByLabelText('QualityErrors direction'), { target: { value: 'lower_better' } });
  fireEvent.change(target, { target: { value: '70' } });
  expect(target).toHaveValue('70');
  const key = periodQueryKey('scope-1', 2026, 10);
  refreshed = true;
  await act(async () => {
    await client.invalidateQueries({ queryKey: key });
  });
  await waitFor(() => expect(client.getQueryData(key)).toMatchObject({ checksum: 'sum-refreshed' }));
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('70');
  expect(screen.getByLabelText('QualityErrors direction')).toHaveValue('lower_better');
  expect(screen.getByText(/Saved target: 55%/)).toBeInTheDocument();
  expect(screen.queryByText(/Saved target: 9 hours/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await waitFor(() => expect(calls('/drafts/draft-1', 'PATCH')).toHaveLength(1));
  const saved = JSON.parse(String(calls('/drafts/draft-1', 'PATCH')[0][1]?.body));
  expect(String(calls('/drafts/draft-1', 'PATCH')[0][0])).toContain('/drafts/draft-1');
  expect(saved.expected_checksum).toBe('sum-draft');
  expect(saved.lines[0]).toMatchObject({ target: 0.7, weight: 1, unit: '%', direction: 'lower_better', target_mode: 'fixed' });
  expect(await screen.findByRole('alert')).toHaveTextContent('stale_draft');
  expect(screen.getByText(/Reload the draft or discard your edits/)).toBeInTheDocument();
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('70');
  expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  expect(calls('/drafts/draft-1', 'PATCH')).toHaveLength(1);
  const cached = client.getQueryData(key) as { checksum: string; lines: Array<{ target: number; unit?: string }> };
  expect(cached.checksum).toBe('sum-refreshed');
  expect(cached.lines[0]).toMatchObject({ target: 9, unit: 'hours' });
  fireEvent.click(screen.getByRole('button', { name: 'Discard edits' }));
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('9');
  expect(screen.queryByDisplayValue('70')).not.toBeInTheDocument();
  expect(calls('/drafts/draft-1', 'PATCH')).toHaveLength(1);
});

it('does not write a different version when the open draft changes during editing', async () => {
  october();
  let refreshed = false;
  mocks.fetchWithRole.mockImplementation(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) {
      return json({ versions: [refreshed ? { ...draft, id: 'draft-other', checksum: 'sum-other' } : draft] });
    }
    if (init?.method === 'PATCH') return json({ ...draft, id: 'draft-other', checksum: 'sum-other', lines: JSON.parse(String(init.body)).lines });
    return json(draft);
  });
  const { client } = renderPanel();
  expect(await screen.findByLabelText('QualityErrors target')).toHaveValue('55');
  fireEvent.change(screen.getByLabelText('QualityErrors target'), { target: { value: '70' } });
  const key = periodQueryKey('scope-1', 2026, 10);
  refreshed = true;
  await act(async () => {
    await client.invalidateQueries({ queryKey: key });
  });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled());
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('70');
  expect(screen.getByText(/will not write that other version/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  expect(mocks.fetchWithRole.mock.calls.filter((call) => call[1]?.method === 'PATCH')).toHaveLength(0);
  fireEvent.click(screen.getByRole('button', { name: 'Discard edits' }));
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('55');
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await waitFor(() => expect(calls('/drafts/draft-other', 'PATCH')).toHaveLength(1));
  const saved = JSON.parse(String(calls('/drafts/draft-other', 'PATCH')[0][1]?.body));
  expect(saved.expected_checksum).toBe('sum-other');
  expect(calls('/drafts/draft-1', 'PATCH')).toHaveLength(0);
});

it('does not send an empty checksum when the draft has none', async () => {
  october();
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) return json({ versions: [{ ...draft, checksum: '   ' }] });
    return json(draft);
  });
  renderPanel();
  expect(await screen.findByLabelText('QualityErrors target')).toHaveValue('55');
  expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
  expect(screen.getByText(/An empty checksum is not sent/)).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  fireEvent.change(screen.getByLabelText('QualityErrors target'), { target: { value: '70' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  expect(mocks.fetchWithRole.mock.calls.filter((call) => call[1]?.method === 'PATCH')).toHaveLength(0);
  expect(screen.getByLabelText('QualityErrors target')).toHaveValue('70');
});

it('does not reuse a checksum from another month or from a revise response that omitted one', async () => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(new Date(2026, 6, 15));
  mocks.fetchWithRole.mockImplementation(async (url: string, init?: RequestInit) => {
    const href = String(url);
    const month = monthOf(href);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) {
      if (month === '8') return json({ versions: [{ ...draft, id: 'draft-august', checksum: 'sum-august', lines: [{ ...line, target: 0.8 }] }] });
      return json({ versions: [{ ...draft, id: 'draft-july', checksum: 'sum-july', lines: [{ ...line, target: 0.55 }] }] });
    }
    if (init?.method === 'PATCH') {
      const id = href.includes('draft-august') ? 'draft-august' : 'draft-july';
      return json({ ...draft, id, checksum: id === 'draft-august' ? 'sum-august-saved' : 'sum-july-saved', lines: JSON.parse(String(init.body)).lines });
    }
    return json(draft);
  });
  renderPanel();
  expect(await screen.findByLabelText('QualityErrors target')).toHaveValue('55');
  fireEvent.change(screen.getByLabelText('QualityErrors target'), { target: { value: '40' } });
  fireEvent.change(screen.getByLabelText('Reporting month'), { target: { value: '8' } });
  expect(await screen.findByLabelText('QualityErrors target')).toHaveValue('80');
  expect(screen.queryByDisplayValue('40')).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('QualityErrors target'), { target: { value: '70' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  await waitFor(() => expect(calls('/drafts/draft-august', 'PATCH')).toHaveLength(1));
  const august = JSON.parse(String(calls('/drafts/draft-august', 'PATCH')[0][1]?.body));
  expect(august.expected_checksum).toBe('sum-august');
  expect(august.lines[0]).toMatchObject({ target: 0.7, weight: 1 });
  expect(calls('/drafts/draft-july', 'PATCH')).toHaveLength(0);
  const patchesBeforeRevise = mocks.fetchWithRole.mock.calls.filter((call) => call[1]?.method === 'PATCH').length;

  let revised = false;
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope] });
    if (href.includes('/periods')) {
      const approvedOnly = { id: 'approved-july', status: 'approved', version_number: 2, checksum: 'sum-approved', lines: [{ ...line, target: 0.55 }] };
      return json({
        versions: revised
          ? [approvedOnly, { id: 'draft-july', status: 'draft', version_number: 3, lines: [{ ...line, target: 0.55 }] }]
          : [approvedOnly],
      });
    }
    if (href.includes('/revise')) {
      revised = true;
      return json({ id: 'draft-july', status: 'draft', version_number: 3, lines: [{ ...line, target: 0.55 }] });
    }
    return json(draft);
  });
  fireEvent.change(screen.getByLabelText('Reporting month'), { target: { value: '7' } });
  await waitFor(() => expect(screen.getByLabelText('QualityErrors target')).toBeDisabled());
  fireEvent.click(screen.getByRole('button', { name: 'Revise this month' }));
  expect(await screen.findByText(/Revision draft opened for this month/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Save draft' })).toBeDisabled();
  expect(screen.getByText(/An empty checksum is not sent/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('QualityErrors target'), { target: { value: '40' } });
  fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
  expect(mocks.fetchWithRole.mock.calls.filter((call) => call[1]?.method === 'PATCH')).toHaveLength(patchesBeforeRevise);
});
