import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { AiFeedbackLearningPanel } from './AiFeedbackLearningPanel';
import { apiFetch } from '../../lib/apiClient';

vi.mock('../../lib/apiClient', () => ({
  apiFetch: vi.fn(),
}));

const mockedApiFetch = vi.mocked(apiFetch);

const SAMPLE_CLUSTERS = {
  success: true,
  total_traces: 2,
  clusters: [
    {
      surface: 'workspace_chat',
      fallback_reason: 'none',
      operation_family: 'current_value',
      scope_team: 'Inbound',
      reason_tag: 'misunderstood_question',
      intent: 'current_value',
      failure_category: 'misunderstood_question',
      total_count: 2,
      up_count: 0,
      down_count: 2,
      pending_count: 2,
      approved_count: 0,
      rejected_count: 0,
      traces: [
        {
          trace_id: 'trace-111',
          prompt_redacted: 'Who holds the Inbound mvp badge in September 2026?',
          intent: 'current_value',
          operation_kind: 'current_value',
          tool_choice: 'get_team_scorecard',
          rating: 'down',
          failure_category: 'misunderstood_question',
          feedback_reason: 'Expected top agent ranking',
          review_status: 'pending',
          reviewer_verified: false,
          created_at: '2026-11-15T10:00:00Z',
        },
      ],
    },
  ],
};

const SAMPLE_PATTERNS = {
  success: true,
  patterns: [
    {
      id: 'pat-99',
      source_trace_id: 'trace-000',
      normalized_pattern: 'mvp badge <TEAM> <MONTH> <YEAR>',
      example_prompt_redacted: 'Which Inbound rep earned the mvp badge?',
      intent: 'ranking',
      operation_kind: 'ranking',
      requested_parts: ['ranking'],
      tool_choice: 'get_team_rankings',
      metric_hint: null,
      failure_category: 'misunderstood_question',
      verified_against_pms: true,
      approved_by_user_id: 'admin-1',
      review_notes: 'Verified against Monthly Presentation',
      is_active: true,
      created_at: '2026-11-15T09:00:00Z',
    },
  ],
};

describe('AiFeedbackLearningPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows loading skeleton then loads clusters, enforces PMS verification gate, and approves pattern', async () => {
    let resolveClusters: (val: unknown) => void = () => {};
    const pendingClusters = new Promise((res) => {
      resolveClusters = res;
    });

    mockedApiFetch.mockImplementation((path: string, init?: RequestInit) => {
      if (path.startsWith('/api/ai/feedback/clusters')) {
        return pendingClusters as Promise<unknown>;
      }
      if (path === '/api/ai/feedback/patterns') {
        return Promise.resolve(SAMPLE_PATTERNS);
      }
      if (path === '/api/ai/traces/trace-111/approve-pattern' && init?.method === 'POST') {
        return Promise.resolve({
          success: true,
          message: 'Pattern verified against live PMS data and saved',
          pattern: {
            ...SAMPLE_PATTERNS.patterns[0],
            id: 'pat-100',
            source_trace_id: 'trace-111',
          },
          trace_review: {
            success: true,
            trace_id: 'trace-111',
            decision: 'approved',
            review_status: 'approved',
            reviewer_verified: true,
            is_distillation_eligible: true,
            reviewer_id: 'admin-1',
          },
        });
      }
      return Promise.resolve({ success: true });
    });

    render(<AiFeedbackLearningPanel />);

    // Loading skeleton visible before data resolves
    expect(screen.getByLabelText('Loading AI feedback clusters')).toBeInTheDocument();

    resolveClusters(SAMPLE_CLUSTERS);

    await waitFor(() => {
      expect(screen.getByText('Who holds the Inbound mvp badge in September 2026?')).toBeInTheDocument();
    });

    // Inspect cluster -> Approve & save pattern disabled until PMS checkbox checked
    fireEvent.click(screen.getByRole('button', { name: /Inspect/i }));
    const approveBtn = screen.getByRole('button', { name: /Approve & save pattern/i });
    expect(approveBtn).toBeDisabled();

    fireEvent.click(screen.getByLabelText('I verified this behavior against live PMS data'));
    expect(approveBtn).toBeEnabled();

    fireEvent.click(approveBtn);

    await waitFor(() => {
      expect(mockedApiFetch).toHaveBeenCalledWith(
        '/api/ai/traces/trace-111/approve-pattern',
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('"verified_against_pms":true'),
        }),
      );
    });
  });

  it('requires inline confirmation before removing an active pattern and handles load errors with retry', async () => {
    mockedApiFetch
      .mockRejectedValueOnce(new Error('Network error'))
      .mockImplementation((path: string, init?: RequestInit) => {
        if (path.startsWith('/api/ai/feedback/clusters')) {
          return Promise.resolve({ success: true, total_traces: 0, clusters: [] });
        }
        if (path === '/api/ai/feedback/patterns') {
          return Promise.resolve(SAMPLE_PATTERNS);
        }
        if (path === '/api/ai/feedback/patterns/pat-99' && init?.method === 'DELETE') {
          return Promise.resolve({ success: true, pattern_id: 'pat-99' });
        }
        return Promise.resolve({ success: true });
      });

    render(<AiFeedbackLearningPanel />);

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Unable to load AI feedback clusters and approved patterns.');

    fireEvent.click(screen.getByRole('button', { name: /Retry/i }));

    const card = await screen.findByTestId('ai-approved-pattern-pat-99');
    expect(card).toBeInTheDocument();

    // Two-step remove confirmation
    fireEvent.click(screen.getByRole('button', { name: /^Remove$/i }));
    expect(mockedApiFetch).not.toHaveBeenCalledWith(
      '/api/ai/feedback/patterns/pat-99',
      expect.anything(),
    );

    fireEvent.click(screen.getByRole('button', { name: /Confirm remove/i }));

    await waitFor(() => {
      expect(mockedApiFetch).toHaveBeenCalledWith(
        '/api/ai/feedback/patterns/pat-99',
        expect.objectContaining({ method: 'DELETE' }),
      );
    });
  });
});
