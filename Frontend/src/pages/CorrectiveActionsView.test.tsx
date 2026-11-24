import { MemoryRouter } from 'react-router-dom';
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PMSAction } from '../types';
import type { UnifiedTeamAction } from '../hooks/useActionStore';

const {
  getAllActions,
  deleteAction,
  roleState,
  downloadCorrectiveActionsPowerPoint,
  followUpState,
  teamActionsState,
  createTeamActionMutate,
  updateTeamActionStatusMutate,
  deleteTeamActionMutate,
} = vi.hoisted(() => ({
  getAllActions: vi.fn(),
  deleteAction: vi.fn(),
  roleState: { role: 'Admin' },
  downloadCorrectiveActionsPowerPoint: vi.fn(() => Promise.resolve()),
  followUpState: { overdue: 0, actions: [] as PMSAction[] },
  teamActionsState: { items: [] as UnifiedTeamAction[] },
  createTeamActionMutate: vi.fn(() => Promise.resolve({ success: true })),
  updateTeamActionStatusMutate: vi.fn(() => Promise.resolve({ success: true })),
  deleteTeamActionMutate: vi.fn(() => Promise.resolve({ success: true })),
}));

vi.mock('../hooks/useActionStore', () => ({
  useActionStore: () => ({ getAllActions, deleteAction }),
  useFollowUp: () => ({ data: { summary: { overdue: followUpState.overdue, due_soon: 0, open: 0, in_progress: 0, completed_this_month: 0, completion_rate: 0 }, actions: followUpState.actions }, isLoading: false, isError: false, refetch: vi.fn() }),
  useActionOwners: () => ({ data: [] }),
  useUpdateActionStatus: () => ({ mutateAsync: vi.fn() }),
  useAllTeamActions: () => ({ data: teamActionsState.items, isLoading: false, isError: false, refetch: vi.fn() }),
  useCreateTeamActionPlanItem: () => ({ mutateAsync: createTeamActionMutate, isPending: false }),
  useUpdateTeamActionStatus: () => ({ mutateAsync: updateTeamActionStatusMutate, isPending: false }),
  useDeleteTeamAction: () => ({ mutateAsync: deleteTeamActionMutate, isPending: false }),
}));

vi.mock('../context/RoleContext', () => ({
  useUserRole: () => ({ role: roleState.role }),
}));

vi.mock('../utils/correctiveActionPowerPoint', () => ({
  downloadCorrectiveActionsPowerPoint,
}));

import CorrectiveActionsView from './CorrectiveActionsView';

const actions: PMSAction[] = [
  {
    id: 'a1', employee_id: 'EMP-1', employee_name: 'Agent One', team: 'Inbound', month: 'June',
    action_type: 'Coaching', action_text: 'Review call handling', root_cause_note: 'AHT gap',
    created_by: 'Admin', created_at: '2026-06-15T10:00:00Z', synced: true,
  },
  {
    id: 'a2', employee_id: 'EMP-2', employee_name: 'Agent Two', team: 'Outbound', month: 'May',
    action_type: 'PIP', action_text: 'Improve productivity', root_cause_note: '',
    created_by: 'Executive', created_at: '2026-05-15T10:00:00Z', synced: false,
  },
];

describe('CorrectiveActionsView', () => {
  beforeEach(() => {
    getAllActions.mockReset();
    getAllActions.mockReturnValue(actions);
    deleteAction.mockReset();
    deleteAction.mockResolvedValue(true);
    roleState.role = 'Admin';
    followUpState.overdue = 0;
    followUpState.actions = [];
    teamActionsState.items = [];
    createTeamActionMutate.mockReset();
    createTeamActionMutate.mockResolvedValue({ success: true });
    updateTeamActionStatusMutate.mockReset();
    updateTeamActionStatusMutate.mockResolvedValue({ success: true });
    deleteTeamActionMutate.mockReset();
    deleteTeamActionMutate.mockResolvedValue({ success: true });
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: vi.fn(() => 'blob:actions') });
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() });
  });

  it('renders action records and summary metrics from the action store', () => {
    render(<MemoryRouter><CorrectiveActionsView /></MemoryRouter>);

    expect(screen.getByRole('heading', { name: 'Corrective Actions' })).toBeInTheDocument();
    expect(screen.getAllByText('Agent One').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Agent Two').length).toBeGreaterThan(0);
    expect(screen.getByText('Visible actions').parentElement).toHaveTextContent('2');
    expect(screen.getByText('Pending sync').parentElement).toHaveTextContent('1');
  });

  it('keeps function scope in the new design and the existing follow-up workflow', () => {
    const marketingAction: PMSAction = { ...actions[1], team: 'Marketing', status: 'Open', due_date: '2026-01-01', follow_up_state: 'overdue' };
    getAllActions.mockReturnValue([actions[0], marketingAction]);
    followUpState.actions = [{ ...actions[0], status: 'Open' }, marketingAction];
    render(<MemoryRouter initialEntries={['/corrective-actions?function=Marketing']}><CorrectiveActionsView /></MemoryRouter>);
    expect(screen.getAllByText('Agent Two').length).toBeGreaterThan(0);
    expect(screen.queryByText('Agent One')).not.toBeInTheDocument();
    expect(screen.getByTestId('action-tile-open')).toHaveTextContent('1');
    fireEvent.click(screen.getByRole('tab', { name: 'Follow-up' }));
    const board = screen.getByRole('region', { name: 'Action follow-up' });
    expect(within(board).getAllByRole('link', { name: 'Agent Two' })).toHaveLength(2);
    expect(within(board).queryByRole('link', { name: 'Agent One' })).not.toBeInTheDocument();
    expect(within(board).getByText('Open', { selector: 'p' }).parentElement).toHaveTextContent('1');
  });

  it('opens an Outlook draft addressed with the agent ID and action details', () => {
    render(<MemoryRouter><CorrectiveActionsView /></MemoryRouter>);

    const forwardLink = screen.getByRole('link', { name: 'Forward corrective action for Agent One in Outlook' });
    const outlookUrl = new URL(forwardLink.getAttribute('href') || '');

    expect(outlookUrl.origin).toBe('https://outlook.office.com');
    expect(outlookUrl.pathname).toBe('/mail/deeplink/compose');
    expect(outlookUrl.searchParams.get('to')).toBe('EMP-1');
    expect(outlookUrl.searchParams.get('subject')).toBe('Corrective action for Agent One (EMP-1)');
    expect(outlookUrl.searchParams.get('body')).toContain('Agent ID: EMP-1');
    expect(outlookUrl.searchParams.get('body')).toContain('Review call handling');
    expect(forwardLink).toHaveAttribute('target', '_blank');
  });

  it('filters records before exporting a PowerPoint document', async () => {
    render(<MemoryRouter><CorrectiveActionsView /></MemoryRouter>);

    fireEvent.click(screen.getByRole('button', { name: /Action filters/i }));
    const teamSelect = screen.getAllByLabelText('Filter by team').find((element) => element.tagName === 'SELECT');
    fireEvent.change(teamSelect as HTMLSelectElement, { target: { value: 'Inbound' } });
    expect(screen.getAllByText('Agent One').length).toBeGreaterThan(0);
    expect(screen.queryByText('Agent Two')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Export PowerPoint' }));
    await waitFor(() => expect(downloadCorrectiveActionsPowerPoint).toHaveBeenCalledWith(
      [actions[0]],
      { team: 'Inbound', month: 'All months', type: 'All types' },
    ));
  });

  it('shows the overdue count on the Follow-up tab', () => {
    followUpState.overdue = 4;
    render(<MemoryRouter><CorrectiveActionsView /></MemoryRouter>);
    expect(screen.getByRole('tab', { name: /Follow-up/ })).toHaveTextContent('4');
    expect(screen.getByLabelText('4 overdue')).toBeInTheDocument();
  });

  it('decodes __pms_meta__: root-cause notes in cards and Outlook deep-links', () => {
    getAllActions.mockReturnValue([
      {
        ...actions[0],
        root_cause_note:
          '__pms_meta__:{"main_issue":"AHT at 3.12 min vs 2.50 min","owner":"Inbound Lead","expected_impact":"+3.0 pts"}',
      },
    ]);
    render(<MemoryRouter><CorrectiveActionsView /></MemoryRouter>);

    expect(
      screen.getAllByText(/AHT at 3\.12 min vs 2\.50 min · Owner: Inbound Lead · Expected impact: \+3\.0 pts/),
    ).toHaveLength(2);
    expect(screen.queryByText(/__pms_meta__:/)).not.toBeInTheDocument();

    const forwardLink = screen.getByRole('link', { name: 'Forward corrective action for Agent One in Outlook' });
    const outlookUrl = new URL(forwardLink.getAttribute('href') || '');
    expect(outlookUrl.searchParams.get('body')).toContain(
      'AHT at 3.12 min vs 2.50 min · Owner: Inbound Lead · Expected impact: +3.0 pts',
    );
  });

  it('supports inline Delete confirmation, Escape dismiss, error state, and role gating', async () => {
    roleState.role = 'Viewer';
    const { rerender } = render(<MemoryRouter><CorrectiveActionsView /></MemoryRouter>);
    expect(screen.queryByTestId('delete-corrective-action-a1')).not.toBeInTheDocument();

    roleState.role = 'Performance Team';
    rerender(<MemoryRouter><CorrectiveActionsView /></MemoryRouter>);
    expect(screen.getByTestId('delete-corrective-action-a1')).toBeInTheDocument();

    // Open and close via Escape
    fireEvent.click(screen.getByTestId('delete-corrective-action-a1'));
    expect(screen.getByRole('alertdialog', { name: /Confirm delete corrective action for Agent One/i })).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
    expect(deleteAction).not.toHaveBeenCalled();

    // Failed delete displays inline error banner
    deleteAction.mockResolvedValueOnce(false);
    fireEvent.click(screen.getByTestId('delete-corrective-action-a1'));
    fireEvent.click(screen.getByRole('button', { name: 'Delete Action' }));
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/Failed to delete corrective action/i);
    });

    // Successful delete calls deleteAction(id, employee_id) and closes confirmation
    deleteAction.mockResolvedValueOnce(true);
    fireEvent.click(screen.getByRole('button', { name: 'Delete Action' }));
    await waitFor(() => {
      expect(deleteAction).toHaveBeenLastCalledWith('a1', 'EMP-1');
    });
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('shows Team actions tab beside Follow-up with whole-team actions and supports adding a new team action', async () => {
    teamActionsState.items = [
      {
        id: 'ta-1',
        card_id: 'coding-plan-1',
        kind: 'cohort_plan',
        team: 'Coding',
        region: 'EGY',
        month: 'October',
        year: 2026,
        title: 'Institute mandatory 100% pre-bill peer audit on OP Coding batches',
        target_kpi: 'Coding EGY Quality Errors Rate (11.3% → ≤ 5.0%)',
        scope_description: '',
        owner: 'Coding & Audit QA Lead',
        status: 'Open',
        due_date: null,
        expected_team_impact: 'Cut coding errors below 5%',
      },
      {
        id: 'ta-2',
        card_id: null,
        kind: 'overall_action',
        team: 'Inbound',
        region: 'UAE',
        month: 'October',
        year: 2026,
        title: 'Daily queue rebalance across peak inbound hours',
        target_kpi: '',
        scope_description: '',
        owner: 'Call Center Manager',
        status: 'In Progress',
        due_date: '2026-11-15',
        expected_team_impact: '',
      },
    ];

    render(<MemoryRouter><CorrectiveActionsView /></MemoryRouter>);

    const teamTab = screen.getByRole('tab', { name: /Team actions/i });
    expect(teamTab).toHaveTextContent('2');
    fireEvent.click(teamTab);

    const panel = screen.getByRole('region', { name: 'Team actions' });
    expect(within(panel).getByText('Team-Level Action Plans')).toBeInTheDocument();
    expect(within(panel).getByText('Institute mandatory 100% pre-bill peer audit on OP Coding batches')).toBeInTheDocument();
    expect(within(panel).getByText('Daily queue rebalance across peak inbound hours')).toBeInTheDocument();
    expect(within(panel).getByText('Whole-Team Action')).toBeInTheDocument();
    expect(within(panel).getByText('Team Summary Action')).toBeInTheDocument();

    // Add a new whole-team action
    fireEvent.click(within(panel).getByRole('button', { name: /Add Team Action/i }));
    const form = within(panel).getByRole('form', { name: 'Add whole-team action form' });
    fireEvent.change(within(form).getByLabelText(/Action plan title/i), {
      target: { value: 'Automate morning claim-queue partitioning' },
    });
    fireEvent.click(within(form).getByRole('button', { name: 'Save Team Action' }));
    await waitFor(() => {
      expect(createTeamActionMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Automate morning claim-queue partitioning',
          status: 'Open',
        }),
      );
    });
  });
});
