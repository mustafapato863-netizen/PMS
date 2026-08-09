import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import PreApprovalsWorkflowSummary from './PreApprovalsWorkflowSummary';

const rowFor = (team: string, score: number): TeamAgentRow => ({
  id: `${team}-${score}`,
  name: 'Test employee',
  team,
  month: 'June',
  performanceLevel: 'Employee',
  score,
  gradeClass: 'B',
  gradeLabel: 'Meets Expectations',
  status: 'Meet',
  rootCauseAuto: '',
  rootCauseNote: '',
  correctiveAction: '',
  suggestedAction: '',
  ahtMinutes: 0,
  bookingRate: 0,
  attendRate: 0,
  raw: { identity: { name: 'Test employee', month: 'June', team } } as TeamAgentRow['raw'],
});

describe('PreApprovalsWorkflowSummary', () => {
  it('opens the selected workflow through the same filter callback', () => {
    const onWorkflowSelect = vi.fn();
    render(
      <PreApprovalsWorkflowSummary
        rows={[rowFor('Pre-Approvals OP Final SHJAJM', 88)]}
        onWorkflowSelect={onWorkflowSelect}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Open OP Final workflow' }));

    expect(onWorkflowSelect).toHaveBeenCalledWith('op_final');
  });
});
