import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ActionsSummaryCard from './ActionsSummaryCard';

describe('ActionsSummaryCard', () => {
  it('uses theme-safe semantic styles for all summary metrics', () => {
    render(
      <ActionsSummaryCard
        month="June"
        stats={{
          total: 10,
          byType: {},
          rootCauses: {},
          employeesActioned: 10,
          actions: [],
        }}
      />,
    );

    expect(screen.getByText('Actions This Month').parentElement).toHaveClass('action-summary-stat-blue');
    expect(screen.getByText('Employees Actioned').parentElement).toHaveClass('action-summary-stat-emerald');
    expect(screen.getByText('Pending Sync').parentElement).toHaveClass('action-summary-stat-amber');
  });
});
