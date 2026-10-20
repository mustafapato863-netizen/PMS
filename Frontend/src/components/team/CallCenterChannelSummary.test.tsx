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

    expect(screen.getByRole('heading', { name: 'Call Center Overview' })).toBeInTheDocument();
    expect(screen.getByText('Department performance')).toBeInTheDocument();
    expect(screen.getByText('Employees affecting the average')).toBeInTheDocument();
    expect(screen.getByText('Next decision')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Open Inbound channel' }));

    expect(onChannelSelect).toHaveBeenCalledWith('inbound');
  });

  it('prints each channel team score and the headcount-weighted department average', () => {
    render(
      <CallCenterChannelSummary
        rows={[rowFor('Inbound', 80), rowFor('Inbound', 100), rowFor('Outbound', 70)]}
        onChannelSelect={vi.fn()}
        channelScores={{ inbound: 92.64, outbound: 87.74 }}
      />,
    );

    const inbound = screen.getByRole('button', { name: 'Open Inbound channel' });
    const outbound = screen.getByRole('button', { name: 'Open Outbound channel' });
    expect(inbound).toHaveTextContent('92.6%');
    expect(inbound).toHaveTextContent('Team score');
    expect(inbound).not.toHaveTextContent('90.0%');
    expect(outbound).toHaveTextContent('87.7%');
    expect(outbound).not.toHaveTextContent('70.0%');
    expect(screen.getByText('91.0%')).toBeInTheDocument();
    expect(screen.getByText(/Average of the Inbound and Outbound team scores/)).toBeInTheDocument();
  });
});
