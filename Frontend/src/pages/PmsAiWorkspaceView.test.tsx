import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import PmsAiWorkspaceView from './PmsAiWorkspaceView';
import { apiFetch } from '../lib/apiClient';

vi.mock('../context/auth', () => ({
  useAuth: () => ({
    currentUser: {
      id: 'mgr-1',
      name: 'Salma Hassan',
      username: 'salma',
      role: 'Manager',
    },
  }),
}));

vi.mock('../store/appStore', () => ({
  useAppStore: (selector: (s: { activeMonth: string }) => unknown) =>
    selector({ activeMonth: 'March' }),
}));

vi.mock('../lib/apiClient', () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

const WATCHING_RESPONSE = {
  success: true,
  data: {
    resolved_session_state: {
      function: 'Call Center',
      team: null,
      branch: null,
      performance_level: null,
      month: 'March',
      year: 2026,
    },
    alerts: [
      {
        id: 'watch-1',
        title: 'Inbound team dropped 8.4%',
        subtitle: 'Abandon Rate (Inbound) spiked in Sharjah',
        severity: 'critical' as const,
        prompt_to_ask: 'Why did Inbound drop in March and who caused it?',
      },
      {
        id: 'watch-2',
        title: '3 corrective actions overdue',
        subtitle: 'Call Center · March 2026',
        severity: 'warning' as const,
        prompt_to_ask: 'Summarize corrective actions and compliance gaps',
      },
    ],
    guardrails: [
      {
        label: 'Never modifies evaluations on its own',
        description: 'Strictly read-only diagnostic mode in Phase 1',
        verified: true,
      },
      {
        label: 'Only sees data your role can see',
        description: 'Enforces RBAC team, function, and branch boundaries',
        verified: true,
      },
    ],
    starter_prompts: [
      {
        id: 'team_drop',
        label: 'Which team dropped the most & why?',
        prompt: 'Which Call Center team dropped the most and who were the main drivers?',
        category: 'team' as const,
        icon_key: 'alert' as const,
      },
      {
        id: 'at_risk',
        label: 'Who is at risk or declining?',
        prompt: 'Who are the employees at risk or showing declining performance?',
        category: 'people' as const,
        icon_key: 'users' as const,
      },
      {
        id: 'kpi_bottleneck',
        label: 'Biggest KPI bottlenecks by team',
        prompt: 'Show KPI bottlenecks and achievement comparison across Call Center teams',
        category: 'kpi' as const,
        icon_key: 'chart' as const,
      },
      {
        id: 'corrective_gaps',
        label: 'Summarize corrective actions & gaps',
        prompt: 'Summarize corrective actions, coaching plans, and compliance gaps',
        category: 'governance' as const,
        icon_key: 'shield' as const,
      },
    ],
    summary_score: 78.4,
    summary_score_change: -3.2,
    measured_records: 25,
  },
};

const CHAT_RESPONSE = {
  success: true,
  data: {
    trace_id: 'trace-42',
    headline: 'Inbound is at 71.2% average score — the lowest among 2 evaluated teams.',
    narrative_bullets: [
      'Inbound is at 71.2% vs Outbound at 86.5%.',
      'Primary driver is Abandon Rate (Inbound) below target.',
    ],
    visual_cards: [
      {
        card_type: 'horizontal_bar' as const,
        title: 'Call Center Team Comparison',
        subtitle: 'March 2026',
        bars: [
          {
            label: 'Inbound',
            value: 71.2,
            display_value: '71.2%',
            secondary_label: '14 employees · Δ -6.4%',
            severity: 'critical' as const,
          },
          {
            label: 'Outbound',
            value: 86.5,
            display_value: '86.5%',
            secondary_label: '11 employees · Δ +1.8%',
            severity: 'good' as const,
          },
        ],
        items: [],
        kpi_rows: [],
      },
      {
        card_type: 'entity_list' as const,
        title: 'Employees Driving Drop',
        items: [
          {
            id: 'emp-1',
            title: 'Tarek Nabil · Inbound',
            subtitle: '61.5% score · Abandon Rate (Inbound) below target',
            severity: 'critical' as const,
            badge_text: 'Needs Improvement',
            route_link: '/employee/emp-1',
          },
        ],
        bars: [],
        kpi_rows: [],
      },
    ],
    citations: [
      { label: 'Scope · Call Center', category: 'scope' as const },
      { label: 'Time · March 2026', category: 'period' as const },
    ],
    deep_links: [
      {
        label: 'Open Insights →',
        route: '/insights?function=Call+Center&month=March',
        icon_key: 'insights' as const,
      },
    ],
    suggested_followups: ['Who are the employees at risk in Inbound?'],
    resolved_session_state: {
      function: 'Call Center',
      team: null,
      branch: null,
      performance_level: null,
      month: 'March',
      year: 2026,
    },
    domain_guardrail_notes: [],
    tool_calls: [
      {
        tool_name: 'compare_teams_and_branches',
        arguments: { function: 'Call Center', month: 'March' },
        records_evaluated: 25,
      },
    ],
    provider_used: 'deterministic-local',
    model_used: 'pms-deterministic-v1',
    latency_ms: 18,
    basis_warning: null,
  },
};

function renderWorkspace(initialEntry = '/ai') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialEntry]}>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return render(<PmsAiWorkspaceView />, { wrapper: Wrapper });
}

describe('PmsAiWorkspaceView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Element.prototype.scrollIntoView = vi.fn();
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/ai/watching')) {
        return WATCHING_RESPONSE;
      }
      if (path === '/api/ai/chat') {
        return CHAT_RESPONSE;
      }
      if (path === '/api/ai/feedback') {
        return { success: true, trace_id: 'trace-42', rating: 'up' };
      }
      return { success: true };
    });
  });

  it('renders ZainX-styled empty state, AI is watching rail, and Guardrails', async () => {
    renderWorkspace('/ai');

    expect(screen.getByText(/Hi Salma, how can I help\?/i)).toBeInTheDocument();
    expect(screen.getByText('AI is watching')).toBeInTheDocument();
    expect(screen.getByText('Guardrails')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Inbound team dropped 8.4%')).toBeInTheDocument();
    });
    expect(screen.getByText('3 corrective actions overdue')).toBeInTheDocument();
    expect(screen.getByText('Which team dropped the most & why?')).toBeInTheDocument();
  });

  it('dispatches a starter prompt, renders structured visual card, and records verification feedback', async () => {
    renderWorkspace('/ai');

    await waitFor(() => {
      expect(screen.getByText('Which team dropped the most & why?')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Which team dropped the most & why?'));

    await waitFor(() => {
      expect(
        screen.getByText(
          'Inbound is at 71.2% average score — the lowest among 2 evaluated teams.',
        ),
      ).toBeInTheDocument();
    });

    // Horizontal bars & entity list rows rendered
    expect(screen.getByText('71.2%')).toBeInTheDocument();
    expect(screen.getByText('86.5%')).toBeInTheDocument();
    expect(screen.getByText('Tarek Nabil · Inbound')).toBeInTheDocument();
    expect(screen.getByText('Open Insights →')).toBeInTheDocument();
    expect(screen.getByText('Scope · Call Center')).toBeInTheDocument();

    // Click thumbs-up verification button for distillation trace
    const approveBtn = screen.getByLabelText('Approve response for AI training');
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(screen.getByText(/Verified/i)).toBeInTheDocument();
    });
    expect(mockedApiFetch).toHaveBeenCalledWith(
      '/api/ai/feedback',
      expect.objectContaining({
        method: 'POST',
      }),
    );
  });
});
