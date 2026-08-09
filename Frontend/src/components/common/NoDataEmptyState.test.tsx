import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import NoDataEmptyState from './NoDataEmptyState';

describe('NoDataEmptyState', () => {
  it('shows a branch-specific message instead of implying the whole team has no data', () => {
    render(
      <NoDataEmptyState
        availablePeriods={[{ month: 'June', year: 2026 }]}
        selectedMonth="June"
        emptyTitle="No Performance Data for Selected Branch"
        emptyDescription="No KPI numbers are available for Sharjah in the selected period."
      />,
    );

    expect(screen.getByText('No Performance Data for Selected Branch')).toBeInTheDocument();
    expect(screen.getByText('No KPI numbers are available for Sharjah in the selected period.')).toBeInTheDocument();
    expect(screen.queryByText(/No performance snapshots or KPI definitions are available/)).not.toBeInTheDocument();
  });
});
