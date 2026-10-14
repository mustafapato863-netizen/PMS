import type { ComponentProps } from 'react';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import TeamRosterSection from './TeamRosterSection';

vi.mock('./EmployeeRowActions', () => ({
  default: ({ row }: { row: TeamAgentRow }) => (
    <button type="button" aria-haspopup="menu" aria-label={`Open actions for ${row.name}`}>More</button>
  ),
}));

type Props = ComponentProps<typeof TeamRosterSection>;

function agent(overrides: Partial<TeamAgentRow>): TeamAgentRow {
  return {
    id: 'EMP-1',
    name: 'Test Agent',
    team: 'Inbound',
    month: 'June',
    performanceLevel: 'Employee',
    score: 94,
    gradeClass: 'B',
    gradeLabel: 'B',
    status: 'Meet',
    rootCauseAuto: 'Attend ↓ (main issue)',
    rootCauseNote: '',
    correctiveAction: '',
    suggestedAction: 'Coaching',
    ahtMinutes: 3,
    bookingRate: 0.5,
    attendRate: 0.7,
    raw: {
      identity: { name: 'Test Agent', employee_id: 'EMP-1', team: 'Inbound', month: 'June' },
      calls: { inbound: 10, outbound: 0, total_handled: 10, abandoned: 1, aht_raw: '00:03:00' },
      geo: {
        bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
        attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
      },
      actual: { booking_rate: 0.5, attend_rate: 0.7, abandon_rate: 0.1, quality_rate: 0.9 },
      achievement: { booking_ach: 1, attend_ach: 0.9 },
      evaluation: { score: 94, grade: 'B' },
    },
    ...overrides,
  };
}

const rows = [
  agent({}),
  agent({ id: 'EMP-2', name: 'Second Agent', score: 72.5, gradeClass: 'D', gradeLabel: 'D', status: 'Below' }),
];

function makeProps(overrides: Partial<Props> = {}): Props {
  return {
    showTopBottomToggle: false,
    rosterView: 'all',
    setRosterView: vi.fn(),
    search: '',
    setSearch: vi.fn(),
    page: 1,
    setPage: vi.fn(),
    totalPages: 1,
    paginated: rows,
    filtered: rows,
    rosterData: { top3: [], bottom3: [], allMeetStandards: false },
    role: 'Admin',
    month: 'June',
    performanceLevel: 'Employee',
    prevRows: new Map<string, { score: number }>(),
    teamAverage: 85,
    getActionsForEmployee: () => [],
    onAddAction: vi.fn(),
    sortCol: 'score',
    sortDir: 'desc',
    toggleSort: vi.fn(),
    canExport: true,
    onExport: vi.fn(),
    ...overrides,
  };
}

function renderRoster(overrides: Partial<Props> = {}) {
  return render(
    <MemoryRouter>
      <TeamRosterSection {...makeProps(overrides)} />
    </MemoryRouter>,
  );
}

const originalMatchMedia = window.matchMedia;

/** jsdom has no matchMedia; this answers the 767px query so the card layout can be tested. */
function stubViewport(narrow: boolean) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: narrow && query === '(max-width: 767px)',
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

beforeEach(() => {
  stubViewport(false);
});

afterEach(() => {
  window.matchMedia = originalMatchMedia;
});

describe('TeamRosterSection: table layout', () => {
  it('leaves the Team column out on a single-team page', () => {
    renderRoster({ showTeamColumn: false });

    expect(screen.queryByRole('columnheader', { name: 'Team' })).not.toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Employee' })).toBeInTheDocument();
  });

  it('shows the Team column on all-teams and parent views', () => {
    renderRoster({ showTeamColumn: true });

    expect(screen.getByRole('columnheader', { name: 'Team' })).toBeInTheDocument();
    expect(within(screen.getByRole('row', { name: /Test Agent/ })).getByText('Inbound')).toBeInTheDocument();
  });

  it('uses sentence-case headers and a sticky header row', () => {
    const { container } = renderRoster();

    expect(screen.getByRole('heading', { name: 'Employee roster' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Root cause' })).toBeInTheDocument();
    expect(container.querySelector('thead')).toHaveClass('sticky', 'top-0');
  });

  it('shows score and grade as one chip in the grade tone', () => {
    renderRoster();

    const chip = screen.getByText('94.0% · B');
    expect(chip).toHaveClass('rounded-md');
    expect(screen.queryByText('B')).not.toBeInTheDocument();
  });

  it('shows status as a dot with the grade status word', () => {
    renderRoster();

    expect(screen.getByText('Meet')).toBeInTheDocument();
    expect(screen.getByText('Below')).toBeInTheDocument();
  });

  it('shows the root cause on one line with main issue as a tag and the full text as tooltip', () => {
    renderRoster();

    const rootCause = screen.getByTitle('Attend ↓ (main issue)');
    expect(rootCause).toHaveTextContent('Attend ↓');
    expect(within(rootCause).getByText('main issue')).toBeInTheDocument();
  });

  it('shows No gap for an A or B row', () => {
    renderRoster({ paginated: [agent({})], filtered: [agent({})] });

    expect(screen.getByText('No gap')).toBeInTheDocument();
  });

  it('shows a dash with a No previous month tooltip when there is no comparison', () => {
    renderRoster();

    expect(screen.getAllByTitle('No previous month')).toHaveLength(rows.length);
  });

  it('calls toggleSort when the Score header is pressed', async () => {
    const user = userEvent.setup();
    const toggleSort = vi.fn();
    renderRoster({ toggleSort });

    await user.click(screen.getByRole('columnheader', { name: 'Score' }));

    expect(toggleSort).toHaveBeenCalledWith('score');
  });
});

describe('TeamRosterSection: row actions', () => {
  it('shows Add action and Open profile as labelled buttons beside the overflow menu', () => {
    renderRoster({ paginated: [rows[0]], filtered: [rows[0]] });

    expect(screen.getByRole('button', { name: 'Add action for Test Agent' })).toHaveAttribute('title', 'Add action');
    expect(screen.getByRole('link', { name: 'Open profile for Test Agent' })).toHaveAttribute('href', expect.stringContaining('/employee/EMP-1'));
    expect(screen.getByRole('button', { name: 'Open actions for Test Agent' })).toHaveAttribute('aria-haspopup', 'menu');
  });

  it('calls onAddAction for the row when Add action is pressed from the keyboard', async () => {
    const user = userEvent.setup();
    const onAddAction = vi.fn();
    renderRoster({ paginated: [rows[0]], filtered: [rows[0]], onAddAction });

    const addButton = screen.getByRole('button', { name: 'Add action for Test Agent' });
    addButton.focus();
    await user.keyboard('{Enter}');

    expect(onAddAction).toHaveBeenCalledWith(expect.objectContaining({ id: 'EMP-1', name: 'Test Agent' }));
  });

  it('hides Add action for a role that cannot manage actions, and keeps Open profile', () => {
    renderRoster({ role: 'Viewer', paginated: [rows[0]], filtered: [rows[0]] });

    expect(screen.queryByRole('button', { name: 'Add action for Test Agent' })).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open profile for Test Agent' })).toBeInTheDocument();
  });
});

describe('TeamRosterSection: toolbar', () => {
  it('keeps search, the segmented view switch and export in one toolbar', async () => {
    const user = userEvent.setup();
    const onExport = vi.fn();
    renderRoster({ showTopBottomToggle: true, onExport });

    expect(screen.getByRole('textbox', { name: 'Search employees' })).toBeInTheDocument();
    const view = screen.getByRole('group', { name: 'Employee roster view' });
    expect(within(view).getByRole('button', { name: 'All Employees' })).toHaveAttribute('aria-pressed', 'true');

    await user.click(screen.getByRole('button', { name: 'Export' }));
    expect(onExport).toHaveBeenCalledTimes(1);
  });

  it('hides export when it is not allowed', () => {
    renderRoster({ canExport: false });

    expect(screen.queryByRole('button', { name: 'Export' })).not.toBeInTheDocument();
  });
});

describe('TeamRosterSection: narrow viewport', () => {
  it('stacks one card per employee below 768px, with no table', () => {
    stubViewport(true);
    renderRoster();

    expect(screen.queryByRole('table')).not.toBeInTheDocument();
    const cards = screen.getAllByRole('article');
    expect(cards).toHaveLength(rows.length);
    expect(within(cards[0]).getByRole('button', { name: 'Add action for Test Agent' })).toBeInTheDocument();
    expect(within(cards[0]).getByRole('link', { name: 'Open profile for Test Agent' })).toBeInTheDocument();
  });
});
