import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ManagerSelectorBar } from './ManagerSelectorBar';
import { buildSnapshots } from './managerSnapshots';

const managers = buildSnapshots(
  [
    {
      employee_id: 'SGHD70149',
      employee_name: 'Dina Samir',
      team_name: 'Marketing',
      role: 'Account Manager',
    },
    {
      employee_id: 'SGHD70150',
      employee_name: 'Mona Ali',
      team_name: 'Marketing',
      role: 'Quality Manager',
    },
  ],
  [],
);

describe('ManagerSelectorBar', () => {
  it('shows the active position and switches managers from the top selector', async () => {
    const onSelectManager = vi.fn();
    const user = userEvent.setup();

    render(
      <ManagerSelectorBar
        activeManager={managers[0]}
        managers={managers}
        teamName="Marketing"
        rosterOpen={false}
        onSelectManager={onSelectManager}
        onToggleRoster={() => undefined}
      />,
    );

    expect(screen.getByText('Account Manager')).toBeInTheDocument();
    await user.selectOptions(screen.getByRole('combobox', { name: 'Switch manager' }), 'SGHD70150');
    expect(onSelectManager).toHaveBeenCalledWith('SGHD70150');
  });

  it('exposes the detailed roster without showing it by default', async () => {
    const onToggleRoster = vi.fn();
    const user = userEvent.setup();

    render(
      <ManagerSelectorBar
        activeManager={managers[0]}
        managers={managers}
        teamName="Marketing"
        rosterOpen={false}
        onSelectManager={() => undefined}
        onToggleRoster={onToggleRoster}
      />,
    );

    const rosterButton = screen.getByRole('button', { name: 'View all (2)' });
    expect(rosterButton).toHaveAttribute('aria-expanded', 'false');
    await user.click(rosterButton);
    expect(onToggleRoster).toHaveBeenCalledOnce();
  });
});
