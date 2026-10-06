import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';

import type { User } from '../../types';
import { UserFormModal } from './UserFormModal';


it('submits an edited full name independently from the login username', async () => {
  const account: User = {
    id: 'user-1',
    name: 'Ahmed Essa',
    username: 'dr_ahmed_essa',
    role: 'Manager',
    is_active: true,
  };
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  const user = userEvent.setup();

  render(
    <UserFormModal
      open
      user={account}
      teams={[]}
      onClose={vi.fn()}
      onSubmit={onSubmit}
    />,
  );

  const fullName = screen.getByRole('textbox', { name: 'Full name' });
  await user.clear(fullName);
  await user.type(fullName, 'Dr. Ahmed Mohamed Essa');
  await user.click(screen.getByRole('button', { name: 'Save changes' }));

  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
    name: 'Dr. Ahmed Mohamed Essa',
    username: 'dr_ahmed_essa',
  }));
});

it('offers the General Manager role and hides the per-team checklist for it', async () => {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  const user = userEvent.setup();

  render(
    <UserFormModal
      open
      teams={[{ name: 'Marketing' }, { name: 'RCM' }]}
      onClose={vi.fn()}
      onSubmit={onSubmit}
    />,
  );

  const roleSelect = screen.getByRole('combobox', { name: 'Role' });
  expect(screen.getByRole('option', { name: 'General Manager' })).toBeInTheDocument();

  await user.selectOptions(roleSelect, 'Manager');
  expect(screen.getByRole('checkbox', { name: 'All branches' })).toBeInTheDocument();
  expect(screen.queryByText(/General manager \(all teams\)/)).not.toBeInTheDocument();
  expect(screen.getByRole('checkbox', { name: 'Marketing' })).toBeInTheDocument();

  await user.selectOptions(roleSelect, 'General Manager');
  expect(screen.queryByRole('checkbox', { name: 'All branches' })).not.toBeInTheDocument();
  expect(screen.queryByRole('checkbox', { name: 'Marketing' })).not.toBeInTheDocument();
  expect(screen.getByText('General Managers have access to all branches and functions.')).toBeInTheDocument();

  await user.type(screen.getByRole('textbox', { name: 'Full name' }), 'Gina Grant');
  await user.type(screen.getByRole('textbox', { name: 'Username' }), 'gina');
  await user.type(screen.getByLabelText(/Password/), 'secret-pass');
  await user.click(screen.getByRole('button', { name: 'Create user' }));

  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ role: 'General Manager', username: 'gina' }));
});


it('assigns selected functions to a Function Viewer', async () => {
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  const user = userEvent.setup();

  render(
    <UserFormModal
      open
      teams={[]}
      onClose={vi.fn()}
      onSubmit={onSubmit}
    />,
  );

  const roleSelect = screen.getByRole('combobox', { name: 'Role' });
  expect(screen.getByRole('option', { name: 'Function Viewer' })).toBeInTheDocument();
  await user.selectOptions(roleSelect, 'Function Viewer');
  await user.click(screen.getByRole('checkbox', { name: 'Marketing' }));
  await user.type(screen.getByRole('textbox', { name: 'Full name' }), 'Gina Grant');
  await user.type(screen.getByRole('textbox', { name: 'Username' }), 'gina');
  await user.type(screen.getByLabelText(/Password/), 'secret-pass');
  await user.click(screen.getByRole('button', { name: 'Create user' }));

  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
    role: 'Function Viewer',
    accessibleFunctions: ['Marketing'],
  }));
});

it('replaces a Manager branch selection without granting all branches', async () => {
  const user = userEvent.setup();
  const onSubmit = vi.fn().mockResolvedValue(undefined);
  render(<UserFormModal open
    user={{ id: 'manager', name: 'Manager', username: 'manager', role: 'Manager', accessible_teams: ['Coding'] }}
    teams={[{ name: 'Coding' }, { name: 'Submission' }]}
    onClose={vi.fn()} onSubmit={onSubmit} />);
  expect(screen.getByRole('checkbox', { name: 'Coding' })).toBeChecked();
  expect(screen.getByRole('checkbox', { name: 'All branches' })).not.toBeChecked();
  await user.click(screen.getByRole('checkbox', { name: 'Coding' }));
  await user.click(screen.getByRole('checkbox', { name: 'Submission' }));
  await user.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
    role: 'Manager', accessibleTeams: ['Submission'], isGeneralManager: false,
  }));
});
