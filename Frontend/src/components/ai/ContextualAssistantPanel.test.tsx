import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import { ContextualAssistantPanel } from './ContextualAssistantPanel';
import type { PageContextV1 } from '../../features/ai/types';

const mockApiFetch = vi.fn();
let mockRole = 'Manager';
let mockUserId = 'user-manager-1';

vi.mock('../../lib/apiClient', () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
}));

vi.mock('../../context/RoleContext', () => ({
  useUserRole: () => ({ role: mockRole }),
}));

vi.mock('../../context/auth', () => ({
  useAuth: () => ({
    currentUser: {
      id: mockUserId,
      username: 'manager',
      role: mockRole,
    },
  }),
}));

const basePageContext: PageContextV1 = {
  page_id: 'monthly_presentation',
  route_id: '/monthly-presentation?region=egy&deepDive=call-center&team=inbound',
  region: 'EGY',
  period: '2026-09',
  month: 'September',
  year: 2026,
  function_id: 'Call Center',
  team_id: 'Inbound',
  selected_metric_id: 'Booking Rate',
  is_fallback_data: false,
};

describe('ContextualAssistantPanel', () => {
  beforeEach(() => {
    mockApiFetch.mockReset();
    mockRole = 'Admin';
    mockUserId = 'user-admin-1';
  });

  it('hides every entry point for non-admin roles even when AI is marked available', () => {
    for (const role of ['Manager', 'Employee', 'General Manager', 'Executive', 'Performance Team', 'Function Viewer']) {
      mockRole = role;
      const view = render(
        <MemoryRouter>
          <ContextualAssistantPanel pageContext={basePageContext} />
        </MemoryRouter>,
      );
      expect(screen.queryByTestId('contextual-assistant-root')).not.toBeInTheDocument();
      expect(screen.queryByTestId('contextual-assistant-launcher')).not.toBeInTheDocument();
      view.unmount();
    }
  });

  it('opens the panel and displays the active page context banner and starter prompts', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ContextualAssistantPanel pageContext={basePageContext} />
      </MemoryRouter>,
    );

    await user.click(screen.getByTestId('contextual-assistant-launcher'));

    expect(screen.getByTestId('contextual-assistant-panel')).toBeInTheDocument();
    expect(screen.getByTestId('contextual-assistant-scope-banner')).toHaveTextContent(
      'Monthly Presentation · Inbound · September 2026 · Booking Rate',
    );
    expect(screen.getByText('Explain this page')).toBeInTheDocument();
  });

  it('displays the fallback sample data warning when is_fallback_data is true', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ContextualAssistantPanel
          pageContext={{ ...basePageContext, is_fallback_data: true }}
        />
      </MemoryRouter>,
    );

    await user.click(screen.getByTestId('contextual-assistant-launcher'));

    expect(screen.getByTestId('contextual-assistant-fallback-warning')).toHaveTextContent(
      'Fallback sample data is displayed on this view',
    );
  });

  it('allows authorized users to review a corrective action proposal, cancel without saving, or save as Open', async () => {
    const user = userEvent.setup();
    const onActionSaved = vi.fn();

    mockApiFetch.mockImplementation(async (endpoint: string) => {
      if (endpoint === '/api/ai/chat') {
        return {
          success: true,
          data: {
            trace_id: 'trace-proposal-1',
            conversation_id: 'conv-1',
            turn_id: 'turn-1',
            outcome: 'answer',
            capability_mode: 'proposal',
            headline: 'In September 2026, Booking Rate is 42.1% vs 45.0% target (2.9 pts gap).',
            narrative_bullets: [],
            visual_cards: [],
            citations: [],
            deep_links: [],
            suggested_followups: [],
            resolved_session_state: {
              function: 'Call Center',
              team: 'Inbound',
              performance_level: 'Employee',
              month: 'September',
              year: 2026,
            },
            effective_context_label: 'Monthly Presentation · Inbound · September 2026 · Booking Rate',
            domain_guardrail_notes: [],
            tool_calls: [
              {
                tool_name: 'get_kpi_score_drivers',
                arguments: {},
                records_evaluated: 8,
              },
            ],
            provider_used: 'deterministic',
            model_used: 'pms-deterministic-v1',
            latency_ms: 12,
            action_proposal: {
              proposal_id: 'prop-123',
              title: 'Booking Rate Coaching Plan',
              scope_summary: 'Inbound · September 2026',
              team: 'Inbound',
              function: 'Call Center',
              performance_level: 'Employee',
              period: '2026-09',
              month: 'September',
              year: 2026,
              employee_id: null,
              employee_name: null,
              metric_id: 'Booking',
              linked_kpi_key: 'Booking',
              metric_display_name: 'Booking Rate',
              actual_display: '42.1%',
              target_display: '45.0%',
              gap_display: '-2.9 pts',
              sample_size: 8,
              observed_facts: ['Booking Rate is 42.1% vs 45.0% target (-2.9 pts gap).'],
              hypothesis:
                'Verify through call audit and QA sampling whether objection handling contributed to the Booking Rate gap.',
              suggested_steps: ['Review call recordings with agents below target.'],
              success_measure: 'Reach >= 45.0% Booking Rate in next published period.',
              action_type: 'Coaching',
              priority: 'High',
              proposed_action_text:
                'Review Booking Rate performance (42.1% vs 45.0% target) and conduct targeted coaching.',
              proposed_root_cause_note:
                'Observed KPI gap on Booking Rate (42.1% vs 45.0% target). Root cause to be verified during coaching review.',
              evidence_revision: 'rev-1',
              can_user_create_action: true,
              persisted_status_on_save: 'Open',
              assignable_owners: [],
            },
          },
        };
      }
      if (endpoint === '/api/ai/proposals/confirm') {
        return {
          success: true,
          message: 'Corrective action saved with status Open.',
          persisted_status: 'Open',
          action_scope: 'team',
          action: { id: 'act-999', status: 'Open' },
        };
      }
      return { success: true };
    });

    render(
      <MemoryRouter>
        <ContextualAssistantPanel
          pageContext={basePageContext}
          onActionSaved={onActionSaved}
        />
      </MemoryRouter>,
    );

    await user.click(screen.getByTestId('contextual-assistant-launcher'));
    await user.click(screen.getByText('Propose a corrective action for Booking Rate'));

    const reviewBtn = await screen.findByTestId('contextual-assistant-review-action-btn');
    expect(reviewBtn).toBeInTheDocument();

    // Open review form and click Cancel -> must NOT call /api/ai/proposals/confirm
    await user.click(reviewBtn);
    expect(screen.getByTestId('contextual-assistant-proposal-form')).toBeInTheDocument();
    await user.click(screen.getByTestId('contextual-assistant-cancel-proposal-btn'));
    expect(screen.queryByTestId('contextual-assistant-proposal-form')).not.toBeInTheDocument();
    expect(
      mockApiFetch.mock.calls.filter((call) => call[0] === '/api/ai/proposals/confirm'),
    ).toHaveLength(0);

    // Re-open review form and confirm save -> calls /api/ai/proposals/confirm and shows Open status
    await user.click(screen.getByTestId('contextual-assistant-review-action-btn'));
    await user.click(screen.getByTestId('contextual-assistant-confirm-proposal-btn'));

    const savedStatus = await screen.findByTestId('contextual-assistant-saved-action-status');
    expect(savedStatus).toHaveTextContent('Saved with status: Open');
    expect(onActionSaved).toHaveBeenCalledTimes(1);
  });

  it('does not render the assistant or call AI for a read-only non-admin', () => {
    mockRole = 'Function Viewer';
    render(
      <MemoryRouter>
        <ContextualAssistantPanel pageContext={basePageContext} />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('contextual-assistant-root')).not.toBeInTheDocument();
    expect(mockApiFetch).not.toHaveBeenCalled();
  });

  it('ignores late responses when pageContext changes mid-request', async () => {
    const user = userEvent.setup();
    let resolveDelayedChat: (val: unknown) => void = () => {};

    mockApiFetch.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveDelayedChat = resolve;
        }),
    );

    const { rerender } = render(
      <MemoryRouter>
        <ContextualAssistantPanel pageContext={basePageContext} />
      </MemoryRouter>,
    );

    await user.click(screen.getByTestId('contextual-assistant-launcher'));
    await user.click(screen.getByText('Explain this page'));

    // Change pageContext while request is still in flight
    rerender(
      <MemoryRouter>
        <ContextualAssistantPanel
          pageContext={{ ...basePageContext, team_id: 'Outbound', selected_metric_id: 'Reachability' }}
        />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('contextual-assistant-scope-banner')).toHaveTextContent(
      'Monthly Presentation · Outbound · September 2026 · Reachability',
    );

    // Resolve the stale Inbound request after context switch
    resolveDelayedChat({
      success: true,
      data: {
        trace_id: 'trace-stale',
        conversation_id: 'conv-stale',
        turn_id: 'turn-stale',
        outcome: 'answer',
        capability_mode: 'page_help',
        headline: 'STALE INBOUND HEADLINE SHOULD NOT RENDER',
        narrative_bullets: [],
        visual_cards: [],
        citations: [],
        deep_links: [],
        suggested_followups: [],
        resolved_session_state: {},
        domain_guardrail_notes: [],
        tool_calls: [],
        provider_used: 'deterministic',
        model_used: 'pms-deterministic-v1',
        latency_ms: 5,
      },
    });

    await waitFor(() => {
      expect(
        screen.queryByText('STALE INBOUND HEADLINE SHOULD NOT RENDER'),
      ).not.toBeInTheDocument();
    });
  });

  it('submits categorized feedback when Not useful is clicked', async () => {
    const user = userEvent.setup();
    mockApiFetch.mockImplementation(async (endpoint: string) => {
      if (endpoint === '/api/ai/chat') {
        return {
          success: true,
          data: {
            trace_id: 'trace-fb-1',
            conversation_id: 'conv-fb',
            turn_id: 'turn-fb',
            outcome: 'answer',
            capability_mode: 'page_help',
            headline: 'Monthly Presentation summarizes performance.',
            narrative_bullets: [],
            visual_cards: [],
            citations: [],
            deep_links: [],
            suggested_followups: [],
            resolved_session_state: {},
            domain_guardrail_notes: [],
            tool_calls: [],
            provider_used: 'deterministic',
            model_used: 'pms-deterministic-v1',
            latency_ms: 5,
          },
        };
      }
      return {
        success: true,
        trace_id: 'trace-fb-1',
        rating: 'down',
        category: 'incorrect_scope',
      };
    });

    render(
      <MemoryRouter>
        <ContextualAssistantPanel pageContext={basePageContext} />
      </MemoryRouter>,
    );

    await user.click(screen.getByTestId('contextual-assistant-launcher'));
    await user.click(screen.getByText('Explain this page'));

    const downBtn = await screen.findByTestId('feedback-down-trace-fb-1');
    await user.click(downBtn);
    await user.click(screen.getByTestId('feedback-cat-trace-fb-1-incorrect_scope'));

    await waitFor(() => {
      const fbCall = mockApiFetch.mock.calls.find((call) => call[0] === '/api/ai/feedback');
      expect(fbCall).toBeDefined();
      expect(JSON.parse(fbCall?.[1]?.body as string)).toMatchObject({
        trace_id: 'trace-fb-1',
        rating: 'down',
        category: 'incorrect_scope',
      });
    });
  });
});
