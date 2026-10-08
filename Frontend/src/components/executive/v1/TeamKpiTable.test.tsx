import { fireEvent, render, screen, within } from '@testing-library/react';
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
  it('shows eight cached KPIs per page, retaining global ranks and direction calculations', () => {
    const manyRows = Array.from({ length: 21 }, (_, index) => ({
      ...rows[0], kpi_key: `kpi-${index}`, kpi_label: `Metric ${index + 1}`,
    }));
    render(<TeamKpiTable rows={manyRows} effective={null} previous={null} score={null} showTeams />);
    const nav = screen.getByRole('navigation', { name: 'Team KPIs — worst first pages' });
    expect(screen.getAllByTestId('kpi-row')).toHaveLength(8);
    expect(nav).toHaveTextContent('Showing 1–8 of 21 · Page 1 of 3');
    expect(within(nav).getByRole('button', { name: 'Previous page' })).toBeDisabled();
    fireEvent.click(within(nav).getByRole('button', { name: 'Next page' }));
    expect(screen.getAllByTestId('kpi-row')).toHaveLength(8);
    expect(screen.queryByText('Metric 1')).not.toBeInTheDocument();
    expect(screen.getByText('Metric 9')).toBeInTheDocument();
    expect(nav).toHaveTextContent('Showing 9–16 of 21 · Page 2 of 3');
    fireEvent.click(within(nav).getByRole('button', { name: 'Next page' }));
    const pageRows = screen.getAllByTestId('kpi-row');
    expect(pageRows).toHaveLength(5);
    expect(within(pageRows[0]).getAllByRole('cell')[1]).toHaveTextContent('17Metric 17');
    expect(within(pageRows[0]).getAllByRole('cell')[5]).toHaveTextContent('↓ −2%');
    expect(nav).toHaveTextContent('Showing 17–21 of 21 · Page 3 of 3');
    expect(within(nav).getByRole('button', { name: 'Next page' })).toBeDisabled();
    fireEvent.click(within(nav).getByRole('button', { name: 'Previous page' }));
    expect(screen.getByText('Metric 9')).toBeInTheDocument();
  });

  it('resets pagination for a new period or scope and hides navigation for small/empty tables', () => {
    const manyRows = Array.from({ length: 17 }, (_, index) => ({
      ...rows[0], kpi_key: `kpi-${index}`, kpi_label: `Metric ${index + 1}`,
    }));
    const period = { key: '2026-08', year: 2026, month: 'August' };
    const { rerender } = render(<TeamKpiTable rows={manyRows} effective={period} previous={null} score={null} />);
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    rerender(<TeamKpiTable rows={manyRows} effective={{ ...period, key: '2026-07', month: 'July' }} previous={null} score={null} />);
    expect(screen.getByText('Metric 1')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next page' }));
    rerender(<TeamKpiTable rows={manyRows.map((row) => ({ ...row, teams: ['Marketing'] }))} effective={period} previous={null} score={null} />);
    expect(screen.getByText('Metric 1')).toBeInTheDocument();
    rerender(<TeamKpiTable rows={rows} effective={period} previous={null} score={null} />);
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('kpi-row')).toHaveLength(2);
    rerender(<TeamKpiTable rows={[]} effective={period} previous={null} score={null} />);
    expect(screen.queryByRole('navigation')).not.toBeInTheDocument();
    expect(screen.getByText('No KPI breakdown for this month.')).toBeInTheDocument();
  });

  it('places Teams first in both the header and each function KPI row', () => {
    render(<TeamKpiTable rows={rows} effective={null} previous={null} score={null} showTeams />);
    expect(screen.getAllByRole('columnheader').map((header) => header.textContent)).toEqual([
      'Teams', 'KPI', 'Direction', 'Actual', 'Target', 'Gap', 'vs last', 'Weight', 'Achievement',
    ]);
    screen.getAllByTestId('kpi-row').forEach((row, index) => {
      const cells = within(row).getAllByRole('cell');
      expect(cells[0]).toHaveTextContent(rows[index].teams.join(', '));
      expect(cells[0]).toHaveAttribute('title', rows[index].teams.join(', '));
      expect(cells[1]).toHaveTextContent(rows[index].kpi_label);
      expect(cells).toHaveLength(9);
    });
  });

  it('keeps KPI first when the table has no Teams column', () => {
    render(<TeamKpiTable rows={rows} effective={null} previous={null} score={null} />);
    expect(screen.getAllByRole('columnheader')[0]).toHaveTextContent('KPI');
    expect(screen.queryByRole('columnheader', { name: 'Teams' })).not.toBeInTheDocument();
  });

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
