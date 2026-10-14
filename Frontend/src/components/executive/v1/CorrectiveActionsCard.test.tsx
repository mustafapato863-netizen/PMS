import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import type { ExecutiveActionItem, ExecutiveCorrectiveActions, ExecutivePeriod } from '../../../features/executive/types';
import CorrectiveActionsCard from './CorrectiveActionsCard';

const period = { key: '2026-10', year: 2026, month: 'October' } as ExecutivePeriod;

function item(overrides: Partial<ExecutiveActionItem> & { id: string }): ExecutiveActionItem {
  return {
    title: 'Coaching',
    team: 'Inbound',
    region: 'EGY',
    employee_name: 'Sara Ahmed',
    owner: null,
    due_date: null,
    status: 'Open',
    follow_up_state: null,
    action_type: 'Coaching',
    action_text: 'Coach on hold time and call opening script',
    root_cause: 'Hold time above target',
    ...overrides,
  };
}

function data(rows: ExecutiveActionItem[], summary: Partial<ExecutiveCorrectiveActions['summary']> = {}): ExecutiveCorrectiveActions {
  return {
    summary: { as_of: '2026-10-14', open: rows.length, overdue: 0, due_this_week: 0, closed_in_month: 0, ...summary },
    actions: rows.slice(0, 4),
    rows,
  };
}

const overdueRow = item({ id: 'o1', employee_name: 'Omar Khalid', due_date: '2026-10-10', follow_up_state: 'overdue', owner: { id: 'u1', name: 'Hany Mostafa' }, action_text: 'Review rejection reasons\nwith the RCM lead' });
const weekRow = item({ id: 'w1', employee_name: 'Lina Nasser', due_date: '2026-10-16', follow_up_state: 'due_this_week', action_type: 'Monitor', action_text: 'Monitor submission accuracy' });
const undatedRow = item({ id: 'n1', employee_name: 'Youssef Hany', action_text: 'Training on the error checklist' });
const closedRow = item({ id: 'c1', employee_name: 'Mona Adel', status: 'Completed', action_text: 'Finished coaching', completed_at: '2026-10-02T09:00:00Z' });

function renderCard(props: Partial<Parameters<typeof CorrectiveActionsCard>[0]> & { rows: ExecutiveActionItem[] }) {
  const { rows, ...rest } = props;
  return render(<MemoryRouter><CorrectiveActionsCard
    data={data(rows)}
    effective={period}
    variant="company"
    {...rest}
  /></MemoryRouter>);
}

function rowsOf() {
  return screen.getAllByTestId('action-row');
}

describe('CorrectiveActionsCard rows', () => {
  it('shows the employee with the team under it, the action type and first line, the reason and the owner', () => {
    renderCard({ rows: [overdueRow] });
    const row = rowsOf()[0];
    expect(within(row).getByRole('link', { name: 'Omar Khalid' })).toBeInTheDocument();
    expect(within(row).getByText('Inbound')).toBeInTheDocument();
    expect(within(row).getByText('Coaching')).toBeInTheDocument();
    expect(within(row).getByText('Review rejection reasons')).toBeInTheDocument();
    expect(within(row).getByText('Hold time above target')).toBeInTheDocument();
    expect(within(row).getByText('Hany Mostafa')).toBeInTheDocument();
  });

  it('shows Unassigned and No due date when the action has neither', () => {
    renderCard({ rows: [undatedRow] });
    const row = rowsOf()[0];
    expect(within(row).getByText('Unassigned')).toBeInTheDocument();
    expect(within(row).getByText('No due date')).toBeInTheDocument();
  });

  it('marks an overdue due date with a screen-reader cue, and not an open one', () => {
    renderCard({ rows: [overdueRow, weekRow] });
    const [overdue, week] = rowsOf();
    expect(within(overdue).getByText('(overdue)')).toBeInTheDocument();
    expect(within(week).queryByText('(overdue)')).not.toBeInTheDocument();
  });

  it('shows one status control per row: a read-only pill for viewers, a select for editors', () => {
    const { unmount } = renderCard({ rows: [weekRow] });
    expect(within(rowsOf()[0]).queryByRole('combobox')).not.toBeInTheDocument();
    expect(within(rowsOf()[0]).getAllByText('Due this week')).toHaveLength(1);
    unmount();

    renderCard({ rows: [weekRow], canEdit: true, onStatusChange: vi.fn().mockResolvedValue(undefined) });
    const select = within(rowsOf()[0]).getByRole('combobox', { name: /Status for Monitor submission accuracy/ });
    expect(select).toBeInTheDocument();
    expect(within(rowsOf()[0]).queryByText('Due this week')).not.toBeInTheDocument();
  });
});

describe('CorrectiveActionsCard expand', () => {
  it('opens the full action text from a keyboard-reachable button and closes it again', async () => {
    const user = userEvent.setup();
    renderCard({ rows: [overdueRow] });
    const toggle = within(rowsOf()[0]).getByRole('button', { name: /Show full action for Omar Khalid/ });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText(/with the RCM lead/)).not.toBeInTheDocument();

    toggle.focus();
    await user.keyboard('{Enter}');
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const detail = document.getElementById(toggle.getAttribute('aria-controls') ?? '');
    expect(detail).toHaveTextContent('Review rejection reasons');
    expect(detail).toHaveTextContent('with the RCM lead');

    await user.keyboard('{Enter}');
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
  });
});

describe('CorrectiveActionsCard tiles as filters', () => {
  it('filters to overdue actions from the tile, marks it active, and returns to all', async () => {
    const user = userEvent.setup();
    renderCard({ rows: [overdueRow, weekRow, undatedRow] });
    expect(rowsOf()).toHaveLength(3);

    const overdueTile = screen.getByTestId('action-tile-overdue');
    await user.click(overdueTile);
    expect(overdueTile).toHaveAttribute('aria-pressed', 'true');
    expect(rowsOf()).toHaveLength(1);
    expect(screen.getByText('1 overdue')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Show all actions' }));
    expect(overdueTile).toHaveAttribute('aria-pressed', 'false');
    expect(rowsOf()).toHaveLength(3);
  });

  it('shows the closed-in-month tile in company views', () => {
    renderCard({ rows: [closedRow] });
    expect(screen.getByTestId('action-tile-closed-in-october')).toBeInTheDocument();
  });

  it('keeps at most ten rows until Show all is pressed', async () => {
    const user = userEvent.setup();
    const many = Array.from({ length: 12 }, (_, index) => item({ id: `r${index}`, employee_name: `Agent ${index}`, action_text: `Action ${index}` }));
    renderCard({ rows: many });
    expect(rowsOf()).toHaveLength(10);
    await user.click(screen.getByRole('button', { name: 'Show all 12' }));
    expect(rowsOf()).toHaveLength(12);
  });
});
