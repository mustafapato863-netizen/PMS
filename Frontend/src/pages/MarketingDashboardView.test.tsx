import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '../context/ThemeContext';
import type { AgentRecord } from '../types';
import type { MarketingTeamConfig } from '../features/marketing/types';
import { MarketingDashboardContent } from './MarketingDashboardView';

vi.mock('recharts', () => {
  const Component = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  return {
    ResponsiveContainer: Component,
    BarChart: Component,
    Bar: Component,
    CartesianGrid: Component,
    Cell: Component,
    Legend: Component,
    Line: Component,
    LineChart: Component,
    Pie: Component,
    PieChart: Component,
    Tooltip: Component,
    XAxis: Component,
    YAxis: Component,
  };
});

const positions = ['Media Buyer', 'Graphic Designer', 'Social Media Specialist', 'Web Developer', 'Content Writer'];
const config: MarketingTeamConfig = {
  team: 'Marketing',
  db_name: 'Marketing',
  region: 'EGY',
  performance_level: 'Employee',
  grade_thresholds: { A: 95, B: 85, C: 75, D: 65 },
  available_positions: positions,
  positions: Object.fromEntries(positions.map((position) => [
    position,
    {
      kpis: [{
        key: `${position}-kpi`,
        label: `${position} KPI`,
        perspective: 'Customer',
        weight: 1,
        direction: 'higher_better',
        unit: '%',
        color: '#2563EB',
        display_order: 1,
      }],
    },
  ])),
};

const marketingRecord = (
  position: string,
  month: string,
  region = 'EGY',
  values: { actual?: number; target?: number; achievement?: number } = {},
): AgentRecord => ({
  year: 2026,
  position,
  region,
  status: 'Meets',
  performance_level: 'Employee',
  identity: { name: 'Test Employee', employee_id: 'SGHD70001', team: 'Marketing', month, position, region },
  calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
  geo: {
    bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
    attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
  },
  actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
  achievement: { booking_ach: 0, attend_ach: 0 },
  evaluation: { score: month === 'June' ? 90 : 85, grade: 'B' },
  kpi_values: [{
    kpi_key: `${position}-kpi`,
    label: `${position} KPI`,
    unit: '%',
    direction: 'higher_better',
    actual_value: values.actual ?? 0.9,
    target_value: values.target ?? 1,
    achievement_ratio: values.achievement ?? 0.9,
    weight_applied: 1,
    contribution: Math.min(values.achievement ?? 0.9, 1),
  }],
});

const LocationProbe = () => {
  const location = useLocation();
  return <output data-testid="location">{location.search}</output>;
};

const defaultRecords = [
  marketingRecord('Media Buyer', 'May'),
  marketingRecord('Media Buyer', 'June'),
  marketingRecord('Graphic Designer', 'June', 'UAE'),
];

const renderDashboard = ({
  canExport = true,
  initial = '/team/marketing?year=2026&month=June&region=All',
  records = defaultRecords,
  role = 'Viewer',
}: {
  canExport?: boolean;
  initial?: string;
  records?: AgentRecord[];
  role?: string;
} = {}) => {
  const onExport = vi.fn().mockResolvedValue(undefined);
  const onAddAction = vi.fn();
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route
            path="/team/marketing"
            element={(
              <>
                <MarketingDashboardContent
                  config={config}
                  records={records}
                  canExport={canExport}
                  onExport={onExport}
                  role={role}
                  getActionsForEmployee={() => []}
                  onAddAction={onAddAction}
                />
                <LocationProbe />
              </>
            )}
          />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
  return { onExport, onAddAction };
};

describe('MarketingDashboardContent', () => {
  it('shows all configured positions and distinguishes missing uploads', () => {
    renderDashboard();
    expect(screen.getByRole('heading', { name: 'Marketing Overview' })).toBeInTheDocument();
    expect(screen.queryByLabelText('Marketing year')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Marketing status')).not.toBeInTheDocument();
    expect(screen.getAllByText('+5.9% MoM').length).toBeGreaterThan(0);
    expect(screen.getByRole('heading', { name: 'Content Writer' })).toBeInTheDocument();
    const contentCard = screen.getByRole('heading', { name: 'Content Writer' }).closest('article');
    expect(contentCard).not.toBeNull();
    expect(within(contentCard as HTMLElement).getByText('No Data')).toBeInTheDocument();
  });

  it('distinguishes uploaded positions excluded by filters from positions never uploaded', () => {
    renderDashboard({ initial: '/team/marketing?year=2026&month=June&region=UAE' });
    const regionSelect = screen.getByLabelText('Marketing region');
    expect(within(regionSelect).queryByRole('option', { name: 'Other' })).not.toBeInTheDocument();
    const mediaCard = screen.getByRole('heading', { name: 'Media Buyer' }).closest('article');
    const contentCard = screen.getByRole('heading', { name: 'Content Writer' }).closest('article');
    expect(within(mediaCard as HTMLElement).getByText('No Results')).toBeInTheDocument();
    expect(within(contentCard as HTMLElement).getByText('No Data')).toBeInTheDocument();
  });

  it('exposes the All Months period and preserves it in the URL', () => {
    renderDashboard({ initial: '/team/marketing?year=2026&month=All&region=All' });
    const monthSelect = screen.getByLabelText('Marketing month');
    expect(monthSelect).toHaveValue('All');
    expect(within(monthSelect).getByRole('option', { name: 'All Months' })).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('month=All');
  });

  it('uses Position as an overview filter without opening the detail dashboard', () => {
    renderDashboard();
    fireEvent.change(screen.getByLabelText('Marketing position'), { target: { value: 'Graphic Designer' } });
    expect(screen.getByRole('heading', { name: 'Marketing Overview' })).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('position=Graphic+Designer');
    expect(screen.getByRole('heading', { name: 'Graphic Designer' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Media Buyer' })).not.toBeInTheDocument();
    expect(screen.getAllByText(/Graphic Designer leads with/i).length).toBeGreaterThan(0);
  });

  it('opens a dedicated position dashboard and returns without losing overview filters', () => {
    renderDashboard({ initial: '/team/marketing?year=2026&month=June&region=EGY&position=Media%20Buyer' });
    const mediaCard = screen.getByRole('heading', { name: 'Media Buyer' }).closest('article');
    fireEvent.click(within(mediaCard as HTMLElement).getByRole('button', { name: /Open Position/i }));
    expect(screen.getByRole('heading', { name: 'Media Buyer · Employee' })).toBeInTheDocument();
    expect(screen.getByLabelText('Marketing performance level')).toBeDisabled();
    expect(screen.getAllByText('90%').length).toBeGreaterThan(0);
    expect(screen.getByText('Target: 100%')).toBeInTheDocument();
    expect(screen.getAllByText('Higher is better').length).toBeGreaterThan(0);
    expect(screen.getByRole('progressbar', { name: 'Media Buyer KPI progress to target' })).toHaveAttribute('aria-valuetext', '90.0% of target');
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    expect(screen.getAllByText('Contribution').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Weight').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Needs Attention').length).toBeGreaterThan(0);
    expect(screen.getByRole('heading', { name: 'Top & Bottom Performers' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Performance Analysis' })).toBeInTheDocument();
    expect(screen.getByText('Unchanged')).toBeInTheDocument();
    expect(screen.getAllByText('Critical gap').length).toBeGreaterThan(0);
    expect(screen.queryByRole('heading', { name: 'KPI Achievement Comparison' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Grade Distribution' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Score Trend — 2 Available Periods' })).toBeInTheDocument();
    expect(screen.getAllByText('June 2026').length).toBeGreaterThan(0);
    expect(screen.getByText('No additional employees are available for this group.')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Employee Performance' })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Marketing roster view'), { target: { value: 'all' } });
    expect(screen.getByRole('heading', { name: 'Employee Performance' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Top & Bottom Performers' })).not.toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Root Cause' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Actions' })).toBeInTheDocument();
    expect(screen.getByText('No gap')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open actions for Test Employee' })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Marketing roster view'), { target: { value: 'top_bottom' } });
    expect(screen.getByRole('heading', { name: 'Top & Bottom Performers' })).toBeInTheDocument();
    expect(screen.getByTestId('location')).toHaveTextContent('position_view=Media+Buyer');
    fireEvent.click(screen.getByRole('button', { name: 'Back to Marketing Overview' }));
    expect(screen.getByTestId('location')).toHaveTextContent('year=2026');
    expect(screen.getByTestId('location')).toHaveTextContent('month=June');
    expect(screen.getByTestId('location')).toHaveTextContent('region=EGY');
    expect(screen.getByTestId('location')).toHaveTextContent('position=Media+Buyer');
    expect(screen.getByTestId('location')).not.toHaveTextContent('position_view=');
  });

  it('loads the selected position KPI model and analysis instead of reusing another position', () => {
    renderDashboard({ initial: '/team/marketing?year=2026&month=June&region=All&position=Graphic%20Designer' });
    const positionCard = screen.getByRole('heading', { name: 'Graphic Designer' }).closest('article');
    fireEvent.click(within(positionCard as HTMLElement).getByRole('button', { name: /Open Position/i }));
    expect(screen.getByRole('heading', { name: 'Graphic Designer · Employee' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Graphic Designer KPIs' })).toBeInTheDocument();
    expect(screen.getAllByText('Graphic Designer KPI').length).toBeGreaterThan(0);
    expect(screen.queryByText('Media Buyer KPI')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Performance Analysis' })).toBeInTheDocument();
  });

  it('shows a neutral review state instead of a misleading progress result for a zero target', () => {
    renderDashboard({
      initial: '/team/marketing?year=2026&month=June&region=All&position_view=Media%20Buyer',
      records: [
        marketingRecord('Media Buyer', 'June', 'EGY', { actual: 0, target: 0, achievement: 0 }),
      ],
    });
    expect(screen.getByText('Target Requires Review')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Media Buyer KPI progress to target' })).not.toHaveAttribute('aria-valuenow');
    expect(screen.getByRole('progressbar', { name: 'Media Buyer KPI progress to target' })).toHaveAttribute('aria-valuetext', 'Target progress unavailable');
  });

  it('reuses the standard employee quick-action menu for authorized Marketing managers', () => {
    const atRiskRecord = marketingRecord('Media Buyer', 'June', 'EGY', { achievement: 0.5 });
    atRiskRecord.evaluation = { score: 50, grade: 'E' };
    const { onAddAction } = renderDashboard({
      initial: '/team/marketing?year=2026&month=June&region=All&position_view=Media%20Buyer',
      records: [atRiskRecord],
      role: 'Manager',
    });

    fireEvent.change(screen.getByLabelText('Marketing roster view'), { target: { value: 'all' } });
    expect(screen.getByText('Media Buyer KPI (main issue)')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open actions for Test Employee' }));

    expect(screen.getByRole('menuitem', { name: 'View Employee Profile' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'View Performance Details' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'View Action History' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Add Corrective Action' }));
    expect(onAddAction).toHaveBeenCalledTimes(1);
  });

  it('updates the region filter and renders the filtered empty state', () => {
    renderDashboard({ initial: '/team/marketing?year=2026&month=June&region=All&status=Below&position_view=Media%20Buyer' });
    fireEvent.change(screen.getByLabelText('Marketing region'), { target: { value: 'UAE' } });
    expect(screen.getByTestId('location')).toHaveTextContent('region=UAE');
    expect(screen.getByTestId('location')).not.toHaveTextContent('status=');
    expect(screen.getByText(/No uploaded results match this position/i)).toBeInTheDocument();
  });

  it('shows export only to authorized roles', () => {
    const { onExport } = renderDashboard();
    fireEvent.click(screen.getByRole('button', { name: 'Export Excel' }));
    expect(onExport).toHaveBeenCalledTimes(1);
  });

  it('hides export for unauthorized roles', () => {
    renderDashboard({ canExport: false });
    expect(screen.queryByRole('button', { name: 'Export Excel' })).not.toBeInTheDocument();
  });
});
