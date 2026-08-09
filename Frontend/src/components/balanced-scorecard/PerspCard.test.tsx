import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PerspCard } from './PerspCard';

describe('PerspCard', () => {
  it('shows the configured perspective weight when some KPI data is missing', () => {
    render(
      <PerspCard
        perspective={{
          key: 'Financial',
          label: 'Financial',
          score: 50.5,
          state: 'partial_data',
          weighted_contribution: 0.126,
          configured_weight: 0.4,
          measured_weight: 0.25,
        }}
        isSelected={false}
        isDimmed={false}
        isStrategy
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText('12.6% of 40%')).toBeInTheDocument();
    expect(screen.queryByText('12.6% of 25%')).not.toBeInTheDocument();
  });

  it('falls back to measured weight for legacy responses', () => {
    render(
      <PerspCard
        perspective={{
          key: 'Customer',
          label: 'Customer',
          score: 42.9,
          weighted_contribution: 0.021,
          measured_weight: 0.05,
        }}
        isSelected={false}
        isDimmed={false}
        isStrategy
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText('2.1% of 5%')).toBeInTheDocument();
  });

  it('keeps the configured weight visible when the perspective has no actual data', () => {
    render(
      <PerspCard
        perspective={{
          key: 'Customer',
          label: 'Customer',
          state: 'no_data',
          score: null,
          weighted_contribution: null,
          configured_weight: 0.05,
          measured_weight: 0,
        }}
        isSelected={false}
        isDimmed={false}
        isStrategy
        onSelect={vi.fn()}
      />,
    );

    expect(screen.getByText('0.0% of 5%')).toBeInTheDocument();
    expect(screen.getByText('0.0%')).toBeInTheDocument();
    expect(screen.queryByText(/N\/A/)).not.toBeInTheDocument();
  });
});
