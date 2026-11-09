import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import TeamDeepDiveView from './components/TeamDeepDiveView';
import {
  INBOUND_TEAM_DEEP_DIVE_SEP_2026,
  type AgentAverageOrBelowRow,
  type IndividualActionPlanCard,
  type TeamDeepDiveData,
} from './teamDeepDiveData';
import { memberPageWindow, TEAM_AGENT_PAGE_SIZE } from './roleMemberPages';

function makeAgent(index: number): AgentAverageOrBelowRow {
  const agentName = `Test Agent ${String(index).padStart(2, '0')}`;
  return {
    employeeId: `emp-${index}`,
    agentName,
    score: 80 + (index % 10),
    previousScore: 82,
    changeVsPrev: -2,
    grade: 'C',
    gradeFullLabel: 'Average',
    weakestKpiKey: 'AHT',
    weakestKpiLabel: 'AHT (Handle Time)',
    mainIssue: `AHT at 3.${index} min (vs 2.50 min target)`,
    kpiCells: [
      { kpiKey: 'AHT', label: 'AHT', actualFormatted: '3.50 min', targetFormatted: '2.50 min', achievementPct: 70, metTarget: false },
      { kpiKey: 'Booking', label: 'Booking Rate', actualFormatted: '60.0%', targetFormatted: '65.0%', achievementPct: 92, metTarget: false },
      { kpiKey: 'Attendance', label: 'Attendance', actualFormatted: '68.0%', targetFormatted: '75.0%', achievementPct: 90, metTarget: false },
      { kpiKey: 'Quality', label: 'Quality', actualFormatted: '96.0%', targetFormatted: '95.0%', achievementPct: 100, metTarget: true },
    ],
  };
}

function makeIndividualCard(agent: AgentAverageOrBelowRow): IndividualActionPlanCard {
  return {
    id: `ind-${agent.employeeId}`,
    employeeId: agent.employeeId,
    agentName: agent.agentName,
    score: agent.score,
    grade: agent.grade,
    gradeFullLabel: agent.gradeFullLabel,
    mainIssue: agent.mainIssue,
    actionText: `Coaching session for ${agent.agentName}`,
    owner: 'Inbound Team Leader',
    expectedImpact: '+1.5% score lift',
    linkedKpiKey: agent.weakestKpiKey,
  };
}

function makeTeamData(count: number): TeamDeepDiveData {
  const agents = Array.from({ length: count }, (_, i) => makeAgent(i + 1));
  const individualCards = agents.map(makeIndividualCard);
  return {
    ...INBOUND_TEAM_DEEP_DIVE_SEP_2026,
    summary: {
      ...INBOUND_TEAM_DEEP_DIVE_SEP_2026.summary,
      headcount: 35,
      averageOrBelowCount: count,
    },
    agentsAverageOrBelow: agents,
    individualActionPlans: individualCards,
  };
}

describe('TeamDeepDive agent pagination and caching', () => {
  it('pre-caches the next page buffer in memberPageWindow', () => {
    const items = Array.from({ length: 24 }, (_, i) => i + 1);
    const page0 = memberPageWindow(items, 0, TEAM_AGENT_PAGE_SIZE);
    expect(page0.visible).toHaveLength(10);
    expect(page0.visible[0]).toBe(1);
    expect(page0.visible[9]).toBe(10);
    expect(page0.cachedNext).toHaveLength(10);
    expect(page0.cachedNext[0]).toBe(11);
    expect(page0.cachedNext[9]).toBe(20);

    const page1 = memberPageWindow(items, 1, TEAM_AGENT_PAGE_SIZE);
    expect(page1.visible).toHaveLength(10);
    expect(page1.cachedNext).toHaveLength(4);
    expect(page1.cachedNext[0]).toBe(21);
    expect(page1.cachedNext[3]).toBe(24);

    const page2 = memberPageWindow(items, 2, TEAM_AGENT_PAGE_SIZE);
    expect(page2.visible).toHaveLength(4);
    expect(page2.cachedNext).toEqual([]);
  });

  it('paginates 16 agents 10 by 10 and synchronizes Section 5 individual cards', async () => {
    const user = userEvent.setup();
    const data = makeTeamData(16);

    render(
      <TeamDeepDiveView
        data={data}
        onNavigateToOverview={() => undefined}
        onNavigateToCallCenter={() => undefined}
      />,
    );

    const table = screen.getByTestId('agents-average-below-table');
    expect(within(table).getAllByTestId(/^low-agent-row-/)).toHaveLength(10);
    expect(within(table).getByText('Test Agent 01')).toBeInTheDocument();
    expect(within(table).getByText('Test Agent 10')).toBeInTheDocument();
    expect(within(table).queryByText('Test Agent 11')).not.toBeInTheDocument();

    const pager = screen.getByTestId('agents-average-below-pager');
    expect(pager).toHaveTextContent('Showing 1–10 of 16 agents');
    expect(pager).toHaveTextContent('1 / 2');

    const prevBtn = screen.getByTestId('agents-average-below-prev');
    const nextBtn = screen.getByTestId('agents-average-below-next');
    expect(prevBtn).toBeDisabled();
    expect(nextBtn).toBeEnabled();

    // Section 5 individual cards sync with visible page (10 cards on page 1)
    const cardsOnPage1 = screen.getAllByTestId(/^individual-action-card-/);
    expect(cardsOnPage1).toHaveLength(10);
    expect(screen.getByTestId('individual-action-card-emp-1')).toBeInTheDocument();
    expect(screen.queryByTestId('individual-action-card-emp-11')).not.toBeInTheDocument();

    // Click Next to navigate to page 2 (agents 11–16)
    await user.click(nextBtn);

    expect(within(table).getAllByTestId(/^low-agent-row-/)).toHaveLength(6);
    expect(within(table).queryByText('Test Agent 01')).not.toBeInTheDocument();
    expect(within(table).getByText('Test Agent 11')).toBeInTheDocument();
    expect(within(table).getByText('Test Agent 16')).toBeInTheDocument();

    expect(pager).toHaveTextContent('Showing 11–16 of 16 agents');
    expect(pager).toHaveTextContent('2 / 2');
    expect(prevBtn).toBeEnabled();
    expect(nextBtn).toBeDisabled();

    // Section 5 individual cards update to the 6 agents on page 2
    const cardsOnPage2 = screen.getAllByTestId(/^individual-action-card-/);
    expect(cardsOnPage2).toHaveLength(6);
    expect(screen.queryByTestId('individual-action-card-emp-1')).not.toBeInTheDocument();
    expect(screen.getByTestId('individual-action-card-emp-11')).toBeInTheDocument();
    expect(screen.getByTestId('individual-action-card-emp-16')).toBeInTheDocument();

    // Click Previous to return to page 1
    await user.click(prevBtn);
    expect(within(table).getAllByTestId(/^low-agent-row-/)).toHaveLength(10);
    expect(within(table).getByText('Test Agent 01')).toBeInTheDocument();
    expect(pager).toHaveTextContent('Showing 1–10 of 16 agents');
    expect(prevBtn).toBeDisabled();
    expect(nextBtn).toBeEnabled();
  });

  it('does not display pager when cohort has 10 or fewer agents', () => {
    const data = makeTeamData(8);

    render(
      <TeamDeepDiveView
        data={data}
        onNavigateToOverview={() => undefined}
        onNavigateToCallCenter={() => undefined}
      />,
    );

    const table = screen.getByTestId('agents-average-below-table');
    expect(within(table).getAllByTestId(/^low-agent-row-/)).toHaveLength(8);
    expect(screen.queryByTestId('agents-average-below-pager')).not.toBeInTheDocument();
  });
});
