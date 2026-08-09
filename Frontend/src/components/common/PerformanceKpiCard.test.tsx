import { render, screen } from '@testing-library/react';
import { Activity } from 'lucide-react';
import { describe, expect, it } from 'vitest';
import PerformanceKpiCard from './PerformanceKpiCard';
import {
  calculateKpiTargetProgress,
  normalizePercentageKpiForDisplay,
  resolveKpiTargetStatus,
} from './performanceKpiProgress';

describe('PerformanceKpiCard', () => {
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

    expect(screen.getByText('Target: 600')).toBeInTheDocument();
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
});
