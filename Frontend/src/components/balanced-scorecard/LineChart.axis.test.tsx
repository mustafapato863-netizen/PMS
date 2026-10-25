import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { LineChart, percentageScoreAxisMax } from './LineChart';

const axisLabels = (svg: HTMLElement) =>
  [...svg.querySelectorAll('text')].map((node) => node.textContent ?? '');

describe('percentageScoreAxisMax', () => {
  it('stays at 100 when every score and the target are at or below 100', () => {
    expect(percentageScoreAxisMax(86.6)).toBe(100);
    expect(percentageScoreAxisMax(100)).toBe(100);
    expect(percentageScoreAxisMax(Number.NaN)).toBe(100);
  });

  it('rounds a value above 100 up to the next 5', () => {
    expect(percentageScoreAxisMax(100.1)).toBe(105);
    expect(percentageScoreAxisMax(103)).toBe(105);
    expect(percentageScoreAxisMax(105)).toBe(110);
    expect(percentageScoreAxisMax(106)).toBe(110);
  });
});

describe('LineChart percentage axis', () => {
  const history = [
    { month: '4', year: 2026, score: 75.8 },
    { month: '5', year: 2026, score: 77.4 },
    { month: '6', year: 2026, score: 76.5 },
    { month: '7', year: 2026, score: 86.4 },
    { month: '8', year: 2026, score: 86.1 },
    { month: '9', year: 2026, score: 86.6 },
  ];

  it('labels the top of a 100% target chart at 100, not above it', () => {
    const view = render(<LineChart history={history} targetValue={100} />);
    const chart = view.getByRole('img', { name: /trend/i });
    const labels = axisLabels(chart);

    expect(labels).toContain('100%');
    expect(labels.some((label) => /^10[1-9]%$/.test(label) || /^1[1-9]\d%$/.test(label))).toBe(false);
    expect(chart.textContent).toMatch(/Target\s+100%/);
  });

  it('raises the top label above the highest point when a score exceeds 100', () => {
    const view = render(
      <LineChart
        history={[
          { month: '8', year: 2026, score: 98 },
          { month: '9', year: 2026, score: 104 },
        ]}
        targetValue={100}
      />,
    );
    const labels = axisLabels(view.getByRole('img', { name: /trend/i }));

    expect(labels).toContain('105%');
    expect(labels).not.toContain('104%');
  });
});
