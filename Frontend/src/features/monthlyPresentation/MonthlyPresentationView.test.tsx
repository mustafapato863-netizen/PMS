import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MonthlyPresentationView, { PresentMode } from './MonthlyPresentationView';

const mocks = vi.hoisted(() => ({ apiFetch: vi.fn(), user: { role: 'Admin', accessible_regions: [] as string[] } }));
vi.mock('../../lib/apiClient', () => ({ apiFetch: mocks.apiFetch }));
vi.mock('../../context/auth', () => ({ useAuth: () => ({ currentUser: mocks.user }) }));
vi.mock('../../context/RoleContext', () => ({ useUserRole: () => ({ role: mocks.user.role }) }));

const ws = (region: string) => ({
  summary: { analyzed_kpis: 2, expected_kpis: 2, coverage_percent: 100 },
  kpi_diagnosis: [{ key: 'k', label: `${region} KPI`, unit: null, direction: 'higher_better', weight: 0.5, actual: 100, target: 100, achievement_percent: 100, status: 'on_track', effect_points: 0, people_below_target: 0, six_months: [], most_below_team: null, other_cohorts: [], teams: [] }],
  team_summaries: [], performance_drivers: [], options: { teams: [] }, people_contribution_analysis: null,
  executive_story: { headline: `${region} headline`, current_score: region === 'EGY' ? 86.4 : 91.2, target_score: 90, gap_points: -3, score_change: 1, basis_context: { like_for_like: true } },
  comparison: { current: null, previous: null, is_adjacent: false, note: null },
});
let seen: string[] = [];
beforeEach(() => {
  seen = [];
  mocks.user = { role: 'Admin', accessible_regions: [] };
  mocks.apiFetch.mockImplementation(async (url: string) => {
    seen.push(url);
    if (url.startsWith('/api/insights/workspace')) return { success: true, data: ws(new URLSearchParams(url.split('?')[1]).get('region')!) };
    if (url.startsWith('/api/corrective-actions/follow-up')) return { success: true, data: { summary: {}, actions: [] } };
    return { success: true, data: [] };
  });
});

function Loc() { const l = useLocation(); return <div data-testid="loc">{l.search}</div>; }
const renderAt = (url: string) => render(
  <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <MemoryRouter initialEntries={[url]}><MonthlyPresentationView today={new Date(2026, 9, 21)} /><Loc /></MemoryRouter>
  </QueryClientProvider>,
);

describe('MonthlyPresentationView', () => {
  it('writes the last complete month and default region into the URL', async () => {
    renderAt('/monthly-presentation');
    await waitFor(() => expect(screen.getByTestId('loc').textContent).toBe('?region=egy&month=2026-09'));
  });

  it('shows the locked period in every slide header and only calls the API with that period/region', async () => {
    renderAt('/monthly-presentation?region=egy&month=2026-09');
    await screen.findByText(/Egypt at 86.4%/);
    expect(screen.getAllByTestId('period-lock')).toHaveLength(11);
    screen.getAllByTestId('period-lock').forEach((el) => expect(el.textContent).toBe('Period locked · September 2026'));
    seen.filter((u) => u.startsWith('/api/insights/workspace')).forEach((u) => {
      expect(u).toContain('region=EGY'); expect(u).toContain('month=September'); expect(u).toContain('year=2026');
    });
    expect(seen.some((u) => u.includes('region=UAE'))).toBe(false);
  });

  it('switching region reloads every request for the new region only', async () => {
    renderAt('/monthly-presentation?region=egy&month=2026-09');
    await screen.findByText(/Egypt at 86.4%/);
    seen = [];
    fireEvent.click(screen.getByRole('radio', { name: 'UAE' }));
    await screen.findByText(/UAE at 91.2%/);
    expect(screen.queryByText(/EGY headline/)).toBeNull();
    const ws = seen.filter((u) => u.startsWith('/api/insights/workspace'));
    expect(ws.length).toBeGreaterThan(0);
    ws.forEach((u) => expect(u).toContain('region=UAE'));
  });

  it('single-region users see a fixed pill and get an access message for the other region', async () => {
    mocks.user = { role: 'Regional Manager', accessible_regions: ['UAE'] };
    renderAt('/monthly-presentation?region=egy&month=2026-09');
    expect(await screen.findByText("You don't have access to Egypt")).toBeTruthy();
    expect(screen.queryByRole('radiogroup')).toBeNull();
    expect(screen.getByTestId('region-pill').textContent).toBe('UAE');
    expect(seen.some((u) => u.startsWith('/api/insights'))).toBe(false);
  });

  it('a month that is not yet available shows the empty state and fetches nothing', async () => {
    renderAt('/monthly-presentation?region=egy&month=2026-10');
    expect(await screen.findByText('October 2026 is not yet available')).toBeTruthy();
    expect(seen.length).toBe(0);
  });

  it('export dialog offers Mask names and the per-region file name', async () => {
    renderAt('/monthly-presentation?region=uae&month=2026-09');
    await screen.findByText(/UAE at 91.2%/);
    fireEvent.click(screen.getByRole('button', { name: /Export PDF/ }));
    const dialog = screen.getByRole('dialog', { name: 'Export PDF' });
    expect(within(dialog).getByLabelText(/Mask names/)).toBeTruthy();
    expect(within(dialog).getByText(/PMS_Monthly_UAE_2026-09.pdf/)).toBeTruthy();
  });

  it('Mark Final is disabled: no endpoint persists Final', async () => {
    renderAt('/monthly-presentation?region=egy&month=2026-09');
    await screen.findByText(/Egypt at 86.4%/);
    expect((screen.getByRole('button', { name: /Mark Final/ }) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe('PresentMode keyboard', () => {
  it('navigates with arrows, PageUp/PageDown, Home/End and exits on Esc', () => {
    const onExit = vi.fn();
    const slides = Array.from({ length: 11 }, (_, i) => <div key={i}>slide {i + 1}</div>);
    render(<PresentMode slides={slides} start={3} onExit={onExit} label="x" />);
    const stage = screen.getByRole('region', { name: /Presentation/ });
    expect(document.activeElement).toBe(stage);
    expect(screen.getByText('slide 3')).toBeTruthy();
    fireEvent.keyDown(stage, { key: 'ArrowRight' }); expect(screen.getByText('slide 4')).toBeTruthy();
    fireEvent.keyDown(stage, { key: 'PageUp' }); expect(screen.getByText('slide 3')).toBeTruthy();
    fireEvent.keyDown(stage, { key: 'End' }); expect(screen.getByText('slide 11')).toBeTruthy();
    fireEvent.keyDown(stage, { key: 'PageDown' }); expect(screen.getByText('slide 11')).toBeTruthy();
    fireEvent.keyDown(stage, { key: 'Home' }); expect(screen.getByText('slide 1')).toBeTruthy();
    fireEvent.keyDown(stage, { key: 'ArrowLeft' }); expect(screen.getByText('slide 1')).toBeTruthy();
    fireEvent.keyDown(stage, { key: 'Escape' }); expect(onExit).toHaveBeenCalled();
  });
});
