import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { apiFetch } from '../../../lib/apiClient';
import { Agent360Scorecard } from './Agent360Scorecard';

vi.mock('../../../lib/apiClient', () => ({ apiFetch: vi.fn() }));
const mockedApiFetch = vi.mocked(apiFetch);

const sampleProfile = {
  employee_code: 'EMP-101',
  employee_name: 'Test Agent',
  current_period: 'September 2026',
  overall_score: 88.5,
  overall_grade: 'B',
  score_trend: [
    { month: 'August', year: 2026, score: 85.0 },
    { month: 'September', year: 2026, score: 88.5 },
  ],
  kpi_scores: [{ name: 'Booking Rate', score: 88.5, grade: 'B', status: 'Good', target: 100, weight: 1 }],
  top_strength: 'Booking',
  top_opportunity: null,
  active_corrective_actions: 1,
  corrective_action_summary: '1 active',
  performance_classification: 'Improving',
  cohort: { cohort_size: 8, cohort_avg_score: 82.0, percentile_band: 'Top 25%' },
  what_if_suggestions: [],
};

describe('Agent360Scorecard', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the self-service scorecard with score and grade', async () => {
    mockedApiFetch.mockResolvedValue(sampleProfile as never);
    render(<Agent360Scorecard />);
    await waitFor(() => expect(screen.getByTestId('agent-360-scorecard')).toBeInTheDocument());
    expect(screen.getByText('My 360° Scorecard')).toBeInTheDocument();
    expect(screen.getAllByText('88.5%').length).toBeGreaterThan(0);
    expect(screen.getAllByText('B').length).toBeGreaterThan(0);
    expect(screen.getByText((_, el) => el?.textContent === '3.5 pts')).toBeInTheDocument();
    expect(screen.getByText('Top 25%')).toBeInTheDocument();
  });

  it('shows a friendly error when not linked', async () => {
    mockedApiFetch.mockRejectedValue(new Error('not linked'));
    render(<Agent360Scorecard />);
    await waitFor(() => expect(screen.getByText(/not linked/i)).toBeInTheDocument());
  });

  it('runs deterministic What-If simulation and displays projected grade', async () => {
    mockedApiFetch.mockImplementation((url: string) => {
      if (url === '/api/ai/agent-360/what-if') {
        return Promise.resolve({
          employee_code: 'EMP-101',
          period: 'September 2026',
          kpi_name: 'Booking Rate',
          improvement_pct: 5,
          current_score: 88.5,
          projected_score: 95.2,
          current_grade: 'B',
          projected_grade: 'A',
          score_delta: 6.7,
          current_achievement: 0.885,
          projected_achievement: 0.952,
          capped: false,
        }) as never;
      }
      return Promise.resolve(sampleProfile as never);
    });

    render(<Agent360Scorecard />);
    await waitFor(() => expect(screen.getByTestId('what-if-simulator')).toBeInTheDocument());
    await userEvent.click(screen.getByRole('button', { name: /Simulate impact/i }));
    expect(await screen.findByText('95.2%')).toBeInTheDocument();
    expect(screen.getByText('Grade B → A')).toBeInTheDocument();
  });

  it('allows managers to switch to an authorized direct report 360°', async () => {
    mockedApiFetch.mockImplementation((url: string) => {
      if (url === '/api/ai/agent-360/directory') {
        return Promise.resolve({
          employees: [{ employee_code: 'EMP-202', employee_name: 'Omar Report', team: 'Inbound', position: 'Agent' }],
        }) as never;
      }
      if (url.includes('employee_code=EMP-202')) {
        return Promise.resolve({
          ...sampleProfile,
          employee_code: 'EMP-202',
          employee_name: 'Omar Report',
          overall_score: 91.0,
          overall_grade: 'B',
        }) as never;
      }
      return Promise.resolve(sampleProfile as never);
    });

    render(<Agent360Scorecard canSwitchEmployee />);
    const picker = await screen.findByLabelText('Inspect employee 360°');
    await userEvent.selectOptions(picker, 'EMP-202');
    expect(await screen.findByText('Omar Report · 360° Scorecard')).toBeInTheDocument();
    expect(screen.getAllByText('91.0%').length).toBeGreaterThan(0);
  });
});
