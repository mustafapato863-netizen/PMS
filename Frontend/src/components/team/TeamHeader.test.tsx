import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import TeamHeader from './TeamHeader';

describe('team scoped filters', () => {
  it('disables the assigned branch and region in the filter sheet, preserving editable dates', () => {
    const setLocation = vi.fn();
    const setRegion = vi.fn();
    render(<MemoryRouter><TeamHeader
      displayName="Inbound" month="June" uniqueMonths={['June', 'May']} setMonth={vi.fn()}
      region="UAE" setRegion={setRegion} location="dubai" setLocation={setLocation}
      lockedBranch="Dubai" lockedRegion="UAE" scopedNavigation
      performanceLevel="All" setPerformanceLevel={vi.fn()} onBack={vi.fn()}
    /></MemoryRouter>);
    fireEvent.click(screen.getByRole('button', { name: /^Filters,/ }));
    expect(screen.getByRole('combobox', { name: 'Branch' })).toBeDisabled();
    expect(screen.getByRole('combobox', { name: 'Region' })).toBeDisabled();
    expect(screen.getByRole('combobox', { name: 'Branch' })).toHaveValue('Dubai');
    expect(screen.getByRole('combobox', { name: 'Region' })).toHaveValue('UAE');
    expect(setLocation).not.toHaveBeenCalled();
    expect(setRegion).not.toHaveBeenCalled();
    expect(screen.getByRole('link', { name: /Team Performance/ })).toHaveAttribute('href', '/executive');
  });
});
