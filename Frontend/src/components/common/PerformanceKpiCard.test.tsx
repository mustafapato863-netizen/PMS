import { fireEvent, render, screen } from '@testing-library/react';
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

  it('flips 180deg on click and keyboard to show the last 6 months actual vs target trend', () => {
    render(
      <PerformanceKpiCard
        icon={Activity}
        label="OP Revenue Ach"
        value="38.5%"
        targetValue="100%"
        badgeText="Below Target"
        badgeType="danger"
        progressPercent={38.5}
        contribution={3.9}
        weight={0.1}
        trendSeries={[
          { month: 'May', actual: 28.4, target: 100 },
          { month: 'Jun', actual: 31.0, target: 100 },
          { month: 'Jul', actual: 33.2, target: 100 },
          { month: 'Aug', actual: 35.1, target: 100 },
          { month: 'Sep', actual: 33.8, target: 100 },
          { month: 'Oct', actual: 38.5, target: 100 },
        ]}
        trendSeriesUnit="%"
      />,
    );

    const card = screen.getByRole('button', { name: /OP Revenue Ach/i });
    expect(card).toHaveAttribute('data-flippable', 'true');
    expect(card).toHaveAttribute('data-flipped', 'false');
    expect(card).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(card);
    expect(card).toHaveAttribute('data-flipped', 'true');
    expect(card).toHaveAttribute('aria-pressed', 'true');

    const backFace = screen.getByTestId('kpi-card-trend-back');
    expect(backFace).toHaveTextContent('Last 6 mo · Actual vs Target');
    expect(backFace).toHaveTextContent('Act 38.5%');
    expect(backFace).toHaveTextContent('Tgt 100.0%');
    expect(backFace).toHaveTextContent('0/6 on target');
    expect(screen.getByRole('img', { name: /OP Revenue Ach actual vs target trend chart/i })).toBeInTheDocument();

    // Keyboard flip back
    fireEvent.keyDown(card, { key: 'Enter' });
    expect(card).toHaveAttribute('data-flipped', 'false');
  });

  it('renders an empty trend fallback on the back face when trendSeries is empty', () => {
    render(
      <PerformanceKpiCard
        icon={Activity}
        label="OP Census Ach"
        value="92.0%"
        contribution={9.2}
        weight={0.1}
        trendSeries={[]}
      />,
    );

    const card = screen.getByRole('button', { name: /OP Census Ach/i });
    fireEvent.click(card);
    expect(card).toHaveAttribute('data-flipped', 'true');
    expect(screen.getByText('No 6-month trend history available yet.')).toBeInTheDocument();
  });

  it('applies Executive 95/90/80/70 grade-gradient rules to card accent and progress bars', () => {
    const { rerender } = render(
      <PerformanceKpiCard
        icon={Activity}
        label="Quality Score"
        value="94.0%"
        targetValue="95%"
        badgeText="Below Target"
        badgeType="danger"
        progressPercent={99.0}
        contribution={4.9}
        weight={0.05}
      />,
    );

    expect(screen.getByTestId('kpi-card-accent-strip')).toHaveStyle({
      background: 'var(--pms-grad-grade-a)',
    });

    rerender(
      <PerformanceKpiCard
        icon={Activity}
        label="Conversion Rate"
        value="84.0%"
        targetValue="100%"
        badgeText="Needs Attention"
        badgeType="warning"
        progressPercent={84.0}
        contribution={20}
        weight={0.25}
      />,
    );
    expect(screen.getByTestId('kpi-card-accent-strip')).toHaveStyle({
      background: 'var(--pms-grad-grade-c)',
    });

    rerender(
      <PerformanceKpiCard
        icon={Activity}
        label="OP Revenue Ach"
        value="38.5%"
        targetValue="100%"
        badgeText="Below Target"
        badgeType="danger"
        progressPercent={38.5}
        contribution={3.9}
        weight={0.1}
      />,
    );
    expect(screen.getByTestId('kpi-card-accent-strip')).toHaveStyle({
      background: 'var(--pms-grad-grade-e)',
    });
  });

  it('shows interactive Score and Target tooltip when hovering a month on the flipped trend', () => {
    render(
      <PerformanceKpiCard
        icon={Activity}
        label="Quality Score"
        value="94.0%"
        targetValue="95%"
        badgeText="Below Target"
        badgeType="danger"
        progressPercent={99.0}
        contribution={4.9}
        weight={0.05}
        trendSeries={[
          { month: 'May', actual: 91.2, target: 95 },
          { month: 'Jun', actual: 92.5, target: 95 },
          { month: 'Jul', actual: 95.4, target: 95 },
          { month: 'Aug', actual: 93.1, target: 95 },
          { month: 'Sep', actual: 94.0, target: 95 },
          { month: 'Oct', actual: 96.2, target: 95 },
        ]}
        trendSeriesUnit="%"
      />,
    );

    const card = screen.getByRole('button', { name: /Quality Score/i });
    fireEvent.click(card);
    expect(card).toHaveAttribute('data-flipped', 'true');
    expect(screen.queryByTestId('kpi-trend-hover-tooltip')).not.toBeInTheDocument();

    fireEvent.mouseEnter(screen.getByTestId('kpi-trend-hit-Jul'));
    const tooltip = screen.getByTestId('kpi-trend-hover-tooltip');
    expect(tooltip).toHaveTextContent('Jul');
    expect(tooltip).toHaveTextContent('Score 95.4%');
    expect(tooltip).toHaveTextContent('Tgt 95.0%');
    expect(tooltip).toHaveTextContent('On target');

    fireEvent.mouseEnter(screen.getByTestId('kpi-trend-hit-Aug'));
    expect(screen.getByTestId('kpi-trend-hover-tooltip')).toHaveTextContent('Score 93.1%');
    expect(screen.getByTestId('kpi-trend-hover-tooltip')).toHaveTextContent('Tgt 95.0%');
    expect(screen.getByTestId('kpi-trend-hover-tooltip')).toHaveTextContent('Below');
  });
});
