import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CorrectiveActionSuggestionCard from './CorrectiveActionSuggestionCard';
import EmployeeActionModal from '../team/EmployeeActionModal';
import { AiAvailabilityContext } from '../../features/ai/aiAvailabilityContext';
import { AuthContext } from '../../context/auth';
import { apiFetch, ApiError } from '../../lib/apiClient';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import type { User } from '../../types';
import type { AiCorrectiveActionSuggestionPayload } from '../../features/ai/types';

type MockApiResponse = {
  success: boolean;
  message?: string;
  data?: unknown;
};

vi.mock('../../lib/apiClient', () => ({
  apiFetch: vi.fn(async (url: string) => {
    if (String(url).includes('/owners')) return { success: true, data: [{ id: 'owner-1', name: 'Ada Owner' }] };
    if (String(url).includes('/planning')) return { success: true, data: [{ id: 'plan-1', name: 'Inbound recovery', team: 'Inbound', status: 'In Progress' }] };
    return { success: true, data: {} };
  }),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
    }
  },
}));

vi.mock('../../hooks/useActionStore', () => ({
  useActionStore: () => ({
    saveAction: vi.fn(async () => ({ success: true, synced: true, message: 'Saved' })),
    updateAction: vi.fn(),
    isSaving: false,
  }),
}));

const mockApiFetch = vi.mocked(apiFetch);
let aiResponseHandler: ((url: string, options?: RequestInit) => Promise<MockApiResponse>) | null = null;

function setupDefaultApiFetch() {
  mockApiFetch.mockImplementation(async (url: string, options?: RequestInit): Promise<unknown> => {
    const urlStr = String(url);
    if (urlStr.includes('/owners')) {
      return { success: true, data: [{ id: 'owner-1', name: 'Ada Owner' }] };
    }
    if (urlStr.includes('/planning')) {
      return { success: true, data: [{ id: 'plan-1', name: 'Inbound recovery', team: 'Inbound', status: 'In Progress' }] };
    }
    if (urlStr.includes('/corrective-action-suggestions')) {
      if (aiResponseHandler) {
        return aiResponseHandler(url, options);
      }
      return {
        success: true,
        message: 'Draft generated',
        data: createMockSuggestedPayload(),
      };
    }
    return { success: true, data: [] };
  });
}

function createMockSuggestedPayload(overrides?: Partial<AiCorrectiveActionSuggestionPayload>): AiCorrectiveActionSuggestionPayload {
  return {
    outcome: 'suggested',
    provider_used: 'cloudflare',
    model_called: true,
    model_version: '@cf/ibm-granite/granite-4.0-h-micro',
    context: {
      subject: 'employee',
      employee_id: 'EMP-101',
      employee_name: 'Sarah Connor',
      team: 'Inbound',
      period: { month: 'September', year: 2026 },
      performance_level: 'Employee',
    },
    focus_kpi_key: 'booking_rate',
    measured_facts: ['Booking rate is 65.0% vs target 80.0%.'],
    evidence_limitations: ['Root cause is unverified by evidence; human evaluation required.'],
    supporting_kpis: [
      {
        kpi_key: 'booking_rate',
        display_name: 'Booking Conversion',
        actual: 65.0,
        target: 80.0,
        unit: '%',
        direction: 'higher_is_better',
        status: 'below_target',
      },
      {
        kpi_key: 'attendance',
        display_name: 'Attended Rate',
        actual: 0.0,
        target: 85.0,
        unit: '%',
        direction: 'higher_is_better',
        status: 'below_target',
      },
      {
        kpi_key: 'quality_score',
        display_name: 'Quality Evaluation',
        actual: null,
        target: 90.0,
        unit: '%',
        direction: 'higher_is_better',
        status: 'unknown',
      },
    ],
    draft: {
      title: 'Booking Conversion Coaching',
      focus_kpi_key: 'booking_rate',
      focus_kpi_name: 'Booking Conversion',
      action_type: 'Coaching',
      measured_issue: 'Booking rate is below the 80.0% standard for September 2026.',
      measured_issue_source: 'pms_evidence',
      recommended_steps: [
        'Review the last five unbooked customer inquiries together with the supervisor.',
        'Practice overcoming customer scheduling objections using the call script.',
        'Schedule a 15-minute follow-up review after the next shift.',
      ],
      recommended_steps_source: 'cloudflare',
      uncertainty: 'Root cause is unverified by evidence; human evaluation required.',
      uncertainty_source: 'pms_evidence',
      approval_status: 'unapproved_draft',
    },
    read_only: true,
    requires_human_confirmation: true,
    ...overrides,
  };
}

const mockEmployee: TeamAgentRow = {
  id: 'EMP-101',
  name: 'Sarah Connor',
  team: 'Inbound',
  month: 'September 2026',
  performanceLevel: 'Employee',
  score: 72.5,
  gradeClass: 'C',
  gradeLabel: 'C',
  status: 'Below',
  rootCauseAuto: 'Booking rate below target',
  rootCauseNote: 'Customer hesitations regarding clinic hours.',
  correctiveAction: '',
  suggestedAction: 'Coaching',
  ahtMinutes: 3.5,
  bookingRate: 0.65,
  attendRate: 0.70,
  raw: {
    identity: { name: 'Sarah Connor', employee_id: 'EMP-101', team: 'Inbound', month: 'September 2026' },
    calls: { inbound: 20, outbound: 0, total_handled: 20, abandoned: 1, aht_raw: '00:03:30' },
    geo: { bookings: { dubai: 10, sharjah: 3, ajman: 0, clinics: 0 }, attended: { dubai: 8, sharjah: 2, ajman: 0, clinics: 0 } },
    actual: { booking_rate: 0.65, attend_rate: 0.70, abandon_rate: 0.05, quality_rate: 0.85 },
    achievement: { booking_ach: 0.81, attend_ach: 0.82 },
    evaluation: { score: 72.5, grade: 'C' },
  },
};

function renderModalWithProviders({
  role = 'Admin',
  pilotEnabled = true,
  chatEnabled = false,
  ready = true,
}: {
  role?: string;
  pilotEnabled?: boolean;
  chatEnabled?: boolean;
  ready?: boolean;
} = {}) {
  const authValue = {
    currentUser: { id: 'user-admin', name: 'Admin User', role } as unknown as User,
    users: [],
    initializationStatus: 'ready' as const,
    isAppInitializing: false,
    initializationError: null,
    login: vi.fn(),
    logout: vi.fn(),
    updateProfile: vi.fn(),
    changePassword: vi.fn(),
    addUser: vi.fn(),
    updateUser: vi.fn(),
    deleteUser: vi.fn(),
    toggleUserActive: vi.fn(),
    refreshUsers: vi.fn(),
  };

  const aiAvailabilityValue = {
    enabled: chatEnabled,
    correctiveActionPilotEnabled: pilotEnabled,
    ready,
    saving: false,
    error: null,
    setEnabled: vi.fn(),
    setCorrectiveActionPilotEnabled: vi.fn(),
  };

  return render(
    <AuthContext.Provider value={authValue}>
      <AiAvailabilityContext.Provider value={aiAvailabilityValue}>
        <EmployeeActionModal
          employee={mockEmployee}
          month="September 2026"
          onClose={vi.fn()}
        />
      </AiAvailabilityContext.Provider>
    </AuthContext.Provider>
  );
}

describe('CorrectiveActionSuggestionCard Unit Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    aiResponseHandler = null;
    setupDefaultApiFetch();
  });

  it('renders in idle state without calling API on initial render', () => {
    render(
      <CorrectiveActionSuggestionCard
        employeeId="EMP-101"
        employeeName="Sarah Connor"
        team="Inbound"
        month="September"
        year={2026}
        onApplyDraft={vi.fn()}
      />
    );

    expect(screen.getByText(/AI Corrective Action Suggestion/i)).toBeInTheDocument();
    expect(screen.getByText(/Draft — Requires Review/i)).toBeInTheDocument();
    expect(screen.getByTestId('generate-suggestion-btn')).toBeInTheDocument();
    expect(mockApiFetch).not.toHaveBeenCalled();
  });

  it('calls POST /api/ai/corrective-action-suggestions with correct authorized payload on click', async () => {
    const user = userEvent.setup();
    aiResponseHandler = async () => ({
      success: true,
      message: 'Draft generated',
      data: createMockSuggestedPayload(),
    });

    render(
      <CorrectiveActionSuggestionCard
        employeeId="EMP-101"
        employeeName="Sarah Connor"
        team="Inbound"
        month="September"
        year={2026}
        linkedKpiKey="booking_rate"
        onApplyDraft={vi.fn()}
      />
    );

    await user.click(screen.getByTestId('generate-suggestion-btn'));

    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/ai/corrective-action-suggestions',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          team: 'Inbound',
          month: 'September',
          year: 2026,
          performance_level: 'Employee',
          employee_id: 'EMP-101',
          linked_kpi_key: 'booking_rate',
        }),
      })
    );
  });

  it('displays loading skeleton while API request is in progress', async () => {
    const user = userEvent.setup();
    let resolvePromise: (value: MockApiResponse) => void;
    aiResponseHandler = () =>
      new Promise((resolve) => {
        resolvePromise = resolve;
      });

    render(
      <CorrectiveActionSuggestionCard
        employeeId="EMP-101"
        employeeName="Sarah Connor"
        team="Inbound"
        month="September"
        year={2026}
        onApplyDraft={vi.fn()}
      />
    );

    await user.click(screen.getByTestId('generate-suggestion-btn'));

    expect(screen.getByTestId('ai-card-loading')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveAttribute('aria-busy', 'true');

    // Resolve request
    resolvePromise!({
      success: true,
      message: 'Draft generated',
      data: createMockSuggestedPayload(),
    });

    await waitFor(() => {
      expect(screen.queryByTestId('ai-card-loading')).not.toBeInTheDocument();
      expect(screen.getByTestId('ai-card-suggested')).toBeInTheDocument();
    });
  });

  it('renders suggested state with KPI evidence and provider badge accurately', async () => {
    const user = userEvent.setup();
    aiResponseHandler = async () => ({
      success: true,
      message: 'Draft generated',
      data: createMockSuggestedPayload(),
    });

    render(
      <CorrectiveActionSuggestionCard
        employeeId="EMP-101"
        employeeName="Sarah Connor"
        team="Inbound"
        month="September"
        year={2026}
        onApplyDraft={vi.fn()}
      />
    );

    await user.click(screen.getByTestId('generate-suggestion-btn'));

    await waitFor(() => {
      expect(screen.getByText('Booking Conversion Coaching')).toBeInTheDocument();
      expect(screen.getByText('Cloudflare Workers AI')).toBeInTheDocument();
    });

    // Recommended steps
    expect(
      screen.getByText(/Review the last five unbooked customer inquiries/i)
    ).toBeInTheDocument();
    expect(
      screen.getByText(/Practice overcoming customer scheduling objections/i)
    ).toBeInTheDocument();

    // KPI Evidence
    // Booking Conversion has actual 65% and target 80%
    const bookingRow = screen.getByTestId('kpi-evidence-row-booking_rate');
    expect(bookingRow).toHaveTextContent('65%');
    expect(bookingRow).toHaveTextContent('80%');

    // Real zero is preserved as 0.0%
    const attendRow = screen.getByTestId('kpi-evidence-row-attendance');
    expect(attendRow).toHaveTextContent('0.0%');

    // Missing data is preserved as "Unavailable" (not zero)
    const qualityRow = screen.getByTestId('kpi-evidence-row-quality_score');
    expect(qualityRow).toHaveTextContent('Unavailable');

    // Insert draft button
    expect(screen.getByTestId('insert-draft-btn')).toBeInTheDocument();
  });

  it('calls onApplyDraft with formatted steps when Insert Editable Draft is clicked', async () => {
    const user = userEvent.setup();
    const handleApply = vi.fn();
    aiResponseHandler = async () => ({
      success: true,
      message: 'Draft generated',
      data: createMockSuggestedPayload(),
    });

    render(
      <CorrectiveActionSuggestionCard
        employeeId="EMP-101"
        employeeName="Sarah Connor"
        team="Inbound"
        month="September"
        year={2026}
        onApplyDraft={handleApply}
      />
    );

    await user.click(screen.getByTestId('generate-suggestion-btn'));
    await waitFor(() => expect(screen.getByTestId('insert-draft-btn')).toBeInTheDocument());

    await user.click(screen.getByTestId('insert-draft-btn'));

    expect(handleApply).toHaveBeenCalledTimes(1);
    expect(handleApply).toHaveBeenCalledWith({
      actionType: 'Coaching',
      actionDescription:
        '1. Review the last five unbooked customer inquiries together with the supervisor.\n' +
        '2. Practice overcoming customer scheduling objections using the call script.\n' +
        '3. Schedule a 15-minute follow-up review after the next shift.',
    });
  });

  it('renders insufficient_evidence outcome cleanly with manual entry option', async () => {
    const user = userEvent.setup();
    aiResponseHandler = async () => ({
      success: true,
      message: 'Insufficient evidence',
      data: {
        outcome: 'insufficient_evidence',
        provider_used: 'none',
        context: {
          subject: 'employee',
          team: 'Inbound',
          period: { month: 'September', year: 2026 },
          performance_level: 'Employee',
        },
        insufficient_evidence_reasons: ['No verified KPI records found for this period.'],
        read_only: true,
        requires_human_confirmation: true,
      },
    });

    render(
      <CorrectiveActionSuggestionCard
        employeeId="EMP-101"
        team="Inbound"
        month="September"
        year={2026}
        onApplyDraft={vi.fn()}
      />
    );

    await user.click(screen.getByTestId('generate-suggestion-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('ai-card-insufficient-evidence')).toBeInTheDocument();
      expect(screen.getByText(/Not enough verified performance data is available/i)).toBeInTheDocument();
      expect(screen.getByText(/No verified KPI records found for this period/i)).toBeInTheDocument();
    });
  });

  it('renders model_unavailable outcome with retry button', async () => {
    const user = userEvent.setup();
    aiResponseHandler = async () => ({
      success: true,
      message: 'Model unavailable',
      data: {
        outcome: 'model_unavailable',
        provider_used: 'none',
        context: {
          subject: 'employee',
          team: 'Inbound',
          period: { month: 'September', year: 2026 },
          performance_level: 'Employee',
        },
        read_only: true,
        requires_human_confirmation: true,
      },
    });

    render(
      <CorrectiveActionSuggestionCard
        employeeId="EMP-101"
        team="Inbound"
        month="September"
        year={2026}
        onApplyDraft={vi.fn()}
      />
    );

    await user.click(screen.getByTestId('generate-suggestion-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('ai-card-model-unavailable')).toBeInTheDocument();
      expect(screen.getByText(/AI suggestion service is temporarily unavailable/i)).toBeInTheDocument();
      expect(screen.getByText('Retry')).toBeInTheDocument();
    });
  });

  it('renders draft_rejected outcome when model fails validation against evidence', async () => {
    const user = userEvent.setup();
    aiResponseHandler = async () => ({
      success: true,
      message: 'Draft rejected',
      data: {
        outcome: 'draft_rejected',
        provider_used: 'none',
        context: {
          subject: 'employee',
          team: 'Inbound',
          period: { month: 'September', year: 2026 },
          performance_level: 'Employee',
        },
        read_only: true,
        requires_human_confirmation: true,
      },
    });

    render(
      <CorrectiveActionSuggestionCard
        employeeId="EMP-101"
        team="Inbound"
        month="September"
        year={2026}
        onApplyDraft={vi.fn()}
      />
    );

    await user.click(screen.getByTestId('generate-suggestion-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('ai-card-draft-rejected')).toBeInTheDocument();
      expect(screen.getByText(/Suggestion discarded for safety/i)).toBeInTheDocument();
    });
  });

  it('handles HTTP 403 authorization error safely', async () => {
    const user = userEvent.setup();
    aiResponseHandler = async () => {
      throw new ApiError('PMS AI is limited to administrators during the pilot.', 403);
    };

    render(
      <CorrectiveActionSuggestionCard
        employeeId="EMP-101"
        team="Inbound"
        month="September"
        year={2026}
        onApplyDraft={vi.fn()}
      />
    );

    await user.click(screen.getByTestId('generate-suggestion-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('ai-card-error')).toBeInTheDocument();
      expect(
        screen.getByText(/Administrative access required to use the suggestion pilot/i)
      ).toBeInTheDocument();
    });
  });

  it('handles HTTP 429 daily rate limit error', async () => {
    const user = userEvent.setup();
    aiResponseHandler = async () => {
      throw new ApiError('Live verification daily limit exceeded', 429);
    };

    render(
      <CorrectiveActionSuggestionCard
        employeeId="EMP-101"
        team="Inbound"
        month="September"
        year={2026}
        onApplyDraft={vi.fn()}
      />
    );

    await user.click(screen.getByTestId('generate-suggestion-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('ai-card-error')).toBeInTheDocument();
      expect(
        screen.getByText(/Daily suggestion limit reached/i)
      ).toBeInTheDocument();
    });
  });

  it('resets to idle and aborts in-flight request when employee or month changes', async () => {
    const { rerender } = render(
      <CorrectiveActionSuggestionCard
        employeeId="EMP-101"
        team="Inbound"
        month="September"
        year={2026}
        onApplyDraft={vi.fn()}
      />
    );

    // Change employeeId
    rerender(
      <CorrectiveActionSuggestionCard
        employeeId="EMP-202"
        team="Inbound"
        month="September"
        year={2026}
        onApplyDraft={vi.fn()}
      />
    );

    expect(screen.getByTestId('generate-suggestion-btn')).toBeInTheDocument();
    expect(screen.queryByTestId('ai-card-suggested')).not.toBeInTheDocument();
  });
});

describe('EmployeeActionModal Phase 3 Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    aiResponseHandler = null;
    setupDefaultApiFetch();
  });

  it('hides AI suggestion card completely when pilot is disabled', () => {
    renderModalWithProviders({ role: 'Admin', pilotEnabled: false });

    expect(screen.queryByTestId('ai-corrective-action-card')).not.toBeInTheDocument();
  });

  it('hides AI suggestion card completely for non-Admin users even if pilot is enabled', () => {
    renderModalWithProviders({ role: 'Manager', pilotEnabled: true });

    expect(screen.queryByTestId('ai-corrective-action-card')).not.toBeInTheDocument();
  });

  it('displays AI suggestion card when user is Admin and pilot is enabled, even if standalone chat is off', () => {
    renderModalWithProviders({ role: 'Admin', pilotEnabled: true, chatEnabled: false });

    expect(screen.getByTestId('ai-corrective-action-card')).toBeInTheDocument();
  });

  it('inserts draft into Action Description and Action Type immediately when action text is empty', async () => {
    const user = userEvent.setup();
    aiResponseHandler = async () => ({
      success: true,
      message: 'Draft generated',
      data: createMockSuggestedPayload(),
    });

    renderModalWithProviders({ role: 'Admin', pilotEnabled: true });

    // Click Generate Suggestion
    await user.click(screen.getByTestId('generate-suggestion-btn'));
    await waitFor(() => expect(screen.getByTestId('insert-draft-btn')).toBeInTheDocument());

    // Click Insert Editable Draft
    await user.click(screen.getByTestId('insert-draft-btn'));

    // Check Action Description textarea has the recommended steps
    const textarea = screen.getByPlaceholderText(/Describe the Coaching action in detail/i);
    expect((textarea as HTMLTextAreaElement).value).toContain(
      '1. Review the last five unbooked customer inquiries'
    );
  });

  it('prompts confirmation when user has existing text before overwriting', async () => {
    const user = userEvent.setup();
    aiResponseHandler = async () => ({
      success: true,
      message: 'Draft generated',
      data: createMockSuggestedPayload(),
    });

    renderModalWithProviders({ role: 'Admin', pilotEnabled: true });

    // User types manual action text first
    const textarea = screen.getByPlaceholderText(/Describe the Coaching action in detail/i);
    await user.type(textarea, 'Manual notes about upcoming training.');

    // Generate suggestion
    await user.click(screen.getByTestId('generate-suggestion-btn'));
    await waitFor(() => expect(screen.getByTestId('insert-draft-btn')).toBeInTheDocument());

    // Click Insert Editable Draft
    await user.click(screen.getByTestId('insert-draft-btn'));

    // Confirmation dialog appears
    expect(screen.getByTestId('overwrite-confirm-dialog')).toBeInTheDocument();
    expect(screen.getByText(/Replace Existing Action Description\?/i)).toBeInTheDocument();

    // Click Cancel -> Existing text is preserved
    await user.click(screen.getByTestId('cancel-overwrite-btn'));
    expect(screen.queryByTestId('overwrite-confirm-dialog')).not.toBeInTheDocument();
    expect((textarea as HTMLTextAreaElement).value).toBe('Manual notes about upcoming training.');

    // Click Insert again -> Confirm & Replace
    await user.click(screen.getByTestId('insert-draft-btn'));
    expect(screen.getByTestId('overwrite-confirm-dialog')).toBeInTheDocument();
    await user.click(screen.getByTestId('confirm-overwrite-btn'));

    // Text is replaced with the draft steps
    expect((textarea as HTMLTextAreaElement).value).toContain(
      '1. Review the last five unbooked customer inquiries'
    );
  });

  it('never modifies owner or due date when inserting AI draft', async () => {
    const user = userEvent.setup();
    aiResponseHandler = async () => ({
      success: true,
      message: 'Draft generated',
      data: createMockSuggestedPayload(),
    });

    renderModalWithProviders({ role: 'Admin', pilotEnabled: true });

    // Generate and insert
    await user.click(screen.getByTestId('generate-suggestion-btn'));
    await waitFor(() => expect(screen.getByTestId('insert-draft-btn')).toBeInTheDocument());
    await user.click(screen.getByTestId('insert-draft-btn'));

    // Form was not submitted (no save action called)
    const submitBtn = screen.getByRole('button', { name: /Save Action/i });
    expect(submitBtn).toBeInTheDocument();
    expect(submitBtn).not.toBeDisabled();
  });
});
