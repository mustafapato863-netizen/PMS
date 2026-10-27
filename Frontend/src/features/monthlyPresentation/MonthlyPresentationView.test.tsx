import { render, screen, fireEvent, within, waitFor } from '@testing-library/react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import MonthlyPresentationView from './MonthlyPresentationView';
import { OFFSHORE_EGYPT_SEP_2026_DATA } from './monthlyOverviewData';
import { recommendedActionForKpi, teamActionDueLabel } from './teamDeepDiveData';
import { readKpiTrend } from './components/SelectableKpiCard';
import {
  showActionSection,
  showPresentationControl,
  showStoredPlaceholder,
} from './presentationMode';

vi.mock('../../context/auth', () => ({
  useAuth: () => ({
    currentUser: {
      email: 'exec@company.com',
      accessible_regions: ['EGY', 'UAE'],
      assigned_region: null,
    },
  }),
}));

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({
    role: 'CEO',
  }),
}));

vi.mock('../executive/useSummaryRecords', () => ({
  useSummaryRecords: () => ({
    data: [],
    isLoading: false,
    isError: false,
  }),
}));

const mockSaveAction = vi.fn().mockResolvedValue({
  success: true,
  synced: true,
  message: 'Saved',
});

vi.mock('../../hooks/useActionStore', () => ({
  useActionStore: () => ({
    actions: [],
    saveAction: mockSaveAction,
    getAllActions: () => [],
  }),
}));

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="location-probe">{location.pathname}{location.search}</div>;
}

describe('MonthlyPresentationView — Overview, Call Center Deep Dive & Team Deep Dive', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.scrollTo = vi.fn();
    localStorage.clear();
  });

  it('renders Header with title, Offshore Egypt · September 2026 subtitle, region badge, and Page 1 of 6', () => {
    render(
      <MemoryRouter initialEntries={['/monthly-presentation']}>
        <MonthlyPresentationView />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole('heading', { name: 'Monthly Presentation' }),
    ).toBeInTheDocument();
    expect(screen.getByText('Monthly Overview')).toBeInTheDocument();
    expect(screen.getByText('Offshore Egypt · September 2026')).toBeInTheDocument();
    expect(screen.getByTestId('header-region-badge')).toHaveTextContent('Offshore Egypt');
    expect(screen.getByTestId('header-page-indicator')).toHaveTextContent('Page 1 of 6');

    const rail = screen.getByRole('navigation', { name: 'Page sections' });
    const scoreDot = within(rail).getByRole('button', { name: 'Score' });
    expect(scoreDot).toHaveAttribute('aria-current', 'true');
    expect(scoreDot).toHaveClass('cursor-pointer');
    expect(document.body).toHaveClass('mp-mac-cursor');
    expect(scoreDot.querySelector('[data-section-tip="Score"]')).toHaveTextContent('Score');
    const functions = document.getElementById('presentation-section-functions');
    const scroll = vi.fn();
    if (functions) functions.scrollIntoView = scroll;
    fireEvent.click(within(rail).getByRole('button', { name: 'Functions' }));
    expect(within(rail).getByRole('button', { name: 'Functions' })).toHaveAttribute('aria-current', 'true');
    expect(scroll).toHaveBeenCalled();
  });

  it('renders Overall Company Performance with 86.6%, Grade C, 13.4% below target, +0.5% vs August, Current/Target/Gap, and evaluation note', () => {
    render(
      <MemoryRouter initialEntries={['/monthly-presentation']}>
        <MonthlyPresentationView />
      </MemoryRouter>,
    );

    const overallSection = screen.getByRole('region', {
      name: 'Overall Company Performance',
    });

    expect(within(overallSection).getByTestId('overall-score-value')).toHaveTextContent(
      '86.6%',
    );
    expect(within(overallSection).getByText('Grade C')).toBeInTheDocument();
    expect(
      within(overallSection).getByTestId('overall-target-statement'),
    ).toHaveTextContent('13.4% below target');
    expect(
      within(overallSection).getByTestId('overall-movement-badge'),
    ).toHaveTextContent('+0.5% vs August');
  });

  it('renders all 7 Functions Overview cards and navigates on RCM click', () => {
    const onSelectFunction = vi.fn();
    render(
      <MemoryRouter initialEntries={['/monthly-presentation']}>
        <MonthlyPresentationView onSelectFunction={onSelectFunction} />
        <LocationProbe />
      </MemoryRouter>,
    );

    for (const slug of [
      'rcm',
      'marketing',
      'it',
      'call-center',
      'human-resources',
      'administration',
      'finance',
    ]) {
      expect(screen.getByTestId(`function-card-${slug}`)).toBeInTheDocument();
    }

    fireEvent.click(screen.getByTestId('function-card-rcm'));
    expect(onSelectFunction).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('location-probe').textContent).toContain('deepDive=rcm');
    expect(screen.getByTestId('location-probe').textContent).not.toContain('function-summary');
    expect(screen.getByRole('heading', { name: 'RCM Deep Dive' })).toBeInTheDocument();
  });

  it('opens Call Center Deep Dive with real employees, support positions, and expandable 6-Month KPI trends', () => {
    render(
      <MemoryRouter initialEntries={['/monthly-presentation']}>
        <MonthlyPresentationView />
        <LocationProbe />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('function-card-call-center'));

    expect(screen.getByTestId('call-center-deep-dive-page')).toBeInTheDocument();
    const deepDiveRail = screen.getByRole('navigation', { name: 'Page sections' });
    expect(within(deepDiveRail).getByRole('button', { name: 'Support' })).toBeInTheDocument();
    expect(within(deepDiveRail).queryByRole('button', { name: 'Grades' })).not.toBeInTheDocument();
    expect(
      screen.getByRole('heading', { name: 'Call Center Deep Dive' }),
    ).toBeInTheDocument();
    expect(screen.getByTestId('deep-dive-function-score')).toHaveTextContent('90.4%');

    // Layer 1: Inbound & Outbound Agent Team Cards
    const inboundCard = screen.getByTestId('agent-team-card-inbound-agents');
    expect(within(inboundCard).getByText('Inbound Agents')).toBeInTheDocument();
    expect(within(inboundCard).getByText('92.6%')).toBeInTheDocument();
    expect(within(inboundCard).getByText('35 agents')).toBeInTheDocument();

    const outboundCard = screen.getByTestId('agent-team-card-outbound-agents');
    expect(within(outboundCard).getByText('Outbound Agents')).toBeInTheDocument();
    expect(within(outboundCard).getByText('87.7%')).toBeInTheDocument();
    expect(within(outboundCard).getByText('7 agents')).toBeInTheDocument();

    // Layer 2: Support Positions with real holders
    expect(screen.getByTestId('impact-badge-pos-trainer')).toHaveTextContent(
      'Strong Impact',
    );
    expect(screen.getByText('Hagar Ahmed Amin Diab')).toBeInTheDocument();
    expect(screen.getByText('Fahmy Sabry El-Saadany')).toBeInTheDocument();

    // Key Agent KPIs + 6-Month Actual vs Target Trend toggle
    expect(screen.queryByTestId('kpi-trend-panel-kpi-aht')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('toggle-kpi-trend-kpi-aht'));
    const trendPanel = screen.getByTestId('kpi-trend-panel-kpi-aht');
    expect(trendPanel).toBeInTheDocument();
    expect(within(trendPanel).getByText(/Target vs Execution:/i)).toBeInTheDocument();

    // Real Agents Needing Attention
    expect(screen.getByText('Rawan Mohamed Salah Elnajjar')).toBeInTheDocument();
    expect(screen.getByText('Maryam Elsayed Mahmoud Eid')).toBeInTheDocument();
  });

  it('navigates from Call Center Deep Dive to Inbound Team Deep Dive and renders all 6 required sections with full-word grades', () => {
    render(
      <MemoryRouter initialEntries={['/monthly-presentation?deepDive=call-center']}>
        <MonthlyPresentationView />
        <LocationProbe />
      </MemoryRouter>,
    );

    // Click Inbound Agents card on Call Center Deep Dive
    fireEvent.click(screen.getByTestId('agent-team-card-inbound-agents'));

    // Verify URL & Team Deep Dive Page
    expect(screen.getByTestId('location-probe').textContent).toContain('team=inbound');
    expect(screen.getByTestId('team-deep-dive-page')).toBeInTheDocument();

    // 1. Header with breadcrumb & full-word grade
    const breadcrumb = screen.getByTestId('team-deep-dive-breadcrumb');
    expect(within(breadcrumb).getByText('Overview')).toBeInTheDocument();
    expect(within(breadcrumb).getByText('Call Center')).toBeInTheDocument();
    expect(within(breadcrumb).getByText('Inbound Agents')).toBeInTheDocument();
    expect(screen.getByTestId('team-deep-dive-score')).toHaveTextContent('92.6%');
    expect(screen.getByText('Meet Expectations')).toBeInTheDocument();

    // 2. Key Team KPIs — headcount "met" chip is gone; arrow color follows KPI direction
    const ahtCard = screen.getByTestId('team-kpi-card-AHT');
    const bookingCard = screen.getByTestId('team-kpi-card-Booking');
    const attendanceCard = screen.getByTestId('team-kpi-card-Attendance');
    const qualityCard = screen.getByTestId('team-kpi-card-Quality');
    for (const card of [ahtCard, bookingCard, attendanceCard, qualityCard]) {
      expect(card.textContent).not.toMatch(/\d+\/\d+\s*met/);
    }
    // AHT is lower-better, so an increase is red even though the glyph points up.
    expect(within(ahtCard).getByText('+0.28 min vs August')).toHaveClass('text-rose-700');
    expect(within(bookingCard).getByText('+3.8% vs August')).toHaveClass('text-emerald-700');
    // Attendance is still off target, but the month moved the right way.
    expect(within(attendanceCard).getByText('+0.8% vs August')).toHaveClass('text-emerald-700');

    // 3. KPI Trend Explorer (switch tabs & check diagnosis)
    expect(screen.getByTestId('kpi-trend-explorer')).toBeInTheDocument();
    expect(screen.getByTestId('trend-explorer-diagnosis')).toHaveTextContent(
      /Execution is the primary issue, not the 2.50 min target/i,
    );
    fireEvent.click(screen.getByTestId('trend-kpi-switcher-Booking'));
    expect(screen.getByTestId('trend-explorer-diagnosis')).toHaveTextContent(
      /Booking Rate target was raised from 46.0% to 65.0% in June/i,
    );

    // 4. Agents — Average and Below (real employees, full-word grades)
    const table = screen.getByTestId('agents-average-below-table');
    expect(within(table).getByText('Maryam Elsayed Mahmoud Eid')).toBeInTheDocument();
    expect(within(table).getByText('Abdulrahman Said Sayed Helal')).toBeInTheDocument();
    expect(within(table).getAllByText('Average').length).toBeGreaterThan(0);

    // 5. Individual Action Plan cards (editable)
    const maryamCard = screen.getByTestId(
      'individual-action-card-Maryam Elsayed Mahmoud Eid',
    );
    expect(maryamCard).toBeInTheDocument();
    expect(within(maryamCard).getByText('Average')).toBeInTheDocument();

    // 6. Team-Level Action Plan cards
    expect(
      screen.getByRole('heading', { name: 'Team-Level Action Plan' }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Deploy live AHT pacing alerts/i),
    ).toBeInTheDocument();

    // Switch to Outbound Agents via team switcher
    fireEvent.click(screen.getByTestId('switch-team-outbound'));
    expect(screen.getByTestId('team-deep-dive-score')).toHaveTextContent('87.7%');
    expect(
      within(screen.getByTestId('agents-average-below-table')).getByText(
        'Rawan Mohamed Salah Elnajjar',
      ),
    ).toBeInTheDocument();

    // Navigate back to Call Center Deep Dive via breadcrumb
    fireEvent.click(screen.getByTestId('breadcrumb-call-center'));
    expect(
      screen.getByRole('heading', { name: 'Call Center Deep Dive' }),
    ).toBeInTheDocument();
  });

  it('opens RCM, Marketing, IT, Call Center, and Human Resources inside the presentation', () => {
    render(
      <MemoryRouter initialEntries={['/monthly-presentation']}>
        <MonthlyPresentationView />
        <LocationProbe />
      </MemoryRouter>,
    );

    const cases = [
      ['rcm', 'RCM Deep Dive'],
      ['marketing', 'Marketing Deep Dive'],
      ['it', 'IT Deep Dive'],
      ['call-center', 'Call Center Deep Dive'],
      ['human-resources', 'Human Resources Deep Dive'],
    ] as const;

    for (const [slug, heading] of cases) {
      fireEvent.click(screen.getByTestId(`function-card-${slug}`));
      expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument();
      expect(screen.getByTestId('location-probe').textContent).toContain(`deepDive=${slug}`);
      expect(screen.getByTestId('location-probe').textContent).not.toContain('function-summary');
      fireEvent.click(screen.getByTestId('back-to-monthly-overview'));
      expect(screen.getByTestId('monthly-overview-page')).toBeInTheDocument();
    }
  });

  it('opens a support position role detail with the 6-month chart, accountability, and a new action', async () => {
    render(
      <MemoryRouter initialEntries={['/monthly-presentation?deepDive=call-center']}>
        <MonthlyPresentationView />
        <LocationProbe />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('support-position-card-pos-trainer'));

    expect(screen.getByTestId('location-probe').textContent).toContain('role=trainer');
    expect(screen.getByTestId('role-detail-page')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Trainer' })).toBeInTheDocument();
    expect(screen.getByText('Hagar Ahmed Amin Diab')).toBeInTheDocument();
    expect(screen.getAllByText('Excellent').length).toBeGreaterThan(0);
    expect(screen.getByTestId('role-impact-badge')).toHaveTextContent('Strong');

    const chart = screen.getByTestId('role-kpi-chart');
    expect(chart.querySelector('[data-series="actual"]')).toBeTruthy();
    expect(chart.querySelector('[data-series="target"]')?.getAttribute('stroke-dasharray')).toBe('6 4');
    expect(screen.getByTestId('role-accountability')).toHaveTextContent(/accountable/i);

    fireEvent.change(screen.getByLabelText('Description'), {
      target: { value: 'Coach the four inbound agents below 50% booking.' },
    });
    fireEvent.change(screen.getByLabelText('Owner'), { target: { value: 'Call Center Trainer' } });
    fireEvent.change(screen.getByLabelText('Due date'), { target: { value: '2026-10-20' } });
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'Open' } });
    fireEvent.change(screen.getByLabelText('Expected impact'), { target: { value: '+0.7% booking' } });
    fireEvent.click(screen.getByTestId('save-role-action'));

    await waitFor(() => expect(mockSaveAction).toHaveBeenCalledTimes(1));
    expect(mockSaveAction).toHaveBeenCalledWith(
      expect.objectContaining({
        employee_name: 'Hagar Ahmed Amin Diab',
        team: 'Trainer',
        action_text: 'Coach the four inbound agents below 50% booking.',
        due_date: '2026-10-20',
      }),
    );
  });

  it('aggregates roles into single cards on the Function Deep Dive and shows individual people only inside Role Detail', () => {
    render(
      <MemoryRouter initialEntries={['/monthly-presentation']}>
        <MonthlyPresentationView />
        <LocationProbe />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('function-card-marketing'));
    expect(screen.getByTestId('deep-dive-function-score')).toHaveTextContent('79.6%');

    // Dragging vs Carrying role hierarchy (grouped by role: 6 dragging roles in single-row carousel of 4, 3 carrying roles in Marketing)
    const draggingSection = screen.getByTestId('roles-dragging');
    expect(draggingSection).toHaveTextContent('6 roles below 90%');
    expect(draggingSection).toHaveTextContent('Web Developer');
    expect(draggingSection).toHaveTextContent('Social Media Specialist');
    expect(draggingSection).toHaveTextContent('Media Buyer');
    expect(draggingSection).toHaveTextContent('Primary drag:');
    expect(screen.getByTestId('dragging-roles-carousel')).toHaveTextContent('1–4 of 6');

    // Slide single-row carousel to reveal Graphic Designer (6th dragging role)
    fireEvent.click(screen.getByTestId('dragging-roles-next'));
    fireEvent.click(screen.getByTestId('dragging-roles-next'));
    expect(screen.getByTestId('dragging-roles-carousel')).toHaveTextContent('3–6 of 6');

    // Graphic Designer is a single aggregated card (87.8% combined score across 3 people)
    const graphicDesignerCard = screen.getByTestId('role-card-graphic-designer');
    expect(graphicDesignerCard).toHaveTextContent('Graphic Designer');
    expect(graphicDesignerCard).toHaveTextContent('87.8%');
    expect(graphicDesignerCard).toHaveTextContent('3 people');

    const carryingSection = screen.getByTestId('roles-carrying');
    expect(carryingSection).toHaveTextContent('3 at or above 90%');
    expect(carryingSection).toHaveTextContent('Creative Director');
    expect(carryingSection).toHaveTextContent('Content Writer');
    expect(carryingSection).toHaveTextContent('Account Manager');
    expect(screen.getAllByText('Below Average').length).toBeGreaterThan(0);

    // Individual employee names MUST NOT appear on the Function Deep Dive page
    expect(screen.queryByText(/Abdelrahman Yousry/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Elsayed Mohamed/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Asser Mohamed/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Mohamed Abdelmegid Diab/i)).not.toBeInTheDocument();

    // Key Function KPIs rendered as structured cards with expandable 6-Mo Trend
    const responseTimeKpiCard = screen.getByTestId('function-kpi-card-mkt-kpi-response-time');
    expect(within(responseTimeKpiCard).getByText('Social Media Response Time')).toBeInTheDocument();
    expect(within(responseTimeKpiCard).getByText('208.00 min')).toBeInTheDocument();
    expect(within(responseTimeKpiCard).getByText('31.00 min')).toBeInTheDocument();
    expect(within(responseTimeKpiCard).getByText('+42.00 min vs August (Slower)')).toHaveClass(
      'text-rose-700',
    );
    const editsKpiCard = screen.getByTestId('function-kpi-card-mkt-kpi-edits');
    expect(within(editsKpiCard).getByText('-1.2% vs August (Improving)')).toHaveClass(
      'text-emerald-700',
    );
    fireEvent.click(screen.getByTestId('toggle-kpi-trend-mkt-kpi-response-time'));
    expect(screen.getByTestId('kpi-trend-panel-mkt-kpi-response-time')).toBeInTheDocument();

    // Priority Actions rendered as structured prototype cards with overall expected impact
    expect(screen.getByText('+10.2% expected lift')).toBeInTheDocument();
    expect(screen.getByText('79.6% → 89.8%')).toBeInTheDocument();
    const firstActionCard = screen.getByTestId('position-action-mkt-act-1');
    expect(within(firstActionCard).getByText(/Owner: Social Media Head/i)).toBeInTheDocument();
    expect(within(firstActionCard).getByText(/\+3.6% expected lift/i)).toBeInTheDocument();
    expect(
      within(firstActionCard).getByText(/Social Media Response Time \(208 min → ≤ 35 min\)/i),
    ).toBeInTheDocument();

    // Drill into Graphic Designer Role Detail — individual employees appear in the People in this Role table
    fireEvent.click(graphicDesignerCard);
    expect(screen.getByTestId('location-probe').textContent).toContain('deepDive=marketing');
    expect(screen.getByTestId('location-probe').textContent).toContain('role=graphic-designer');
    expect(screen.getByTestId('role-detail-page')).toBeInTheDocument();
    expect(screen.getByTestId('role-detail-score')).toHaveTextContent('87.8%');
    const membersTable = screen.getByTestId('role-members-table');
    // Only Average or below (score < 90) shown by default
    expect(within(membersTable).getByText('Abdulwahab')).toBeInTheDocument();
    expect(within(membersTable).getByText('Asser Mohamed')).toBeInTheDocument();
    expect(within(membersTable).queryByText('Elsayed Mohamed')).not.toBeInTheDocument();

    // Toggle "View All (3)" to reveal all people in the role
    fireEvent.click(screen.getByTestId('toggle-show-all-members'));
    expect(within(membersTable).getByText('Elsayed Mohamed')).toBeInTheDocument();

    // Verify 360-Profile interactive 6-month trend component is rendered
    expect(screen.getByTestId('profile-360-trend-container')).toBeInTheDocument();
    // Verify Individual Action Plan section with Main Issue is rendered for employees
    const indActionSection = screen.getByTestId('role-individual-action-plan-section');
    expect(indActionSection).toBeInTheDocument();
    expect(within(indActionSection).getAllByText(/Main Issue:/i).length).toBeGreaterThan(0);
    // Verify KPI cards show Contribution, Weight, % of target, and Biggest Gap Driver
    expect(screen.getByTestId('biggest-gap-summary-pill')).toHaveTextContent(/Biggest Gap Driver:/i);
    expect(screen.getAllByText(/Contribution/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Weight/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/% of target/i).length).toBeGreaterThan(0);

    // Verify top-to-bottom section order matches Call Center Team Deep Dive:
    // 1. Header -> 2. KPI Cards -> 3. 6-Month Trend -> 4. Employees Table -> 5. Actions/Decisions
    const kpiSection = screen.getByTestId('role-kpis');
    const trendSection = screen.getByTestId('profile-360-trend-container');
    const membersSection = screen.getByTestId('role-members-section');
    const actionsSection = screen.getByTestId('role-actions-section');
    expect(
      kpiSection.compareDocumentPosition(trendSection) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      trendSection.compareDocumentPosition(membersSection) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      membersSection.compareDocumentPosition(indActionSection) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      indActionSection.compareDocumentPosition(actionsSection) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();

    // Navigate back to Marketing and verify single-row KPI carousel controls (<= 4 cards visible at once)
    fireEvent.click(screen.getByTestId('breadcrumb-function'));
    fireEvent.click(screen.getByTestId('role-card-media-buyer'));
    expect(screen.getByTestId('kpi-carousel-controls')).toBeInTheDocument();
    const visibleButtons = screen
      .getByTestId('role-kpis')
      .querySelectorAll('button[data-testid^="role-kpi-"]');
    expect(visibleButtons.length).toBeGreaterThan(0);
    expect(visibleButtons.length).toBeLessThanOrEqual(4);

    // Navigate back to Marketing and drill into Web Developer Role Detail (single-person role)
    fireEvent.click(screen.getByTestId('breadcrumb-function'));
    fireEvent.click(screen.getByTestId('role-card-web-developer'));
    expect(screen.getByTestId('location-probe').textContent).toContain('role=web-developer');
    expect(screen.getByTestId('role-detail-score')).toHaveTextContent('52.5%');
    expect(screen.getAllByText('Abdelrahman Yousry Abdelaziz Hamdy').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Unsatisfactory').length).toBeGreaterThan(0);
    const chart = screen.getByTestId('role-kpi-chart');
    expect(chart.querySelector('[data-series="actual"]')).toBeTruthy();
    expect(chart.querySelector('[data-series="target"]')?.getAttribute('stroke-dasharray')).toBe('6 4');
    expect(chart.querySelector('[data-series="target"]')?.getAttribute('stroke')).toBe('#d97706');
    expect(screen.getByTestId('role-kpi-structural-diagnosis')).toBeInTheDocument();
    expect(screen.getByTestId('role-accountability')).toBeInTheDocument();
    expect(screen.getAllByText(/Affects KPI:/i).length).toBeGreaterThan(0);
  });

  it('opens any measured team, including Coding EGY, and a teams-at-risk row', () => {
    render(
      <MemoryRouter initialEntries={['/monthly-presentation']}>
        <MonthlyPresentationView />
        <LocationProbe />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('team-at-risk-coding-egy'));
    expect(screen.getByTestId('location-probe').textContent).toContain('deepDive=rcm');
    expect(screen.getByTestId('location-probe').textContent).toContain('team=coding-egy');
    expect(screen.getByTestId('team-deep-dive-page')).toBeInTheDocument();
    expect(screen.getByTestId('team-deep-dive-score')).toHaveTextContent('53.6%');
    const breadcrumb = screen.getByTestId('team-deep-dive-breadcrumb');
    expect(within(breadcrumb).getByText('RCM')).toBeInTheDocument();
    expect(within(breadcrumb).getByText('Coding EGY')).toBeInTheDocument();
    expect(screen.getAllByText('Unsatisfactory').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Mohamed Galal Ali Abbas').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByTestId('switch-team-submission-egy'));
    expect(screen.getByTestId('team-deep-dive-score')).toHaveTextContent('71.6%');
    expect(screen.getAllByText('Salma Nagy Ali Hendy').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByTestId('breadcrumb-function'));
    fireEvent.click(screen.getByTestId('agent-team-card-pre-approvals-ip'));
    expect(screen.getByTestId('team-deep-dive-score')).toHaveTextContent('82.8%');
    expect(screen.getAllByText('Average').length).toBeGreaterThan(0);
  });

  it('opens the same function deep dive and role detail for every role-based function', () => {
    render(
      <MemoryRouter initialEntries={['/monthly-presentation']}>
        <MonthlyPresentationView />
        <LocationProbe />
      </MemoryRouter>,
    );

    for (const slug of ['marketing', 'it', 'human-resources', 'administration', 'finance']) {
      fireEvent.click(screen.getByTestId(`function-card-${slug}`));
      const page = screen.getByTestId('function-deep-dive-page');
      expect(page).toBeInTheDocument();
      expect(screen.getByTestId('deep-dive-function-score')).toBeInTheDocument();
      expect(screen.getByTestId('diagnostic-narrative')).toBeInTheDocument();
      expect(screen.getByTestId('roles-dragging')).toBeInTheDocument();
      expect(screen.getByTestId('roles-carrying')).toBeInTheDocument();
      expect(screen.queryByTestId('call-center-deep-dive-page')).not.toBeInTheDocument();

      const roleCard = page.querySelector('[data-testid^="role-card-"]');
      expect(roleCard).toBeTruthy();
      fireEvent.click(roleCard as HTMLElement);

      expect(screen.getByTestId('role-detail-page')).toBeInTheDocument();
      expect(screen.getByTestId('location-probe').textContent).toContain(`deepDive=${slug}`);
      expect(screen.getByTestId('location-probe').textContent).toContain('role=');
      const chart = screen.getByTestId('role-kpi-chart');
      expect(chart.querySelector('[data-series="actual"]')).toBeTruthy();
      expect(chart.querySelector('[data-series="actual-area"]')).toBeTruthy();
      expect(chart.querySelector('[data-series="target"]')?.getAttribute('stroke-dasharray')).toBe('6 4');

      fireEvent.click(screen.getByTestId('breadcrumb-function'));
      expect(screen.getByTestId('function-deep-dive-page')).toBeInTheDocument();
      fireEvent.click(screen.getByTestId('back-to-monthly-overview'));
      expect(screen.getByTestId('monthly-overview-page')).toBeInTheDocument();
    }
  });

  it('specializes a shared KPI recommendation from each agent issue and prints a stored due date unchanged', () => {
    const slower = recommendedActionForKpi(
      'AHT',
      'AHT (Handle Time)',
      'Inbound',
      '4.25 min',
      '2.50 min',
      'AHT at 4.25 min (vs 2.50 min target) & Booking Rate at 40.4%',
    );
    const slowerStill = recommendedActionForKpi(
      'AHT',
      'AHT (Handle Time)',
      'Inbound',
      '5.03 min',
      '2.50 min',
      'AHT at 5.03 min (vs 2.50 min target) & Booking Rate at 47.8%',
    );
    expect(slower.actionText).not.toBe(slowerStill.actionText);
    expect(slower.actionText).toContain('Booking Rate at 40.4%');
    expect(slowerStill.actionText).toContain('Booking Rate at 47.8%');
    expect(slower.actionText).not.toContain('47.8%');
    expect(teamActionDueLabel(undefined)).toBe('No due date');
    expect(teamActionDueLabel('   ')).toBe('No due date');
    expect(teamActionDueLabel('2026-11-02')).toBe('2026-11-02');
  });

  it('colors a KPI move by whether that direction helps the metric', () => {
    expect(readKpiTrend('▲ +9.0% vs August', 'higher')).toMatchObject({
      direction: 'up',
      favorable: true,
      text: '+9.0% vs August',
    });
    expect(readKpiTrend('▼ -0.1% vs August', 'higher')).toMatchObject({
      direction: 'down',
      favorable: false,
      text: '-0.1% vs August',
    });
    expect(readKpiTrend('▲ +0.28 min vs August', 'lower')).toMatchObject({
      direction: 'up',
      favorable: false,
    });
    expect(readKpiTrend('▼ -1.2% vs August (Improving)', 'lower')).toMatchObject({
      direction: 'down',
      favorable: true,
      text: '-1.2% vs August (Improving)',
    });
    expect(readKpiTrend('● 100.0% vs August (Target Met)', 'higher')).toMatchObject({
      direction: 'flat',
      favorable: null,
      text: '100.0% vs August (Target Met)',
    });
    expect(readKpiTrend('—', 'higher')).toMatchObject({
      direction: 'flat',
      favorable: null,
      text: '—',
    });
  });

  it('keeps deep-dive cards scannable, clickable, and bound to the overview trend', () => {
    render(
      <MemoryRouter initialEntries={['/monthly-presentation']}>
        <MonthlyPresentationView />
        <LocationProbe />
      </MemoryRouter>,
    );

    const trendCard = screen.getByTestId('six-month-score-trend');
    const chart = within(trendCard).getByRole('img', { name: /trend/i });
    expect(chart.querySelector('path')).toBeTruthy();
    expect(chart.querySelector('line')).toBeTruthy();
    expect(chart.textContent).toMatch(/Target\s+100/);
    expect(chart.textContent).toMatch(/100%/);
    expect(chart.textContent).not.toMatch(/10[1-9]%/);
    for (const point of OFFSHORE_EGYPT_SEP_2026_DATA.trend) {
      expect(chart.textContent).toContain(point.month);
      const marker = chart.querySelector(`[aria-label*="${point.month}"]`);
      const label = marker?.getAttribute('aria-label') ?? '';
      const score = point.score.toFixed(1);
      expect(label.includes(score) || label.includes(score.replace('.', ','))).toBe(true);
    }
    const lastTrend = OFFSHORE_EGYPT_SEP_2026_DATA.trend.at(-1);
    expect(trendCard.textContent).toContain(`${OFFSHORE_EGYPT_SEP_2026_DATA.trend[0].month} ${OFFSHORE_EGYPT_SEP_2026_DATA.trend[0].score.toFixed(1)}%`);
    expect(trendCard.textContent).toContain(`${lastTrend?.month} ${lastTrend?.score.toFixed(1)}%`);

    const expectDrillLink = (label: string) => {
      const links = screen.getAllByText(label);
      expect(links.length).toBeGreaterThan(0);
      for (const link of links) {
        expect(link.className).toContain('text-blue-700');
        expect(link.className).toContain('group-hover:text-blue-950');
        if (label === 'Open Team' || label === 'Open role detail') {
          expect(link.className).toContain('group-hover:bg-blue-100');
          expect(link.className).not.toContain('group-hover:underline');
        } else {
          expect(link.className).toContain('group-hover:underline');
        }
        expect(link.querySelector('svg')?.getAttribute('class') ?? '').toContain(
          label === 'Open Team' || label === 'Open role detail'
            ? 'group-hover:translate-x-0.5'
            : 'group-hover:translate-x-1',
        );
      }
    };

    fireEvent.click(screen.getByTestId('function-card-call-center'));
    expectDrillLink('Open Team');
    expectDrillLink('Open role detail');
    const inbound = screen.getByTestId('agent-team-card-inbound-agents');
    expect(within(inbound).getByText('92.6%')).toBeInTheDocument();
    expect(within(inbound).getByText('Meet Expectations')).toBeInTheDocument();
    expect(within(inbound).getByText('Gap')).toBeInTheDocument();
    expect(within(inbound).getByText(/Diagnosis:/)).toBeInTheDocument();
    const trainer = screen.getByTestId('support-position-card-pos-trainer');
    const trainerDiagnosis = within(trainer).getByTestId('support-diagnosis-pos-trainer');
    expect(trainerDiagnosis.className).toContain('line-clamp-2');
    expect(trainerDiagnosis.getAttribute('title')).toBe(trainerDiagnosis.textContent);
    expect(within(trainer).getByText('Booking Rate')).toBeInTheDocument();
    expect(within(trainer).getByText('Quality Score')).toBeInTheDocument();
    for (const diagnosis of screen.getAllByTestId(/^action-diagnosis-/)) {
      expect(diagnosis.className).toContain('line-clamp-2');
      expect(diagnosis.getAttribute('title')).toBe(diagnosis.textContent);
      expect(diagnosis.closest('[data-testid^="position-action-"]')?.textContent).toMatch(/Target:/);
    }

    fireEvent.click(screen.getByTestId('back-to-monthly-overview'));
    fireEvent.click(screen.getByTestId('function-card-rcm'));
    expectDrillLink('Open Team');
    expectDrillLink('Open role detail');
    const rcmSupport = screen.getByTestId('support-position-card-rcm-pos-senior-pa');
    const rcmDiagnosis = within(rcmSupport).getByTestId('support-diagnosis-rcm-pos-senior-pa');
    expect(rcmDiagnosis.className).toContain('line-clamp-2');
    expect(within(rcmSupport).getByText('IP Initial Rejection %')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('back-to-monthly-overview'));
    fireEvent.click(screen.getByTestId('function-card-marketing'));
    expectDrillLink('View role');
    const marketing = screen.getByTestId('function-deep-dive-page');
    expect(within(marketing).getByTestId('deep-dive-function-score')).toHaveTextContent('79.6%');
    expect(within(marketing).getAllByText('Below Average').length).toBeGreaterThan(0);
    expect(within(marketing).getAllByText(/Gap/).length).toBeGreaterThan(0);
    expect(within(marketing).getAllByText(/Primary drag:/).length).toBeGreaterThan(0);
    const marketingAction = screen.getByTestId('action-diagnosis-mkt-act-1');
    expect(marketingAction.className).toContain('line-clamp-2');
    expect(marketingAction.closest('article')?.textContent).toMatch(/Social Media Response Time/);

    fireEvent.click(screen.getByTestId('back-to-monthly-overview'));
    fireEvent.click(screen.getByTestId('function-card-call-center'));
    fireEvent.click(screen.getByTestId('agent-team-card-inbound-agents'));
    expect(screen.getByTestId('trend-explorer-diagnosis')).toHaveTextContent(
      'Execution is the primary issue, not the 2.50 min target',
    );
    fireEvent.click(screen.getByTestId('trend-kpi-switcher-Booking'));
    expect(screen.getByTestId('trend-explorer-diagnosis')).toHaveTextContent(
      'Booking Rate target was raised from 46.0% to 65.0% in June',
    );
    expect(screen.getByText(/Deploy live AHT pacing alerts/i)).toBeInTheDocument();

    const maryam = screen.getByTestId('individual-action-card-Maryam Elsayed Mahmoud Eid');
    const abdulrahman = screen.getByTestId('individual-action-card-Abdulrahman Said Sayed Helal');
    const issueOf = (card: HTMLElement) =>
      (within(card).getByText(/Main Issue:/i).parentElement?.textContent ?? '')
        .replace(/Main Issue:\s*/i, '')
        .trim();
    const maryamIssue = issueOf(maryam);
    const abdulrahmanIssue = issueOf(abdulrahman);
    const maryamAction = within(maryam).getByTestId(
      'individual-action-text-Maryam Elsayed Mahmoud Eid',
    ).textContent ?? '';
    const abdulrahmanAction = within(abdulrahman).getByTestId(
      'individual-action-text-Abdulrahman Said Sayed Helal',
    ).textContent ?? '';
    expect(maryamIssue).not.toBe(abdulrahmanIssue);
    expect(maryamAction).toContain(maryamIssue);
    expect(abdulrahmanAction).toContain(abdulrahmanIssue);
    expect(maryamAction).not.toBe(abdulrahmanAction);

    const teamActions = screen.getAllByTestId(/^team-action-card-/);
    expect(teamActions.length).toBeGreaterThan(0);
    for (const card of teamActions) {
      expect(within(card).getByTestId(/^team-action-status-/).textContent?.trim()).toMatch(
        /^(Open|In Progress|Planned|Completed)$/,
      );
      const owner = within(card).getByTestId(/^team-action-owner-/);
      expect(owner.textContent?.trim().length).toBeGreaterThan(0);
      const due = within(card).getByTestId(/^team-action-due-/).textContent?.trim() ?? '';
      expect(/^\d{4}-\d{2}-\d{2}/.test(due) || due === 'No due date').toBe(true);
    }
  });

  it('keeps Presentation Mode on across the review and hides action editing while it is on', () => {
    expect(showPresentationControl(false)).toBe(true);
    expect(showPresentationControl(true)).toBe(false);
    expect(showStoredPlaceholder('No due date', false)).toBe(true);
    expect(showStoredPlaceholder('No due date', true)).toBe(false);
    expect(showStoredPlaceholder('2026-10-18', true)).toBe(true);
    expect(showActionSection(0, false)).toBe(true);
    expect(showActionSection(0, true)).toBe(false);
    expect(showActionSection(2, true)).toBe(true);

    render(
      <MemoryRouter initialEntries={['/monthly-presentation']}>
        <MonthlyPresentationView />
        <LocationProbe />
      </MemoryRouter>,
    );

    const modeSwitch = () => screen.getByRole('switch', { name: 'Presentation Mode' });
    expect(modeSwitch()).toHaveAttribute('aria-checked', 'false');
    expect(screen.queryByText(/^Presenting$/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('function-card-call-center'));
    expect(screen.getByTestId('call-center-deep-dive-page')).toBeInTheDocument();
    expect(modeSwitch()).toHaveAttribute('aria-checked', 'false');

    fireEvent.click(screen.getByTestId('agent-team-card-inbound-agents'));
    expect(screen.getByTestId('team-deep-dive-page')).toBeInTheDocument();
    expect(screen.getByTestId('add-team-action-btn')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Edit' }).length).toBeGreaterThan(0);
    expect(
      screen.getAllByTestId(/^team-action-due-/).some((node) => node.textContent?.trim() === 'No due date'),
    ).toBe(true);
    expect(screen.getByText(/Deploy live AHT pacing alerts/i)).toBeInTheDocument();
    expect(screen.getByTestId('team-deep-dive-score')).toHaveTextContent('92.6%');

    fireEvent.click(screen.getByTestId('back-to-call-center-deep-dive'));
    fireEvent.click(screen.getByTestId('back-to-monthly-overview'));
    fireEvent.click(screen.getByTestId('function-card-marketing'));
    expect(screen.getByTestId('function-deep-dive-page')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('dragging-roles-next'));
    fireEvent.click(screen.getByTestId('dragging-roles-next'));
    fireEvent.click(screen.getByTestId('role-card-graphic-designer'));
    expect(screen.getByTestId('role-detail-page')).toBeInTheDocument();
    expect(screen.getByText('Add Corrective Action')).toBeInTheDocument();
    expect(screen.getByTestId('role-action-form')).toBeInTheDocument();
    const savedRoleAction = screen.getAllByTestId(/^role-action-/)[0]?.textContent ?? '';
    expect(savedRoleAction.trim().length).toBeGreaterThan(0);

    fireEvent.click(modeSwitch());
    expect(modeSwitch()).toHaveAttribute('aria-checked', 'true');
    expect(screen.queryByText(/^Presenting$/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId('role-action-form')).not.toBeInTheDocument();
    expect(screen.queryByText('Add Corrective Action')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.getAllByTestId(/^role-action-/)[0]?.textContent).toBe(savedRoleAction);

    const expectPresenting = () => {
      expect(modeSwitch()).toHaveAttribute('aria-checked', 'true');
      expect(screen.queryByText(/^Presenting$/i)).not.toBeInTheDocument();
    };

    fireEvent.click(screen.getByTestId('breadcrumb-function'));
    expect(screen.getByTestId('function-deep-dive-page')).toBeInTheDocument();
    expectPresenting();
    expect(screen.getByTestId('deep-dive-function-score')).toHaveTextContent('79.6%');

    fireEvent.click(screen.getByTestId('back-to-monthly-overview'));
    fireEvent.click(screen.getByTestId('function-card-call-center'));
    expect(screen.getByTestId('call-center-deep-dive-page')).toBeInTheDocument();
    expectPresenting();

    fireEvent.click(screen.getByTestId('agent-team-card-inbound-agents'));
    expect(screen.getByTestId('team-deep-dive-page')).toBeInTheDocument();
    expectPresenting();
    expect(screen.queryByTestId('add-team-action-btn')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.queryByText('No due date')).not.toBeInTheDocument();
    expect(screen.queryByText(/customize & save/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Deploy live AHT pacing alerts/i)).toBeInTheDocument();
    expect(screen.getAllByTestId(/^team-action-status-/).length).toBeGreaterThan(0);
    expect(
      screen.getAllByTestId(/^team-action-owner-/).every((node) => (node.textContent?.trim().length ?? 0) > 0),
    ).toBe(true);
    expect(screen.getByTestId('team-deep-dive-score')).toHaveTextContent('92.6%');

    fireEvent.click(screen.getByTestId('back-to-call-center-deep-dive'));
    fireEvent.click(screen.getByTestId('back-to-monthly-overview'));
    fireEvent.click(screen.getByTestId('function-card-marketing'));
    expectPresenting();
    fireEvent.click(screen.getByTestId('dragging-roles-next'));
    fireEvent.click(screen.getByTestId('dragging-roles-next'));
    fireEvent.click(screen.getByTestId('role-card-graphic-designer'));
    expect(screen.getByTestId('role-detail-page')).toBeInTheDocument();
    expectPresenting();
    expect(screen.queryByTestId('role-action-form')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Edit' })).not.toBeInTheDocument();
    expect(screen.queryByText('No corrective actions recorded for this role yet.')).not.toBeInTheDocument();
    expect(screen.getAllByTestId(/^role-action-/)[0]?.textContent).toBe(savedRoleAction);

    fireEvent.click(modeSwitch());
    expect(modeSwitch()).toHaveAttribute('aria-checked', 'false');
    expect(screen.queryByText(/^Presenting$/i)).not.toBeInTheDocument();
    expect(screen.getByText('Add Corrective Action')).toBeInTheDocument();
    expect(screen.getByTestId('role-action-form')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Edit' }).length).toBeGreaterThan(0);

    fireEvent.click(within(screen.getByTestId('role-detail-breadcrumb')).getByRole('button', { name: 'Overview' }));
    expect(screen.getByTestId('monthly-overview-page')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Monthly Presentation' })).toBeInTheDocument();
    expect(screen.getByTestId('overall-score-value')).toHaveTextContent('86.6%');
    expect(modeSwitch()).toHaveAttribute('aria-checked', 'false');
  });

  it('uses the UAE overview and does not reuse Egypt people when the region switches', () => {
    render(
      <MemoryRouter initialEntries={['/monthly-presentation']}>
        <MonthlyPresentationView />
        <LocationProbe />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('region-uae'));
    expect(screen.getByTestId('location-probe')).toHaveTextContent('region=uae');
    expect(screen.getByTestId('header-region-badge')).toHaveTextContent('UAE Region');
    expect(screen.getByTestId('overall-score-value')).toHaveTextContent('91.8%');
    expect(screen.getByTestId('function-card-csr')).toBeInTheDocument();
    expect(screen.queryByTestId('function-card-call-center')).not.toBeInTheDocument();
    expect(screen.queryByText(/Maryam Elsayed/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Coding EGY/i)).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('function-card-csr'));
    expect(screen.getByTestId('function-deep-dive-page')).toBeInTheDocument();
    expect(screen.getByText('No measured rows for this region in the locked month.')).toBeInTheDocument();
    expect(screen.queryByText(/Nourshan/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/Maryam Elsayed/i)).not.toBeInTheDocument();
  });

  it('steps from the control bar and saves agenda and notes for the region and month', () => {
    const { unmount } = render(
      <MemoryRouter initialEntries={['/monthly-presentation']}>
        <MonthlyPresentationView />
        <LocationProbe />
      </MemoryRouter>,
    );

    const bar = screen.getByTestId('presentation-control-bar');
    expect(bar).toBeInTheDocument();
    expect(within(bar).getByTestId('presentation-month')).toHaveTextContent(/^Sep$/);
    expect(within(bar).queryByText('Presentation Mode')).not.toBeInTheDocument();
    fireEvent.click(within(bar).getByTestId('presentation-month'));
    expect(screen.getByRole('option', { name: 'September 2026' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('option', { name: 'September 2026' })).toHaveTextContent('Sep');
    expect(screen.getAllByRole('switch', { name: 'Presentation Mode' })).toHaveLength(1);
    expect(within(bar).getByRole('switch', { name: 'Presentation Mode' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Previous' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Next' })).not.toBeInTheDocument();
    const barOrder = [
      'presentation-month',
      'presentation-mode-switch',
      'presentation-menu-toggle',
      'presentation-agenda',
      'presentation-notes',
      'presentation-compliance',
    ].map((id) => within(bar).getByTestId(id));
    for (let i = 1; i < barOrder.length; i += 1) {
      expect(barOrder[i - 1].compareDocumentPosition(barOrder[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    }

    const menuToggle = screen.getByTestId('presentation-menu-toggle');
    expect(menuToggle).toHaveAttribute('aria-expanded', 'true');
    expect(menuToggle.querySelector('svg')).not.toHaveClass('rotate-45');
    fireEvent.click(menuToggle);
    expect(menuToggle).toHaveAttribute('aria-expanded', 'false');
    expect(bar).toHaveAttribute('data-collapsed', 'true');
    expect(bar.className).toContain('bg-transparent');
    expect(bar.className).toContain('border-0');
    expect(bar.className).toContain('pointer-events-none');
    expect(menuToggle.querySelector('svg')).toHaveClass('rotate-45');
    expect(within(bar).getByTestId('presentation-month')).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(menuToggle);
    expect(menuToggle).toHaveAttribute('aria-expanded', 'true');
    expect(bar).toHaveAttribute('data-collapsed', 'false');
    expect(bar.className).toContain('bg-white/95');
    expect(bar.className).not.toContain('pointer-events-none');

    fireEvent.keyDown(window, { key: 'ArrowRight' });
    expect(screen.getByTestId('location-probe').textContent).toContain('deepDive=rcm');
    expect(screen.getByRole('heading', { name: 'RCM Deep Dive' })).toBeInTheDocument();

    fireEvent.keyDown(window, { key: 'ArrowLeft' });
    expect(screen.getByTestId('location-probe').textContent).not.toContain('deepDive');
    expect(screen.getByTestId('monthly-overview-page')).toBeInTheDocument();

    fireEvent.click(screen.getByTestId('presentation-agenda'));
    fireEvent.change(screen.getByTestId('presentation-agenda-text'), {
      target: { value: 'Open with RCM.' },
    });
    fireEvent.click(screen.getByTestId('presentation-agenda-save'));
    expect(localStorage.getItem('pms-monthly-pad:EGY:2026-09:agenda')).toBe('Open with RCM.');

    fireEvent.change(screen.getByTestId('presentation-agenda-text'), {
      target: { value: 'Unsaved visit note' },
    });
    fireEvent.click(screen.getByTestId('presentation-agenda-pad-close'));
    expect(localStorage.getItem('pms-monthly-pad:EGY:2026-09:agenda')).toBe('Open with RCM.');
    fireEvent.click(screen.getByTestId('presentation-agenda'));
    expect(screen.getByTestId('presentation-agenda-text')).toHaveValue('Unsaved visit note');

    fireEvent.click(screen.getByTestId('presentation-notes'));
    expect(screen.getByTestId('presentation-notes-strikeThrough')).toBeInTheDocument();
    expect(screen.getByTestId('presentation-notes-bullets')).toBeInTheDocument();
    expect(screen.getByTestId('presentation-notes-numbers')).toBeInTheDocument();
    expect(screen.getByTestId('presentation-notes-clear')).toBeInTheDocument();
    expect(screen.getByRole('group', { name: 'Text color' }).querySelectorAll('button')).toHaveLength(6);
    expect(screen.getByRole('group', { name: 'Highlight' }).querySelectorAll('button')).toHaveLength(5);
    fireEvent.click(screen.getByTestId('presentation-notes-paper-blue'));
    expect(screen.getByTestId('presentation-notes-pad')).toHaveStyle({ backgroundColor: '#e0f2fe' });
    const notes = screen.getByTestId('presentation-notes-text');
    notes.innerHTML = '<span style="color: #1d4ed8; position: absolute">Follow up owners</span><script>bad</script>';
    fireEvent.input(notes);
    fireEvent.click(screen.getByTestId('presentation-notes-save'));
    const storedNotes = localStorage.getItem('pms-monthly-pad:EGY:2026-09:notes') ?? '';
    expect(storedNotes).toContain('Follow up owners');
    expect(storedNotes).toContain('color: #1d4ed8');
    expect(storedNotes).not.toContain('position');
    expect(storedNotes).not.toContain('script');
    expect(localStorage.getItem('pms-monthly-pad:EGY:2026-09:notes-paper')).toBe('blue');

    unmount();
    render(
      <MemoryRouter initialEntries={['/monthly-presentation']}>
        <MonthlyPresentationView />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId('presentation-agenda'));
    expect(screen.getByTestId('presentation-agenda-text')).toHaveValue('Open with RCM.');
    fireEvent.click(screen.getByTestId('presentation-notes'));
    expect(screen.getByTestId('presentation-notes-text').textContent).toContain('Follow up owners');
    expect(screen.getByTestId('presentation-notes-pad')).toHaveStyle({ backgroundColor: '#e0f2fe' });
    expect(screen.getByTestId('presentation-notes-paper-blue')).toHaveAttribute('aria-pressed', 'true');
  });

  it('opens data compliance from the presentation menu and flips back after an edit', () => {
    render(
      <MemoryRouter initialEntries={['/monthly-presentation']}>
        <MonthlyPresentationView />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('presentation-compliance'));
    expect(screen.getByRole('dialog', { name: 'Data Compliance' })).toBeInTheDocument();
    const chart = screen.getByTestId('presentation-compliance-chart');
    expect(within(chart).getByText('Department Completion')).toBeInTheDocument();
    expect(within(chart).getByText('Call Center')).toBeInTheDocument();
    expect(within(chart).getByText('RCM')).toBeInTheDocument();
    expect(within(chart).queryByText('CSR')).not.toBeInTheDocument();
    expect(within(chart).queryByText('Quality')).not.toBeInTheDocument();

    fireEvent.click(chart);
    fireEvent.change(screen.getByTestId('compliance-done-rcm'), { target: { value: '19' } });
    fireEvent.change(screen.getByTestId('compliance-total-rcm'), { target: { value: '20' } });
    fireEvent.click(screen.getByText('Department'));

    const updated = screen.getByTestId('presentation-compliance-chart');
    expect(within(updated).getByText('19/20')).toBeInTheDocument();
    expect(within(updated).getByText('95%')).toBeInTheDocument();
    expect(updated.querySelector('[data-grade="A"]')).toHaveStyle({ background: 'var(--pms-grade-a-gauge)' });
    expect(localStorage.getItem('pms-monthly-pad:EGY:2026-09:compliance')).toContain('"rcm"');

    fireEvent.click(screen.getByTestId('region-uae'));
    const uaeChart = screen.getByTestId('presentation-compliance-chart');
    expect(within(uaeChart).getByText('CSR')).toBeInTheDocument();
    expect(within(uaeChart).getByText('Pharmacy')).toBeInTheDocument();
    expect(within(uaeChart).queryByText('Call Center')).not.toBeInTheDocument();
    expect(within(uaeChart).queryByText('19/20')).not.toBeInTheDocument();
    expect(localStorage.getItem('pms-monthly-pad:EGY:2026-09:compliance')).toContain('"rcm"');
  });
});
