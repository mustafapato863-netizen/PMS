import { fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { AgentRecord } from '../../../types';
import type { ExecutiveSummary } from '../../../features/executive/types';
import AffectedAgentKpiBreakdown from './AffectedAgentKpiBreakdown';

const mocks = vi.hoisted(() => ({ usePerformanceData: vi.fn() }));

vi.mock('../../../hooks/usePerformanceData', () => ({
  usePerformanceData: mocks.usePerformanceData,
  mapScopedPerformanceRecord: vi.fn(),
}));

vi.mock('../../../hooks/api/usePerformanceDashboard', () => ({
  scopedPerformanceApiEnabled: false,
  useScopedEmployeePerformanceHistory: vi.fn(() => ({ data: undefined, isFetching: false, isError: false })),
}));

const performanceRecords = [
  {
    identity: { employee_id: 'agent-1', name: 'Alex Agent', team: 'Client Services', month: 'March', region: 'EGY' },
    year: 2026,
    region: 'EGY',
    position: 'Specialist',
    performance_level: 'Employee',
    evaluation: { score: 80 },
    kpi_values: [{ kpi_key: 'booking_rate', label: 'Booking Rate', actual_value: 84, target_value: 90, direction: 'higher_better', unit: '%', achievement_ratio: 0.93, weight_applied: 0.5 }],
  },
  {
    identity: { employee_id: 'agent-2', name: 'Sam Agent', team: 'Client Services', month: 'March', region: 'EGY' },
    year: 2026,
    region: 'EGY',
    position: 'Senior Specialist',
    performance_level: 'Employee',
    evaluation: { score: 85 },
    kpi_values: [{ kpi_key: 'booking_rate', label: 'Booking Rate', actual_value: 95, target_value: 90, direction: 'higher_better', unit: '%', achievement_ratio: 1, weight_applied: 0.5 }],
  },
] as unknown as AgentRecord[];

const summary = {
  period: {
    effective: { key: '2026-03', year: 2026, month: 'March' },
    previous: { key: '2026-02', year: 2026, month: 'February' },
  },
  scope: { view: 'function', function: null, team: null, region: 'EGY' },
  people: {
    bottom: [{ employee_id: 'agent-1', name: 'Alex Agent', position: 'Specialist', score: 80, previous_score: 82, change: -2, grade: 'C' }],
    biggest_drops: [{ employee_id: 'agent-2', name: 'Sam Agent', position: 'Senior Specialist', score: 85, previous_score: 90, change: -5, grade: 'B' }],
  },
} as unknown as ExecutiveSummary;

describe('AffectedAgentKpiBreakdown', () => {
  beforeEach(() => {
    mocks.usePerformanceData.mockReturnValue({ agents: performanceRecords, loading: false });
  });

  it('switches affected agents and shows the selected agent actual, target, and gap', () => {
    render(<AffectedAgentKpiBreakdown summary={summary} source="composed" performanceLevel="All" />);

    const agentSelect = screen.getByRole('combobox', { name: 'Affected agent' });
    expect(agentSelect).toHaveValue('agent-1');
    expect(within(agentSelect).getByRole('option', { name: 'Sam Agent · Largest drop' })).toBeInTheDocument();

    fireEvent.change(agentSelect, { target: { value: 'agent-2' } });

    const kpiRow = screen.getByText('Booking Rate').closest('[role="row"]');
    expect(kpiRow).not.toBeNull();
    const cells = within(kpiRow as HTMLElement).getAllByRole('cell');
    expect(cells[2]).toHaveTextContent('95%');
    expect(cells[3]).toHaveTextContent('90%');
    expect(cells[4]).toHaveTextContent('↑ +5 pp');
  });
});
