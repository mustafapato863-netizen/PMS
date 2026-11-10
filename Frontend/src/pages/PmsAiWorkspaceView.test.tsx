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

    expect(screen.getByText('Which Call Center team dropped most?')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Which Call Center team dropped most?'));

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
    fireEvent.click(screen.getByText('Which Call Center team dropped most?'));
    const useful = await screen.findByLabelText('Mark response as useful');
    fireEvent.click(useful);
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save feedback');
    expect(screen.queryByText('Feedback saved')).not.toBeInTheDocument();
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

    fireEvent.click(screen.getByText('Which Call Center team dropped most?'));

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

  it('cancels in-flight requests on scope filter change and clears incompatible confirmed context', async () => {
    let resolveDelayedTurn: ((val: unknown) => void) | null = null;
    let chatCallIdx = 0;

    mockedApiFetch.mockImplementation(async (path: string) => {
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
    const teamDropdownBtn = screen.getByLabelText('Filter Call Center Team');
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
      if (path === '/api/ai/conversations/conv-stale/context') {
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

    renderWorkspace('/ai');

    // With multiple catalog functions, Department dropdown is rendered once catalog query resolves
    const deptBtn = await screen.findByLabelText('Filter Department');
    expect(deptBtn).toBeInTheDocument();

    // Both department and team filter dropdowns default to neutral "All authorized departments"
    expect(screen.getAllByText('All authorized departments').length).toBeGreaterThanOrEqual(2);

    // Select Department: Operations
    fireEvent.click(deptBtn);
    await waitFor(() => {
      expect(screen.getByRole('option', { name: /Operations/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('option', { name: /Operations/i }));

    // Send a prompt and verify the request session state includes function='Operations'
    const input = screen.getByLabelText('Ask PMS AI a question');
    fireEvent.change(input, { target: { value: 'What is Operations performance?' } });
    fireEvent.click(screen.getByLabelText('Send prompt'));

    await waitFor(() => {
      const chatCalls = mockedApiFetch.mock.calls.filter((call) => call[0] === '/api/ai/chat');
      expect(chatCalls.length).toBeGreaterThan(0);
      const reqBody = JSON.parse(String(chatCalls[0][1]?.body || '{}'));
      expect(reqBody.session_state.function).toBe('Operations');
    });
  });
});
