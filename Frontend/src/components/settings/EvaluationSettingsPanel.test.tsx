import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

import { EvaluationSettingsPanel } from './EvaluationSettingsPanel';

const roleState = vi.hoisted(() => ({ role: 'Admin' as string }));

const mocks = vi.hoisted(() => ({
  fetchWithRole: vi.fn(),
}));

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

function json(data: unknown) {
  return { ok: true, json: async () => ({ success: true, data }) };
}

beforeEach(() => {
  roleState.role = 'Admin';
  mocks.fetchWithRole.mockImplementation(async (url: string, init?: RequestInit) => {
    const href = String(url);
    if (href.includes('/catalog')) return json({ scopes: [scope, blocked] });
    if (href.includes('/periods')) return json({ versions: [draft] });
    if (href.includes('/drafts') && init?.method === 'POST') {
      return json({ ...draft, id: 'draft-2', notes: 'Copied from the approved previous month.', lines: [{ ...draft.lines[0], target: 65 }] });
    }
    if (href.includes('/approve')) return json({ ...draft, status: 'approved' });
    if (href.includes('/apply')) return json({ revision_id: 'revision-1' });
    if (href.includes('/preview')) return json({ score: 92.31, rows: [{ kpi_key: 'QualityErrors', achievement: 0.923077 }] });
    return json({ lines: draft.lines });
  });
});

it('lets an admin copy a month and keeps approve separate from apply', async () => {
  const user = userEvent.setup();
  render(<EvaluationSettingsPanel />);
  expect(await screen.findByRole('button', { name: 'Approve' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Apply' })).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText('Reporting month'), '8');
  await user.click(screen.getByRole('button', { name: 'Copy previous month' }));
  expect(await screen.findByDisplayValue('65')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Approve' }));
  expect(await screen.findByText(/Existing scores were not recalculated/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Apply' }));
  expect(await screen.findByText(/Apply updated this month only/)).toBeInTheDocument();
});

it('does not let a non-admin approve', async () => {
  roleState.role = 'Manager';
  render(<EvaluationSettingsPanel />);
  expect(await screen.findByText('Approval is limited to Admin.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument();
});

it('shows a blocked scope instead of treating it as supported', async () => {
  const user = userEvent.setup();
  render(<EvaluationSettingsPanel />);
  await screen.findByLabelText('Evaluation scope');
  await user.selectOptions(screen.getByLabelText('Evaluation scope'), 'scope-2');
  expect(await screen.findByText(/No supported importer/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
});
