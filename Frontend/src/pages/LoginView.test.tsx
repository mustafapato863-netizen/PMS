import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import LoginView from './LoginView';
import { ThemeProvider } from '../context/ThemeContext';

const mockLogin = vi.fn();
const mockNavigate = vi.fn();

vi.mock('../context/auth', () => ({
  useAuth: () => ({
    login: mockLogin,
    currentUser: null,
    logout: vi.fn(),
  }),
}));

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

describe('LoginView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const renderLogin = () => {
    return render(
      <MemoryRouter>
        <ThemeProvider>
          <LoginView />
        </ThemeProvider>
      </MemoryRouter>
    );
  };

  it('renders the animated SGH brand emblem, title, and inputs', () => {
    renderLogin();

    expect(screen.getByText('SGH Hub')).toBeInTheDocument();
    expect(screen.getByText('Performance Intelligence Portal')).toBeInTheDocument();
    expect(screen.getByLabelText('Username')).toBeInTheDocument();
    expect(screen.getByLabelText('Password')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^sign in$/i })).toBeInTheDocument();
  });

  it('toggles password visibility', async () => {
    const user = userEvent.setup();
    renderLogin();

    const passwordInput = screen.getByLabelText('Password');
    expect(passwordInput).toHaveAttribute('type', 'password');

    const toggleButton = screen.getByRole('button', { name: /show password/i });
    await user.click(toggleButton);

    expect(passwordInput).toHaveAttribute('type', 'text');
    expect(screen.getByRole('button', { name: /hide password/i })).toBeInTheDocument();
  });

  it('validates required fields on empty submit', async () => {
    const user = userEvent.setup();
    renderLogin();

    const submitButton = screen.getByRole('button', { name: /^sign in$/i });
    await user.click(submitButton);

    expect(screen.getByText('Username is required')).toBeInTheDocument();
    expect(screen.getByText('Password is required')).toBeInTheDocument();
    expect(mockLogin).not.toHaveBeenCalled();
  });

  it('submits valid credentials and navigates on success', async () => {
    mockLogin.mockResolvedValueOnce({ success: true });
    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText('Username'), 'admin');
    await user.type(screen.getByLabelText('Password'), 'password123');

    await user.click(screen.getByRole('button', { name: /^sign in$/i }));

    expect(mockLogin).toHaveBeenCalledWith('admin', 'password123');
    expect(mockNavigate).toHaveBeenCalledWith('/executive', { replace: true });
  });

  it('displays error alert on failed login', async () => {
    mockLogin.mockResolvedValueOnce({ success: false, error: 'Invalid credentials' });
    const user = userEvent.setup();
    renderLogin();

    await user.type(screen.getByLabelText('Username'), 'admin');
    await user.type(screen.getByLabelText('Password'), 'wrongpass');

    await user.click(screen.getByRole('button', { name: /^sign in$/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent('Invalid credentials');
  });
});
