import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import TeamKpiTable from './TeamKpiTable';
import type { ExecutiveKpiRow } from '../../../features/executive/types';

const rows: ExecutiveKpiRow[] = [
  {
    kpi_key: 'rejection', kpi_label: 'Rejection Rate', kpi_direction: 'lower_better', unit: '%',
    actual: 7, target: 5, previous_actual: 4, gap_value: -2, raw_gap: 2, raw_change: 3, change_value: -3,
    trend_status: 'declining', weight: 0.5, achievement_percent: 71, grade: 'D', target_status: 'missed', teams: ['CSR'],
  },
  {
    kpi_key: 'response', kpi_label: 'Response Rate', kpi_direction: 'higher_better', unit: '%',
    actual: 95, target: 90, previous_actual: 92, gap_value: 5, raw_gap: 5, raw_change: 3, change_value: 3,
    trend_status: 'improving', weight: 0.5, achievement_percent: 100, grade: 'A', target_status: 'met', teams: ['Marketing'],
  },
];

describe('TeamKpiTable direction semantics', () => {
  it('renders direction-adjusted gap and movement arrows, values, and tones per KPI', () => {
    render(<TeamKpiTable rows={rows} effective={null} previous={null} score={null} />);
    const kpiRows = screen.getAllByTestId('kpi-row');
    const rejectionCells = within(kpiRows[0]).getAllByRole('cell');
    const responseCells = within(kpiRows[1]).getAllByRole('cell');

    expect(rejectionCells[4]).toHaveTextContent('↓ −2%');
    expect(rejectionCells[4]).toHaveAttribute('data-tone', 'bad');
    expect(rejectionCells[5]).toHaveTextContent('↓ −3%');
    expect(rejectionCells[5]).toHaveAttribute('data-tone', 'bad');

    expect(responseCells[4]).toHaveTextContent('↑ +5%');
    expect(responseCells[4]).toHaveAttribute('data-tone', 'good');
    expect(responseCells[5]).toHaveTextContent('↑ +3%');
    expect(responseCells[5]).toHaveAttribute('data-tone', 'good');
  });
});
