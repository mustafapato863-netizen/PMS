import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { InsightTrackingIndicator } from '../../features/insights/types';
import TrackingIndicatorsCard from './TrackingIndicatorsCard';

// Synthetic Pre-Approvals IP Offshore month: 25 policy rejections of 381 assigned
// requests (6.6%), 26 rejections in all (96.2% policy share), August 8 of 300 (2.7%).
const offshore: InsightTrackingIndicator = {
  key: 'PolicyRejection',
  label: 'Policy Rejection Rate',
  description: null,
  unit: '%',
  team: 'Pre-Approvals IP Offshore',
  effective_from: '2026-06',
  period: { year: 2026, month: 'September', key: '2026-09' },
  value: 25 / 381,
  numerator: 25,
  denominator: 381,
  denominator_label: 'assigned requests',
  share_denominator: 26,
  share_denominator_label: 'rejections',
  policy_share: 25 / 26,
  record_count: 2,
  previous_period: { year: 2026, month: 'August', key: '2026-08' },
  previous_value: 8 / 300,
  change: 25 / 381 - 8 / 300,
  trend: [
    { period: { year: 2026, month: 'June', key: '2026-06' }, value: 4 / 200, record_count: 1 },
    { period: { year: 2026, month: 'July', key: '2026-07' }, value: 6 / 240, record_count: 1 },
    { period: { year: 2026, month: 'August', key: '2026-08' }, value: 8 / 300, record_count: 1 },
    { period: { year: 2026, month: 'September', key: '2026-09' }, value: 25 / 381, record_count: 2 },
  ],
};

describe('TrackingIndicatorsCard', () => {
  it('renders nothing when the scope has no tracking indicator', () => {
    const { container } = render(<TrackingIndicatorsCard indicators={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('shows the value, the counts, the policy share and the change against the previous month', () => {
    render(<TrackingIndicatorsCard indicators={[offshore]} />);

    expect(screen.getByText('Policy Rejection Rate')).toBeInTheDocument();
    expect(screen.getByText('6.6%')).toBeInTheDocument();
    expect(screen.getByText('25 of 381 assigned requests')).toBeInTheDocument();
    expect(screen.getByText('96.2% of 26 rejections are policy')).toBeInTheDocument();
    expect(screen.getByText('+3.9 pts vs August (2.7%)')).toBeInTheDocument();
  });

  it('carries the tracking-only tag and no target, achievement or status', () => {
    render(<TrackingIndicatorsCard indicators={[offshore]} />);

    expect(screen.getByText('Tracking only · not in the score')).toBeInTheDocument();
    expect(screen.queryByText(/target/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/below|on track|at risk|achiev/i)).not.toBeInTheDocument();
  });

  it('uses neutral colours: no red or green on the card', () => {
    const { container } = render(<TrackingIndicatorsCard indicators={[offshore]} />);

    const coloured = container.querySelectorAll('[class*="text-red"], [class*="text-rose"], [class*="text-emerald"], [class*="text-green"]');
    expect(coloured).toHaveLength(0);
  });

  it('shows a percentage below one point with two decimals', () => {
    render(<TrackingIndicatorsCard indicators={[{ ...offshore, value: 0.0026, previous_value: null, change: null, trend: [] }]} />);

    expect(screen.getByText('0.26%')).toBeInTheDocument();
    expect(screen.getByText('No earlier month in this scope')).toBeInTheDocument();
  });

  it('describes the monthly trend for screen readers', () => {
    render(<TrackingIndicatorsCard indicators={[offshore]} />);

    expect(screen.getByRole('img', { name: /Policy Rejection Rate monthly trend: Jun 2\.0%, Jul 2\.5%, Aug 2\.7%, Sep 6\.6%/ })).toBeInTheDocument();
  });
});
