import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import LoginView from './LoginView';
import { ThemeProvider } from '../context/ThemeContext';

const mockLogin = vi.fn();

vi.mock('../context/auth', () => ({
  useAuth: () => ({
    login: mockLogin,
    currentUser: null,
    logout: vi.fn(),
  }),
}));

describe('LoginView rate limiting', () => {
  beforeEach(() => {
    mockLogin.mockReset();
  });

  it('shows a rate-limited login inline, in the alert the form already uses for sign-in errors', async () => {
    mockLogin.mockResolvedValue({ success: false, error: 'Too many requests. Try again in 30 seconds.' });
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ThemeProvider>
          <LoginView />
        </ThemeProvider>
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText('Username'), 'ops-user');
    await user.type(screen.getByLabelText('Password'), 'SecurePassword123!');
    await user.click(screen.getByRole('button', { name: /^sign in$/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Too many requests. Try again in 30 seconds.');
    expect(mockLogin).toHaveBeenCalledTimes(1);
  });
});
