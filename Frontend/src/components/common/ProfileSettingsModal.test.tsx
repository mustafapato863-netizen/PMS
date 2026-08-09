import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { ProfileSettingsModal } from './ProfileSettingsModal';


const user = {
  id: 'user-1',
  name: 'Ahmed Essa',
  username: 'dr_ahmed_essa',
  role: 'Manager' as const,
};

describe('ProfileSettingsModal', () => {
  it('updates the full name while keeping username read-only', async () => {
    const actor = userEvent.setup();
    const updateProfile = vi.fn().mockResolvedValue({ success: true });
    render(
      <ProfileSettingsModal
        user={user}
        onClose={vi.fn()}
        onUpdateProfile={updateProfile}
        onChangePassword={vi.fn()}
      />,
    );

    const username = screen.getByRole('textbox', { name: 'Username' });
    expect(username).toHaveValue('dr_ahmed_essa');
    expect(username).toHaveAttribute('readonly');
    await actor.clear(screen.getByRole('textbox', { name: 'Full name' }));
    await actor.type(screen.getByRole('textbox', { name: 'Full name' }), 'Ahmed Mohamed Essa');
    await actor.click(screen.getByRole('button', { name: 'Save name' }));

    expect(updateProfile).toHaveBeenCalledWith('Ahmed Mohamed Essa');
    expect(await screen.findByText('Full name updated successfully.')).toBeInTheDocument();
  });

  it('blocks mismatched confirmation and submits matching passwords', async () => {
    const actor = userEvent.setup();
    const changePassword = vi.fn().mockResolvedValue({ success: true });
    render(
      <ProfileSettingsModal
        user={user}
        onClose={vi.fn()}
        onUpdateProfile={vi.fn()}
        onChangePassword={changePassword}
      />,
    );

    await actor.type(screen.getByLabelText('Current password'), 'SecurePassword123!');
    await actor.type(screen.getByLabelText('New password'), 'ChangedPassword456!');
    await actor.type(screen.getByLabelText('Confirm new password'), 'DifferentPassword789!');
    await actor.click(screen.getByRole('button', { name: 'Change password' }));
    expect(changePassword).not.toHaveBeenCalled();
    expect(screen.getByText('New passwords do not match.')).toBeInTheDocument();

    await actor.clear(screen.getByLabelText('Confirm new password'));
    await actor.type(screen.getByLabelText('Confirm new password'), 'ChangedPassword456!');
    await actor.click(screen.getByRole('button', { name: 'Change password' }));

    expect(changePassword).toHaveBeenCalledWith('SecurePassword123!', 'ChangedPassword456!');
    expect(await screen.findByText('Password changed successfully.')).toBeInTheDocument();
  });
});
