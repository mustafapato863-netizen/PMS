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
  grade_thresholds: { A: 95, B: 90, C: 80, D: 70 },
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
  teamLabel = 'Marketing',
  teamDbName = teamLabel,
  dashboardConfig = config,
}: {
  canExport?: boolean;
  initial?: string;
  records?: AgentRecord[];
  role?: string;
  teamLabel?: string;
  teamDbName?: string;
  dashboardConfig?: MarketingTeamConfig;
} = {}) => {
  const onExport = vi.fn().mockResolvedValue(undefined);
  const onAddAction = vi.fn();
  render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[initial]}>
        <Routes>
          <Route
            path="/team/:teamId"
            element={(
              <>
                <MarketingDashboardContent
                  config={dashboardConfig}
                  records={records}
                  canExport={canExport}
                  onExport={onExport}
                  role={role}
                  getActionsForEmployee={() => []}
                  onAddAction={onAddAction}
                  teamLabel={teamLabel}
                  teamDbName={teamDbName}
                />
                <LocationProbe />
              </>
            )}
          />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
  const filtersButton = screen.queryByRole('button', { name: /Filters/i });
  if (filtersButton) fireEvent.click(filtersButton);
  return { onExport, onAddAction };
};

describe('MarketingDashboardContent', () => {
  it('renders uploaded KPI labels and percentage units with source weights', () => {
    const source = marketingRecord('Social Media Specialist', 'September');
    source.kpi_values![0].weight_applied = .8;
    source.kpi_values![0].contribution = .72;
    source.kpi_values!.push(
      {
        kpi_key: 'mkt_social_media_specialist_reporting', label: 'Reporting', unit: '%',
        direction: 'higher_better', actual_value: .9, target_value: 1,
        achievement_ratio: .9, weight_applied: .1, contribution: .09,
      },
      {
        kpi_key: 'mkt_social_media_specialist_content_calen_afe3843e',
        label: 'Content calendar adherence', unit: '%', direction: 'higher_better',
        actual_value: .97, target_value: 1, achievement_ratio: .97,
        weight_applied: .1, contribution: .097,
      },
    );
    renderDashboard({
      initial: '/team/marketing?year=2026&month=September&region=All&position_view=Social%20Media%20Specialist',
      records: [source],
    });
    for (const [label, actual, contribution] of [
      ['Reporting', '90%', '9.0%'],
      ['Content calendar adherence', '97%', '9.7%'],
    ]) {
      const card = screen.getByRole('progressbar', { name: `${label} progress to target` }).closest('article');
      expect(card).toHaveTextContent(label);
      expect(card).toHaveTextContent(actual);
      expect(card).toHaveTextContent('100%');
      expect(card).not.toHaveTextContent('Target:');
      expect(card).toHaveTextContent('Weight10%');
      expect(card).toHaveTextContent(`Contribution${contribution}`);
      expect(card).not.toHaveTextContent('number');
      expect(card).not.toHaveTextContent('mkt_social_media_specialist_');
    }
  });

  it('opens Finance on the latest month, so one current employee is not mixed with earlier roles', () => {
    const accountant = marketingRecord('General Accountant', 'September');
    accountant.identity = {
      ...accountant.identity,
      name: 'Ahmed Mohamed Sayed Ahmed',
      employee_id: 'SGHD70233',
      team: 'Finance',
    };
    accountant.evaluation = { score: 97.1, grade: 'A' };
    accountant.kpi_values = [
      ['Journal Entry Accuracy Rate', 0.35, 0.321],
      ['Bank Reconciliation Completion Rate', 0.3, 0.3],
      ['Month-End Close Deadline Compliance', 0.35, 0.35],
    ].map(([label, weight, contribution]) => ({
      kpi_key: String(label),
      label: String(label),
      unit: '%',
      direction: 'higher_better' as const,
      actual_value: 0.9,
      target_value: 1,
      achievement_ratio: 0.9,
      weight_applied: Number(weight),
      contribution: Number(contribution),
    }));
    const earlier = marketingRecord('FP&A Manager', 'May');
    earlier.identity = {
      ...earlier.identity,
      name: 'Khawar Bilal',
      employee_id: 'SGHD60013',
      team: 'Finance',
    };
    earlier.kpi_values = [{
      kpi_key: 'Collection Rate',
      label: 'Collection Rate',
      unit: 'number',
      direction: 'higher_better',
      actual_value: 51992564,
      target_value: 1,
      achievement_ratio: 0.79,
      weight_applied: 0.15,
      contribution: 0.12,
    }];
    const financeConfig: MarketingTeamConfig = {
      team: 'Finance',
      db_name: 'Finance',
      region: 'All',
      performance_level: 'Employee',
      grade_thresholds: { A: 95, B: 90, C: 80, D: 70 },
      available_positions: ['General Accountant', 'FP&A Manager'],
      positions: {
        'General Accountant': {
          kpis: accountant.kpi_values.map((kpi, index) => ({
            key: kpi.kpi_key,
            label: kpi.label,
            perspective: 'Financial',
            weight: kpi.weight_applied ?? 0,
            direction: 'higher_better' as const,
            unit: '%',
            color: '#2563EB',
            display_order: index + 1,
          })),
        },
        'FP&A Manager': {
          kpis: [{
            key: 'Collection Rate',
            label: 'Collection Rate',
            perspective: 'Financial',
            weight: 0.15,
            direction: 'higher_better',
            unit: 'number',
            color: '#0D9488',
            display_order: 1,
          }],
        },
      },
    };

    renderDashboard({
      initial: '/team/finance?performance_level=Employee',
      records: [earlier, accountant],
      teamLabel: 'Finance',
      teamDbName: 'Finance',
      dashboardConfig: financeConfig,
    });

    expect(screen.getByRole('heading', { name: 'Finance Overview' })).toBeInTheDocument();
    expect(screen.getByLabelText('Finance month')).toHaveValue('2026-09');
    expect(screen.getByText('Active Employees').parentElement).toHaveTextContent('1');
    expect(screen.queryByText('Khawar Bilal')).not.toBeInTheDocument();
    expect(screen.queryByText('Collection Rate')).not.toBeInTheDocument();

    const accountantCard = screen.getByRole('heading', { name: 'General Accountant' }).closest('article');
    expect(accountantCard).not.toBeNull();
    expect(within(accountantCard as HTMLElement).getByText('3')).toBeInTheDocument();
    const earlierCard = screen.getByRole('heading', { name: 'FP&A Manager' }).closest('article');
    expect(within(earlierCard as HTMLElement).getByText('No Results')).toBeInTheDocument();

    fireEvent.click(within(accountantCard as HTMLElement).getByRole('button', { name: /Open Position/i }));
    expect(screen.getByRole('link', { name: 'Ahmed Mohamed Sayed Ahmed' })).toBeInTheDocument();
    for (const label of [
      'Journal Entry Accuracy Rate',
      'Bank Reconciliation Completion Rate',
      'Month-End Close Deadline Compliance',
    ]) {
      expect(screen.getByRole('progressbar', { name: `${label} progress to target` })).toBeInTheDocument();
    }
    expect(screen.queryByText('Collection Rate')).not.toBeInTheDocument();
    expect(screen.queryByText('Khawar Bilal')).not.toBeInTheDocument();
  });

  it('names the position overview after the selected department', () => {
    renderDashboard({ teamLabel: 'IT', teamDbName: 'IT' });
    expect(screen.getByRole('heading', { name: 'IT Overview' })).toBeInTheDocument();
    expect(screen.getByText('IT Average')).toBeInTheDocument();
    expect(screen.getByText('IT Grade Distribution')).toBeInTheDocument();
    expect(screen.getByText('IT Score Trend')).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Marketing Overview' })).not.toBeInTheDocument();
  });

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
    expect(screen.getAllByText('100%').length).toBeGreaterThan(0);
    expect(screen.queryByText(/^Target:/)).not.toBeInTheDocument();
    expect(screen.getAllByText('Higher is better').length).toBeGreaterThan(0);
    expect(screen.getByRole('progressbar', { name: 'Media Buyer KPI progress to target' })).toHaveAttribute('aria-valuetext', '90.0% of target');
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    expect(screen.getAllByText('Contribution').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Weight').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Needs Attention').length).toBeGreaterThan(0);
    expect(screen.getByRole('heading', { name: 'Employee Performance' })).toBeInTheDocument();
    const viewTiles = within(screen.getByRole('group', { name: 'Marketing roster view' }));
    expect(viewTiles.getByRole('button', { name: 'All Employees' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.queryByRole('combobox', { name: 'Marketing roster view' })).not.toBeInTheDocument();
    fireEvent.click(viewTiles.getByRole('button', { name: 'Top / Bottom' }));
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
    fireEvent.click(viewTiles.getByRole('button', { name: 'All Employees' }));
    expect(screen.getByRole('heading', { name: 'Employee Performance' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Top & Bottom Performers' })).not.toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Root Cause' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Actions' })).toBeInTheDocument();
    expect(screen.getByText('No gap')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open actions for Test Employee' })).toBeInTheDocument();
    fireEvent.click(viewTiles.getByRole('button', { name: 'Top / Bottom' }));
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

    expect(within(screen.getByRole('group', { name: 'Marketing roster view' })).getByRole('button', { name: 'All Employees' })).toHaveAttribute('aria-pressed', 'true');
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
