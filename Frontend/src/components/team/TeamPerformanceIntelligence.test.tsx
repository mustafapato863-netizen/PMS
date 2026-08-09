import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import type { TeamKpiAnalysis } from '../../features/team/teamKpiAnalysis';
import { TeamPerformanceIntelligence } from './TeamPerformanceIntelligence';

const kpi: TeamKpiAnalysis = {
  key: 'booking_rate',
  label: 'Booking Rate',
  unit: '%',
  lowerBetter: false,
  actual: 0.58,
  target: 0.65,
  previousActual: 0.55,
  baselineActual: 0.7,
  baselineMonth: 'May',
  previousBaselineActual: 0.68,
  previousBaselineMonth: 'April',
  isNewBaseline: false,
  weight: 0.1,
  contribution: 8.9,
  achievement: 89.2,
  movementPercent: 5.5,
  movementPositive: true,
  targetMet: false,
  gapPoints: 1.1,
  severity: 'attention',
  volumeData: null,
};

describe('TeamPerformanceIntelligence', () => {
  it('uses the selected team name while presenting its real KPI analysis', () => {
    render(
      <TeamPerformanceIntelligence
        displayName="Outbound"
        month="June"
        averageScore={82.4}
        atRiskEmployees={2}
        kpis={[kpi]}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Outbound Performance Summary' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Performance Analysis' })).toBeInTheDocument();
    expect(screen.getAllByText('Booking Rate')).toHaveLength(2);
    expect(screen.getByText('KPIs needing attention').nextElementSibling).toHaveTextContent('1');
    const bookingCard = screen.getByRole('button', { name: /Booking Rate/ });
    expect(bookingCard).toHaveTextContent('June');
    expect(bookingCard).toHaveTextContent('Actual 58.0%');
    expect(bookingCard).toHaveTextContent('Best 70.0% (May)');
    expect(bookingCard).toHaveTextContent('12.0% below best');
  });

  it('separates No Show improvement from its remaining target gap', async () => {
    const user = userEvent.setup();
    const noShow: TeamKpiAnalysis = {
      ...kpi,
      key: 'no_show_rate',
      label: 'No Show Rate',
      lowerBetter: true,
      actual: 0.511,
      target: 0.2,
      previousActual: 0.522,
      baselineActual: 0.5,
      baselineMonth: 'May',
      achievement: 39.1,
      movementPercent: -2.1,
      movementPositive: true,
      gapPoints: 60.9,
      severity: 'critical',
    };
    render(<TeamPerformanceIntelligence displayName="Inbound" month="June" averageScore={80} atRiskEmployees={1} kpis={[noShow]} />);

    expect(screen.getByText('Lower is better')).toBeInTheDocument();
    expect(screen.getByText('Improving')).toBeInTheDocument();
    expect(screen.getByText('Still above target')).toBeInTheDocument();
    expect(screen.getByText(/Improved by 1.1%/)).toBeInTheDocument();
    const noShowCard = screen.getByRole('button', { name: /No Show Rate/ });
    expect(noShowCard).toHaveTextContent('Best 50.0% (May)');
    expect(noShowCard).toHaveTextContent('1.1% above best');

    await user.click(noShowCard);
    expect(screen.getByText(/Movement:/)).toBeInTheDocument();
    expect(screen.getByText(/Baseline:/).parentElement).toHaveTextContent('Best historical result: 50.0% (May). June - 1.1% From Baseline.');
    expect(screen.queryByText(/Calculated as/)).not.toBeInTheDocument();
  });

  it('lists only currently weighted KPIs as main score factors', () => {
    const noShow: TeamKpiAnalysis = {
      ...kpi,
      key: 'no_show_rate',
      label: 'No Show Rate',
      weight: null,
      contribution: null,
    };
    render(<TeamPerformanceIntelligence displayName="Outbound" month="June" averageScore={80} atRiskEmployees={0} kpis={[noShow, kpi]} />);

    const scoreFactors = screen.getByText('Main score factors').nextElementSibling;
    expect(scoreFactors).toHaveTextContent('Booking Rate');
    expect(scoreFactors).not.toHaveTextContent('No Show Rate');
  });

  it('marks a current-month record as the new baseline and compares it with the last baseline', async () => {
    const user = userEvent.setup();
    const onTarget: TeamKpiAnalysis = {
      ...kpi,
      key: 'initial_error_rate',
      label: 'Initial Error Rate',
      lowerBetter: true,
      actual: 0.018,
      target: 0.03,
      baselineActual: 0.018,
      baselineMonth: 'June',
      previousBaselineActual: 0.038,
      previousBaselineMonth: 'May',
      isNewBaseline: true,
      targetMet: true,
      achievement: 100,
      gapPoints: 0,
      severity: 'on_target',
    };

    render(<TeamPerformanceIntelligence displayName="Pre-Approvals" month="June" averageScore={86} atRiskEmployees={0} kpis={[onTarget]} />);

    const initialErrorCard = screen.getByRole('button', { name: /Initial Error Rate/ });
    expect(initialErrorCard).toHaveTextContent('Best 1.8% (June)');
    expect(initialErrorCard).toHaveTextContent('+2.0% · New Baseline');

    await user.click(initialErrorCard);
    expect(screen.getByText('Baseline:', { selector: 'strong' }).parentElement).toHaveTextContent('Previous Baseline: 3.8% (May). June +2.0% From Last Baseline. June is the New Baseline.');
  });

  it('does not report a breach when the baseline is unavailable', () => {
    const unconfigured: TeamKpiAnalysis = {
      ...kpi,
      target: 0,
      baselineActual: null,
      baselineMonth: null,
      previousBaselineActual: null,
      previousBaselineMonth: null,
      isNewBaseline: false,
      targetMet: false,
      achievement: null,
      severity: 'configuration_requires_review',
    };

    render(<TeamPerformanceIntelligence displayName="Inbound" month="June" averageScore={80} atRiskEmployees={1} kpis={[unconfigured]} />);

    const unconfiguredCard = screen.getByRole('button', { name: /Booking Rate/ });
    expect(unconfiguredCard).toHaveTextContent('Best N/A');
    expect(unconfiguredCard).toHaveTextContent('Not available');
  });
});
