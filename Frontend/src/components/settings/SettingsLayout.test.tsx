import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { SettingsLayout } from './SettingsLayout';
import type { SettingsPage } from './shell/settingsNavigation';

function Address() {
  const { pathname, search } = useLocation();
  return <p data-testid="address">{`${pathname}${search}`}</p>;
}

function renderLayout(activePage: SettingsPage, initialPath = '/settings/data') {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <SettingsLayout activePage={activePage}>
        <div>Panel content</div>
      </SettingsLayout>
      <Address />
    </MemoryRouter>,
  );
}

describe('SettingsLayout', () => {
  it('lists the grouped sections as links and marks the active one as the current page', () => {
    renderLayout('upload');
    const nav = screen.getByRole('navigation', { name: 'Settings sections' });

    for (const heading of ['Data', 'Evaluation', 'Access', 'System']) {
      expect(within(nav).getByText(heading)).toBeInTheDocument();
    }
    const dataUploads = within(nav).getByRole('link', { name: 'Data uploads' });
    expect(dataUploads).toHaveAttribute('href', '/settings/data');
    expect(dataUploads).toHaveAttribute('aria-current', 'page');
    expect(within(nav).getByRole('link', { name: 'Users' })).not.toHaveAttribute('aria-current');
    expect(within(nav).getByRole('link', { name: 'Overview' })).not.toHaveAttribute('aria-current');
    expect(screen.getByText('Panel content')).toBeInTheDocument();
  });

  it('marks Overview as the current page on the overview', () => {
    renderLayout('overview', '/settings/overview');
    expect(screen.getByRole('link', { name: 'Overview' })).toHaveAttribute('aria-current', 'page');
  });

  it('changes the address when a section is clicked', async () => {
    renderLayout('upload');
    await userEvent.click(screen.getByRole('link', { name: 'Users' }));
    expect(screen.getByTestId('address')).toHaveTextContent(/^\/settings\/users$/);
  });

  it('does not list the teams section, which stays unreachable', () => {
    renderLayout('upload');
    expect(screen.queryByRole('link', { name: /team/i })).not.toBeInTheDocument();
  });
});
