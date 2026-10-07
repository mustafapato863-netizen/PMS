import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
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
  afterEach(() => vi.unstubAllGlobals());
  it('draws a smooth trend and highlights the latest score in the grade palette', () => {
    const { container } = render(<FunctionCards cards={[card]} previous={period('May', '05')} linkable={false} />);

    expect(screen.getByRole('img', { name: /RCM score trend, last six months/ })).toBeInTheDocument();
    expect(screen.getAllByTestId('function-trend-value')).toHaveLength(6);
    expect(screen.getAllByTestId('function-trend-value').at(-1)).toHaveTextContent('86.5%');
    expect(container.querySelector('[data-testid="function-trend-series"]')?.getAttribute('d')).toMatch(/C\d/);
    expect(screen.getByRole('img', { name: /Jan 82.1%/ })).toBeInTheDocument();
    expect(container.querySelector('[data-grade="C"]')).toBeInTheDocument();
  });

  it('does not invent a grade or score when the function and its history are unavailable', () => {
    render(<FunctionCards cards={[{ ...card, score: null, trend: card.trend.map((point) => ({ ...point, score: null })) }]} previous={null} linkable={false} />);
    expect(screen.getByText('No grade')).toBeInTheDocument();
    expect(screen.getByTestId('function-trend-empty')).toBeVisible();
    expect(screen.queryByTestId('function-trend-value')).not.toBeInTheDocument();
  });

  it('keeps missing months as gaps without fabricating values or area fills', () => {
    render(<FunctionCards cards={[{ ...card, trend: card.trend.map((point, index) => index === 2 ? { ...point, score: null } : point) }]} previous={null} linkable={false} />);
    expect(screen.getAllByTestId('function-trend-series')).toHaveLength(2);
    expect(screen.getAllByTestId('function-trend-area')).toHaveLength(2);
    expect(screen.getAllByTestId('function-trend-value')).toHaveLength(5);
  });

  it('renders static cards without resize observers, hover updates, tooltips, or animation', () => {
    const observer = vi.fn();
    vi.stubGlobal('ResizeObserver', observer);
    render(<FunctionCards cards={[card]} previous={null} linkable={false} />);
    const chart = screen.getByTestId('function-trend-chart');
    const markup = chart.innerHTML;
    fireEvent.pointerMove(chart, { clientX: 100, clientY: 50 });
    fireEvent.pointerDown(chart, { clientX: 100, clientY: 50 });
    expect(chart.innerHTML).toBe(markup);
    expect(chart).toHaveAttribute('pointer-events', 'none');
    expect(chart.querySelector('[tabindex], animate, animateTransform, title')).toBeNull();
    expect(screen.queryByTestId('executive-trend-tooltip')).not.toBeInTheDocument();
    expect(observer).not.toHaveBeenCalled();
  });

  it('labels the adaptive axis honestly and includes scores below 50 and above 100', () => {
    const { rerender } = render(<FunctionCards cards={[card]} previous={null} linkable={false} />);
    expect(screen.getAllByTestId('function-trend-tick').map((tick) => tick.textContent)).toEqual(['50%', '75%', '100%']);
    rerender(<FunctionCards cards={[{ ...card, trend: [{ period: period('January', '01'), score: 18 }, { period: period('February', '02'), score: 120 }] }]} previous={null} linkable={false} />);
    expect(screen.getAllByTestId('function-trend-tick').map((tick) => tick.textContent)).toEqual(['0%', '62.5%', '125%']);
    expect(screen.getAllByTestId('function-trend-value').map((label) => label.textContent)).toEqual(['18.0%', '120.0%']);
  });

  it('uses unique area fills and preserves each function details route', () => {
    const { container } = render(<MemoryRouter><FunctionCards cards={[card, { ...card, function: 'Marketing', grade: 'B', score: 93 }]} previous={null} linkable /></MemoryRouter>);
    expect(screen.getByRole('link', { name: 'View RCM function' })).toHaveAttribute('href', '/function-summary/rcm');
    expect(screen.getByRole('link', { name: 'View Marketing function' })).toHaveAttribute('href', '/function-summary/marketing');
    const fills = [...container.querySelectorAll('linearGradient')].map((gradient) => gradient.id);
    expect(new Set(fills).size).toBe(2);
    expect(within(screen.getByRole('article', { name: 'Marketing function' })).getByText('Grade B')).toBeInTheDocument();
  });
});
