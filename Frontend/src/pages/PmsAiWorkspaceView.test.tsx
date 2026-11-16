import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import PmsAiWorkspaceView from './PmsAiWorkspaceView';
import { apiFetch } from '../lib/apiClient';

const mockAuthState = {
  currentUser: {
    id: 'mgr-1',
    name: 'Salma Hassan',
    username: 'salma',
    role: 'Manager',
  },
};

vi.mock('../context/auth', () => ({
  useAuth: () => mockAuthState,
}));

let mockActiveMonth = 'March';

vi.mock('../store/appStore', () => ({
  useAppStore: (selector: (s: { activeMonth: string }) => unknown) =>
    selector({ activeMonth: mockActiveMonth }),
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
    sessionStorage.clear();
    mockAuthState.currentUser = {
      id: 'mgr-1',
      name: 'Salma Hassan',
      username: 'salma',
      role: 'Manager',
    };
    Element.prototype.scrollIntoView = vi.fn();
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/ai/watching')) {
        return WATCHING_RESPONSE;
      }
      if (path.startsWith('/api/ai/conversations?')) {
        return { success: true, message: 'Loaded', conversations: [] };
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

  it('keeps AI is watching panel closed by default without fetching /api/ai/watching until opened', async () => {
    renderWorkspace('/ai');

    expect(screen.getByText(/Hi Salma, how can I help\?/i)).toBeInTheDocument();
    expect(screen.queryByText('AI is watching')).not.toBeInTheDocument();

    // Verify /api/ai/watching is not called while the rail is closed
    const watchingCallsWhileClosed = mockedApiFetch.mock.calls.filter((call) =>
      String(call[0]).startsWith('/api/ai/watching'),
    );
    expect(watchingCallsWhileClosed).toHaveLength(0);

    // Open the rail and verify /api/ai/watching executes and renders alerts & guardrails
    const showRailBtn = screen.getByLabelText('Show AI is watching panel');
    expect(showRailBtn).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(showRailBtn);

    expect(screen.getByText('AI is watching')).toBeInTheDocument();
    expect(screen.getByText('Guardrails')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Inbound team dropped 8.4%')).toBeInTheDocument();
    });
    expect(screen.getByText('3 corrective actions overdue')).toBeInTheDocument();
    expect(screen.getByText('Which team dropped the most & why?')).toBeInTheDocument();

    const watchingCallsAfterOpen = mockedApiFetch.mock.calls.filter((call) =>
      String(call[0]).startsWith('/api/ai/watching'),
    );
    expect(watchingCallsAfterOpen).toHaveLength(1);
  });

  it('dispatches a starter prompt and records feedback without claiming it was verified', async () => {
    renderWorkspace('/ai');

    expect(screen.getByText('Which team in All authorized departments dropped most?')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Which team in All authorized departments dropped most?'));

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

    // User feedback is a review signal, not an Admin verification.
    const approveBtn = screen.getByLabelText('Mark response as useful');
    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(screen.getByText('Feedback saved')).toBeInTheDocument();
    });
    expect(mockedApiFetch).toHaveBeenCalledWith(
      '/api/ai/feedback',
      expect.objectContaining({
        method: 'POST',
      }),
    );
  });

  it('does not show feedback as saved when its request fails', async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === '/api/ai/chat') return CHAT_RESPONSE;
      if (path === '/api/ai/feedback') throw new Error('Unavailable');
      return { success: true };
    });
    renderWorkspace('/ai');
    fireEvent.click(screen.getByText('Which team in All authorized departments dropped most?'));
    const useful = await screen.findByLabelText('Mark response as useful');
    fireEvent.click(useful);
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save feedback');
    expect(screen.queryByText('Feedback saved')).not.toBeInTheDocument();
  });

  it('renders Executive Brief mode with scope banner, primary source link, and zero-call View details expansion', async () => {
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

    fireEvent.click(screen.getByText('Which team in All authorized departments dropped most?'));

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
    const viewDetailsBtn = screen.getByRole('button', { name: /View details/i });
    expect(viewDetailsBtn).toHaveAttribute('aria-expanded', 'false');

    const chatCallsBeforeExpand = mockedApiFetch.mock.calls.filter(
      (call) => call[0] === '/api/ai/chat',
    ).length;
    expect(chatCallsBeforeExpand).toBe(1);

    // Clicking View details expands the same authorized evidence with zero additional model calls
    fireEvent.click(viewDetailsBtn);

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

    // Clicking New chat resets to a fresh draft conversation WITHOUT calling DELETE on the previous chat
    const newChatBtn = screen.getByTestId('ai-new-chat-btn');
    fireEvent.click(newChatBtn);
    await waitFor(() => {
      expect(screen.getByText(/Hi Salma, how can I help\?/i)).toBeInTheDocument();
    });
    const deleteCalls = mockedApiFetch.mock.calls.filter(
      (call) =>
        call[0] === '/api/ai/conversations/conv-123' &&
        (call[1] as { method?: string } | undefined)?.method === 'DELETE',
    );
    expect(deleteCalls).toHaveLength(0);
  });

  it('cancels in-flight requests on scope filter change and clears incompatible confirmed context', async () => {
    let resolveDelayedTurn: ((val: unknown) => void) | null = null;
    let chatCallIdx = 0;

    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === '/api/ai/catalog') {
        return { success: true, data: { eligible_teams: [
          { value: 'Inbound', label: 'Inbound', function: 'Call Center' },
          { value: 'Outbound', label: 'Outbound', function: 'Call Center' },
        ] } };
      }
      if (path.startsWith('/api/ai/watching')) {
        return WATCHING_RESPONSE;
      }
      if (path === '/api/ai/chat') {
        chatCallIdx += 1;
        if (chatCallIdx === 1) {
          return {
            success: true,
            data: {
              ...CHAT_RESPONSE.data,
              conversation_id: 'conv-scope-1',
              context_version: 2,
              headline: 'Adham in Inbound scored 91.5%.',
              resolved_session_state: {
                ...CHAT_RESPONSE.data.resolved_session_state,
                team: 'Inbound',
                last_confirmed_query: {
                  intent: 'ranking' as const,
                  function: 'Call Center',
                  team: 'Inbound',
                  position: 'Agent',
                  metric_id: 'inbound:booking_cr',
                  last_subject_employee_id: 'emp-adham',
                  last_subject_employee_name: 'Adham',
                  periods: ['2026-03'],
                },
              },
            },
          };
        }
        if (chatCallIdx === 2) {
          return new Promise((resolve) => {
            resolveDelayedTurn = resolve;
          });
        }
        return {
          success: true,
          data: {
            ...CHAT_RESPONSE.data,
            conversation_id: 'conv-scope-1',
            context_version: 3,
            headline: 'Outbound team average is 86.5%.',
          },
        };
      }
      return { success: true };
    });

    renderWorkspace('/ai');

    const input = screen.getByLabelText('Ask PMS AI a question');
    fireEvent.change(input, { target: { value: 'Who is top in Inbound?' } });
    fireEvent.click(screen.getByLabelText('Send prompt'));

    await waitFor(() => {
      expect(screen.getByText('Adham in Inbound scored 91.5%.')).toBeInTheDocument();
    });

    // Start a second slow request in Inbound
    fireEvent.change(input, { target: { value: 'Slow Inbound follow-up' } });
    fireEvent.click(screen.getByLabelText('Send prompt'));
    expect(screen.getByLabelText('Analyzing workspace data')).toBeInTheDocument();

    // Change Team filter to Outbound while request 2 is still in flight
    const teamDropdownBtn = screen.getByLabelText('Filter Team');
    fireEvent.click(teamDropdownBtn);
    const outboundOption = await screen.findByRole('option', { name: /Outbound/i });
    fireEvent.click(outboundOption);

    // Pending skeleton should be cancelled immediately and composer re-enabled
    expect(screen.queryByLabelText('Analyzing workspace data')).not.toBeInTheDocument();
    expect(input).not.toBeDisabled();

    // Even if the stale Inbound response resolves later, it must never render
    (resolveDelayedTurn as ((val: unknown) => void) | null)?.({
      success: true,
      data: {
        ...CHAT_RESPONSE.data,
        headline: 'STALE INBOUND REPLY SHOULD NOT RENDER',
      },
    });

    // Send a new request under Outbound filter and verify incompatible confirmed context was cleared
    fireEvent.change(input, { target: { value: 'How is Outbound doing?' } });
    fireEvent.click(screen.getByLabelText('Send prompt'));

    await waitFor(() => {
      expect(screen.getByText('Outbound team average is 86.5%.')).toBeInTheDocument();
    });
    expect(screen.queryByText('STALE INBOUND REPLY SHOULD NOT RENDER')).not.toBeInTheDocument();

    const chatCalls = mockedApiFetch.mock.calls.filter((call) => call[0] === '/api/ai/chat');
    expect(chatCalls.length).toBe(3);
    const thirdBody = JSON.parse(String(chatCalls[2][1]?.body || '{}'));
    expect(thirdBody.session_state.team).toBe('Outbound');
    expect(thirdBody.session_state.last_confirmed_query.team).toBe('Outbound');
    expect(thirdBody.session_state.last_confirmed_query.metric_id).toBeNull();
    expect(thirdBody.session_state.last_confirmed_query.last_subject_employee_id).toBeNull();
    expect(thirdBody.session_state.last_confirmed_query.last_subject_employee_name).toBeNull();
  });

  it('re-enables composer and cancels in-flight turn when switching accounts, and toggles AI is watching rail', async () => {
    let resolveInFlight: ((val: unknown) => void) | null = null;
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/ai/watching')) {
        return WATCHING_RESPONSE;
      }
      if (path === '/api/ai/chat') {
        return new Promise((resolve) => {
          resolveInFlight = resolve;
        });
      }
      return { success: true };
    });

    const { rerender } = renderWorkspace('/ai');

    // Panel starts closed; toggle open and then closed
    expect(screen.queryByText('AI is watching')).not.toBeInTheDocument();
    const showRailBtn = screen.getByLabelText('Show AI is watching panel');
    fireEvent.click(showRailBtn);
    expect(screen.getByText('AI is watching')).toBeInTheDocument();
    const hideRailBtn = screen.getByLabelText('Hide AI is watching panel');
    fireEvent.click(hideRailBtn);
    expect(screen.queryByText('AI is watching')).not.toBeInTheDocument();

    // Send a prompt that stays in flight
    const input = screen.getByLabelText('Ask PMS AI a question');
    fireEvent.change(input, { target: { value: 'Check my team' } });
    fireEvent.click(screen.getByLabelText('Send prompt'));
    expect(input).toBeDisabled();

    // Switch account while request is in flight
    mockAuthState.currentUser = {
      id: 'mgr-2',
      name: 'Omar Khalid',
      username: 'omar',
      role: 'Manager',
    };
    rerender(<PmsAiWorkspaceView />);

    await waitFor(() => {
      expect(screen.getByText(/Hi Omar, how can I help\?/i)).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Ask PMS AI a question')).not.toBeDisabled();

    // Resolving the old user's request must not leak into Omar's workspace
    (resolveInFlight as ((val: unknown) => void) | null)?.({
      success: true,
      data: {
        ...CHAT_RESPONSE.data,
        headline: 'SALMA PRIVATE DATA',
      },
    });
    expect(screen.queryByText('SALMA PRIVATE DATA')).not.toBeInTheDocument();
  });

  it('recovers from 409 stale context by immediately binding retry payload to freshly fetched confirmed_context and context_version', async () => {
    let chatAttempt = 0;
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/ai/watching')) {
        return WATCHING_RESPONSE;
      }
      if (path.startsWith('/api/ai/conversations/conv-stale/context')) {
        return {
          success: true,
          data: {
            conversation_id: 'conv-stale',
            context_version: 5,
            confirmed_context: {
              intent: 'actual_vs_target',
              function: 'Call Center',
              team: 'Outbound',
              periods: ['2026-08'],
            },
          },
        };
      }
      if (path === '/api/ai/chat') {
        chatAttempt += 1;
        if (chatAttempt === 1) {
          // Turn 1 establishes conv-stale at context_version 2 with Inbound context
          return {
            success: true,
            data: {
              ...CHAT_RESPONSE.data,
              conversation_id: 'conv-stale',
              context_version: 2,
              headline: 'Initial Inbound turn at version 2.',
              resolved_session_state: {
                ...CHAT_RESPONSE.data.resolved_session_state,
                last_confirmed_query: {
                  intent: 'ranking' as const,
                  function: 'Call Center',
                  team: 'Inbound',
                  periods: ['2026-03'],
                },
              },
            },
          };
        }
        if (chatAttempt === 2) {
          // Turn 2 encounters a 409 conflict because another tab advanced conv-stale to version 5
          throw new Error('409: Stale context_version 2; current is 5.');
        }
        return {
          success: true,
          data: {
            ...CHAT_RESPONSE.data,
            conversation_id: 'conv-stale',
            context_version: 6,
            headline: 'Recovered cleanly at context version 6.',
          },
        };
      }
      return { success: true };
    });

    renderWorkspace('/ai');

    const input = screen.getByLabelText('Ask PMS AI a question');
    fireEvent.change(input, { target: { value: 'Initial Inbound question' } });
    fireEvent.click(screen.getByLabelText('Send prompt'));

    await waitFor(() => {
      expect(screen.getByText('Initial Inbound turn at version 2.')).toBeInTheDocument();
    });

    // Now send Turn 2, which fails with 409
    fireEvent.change(input, { target: { value: 'Check target after other tab update' } });
    fireEvent.click(screen.getByLabelText('Send prompt'));

    await waitFor(() => {
      expect(screen.getByText(/409: Stale context_version/i)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /Retry/i }));

    await waitFor(() => {
      expect(screen.getByText('Recovered cleanly at context version 6.')).toBeInTheDocument();
    });

    // Verify retry payload used freshly fetched context_version (5) and confirmed_context (Outbound / 2026-08), NOT stale React state (Inbound / 2026-03)
    const chatCalls = mockedApiFetch.mock.calls.filter((call) => call[0] === '/api/ai/chat');
    expect(chatCalls).toHaveLength(3);
    const retryBody = JSON.parse(String(chatCalls[2][1]?.body || '{}'));
    expect(retryBody.conversation_id).toBe('conv-stale');
    expect(retryBody.context_version).toBe(5);
    expect(retryBody.session_state.last_confirmed_query).toEqual({
      intent: 'actual_vs_target',
      function: 'Call Center',
      team: 'Outbound',
      periods: ['2026-08'],
    });
    // Also verify a fresh client_request_id was generated on 409 conflict recovery
    const failedBody = JSON.parse(String(chatCalls[1][1]?.body || '{}'));
    expect(retryBody.client_request_id).not.toBe(failedBody.client_request_id);

    // Only one user prompt bubble for Turn 2 should exist (no duplicate bubble on Retry)
    expect(screen.getAllByText('Check target after other tab update')).toHaveLength(1);
  });

  it('renders neutral opening with "All authorized departments" and allows department switching', async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path === '/api/ai/catalog') {
        return {
          success: true,
          data: {
            functions: [
              { key: 'Call Center', label: 'Call Center' },
              { key: 'Operations', label: 'Operations' },
              { key: 'Finance', label: 'Finance' },
            ],
            teams: [
              { key: 'Inbound', label: 'Inbound', function_key: 'Call Center' },
              { key: 'Outbound', label: 'Outbound', function_key: 'Call Center' },
              { key: 'Dispatch', label: 'Dispatch', function_key: 'Operations' },
            ],
            branches: [{ key: 'dubai', label: 'Dubai' }],
            performance_levels: [{ key: 'Employee', label: 'Employee' }],
            kpis: [],
          },
        };
      }
      if (path === '/api/ai/chat') {
        return CHAT_RESPONSE;
      }
      return { success: true };
    });

    renderWorkspace('/ai?position=Old%20Role');

    // With multiple catalog functions, Department dropdown is rendered once catalog query resolves
    const deptBtn = await screen.findByLabelText('Filter Department');
    expect(deptBtn).toBeInTheDocument();

    expect(screen.getByText('All authorized departments')).toBeInTheDocument();
    expect(screen.getByText('All authorized teams')).toBeInTheDocument();

    // Select Department: Operations
    fireEvent.click(deptBtn);
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /Operations/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('option', { name: /Operations/i }));

    fireEvent.click(screen.getByLabelText('Filter Operations Team'));
    expect(screen.getByRole('option', { name: /Dispatch/i })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: /Inbound/i })).not.toBeInTheDocument();

    // Send a prompt and verify the request session state includes function='Operations'
    const input = screen.getByLabelText('Ask PMS AI a question');
    fireEvent.change(input, { target: { value: 'What is Operations performance?' } });
    fireEvent.click(screen.getByLabelText('Send prompt'));

    await waitFor(() => {
      const chatCalls = mockedApiFetch.mock.calls.filter((call) => call[0] === '/api/ai/chat');
      expect(chatCalls.length).toBeGreaterThan(0);
      const reqBody = JSON.parse(String(chatCalls[0][1]?.body || '{}'));
      expect(reqBody.session_state.function).toBe('Operations');
      expect(reqBody.session_state.position).toBeNull();
    });
  });

  it('names an empty team control and the branch control without a Call Center or UAE default', () => {
    renderWorkspace('/ai');

    expect(screen.getByLabelText('Filter Team')).toBeInTheDocument();
    expect(screen.queryByLabelText('Filter Call Center Team')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Filter Branch')).toBeInTheDocument();
    expect(screen.queryByLabelText('Filter UAE Branch')).not.toBeInTheDocument();
    expect(screen.queryByText(/Call Center/i)).not.toBeInTheDocument();
  });

  it('keeps Call Center labels only when Call Center is the selected function', () => {
    renderWorkspace('/ai?function=Call%20Center');

    expect(screen.getByLabelText('Filter Call Center Team')).toBeInTheDocument();
    expect(screen.getByText('Which Call Center team dropped most?')).toBeInTheDocument();
    expect(screen.getByLabelText('Filter Branch')).toBeInTheDocument();
  });

  it('uses the selected function in the empty-state starter fallback', () => {
    renderWorkspace('/ai?function=Pharmacy');

    expect(screen.getByLabelText('Filter Pharmacy Team')).toBeInTheDocument();
    expect(screen.getByText('Which team in Pharmacy dropped most?')).toBeInTheDocument();
    expect(screen.queryByText(/Call Center/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Filter UAE Branch')).not.toBeInTheDocument();
  });

  it('displays Latest Period instead of hardcoded September 2026 when watchingData is null and month is unset', () => {
    const prevMonth = mockActiveMonth;
    mockActiveMonth = '';
    try {
      renderWorkspace('/ai');
      expect(screen.getByText('Latest Period')).toBeInTheDocument();
      expect(screen.queryByText('September 2026')).not.toBeInTheDocument();
    } finally {
      mockActiveMonth = prevMonth;
    }
  });

  it('supports mid-chat Scenarios toggle and Different angle variation_seed submission', { timeout: 15000 }, async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/ai/watching')) {
        return WATCHING_RESPONSE;
      }
      if (path === '/api/ai/chat') {
        return {
          ...CHAT_RESPONSE,
          data: {
            ...CHAT_RESPONSE.data,
            outcome: 'answer' as const,
          },
        };
      }
      return { success: true };
    });

    renderWorkspace('/ai?function=Call%20Center&team=Inbound');

    const input = screen.getByLabelText('Ask PMS AI a question');
    fireEvent.change(input, { target: { value: 'Show Inbound score' } });
    fireEvent.click(screen.getByLabelText('Send prompt'));

    await waitFor(() => {
      expect(screen.getByTestId('ai-regenerate-angle-btn')).toBeInTheDocument();
    });

    // Mid-chat Scenarios drawer opens and shows scoped scenarios
    const scenariosBtn = screen.getByTestId('ai-midchat-scenarios-toggle');
    fireEvent.click(scenariosBtn);
    expect(screen.getByTestId('ai-midchat-scenarios-panel')).toBeInTheDocument();

    // Clicking Different angle re-submits the userPrompt with incremented variation_seed: 1
    fireEvent.click(screen.getByTestId('ai-regenerate-angle-btn'));
    await waitFor(() => {
      const chatCalls = mockedApiFetch.mock.calls.filter((call) => call[0] === '/api/ai/chat');
      expect(chatCalls.length).toBeGreaterThanOrEqual(2);
      const secondBody = JSON.parse(String(chatCalls[1][1]?.body || '{}'));
      expect(secondBody.prompt).toBe('Show Inbound score');
      expect(secondBody.variation_seed).toBe(1);
    });
  });

  it('does not leak UAE/Dubai/Sharjah cards when region=EGY is active on Call Center', () => {
    renderWorkspace('/ai?function=Call%20Center&region=EGY');

    expect(screen.getByText('Compare EGY teams & KPIs')).toBeInTheDocument();
    expect(screen.queryByText(/Dubai|Sharjah|UAE|Ajman|Clinics/i)).not.toBeInTheDocument();
  });

  it('lists Recent chats with accessible delete dialog, preserves pending delete on New click, handles failed delete, and confirms delete with DELETE API', async () => {
    const conversations = [
      {
        conversation_id: 'conv-a',
        title: 'Inbound bookings leader',
        created_at: '2026-09-01T10:00:00Z',
        updated_at: '2026-09-01T10:05:00Z',
        turn_count: 2,
        last_outcome: 'answer',
        last_scope_banner: 'Call Center · Inbound · August 2026',
        last_period: 'August 2026',
        has_restricted_turns: false,
        context_version: 2,
      },
    ];
    let shouldFailDelete = false;
    mockedApiFetch.mockImplementation(async (path: string, init?: { method?: string }) => {
      if (path.startsWith('/api/ai/conversations?origin=legacy')) {
        return { success: true, message: 'Loaded', conversations: [] };
      }
      if (path.startsWith('/api/ai/conversations?origin=workspace')) {
        return { success: true, message: 'Loaded', conversations };
      }
      if (path === '/api/ai/conversations/conv-a' && init?.method === 'DELETE') {
        if (shouldFailDelete) {
          throw new Error('HTTP 500: Failed to delete');
        }
        return { success: true, message: 'Deleted' };
      }
      if (path.startsWith('/api/ai/conversations/conv-a') && (!init?.method || init.method === 'GET')) {
        return {
          success: true,
          message: 'Loaded',
          data: {
            conversation_id: 'conv-a',
            owner_user_id: 'mgr-1',
            title: 'Inbound bookings leader',
            status: 'active',
            context_version: 2,
            confirmed_context: {},
            pending_clarification: null,
            has_restricted_turns: false,
            turns: [],
          },
        };
      }
      return { success: true };
    });

    renderWorkspace('/ai?conversation=conv-a');

    const toggleBtn = screen.getByTestId('ai-history-toggle');
    fireEvent.click(toggleBtn);

    await waitFor(() => {
      expect(screen.getByTestId('ai-recent-chat-conv-a')).toBeInTheDocument();
    });
    expect(screen.getByText('Recent chats (1)')).toBeInTheDocument();
    expect(screen.getByText('Only the selected chat is active')).toBeInTheDocument();
    expect(screen.getByTestId('ai-recent-chat-active-conv-a')).toHaveTextContent('Active');

    // Open accessible confirmation dialog; Cancel preserves chat and does not call DELETE
    fireEvent.click(screen.getByLabelText('Delete conversation Inbound bookings leader'));
    const dialog = screen.getByTestId('ai-delete-confirm-dialog');
    expect(dialog).toHaveAttribute('role', 'dialog');
    expect(dialog).toHaveAttribute('aria-modal', 'true');
    expect(dialog).toHaveTextContent('Delete "Inbound bookings leader"?');

    // Clicking New while delete confirmation dialog is open MUST NOT dismiss confirmation
    fireEvent.click(screen.getByRole('button', { name: 'New' }));
    expect(screen.getByTestId('ai-delete-confirm-dialog')).toBeInTheDocument();

    // Pressing Escape closes ONLY the delete dialog, keeping the Recent chats drawer open
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByTestId('ai-delete-confirm-dialog')).not.toBeInTheDocument();
    expect(screen.getByTestId('ai-recent-chats-panel')).toBeInTheDocument();

    // Cancel button also closes cleanly without calling DELETE
    fireEvent.click(screen.getByLabelText('Delete conversation Inbound bookings leader'));
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(screen.queryByTestId('ai-delete-confirm-dialog')).not.toBeInTheDocument();
    expect(
      mockedApiFetch.mock.calls.filter(
        (c) => c[0] === '/api/ai/conversations/conv-a' && (c[1] as { method?: string })?.method === 'DELETE',
      ),
    ).toHaveLength(0);

    // Failed delete retains item and shows accessible alert
    shouldFailDelete = true;
    fireEvent.click(screen.getByLabelText('Delete conversation Inbound bookings leader'));
    fireEvent.click(screen.getByRole('button', { name: 'Delete chat' }));
    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent('Could not delete this conversation');
    });
    expect(screen.getByTestId('ai-recent-chat-conv-a')).toBeInTheDocument();

    // Confirm delete calls DELETE, removes row, and resets active chat to fresh draft
    shouldFailDelete = false;
    fireEvent.click(screen.getByLabelText('Delete conversation Inbound bookings leader'));
    fireEvent.click(screen.getByRole('button', { name: 'Delete chat' }));

    await waitFor(() => {
      expect(mockedApiFetch).toHaveBeenCalledWith(
        '/api/ai/conversations/conv-a',
        expect.objectContaining({ method: 'DELETE' }),
      );
    });
    await waitFor(() => {
      expect(screen.queryByTestId('ai-recent-chat-conv-a')).not.toBeInTheDocument();
    });
    expect(screen.getByTestId('ai-session-draft-badge')).toHaveTextContent('New draft · fresh context');
  });

  it('resumes saved conversation from URL & sessionStorage, renders failed-turn Retry, and handles 404 safely', async () => {
    const convDetail = {
      success: true,
      message: 'Loaded',
      data: {
        conversation_id: 'conv-resume',
        owner_user_id: 'mgr-1',
        title: 'Inbound score check',
        status: 'active',
        context_version: 2,
        confirmed_context: { function: 'Call Center', team: 'Inbound', month: 'August', year: 2026 },
        pending_clarification: null,
        has_restricted_turns: false,
        created_at: '2026-09-01T10:00:00Z',
        updated_at: '2026-09-01T10:02:00Z',
        turns: [
          {
            turn_id: 'turn-1',
            turn_index: 1,
            status: 'completed',
            user_prompt: 'What is Inbound score in August?',
            error_message: null,
            scope_used: 'Call Center · Inbound',
            period_used: 'August 2026',
            created_at: '2026-09-01T10:00:00Z',
            completed_at: '2026-09-01T10:00:05Z',
            response: CHAT_RESPONSE.data,
          },
          {
            turn_id: 'turn-2',
            client_request_id: 'original-retry-id',
            retry_settings: {
              session_state: { team: 'Inbound', month: 'August', year: 2026 },
              answer_detail: 'details',
            },
            turn_index: 2,
            status: 'failed',
            user_prompt: 'Why did it drop?',
            error_message: 'AI provider temporarily unavailable.',
            scope_used: null,
            period_used: null,
            created_at: '2026-09-01T10:01:00Z',
            completed_at: null,
            response: null,
          },
        ],
      },
    };

    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/ai/conversations?origin=legacy')) {
        return { success: true, message: 'Loaded', conversations: [] };
      }
      if (path.startsWith('/api/ai/conversations?origin=workspace')) {
        return {
          success: true,
          message: 'Loaded',
          conversations: [
            {
              conversation_id: 'conv-resume',
              origin: 'workspace',
              title: 'Inbound score check',
              created_at: '2026-09-01T10:00:00Z',
              updated_at: '2026-09-01T10:02:00Z',
              turn_count: 2,
              last_outcome: 'failed',
              last_scope_banner: 'Call Center · Inbound',
              last_period: 'August 2026',
              has_restricted_turns: false,
              context_version: 2,
            },
          ],
        };
      }
      if (path.startsWith('/api/ai/conversations/conv-resume')) {
        return convDetail;
      }
      if (path.startsWith('/api/ai/conversations/conv-missing')) {
        throw new Error('HTTP 404: Conversation not found.');
      }
      if (path === '/api/ai/chat') {
        return { ...CHAT_RESPONSE, data: { ...CHAT_RESPONSE.data, conversation_id: 'conv-resume' } };
      }
      return { success: true };
    });

    // 1. Resume via ?conversation=conv-resume
    const firstRender = renderWorkspace('/ai?conversation=conv-resume');
    await waitFor(() => {
      expect(screen.getByText('What is Inbound score in August?')).toBeInTheDocument();
    });
    expect(screen.getByText('Why did it drop?')).toBeInTheDocument();
    expect(screen.getByText('AI provider temporarily unavailable.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
    expect(sessionStorage.getItem('pms_ai_last_conversation_mgr-1')).toBe('conv-resume');
    firstRender.unmount();

    // 2. Reopen /ai with no query param -> restores from per-user sessionStorage
    const secondRender = renderWorkspace('/ai');
    await waitFor(() => {
      expect(screen.getByText('What is Inbound score in August?')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /Retry/i }));
    await waitFor(() => {
      const retry = mockedApiFetch.mock.calls.find(([route]) => route === '/api/ai/chat');
      expect(JSON.parse(String(retry?.[1]?.body))).toMatchObject({
        client_request_id: 'original-retry-id',
        conversation_id: 'conv-resume',
        session_state: { team: 'Inbound', month: 'August', year: 2026 },
        answer_detail: 'details',
      });
    });
    secondRender.unmount();

    // 3. Missing / unauthorized conversation -> non-leaking notice & fallback to empty draft
    sessionStorage.clear();
    renderWorkspace('/ai?conversation=conv-missing');
    await waitFor(() => {
      expect(screen.getByRole('status')).toHaveTextContent(
        'This chat is not available in PMS AI. Open it from its original assistant or select it under Older chats.',
      );
    });
    expect(screen.getByText(/Hi Salma, how can I help\?/i)).toBeInTheDocument();
  });

  it('renders restricted historical turns without leaking revoked scope or citations', async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/ai/conversations?origin=legacy')) {
        return { success: true, message: 'Loaded', conversations: [] };
      }
      if (path.startsWith('/api/ai/conversations?origin=workspace')) {
        return {
          success: true,
          message: 'Loaded',
          conversations: [
            {
              conversation_id: 'conv-revoked',
              origin: 'workspace',
              title: 'Restricted conversation',
              created_at: '2026-09-01T10:00:00Z',
              updated_at: '2026-09-01T10:05:00Z',
              turn_count: 1,
              last_outcome: 'restricted_access',
              last_scope_banner: null,
              last_period: null,
              has_restricted_turns: true,
              context_version: 1,
            },
          ],
        };
      }
      if (path.startsWith('/api/ai/conversations/conv-revoked')) {
        return {
          success: true,
          message: 'Loaded',
          data: {
            conversation_id: 'conv-revoked',
            owner_user_id: 'mgr-1',
            title: 'Restricted conversation',
            status: 'active',
            context_version: 1,
            confirmed_context: {},
            pending_clarification: null,
            has_restricted_turns: true,
            created_at: '2026-09-01T10:00:00Z',
            updated_at: '2026-09-01T10:05:00Z',
            turns: [
              {
                turn_id: 'turn-r1',
                turn_index: 1,
                status: 'restricted',
                user_prompt: 'Restricted question (scope no longer authorized)',
                error_message: null,
                scope_used: null,
                period_used: null,
                created_at: '2026-09-01T10:00:00Z',
                completed_at: '2026-09-01T10:00:03Z',
                response: {
                  ...CHAT_RESPONSE.data,
                  outcome: 'restricted_access',
                  headline:
                    'This historical answer is hidden because your current permissions no longer include its data scope.',
                  narrative_bullets: [],
                  visual_cards: [],
                  citations: [],
                  deep_links: [],
                  primary_source_link: null,
                  suggested_followups: [],
                  scope_banner: null,
                },
              },
            ],
          },
        };
      }
      return { success: true };
    });

    renderWorkspace('/ai?conversation=conv-revoked');

    await waitFor(() => {
      expect(
        screen.getByText(
          'This historical answer is hidden because your current permissions no longer include its data scope.',
        ),
      ).toBeInTheDocument();
    });
    expect(screen.getByText('Restricted question (scope no longer authorized)')).toBeInTheDocument();
    expect(screen.queryByText(/Sharjah|96\.4%/)).not.toBeInTheDocument();
  });

  it('keeps in-flight request alive across New chat switching without aborting or leaking responses', async () => {
    let resolveChatA!: (value: unknown) => void;
    let chatASignal: AbortSignal | undefined;

    mockedApiFetch.mockImplementation((path: string, init?: RequestInit) => {
      if (path.startsWith('/api/ai/conversations?')) {
        return Promise.resolve({ success: true, message: 'Loaded', conversations: [] });
      }
      if (path === '/api/ai/chat') {
        const parsed = JSON.parse(String(init?.body || '{}'));
        if (parsed.prompt === 'Slow question in Chat A') {
          chatASignal = init?.signal ?? undefined;
          return new Promise((resolve) => {
            resolveChatA = resolve;
          });
        }
        return Promise.resolve({
          ...CHAT_RESPONSE,
          data: {
            ...CHAT_RESPONSE.data,
            conversation_id: 'conv-chat-b',
            context_version: 1,
            headline: 'Chat B completed cleanly.',
          },
        });
      }
      return Promise.resolve({ success: true });
    });

    renderWorkspace('/ai?function=Call%20Center');

    const input = screen.getByRole('textbox');
    fireEvent.change(input, { target: { value: 'Slow question in Chat A' } });
    fireEvent.click(screen.getByLabelText('Send prompt'));

    await waitFor(() => {
      expect(screen.getByText('Slow question in Chat A')).toBeInTheDocument();
    });

    // Switch to New chat while Chat A is still in-flight
    fireEvent.click(screen.getByTestId('ai-new-chat-btn'));

    // Chat A was NOT aborted
    expect(chatASignal?.aborted).toBe(false);

    // Chat B composer is enabled and can run independently
    const inputB = screen.getByRole('textbox');
    expect(inputB).not.toBeDisabled();
    fireEvent.change(inputB, { target: { value: 'Fast question in Chat B' } });
    fireEvent.click(screen.getByLabelText('Send prompt'));

    await waitFor(() => {
      expect(screen.getByText('Chat B completed cleanly.')).toBeInTheDocument();
    });

    // Now Chat A completes in background -> Chat B stream must NOT be overwritten
    resolveChatA({
      ...CHAT_RESPONSE,
      data: {
        ...CHAT_RESPONSE.data,
        conversation_id: 'conv-chat-a',
        context_version: 1,
        headline: 'Chat A resolved in background.',
      },
    });

    await waitFor(() => {
      const convListCalls = mockedApiFetch.mock.calls.filter(
        (c) => String(c[0]).startsWith('/api/ai/conversations?origin=workspace'),
      );
      expect(convListCalls.length).toBe(3);
    });
    expect(screen.getByText('Chat B completed cleanly.')).toBeInTheDocument();
    expect(screen.queryByText('Chat A resolved in background.')).not.toBeInTheDocument();
  });

  it('renders conversation-first new-chat screen with <= 3 starters, Guardrails Info popover, mobile Filters toggle, and Escape-dismissible history drawer', async () => {
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/ai/conversations?origin=legacy')) {
        return { success: true, message: 'OK', conversations: [] };
      }
      if (path.startsWith('/api/ai/conversations?origin=workspace')) {
        return {
          success: true,
          message: 'OK',
          conversations: [
            {
              conversation_id: 'conv-drawer-1',
              title: 'Inbound bookings check',
              created_at: '2026-09-01T10:00:00Z',
              updated_at: '2026-09-01T10:05:00Z',
              turn_count: 1,
              last_outcome: 'answer',
              last_scope_banner: 'Call Center · Inbound',
              last_period: 'September 2026',
              has_restricted_turns: false,
              context_version: 1,
            },
          ],
        };
      }
      if (path.startsWith('/api/ai/watching')) {
        return WATCHING_RESPONSE;
      }
      return { success: true };
    });

    renderWorkspace('/ai?function=Call%20Center');

    // New-chat greeting displays at most 3 starter suggestions and no category tablist
    const starterGrid = screen.getByTestId('ai-starter-suggestions');
    expect(starterGrid.querySelectorAll('button').length).toBeLessThanOrEqual(3);
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();

    // Mobile Filters toggle updates aria-expanded cleanly
    const filtersToggle = screen.getByRole('button', { name: 'Show scope filters' });
    expect(filtersToggle).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(filtersToggle);
    expect(screen.getByRole('button', { name: 'Hide scope filters' })).toHaveAttribute(
      'aria-expanded',
      'true',
    );

    // Guardrails Info button opens accessible dialog constrained to container width and closes on Escape
    const infoBtn = screen.getByRole('button', { name: 'How PMS AI protects data' });
    fireEvent.click(infoBtn);
    const guardrailsDialog = screen.getByRole('dialog', { name: 'How PMS AI protects data' });
    expect(guardrailsDialog).toBeInTheDocument();
    expect(guardrailsDialog).toHaveClass('max-w-[calc(100%-2rem)]');
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(
      screen.queryByRole('dialog', { name: 'How PMS AI protects data' }),
    ).not.toBeInTheDocument();

    // Recent chats drawer opens via toggle and closes cleanly via Escape key
    fireEvent.click(screen.getByTestId('ai-history-toggle'));
    await waitFor(() => {
      expect(screen.getByTestId('ai-recent-chats-panel')).toBeInTheDocument();
    });
    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => {
      expect(screen.queryByTestId('ai-recent-chats-panel')).not.toBeInTheDocument();
    });
  });

  it('does not inherit previous conversation confirmed context in New chat, sends origin=workspace, and clears Active badge on saved chats', async () => {
    let chatTurn = 0;
    mockedApiFetch.mockImplementation(async (path: string) => {
      if (path.startsWith('/api/ai/conversations?origin=legacy')) {
        return { success: true, message: 'Loaded', conversations: [] };
      }
      if (path.startsWith('/api/ai/conversations?origin=workspace')) {
        return {
          success: true,
          message: 'Loaded',
          conversations: [
            {
              conversation_id: 'conv-prev',
              origin: 'workspace',
              title: 'Previous Inbound check',
              turn_count: 1,
              has_restricted_turns: false,
              context_version: 2,
            },
          ],
        };
      }
      if (path.startsWith('/api/ai/conversations/conv-prev')) {
        return {
          success: true,
          message: 'Loaded',
          data: {
            conversation_id: 'conv-prev',
            origin: 'workspace',
            owner_user_id: 'mgr-1',
            title: 'Previous Inbound check',
            status: 'active',
            context_version: 2,
            confirmed_context: {
              intent: 'ranking',
              function: 'Call Center',
              team: 'Inbound',
              metric_id: 'inbound:booking_cr',
              periods: ['2026-08'],
            },
            has_restricted_turns: false,
            turns: [
              {
                turn_id: 't1',
                turn_index: 1,
                status: 'completed',
                user_prompt: 'Who is top in Inbound?',
                response: CHAT_RESPONSE.data,
              },
            ],
          },
        };
      }
      if (path === '/api/ai/chat') {
        chatTurn += 1;
        return {
          ...CHAT_RESPONSE,
          data: {
            ...CHAT_RESPONSE.data,
            conversation_id: `conv-new-${chatTurn}`,
            headline: 'Fresh new chat response.',
          },
        };
      }
      return { success: true };
    });

    renderWorkspace('/ai?conversation=conv-prev');

    await waitFor(() => {
      expect(screen.getByText('Who is top in Inbound?')).toBeInTheDocument();
    });

    // Open Recent chats to verify Active badge is on conv-prev
    fireEvent.click(screen.getByTestId('ai-history-toggle'));
    expect(screen.getByTestId('ai-recent-chat-active-conv-prev')).toBeInTheDocument();

    // Start New chat -> clears Active badge on saved items and resets lastConfirmedQuery to null
    fireEvent.click(screen.getByTestId('ai-new-chat-btn'));
    expect(screen.queryByTestId('ai-recent-chat-active-conv-prev')).not.toBeInTheDocument();
    expect(screen.getByTestId('ai-session-draft-badge')).toHaveTextContent('New draft · fresh context');

    const input = screen.getByLabelText('Ask PMS AI a question');
    fireEvent.change(input, { target: { value: 'What is Outbound score?' } });
    fireEvent.click(screen.getByLabelText('Send prompt'));

    await waitFor(() => {
      expect(screen.getByText('Fresh new chat response.')).toBeInTheDocument();
    });

    const chatCalls = mockedApiFetch.mock.calls.filter((call) => call[0] === '/api/ai/chat');
    expect(chatCalls).toHaveLength(1);
    const body = JSON.parse(String(chatCalls[0][1]?.body || '{}'));
    expect(body.origin).toBe('workspace');
    expect(body.session_state.last_confirmed_query).toBeNull();
  });

  it('prevents a slow in-flight conversation list fetch started before DELETE from reinserting a deleted conversation', async () => {
    let listCallCount = 0;
    let resolveSlowRefresh!: (val: unknown) => void;
    const convA = {
      conversation_id: 'conv-a',
      title: 'Slow race chat A',
      turn_count: 1,
      has_restricted_turns: false,
      context_version: 1,
    };
    const convB = {
      conversation_id: 'conv-b',
      title: 'Retained chat B',
      turn_count: 1,
      has_restricted_turns: false,
      context_version: 1,
    };

    mockedApiFetch.mockImplementation((path: string, init?: { method?: string }) => {
      if (path.startsWith('/api/ai/conversations?origin=legacy')) {
        return Promise.resolve({ success: true, message: 'Loaded', conversations: [] });
      }
      if (path.startsWith('/api/ai/conversations?origin=workspace')) {
        listCallCount += 1;
        if (listCallCount === 1) {
          return Promise.resolve({ success: true, message: 'Loaded', conversations: [convA, convB] });
        }
        // Second refresh (triggered by sending a chat turn) stays in flight while DELETE runs
        return new Promise((resolve) => {
          resolveSlowRefresh = resolve;
        });
      }
      if (path === '/api/ai/conversations/conv-a' && init?.method === 'DELETE') {
        return Promise.resolve({ success: true, message: 'Deleted' });
      }
      if (path === '/api/ai/chat') {
        return Promise.resolve({
          ...CHAT_RESPONSE,
          data: {
            ...CHAT_RESPONSE.data,
            conversation_id: 'conv-b',
            headline: 'Turn completed in conv-b.',
          },
        });
      }
      return Promise.resolve({ success: true });
    });

    renderWorkspace('/ai');

    fireEvent.click(screen.getByTestId('ai-history-toggle'));
    await waitFor(() => {
      expect(screen.getByTestId('ai-recent-chat-conv-a')).toBeInTheDocument();
    });

    // Trigger a chat turn so refreshRecentConversations() starts a slow in-flight GET (call #2)
    const input = screen.getByLabelText('Ask PMS AI a question');
    fireEvent.change(input, { target: { value: 'Check Outbound' } });
    fireEvent.click(screen.getByLabelText('Send prompt'));

    await waitFor(() => {
      expect(listCallCount).toBe(2);
    });

    // While GET #2 is still in flight, delete conv-a
    fireEvent.click(screen.getByLabelText('Delete conversation Slow race chat A'));
    fireEvent.click(screen.getByRole('button', { name: 'Delete chat' }));

    await waitFor(() => {
      expect(screen.queryByTestId('ai-recent-chat-conv-a')).not.toBeInTheDocument();
    });

    // Now the stale in-flight GET #2 resolves with [convA, convB] -> convA must NOT reappear
    resolveSlowRefresh({
      success: true,
      message: 'Loaded',
      conversations: [convA, convB],
    });

    await waitFor(() => {
      expect(screen.getByTestId('ai-recent-chat-conv-b')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('ai-recent-chat-conv-a')).not.toBeInTheDocument();
  });

  it('lists legacy chats in Older section and promotes on select or URL resume', async () => {
    let promoted = false;
    mockedApiFetch.mockImplementation(async (path: string, init?: { method?: string }) => {
      if (path.startsWith('/api/ai/conversations?origin=workspace')) {
        return {
          success: true,
          message: 'Loaded',
          conversations: promoted
            ? [
                {
                  conversation_id: 'conv-legacy-1',
                  origin: 'workspace',
                  title: 'Pre-origin chat',
                  turn_count: 1,
                  has_restricted_turns: false,
                  context_version: 1,
                },
              ]
            : [],
        };
      }
      if (path.startsWith('/api/ai/conversations?origin=legacy')) {
        return {
          success: true,
          message: 'Loaded',
          conversations: promoted
            ? []
            : [
                {
                  conversation_id: 'conv-legacy-1',
                  origin: 'legacy',
                  title: 'Pre-origin chat',
                  turn_count: 1,
                  has_restricted_turns: false,
                  context_version: 1,
                },
              ],
        };
      }
      if (path === '/api/ai/conversations/conv-legacy-1/promote' && init?.method === 'POST') {
        promoted = true;
        return {
          success: true,
          message: 'Promoted',
          data: { conversation_id: 'conv-legacy-1', origin: 'workspace' },
        };
      }
      if (path === '/api/ai/conversations/conv-legacy-1?origin=legacy') {
        return {
          success: true,
          message: 'Loaded',
          data: {
            conversation_id: 'conv-legacy-1',
            origin: 'legacy',
            owner_user_id: 'mgr-1',
            title: 'Pre-origin chat',
            status: 'active',
            context_version: 1,
            confirmed_context: {},
            has_restricted_turns: false,
            turns: [
              {
                turn_id: 't-leg-1',
                turn_index: 1,
                status: 'completed',
                user_prompt: 'Old workspace prompt',
                response: CHAT_RESPONSE.data,
              },
            ],
          },
        };
      }
      return { success: true };
    });

    renderWorkspace('/ai');

    fireEvent.click(screen.getByTestId('ai-history-toggle'));
    await waitFor(() => {
      expect(screen.getByTestId('ai-legacy-chat-section')).toBeInTheDocument();
      expect(screen.getByTestId('ai-recent-chat-conv-legacy-1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Pre-origin chat'));
    await waitFor(() => {
      expect(mockedApiFetch).toHaveBeenCalledWith(
        '/api/ai/conversations/conv-legacy-1/promote',
        expect.objectContaining({ method: 'POST' }),
      );
      expect(screen.getByText('Old workspace prompt')).toBeInTheDocument();
      expect(screen.queryByTestId('ai-legacy-chat-section')).not.toBeInTheDocument();
    });
  });
});
