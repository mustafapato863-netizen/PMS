import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ExecutiveFunctionCard, ExecutivePeriod } from '../../../features/executive/types';
import FunctionCards from './FunctionCards';

const period = (month: string, monthNumber: string): ExecutivePeriod => ({
  key: `2026-${monthNumber}`,
  year: 2026,
  month,
});

const card: ExecutiveFunctionCard = {
  function: 'RCM',
  score: 86.5,
  previous_score: 89.6,
  change: -3.1,
  gap: -13.5,
  grade: 'C',
  employees: 37,
  teams: ['Coding', 'Re-Submission', 'Submission'],
  regions: ['UAE'],
  falling_months: 2,
  trend: [
    { period: period('January', '01'), score: 82.1 },
    { period: period('February', '02'), score: 82.1 },
    { period: period('March', '03'), score: 80.4 },
    { period: period('April', '04'), score: 83.2 },
    { period: period('May', '05'), score: 84.0 },
    { period: period('June', '06'), score: 86.5 },
  ],
  is_most_improved: false,
};

describe('FunctionCards trend chart', () => {
  it('draws a smooth trend and highlights the latest score in the grade palette', () => {
    const { container } = render(<FunctionCards cards={[card]} previous={period('May', '05')} linkable={false} />);

    expect(screen.getByRole('img', { name: 'RCM 6-month trend, latest score 86.5%' })).toBeInTheDocument();
    expect(screen.getByTestId('sparkline-latest-score')).toHaveTextContent('86.5%');
    expect(container.querySelector('[data-testid="sparkline-line"]')?.getAttribute('d')).toMatch(/C\d/);
    expect(container.querySelector('svg title')?.textContent).toBe('January 2026: 82.1%');
  });

  it('does not invent a latest-score badge when the function score is unavailable', () => {
    render(<FunctionCards cards={[{ ...card, score: null }]} previous={null} linkable={false} />);

    expect(screen.getByRole('img', { name: 'RCM 6-month trend' })).toBeInTheDocument();
    expect(screen.queryByTestId('sparkline-latest-score')).not.toBeInTheDocument();
  });
});
