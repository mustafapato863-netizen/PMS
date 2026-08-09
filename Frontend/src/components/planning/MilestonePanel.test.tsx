import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { PlanDetail } from '../../features/planning/types';
import MilestonePanel from './MilestonePanel';

const mutations = vi.hoisted(() => ({ create: vi.fn(), update: vi.fn(), remove: vi.fn() }));

vi.mock('../../hooks/api/usePlanning', () => ({
  useCreateMilestone: () => ({ mutateAsync: mutations.create, isPending: false, error: null }),
  useUpdateMilestone: () => ({ mutateAsync: mutations.update, isPending: false, error: null }),
  useDeleteMilestone: () => ({ mutateAsync: mutations.remove, isPending: false, error: null }),
}));

const detail: PlanDetail = {
  id: 'plan-1', name: 'Improve response time', scope: 'Marketing', scope_type: 'Team', team: 'Marketing', performance_level: 'Employee',
  status: 'In Progress', stored_status: 'In Progress', risk_reasons: [], progress: { overall: 0, components: {}, explanation: '' },
  owner: { id: 'owner-1', name: 'manager' }, period: '20 Jul 2026 – 20 Oct 2026', due_date: '2026-10-20',
  counts: { objectives: 1, actions: 1, kpis: 1, milestones: 1, notes: 0 }, updated_at: null,
  summary: { scope_type: 'Team', scope_name: 'Marketing', period: '20 Jul 2026 – 20 Oct 2026', owner: { id: 'owner-1', name: 'manager' }, baseline: 89, target: 4, current: 89, expected_impact: -85, actual_impact: null, unit: 'min', direction: 'lower_better', status_reason: null },
  objectives: [], actions: [], kpis: [], notes: [], linked_insights: [],
  milestones: [{ id: 'milestone-1', name: 'Review solution', due_date: '2026-08-15', status: 'Pending', completion_date: null, owner_id: 'owner-1', owner: 'manager', note: 'Validate the first step' }],
};

const owners = [{ id: 'owner-1', name: 'manager' }];

describe('MilestonePanel', () => {
  beforeEach(() => {
    mutations.create.mockReset().mockResolvedValue(detail);
    mutations.update.mockReset().mockResolvedValue(detail);
    mutations.remove.mockReset().mockResolvedValue({ ...detail, milestones: [] });
  });

  it('adds a solution step with an owner, due date, status and notes', async () => {
    const user = userEvent.setup();
    render(<MilestonePanel detail={{ ...detail, milestones: [] }} owners={owners} canEdit />);

    await user.click(screen.getByRole('button', { name: 'Add solution step' }));
    await user.type(screen.getByRole('textbox', { name: 'Solution step' }), 'Validate response-time fix');
    await user.clear(screen.getByLabelText('Milestone due date'));
    await user.type(screen.getByLabelText('Milestone due date'), '2026-08-20');
    await user.selectOptions(screen.getByLabelText('Milestone status'), 'In Progress');
    await user.type(screen.getByRole('textbox', { name: 'Milestone notes' }), 'Review the actual result');
    await user.click(screen.getByRole('button', { name: 'Add step' }));

    expect(mutations.create).toHaveBeenCalledWith({
      planId: 'plan-1',
      payload: {
        name: 'Validate response-time fix', due_date: '2026-08-20', owner_user_id: 'owner-1',
        status: 'In Progress', note: 'Review the actual result',
      },
    });
  }, 15_000);

  it('marks a milestone completed and can reopen it', async () => {
    const user = userEvent.setup();
    const { rerender } = render(<MilestonePanel detail={detail} owners={owners} canEdit />);

    await user.click(screen.getByRole('button', { name: 'Mark completed' }));
    expect(mutations.update).toHaveBeenCalledWith({ planId: 'plan-1', milestoneId: 'milestone-1', payload: { status: 'Completed' } });

    rerender(<MilestonePanel detail={{ ...detail, milestones: [{ ...detail.milestones[0], status: 'Completed', completion_date: '2026-07-20' }] }} owners={owners} canEdit />);
    await user.click(screen.getByRole('button', { name: 'Reopen' }));
    expect(mutations.update).toHaveBeenLastCalledWith({ planId: 'plan-1', milestoneId: 'milestone-1', payload: { status: 'Pending' } });
  });

  it('edits and deletes an existing milestone', async () => {
    const user = userEvent.setup();
    render(<MilestonePanel detail={detail} owners={owners} canEdit />);

    await user.click(screen.getByRole('button', { name: 'Edit Review solution' }));
    const name = screen.getByRole('textbox', { name: 'Solution step' });
    await user.clear(name);
    await user.type(name, 'Validate final solution');
    await user.selectOptions(screen.getByLabelText('Milestone status'), 'In Progress');
    await user.click(screen.getByRole('button', { name: 'Save changes' }));
    expect(mutations.update).toHaveBeenCalledWith(expect.objectContaining({
      planId: 'plan-1', milestoneId: 'milestone-1',
      payload: expect.objectContaining({ name: 'Validate final solution', status: 'In Progress' }),
    }));

    await user.click(screen.getByRole('button', { name: 'Delete Review solution' }));
    expect(screen.getByRole('alertdialog', { name: 'Delete this milestone?' })).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Delete milestone' }));
    expect(mutations.remove).toHaveBeenCalledWith({ planId: 'plan-1', milestoneId: 'milestone-1' });
  });
});
