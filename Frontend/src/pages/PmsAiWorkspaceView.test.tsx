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

  it('renders Executive Brief mode with scope banner, primary source link, and zero-call Show details expansion', async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/ai/watching')) {
        return WATCHING_RESPONSE;
      }
      if (path === '/api/ai/chat') {
        return {
          success: true,
          data: {
            ...CHAT_RESPONSE.data,
            answer_detail: 'brief' as const,
            scope_banner: 'All UAE · Inbound · Employee · March 2026',
            primary_source_link: {
              label: 'Open Inbound Scorecard →',
              route: '/team/Inbound?month=March',
              icon_key: 'team' as const,
            },
          },
        };
      }
      return { success: true };
    });

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

    // Scope banner and primary source link are visible immediately in Brief mode
    expect(screen.getByTestId('ai-scope-banner')).toHaveTextContent(
      'All UAE · Inbound · Employee · March 2026',
    );
    expect(screen.getByTestId('ai-primary-source-link')).toHaveTextContent(
      'Open Inbound Scorecard →',
    );

    // Visual breakdown cards start collapsed in Brief mode
    expect(screen.queryByText('Tarek Nabil · Inbound')).not.toBeInTheDocument();
    const showDetailsBtn = screen.getByRole('button', { name: /Show details/i });
    expect(showDetailsBtn).toHaveAttribute('aria-expanded', 'false');

    const chatCallsBeforeExpand = mockedApiFetch.mock.calls.filter(
      (call) => call[0] === '/api/ai/chat',
    ).length;
    expect(chatCallsBeforeExpand).toBe(1);

    // Clicking Show details expands the same authorized evidence with zero additional model calls
    fireEvent.click(showDetailsBtn);

    expect(screen.getByText('Tarek Nabil · Inbound')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Hide details/i })).toHaveAttribute(
      'aria-expanded',
      'true',
    );

    const chatCallsAfterExpand = mockedApiFetch.mock.calls.filter(
      (call) => call[0] === '/api/ai/chat',
    ).length;
    expect(chatCallsAfterExpand).toBe(1);
  });

  it('handles clarification choice click, persists last_confirmed_query across follow-up turns, and retries 503 errors', async () => {
    let chatTurn = 0;
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/ai/watching')) {
        return WATCHING_RESPONSE;
      }
      if (path === '/api/ai/chat') {
        chatTurn += 1;
        if (chatTurn === 1) {
          throw new Error('503: The AI routing provider is temporarily unavailable.');
        }
        if (chatTurn === 2) {
          return {
            success: true,
            data: {
              ...CHAT_RESPONSE.data,
              conversation_id: 'conv-123',
              context_version: 2,
              outcome: 'clarification' as const,
              headline: 'Which attendance metric would you like to inspect for Call Center?',
              visual_cards: [],
              clarification: {
                code: 'AMBIGUOUS_ATTENDANCE_DEFINITION' as const,
                question: 'Which attendance metric would you like to inspect for Call Center?',
                choices: [
                  {
                    id: 'choice-patient-attendance-inbound',
                    label: 'Inbound Patient Attendance Rate (Attended / Bookings)',
                    prompt_to_send: 'What is Inbound Patient Attendance Rate vs target in September 2026?',
                    team: 'Inbound',
                    metric_id: 'inbound:attendance_rate',
                  },
                ],
              },
              resolved_session_state: {
                ...CHAT_RESPONSE.data.resolved_session_state,
                last_confirmed_query: {
                  intent: 'clarify' as const,
                  function: 'Call Center',
                  periods: ['2026-09'],
                },
              },
            },
          };
        }
        return {
          success: true,
          data: {
            ...CHAT_RESPONSE.data,
            conversation_id: 'conv-123',
            context_version: 3,
            outcome: 'answer' as const,
            headline: 'Inbound Patient Attendance Rate is 52.8% vs 65.0% target.',
          },
        };
      }
      return { success: true };
    });

    renderWorkspace('/ai');

    const input = screen.getByLabelText('Ask PMS AI a question');
    fireEvent.change(input, { target: { value: 'What is Attendance in September 2026?' } });
    fireEvent.click(screen.getByLabelText('Send prompt'));

    // Turn 1 fails with 503 error banner + Retry button
    await waitFor(() => {
      expect(screen.getByText(/Unable to complete analysis/i)).toBeInTheDocument();
    });
    const retryBtn = screen.getByRole('button', { name: /Retry/i });
    fireEvent.click(retryBtn);

    // Turn 2 returns clarification prompt & choice button
    await waitFor(() => {
      expect(
        screen.getByText('Inbound Patient Attendance Rate (Attended / Bookings)'),
      ).toBeInTheDocument();
    });

    // Clicking the clarification choice sends the clarified prompt with last_confirmed_query in session_state
    fireEvent.click(
      screen.getByText('Inbound Patient Attendance Rate (Attended / Bookings)'),
    );

    await waitFor(() => {
      expect(
        screen.getByText('Inbound Patient Attendance Rate is 52.8% vs 65.0% target.'),
      ).toBeInTheDocument();
    });

    const chatCalls = mockedApiFetch.mock.calls.filter((call) => call[0] === '/api/ai/chat');
    expect(chatCalls.length).toBe(3);
    const thirdCallBody = JSON.parse(String(chatCalls[2][1]?.body || '{}'));
    expect(thirdCallBody.session_state.last_confirmed_query.intent).toBe('clarify');
    expect(thirdCallBody.conversation_id).toBe('conv-123');
    expect(thirdCallBody.context_version).toBe(2);
    expect(thirdCallBody.clarification_choice_id).toBe('choice-patient-attendance-inbound');

    // Clicking New chat deletes the server conversation and resets the stream
    const newChatBtn = screen.getByRole('button', { name: /New chat/i });
    fireEvent.click(newChatBtn);
    await waitFor(() => {
      expect(mockedApiFetch).toHaveBeenCalledWith(
        '/api/ai/conversations/conv-123',
        expect.objectContaining({ method: 'DELETE' }),
      );
    });
  });
});
