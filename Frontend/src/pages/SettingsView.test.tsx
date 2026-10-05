import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import SettingsView from './SettingsView';

const roleState = vi.hoisted(() => ({ role: 'General Manager' as string }));

vi.mock('../context/RoleContext', () => ({
  useUserRole: () => ({ role: roleState.role }),
}));

vi.mock('../components/settings/SettingsLayout', () => ({
  SettingsLayout: ({ children }: { children: React.ReactNode }) => <div data-testid="settings-layout">{children}</div>,
}));
vi.mock('../components/settings/DataManagementPanel', () => ({ DataManagementPanel: () => <p>Data management panel</p> }));
vi.mock('../components/settings/KPIConfigPanel', () => ({ KPIConfigPanel: () => null }));
vi.mock('../components/settings/UserManagementPanel', () => ({ UserManagementPanel: () => null }));
vi.mock('../components/settings/CorrectiveActionDataPanel', () => ({ CorrectiveActionDataPanel: () => null }));
vi.mock('../components/settings/SystemErrorsPanel', () => ({ SystemErrorsPanel: () => null }));
vi.mock('./TeamManagementView', () => ({ default: () => null }));

describe('SettingsView soft-lock', () => {
  it.each(['General Manager', 'Manager', 'Executive', 'Viewer'])('shows the Administrator access required panel to %s', (role) => {
    roleState.role = role;
    render(<SettingsView />);
    expect(screen.getByText('Administrator access required')).toBeInTheDocument();
    expect(screen.queryByTestId('settings-layout')).not.toBeInTheDocument();
    expect(screen.queryByText('Data management panel')).not.toBeInTheDocument();
  });

  it('renders the admin panels for Admin', () => {
    roleState.role = 'Admin';
    render(<SettingsView />);
    expect(screen.getByTestId('settings-layout')).toBeInTheDocument();
    expect(screen.getByText('Data management panel')).toBeInTheDocument();
    expect(screen.queryByText('Administrator access required')).not.toBeInTheDocument();
  });
});
