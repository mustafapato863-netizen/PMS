import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import Breadcrumb from './Breadcrumb';

describe('Breadcrumb', () => {
  it('renders an accessible trail with navigable ancestors and a current page', () => {
    render(
      <MemoryRouter>
        <Breadcrumb
          items={[
            { label: 'Dashboard', href: '/executive', icon: 'home' },
            { label: 'Team Performance', href: '/team/all', icon: 'teams' },
            { label: 'RCM', icon: 'team' },
          ]}
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole('navigation', { name: 'Breadcrumb' })).toBeInTheDocument();
    expect(screen.getByRole('list')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Dashboard' })).toHaveAttribute('href', '/executive');
    expect(screen.getByRole('link', { name: 'Team Performance' })).toHaveAttribute('href', '/team/all');
    expect(screen.getByText('RCM').closest('[aria-current="page"]')).toHaveAttribute('aria-current', 'page');
    expect(screen.queryByRole('link', { name: 'RCM' })).not.toBeInTheDocument();
  });
});
