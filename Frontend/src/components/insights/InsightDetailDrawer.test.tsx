import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import type { InsightItem } from '../../features/insights/types';
import InsightDetailDrawer from './InsightDetailDrawer';

const insight = {
  id: 'score-1',
  severity: 'risk',
  insight_type: 'performance',
  title: 'Agent average declined by 10.0%',
  explanation: 'Average score moved from 80.0 to 70.0 across 1 measured record.',
  scope: 'Outbound · Agent',
  impact_points: -10,
  trend_label: 'vs July 2026',
  priority_reason: 'Overall score movement is 10.0%.',
  status: 'open',
  team: 'Outbound',
  performance_level: 'Employee',
  position: 'Agent',
  employee_id: null,
  kpi_key: null,
  detail: {
    current_value: 70,
    previous_value: 80,
    target_value: null,
    unit: '%',
    direction: null,
    impact_points: -10,
    affected_teams: [],
    affected_positions: [],
    affected_employees: [],
    evidence: [],
    warnings: ['A source field is missing.'],
    recommended_focus: 'Review the score movement.',
    basis_note: 'Scores can be affected by evaluation settings. Comparable raw performance is unchanged.',
  },
  planning_context: { source_insight_id: 'score-1' },
} as InsightItem;

describe('InsightDetailDrawer basis note', () => {
  it('shows the settings note outside the data-quality warnings', () => {
    render(<MemoryRouter><InsightDetailDrawer insight={insight} onClose={() => undefined} /></MemoryRouter>);

    expect(screen.getByText('Average score moved from 80.0 to 70.0 across 1 measured record.')).toBeInTheDocument();
    const note = screen.getByTestId('basis-comparison-note');
    expect(note).toHaveTextContent('Scores can be affected by evaluation settings.');
    expect(note).toHaveTextContent('Comparable raw performance is unchanged.');
    const quality = screen.getByText('Data-quality warnings').closest('section');
    expect(quality).toHaveTextContent('A source field is missing.');
    expect(quality).not.toHaveTextContent('evaluation settings');
  });
});
