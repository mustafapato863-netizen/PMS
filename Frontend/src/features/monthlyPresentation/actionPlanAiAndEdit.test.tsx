import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthContext, type AuthContextProps } from '../../context/auth';
import { ApiError, apiErrorMessage } from '../../lib/apiClient';
import * as apiClientModule from '../../lib/apiClient';
import {
  collectSuggestionNotices,
  formatInsufficientEvidenceReason,
  hasSupportedProjectedImpact,
  resolveTeamCardFocusKpiKey,
} from './components/actionPlanAiUtils';
import { IndividualEvidenceDrawer } from './components/ActionPlanAiAssistant';
import RoleDetailView from './components/RoleDetailView';
import TeamDeepDiveView from './components/TeamDeepDiveView';
import { INBOUND_TEAM_DEEP_DIVE_SEP_2026, type TeamDeepDiveData, type TeamLevelActionPlanCard } from './teamDeepDiveData';
import type { RoleDetailData } from './roleDetailData';

const aiDraftResponse = {
  success: true,
  data: {
    outcome: 'suggested',
    provider_used: 'cloudflare',
    fallback_used: false,
    measured_facts: [
      'AHT at 3.12 min vs 2.50 min target in September 2026',
      'Score trend: 84.0% -> 79.0% (-5.0 pts, declining)',
    ],
    evidence_limitations: [],
    supporting_kpis: [],
    insufficient_evidence_reasons: [],
    draft: {
      title: 'Run structured call-closing cadence coaching',
      focus_kpi_key: 'AHT',
      focus_kpi_name: 'AHT (Handle Time)',
      action_type: 'Coaching',
      measured_issue: 'AHT exceeded 2.50 min target across two trailing months',
      recommended_steps: [
        'Audit five call closings for hold spikes.',
        'Drill wrap-up macro shortcuts daily.',
        'Review handling duration mid-week.',
      ],
      uncertainty: 'Verify shift volume shifts alongside coaching.',
      approval_status: 'unapproved_draft',
    },
  },
};

function makeTeamFixture(): TeamDeepDiveData {
  return {
    ...INBOUND_TEAM_DEEP_DIVE_SEP_2026,
    individualActionPlans: [
      {
        ...INBOUND_TEAM_DEEP_DIVE_SEP_2026.individualActionPlans[0],
        id: 'ind-inbound-0',
        employeeId: 'EMP-101',
        agentName: 'Maryam Elsayed',
        score: 79.2,
        previousScore: 84.0,
        changeVsPrev: -4.8,
        scoreTrendLabel: '84.0% → 79.2% (-4.8 pts, declining)',
        weakKpis: [
          {
            key: 'AHT',
            name: 'AHT (Handle Time)',
            actual: 3.12,
            target: 2.5,
            unit: 'min',
            gapText: '3.12 min vs 2.50 min (+0.62 min over)',
          },
        ],
        recordTeam: 'Inbound',
        performanceLevel: 'Employee',
      },
    ],
    teamActionPlans: [
      {
        id: 'team-act-1',
        title: 'Standardize call wrap-up macro templates',
        targetKpi: 'AHT · 3.01 min → 2.50 min',
        scopeDescription: 'All 14 Inbound agents',
        owner: 'Inbound Team Leader',
        expectedTeamImpact: '+1.2% team score lift',
        status: 'Open',
        dueDate: '2026-10-10',
        linkedKpiKey: 'AHT',
      },
    ],
  };
}

function makeRoleFixture(): RoleDetailData {
  return {
    roleSlug: 'hr-specialist',
    roleTitle: 'HR Specialist',
    personName: 'Nour Hassan',
    employeeId: 'EMP-HR-1',
    headcount: 2,
    below90Count: 1,
    members: [
      {
        employeeId: 'EMP-HR-1',
        personName: 'Nour Hassan',
        score: 78.5,
        grade: 'C',
        gradeFullLabel: 'Average',
        gap: -11.5,
        changeVsPrev: -4.5,
        keyKpiLabel: 'Time to Fill',
        keyKpiActual: '38 days',
        keyKpiTarget: '30 days',
        keyKpiMet: false,
        signal: 'Time to Fill exceeded target',
        kpiCells: [],
      },
    ],
    functionSlug: 'human-resources',
    functionName: 'Human Resources',
    regionName: 'Egypt',
    branchLabel: 'Cairo',
    monthLabel: 'September 2026',
    periodKey: '2026-09',
    previousMonthLabel: 'August',
    score: 78.5,
    gap: -11.5,
    changeVsPrev: -4.5,
    grade: 'C',
    gradeFullLabel: 'Average',
    diagnosis: 'Hiring turnaround delayed in September.',
    impactLevel: 'Strong',
    impactDiagnosis: 'Directly drives onboarding velocity across client teams.',
    accountableKpis: ['Time to Fill'],
    accountabilityGaps: [
      {
        id: 'gap-ttf',
        statement: 'Time to Fill reached 38 days vs 30-day target.',
        ownership: 'Accountable owner: HR Specialist',
      },
    ],
    kpis: [
      {
        id: 'ttf',
        kpiKey: 'time_to_fill',
        name: 'Time to Fill',
        shortName: 'Time to Fill',
        unit: 'days',
        betterDirection: 'lower',
        actualDisplay: '38 days',
        targetDisplay: '30 days',
        achievementPct: 78.9,
        weightPct: 30,
        contributionPct: 23.7,
        pointsLost: 6.3,
        statusBadge: 'Below Target',
        momDeltaPct: -4.2,
        isMomGood: false,
        isBiggestGap: true,
        gapLabel: '+8 days',
        diagnosis: 'Sourcing cycle slower than benchmark.',
        trend6Mo: [],
      },
    ],
    kpiScope: 'role',
    individualActionPlans: [
      {
        id: 'ind-role-hr-1',
        employeeId: 'EMP-HR-1',
        personName: 'Nour Hassan',
        score: 78.5,
        grade: 'C',
        gradeFullLabel: 'Average',
        mainIssue: 'Time to Fill at 38 days vs 30 days',
        actionText: 'Review sourcing pipeline weekly.',
        owner: 'HR Lead',
        expectedImpact: '+4.0% score lift',
        linkedKpiKey: 'time_to_fill',
        recordTeam: 'HR Specialist',
        performanceLevel: 'Employee',
        scoreTrendLabel: '83.0% → 78.5% (-4.5 pts, declining)',
        weakKpis: [
          {
            key: 'time_to_fill',
            name: 'Time to Fill',
            actual: 38,
            target: 30,
            unit: 'days',
            gapText: '38 vs 30 (+8 over)',
          },
        ],
      },
    ],
    actions: [
      {
        id: 'role-act-1',
        title: 'HR Specialist Intervention',
        description: 'Streamline interview scheduling handoffs.',
        owner: 'HR Lead',
        dueDate: null,
        status: 'Open',
        expectedImpact: '+3.0% score lift',
        linkedKpiName: 'Time to Fill',
        linkedKpiKey: 'time_to_fill',
        employeeId: 'EMP-HR-1',
        affectedPeople: ['Nour Hassan'],
      },
    ],
  };
}

function makeAuthValue(role: NonNullable<AuthContextProps['currentUser']>['role']): AuthContextProps {
  return {
    currentUser: {
      id: 'user-1',
      name: 'Test User',
      username: 'testuser',
      role,
      accessible_teams: ['Inbound'],
      accessible_regions: ['EGY'],
    },
    users: [],
    initializationStatus: 'ready',
    isAppInitializing: false,
    initializationError: null,
    login: async () => ({ success: true }),
    logout: () => {},
    updateProfile: async () => ({ success: true }),
    changePassword: async () => ({ success: true }),
    addUser: async () => ({ success: true }),
    updateUser: async () => ({ success: true }),
    deleteUser: async () => ({ success: true }),
    toggleUserActive: async () => ({ success: true }),
    refreshUsers: async () => {},
  };
}

describe('Monthly Presentation Editable & AI-Assisted Action Plans', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('edits Team-Level Action Plan cards inline, calls onSaveTeamAction, and overlays savedTeamActions', { timeout: 15000 }, async () => {
    const user = userEvent.setup();
    const onSaveTeamAction = vi.fn().mockResolvedValue(undefined);
    const data = makeTeamFixture();

    const { rerender } = render(
      <TeamDeepDiveView
        data={data}
        onNavigateToOverview={() => {}}
        onNavigateToCallCenter={() => {}}
        onSaveTeamAction={onSaveTeamAction}
      />,
    );

    const teamCard = screen.getByTestId('team-action-card-team-act-1');
    await user.click(within(teamCard).getByTestId('edit-team-action-team-act-1'));

    const titleBox = within(teamCard).getByDisplayValue('Standardize call wrap-up macro templates');
    await user.clear(titleBox);
    await user.type(titleBox, 'Updated macro coaching rollout');

    const statusSelect = within(teamCard).getByDisplayValue('Open');
    await user.selectOptions(statusSelect, 'Planned');

    const ownerBox = within(teamCard).getByDisplayValue('Inbound Team Leader');
    await user.clear(ownerBox);
    await user.type(ownerBox, 'QA Supervisor');

    await user.click(within(teamCard).getByRole('button', { name: /Save Team Action/i }));

    expect(onSaveTeamAction).toHaveBeenCalledTimes(1);
    const savedArg = onSaveTeamAction.mock.calls[0][0] as TeamLevelActionPlanCard;
    expect(savedArg.id).toBe('team-act-1');
    expect(savedArg.title).toBe('Updated macro coaching rollout');
    expect(savedArg.status).toBe('Planned');
    expect(savedArg.owner).toBe('QA Supervisor');

    // Re-rendering with savedTeamActions reflects persisted server status cleanly
    rerender(
      <TeamDeepDiveView
        data={data}
        savedTeamActions={[savedArg]}
        onNavigateToOverview={() => {}}
        onNavigateToCallCenter={() => {}}
        onSaveTeamAction={onSaveTeamAction}
      />,
    );
    expect(screen.getByTestId('team-action-status-team-act-1')).toHaveTextContent('Planned');
    expect(screen.getByTestId('team-action-owner-team-act-1')).toHaveTextContent('QA Supervisor');
  });

  it('requests AI recommendation with strict schema (no extra keys), populates draft without auto-saving, and supports RoleDetailView', { timeout: 15000 }, async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.spyOn(apiClientModule, 'apiFetch').mockResolvedValue(aiDraftResponse);
    const onSaveIndividual = vi.fn().mockResolvedValue(undefined);
    const onSaveRole = vi.fn().mockResolvedValue(undefined);

    const { unmount } = render(
      <TeamDeepDiveView
        data={makeTeamFixture()}
        onNavigateToOverview={() => {}}
        onNavigateToCallCenter={() => {}}
        onSaveIndividualAction={onSaveIndividual}
      />,
    );

    const indCard = screen.getByTestId('individual-action-card-EMP-101');
    expect(within(indCard).getByTestId('individual-trend-badge-EMP-101')).toHaveTextContent('84.0% → 79.2%');
    expect(within(indCard).getByTestId('individual-weak-kpi-EMP-101-AHT')).toHaveTextContent('AHT (Handle Time)');

    await user.click(
      within(indCard).getByRole('button', { name: /Generate AI recommendation for Maryam Elsayed/i }),
    );

    await waitFor(() => {
      expect(within(indCard).getByText(/Unapproved AI Draft/i)).toBeInTheDocument();
    });
    expect(within(indCard).getByText('PMS AI')).toBeInTheDocument();
    expect(within(indCard).queryByText(/cloudflare|gemini/i)).not.toBeInTheDocument();
    expect(within(indCard).getByText(/AHT at 3.12 min vs 2.50 min target/i)).toBeInTheDocument();
    expect(onSaveIndividual).not.toHaveBeenCalled();

    // Verify exact strict Pydantic schema keys sent (never subject_type, region, or focus_kpi_key)
    const callInit = fetchSpy.mock.calls[0]?.[1] as RequestInit;
    const sentBody = JSON.parse(String(callInit.body));
    expect(sentBody).toEqual({
      team: 'Inbound',
      month: 'September',
      year: 2026,
      performance_level: 'Employee',
      employee_id: 'EMP-101',
      linked_kpi_key: 'AHT',
    });
    expect(sentBody).not.toHaveProperty('subject_type');
    expect(sentBody).not.toHaveProperty('region');
    expect(sentBody).not.toHaveProperty('focus_kpi_key');

    await user.click(within(indCard).getByRole('button', { name: /Save Action/i }));
    expect(onSaveIndividual).toHaveBeenCalledTimes(1);
    expect(onSaveIndividual.mock.calls[0][0].actionText).toContain('Run structured call-closing cadence coaching');

    unmount();

    // Verify RoleDetailView AI recommendation + Role Action edit
    render(
      <RoleDetailView
        data={makeRoleFixture()}
        onNavigateToOverview={() => {}}
        onNavigateToFunction={() => {}}
        onSaveAction={onSaveRole}
      />,
    );

    const roleAct = screen.getByTestId('role-action-role-act-1');
    await user.click(
      within(roleAct).getByRole('button', { name: /Generate AI recommendation/i }),
    );
    await waitFor(() => {
      expect(within(roleAct).getByText(/Unapproved AI Draft/i)).toBeInTheDocument();
    });
    expect(onSaveRole).not.toHaveBeenCalled();
    const roleCallInit = fetchSpy.mock.calls[1]?.[1] as RequestInit;
    const roleBody = JSON.parse(String(roleCallInit.body));
    expect(roleBody.employee_id).toBe('EMP-HR-1');
    expect(roleBody.team).toBe('HR Specialist');
    expect(roleBody.performance_level).toBe('Employee');
  });

  it('asks confirmation before overwriting unsaved manual edits and respects Discard Draft vs Apply AI Draft', { timeout: 15000 }, async () => {
    const user = userEvent.setup();
    vi.spyOn(apiClientModule, 'apiFetch').mockResolvedValue(aiDraftResponse);

    render(
      <TeamDeepDiveView
        data={makeTeamFixture()}
        onNavigateToOverview={() => {}}
        onNavigateToCallCenter={() => {}}
      />,
    );

    const indCard = screen.getByTestId('individual-action-card-EMP-101');
    await user.click(within(indCard).getByRole('button', { name: 'Edit' }));

    const textareas = within(indCard).getAllByRole('textbox');
    const actionTextarea = textareas[1];
    await user.clear(actionTextarea);
    await user.type(actionTextarea, 'My unsaved manual coaching plan');

    await user.click(
      within(indCard).getByRole('button', { name: /Generate AI recommendation for Maryam Elsayed/i }),
    );

    await waitFor(() => {
      expect(within(indCard).getByText(/unsaved manual edits/i)).toBeInTheDocument();
    });
    // Manual draft must NOT be overwritten yet
    expect(actionTextarea).toHaveValue('My unsaved manual coaching plan');

    await user.click(within(indCard).getByRole('button', { name: /^Discard Draft$/i }));
    expect(actionTextarea).toHaveValue('My unsaved manual coaching plan');

    // Re-trigger and click Apply AI Draft
    await user.click(
      within(indCard).getByRole('button', { name: /Generate AI recommendation for Maryam Elsayed/i }),
    );
    await waitFor(() => {
      expect(within(indCard).getByRole('button', { name: /^Apply AI Draft$/i })).toBeInTheDocument();
    });
    await user.click(within(indCard).getByRole('button', { name: /^Apply AI Draft$/i }));
    expect(String((actionTextarea as HTMLTextAreaElement).value)).toContain(
      'Run structured call-closing cadence coaching',
    );
  });

  it('handles 403 pilot-disabled for Admin (Enable AI Pilot & Generate) vs non-admin Manager', { timeout: 15000 }, async () => {
    const user = userEvent.setup();
    const fetchSpy = vi
      .spyOn(apiClientModule, 'apiFetch')
      .mockRejectedValueOnce(new ApiError('AI Corrective Action Pilot is disabled in settings.', 403))
      .mockResolvedValueOnce({ success: true, data: { corrective_action_pilot_enabled: true } })
      .mockResolvedValueOnce(aiDraftResponse);

    const { unmount } = render(
      <AuthContext.Provider value={makeAuthValue('Admin')}>
        <TeamDeepDiveView
          data={makeTeamFixture()}
          onNavigateToOverview={() => {}}
          onNavigateToCallCenter={() => {}}
        />
      </AuthContext.Provider>,
    );

    const indCard = screen.getByTestId('individual-action-card-EMP-101');
    await user.click(
      within(indCard).getByRole('button', { name: /Generate AI recommendation for Maryam Elsayed/i }),
    );

    await waitFor(() => {
      expect(within(indCard).getByRole('button', { name: /Enable AI Pilot & Generate/i })).toBeInTheDocument();
    });

    await user.click(within(indCard).getByRole('button', { name: /Enable AI Pilot & Generate/i }));

    await waitFor(() => {
      expect(within(indCard).getByText(/Unapproved AI Draft/i)).toBeInTheDocument();
    });
    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/settings/ai-corrective-action-pilot',
      expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ enabled: true }),
      }),
    );

    unmount();

    // Non-admin Manager gets 403 notice without admin toggle button
    vi.spyOn(apiClientModule, 'apiFetch').mockRejectedValueOnce(
      new ApiError('AI Corrective Action Pilot is disabled.', 403),
    );
    render(
      <AuthContext.Provider value={makeAuthValue('Manager')}>
        <TeamDeepDiveView
          data={makeTeamFixture()}
          onNavigateToOverview={() => {}}
          onNavigateToCallCenter={() => {}}
        />
      </AuthContext.Provider>,
    );
    const mgrCard = screen.getByTestId('individual-action-card-EMP-101');
    await user.click(
      within(mgrCard).getByRole('button', { name: /Generate AI recommendation for Maryam Elsayed/i }),
    );
    await waitFor(() => {
      expect(within(mgrCard).getByText(/Ask an Administrator to enable/i)).toBeInTheDocument();
    });
    expect(within(mgrCard).queryByRole('button', { name: /Enable AI Pilot & Generate/i })).not.toBeInTheDocument();
  });

  it('hides all Edit, AI Recommend, Add Team Action buttons and banners when presentationMode is true', () => {
    const { unmount } = render(
      <TeamDeepDiveView
        data={makeTeamFixture()}
        onNavigateToOverview={() => {}}
        onNavigateToCallCenter={() => {}}
        presentationMode
      />,
    );

    expect(screen.queryByRole('button', { name: /Generate AI recommendation/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId('add-team-action-btn')).not.toBeInTheDocument();
    expect(screen.queryByTestId('edit-team-action-team-act-1')).not.toBeInTheDocument();
    // Read-only trend & weak KPI badges remain visible
    expect(screen.getByTestId('individual-trend-badge-EMP-101')).toHaveTextContent('84.0% → 79.2%');

    unmount();

    render(
      <RoleDetailView
        data={makeRoleFixture()}
        onNavigateToOverview={() => {}}
        onNavigateToFunction={() => {}}
        onSaveAction={() => {}}
        presentationMode
      />,
    );
    expect(screen.queryByRole('button', { name: /Generate AI recommendation/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Edit$/i })).not.toBeInTheDocument();
    expect(screen.queryByTestId('role-action-form')).not.toBeInTheDocument();
    expect(screen.getByTestId('role-individual-trend-badge-EMP-HR-1')).toHaveTextContent('83.0% → 78.5%');
  });

  it('sends linked_kpi_key="Attendance" when clicking AI on Inbound built-in 3rd Whole-Team Action card', { timeout: 15000 }, async () => {
    const user = userEvent.setup();
    const fetchSpy = vi.spyOn(apiClientModule, 'apiFetch').mockResolvedValue({
      ...aiDraftResponse,
      data: {
        ...aiDraftResponse.data,
        draft: {
          ...aiDraftResponse.data.draft,
          focus_kpi_key: 'Attendance',
          focus_kpi_name: 'Attendance Rate',
        },
      },
    });

    render(
      <TeamDeepDiveView
        data={INBOUND_TEAM_DEEP_DIVE_SEP_2026}
        onNavigateToOverview={() => {}}
        onNavigateToCallCenter={() => {}}
      />,
    );

    const attendanceCard = screen.getByTestId('team-action-card-team-act-inb-3');
    expect(within(attendanceCard).getByText(/Rebalance afternoon shift overlaps & review shrinkage assumptions against the 75% Attendance benchmark/i)).toBeInTheDocument();

    await user.click(
      within(attendanceCard).getByRole('button', { name: /Generate AI recommendation/i }),
    );

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledTimes(1);
    });

    const callInit = fetchSpy.mock.calls[0]?.[1] as RequestInit;
    const sentBody = JSON.parse(String(callInit.body));
    expect(sentBody.team).toBe('Inbound');
    expect(sentBody.employee_id).toBeNull();
    expect(sentBody.linked_kpi_key).toBe('Attendance');
  });

  it('resolveTeamCardFocusKpiKey resolves target/title KPIs and skips Target Met KPIs', () => {
    const kpis = [
      { kpiKey: 'AHT', label: 'AHT (Handle Time)', shortLabel: 'AHT', verdictBadge: 'Execution Issue' },
      { kpiKey: 'Booking', label: 'Booking Rate', shortLabel: 'Booking Rate', verdictBadge: 'Target Met' },
      { kpiKey: 'Attendance', label: 'Attendance Rate', shortLabel: 'Attendance', verdictBadge: 'Execution Issue' },
    ];

    expect(
      resolveTeamCardFocusKpiKey(
        {
          linkedKpiKey: null,
          targetKpi: 'Attendance Rate · 68.2% → 73.0%+',
          title: 'Rebalance shift overlaps',
        },
        kpis,
        'AHT',
      ),
    ).toBe('Attendance');

    // Target Met card returns null so backend chooses a below-target KPI
    expect(
      resolveTeamCardFocusKpiKey(
        {
          linkedKpiKey: null,
          targetKpi: 'Booking Rate · 32.4% → 35.0%+',
          title: 'Peer call-shadowing',
        },
        kpis,
        'AHT',
      ),
    ).toBeNull();

    // Unmatched card with Target Met explorer falls back to null; below-target explorer returns explorer key
    expect(
      resolveTeamCardFocusKpiKey(
        { linkedKpiKey: null, targetKpi: 'General Coaching', title: 'Coaching plan' },
        kpis,
        'Booking',
      ),
    ).toBeNull();
    expect(
      resolveTeamCardFocusKpiKey(
        { linkedKpiKey: null, targetKpi: 'General Coaching', title: 'Coaching plan' },
        kpis,
        'Attendance',
      ),
    ).toBe('Attendance');
  });

  it('apiErrorMessage keeps 500 generic with Reference and shows 503 SERVICE_UNAVAILABLE message with Reference', () => {
    expect(
      apiErrorMessage(
        { message: 'Database detail leak', request_id: 'bc0ac6cb-1b86-460e-96ed-a182d43685ab' },
        500,
      ),
    ).toBe('The server could not complete the request. Please try again. Reference: bc0ac6cb-1b86-460e-96ed-a182d43685ab');

    expect(
      apiErrorMessage(
        {
          code: 'SERVICE_UNAVAILABLE',
          message: 'Service is temporarily busy. Please try again in a moment.',
          request_id: 'req-503-1',
        },
        503,
      ),
    ).toBe('Service is temporarily busy. Please try again in a moment. Reference: req-503-1');

    expect(
      apiErrorMessage(
        {
          code: 'OTHER_CODE',
          message: 'Internal node error',
          request_id: 'req-503-2',
        },
        503,
      ),
    ).toBe('The server could not complete the request. Please try again. Reference: req-503-2');
  });

  it('renders 4-part card UX, collapsed View evidence drawer (visible in Presentation Mode), failure states, duplicate-click guard, and scope-switch abort', { timeout: 15000 }, async () => {
    const user = userEvent.setup();
    const richTeamData = {
      ...INBOUND_TEAM_DEEP_DIVE_SEP_2026,
      individualActionPlans: [
        {
          ...INBOUND_TEAM_DEEP_DIVE_SEP_2026.individualActionPlans[0],
          id: 'ind-rich-1',
          employeeId: 'EMP-RICH-1',
          agentName: 'Salma Hassan',
          score: 76.7,
          previousScore: 89.6,
          changeVsPrev: -12.9,
          previousPeriodLabel: 'Aug 2026',
          previousIsAdjacent: false,
          missingIntermediatePeriods: ['Sep 2026'],
          fullWindowComparisonLabel: 'Full window (May–Oct 2026): 89.8% → 76.7% (-13.1 pts)',
          scoreTrendLabel: '89.8% → 89.6% → 76.7% (-13.1 pts, declining)',
          mainIssue: 'Booking Rate at 40.0% (vs 50.0% target)',
          actionText: 'Complete weekly objection-handling calibration to raise Booking Rate toward 50.0%.',
          owner: 'Trainer',
          followUpLabel: 'Recheck after 1 week',
          expectedImpact: '+6.0 pts agent score if Booking Rate reaches 50.0% (+0.6 pts team lift)',
          linkedKpiKey: 'Booking',
          allKpiEvidence: [
            {
              kpiKey: 'Booking',
              label: 'Booking Rate',
              actual: 40.0,
              target: 50.0,
              unit: '%',
              actualFormatted: '40.0%',
              targetFormatted: '50.0%',
              achievementPct: 80.0,
              metTarget: false,
              weight: 0.3,
              contributesToScore: true,
              observationStatus: 'verified' as const,
              projectedAgentScoreLift: 6.0,
            },
            {
              kpiKey: 'CSAT',
              label: 'CSAT Survey',
              actual: 0,
              target: 90.0,
              unit: '%',
              actualFormatted: '0.0% (unverified)',
              targetFormatted: '90.0%',
              achievementPct: 0,
              metTarget: false,
              weight: 0,
              contributesToScore: false,
              observationStatus: 'unverified_zero' as const,
              projectedAgentScoreLift: null,
            },
          ],
          priorActions: [
            {
              id: 'pa-1',
              actionType: 'Coaching',
              status: 'Open',
              month: 'August',
              year: 2026,
              linkedKpiKey: 'Booking',
            },
          ],
        },
      ],
    };

    let resolvePending!: (val: unknown) => void;
    let recordedSignal: AbortSignal | undefined;
    const fetchSpy = vi
      .spyOn(apiClientModule, 'apiFetch')
      .mockImplementation((_url, init) => {
        recordedSignal = (init as RequestInit | undefined)?.signal ?? undefined;
        return new Promise((resolve) => {
          resolvePending = resolve;
        });
      });

    const { rerender } = render(
      <TeamDeepDiveView
        data={richTeamData}
        presentationMode={false}
        onNavigateToOverview={() => {}}
        onNavigateToCallCenter={() => {}}
      />,
    );

    const card = screen.getByTestId('individual-action-card-EMP-RICH-1');
    // Part 1: Score and change
    expect(within(card).getByTestId('individual-score-change-EMP-RICH-1')).toHaveTextContent('-12.9 pts vs Aug 2026');
    // Part 2 & Part 3: Main issue & Next step without duplicate Specific issue:
    expect(within(card).getByTestId('individual-main-issue-EMP-RICH-1')).toHaveTextContent('Booking Rate at 40.0%');
    expect(within(card).getByText('Next step')).toBeInTheDocument();
    expect(within(card).getByTestId('individual-action-text-EMP-RICH-1')).not.toHaveTextContent('Specific issue:');
    expect(within(card).getByText('Role: Trainer')).toBeInTheDocument();
    expect(within(card).getByText('Follow-up: Recheck after 1 week')).toBeInTheDocument();

    // Part 4: View evidence collapsed by default, opens on click
    const drawer = within(card).getByTestId('individual-evidence-drawer-EMP-RICH-1');
    expect(drawer).not.toBeVisible();
    await user.click(within(card).getByRole('button', { name: /View evidence/i }));
    expect(drawer).toBeVisible();
    expect(within(drawer).getByText(/Full window \(May–Oct 2026\): 89\.8% → 76\.7% \(-13\.1 pts\)/i)).toBeInTheDocument();
    expect(within(drawer).getByText('Scored · Weight 30%')).toBeInTheDocument();
    expect(within(drawer).getByText('Diagnostic')).toBeInTheDocument();
    expect(within(drawer).getByText('0.0% (unverified)')).toBeInTheDocument();
    expect(within(drawer).getByText(/Open · August 2026/i)).toBeInTheDocument();
    expect(within(drawer).getByText(/Potential score lift if Booking Rate reaches 50/i)).toBeInTheDocument();

    // Duplicate-request prevention while in-flight, and Next step remains visible & editable
    const suggestBtn = within(card).getByRole('button', { name: /Generate AI recommendation for Salma Hassan/i });
    await user.click(suggestBtn);
    await user.click(suggestBtn);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(within(card).getByTestId('individual-action-text-EMP-RICH-1')).toBeVisible();

    // Scope switch aborts in-flight request cleanly
    rerender(
      <TeamDeepDiveView
        data={{ ...richTeamData, periodKey: '2026-10', monthLabel: 'October 2026' }}
        presentationMode={false}
        onNavigateToOverview={() => {}}
        onNavigateToCallCenter={() => {}}
      />,
    );
    expect(recordedSignal?.aborted).toBe(true);
    resolvePending({ success: true, data: { outcome: 'model_unavailable' } });

    // Failure states: insufficient_evidence has NO Retry button, 401 distinguishes auth, model_unavailable shows Retry
    fetchSpy.mockResolvedValueOnce({
      success: true,
      data: {
        outcome: 'insufficient_evidence',
        provider_used: 'none',
        insufficient_evidence_reasons: ['Quality score source entry is blank.'],
        evidence_limitations: ['Verify source records in the raw upload sheet.'],
        measured_facts: [],
        supporting_kpis: [],
      },
    });
    const updatedCard = screen.getByTestId('individual-action-card-EMP-RICH-1');
    await user.click(within(updatedCard).getByRole('button', { name: /Generate AI recommendation for Salma Hassan/i }));
    await waitFor(() => {
      expect(within(updatedCard).getByText(/Insufficient KPI evidence — verify source records/i)).toBeInTheDocument();
    });
    expect(within(updatedCard).queryByRole('button', { name: /^Retry$/i })).not.toBeInTheDocument();
    expect(within(updatedCard).getByTestId('individual-action-text-EMP-RICH-1')).toBeVisible();

    fetchSpy.mockRejectedValueOnce(new ApiError('Authentication required', 401));
    await user.click(within(updatedCard).getByRole('button', { name: /Generate AI recommendation for Salma Hassan/i }));
    await waitFor(() => {
      expect(within(updatedCard).getByText(/Sign in required to generate AI suggestions/i)).toBeInTheDocument();
    });
    expect(within(updatedCard).queryByRole('button', { name: /^Retry$/i })).not.toBeInTheDocument();

    fetchSpy.mockResolvedValueOnce({
      success: true,
      data: {
        outcome: 'model_unavailable',
        provider_used: 'none',
        insufficient_evidence_reasons: ['Cloudflare timeout.'],
        evidence_limitations: [],
        measured_facts: [],
        supporting_kpis: [],
      },
    });
    await user.click(within(updatedCard).getByRole('button', { name: /Generate AI recommendation for Salma Hassan/i }));
    await waitFor(() => {
      expect(within(updatedCard).getByText(/AI suggestion provider is temporarily unavailable/i)).toBeInTheDocument();
    });
    expect(within(updatedCard).getByRole('button', { name: /^Retry$/i })).toBeInTheDocument();

    // Presentation mode hides Suggest action & Edit, but keeps View evidence visible and functional
    rerender(
      <TeamDeepDiveView
        data={richTeamData}
        presentationMode={true}
        onNavigateToOverview={() => {}}
        onNavigateToCallCenter={() => {}}
      />,
    );
    const presCard = screen.getByTestId('individual-action-card-EMP-RICH-1');
    expect(within(presCard).queryByRole('button', { name: /Generate AI recommendation/i })).not.toBeInTheDocument();
    expect(within(presCard).queryByRole('button', { name: /^Edit$/i })).not.toBeInTheDocument();
    const presEvidenceBtn = within(presCard).getByRole('button', { name: /View evidence/i });
    expect(presEvidenceBtn).toBeVisible();
    await user.click(presEvidenceBtn);
    const presDrawer = within(presCard).getByTestId('individual-evidence-drawer-EMP-RICH-1');
    expect(presDrawer).toBeVisible();
    expect(within(presDrawer).getByText(/assuming other KPIs stay constant/i)).toBeInTheDocument();
  });

  it('humanizes backend insufficient-evidence codes and suppresses green projected-impact banner without numeric support', { timeout: 15000 }, async () => {
    expect(formatInsufficientEvidenceReason('no_complete_kpi_below_target')).toBe(
      'All measured KPIs for this selection are meeting or above target.',
    );
    expect(
      formatInsufficientEvidenceReason('linked_kpi_missing_actual_or_target:QualityScore', [
        { kpi_key: 'QualityScore', display_name: 'Quality Score' },
      ]),
    ).toBe('Source actual or target value for Quality Score is missing — verify source records.');
    expect(
      formatInsufficientEvidenceReason('unverified_zero_for_kpi:Quality'),
    ).toBe('Quality is recorded as 0.0% without a verified audit or sample count — verify source records first.');
    expect(
      formatInsufficientEvidenceReason('zero_with_missing_raw_kpi_data:Booking'),
    ).toBe('Booking shows 0 with missing raw source entries — verify source records.');

    // When outcome !== insufficient_evidence and evidence_limitations exists, avoid duplicating raw warning codes
    const notices = collectSuggestionNotices({
      outcome: 'draft_rejected',
      insufficient_evidence_reasons: ['unverified_zero_for_kpi:Quality'],
      evidence_limitations: ['Verify Quality source records before coaching.'],
      supporting_kpis: [],
    });
    expect(notices).toEqual(['Verify Quality source records before coaching.']);

    expect(hasSupportedProjectedImpact(null)).toBe(false);
    expect(hasSupportedProjectedImpact(Number.NaN)).toBe(false);
    expect(hasSupportedProjectedImpact(0)).toBe(false);
    expect(hasSupportedProjectedImpact(-1)).toBe(false);
    expect(hasSupportedProjectedImpact(6)).toBe(true);

    const { rerender } = render(
      <IndividualEvidenceDrawer
        panelId="p-unverified"
        isOpen={true}
        employeeId="EMP-UNV"
        testIdPrefix="individual"
        expectedImpact="Verify source records before estimating score impact"
        projectedAgentScoreLift={null}
        linkedKpiLabel="Quality Score"
        linkedKpiTarget="95.0%"
      />,
    );
    expect(screen.queryByText(/Projected impact/i)).not.toBeInTheDocument();
    expect(screen.getByTestId('individual-impact-unavailable-EMP-UNV')).toHaveTextContent(
      /Action plan note \(not recalculated from KPI evidence\): Verify source records before estimating score impact/i,
    );

    rerender(
      <IndividualEvidenceDrawer
        panelId="p-diagnostic"
        isOpen={true}
        employeeId="EMP-DIAG"
        testIdPrefix="individual"
        expectedImpact="Diagnostic KPI (not weighted in overall score)"
        projectedAgentScoreLift={null}
      />,
    );
    expect(screen.queryByText(/Projected impact/i)).not.toBeInTheDocument();
    expect(screen.getByTestId('individual-impact-unavailable-EMP-DIAG')).toHaveTextContent(
      /Diagnostic KPI/i,
    );

    rerender(
      <IndividualEvidenceDrawer
        panelId="p-empty"
        isOpen={true}
        employeeId="EMP-EMPTY"
        testIdPrefix="individual"
        expectedImpact="Not specified"
        projectedAgentScoreLift={null}
      />,
    );
    expect(screen.queryByText(/Projected impact/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId('individual-impact-unavailable-EMP-EMPTY')).not.toBeInTheDocument();

    // Banner never renders raw snake-case codes in TeamDeepDiveView either
    const user = userEvent.setup();
    vi.spyOn(apiClientModule, 'apiFetch').mockResolvedValueOnce({
      success: true,
      data: {
        outcome: 'insufficient_evidence',
        provider_used: 'none',
        insufficient_evidence_reasons: ['linked_kpi_missing_actual_or_target:Quality'],
        evidence_limitations: [],
        measured_facts: [],
        supporting_kpis: [{ kpi_key: 'Quality', display_name: 'Quality Score' }],
      },
    });
    render(
      <TeamDeepDiveView
        data={makeTeamFixture()}
        presentationMode={false}
        onNavigateToOverview={() => {}}
        onNavigateToCallCenter={() => {}}
      />,
    );
    const firstCard = screen.getByTestId('individual-action-card-EMP-101');
    await user.click(within(firstCard).getByRole('button', { name: /Generate AI recommendation/i }));
    await waitFor(() => {
      expect(within(firstCard).getByText(/Source actual or target value for Quality Score is missing/i)).toBeInTheDocument();
    });
    expect(within(firstCard).queryByText(/linked_kpi_missing_actual_or_target/)).not.toBeInTheDocument();
  });

  it('maintains RoleDetailView individual card parity for Suggest action, Edit, View evidence, draft metadata, and unsaved-edit safety', { timeout: 15000 }, async () => {
    const user = userEvent.setup();
    const roleData = makeRoleFixture();
    const onSaveAction = vi.fn().mockResolvedValue(undefined);
    const fetchSpy = vi.spyOn(apiClientModule, 'apiFetch').mockResolvedValue({
      success: true,
      data: {
        outcome: 'suggested',
        provider_used: 'cloudflare',
        measured_facts: ['Hiring SLA at 48% vs 80% target'],
        evidence_limitations: [],
        supporting_kpis: [],
        insufficient_evidence_reasons: [],
        draft: {
          title: 'Draft: address Hiring SLA below target',
          focus_kpi_key: 'HiringSLA',
          focus_kpi_name: 'Hiring SLA',
          action_type: 'Monitor',
          measured_issue: 'Hiring SLA at 48% vs 80% target in September 2026.',
          recommended_steps: ['Verify Hiring SLA source records and review open requisitions.'],
          approval_status: 'unapproved_draft',
          responsible_role: 'HR Specialist',
          recommended_follow_up: 'Recheck after one week',
          observation_status: 'unverified_zero',
        },
      },
    });

    render(
      <RoleDetailView
        data={roleData}
        onNavigateToOverview={() => {}}
        onNavigateToFunction={() => {}}
        onSaveAction={onSaveAction}
      />,
    );

    const roleCard = screen.getByTestId('role-individual-action-card-EMP-HR-1');
    const suggestBtn = within(roleCard).getByRole('button', {
      name: /Generate AI recommendation for Nour Hassan/i,
    });
    expect(suggestBtn).toHaveTextContent('Suggest action');
    expect(within(roleCard).getByRole('button', { name: /^Edit$/i })).toBeInTheDocument();
    const viewEvidenceBtn = within(roleCard).getByRole('button', { name: /View evidence/i });
    expect(viewEvidenceBtn).toBeInTheDocument();
    expect(within(roleCard).getByTestId('role-individual-evidence-drawer-EMP-HR-1')).not.toBeVisible();
    await user.click(viewEvidenceBtn);
    expect(within(roleCard).getByTestId('role-individual-evidence-drawer-EMP-HR-1')).toBeVisible();

    // Unsaved manual edits trigger overwrite confirmation instead of clobbering
    await user.click(within(roleCard).getByRole('button', { name: /^Edit$/i }));
    const actionBox = within(roleCard).getByDisplayValue(roleData.individualActionPlans[0].actionText);
    await user.clear(actionBox);
    await user.type(actionBox, 'Manual HR review steps');

    await user.click(suggestBtn);
    await waitFor(() => {
      expect(within(roleCard).getByText(/You have unsaved manual edits on this card/i)).toBeInTheDocument();
    });
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    await user.click(within(roleCard).getByRole('button', { name: /Apply AI Draft/i }));
    await user.click(within(roleCard).getByRole('button', { name: /Save Action/i }));
    expect(onSaveAction).toHaveBeenCalledTimes(1);
    expect(within(roleCard).getByText('Role: HR Specialist')).toBeInTheDocument();
    expect(within(roleCard).getByText('Follow-up: Recheck after one week')).toBeInTheDocument();
  });

  it('does not mutate card Role or Follow-up before Save Action and resets cleanly on Discard Draft and Cancel', { timeout: 15000 }, async () => {
    const user = userEvent.setup();
    const draftWithRoleAndFollowUp = {
      success: true,
      data: {
        outcome: 'suggested',
        provider_used: 'cloudflare',
        measured_facts: [
          'Quality Score (quality_score) in September 2026: missing_actual_for_kpi:quality_score.',
        ],
        evidence_limitations: ['PMS data shows the measured gap, not its cause.'],
        supporting_kpis: [
          {
            kpi_key: 'quality_score',
            display_name: 'Quality Score',
            actual: 70,
            target: 95,
            unit: '%',
            direction: 'higher_better',
            status: 'below_target',
          },
        ],
        draft: {
          title: 'Calibrate quality scoring',
          focus_kpi_key: 'AHT',
          focus_kpi_name: 'AHT',
          action_type: 'Coaching',
          measured_issue: 'AHT at 3.12 min vs 2.50 min target',
          recommended_steps: ['Run structured call-closing cadence coaching.'],
          uncertainty: 'PMS data shows the measured gap, not its cause.',
          approval_status: 'unapproved_draft',
          responsible_role: 'Quality Specialist',
          recommended_follow_up: 'Recheck after 2 weeks',
          observation_status: 'verified',
        },
        insufficient_evidence_reasons: [],
      },
    };
    vi.spyOn(apiClientModule, 'apiFetch').mockResolvedValue(draftWithRoleAndFollowUp);

    const teamFixture = makeTeamFixture();
    teamFixture.individualActionPlans[0] = {
      ...teamFixture.individualActionPlans[0],
      owner: 'Team Leader',
      followUpLabel: 'Weekly review',
    };

    const onSaveIndividual = vi.fn().mockResolvedValue(undefined);
    const { unmount } = render(
      <TeamDeepDiveView
        data={teamFixture}
        onNavigateToOverview={() => {}}
        onNavigateToCallCenter={() => {}}
        onSaveIndividualAction={onSaveIndividual}
      />,
    );

    const indCard = screen.getByTestId('individual-action-card-EMP-101');
    expect(within(indCard).getByText('Role: Team Leader')).toBeInTheDocument();
    expect(within(indCard).getByText('Follow-up: Weekly review')).toBeInTheDocument();

    // 1) Suggest action -> Cancel must exit edit mode without mutating Role or Follow-up
    await user.click(
      within(indCard).getByRole('button', { name: /Generate AI recommendation for Maryam Elsayed/i }),
    );
    await waitFor(() => {
      expect(within(indCard).getByText(/Unapproved AI Draft/i)).toBeInTheDocument();
    });
    // Leaked snake_case code and raw kpi_key in measured_facts are humanized in banner
    expect(within(indCard).queryByText(/missing_actual_for_kpi/)).not.toBeInTheDocument();
    expect(within(indCard).queryByText(/\(quality_score\)/)).not.toBeInTheDocument();
    expect(within(indCard).getByText(/Actual value for Quality Score is unavailable/i)).toBeInTheDocument();

    await user.click(within(indCard).getByRole('button', { name: /^Cancel$/i }));
    expect(onSaveIndividual).not.toHaveBeenCalled();
    expect(within(indCard).getByText('Role: Team Leader')).toBeInTheDocument();
    expect(within(indCard).getByText('Follow-up: Weekly review')).toBeInTheDocument();

    // 2) Suggest action -> Discard Draft must reset draft fields and leave Role and Follow-up unchanged
    await user.click(within(indCard).getByRole('button', { name: /^Discard Draft$/i }));
    expect(within(indCard).getByText('Role: Team Leader')).toBeInTheDocument();
    expect(within(indCard).getByText('Follow-up: Weekly review')).toBeInTheDocument();

    // 3) Re-suggest -> Discard Draft directly from auto-opened editor
    await user.click(
      within(indCard).getByRole('button', { name: /Generate AI recommendation for Maryam Elsayed/i }),
    );
    await waitFor(() => {
      expect(within(indCard).getByRole('button', { name: /^Save Action$/i })).toBeInTheDocument();
    });
    await user.click(within(indCard).getByRole('button', { name: /^Discard Draft$/i }));
    expect(within(indCard).getByText('Role: Team Leader')).toBeInTheDocument();
    expect(within(indCard).getByText('Follow-up: Weekly review')).toBeInTheDocument();
    expect(onSaveIndividual).not.toHaveBeenCalled();

    // 4) Re-suggest -> Save Action persists new Role and Follow-up
    await user.click(
      within(indCard).getByRole('button', { name: /Generate AI recommendation for Maryam Elsayed/i }),
    );
    await waitFor(() => {
      expect(within(indCard).getByRole('button', { name: /^Save Action$/i })).toBeInTheDocument();
    });
    await user.click(within(indCard).getByRole('button', { name: /^Save Action$/i }));
    expect(onSaveIndividual).toHaveBeenCalledTimes(1);
    expect(within(indCard).getByText('Role: Quality Specialist')).toBeInTheDocument();
    expect(within(indCard).getByText('Follow-up: Recheck after 2 weeks')).toBeInTheDocument();

    unmount();

    // 5) RoleDetailView parity: Suggest action -> Cancel & Discard Draft leave Role and Follow-up unchanged
    const roleFixture = makeRoleFixture();
    roleFixture.individualActionPlans = [
      {
        ...roleFixture.individualActionPlans![0],
        owner: 'Initial Role Owner',
        followUpLabel: 'Initial Follow-up',
      },
    ];
    const onSaveRoleAction = vi.fn().mockResolvedValue(undefined);
    render(
      <RoleDetailView
        data={roleFixture}
        onNavigateToOverview={() => {}}
        onNavigateToFunction={() => {}}
        onSaveAction={onSaveRoleAction}
      />,
    );

    const roleCard = screen.getByTestId('role-individual-action-card-EMP-HR-1');
    expect(within(roleCard).getByText('Role: Initial Role Owner')).toBeInTheDocument();
    expect(within(roleCard).getByText('Follow-up: Initial Follow-up')).toBeInTheDocument();

    await user.click(
      within(roleCard).getByRole('button', { name: /Generate AI recommendation for Nour Hassan/i }),
    );
    await waitFor(() => {
      expect(within(roleCard).getByRole('button', { name: /^Save Action$/i })).toBeInTheDocument();
    });
    await user.click(within(roleCard).getByRole('button', { name: /^Cancel$/i }));
    expect(within(roleCard).getByText('Role: Initial Role Owner')).toBeInTheDocument();
    expect(within(roleCard).getByText('Follow-up: Initial Follow-up')).toBeInTheDocument();

    await user.click(within(roleCard).getByRole('button', { name: /^Discard Draft$/i }));
    expect(within(roleCard).getByText('Role: Initial Role Owner')).toBeInTheDocument();
    expect(within(roleCard).getByText('Follow-up: Initial Follow-up')).toBeInTheDocument();
    expect(onSaveRoleAction).not.toHaveBeenCalled();
  });
});

describe('Action Plan delete, restore, and presentation mode hiding', () => {
  it('handles inline Cancel, Confirm, Restore, and presentationMode hiding for TeamDeepDiveView Individual and Team-Level cards', async () => {
    const user = userEvent.setup();
    const onDeleteIndividualAction = vi.fn().mockResolvedValue(undefined);
    const onDeleteTeamAction = vi.fn().mockResolvedValue(undefined);
    const onRestoreTeamActions = vi.fn().mockResolvedValue(undefined);

    const { rerender } = render(
      <TeamDeepDiveView
        data={makeTeamFixture()}
        onNavigateToOverview={() => {}}
        onNavigateToCallCenter={() => {}}
        onSwitchTeam={() => {}}
        onDeleteIndividualAction={onDeleteIndividualAction}
        onDeleteTeamAction={onDeleteTeamAction}
        onRestoreTeamActions={onRestoreTeamActions}
      />,
    );

    // 1. Individual Action Plan: Cancel keeps card
    await user.click(screen.getByTestId('delete-individual-action-EMP-101'));
    const indDialog = screen.getByRole('alertdialog', { name: /Confirm delete action for Maryam Elsayed/i });
    await user.click(within(indDialog).getByRole('button', { name: /^Cancel$/i }));
    expect(screen.getByTestId('individual-action-card-EMP-101')).toBeInTheDocument();
    expect(onDeleteIndividualAction).not.toHaveBeenCalled();

    // 2. Individual Action Plan: Confirm deletes card -> empty state -> Restore brings it back
    await user.click(screen.getByTestId('delete-individual-action-EMP-101'));
    await user.click(screen.getByTestId('confirm-delete-individual-action-EMP-101'));
    await waitFor(() => {
      expect(screen.queryByTestId('individual-action-card-EMP-101')).not.toBeInTheDocument();
    });
    expect(onDeleteIndividualAction).toHaveBeenCalledWith('EMP-101', 'September', 'ind-inbound-0');
    expect(screen.getByText('No individual action plans for this period.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Restore dismissed suggestions/i }));
    expect(screen.getByTestId('individual-action-card-EMP-101')).toBeInTheDocument();

    // 3. Team-Level Action Plan: Cancel keeps card -> Confirm deletes -> Restore brings it back
    await user.click(screen.getByTestId('delete-team-action-team-act-1'));
    const teamDialog = screen.getByRole('alertdialog', { name: /Confirm delete team action/i });
    await user.click(within(teamDialog).getByRole('button', { name: /^Cancel$/i }));
    expect(screen.getByTestId('team-action-card-team-act-1')).toBeInTheDocument();
    expect(onDeleteTeamAction).not.toHaveBeenCalled();

    await user.click(screen.getByTestId('delete-team-action-team-act-1'));
    await user.click(screen.getByTestId('confirm-delete-team-action-team-act-1'));
    await waitFor(() => {
      expect(screen.queryByTestId('team-action-card-team-act-1')).not.toBeInTheDocument();
    });
    expect(onDeleteTeamAction).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/No team-level actions for this period/i)).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Restore default actions/i }));
    await waitFor(() => {
      expect(screen.getByTestId('team-action-card-team-act-1')).toBeInTheDocument();
    });
    expect(onRestoreTeamActions).toHaveBeenCalledWith(['team-act-1']);

    // 4. Presentation mode hides Delete and Restore controls
    await user.click(screen.getByTestId('delete-individual-action-EMP-101'));
    await user.click(screen.getByTestId('confirm-delete-individual-action-EMP-101'));
    await waitFor(() => {
      expect(screen.queryByTestId('individual-action-card-EMP-101')).not.toBeInTheDocument();
    });

    rerender(
      <TeamDeepDiveView
        data={makeTeamFixture()}
        onNavigateToOverview={() => {}}
        onNavigateToCallCenter={() => {}}
        onSwitchTeam={() => {}}
        onDeleteIndividualAction={onDeleteIndividualAction}
        onDeleteTeamAction={onDeleteTeamAction}
        onRestoreTeamActions={onRestoreTeamActions}
        presentationMode={true}
      />,
    );
    expect(screen.queryByTestId('delete-team-action-team-act-1')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Restore/i })).not.toBeInTheDocument();
  });

  it('handles inline Cancel, Confirm, Restore, and presentationMode hiding for RoleDetailView Individual and Role-Level cards', async () => {
    const user = userEvent.setup();
    const onDeleteIndividualAction = vi.fn().mockResolvedValue(undefined);
    const onDeleteAction = vi.fn().mockResolvedValue(undefined);

    const { rerender } = render(
      <RoleDetailView
        data={makeRoleFixture()}
        onNavigateToOverview={() => {}}
        onNavigateToFunction={() => {}}
        onSaveAction={vi.fn().mockResolvedValue(undefined)}
        onDeleteIndividualAction={onDeleteIndividualAction}
        onDeleteAction={onDeleteAction}
      />,
    );

    // 1. Role Individual Action Plan: Cancel keeps card -> Confirm deletes -> Restore brings it back
    await user.click(screen.getByTestId('delete-role-individual-action-EMP-HR-1'));
    const indDialog = screen.getByRole('alertdialog', { name: /Confirm delete action for Nour Hassan/i });
    await user.click(within(indDialog).getByRole('button', { name: /^Cancel$/i }));
    expect(screen.getByTestId('role-individual-action-card-EMP-HR-1')).toBeInTheDocument();
    expect(onDeleteIndividualAction).not.toHaveBeenCalled();

    await user.click(screen.getByTestId('delete-role-individual-action-EMP-HR-1'));
    await user.click(screen.getByTestId('confirm-delete-role-individual-action-EMP-HR-1'));
    await waitFor(() => {
      expect(screen.queryByTestId('role-individual-action-card-EMP-HR-1')).not.toBeInTheDocument();
    });
    expect(onDeleteIndividualAction).toHaveBeenCalledWith('EMP-HR-1', 'September', undefined);
    expect(screen.getByText('No individual action plans for this period.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Restore dismissed suggestions/i }));
    expect(screen.getByTestId('role-individual-action-card-EMP-HR-1')).toBeInTheDocument();

    // 2. Role-Level Action Plan: Cancel keeps card -> Confirm deletes -> Restore brings it back
    await user.click(screen.getByTestId('delete-role-action-role-act-1'));
    const roleDialog = screen.getByRole('alertdialog', { name: /Confirm delete role action/i });
    await user.click(within(roleDialog).getByRole('button', { name: /^Cancel$/i }));
    expect(screen.getByTestId('role-action-role-act-1')).toBeInTheDocument();
    expect(onDeleteAction).not.toHaveBeenCalled();

    await user.click(screen.getByTestId('delete-role-action-role-act-1'));
    await user.click(screen.getByTestId('confirm-delete-role-action-role-act-1'));
    await waitFor(() => {
      expect(screen.queryByTestId('role-action-role-act-1')).not.toBeInTheDocument();
    });
    expect(onDeleteAction).toHaveBeenCalledTimes(1);
    expect(screen.getByText('No corrective actions recorded for this role yet.')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /Restore dismissed suggestions/i }));
    expect(screen.getByTestId('role-action-role-act-1')).toBeInTheDocument();

    // 3. Presentation mode hides all Delete & Restore controls
    await user.click(screen.getByTestId('delete-role-action-role-act-1'));
    await user.click(screen.getByTestId('confirm-delete-role-action-role-act-1'));
    await waitFor(() => {
      expect(screen.queryByTestId('role-action-role-act-1')).not.toBeInTheDocument();
    });

    rerender(
      <RoleDetailView
        data={makeRoleFixture()}
        onNavigateToOverview={() => {}}
        onNavigateToFunction={() => {}}
        onSaveAction={vi.fn().mockResolvedValue(undefined)}
        onDeleteIndividualAction={onDeleteIndividualAction}
        onDeleteAction={onDeleteAction}
        presentationMode={true}
      />,
    );
    expect(screen.queryByTestId('delete-role-individual-action-EMP-HR-1')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Restore/i })).not.toBeInTheDocument();
  });

  it('renders Saved vs Suggested badges, supports 1-click Save, Escape-closes Delete dialogs, and keeps team/role headers de-crowded', async () => {
    localStorage.clear();
    const user = userEvent.setup();
    let resolveIndSave!: () => void;
    const onSaveIndividualAction = vi.fn().mockImplementation(
      () => new Promise<void>((resolve) => { resolveIndSave = resolve; }),
    );
    const teamFixture = makeTeamFixture();
    teamFixture.individualActionPlans[0] = {
      ...teamFixture.individualActionPlans[0],
      isSavedToStore: false,
    };

    const { rerender } = render(
      <TeamDeepDiveView
        data={teamFixture}
        onNavigateToOverview={() => {}}
        onNavigateToCallCenter={() => {}}
        onSaveIndividualAction={onSaveIndividualAction}
      />,
    );

    const indCard = screen.getByTestId('individual-action-card-EMP-101');
    expect(within(indCard).getByText('Suggested — not saved')).toBeInTheDocument();
    const quickSaveInd = within(indCard).getByTestId('quick-save-individual-action-EMP-101');
    await user.click(quickSaveInd);
    expect(quickSaveInd).toBeDisabled();
    expect(quickSaveInd).toHaveTextContent('Saving…');
    resolveIndSave();
    await waitFor(() => {
      expect(within(indCard).getByText('Saved')).toBeInTheDocument();
    });
    expect(within(indCard).queryByTestId('quick-save-individual-action-EMP-101')).not.toBeInTheDocument();

    // Team-Level header row contains strictly Whole-Team Action + Status Pill (no action buttons in header)
    const teamCard = screen.getByTestId('team-action-card-team-act-1');
    const teamHeaderRow = within(teamCard).getByText('Whole-Team Action').parentElement!;
    expect(within(teamHeaderRow).queryByRole('button')).not.toBeInTheDocument();

    // Escape closes inline Delete alertdialog in TeamDeepDiveView
    await user.click(within(indCard).getByTestId('delete-individual-action-EMP-101'));
    expect(screen.getByRole('alertdialog', { name: /Confirm delete action for Maryam Elsayed/i })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();

    await user.click(within(teamCard).getByTestId('delete-team-action-team-act-1'));
    expect(screen.getByRole('alertdialog', { name: /Confirm delete team action/i })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();

    // RoleDetailView parity: Saved vs Suggested badges, 1-click Save on both individual and role-level cards, Escape close
    const roleFixture = makeRoleFixture();
    roleFixture.individualActionPlans = [
      { ...roleFixture.individualActionPlans![0], suggested: true },
    ];
    roleFixture.actions = [
      { ...roleFixture.actions[0], suggested: true },
    ];
    const onSaveAction = vi.fn().mockResolvedValue(undefined);

    rerender(
      <RoleDetailView
        data={roleFixture}
        onNavigateToOverview={() => {}}
        onNavigateToFunction={() => {}}
        onSaveAction={onSaveAction}
      />,
    );

    const roleIndCard = screen.getByTestId('role-individual-action-card-EMP-HR-1');
    expect(within(roleIndCard).getByText('Suggested — not saved')).toBeInTheDocument();
    await user.click(within(roleIndCard).getByTestId('quick-save-role-individual-action-EMP-HR-1'));
    await waitFor(() => {
      expect(within(roleIndCard).getByText('Saved')).toBeInTheDocument();
    });
    expect(within(roleIndCard).queryByTestId('quick-save-role-individual-action-EMP-HR-1')).not.toBeInTheDocument();

    const roleCard = screen.getByTestId('role-action-role-act-1');
    const roleHeaderRow = within(roleCard).getByText('Suggested action — not saved').parentElement!;
    expect(within(roleHeaderRow).queryByRole('button')).not.toBeInTheDocument();
    await user.click(within(roleCard).getByTestId('quick-save-role-action-role-act-1'));
    await waitFor(() => {
      expect(within(roleCard).getByText('Whole-Role Action')).toBeInTheDocument();
    });
    expect(within(roleCard).queryByTestId('quick-save-role-action-role-act-1')).not.toBeInTheDocument();

    await user.click(within(roleCard).getByTestId('delete-role-action-role-act-1'));
    expect(screen.getByRole('alertdialog', { name: /Confirm delete role action/i })).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument();
  });

  it('keeps Team-Level cards compact behind View evidence, isolates card height with items-start, and offers PMS evidence fallback on rejected drafts without saving', { timeout: 15000 }, async () => {
    const user = userEvent.setup();
    const onSaveTeamAction = vi.fn().mockResolvedValue(undefined);
    const data = makeTeamFixture();

    vi.spyOn(apiClientModule, 'apiFetch').mockResolvedValueOnce({
      success: true,
      data: {
        outcome: 'draft_rejected',
        provider_used: 'none',
        fallback_reason: 'validation_failed',
        validation_errors: ['word_outside_allowed_vocabulary'],
        cohort_in_scope_count: 7,
        cohort_measured_count: 6,
        cohort_unmeasured_count: 1,
        cohort_below_target_count: 6,
        cohort_coverage_label: '6 measured out of 7 in scope (1 unmeasured · 6 below target)',
        official_target_label: '75%',
        measured_facts: [
          '6 of 6 Outbound members with complete data were below target on Reachability in September 2026 (higher is better).',
          'Target for Reachability: 75%.',
          'Cohort counts: 6 measured out of 7 in scope (1 unmeasured; 6 below target).',
        ],
        evidence_limitations: [],
        supporting_kpis: [],
        insufficient_evidence_reasons: [],
        draft: null,
        evidence_next_step: 'Review Reachability by dialing window and check disconnected numbers before changing the schedule.',
        evidence_next_step_label: 'Suggested next step from PMS evidence',
        evidence_next_step_role: 'Workforce Analyst',
        evidence_next_step_follow_up: 'Review after one week',
        evidence_next_step_action_type: 'Monitor',
        evidence_next_step_source: 'pms_evidence',
      },
    });

    render(
      <TeamDeepDiveView
        data={data}
        onNavigateToOverview={() => {}}
        onNavigateToCallCenter={() => {}}
        onSaveTeamAction={onSaveTeamAction}
      />,
    );

    const teamCard = screen.getByTestId('team-action-card-team-act-1');
    // Grids size cards independently so expanding notices or evidence does not stretch neighbors
    expect(teamCard.parentElement?.className).toContain('items-start');
    const indCard = screen.getByTestId('individual-action-card-EMP-101');
    expect(indCard.parentElement?.className).toContain('items-start');

    // Cohort counts and conditional projection start collapsed inside View evidence
    const teamDrawer = within(teamCard).getByTestId('team-evidence-drawer-team-act-1');
    expect(teamDrawer).not.toBeVisible();
    expect(within(teamCard).getByText('Review date')).toBeInTheDocument();

    // Trigger AI -> draft_rejected renders 1-sentence inline status + Retry beside Suggest, plus PMS evidence fallback
    await user.click(
      within(teamCard).getByRole('button', { name: /Generate AI recommendation for Standardize call wrap-up macro templates/i }),
    );
    await waitFor(() => {
      expect(within(teamCard).getByText('AI draft did not pass evidence verification.')).toBeInTheDocument();
    });
    expect(within(teamCard).getByRole('button', { name: /^Retry$/i })).toBeInTheDocument();
    expect(within(teamCard).getByText('Suggested next step from PMS evidence')).toBeInTheDocument();
    expect(
      within(teamCard).getByText(/Review Reachability by dialing window and check disconnected numbers/i),
    ).toBeInTheDocument();
    expect(onSaveTeamAction).not.toHaveBeenCalled();

    // Existing card remains editable; "Use suggested step" populates editable fields without saving
    await user.click(within(teamCard).getByRole('button', { name: /Use suggested step/i }));
    expect(onSaveTeamAction).not.toHaveBeenCalled();
    expect(
      within(teamCard).getByDisplayValue(
        'Review Reachability by dialing window and check disconnected numbers before changing the schedule.',
      ),
    ).toBeInTheDocument();

    // Expanding View evidence exposes explicit "6 measured out of 7 in scope" and conditional projection
    await user.click(within(teamCard).getByRole('button', { name: /View evidence/i }));
    expect(teamDrawer).toBeVisible();
    expect(within(teamDrawer).getByTestId('team-cohort-counts-team-act-1')).toHaveTextContent(
      '6 measured out of 7 in scope (1 unmeasured · 6 below target)',
    );
    expect(within(teamDrawer).getByTestId('team-action-plan-estimate-team-act-1')).toHaveTextContent(
      /Action plan estimate \(not recalculated from KPI evidence\):.*\+1\.2% team score lift/i,
    );
  });
});
