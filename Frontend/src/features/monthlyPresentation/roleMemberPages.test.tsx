import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import RoleDetailView from './components/RoleDetailView';
import type { RoleDetailData, RoleKpiSeries, RoleMemberItem } from './roleDetailData';
import { memberPageWindow } from './roleMemberPages';

describe('memberPageWindow', () => {
  it('shows 10 rows and keeps the next page so the following click reuses it', () => {
    const items = Array.from({ length: 25 }, (_, index) => index);
    const cache = new Map<string, readonly number[]>();

    const first = memberPageWindow(items, 0, cache, 'csr');
    expect(first.visible).toEqual([0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
    expect(first.pageCount).toBe(3);
    expect(first.rangeStart).toBe(1);
    expect(first.rangeEnd).toBe(10);
    expect(cache.has('csr:1')).toBe(true);
    expect(cache.has('csr:2')).toBe(false);

    const second = memberPageWindow(items, 1, cache, 'csr');
    expect(second.visible).toBe(cache.get('csr:1'));
    expect(second.visible).toEqual([10, 11, 12, 13, 14, 15, 16, 17, 18, 19]);
    expect(cache.get('csr:2')).toEqual([20, 21, 22, 23, 24]);

    const third = memberPageWindow(items, 2, cache, 'csr');
    expect(third.visible).toBe(cache.get('csr:2'));
    expect(third.rangeStart).toBe(21);
    expect(third.rangeEnd).toBe(25);
    expect(memberPageWindow(items, 9, cache, 'csr').page).toBe(2);
  });

  it('hides paging when the list fits on one page', () => {
    const small = memberPageWindow([1, 2, 3, 4, 5, 6, 7, 8], 0, new Map(), 'small');
    expect(small.pageCount).toBe(1);
    expect(small.visible).toHaveLength(8);

    const empty = memberPageWindow<number>([], 0, new Map(), 'none');
    expect(empty.pageCount).toBe(1);
    expect(empty.visible).toEqual([]);
    expect(empty.rangeStart).toBe(0);
    expect(empty.rangeEnd).toBe(0);
  });
});

const attended: RoleKpiSeries = {
  id: 'attended',
  kpiKey: 'AttendedCR',
  name: 'Attended CR',
  shortName: 'Attended CR',
  unit: '%',
  betterDirection: 'higher',
  actualDisplay: '48.8%',
  targetDisplay: '100.0%',
  achievementPct: 48.8,
  weightPct: 30,
  contributionPct: 14.6,
  pointsLost: 15.4,
  statusBadge: 'Below Target',
  momDeltaPct: -14.4,
  isMomGood: false,
  isBiggestGap: true,
  gapLabel: '51.2% off target',
  diagnosis: 'Attended CR is below target.',
  trend6Mo: [
    {
      month: 'Aug',
      periodKey: '2026-08',
      actual: 57,
      target: 90,
      actualFormatted: '57.0%',
      targetFormatted: '90.0%',
      metTarget: false,
    },
    {
      month: 'Sep',
      periodKey: '2026-09',
      actual: 48.8,
      target: 100,
      actualFormatted: '48.8%',
      targetFormatted: '100.0%',
      metTarget: false,
    },
  ],
};

function member(index: number): RoleMemberItem {
  const personName = `Agent ${String(index).padStart(2, '0')}`;
  return {
    employeeId: `e${index}`,
    personName,
    score: 52,
    grade: 'E',
    gradeFullLabel: 'Unsatisfactory',
    gap: -48,
    changeVsPrev: null,
    signal: 'Attended CR below target',
    keyKpiLabel: 'Attended CR',
    keyKpiActual: '48.8%',
    keyKpiTarget: '100.0%',
    keyKpiMet: false,
  };
}

function detail(count: number): RoleDetailData {
  const members = Array.from({ length: count }, (_, index) => member(index + 1));
  return {
    roleSlug: 'csr-dubai',
    roleTitle: 'CSR',
    personName: 'CSR',
    employeeId: members[0]?.employeeId ?? 'csr',
    headcount: count,
    below90Count: count,
    members,
    functionSlug: 'csr',
    functionName: 'CSR',
    regionName: 'UAE Region',
    branchLabel: 'Dubai',
    monthLabel: 'September 2026',
    previousMonthLabel: 'August',
    periodKey: '2026-09',
    score: 52.3,
    grade: 'E',
    gradeFullLabel: 'Unsatisfactory',
    gap: -47.7,
    changeVsPrev: -5.5,
    diagnosis: 'Dubai is below target.',
    impactLevel: 'Limited',
    impactDiagnosis: 'Attended CR is the drag.',
    accountableKpis: ['Attended CR'],
    accountabilityGaps: [
      {
        id: 'gap-attended',
        statement: 'Attended CR: 48.8% actual vs 100.0% target (51.2% off target)',
        ownership: `Accountable owner: CSR · Dubai · ${count} people`,
      },
    ],
    kpis: [attended],
    kpiScope: 'function',
    individualActionPlans: members.map((person) => ({
      id: `plan-${person.employeeId}`,
      employeeId: person.employeeId,
      personName: person.personName,
      score: person.score,
      grade: person.grade,
      gradeFullLabel: person.gradeFullLabel,
      mainIssue: 'Attended CR below target',
      actionText: `Coach ${person.personName}`,
      owner: 'CSR Lead',
      expectedImpact: '+2.0% employee score',
      linkedKpiKey: 'AttendedCR',
    })),
    actions: [],
  };
}

function renderRole(count: number) {
  return render(
    <RoleDetailView
      data={detail(count)}
      onNavigateToOverview={() => undefined}
      onNavigateToFunction={() => undefined}
      onSaveAction={() => undefined}
    />,
  );
}

describe('role member pager', () => {
  it('pages the people table and the coaching cards ten at a time', async () => {
    const user = userEvent.setup();
    renderRole(25);

    const table = screen.getByTestId('role-members-table');
    expect(within(table).getAllByTestId(/^role-member-/)).toHaveLength(10);
    expect(within(table).getByText('Agent 01')).toBeInTheDocument();
    expect(within(table).queryByText('Agent 11')).not.toBeInTheDocument();

    const pager = screen.getByTestId('role-members-pager');
    expect(pager).toHaveTextContent('1–10 of 25');
    expect(screen.getByRole('button', { name: 'Previous people' })).toBeDisabled();

    const coaching = screen.getByTestId('role-individual-action-plan-section');
    expect(within(coaching).getAllByRole('heading', { name: /Agent / })).toHaveLength(10);
    expect(within(coaching).getByRole('heading', { name: 'Agent 01' })).toBeInTheDocument();
    expect(within(coaching).queryByRole('heading', { name: 'Agent 11' })).not.toBeInTheDocument();

    const owner = screen.getByTestId('role-accountability');
    expect(owner).toHaveTextContent('Accountable owner: CSR · Dubai · 25 people');
    expect(owner).not.toHaveTextContent('Agent 01');

    await user.click(screen.getByRole('button', { name: 'Next people' }));

    expect(within(table).queryByText('Agent 01')).not.toBeInTheDocument();
    expect(within(table).getByText('Agent 11')).toBeInTheDocument();
    expect(within(table).queryByText('Agent 21')).not.toBeInTheDocument();
    expect(pager).toHaveTextContent('11–20 of 25');
    expect(pager).toHaveTextContent('2 / 3');
    expect(within(coaching).getByRole('heading', { name: 'Agent 11' })).toBeInTheDocument();
    expect(within(coaching).queryByRole('heading', { name: 'Agent 01' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Next people' }));
    expect(within(table).getByText('Agent 21')).toBeInTheDocument();
    expect(within(table).getByText('Agent 25')).toBeInTheDocument();
    expect(within(table).getAllByTestId(/^role-member-/)).toHaveLength(5);
    expect(pager).toHaveTextContent('21–25 of 25');
    expect(screen.getByRole('button', { name: 'Next people' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Previous people' }));
    expect(within(table).getByText('Agent 11')).toBeInTheDocument();
    expect(pager).toHaveTextContent('11–20 of 25');
  });

  it('leaves a short people list without a pager', () => {
    renderRole(8);
    expect(screen.getByTestId('role-members-table').querySelectorAll('[data-testid^="role-member-"]')).toHaveLength(8);
    expect(screen.queryByTestId('role-members-pager')).not.toBeInTheDocument();
  });
});
