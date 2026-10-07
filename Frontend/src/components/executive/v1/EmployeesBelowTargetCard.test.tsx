import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { composeExecutiveSummary, type ExecRecord } from '../../../features/executive/compose';
import EmployeesBelowTargetCard from './EmployeesBelowTargetCard';

describe('EmployeesBelowTargetCard', () => {
  it('shows all below-90 people across levels with their own period and level-scoped 360 links', () => {
    const period = { key: '2026-08', month: 'August', year: 2026 };
    const records: ExecRecord[] = [
      ...Array.from({ length: 6 }, (_, index) => ({ employeeId: `e${index}`, name: `Person ${index}`, team: 'Coding', region: 'UAE', position: 'Coder', level: 'Employee', score: 80 + index, period, kpis: [] })),
      { employeeId: 'manager', name: 'Team Manager', team: 'Coding', region: 'UAE', position: 'Manager', level: 'Managerial', score: 88, period, kpis: [] },
      { employeeId: 'at90', name: 'At cutoff', team: 'Coding', region: 'UAE', position: 'Director', level: 'Corporate', score: 90, period, kpis: [] },
    ];
    const summary = composeExecutiveSummary({ view: 'function', functionName: 'RCM', role: 'Admin', records, filters: {}, today: new Date(2026, 8, 1) });
    render(<MemoryRouter><EmployeesBelowTargetCard summary={summary} /></MemoryRouter>);
    const card = screen.getByRole('region', { name: 'Employees below 90%' });
    expect(within(card).getAllByRole('link')).toHaveLength(7);
    expect(within(card).queryByText('At cutoff')).not.toBeInTheDocument();
    expect(within(card).getByRole('link', { name: /Team Manager/ })).toHaveAttribute('href', '/employee/manager?month=August&year=2026&performance_level=Managerial');
  });
});
