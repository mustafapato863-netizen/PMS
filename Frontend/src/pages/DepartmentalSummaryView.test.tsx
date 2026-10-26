import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { User } from '../types';
import type { ExecutiveSummary } from '../features/executive/types';
import { composeExecutiveSummary, monthsBetween, periodOf, previousRangeOf, toExecRecords, type ComposeInput } from '../features/executive/compose';
import { FIXTURE_TEAM_FUNCTIONS, fixtureActions, fixtureAgentRecords, fixtureDrivers } from '../features/executive/executive.fixture';
import type { UseExecutiveSummaryArgs } from '../features/executive/useExecutiveSummary';
import DepartmentalSummaryView from './DepartmentalSummaryView';
import { periodOptionsFor } from '../features/executive/viewModel';

const state = vi.hoisted(() => ({
  role: 'Admin' as string,
  user: null as Partial<User> | null,
  summary: null as ExecutiveSummary | null,
  loading: false,
  lastArgs: null as UseExecutiveSummaryArgs | null,
}));

vi.mock('../context/RoleContext', () => ({ useUserRole: () => ({ role: state.role }) }));
vi.mock('../context/auth', () => ({ useAuth: () => ({ currentUser: state.user }) }));
vi.mock('../features/executive/useExecutiveSummary', () => ({
  useExecutiveSummary: (args: UseExecutiveSummaryArgs) => {
    state.lastArgs = args;
    // Mirrors the hook: every assigned team; the URL team only when assigned; otherwise the single team, or none.
    const managerTeamOptions = args.view === 'managerial' ? (args.managerTeams ?? ['Inbound']) : [];
    const requested = args.filters.team;
    const managerTeam = args.view !== 'managerial' ? null
      : requested && managerTeamOptions.includes(requested) ? requested
        : managerTeamOptions.length === 1 ? managerTeamOptions[0] : null;
    return {
      summary: state.summary,
      options: { regions: ['EGY', 'UAE'], functions: ['Call Center', 'RCM', 'Pre-Approvals', 'Marketing'], teams: ['Inbound', 'Outbound', 'Pre-Approvals IP Offshore', 'Pre-Approvals OP Dubai'], levels: ['Employee'] },
      isLoading: state.loading,
      error: null,
      source: 'composed',
      managerTeam,
      managerTeamOptions,
    };
  },
}));
vi.mock('../lib/apiClient', () => ({
  apiFetch: vi.fn().mockResolvedValue({
    success: true,
    data: { items: [], page_size: 8, next_cursor: null, has_more: false, total: 0 },
  }),
}));

const TODAY = new Date(2026, 6, 6);
const records = toExecRecords(fixtureAgentRecords());
const build = (patch: Partial<ComposeInput> = {}) => composeExecutiveSummary({
  view: 'corporate', role: 'Admin', records, filters: {}, teamFunctions: FIXTURE_TEAM_FUNCTIONS,
  drivers: fixtureDrivers(), actions: fixtureActions(TODAY), comparisonRecords: records, today: TODAY, ...patch,
});

function renderAt(path = '/executive') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const rendered = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/executive" element={<DepartmentalSummaryView />} />
          <Route path="/function-summary" element={<div>Function Summary page</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const launcher = screen.queryByRole('button', { name: /Departmental filters/i });
  if (launcher) fireEvent.click(launcher);
  return rendered;
}

beforeEach(() => {
  state.role = 'Admin';
  state.user = { id: 'u1', name: 'Super Admin', role: 'Admin', accessible_teams: [] };
  state.summary = build();
  state.loading = false;
  state.lastArgs = null;
});

describe('DepartmentalSummaryView role routing', () => {
  it('treats legacy All filter values as unfiltered when returning from other dashboards', () => {
    renderAt('/executive?region=All&branch=all&function=ALL&team=All&level=All');
    expect(state.lastArgs?.filters).toMatchObject({
      region: undefined, branch: undefined, teamFunction: undefined, team: undefined, performanceLevel: undefined,
    });
    expect(screen.getByLabelText('Region')).toHaveValue('');
  });
  it.each([
    { role: 'Branch Director', grant: { accessible_branches: ['dubai'] }, url: 'branch=sharjah&region=UAE', filter: 'branch', value: 'dubai', label: /Branch: Dubai \(fixed by your role\)/ },
    { role: 'Regional Manager', grant: { accessible_regions: ['UAE'] }, url: 'region=EGY&branch=dubai', filter: 'region', value: 'UAE', label: /Region: UAE \(fixed by your role\)/ },
  ])('locks $role grant even with a contradictory URL and clear', ({ role, grant, url, filter, value, label }) => {
    state.role = role;
    state.user = { id: 'director', ...grant };
    renderAt(`/executive?period=2026-06&${url}&level=Corporate`);
    expect(state.lastArgs?.filters[filter as 'branch' | 'region']).toBe(value);
    expect(screen.getByRole('group', { name: label })).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(state.lastArgs?.filters[filter as 'branch' | 'region']).toBe(value);
    expect(state.lastArgs?.filters.periodKey).toBe('2026-06');
    expect(state.lastArgs?.filters.performanceLevel).toBeUndefined();
  });
  it.each(['Admin', 'General Manager', 'Executive', 'Viewer'])('%s gets the Corporate view', (role) => {
    state.role = role;
    renderAt();
    expect(state.lastArgs?.view).toBe('corporate');
    expect(screen.getByTestId('executive-corporate')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Executive Summary' })).toBeInTheDocument();
  });

  it('Manager gets the Managerial view with region/function/team locked', () => {
    state.role = 'Manager';
    state.user = { id: 'm1', name: 'Hany Mostafa', role: 'Manager', accessible_teams: ['Inbound'] };
    state.summary = build({ view: 'managerial', role: 'Manager', team: 'Inbound', comparisonRecords: null });
    renderAt();
    expect(state.lastArgs).toMatchObject({ view: 'managerial', managerTeams: ['Inbound'] });
    expect(screen.getByTestId('executive-managerial')).toBeInTheDocument();
    expect(screen.getByText('Team scope')).toBeInTheDocument();
    const filters = screen.getByRole('group', { name: 'Departmental filters' });
    expect(within(filters).getByRole('group', { name: /Region: EGY \(fixed by your role\)/ })).toBeInTheDocument();
    expect(within(filters).getByRole('group', { name: /Function: Call Center \(fixed by your role\)/ })).toBeInTheDocument();
    expect(within(filters).getByRole('group', { name: /Team: Inbound \(fixed by your role\)/ })).toBeInTheDocument();
    const scopeNotes = screen.getAllByRole('note').filter((note) => note.textContent?.startsWith('Scoped to your team.'));
    expect(scopeNotes).toHaveLength(1);
    expect(scopeNotes[0]).toHaveTextContent('Scoped to your team');
    expect(scopeNotes[0]).toHaveTextContent('This page shows your team only. Other teams are not named.');
    expect(screen.getByRole('heading', { name: 'Team KPIs — worst first' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Corrective actions' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Functions' })).not.toBeInTheDocument();
  });

  it('Manager with two assigned teams sees both, picks from exactly those two plus "All my teams", and ignores an unassigned URL team', () => {
    state.role = 'Manager';
    state.user = { id: 'm2', name: 'Two-team manager', role: 'Manager', accessible_teams: ['Inbound', 'Outbound'] };
    state.summary = build({ view: 'managerial', role: 'Manager', teamScope: ['Inbound', 'Outbound'], comparisonRecords: null });
    renderAt('/executive?team=Coding');
    expect(state.lastArgs).toMatchObject({ view: 'managerial', managerTeams: ['Inbound', 'Outbound'] });
    const filters = screen.getByRole('group', { name: 'Departmental filters' });
    expect(within(filters).queryByRole('group', { name: /Team: .*fixed by your role/ })).not.toBeInTheDocument();
    const teamPicker = within(filters).getByRole('button', { name: 'Team' });
    expect(teamPicker).toHaveTextContent('All my teams');
    fireEvent.click(teamPicker);
    const menu = screen.getByRole('listbox', { name: 'Team' });
    expect(within(menu).getAllByRole('option').map((option) => option.textContent?.trim())).toEqual(['All my teams', 'Inbound', 'Outbound']);
    expect(screen.getByTestId('executive-managerial')).toBeInTheDocument();
  });

  it('reads a range from the URL, passes it to the summary and shows the Range mode', () => {
    renderAt('/executive?from=2026-06&to=2026-09');
    expect(state.lastArgs?.range).toEqual({ from: '2026-06', to: '2026-09' });
    expect(screen.getByRole('button', { name: 'Range' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Last 3 months' })).toBeInTheDocument();
  });

  it('names the range on every card in range mode: no label shows the last month on its own', () => {
    const months = monthsBetween(periodOf(2026, 'June'), periodOf(2026, 'September'));
    state.role = 'Admin';
    state.summary = build({ range: { months, previousMonths: previousRangeOf(months) } });
    renderAt('/executive?from=2026-06&to=2026-09');
    const text = document.body.textContent ?? '';
    expect(text).toContain('Jun – Sep 2026');
    // "Sep 2026" alone is the last month. "Apr – Sep 2026" is a range (the monthly trend axis), so it is allowed.
    expect(text).not.toMatch(/(?<!– )\b(?:September|Sep) 2026\b/);
    expect(text).not.toMatch(/(?<!– )\bSeptember\b/);
  });

  it('treats From after To as no range and says so', () => {
    renderAt('/executive?from=2026-09&to=2026-06');
    expect(state.lastArgs?.range).toBeNull();
    expect(screen.getByText(/From month on or before To/)).toBeInTheDocument();
  });

  it('applies the selected team parent function together with the team filter', () => {
    renderAt();

    fireEvent.change(screen.getByLabelText('Team'), { target: { value: 'Inbound' } });

    expect(state.lastArgs?.filters).toMatchObject({ teamFunction: 'Call Center', team: 'Inbound' });
  });

  it('clears scope filters from the icon while preserving the selected period', () => {
    renderAt('/executive?period=2026-06&region=UAE&branch=Dubai&function=RCM&team=Inbound&level=Employee');

    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));

    expect(state.lastArgs?.filters).toEqual({ periodKey: '2026-06' });
  });

  it('restores a sub-team link under RCM and clears both hierarchy selections', () => {
    renderAt('/executive?period=2026-06&function=RCM&team=Pre-Approvals&sub_team=Pre-Approvals%20IP%20Offshore&level=Corporate');
    expect(state.lastArgs?.filters).toMatchObject({ teamFunction: 'RCM', team: 'Pre-Approvals IP Offshore', performanceLevel: 'Corporate' });
    expect(screen.getByLabelText('Team')).toHaveValue('Pre-Approvals');
    expect(screen.getByLabelText('Sub-team')).toHaveValue('Pre-Approvals IP Offshore');
    fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
    expect(state.lastArgs?.filters).toEqual({ periodKey: '2026-06' });
    expect(screen.queryByLabelText('Sub-team')).not.toBeInTheDocument();
  });

  it('ignores a sub-team URL value outside the selected parent', () => {
    renderAt('/executive?function=RCM&team=Pre-Approvals&sub_team=Coding');
    expect(state.lastArgs?.filters.team).toBe('Pre-Approvals');
  });

  it('ignores a contradictory legacy function/team link when restoring its new parent', () => {
    renderAt('/executive?function=Pre-Approvals&team=Coding');
    expect(state.lastArgs?.filters).toMatchObject({ teamFunction: 'RCM', team: 'Pre-Approvals' });
  });

  it('opens the canonical team page from the managerial report and roster links', () => {
    state.role = 'Manager';
    state.user = { id: 'm1', name: 'Hany Mostafa', role: 'Manager', accessible_teams: ['Pre-Approvals IP Offshore'] };
    state.summary = build({ view: 'managerial', role: 'Manager', team: 'Pre-Approvals IP Offshore', comparisonRecords: null });
    renderAt();
    expect(screen.getByRole('link', { name: 'Open team report' })).toHaveAttribute('href', '/team/pre-approvals');
    expect(screen.getByRole('link', { name: 'View roster' })).toHaveAttribute('href', '/team/pre-approvals');
  });

  it('Function Viewer is redirected to /function-summary', () => {
    state.role = 'Function Viewer';
    renderAt();
    expect(screen.getByText('Function Summary page')).toBeInTheDocument();
  });

  it('marks the corporate view read-only for Executive and Viewer, not for Admin', () => {
    state.role = 'Executive';
    const { unmount } = renderAt();
    expect(screen.getByText('Read-only')).toBeInTheDocument();
    unmount();
    state.role = 'Admin';
    renderAt();
    expect(screen.queryByText('Read-only')).not.toBeInTheDocument();
  });
});

describe('Corporate sections', () => {
  it('renders the company summary of every function without an Insights hand-off', () => {
    renderAt();
    expect(screen.getByRole('heading', { name: /^June 2026 company performance is \d+\.\d% below target\.$/ })).toBeInTheDocument();
    expect(screen.getAllByRole('article').map((card) => card.getAttribute('aria-label'))).toEqual(
      (state.summary?.functions ?? []).map((card) => `${card.function} function`),
    );
    expect(screen.getAllByRole('heading', { name: 'Call Center' })).toHaveLength(1);
    expect(screen.queryByTestId('exec-start-here')).not.toBeInTheDocument();
    expect(screen.queryByText(/Start with .+/)).not.toBeInTheDocument();
    expect(screen.getAllByText('People average').length).toBeGreaterThan(0);
    expect(screen.getAllByText(/% of the gap/).length).toBeGreaterThan(0);
    expect(screen.queryByText('Start here')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('function-trend-chart').length).toBeGreaterThan(0);
    expect(screen.queryByText('Healthy benchmark')).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'View RCM function' })).toHaveAttribute('href', '/function-summary/rcm');
    expect(screen.queryByRole('link', { name: 'Review RCM summary' })).not.toBeInTheDocument();
    const callCenter = screen.getByRole('article', { name: 'Call Center function' });
    expect(callCenter).toHaveTextContent('Inbound');
    expect(callCenter).toHaveTextContent('Outbound');
    expect(within(callCenter).getByText('Gap')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'What moved the score vs May' })).toBeInTheDocument();
    expect(screen.getAllByTestId('region-box')).toHaveLength(2);
    expect(screen.queryByRole('link', { name: 'Open Insights' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'View all drivers' })).not.toBeInTheDocument();
    expect(screen.queryByText('Function scorecards, regions, and KPI drivers are in Insights.')).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Teams at risk' })).toBeInTheDocument();
    expect(screen.getAllByTestId('risk-row')).toHaveLength(state.summary?.teams.filter((team) => team.score !== null && team.score < 90).length ?? 0);
    fireEvent.click(screen.getByRole('button', { name: 'Show all teams' }));
    expect(screen.getByRole('heading', { name: 'All teams' })).toBeInTheDocument();
    expect(screen.getAllByTestId('risk-row')).toHaveLength(state.summary?.teams.length ?? 0);
    expect(screen.getByRole('heading', { name: 'Grade distribution' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Corrective actions' })).toBeInTheDocument();
    expect(screen.getByTestId('corrective-action-insights')).toBeInTheDocument();
    expect(screen.queryByTestId('action-tile-due-this-week')).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open Corrective Actions' })).not.toBeInTheDocument();
  });

  it('keeps the full board for a role that cannot open Insights', () => {
    state.role = 'Branch Director';
    state.user = { id: 'director', role: 'Branch Director', accessible_branches: ['dubai'] };
    renderAt();
    expect(screen.getAllByRole('article').map((card) => card.getAttribute('aria-label'))).toEqual(
      (state.summary?.functions ?? []).map((card) => `${card.function} function`),
    );
    expect(screen.getByRole('link', { name: 'View RCM function' })).toHaveAttribute('href', '/function-summary/rcm');
    expect(screen.queryByRole('link', { name: 'Review RCM summary' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'What moved the score vs May' })).toBeInTheDocument();
    expect(screen.getAllByTestId('region-box')).toHaveLength(2);
    expect(screen.queryByRole('link', { name: 'Open Insights' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Teams at risk' })).toBeInTheDocument();
  });

  it('labels the driver metric neutrally until weighted_gap_points arrives', () => {
    state.role = 'Executive';
    renderAt();
    expect(screen.getByText(/change in the KPI's weighted contribution to the score vs May/)).toBeInTheDocument();
  });

  it('switches the driver footnote to weight × gap when the backend sends it', () => {
    state.role = 'Executive';
    state.summary = build({ drivers: fixtureDrivers({ weightedGap: true }) });
    renderAt();
    expect(screen.getByText('Red is KPI weight × gap to target (%). Green is the change in weighted contribution vs May (%).')).toBeInTheDocument();
  });

  it('renders direction-aware driver rows: a rising lower-is-better KPI is red, a falling one is green', () => {
    state.role = 'Executive';
    renderAt();
    const negatives = screen.getAllByTestId('driver-negative');
    const rejection = negatives.find((row) => row.textContent?.includes('Initial Rejection %'))!;
    expect(within(rejection).getByText('↓ better')).toBeInTheDocument();
    expect(within(rejection).getByText('↓ −1.6%')).toHaveAttribute('data-tone', 'bad');
    const denial = screen.getAllByTestId('driver-positive').find((row) => row.textContent?.includes('Denial Rate'))!;
    expect(within(denial).getByText('↑ +0.8%')).toHaveAttribute('data-tone', 'good');
    expect(negatives.every((row) => !/\b(?:pp|pts)\b/.test(row.textContent ?? ''))).toBe(true);
  });

  it('hides function links and the Insights link for Executive (no Function Summary / Insights access)', () => {
    state.role = 'Executive';
    renderAt();
    expect(screen.queryByRole('link', { name: /View .* function/ })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Review RCM summary' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open Insights' })).not.toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'View all drivers' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'What moved the score vs May' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Corrective actions' })).toBeInTheDocument();
  });

  it('hides corrective actions for Viewer and keeps the full board', () => {
    state.role = 'Viewer';
    renderAt();
    expect(screen.queryByRole('heading', { name: 'Corrective actions' })).not.toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'What moved the score vs May' })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'Open Insights' })).not.toBeInTheDocument();
  });

  it('softens drivers when the workspace is unavailable instead of inventing numbers', () => {
    state.role = 'Executive';
    state.summary = build({ drivers: null });
    renderAt();
    expect(screen.getByText("Driver analysis isn't available for this view yet.")).toBeInTheDocument();
    expect(screen.queryAllByTestId('driver-negative')).toHaveLength(0);
  });
});

describe('fallback and empty states', () => {
  it('shows the fallback notice when the requested month has no data', () => {
    state.summary = build({ requestedPeriodKey: '2026-07' });
    renderAt('/executive?period=2026-07');
    expect(screen.getByText('No performance data for July 2026 yet — showing June 2026, the latest month with data.')).toBeInTheDocument();
    expect(screen.getByTestId('executive-corporate')).toBeInTheDocument();
    expect(state.lastArgs?.filters.periodKey).toBe('2026-07');
  });

  it('shows the full empty state with Upload for Admin when the scope has no data at all', () => {
    state.summary = build({ records: [], comparisonRecords: [] });
    renderAt('/executive?period=2026-07');
    expect(screen.getByTestId('executive-empty')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'No performance data for July 2026' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Upload performance data' })).toHaveAttribute('href', '/settings');
    expect(screen.getByRole('button', { name: 'Pick another month' })).toBeInTheDocument();
  });

  it('tells non-admins to ask their admin instead of offering Upload', () => {
    state.role = 'Manager';
    state.summary = build({ view: 'managerial', role: 'Manager', team: 'Inbound', records: [], comparisonRecords: null });
    renderAt('/executive?period=2026-07');
    expect(screen.queryByRole('link', { name: 'Upload performance data' })).not.toBeInTheDocument();
    expect(screen.getByText('Ask your admin to upload July data.')).toBeInTheDocument();
  });

  it('lists the requested month as "(no data)" in the Date filter', () => {
    const options = periodOptionsFor(build(), '2026-07', TODAY);
    expect(options[0]).toEqual({ value: '2026-07', label: 'July 2026 (no data)' });
    expect(options[1]).toEqual({ value: '2026-06', label: 'June 2026' });
  });

  it('opens and closes the Executive Summary Quick Help guide popover in ExecutiveHero', () => {
    renderAt();
    const helpBtn = screen.getByRole('button', { name: 'Quick help and executive guide' });
    expect(helpBtn).toBeInTheDocument();
    expect(screen.queryByRole('dialog', { name: 'Quick help and executive guide' })).not.toBeInTheDocument();

    fireEvent.click(helpBtn);
    const dialog = screen.getByRole('dialog', { name: 'Quick help and executive guide' });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveTextContent('Executive Summary Guide');
    expect(dialog).toHaveTextContent('1. What is happening?');
    expect(dialog).toHaveTextContent('2. Why does it matter?');
    expect(dialog).toHaveTextContent('3. What action should you take?');

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog', { name: 'Quick help and executive guide' })).not.toBeInTheDocument();
  });
});

