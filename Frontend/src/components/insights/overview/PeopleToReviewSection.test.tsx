import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import type { InsightPeopleContributionAnalysis, InsightPersonContribution } from '../../../features/insights/types';
import { PeopleToReviewSection } from './OverviewSections';

const person = (overrides: Partial<InsightPersonContribution> & { employee_id: string }): InsightPersonContribution => ({
  employee_name: `Agent ${overrides.employee_id}`,
  team: 'Pre-Approvals IP Offshore',
  performance_level: 'Employee',
  position: 'Agent L1',
  kpi_key: 'InitialErrorRate',
  kpi_label: 'Initial Error Rate',
  unit: '%',
  direction: 'lower_better',
  current_value: 4.5,
  target_value: 2,
  gap: -2.5,
  weighted_impact: -1.9,
  trend: null,
  severity: 'High',
  classification: 'negative',
  achievement_percent: 44,
  performance_score: 81.4,
  ...overrides,
});

function analysis(rows: InsightPersonContribution[], employeesMeasured = 10): InsightPeopleContributionAnalysis {
  return {
    kpi_key: 'InitialErrorRate',
    kpi_label: 'Initial Error Rate',
    unit: '%',
    direction: 'lower_better',
    total_employees: employeesMeasured,
    negative_contributors: rows.length,
    positive_contributors: 0,
    data_issues: 0,
    rows,
  };
}

const rowsOf = () => within(screen.getByRole('list', { name: 'People to review' })).getAllByRole('button');

describe('PeopleToReviewSection', () => {
  it('shows the performance level as the role when the position is the "All positions" placeholder, and a dash when both are missing', () => {
    render(<PeopleToReviewSection analysis={analysis([
      person({ employee_id: 'A', position: 'All positions', performance_level: 'Team Leader' }),
      person({ employee_id: 'B', position: '', performance_level: '' , weighted_impact: -0.5}),
    ])} onOpenEmployee={vi.fn()} />);

    const [first, second] = rowsOf();
    expect(within(first).getByText('Team Leader')).toBeInTheDocument();
    expect(within(second).getByText('—')).toBeInTheDocument();
  });

  it('keeps a real position as the role', () => {
    render(<PeopleToReviewSection analysis={analysis([person({ employee_id: 'A', position: 'Media Buyer' })])} onOpenEmployee={vi.fn()} />);
    expect(within(rowsOf()[0]).getByText('Media Buyer')).toBeInTheDocument();
  });

  it('shows the effect in points, with two decimals below one point and one decimal from it', () => {
    render(<PeopleToReviewSection analysis={analysis([
      person({ employee_id: 'A', weighted_impact: -1.9 }),
      person({ employee_id: 'B', weighted_impact: -0.42, classification: 'negative' }),
    ])} onOpenEmployee={vi.fn()} />);

    expect(within(rowsOf()[0]).getByText('−1.9 pts')).toBeInTheDocument();
    expect(within(rowsOf()[1]).getByText('−0.42 pts')).toBeInTheDocument();
  });

  it('names the effect column and explains it from a keyboard-reachable info button', async () => {
    const user = userEvent.setup();
    render(<PeopleToReviewSection analysis={analysis([person({ employee_id: 'A' })])} onOpenEmployee={vi.fn()} />);

    const info = screen.getByRole('button', { name: 'What "Effect on team score" means for Initial Error Rate' });
    expect(screen.getByText('Effect on team score')).toBeInTheDocument();
    expect(info).toHaveAttribute('aria-expanded', 'false');

    info.focus();
    await user.keyboard('{Enter}');
    expect(info).toHaveAttribute('aria-expanded', 'true');
    const explanation = screen.getByRole('note');
    expect(explanation).toHaveTextContent("Points this person's Initial Error Rate shortfall takes off the team's average score.");
    expect(explanation).toHaveTextContent('KPI weight minus what they earned, shared across the employees measured.');
    expect(info).toHaveAttribute('aria-controls', explanation.id);

    await user.keyboard('{Escape}');
    expect(screen.queryByRole('note')).not.toBeInTheDocument();
    expect(info).toHaveAttribute('aria-expanded', 'false');
  });

  it('gives each person their own loss on their score in the row label: effect × employees measured', () => {
    // −1.9 points on the team average over 10 measured employees is −19.0 points on the person's own score.
    render(<PeopleToReviewSection analysis={analysis([person({ employee_id: 'A', employee_name: 'Analyst One', weighted_impact: -1.9 })], 10)} onOpenEmployee={vi.fn()} />);
    expect(rowsOf()[0]).toHaveAccessibleName('Open Analyst One: effect on team score −1.9 pts, −19.0 pts on their own score');
  });

  it('expands "View all" in place, turns it into "Show less", and collapses it again, without changing the page filters', async () => {
    const user = userEvent.setup();
    const onOpenFullAnalysis = vi.fn();
    const rows = [1, 2, 3, 4, 5].map((index) => person({ employee_id: `E${index}`, employee_name: `Person ${index}`, weighted_impact: -index }));
    render(<PeopleToReviewSection analysis={analysis(rows)} onOpenEmployee={vi.fn()} onOpenFullAnalysis={onOpenFullAnalysis} />);

    const toggle = screen.getByRole('button', { name: 'View all' });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(toggle).toHaveAttribute('aria-controls', 'people-review-list');
    expect(rowsOf()).toHaveLength(3);

    await user.click(toggle);
    expect(screen.getByRole('button', { name: 'Show less' })).toHaveAttribute('aria-expanded', 'true');
    expect(rowsOf()).toHaveLength(5);

    await user.click(screen.getByRole('button', { name: 'Show less' }));
    expect(screen.getByRole('button', { name: 'View all' })).toHaveAttribute('aria-expanded', 'false');
    expect(rowsOf()).toHaveLength(3);
    expect(onOpenFullAnalysis).not.toHaveBeenCalled();
  });

  it('opens the full KPI analysis from a named button, and offers "Back to overview" while it is open', async () => {
    const user = userEvent.setup();
    const onOpenFullAnalysis = vi.fn();
    const onBackToOverview = vi.fn();
    const { rerender } = render(<PeopleToReviewSection analysis={analysis([person({ employee_id: 'A' })])} onOpenEmployee={vi.fn()} onOpenFullAnalysis={onOpenFullAnalysis} onBackToOverview={onBackToOverview} />);

    await user.click(screen.getByRole('button', { name: 'Full Initial Error Rate analysis' }));
    expect(onOpenFullAnalysis).toHaveBeenCalledTimes(1);

    rerender(<PeopleToReviewSection analysis={analysis([person({ employee_id: 'A' })])} onOpenEmployee={vi.fn()} fullAnalysisOpen onOpenFullAnalysis={onOpenFullAnalysis} onBackToOverview={onBackToOverview} />);
    expect(screen.queryByRole('button', { name: 'Full Initial Error Rate analysis' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Back to overview' }));
    expect(onBackToOverview).toHaveBeenCalledTimes(1);
  });

  it('says who is listed in the subtitle', () => {
    render(<PeopleToReviewSection analysis={analysis([person({ employee_id: 'A' })])} onOpenEmployee={vi.fn()} />);
    expect(screen.getByText('People pulling the team score down most on Initial Error Rate')).toBeInTheDocument();
  });
});
