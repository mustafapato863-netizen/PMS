import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import MarketingTeamRoute from './MarketingTeamRoute';

vi.mock('./MarketingDashboardView', () => ({
  default: () => <div>Marketing Employee Dashboard</div>,
}));

vi.mock('./TeamDashboardView', () => ({
  default: ({ teamIdOverride }: { teamIdOverride?: string }) => (
    <div>
      Marketing Management Dashboard
      <span data-testid="team-id-override">{teamIdOverride}</span>
    </div>
  ),
}));

const renderRoute = (initialEntry: string) => render(
  <MemoryRouter initialEntries={[initialEntry]}>
    <Routes>
      <Route path="/team/marketing" element={<MarketingTeamRoute />} />
    </Routes>
  </MemoryRouter>,
);

describe('MarketingTeamRoute', () => {
  it('keeps the specialized Marketing dashboard for Employee and default links', () => {
    renderRoute('/team/marketing?performance_level=Employee');
    expect(screen.getByText('Marketing Employee Dashboard')).toBeInTheDocument();
    expect(screen.queryByText('Marketing Management Dashboard')).not.toBeInTheDocument();
  });

  it.each(['Managerial', 'Corporate'])(
    'uses the standard team dashboard for %s Marketing',
    (performanceLevel) => {
      renderRoute(`/team/marketing?performance_level=${performanceLevel}`);
      expect(screen.getByText('Marketing Management Dashboard')).toBeInTheDocument();
      expect(screen.getByTestId('team-id-override')).toHaveTextContent('marketing');
      expect(screen.queryByText('Marketing Employee Dashboard')).not.toBeInTheDocument();
    },
  );
});
