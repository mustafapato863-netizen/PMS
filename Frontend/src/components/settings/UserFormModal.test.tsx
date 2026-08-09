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
