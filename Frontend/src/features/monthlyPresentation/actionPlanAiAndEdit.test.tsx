import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthContext, type AuthContextProps } from '../../context/auth';
import { ApiError } from '../../lib/apiClient';
import * as apiClientModule from '../../lib/apiClient';
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

  it('edits Team-Level Action Plan cards inline, calls onSaveTeamAction, and overlays savedTeamActions', async () => {
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

  it('requests AI recommendation with strict schema (no extra keys), populates draft without auto-saving, and supports RoleDetailView', async () => {
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
    expect(within(indCard).getByText('Cloudflare AI')).toBeInTheDocument();
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
    expect(roleBody.employee_id).toBeNull();
    expect(roleBody.team).toBe('HR Specialist');
  });

  it('asks confirmation before overwriting unsaved manual edits and respects Discard Draft vs Apply AI Draft', async () => {
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

  it('handles 403 pilot-disabled for Admin (Enable AI Pilot & Generate) vs non-admin Manager', async () => {
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
});
