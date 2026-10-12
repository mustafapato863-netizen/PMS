import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { EvaluationSettingsPanel } from './EvaluationSettingsPanel';

const mocks = vi.hoisted(() => ({ fetchWithRole: vi.fn() }));

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({ role: 'Admin', fetchWithRole: mocks.fetchWithRole }),
}));
vi.mock('../../hooks/usePerformanceData', () => ({
  refreshPerformanceData: vi.fn(),
}));

const CODING = { id: 'scope-coding', display_name: 'Coding', performance_level: 'Employee', position_name: '', readiness: 'supported', supported: true };
const SALES = { id: 'scope-sales', display_name: 'Sales', performance_level: 'Managerial', position_name: '', readiness: 'supported', supported: true };
const CATALOG = [CODING, SALES];

function json(data: unknown) {
  return { ok: true, status: 200, json: async () => ({ success: true, data }) };
}

beforeEach(() => {
  mocks.fetchWithRole.mockReset();
  mocks.fetchWithRole.mockImplementation(async (url: string) => {
    const href = String(url);
    if (href.includes('/apply-jobs/capabilities')) return json({ enabled: false });
    if (href.includes('/catalog')) return json({ scopes: CATALOG });
    if (href.includes('/periods')) {
      const scopeId = new URL(href, window.location.origin).searchParams.get('scope_id');
      const scope = CATALOG.find((item) => item.id === scopeId) ?? null;
      return json({ scope, versions: [], revisions: [] });
    }
    return json({});
  });
});

afterEach(() => {
  window.history.replaceState(null, '', '/');
});

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <EvaluationSettingsPanel />
    </QueryClientProvider>,
  );
}

describe('EvaluationSettingsPanel ?scope= from the Overview', () => {
  it('opens the level and scope named in the link', async () => {
    window.history.replaceState(null, '', '/settings/evaluation?scope=scope-sales&year=2026&month=6');
    renderPanel();
    await waitFor(() => expect(screen.getByLabelText('Performance level')).toHaveValue('Managerial'));
    expect(screen.getByLabelText('Evaluation scope')).toHaveValue('scope-sales');
    expect(screen.getByLabelText('Reporting month')).toHaveValue('6');
  });

  it('changes nothing when the parameter is absent', async () => {
    window.history.replaceState(null, '', '/settings/evaluation?year=2026&month=6');
    renderPanel();
    await waitFor(() => expect(screen.getByLabelText('Evaluation scope')).toHaveValue('scope-coding'));
    expect(screen.getByLabelText('Performance level')).toHaveValue('Employee');
  });

  it('changes nothing when the scope is unknown', async () => {
    window.history.replaceState(null, '', '/settings/evaluation?scope=not-a-scope&year=2026&month=6');
    renderPanel();
    await waitFor(() => expect(screen.getByLabelText('Evaluation scope')).toHaveValue('scope-coding'));
    expect(screen.getByLabelText('Performance level')).toHaveValue('Employee');
  });
});
