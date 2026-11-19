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

  it('paginates clusters 10 by 10 and automatically prefetches and caches the next 10 page', async () => {
    const makeCluster = (idx: number) => ({
      ...SAMPLE_CLUSTERS.clusters[0],
      scope_team: `Team-${idx}`,
      traces: [
        {
          ...SAMPLE_CLUSTERS.clusters[0].traces[0],
          trace_id: `trace-${idx}`,
          prompt_redacted: `Cluster prompt #${idx}`,
        },
      ],
    });
    const allClusters = Array.from({ length: 25 }, (_, i) => makeCluster(i + 1));

    const fetchedPages: number[] = [];
    mockedApiFetch.mockImplementation((path: string) => {
      if (path.startsWith('/api/ai/feedback/clusters')) {
        const url = new URL(`http://localhost${path}`);
        const p = Number(url.searchParams.get('page') || '1');
        const ps = Number(url.searchParams.get('page_size') || '10');
        fetchedPages.push(p);
        const start = (p - 1) * ps;
        const slice = allClusters.slice(start, start + ps);
        const totalPages = Math.ceil(allClusters.length / ps);
        return Promise.resolve({
          success: true,
          total_traces: 50,
          total_clusters: allClusters.length,
          pending_total: 25,
          flagged_total: 15,
          page: p,
          page_size: ps,
          total_pages: totalPages,
          has_next: p < totalPages,
          has_prev: p > 1,
          clusters: slice,
        });
      }
      if (path === '/api/ai/feedback/patterns') {
        return Promise.resolve(SAMPLE_PATTERNS);
      }
      return Promise.resolve({ success: true });
    });

    render(<AiFeedbackLearningPanel />);

    // Page 1 shows items 1..10 and automatically prefetches page 2 in background
    expect(await screen.findByText('Cluster prompt #1')).toBeInTheDocument();
    expect(screen.getByText('Cluster prompt #10')).toBeInTheDocument();
    expect(screen.queryByText('Cluster prompt #11')).not.toBeInTheDocument();
    expect(screen.getByText('Showing 1–10 of 25')).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchedPages).toEqual([1, 2]);
      expect(screen.getByTestId('next-page-cached-badge')).toHaveTextContent('Next 10 ready');
    });

    // Click Next 10 -> serves page 2 immediately from cache (NO second fetch for page 2) and prefetches page 3
    fireEvent.click(screen.getByRole('button', { name: /Next 10/i }));

    expect(await screen.findByText('Cluster prompt #11')).toBeInTheDocument();
    expect(screen.getByText('Cluster prompt #20')).toBeInTheDocument();
    expect(screen.getByText('Showing 11–20 of 25')).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchedPages).toEqual([1, 2, 3]);
    });
    // Page 2 was fetched only once (during background prefetch)
    expect(fetchedPages.filter((p) => p === 2)).toHaveLength(1);
  });

  it('runs root-cause diagnosis, applies suggestion to form while keeping PMS verification unchecked', async () => {
    mockedApiFetch.mockImplementation((path: string, init?: RequestInit) => {
      if (path.startsWith('/api/ai/feedback/clusters') && !path.endsWith('/analyze')) {
        return Promise.resolve(SAMPLE_CLUSTERS);
      }
      if (path === '/api/ai/feedback/patterns') {
        return Promise.resolve(SAMPLE_PATTERNS);
      }
      if (path === '/api/ai/feedback/analyzer/status') {
        return Promise.resolve({
          success: true,
          enabled: true,
          configured: true,
          daily_used: 4,
          daily_limit: 50,
        });
      }
      if (path === '/api/ai/traces/trace-111/analyze' && init?.method === 'POST') {
        return Promise.resolve({
          success: true,
          trace_id: 'trace-111',
          outcome: 'analyzed',
          root_cause_category: 'intent_misclassification',
          root_cause_summary: 'MVP badge phrasing was routed to current_value instead of ranking.',
          why_answer_failed: [
            'Router treated mvp badge as a team metric snapshot.',
            'Expected top agent leaderboard for the Inbound team.',
          ],
          recommended_system_fix: 'Map mvp badge phrasing to ranking intent.',
          suggested_pattern: {
            corrected_pattern_prompt: 'Who holds the <TEAM> mvp badge in <MONTH> <YEAR>?',
            intent: 'ranking',
            operation_kind: 'ranking',
            metric_hint: 'final_score',
          },
          confidence: 0.91,
          cached: false,
          quarantine_reasons: [],
        });
      }
      return Promise.resolve({ success: true });
    });

    render(<AiFeedbackLearningPanel />);

    expect(await screen.findByText('Who holds the Inbound mvp badge in September 2026?')).toBeInTheDocument();
    expect(await screen.findByTestId('analyzer-status-pill')).toHaveTextContent('AI Diagnosis: 4 / 50 today');

    fireEvent.click(screen.getByRole('button', { name: /Inspect/i }));
    // First check the PMS checkbox manually to verify Apply Suggestion resets it back to unchecked
    const pmsCheckbox = screen.getByLabelText('I verified this behavior against live PMS data') as HTMLInputElement;
    fireEvent.click(pmsCheckbox);
    expect(pmsCheckbox.checked).toBe(true);

    fireEvent.click(screen.getByRole('button', { name: /Analyze Root Cause/i }));

    const diagnosisCard = await screen.findByTestId('trace-diagnosis-card');
    expect(diagnosisCard).toHaveTextContent('Intent misclassification');
    expect(diagnosisCard).toHaveTextContent('91% confidence');
    expect(diagnosisCard).toHaveTextContent('MVP badge phrasing was routed to current_value instead of ranking.');

    fireEvent.click(screen.getByRole('button', { name: /Apply suggestion to form/i }));

    // Form fields prefilled from suggestion
    expect(screen.getByDisplayValue('Who holds the <TEAM> mvp badge in <MONTH> <YEAR>?')).toBeInTheDocument();
    expect(screen.getByDisplayValue('final_score')).toBeInTheDocument();
    // Critical safety gate: PMS verification checkbox MUST be reset to unchecked
    expect(pmsCheckbox.checked).toBe(false);
    expect(screen.getByRole('button', { name: /Approve & save pattern/i })).toBeDisabled();
  });

  it('displays privacy quarantine notice when trace diagnosis is blocked for residual PII', async () => {
    mockedApiFetch.mockImplementation((path: string, init?: RequestInit) => {
      if (path.startsWith('/api/ai/feedback/clusters') && !path.endsWith('/analyze')) {
        return Promise.resolve(SAMPLE_CLUSTERS);
      }
      if (path === '/api/ai/feedback/patterns') {
        return Promise.resolve(SAMPLE_PATTERNS);
      }
      if (path === '/api/ai/feedback/analyzer/status') {
        return Promise.resolve({
          success: true,
          enabled: true,
          configured: true,
          daily_used: 1,
          daily_limit: 50,
        });
      }
      if (path === '/api/ai/traces/trace-111/analyze' && init?.method === 'POST') {
        return Promise.resolve({
          success: false,
          trace_id: 'trace-111',
          outcome: 'blocked_pii_quarantine',
          why_answer_failed: [],
          confidence: 0,
          cached: false,
          quarantine_reasons: ['residual_email'],
          message: 'Blocked before outbound transmission due to residual PII.',
        });
      }
      return Promise.resolve({ success: true });
    });

    render(<AiFeedbackLearningPanel />);
    expect(await screen.findByTestId('analyzer-status-pill')).toHaveTextContent('AI Diagnosis: 1 / 50 today');

    fireEvent.click(screen.getByRole('button', { name: /Inspect/i }));
    fireEvent.click(screen.getByRole('button', { name: /Analyze Root Cause/i }));

    const diagnosisCard = await screen.findByTestId('trace-diagnosis-card');
    expect(diagnosisCard).toHaveTextContent('Blocked by privacy quarantine — no data left PMS');
    expect(diagnosisCard).toHaveTextContent('residual_email');
  });

  it('summarizes a selected cluster with recurring issues and engineering fixes', async () => {
    mockedApiFetch.mockImplementation((path: string, init?: RequestInit) => {
      if (path.startsWith('/api/ai/feedback/clusters') && !path.endsWith('/analyze')) {
        return Promise.resolve(SAMPLE_CLUSTERS);
      }
      if (path === '/api/ai/feedback/patterns') {
        return Promise.resolve(SAMPLE_PATTERNS);
      }
      if (path === '/api/ai/feedback/analyzer/status') {
        return Promise.resolve({
          success: true,
          enabled: true,
          configured: true,
          daily_used: 2,
          daily_limit: 50,
        });
      }
      if (path === '/api/ai/feedback/clusters/analyze' && init?.method === 'POST') {
        return Promise.resolve({
          success: true,
          outcome: 'analyzed',
          traces_analyzed: 2,
          traces_quarantined: 0,
          primary_root_cause: 'missing_kpi_alias',
          executive_summary: 'Users frequently ask for mvp badge which maps to final_score ranking.',
          recurring_issues: ['mvp badge alias missing from router dictionary'],
          recommended_engineering_fixes: ['Add mvp badge alias to ranking intent patterns'],
          confidence: 0.88,
        });
      }
      return Promise.resolve({ success: true });
    });

    render(<AiFeedbackLearningPanel />);
    expect(await screen.findByTestId('analyzer-status-pill')).toHaveTextContent('AI Diagnosis: 2 / 50 today');

    fireEvent.click(screen.getByRole('button', { name: /Inspect/i }));
    fireEvent.click(screen.getByRole('button', { name: /Summarize Cluster/i }));

    const clusterCard = await screen.findByTestId('cluster-diagnosis-card');
    expect(clusterCard).toHaveTextContent('Missing KPI alias');
    expect(clusterCard).toHaveTextContent('2 traces analyzed');
    expect(clusterCard).toHaveTextContent('mvp badge alias missing from router dictionary');
    expect(clusterCard).toHaveTextContent('Add mvp badge alias to ranking intent patterns');
  });
});
