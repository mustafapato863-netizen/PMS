import { render, screen } from '@testing-library/react';
import { Activity } from 'lucide-react';
import { describe, expect, it, vi } from 'vitest';
import PerformanceKpiCard from './PerformanceKpiCard';
import {
  calculateKpiTargetProgress,
  formatPercentOfTargetLabel,
  normalizePercentageKpiForDisplay,
  resolveKpiTargetStatus,
} from './performanceKpiProgress';

describe('PerformanceKpiCard', () => {
  it('identifies an average weight for a mixed employee-period cohort', () => {
    render(
      <PerformanceKpiCard
        icon={Activity}
        label="Reporting"
        value="90%"
        targetValue="100%"
        contribution={4.5}
        weight={0.05}
        weightLabel="Avg. weight"
      />,
    );
    const card = screen.getByText('Reporting').closest('article');
    expect(card).toHaveTextContent('Avg. weight5%');
    expect(card).toHaveTextContent('Contribution4.5%');
    expect(screen.getByText('100%')).toBeInTheDocument();
    expect(screen.queryByText('Target: 100%')).not.toBeInTheDocument();
  });

  it('calculates target progress for higher and lower better KPIs', () => {
    expect(calculateKpiTargetProgress(34, 42)).toBeCloseTo(80.95);
    expect(calculateKpiTargetProgress(136, 60, true)).toBeCloseTo(44.12);
    expect(calculateKpiTargetProgress(0, 60, true)).toBe(100);
    expect(calculateKpiTargetProgress(0, 0)).toBeNull();
  });

  it('resolves lower-better status from the displayed actual and target values', () => {
    const belowMaximum = resolveKpiTargetStatus(3.64, 15, true);
    expect(belowMaximum.status).toBe('on_target');
    expect(belowMaximum.progressPercent).toBeCloseTo(412.09);
    expect(formatPercentOfTargetLabel(200)).toBe('100.0% of target');
    expect(formatPercentOfTargetLabel(95.4)).toBe('95.4% of target');
    expect(formatPercentOfTargetLabel(belowMaximum.progressPercent ?? 0)).toBe('100.0% of target');
    expect(resolveKpiTargetStatus(18, 15, true).status).toBe('needs_attention');
    expect(resolveKpiTargetStatus(30, 15, true).status).toBe('below_target');
  });

  it('preserves higher-better and unavailable target status behavior', () => {
    expect(resolveKpiTargetStatus(100, 100).status).toBe('on_target');
    expect(resolveKpiTargetStatus(90, 100).status).toBe('needs_attention');
    expect(resolveKpiTargetStatus(70, 100).status).toBe('below_target');
    expect(resolveKpiTargetStatus(null, 100).status).toBe('no_data');
    expect(resolveKpiTargetStatus(0, 0).status).toBe('target_review');
  });

  it('keeps an above-target fractional percentage on the percentage scale', () => {
    expect(normalizePercentageKpiForDisplay(1.077, 1, '%')).toBeCloseTo(107.7);
  });

  it('puts the target under the status and leaves the Target badge off the card', () => {
    render(
      <PerformanceKpiCard
        icon={Activity}
        label="Booking Conversion"
        value="62.0%"
        targetValue="65%"
        badgeText="Below Target"
        badgeType="danger"
        progressPercent={95.4}
        contribution={9.5}
        weight={0.1}
      />,
    );

    const card = screen.getByText('Booking Conversion').closest('article');
    const status = screen.getByText('Below Target');
    const target = screen.getByText('65%');
    expect(status.compareDocumentPosition(target) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(card).toHaveTextContent('65%');
    expect(screen.queryByText('Target: 65%')).not.toBeInTheDocument();
  });

  it('places the monthly movement beside the detail and renders target progress', () => {
    render(
      <PerformanceKpiCard
        icon={Activity}
        iconAccentColor="#0D9488"
        label="Conversion Rate"
        value="34%"
        detailLabel="Target: 42%"
        badgeText="Needs Attention"
        badgeType="warning"
        trendDelta={-5.6}
        isTrendGood={false}
        progressPercent={81}
        contribution={24.3}
        weight={0.3}
      />,
    );

    expect(screen.getByText('Target: 42%')).not.toHaveAttribute('title');
    expect(screen.getByText('-5.6% MoM')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Conversion Rate progress to target' })).toHaveAttribute('aria-valuenow', '81');
    expect(screen.getByText('81.0% of target')).toBeInTheDocument();
    expect(screen.getByText('24.3%')).toBeInTheDocument();
    expect(screen.getByText('30%')).toBeInTheDocument();
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument();
    expect(document.querySelector('[data-kpi-icon-accent="#0D9488"]')).toHaveStyle({ backgroundColor: '#0D9488' });
  });

  it('caps extreme over-target progress at 100 percent in the display label', () => {
    render(
      <PerformanceKpiCard
        icon={Activity}
        label="Rejection Rate"
        value="3.4%"
        detailLabel="Target: 13.9%"
        badgeText="On Target"
        badgeType="success"
        progressPercent={41075}
        contribution={40}
        weight={0.4}
      />,
    );

    expect(screen.getByText('100.0% of target')).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'Rejection Rate progress to target' })).toHaveAttribute('aria-valuetext', '100.0% of target');
    expect(screen.queryByText('41075.0% of target')).not.toBeInTheDocument();
  });

  it('does not append a percentage sign to a unitless numeric target', () => {
    render(
      <PerformanceKpiCard
        icon={Activity}
        label="Average Transaction Value"
        value="711.9"
        targetValue="600.0"
        progressPercent={118.6}
        contribution={20}
        weight={0.2}
      />,
    );

    expect(screen.getByText('600')).toBeInTheDocument();
    expect(screen.queryByText('Target: 600')).not.toBeInTheDocument();
    expect(screen.queryByText('Target: 600%')).not.toBeInTheDocument();
  });

  it('shows a neutral unavailable state when the target cannot produce progress', () => {
    render(
      <PerformanceKpiCard
        icon={Activity}
        label="App Installs"
        value="0"
        detailLabel="Target: 0"
        badgeText="Target Requires Review"
        badgeType="neutral"
        progressPercent={null}
        contribution={0}
        weight={0.1}
      />,
    );

    const progress = screen.getByRole('progressbar', { name: 'App Installs progress to target' });
    expect(progress).not.toHaveAttribute('aria-valuenow');
    expect(progress).toHaveAttribute('aria-valuetext', 'Target progress unavailable');
    expect(screen.getByText('Target unavailable')).toBeInTheDocument();
  });

  it('caps a contribution at the configured KPI weight', () => {
    render(
      <PerformanceKpiCard
        icon={Activity}
        label="Submission Within Month"
        value="98.9%"
        contribution={35.5}
        weight={0.3}
      />,
    );

    expect(screen.getByText('30.0%')).toBeInTheDocument();
    expect(screen.getByText('30%')).toBeInTheDocument();
  });

  it.each([
    { contribution: 0.7142857142857143, value: '1.0%', expected: '0.7%', forbidden: ['50.0%'] },
    { contribution: 1, value: '2.0%', expected: '1.0%', forbidden: ['50.0%', '100.0%'] },
    { contribution: 0, value: '1.4%', expected: '0.0%', forbidden: ['—'] },
  ])('prints $contribution score points as $expected without rescaling', ({ contribution, value, expected, forbidden }) => {
    render(
      <PerformanceKpiCard
        icon={Activity}
        label="Patient Attendance Rate"
        value={value}
        contribution={contribution}
        weight={0.5}
      />,
    );

    const card = screen.getByText('Patient Attendance Rate').closest('article');
    expect(card).toHaveTextContent(`Contribution${expected}`);
    expect(card).toHaveTextContent('Weight50%');
    for (const text of forbidden) expect(card).not.toHaveTextContent(`Contribution${text}`);
  });

  it('shows a view-only KPI without a weight', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    render(
      <PerformanceKpiCard
        icon={Activity}
        label="IP Initial Rejection %(All)"
        value="3.2%"
        contribution={0}
        weight={0}
        viewOnly
      />,
    );

    const card = screen.getByText('IP Initial Rejection %(All)').closest('article');
    expect(card).toHaveTextContent('View');
    expect(card).not.toHaveTextContent('Weight');
    expect(card).toHaveTextContent('Contribution—');
    expect(warn).not.toHaveBeenCalled();
    warn.mockRestore();
  });
});
