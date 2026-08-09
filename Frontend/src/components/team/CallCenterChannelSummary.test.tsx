import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import CallCenterChannelSummary from './CallCenterChannelSummary';

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

describe('CallCenterChannelSummary', () => {
  it('opens the selected channel through the same filter callback', () => {
    const onChannelSelect = vi.fn();
    render(
      <CallCenterChannelSummary
        rows={[rowFor('Inbound', 88), rowFor('Outbound', 76)]}
        onChannelSelect={onChannelSelect}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Open Inbound channel' }));

    expect(onChannelSelect).toHaveBeenCalledWith('inbound');
  });
});
