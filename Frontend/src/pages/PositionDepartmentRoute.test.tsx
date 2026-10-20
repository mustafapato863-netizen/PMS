import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import PositionDepartmentRoute from './PositionDepartmentRoute';

vi.mock('./MarketingDashboardView', () => ({
  default: ({ teamId }: { teamId?: string }) => (
    <div>
      Position Overview
      <span data-testid="overview-team">{teamId}</span>
    </div>
  ),
}));

vi.mock('./TeamDashboardView', () => ({
  default: () => <div>Standard Team Dashboard</div>,
}));

const renderRoute = (initialEntry: string) => render(
  <MemoryRouter initialEntries={[initialEntry]}>
    <Routes>
      <Route path="/team/:teamId" element={<PositionDepartmentRoute />} />
    </Routes>
  </MemoryRouter>,
);

describe('PositionDepartmentRoute', () => {
  it.each(['finance', 'human-resources', 'it', 'administration'])(
    'shows the position overview for Employee %s',
    async (teamId) => {
      renderRoute(`/team/${teamId}?performance_level=Employee`);
      expect(await screen.findByText('Position Overview')).toBeInTheDocument();
      expect(screen.getByTestId('overview-team')).toHaveTextContent(teamId);
      expect(screen.queryByText('Standard Team Dashboard')).not.toBeInTheDocument();
    },
  );

  it('shows the position overview when the performance level is omitted', async () => {
    renderRoute('/team/it');
    expect(await screen.findByText('Position Overview')).toBeInTheDocument();
  });

  it.each(['Managerial', 'Corporate'])(
    'keeps the standard team dashboard for %s departments',
    async (performanceLevel) => {
      renderRoute(`/team/finance?performance_level=${performanceLevel}`);
      expect(await screen.findByText('Standard Team Dashboard')).toBeInTheDocument();
      expect(screen.queryByText('Position Overview')).not.toBeInTheDocument();
    },
  );

  it('keeps channel and operational teams on the standard dashboard', async () => {
    renderRoute('/team/inbound?performance_level=Employee');
    expect(await screen.findByText('Standard Team Dashboard')).toBeInTheDocument();
    renderRoute('/team/call-center?performance_level=Employee');
    expect((await screen.findAllByText('Standard Team Dashboard')).length).toBeGreaterThan(0);
    expect(screen.queryByText('Position Overview')).not.toBeInTheDocument();
  });
});
