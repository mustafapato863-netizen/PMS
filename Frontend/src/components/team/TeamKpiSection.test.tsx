import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ThemeProvider } from '../../context/ThemeContext';
import TeamKpiSection from './TeamKpiSection';

const teamMetrics = {
  attendCR: 67.2,
  bookingCR: 54.8,
  avgAHT: '2:52',
  avgAHTSec: 172,
  abandonRate: 0,
  reachabilityRate: 0,
  totalBookings: 28390,
  totalAttended: 19069,
  totalCallsHandled: 51773,
  totalAbandoned: 0,
  utzRate: 81.9,
  hasUtz: true,
  dynamicKpis: [{ label: 'Quality Score', actual: 0.977, target: 0.95, unit: '%' }],
};

const renderSection = (month: 'May' | 'June') => render(
  <ThemeProvider>
    <TeamKpiSection
      totalAgents={31}
      avgScore={91.7}
      pctAB={90.3}
      pctDE={0}
      classCounts={{ A: 10, B: 18, C: 3, D: 0, E: 0 }}
      isCallCenterView
      isInbound
      teamMetrics={teamMetrics}
      prevTeamMetrics={null}
      avgAHTSec={172}
      teamId="inbound"
      teamName="Inbound"
      month={month}
      teamWeights={{ Attend: 0.7, Booking: 0.1, Quality: 0.05, AHT: 0.05, Other: 0.1 }}
    />
  </ThemeProvider>,
);

describe('TeamKpiSection active monthly KPI cards', () => {
  it('shows Quality with its contribution and weight in a scored month', () => {
    renderSection('May');

    const qualityCard = screen.getByText('Quality Score').closest('article');
    expect(qualityCard).toHaveTextContent('97.7%');
    expect(qualityCard).toHaveTextContent('Target: 95%');
    expect(qualityCard).toHaveTextContent('Contribution5.0%');
    expect(qualityCard).toHaveTextContent('Weight5%');
  });

  it('hides Quality when June excludes it and exposes the redistributed 15% weight', () => {
    renderSection('June');

    expect(screen.queryByText('Quality Score')).not.toBeInTheDocument();
    const utilizationCard = screen.getByText('Utilization').closest('article');
    expect(utilizationCard).toHaveTextContent('Weight15%');
  });

  it('shows aggregate weights and contributions when the legacy settings weights are unavailable', () => {
    render(
      <ThemeProvider>
        <TeamKpiSection
          totalAgents={32}
          avgScore={91.1}
          pctAB={93.8}
          pctDE={0}
          classCounts={{ A: 10, B: 20, C: 2, D: 0, E: 0 }}
          isCallCenterView
          isInbound
          teamMetrics={{
            ...teamMetrics,
            dynamicKpis: [
              { label: 'Attendance Rate', actual: 0.678, target: 0.75, unit: '%', weight: 0.7, contribution: 63.3 },
              { label: 'Booking Rate', actual: 0.534, target: 0.45, unit: '%', weight: 0.1, contribution: 10 },
              { label: 'AHT (Handle Time)', actual: 2.73, target: 2.75, unit: 'min', isLowerBetter: true, weight: 0.05, contribution: 4.6 },
              { label: 'UTZ', actual: 0.819, target: 0.85, unit: '%', weight: 0.15, contribution: 14.4 },
              { label: 'Quality Score', actual: 0, target: 0.95, unit: '%', weight: 0, contribution: 0 },
            ],
          }}
          prevTeamMetrics={null}
          avgAHTSec={164}
          teamId="inbound"
          teamName="Inbound"
          month="June"
        />
      </ThemeProvider>,
    );

    expect(screen.getByText('Patient Attendance Rate').closest('article')).toHaveTextContent('Contribution63.3%');
    expect(screen.getByText('Patient Attendance Rate').closest('article')).toHaveTextContent('Weight70%');
    expect(screen.getByText('Booking Conversion').closest('article')).toHaveTextContent('Contribution10.0%');
    expect(screen.getByText('Booking Conversion').closest('article')).toHaveTextContent('Weight10%');
    expect(screen.getByText('Avg. Handle Time').closest('article')).toHaveTextContent('Target: 2:45');
    expect(screen.getByText('Avg. Handle Time').closest('article')).toHaveTextContent('Contribution4.6%');
    expect(screen.getByText('Avg. Handle Time').closest('article')).toHaveTextContent('Weight5%');
  });

  it('automatically renders every additional scored call-center KPI', () => {
    render(
      <ThemeProvider>
        <TeamKpiSection
          totalAgents={32}
          avgScore={91.1}
          pctAB={93.8}
          pctDE={0}
          classCounts={{ A: 10, B: 20, C: 2, D: 0, E: 0 }}
          isCallCenterView
          isInbound
          teamMetrics={{
            ...teamMetrics,
            dynamicKpis: [
              { label: 'Attendance Rate', actual: 0.678, target: 0.75, unit: '%', weight: 0.65, contribution: 58.8 },
              { label: 'Booking Rate', actual: 0.534, target: 0.45, unit: '%', weight: 0.1, contribution: 10 },
              { label: 'AHT (Handle Time)', actual: 2.73, target: 2.5, unit: 'min', isLowerBetter: true, weight: 0.05, contribution: 4.6 },
              { label: 'UTZ', actual: 0.819, target: 0.85, unit: '%', weight: 0.15, contribution: 14.4 },
              { label: 'No Show Rate', actual: 0.032, target: 0.02, unit: '%', isLowerBetter: true, weight: 0.05, contribution: 3.1 },
            ],
          }}
          prevTeamMetrics={null}
          avgAHTSec={164}
          teamId="inbound"
          teamName="Inbound"
          month="June"
        />
      </ThemeProvider>,
    );

    const noShowCard = screen.getByText('No Show Rate').closest('article');
    expect(noShowCard).toHaveTextContent('3.2%');
    expect(noShowCard).toHaveTextContent('Target: ≤ 2.0%');
    expect(noShowCard).toHaveTextContent('Contribution3.1%');
    expect(noShowCard).toHaveTextContent('Weight5%');
  });

  it('shows the pooled IP Offshore rates and effective dynamic weights', () => {
    render(
      <ThemeProvider>
        <TeamKpiSection
          totalAgents={5}
          avgScore={68.8}
          pctAB={20}
          pctDE={60}
          classCounts={{ A: 0, B: 1, C: 1, D: 0, E: 3 }}
          isCallCenterView={false}
          isInbound={false}
          teamMetrics={{
            ...teamMetrics,
            rejectionRate: (26 / 405) * 100,
            errorRate: (28 / 918) * 100,
            submissionRate: (255 / 334) * 100,
            rejectionWeight: 0.54,
            rejectionContribution: 25,
            errorWeight: 0.12,
            errorContribution: 10,
            submissionWeight: 0.34,
            submissionContribution: 27,
          }}
          prevTeamMetrics={null}
          avgAHTSec={0}
          teamId="pre-approvals"
          teamName="Pre-Approvals IP Offshore"
          month="June"
          teamWeights={{ Rejection: 0.50, InitialError: 0.20, Submission: 0.30 }}
        />
      </ThemeProvider>,
    );

    const rejectionCard = screen.getByText('IP Rejection Rate').closest('article');
    const errorCard = screen.getByText('Initial Error Rate').closest('article');
    const submissionCard = screen.getByText('Submission Rate').closest('article');
    expect(rejectionCard).toHaveTextContent('6.4%');
    expect(rejectionCard).toHaveTextContent('Target: ≤ 3.0%');
    expect(rejectionCard).toHaveTextContent('Weight54%');
    expect(errorCard).toHaveTextContent('3.1%');
    expect(errorCard).toHaveTextContent('Target: ≤ 3.0%');
    expect(errorCard).toHaveTextContent('Weight12%');
    expect(submissionCard).toHaveTextContent('76.3%');
    expect(submissionCard).toHaveTextContent('Target: 90%');
    expect(submissionCard).toHaveTextContent('Weight34%');
  });

  it('shows the 100% target on every Sales performance card', () => {
    render(
      <ThemeProvider>
        <TeamKpiSection
          totalAgents={10}
          avgScore={87}
          pctAB={70}
          pctDE={10}
          classCounts={{ A: 3, B: 4, C: 2, D: 1, E: 0 }}
          isCallCenterView={false}
          isInbound={false}
          teamMetrics={{
            ...teamMetrics,
            opCensusRate: 92,
            opRevenueRate: 98,
            ipCensusRate: 101,
            ipRevenueRate: 96,
            activityRate: 105,
          }}
          prevTeamMetrics={null}
          avgAHTSec={0}
          teamId="sales"
          teamName="Sales"
          month="June"
        />
      </ThemeProvider>,
    );

    for (const label of ['OP Census Ach', 'OP Revenue Ach', 'IP Census Ach', 'IP Revenue Ach', 'Activity Score']) {
      expect(screen.getByText(label).closest('article')).toHaveTextContent('Target: 100%');
    }
  });

  it('uses KPI record weights for newly onboarded position-scoped teams', () => {
    render(
      <ThemeProvider>
        <TeamKpiSection
          totalAgents={8}
          avgScore={92.4}
          pctAB={55}
          pctDE={25}
          classCounts={{ A: 5, B: 1, C: 0, D: 1, E: 1 }}
          isCallCenterView={false}
          isInbound={false}
          teamMetrics={{
            ...teamMetrics,
            dynamicKpis: [{
              label: 'Initial Rejection Rate',
              actual: 0.063,
              target: 0.053,
              unit: '%',
              isLowerBetter: true,
              weight: 0.6,
              contribution: 50.3,
            }],
          }}
          prevTeamMetrics={null}
          avgAHTSec={0}
          teamId="pre-approvals-op-dubai"
          teamName="Pre-Approvals OP Dubai"
          month="May"
        />
      </ThemeProvider>,
    );

    const rejectionCard = screen.getByText('Initial Rejection Rate').closest('article');
    expect(rejectionCard).toHaveTextContent('Target: ≤ 5.3%');
    expect(rejectionCard).toHaveTextContent('Contribution50.3%');
    expect(rejectionCard).toHaveTextContent('Weight60%');
  });

  it('caps KPI contributions at the configured weight for Pre-Approvals IP Final Dubai', () => {
    render(
      <ThemeProvider>
        <TeamKpiSection
          totalAgents={4}
          avgScore={108}
          pctAB={100}
          pctDE={0}
          classCounts={{ A: 4, B: 0, C: 0, D: 0, E: 0 }}
          isCallCenterView={false}
          isInbound={false}
          teamMetrics={{
            ...teamMetrics,
            dynamicKpis: [{
              label: 'Submission Within Month %',
              actual: 0.989,
              target: 0.96,
              unit: '%',
              weight: 0.3,
              contribution: 35.5,
            }],
          }}
          prevTeamMetrics={null}
          avgAHTSec={0}
          teamId="pre-approvals-ip-final-dubai"
          teamName="Pre-Approvals IP Final Dubai"
          month="May"
        />
      </ThemeProvider>,
    );

    const submissionCard = screen.getByText('Submission Within Month %').closest('article');
    expect(submissionCard).toHaveTextContent('Target: 96%');
    expect(submissionCard).toHaveTextContent('Contribution30.0%');
    expect(submissionCard).toHaveTextContent('Weight30%');
  });

  it('renders an above-target fractional percentage KPI consistently', () => {
    render(
      <ThemeProvider>
        <TeamKpiSection
          totalAgents={9}
          avgScore={83.2}
          pctAB={44.4}
          pctDE={11.1}
          classCounts={{ A: 2, B: 2, C: 4, D: 1, E: 0 }}
          isCallCenterView={false}
          isInbound={false}
          teamMetrics={{
            ...teamMetrics,
            dynamicKpis: [{
              label: 'TAT',
              actual: 1.077,
              target: 1,
              unit: '%',
              weight: 0.3,
              contribution: 32.3,
            }],
          }}
          prevTeamMetrics={null}
          avgAHTSec={0}
          teamId="re-submission"
          teamName="Re-Submission"
          month="June"
        />
      </ThemeProvider>,
    );

    const tatCard = screen.getByText('TAT').closest('article');
    expect(tatCard).toHaveTextContent('107.7%');
    expect(tatCard).toHaveTextContent('Target: 100%');
    expect(tatCard).toHaveTextContent('On Target');
  });
});
