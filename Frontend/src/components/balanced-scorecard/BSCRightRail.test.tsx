import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { BSCRightRail } from './BSCRightRail';
import { GaugeSVG } from './GaugeSVG';

const history = [
  { month: 'May', year: 2026, score: 68.1 },
  { month: 'June', year: 2026, score: 70.3 },
];

const renderRail = (overallScore: number | null) =>
  render(
    <BSCRightRail
      perspectives={[]}
      overallScore={overallScore}
      selectedKpiRow={null}
      kpiHistory={[]}
      overallHistory={history}
      selectedMonth="June"
    />,
  );

describe('BSCRightRail Overall Performance card', () => {
  it('shows 70.3% as D "Below Average" with orange grade tokens', () => {
    renderRail(70.3);
    const card = screen.getByRole('region', { name: 'Overall performance score' });
    const scoreEl = within(card).getAllByText('70.3%')[0];

    expect(scoreEl).toHaveAttribute('data-grade', 'D');
    expect(scoreEl.style.color).toBe('var(--pms-grade-d-text)');
    const badge = within(card).getByText('Below Average');
    expect(badge.style.background).toBe('var(--pms-grade-d-badge-bg)');
    expect(badge.style.color).toBe('var(--pms-grade-d-badge-text)');
    expect(within(card).queryByText('Good')).not.toBeInTheDocument();
  });

  it('uses the Excellent label and A tokens at ≥95', () => {
    renderRail(97.2);
    const card = screen.getByRole('region', { name: 'Overall performance score' });
    expect(within(card).getByText('Excellent')).toBeInTheDocument();
    expect(within(card).getAllByText('97.2%')[0].style.color).toBe('var(--pms-grade-a-text)');
  });

  it('uses the Unsatisfactory label and E tokens below 70', () => {
    renderRail(58.4);
    const card = screen.getByRole('region', { name: 'Overall performance score' });
    expect(within(card).getByText('Unsatisfactory')).toBeInTheDocument();
    expect(within(card).getAllByText('58.4%')[0].style.color).toBe('var(--pms-grade-e-text)');
  });

  it('keeps the No data label when there is no score', () => {
    render(
      <BSCRightRail perspectives={[]} overallScore={null} selectedKpiRow={null} kpiHistory={[]} overallHistory={[]} />,
    );
    const card = screen.getByRole('region', { name: 'Overall performance score' });
    expect(within(card).getByText('No data')).toBeInTheDocument();
  });
});

describe('GaugeSVG', () => {
  it('fills the arc with the grade gauge token', () => {
    const { container } = render(<GaugeSVG score={70.3} />);
    const stops = Array.from(container.querySelectorAll('stop'));
    expect(stops).toHaveLength(3);
    for (const stop of stops) {
      expect(stop.getAttribute('style')).toContain('var(--pms-grade-d-gauge)');
    }
  });
});
