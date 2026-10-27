import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import CallCenterChannelSummary from './CallCenterChannelSummary';

const rowFor = (team: string, score: number): TeamAgentRow => ({
  id: `${team}-${score}-${Math.random()}`,
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
  it('opens the selected channel through the same filter callback and renders Support Positions', () => {
    const onChannelSelect = vi.fn();
    render(
      <CallCenterChannelSummary
        rows={[rowFor('Inbound', 88), rowFor('Outbound', 76), rowFor('Call Center', 91)]}
        onChannelSelect={onChannelSelect}
      />,
    );

    expect(screen.getByRole('heading', { name: 'Call Center Overview' })).toBeInTheDocument();
    expect(screen.getByText('Department performance')).toBeInTheDocument();
    expect(screen.getByText('Employees affecting the average')).toBeInTheDocument();
    expect(screen.getByText('Next decision')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open Support Positions section' })).toHaveTextContent('91.0%');
    fireEvent.click(screen.getByRole('button', { name: 'Open Inbound channel' }));

    expect(onChannelSelect).toHaveBeenCalledWith('inbound');
  });

  it('prints each channel team score, the Support Positions average, and the 3-team department average', () => {
    render(
      <CallCenterChannelSummary
        rows={[
          rowFor('Inbound', 80),
          rowFor('Inbound', 100),
          rowFor('Outbound', 70),
          rowFor('Call Center', 93.39),
          rowFor('Call Center', 84.44),
          rowFor('Call Center', 100.0),
          rowFor('Call Center', 86.29),
        ]}
        onChannelSelect={vi.fn()}
        channelScores={{ inbound: 92.64, outbound: 87.74 }}
      />,
    );

    const inbound = screen.getByRole('button', { name: 'Open Inbound channel' });
    const outbound = screen.getByRole('button', { name: 'Open Outbound channel' });
    const support = screen.getByRole('button', { name: 'Open Support Positions section' });

    expect(inbound).toHaveTextContent('92.6%');
    expect(inbound).toHaveTextContent('Team score');
    expect(inbound).not.toHaveTextContent('90.0%');
    expect(outbound).toHaveTextContent('87.7%');
    expect(outbound).not.toHaveTextContent('70.0%');
    expect(support).toHaveTextContent('91.0%');
    expect(support).toHaveTextContent('Average score');
    expect(support).toHaveTextContent('4 employees');
    // (92.6 + 87.7 + 91.0) / 3 = 90.433... -> 90.4%
    expect(screen.getByText('90.4%')).toBeInTheDocument();
    expect(screen.getByText(/Average of the Inbound, Outbound, and Support Positions team scores/)).toBeInTheDocument();
  });
});
