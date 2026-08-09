import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ManagerSummarySection } from './ManagerSummarySection';
import type { ManagerSnapshot } from './managerSnapshots';
import type { BscHistoryPoint, BscKpiRow } from '../../hooks/api/useBalancedScorecard';

const manager: ManagerSnapshot = {
  employeeId: 'SGHD70149',
  employeeName: 'Dina Samir',
  teamName: 'Account Manager',
  role: 'Account Manager',
  score: 88,
  contribution: 0.88,
  topKpi: 'Campaign delivery',
  trend: 4.2,
};

const kpis: BscKpiRow[] = [
  {
    kpi_key: 'response-time',
    kpi_label: 'Response Time',
    perspective: 'Internal Process',
    score: 33.7,
    state: 'configured',
    weight: 0.15,
    actual_value: 89,
    target_value: 30,
    unit: 'min',
  },
  {
    kpi_key: 'revenue',
    kpi_label: 'Revenue',
    perspective: 'Financial',
    score: 102,
    state: 'configured',
    weight: 0.2,
    actual_value: 102,
    target_value: 100,
    unit: '%',
  },
];

const history: BscHistoryPoint[] = [
  { month: 'May', year: 2026, score: 82 },
  { month: 'June', year: 2026, score: 88 },
];

describe('ManagerSummarySection', () => {
  it('exposes accessible KPI filters and filters the responsive card grid', async () => {
    const user = userEvent.setup();

    render(
      <ManagerSummarySection
        activeManager={manager}
        rosterManagers={[manager]}
        kpiTable={kpis}
        history={history}
        onSelectKpi={() => undefined}
        selectedKpi={null}
      />,
    );

    expect(screen.getByRole('tablist', { name: 'Filter KPI cards by perspective' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Response Time/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Revenue/ })).toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: /Needs Attention/ }));

    expect(screen.getByRole('button', { name: /Response Time/ })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Revenue/ })).not.toBeInTheDocument();
  });

  it('supports KPI selection and hover callbacks from semantic card buttons', () => {
    const onSelectKpi = vi.fn();
    const onKpiHover = vi.fn();
    const onKpiLeave = vi.fn();

    render(
      <ManagerSummarySection
        activeManager={manager}
        rosterManagers={[manager]}
        kpiTable={kpis}
        history={history}
        onSelectKpi={onSelectKpi}
        selectedKpi="response-time"
        onKpiHover={onKpiHover}
        onKpiLeave={onKpiLeave}
      />,
    );

    const card = screen.getByRole('button', { name: /Response Time/ });
    expect(card).toHaveAttribute('aria-pressed', 'true');

    fireEvent.mouseEnter(card);
    fireEvent.mouseLeave(card);
    fireEvent.click(card);

    expect(onKpiHover).toHaveBeenCalledOnce();
    expect(onKpiLeave).toHaveBeenCalledOnce();
    expect(onSelectKpi).toHaveBeenCalledWith('response-time');
  });
});
