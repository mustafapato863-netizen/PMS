import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { summarizeActions } from '../../../features/executive/compose';
import type { ExecutivePeriod } from '../../../features/executive/types';
import CorrectiveActionInsightsCard from './CorrectiveActionInsightsCard';

const period: ExecutivePeriod = { key: '2026-06', year: 2026, month: 'June' };
const data = summarizeActions([
  { id: '1', employee_id: 'a', team: 'Inbound', month: 'June', action_type: 'Coaching', root_cause_note: 'Booking rate', status: 'Open' },
  { id: '2', employee_id: 'b', team: 'Inbound', month: 'June', action_type: 'Coaching', root_cause_note: 'Booking rate, AHT', status: 'Completed' },
  { id: '3', employee_id: 'c', team: 'Coding', month: 'June', action_type: 'Training', root_cause_note: 'Quality score', status: 'Open' },
], new Date(2026, 6, 6), period);

describe('CorrectiveActionInsightsCard', () => {
  it('renders the old analytical breakdown without operational status controls or links', () => {
    render(<CorrectiveActionInsightsCard data={data} effective={period} scopeLabel="Company-wide" />);
    const types = screen.getAllByTestId('action-type-rank');
    expect(types[0]).toHaveTextContent('Coaching2 actions');
    const teams = screen.getAllByTestId('action-team-rank');
    expect(teams[0]).toHaveTextContent('Inbound2 actions');
    expect(screen.getAllByTestId('action-kpi-rank')[0]).toHaveTextContent('Booking Rate2 actions');
    const iconLabels = screen.getAllByTestId('ranked-row-icon').map((icon) => icon.getAttribute('data-icon-for'));
    expect(iconLabels).toEqual(expect.arrayContaining(['Coaching', 'Inbound', 'Booking Rate', 'AHT (Handle Time)', 'Quality Score']));
    expect(screen.getAllByTestId('ranked-row-icon')).toHaveLength(7);
    expect(screen.getByText('Actions this month').parentElement).toHaveTextContent('3');
    expect(screen.getByText('Company-wide · June 2026 · Decision patterns')).toBeInTheDocument();
    expect(screen.queryByTestId('action-tile-open')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open Corrective Actions' })).not.toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: /status/i })).not.toBeInTheDocument();
  });

  it('selecting a team updates types, repeated KPIs and counts without leaking other teams', () => {
    render(<CorrectiveActionInsightsCard data={data} effective={period} scopeLabel="Company-wide" />);
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter actions by team' }), { target: { value: 'Coding' } });
    expect(screen.getByRole('heading', { name: 'Most repeated KPIs · Coding' })).toBeInTheDocument();
    expect(screen.getAllByTestId('action-kpi-rank')).toHaveLength(1);
    expect(screen.getByTestId('action-kpi-rank')).toHaveTextContent('Quality Score1 action');
    expect(screen.getByTestId('action-type-rank')).toHaveTextContent('Training1 action');
    expect(screen.queryByText('Booking Rate')).not.toBeInTheDocument();
    expect(screen.getByText('Actions this month').parentElement).toHaveTextContent('1');
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter actions by team' }), { target: { value: '' } });
    expect(screen.getByText('Actions this month').parentElement).toHaveTextContent('3');
  });

  it('clears stale local team selection when global scope changes', () => {
    const { rerender } = render(<CorrectiveActionInsightsCard data={data} effective={period} scopeLabel="Company-wide" />);
    fireEvent.change(screen.getByRole('combobox', { name: 'Filter actions by team' }), { target: { value: 'Inbound' } });
    const coding = { ...data, analytics: { actions: data.analytics!.actions.filter((action) => action.team === 'Coding'), unassigned_period: 0 } };
    rerender(<CorrectiveActionInsightsCard data={coding} effective={period} scopeLabel="RCM" />);
    const select = screen.getByRole('combobox', { name: 'Filter actions by team' });
    expect(select).toHaveValue('');
    expect(within(select).queryByRole('option', { name: 'Inbound' })).not.toBeInTheDocument();
    expect(screen.getByTestId('action-kpi-rank')).toHaveTextContent('Quality Score');
  });

  it('distinguishes no recorded actions from unavailable analytics', () => {
    const empty = summarizeActions([], new Date(2026, 6, 6), period);
    const { rerender } = render(<CorrectiveActionInsightsCard data={empty} effective={period} scopeLabel="Company-wide" />);
    expect(screen.getByText('No corrective actions recorded for June 2026 in this scope.')).toBeInTheDocument();
    rerender(<CorrectiveActionInsightsCard data={null} effective={period} scopeLabel="Company-wide" />);
    expect(screen.getByText("Action analysis isn't available for this view yet.")).toBeInTheDocument();
  });
});
