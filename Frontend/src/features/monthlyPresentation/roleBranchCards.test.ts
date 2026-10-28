import { createElement } from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import type { ExecRecord } from '../executive/compose';
import type { CallCenterDeepDiveData } from './callCenterDeepDiveData';
import FunctionRoleBoard from './components/FunctionRoleBoard';
import { buildRoleDetail, resolveRoleCards } from './roleDetailData';

const period = { year: 2026, month: 'September', key: '2026-09' };

function person(
  employeeId: string,
  name: string,
  score: number,
  branches: string[],
  team = 'CSR',
  position: string | null = null,
): ExecRecord {
  return {
    employeeId,
    name,
    team,
    region: 'UAE',
    position,
    level: 'Employee',
    branches,
    period,
    score,
    kpis: [],
  };
}

function dive(functionSlug: string, functionName: string): CallCenterDeepDiveData {
  return {
    functionSlug,
    functionName,
    regionCode: 'UAE',
    regionName: 'UAE Region',
    periodKey: period.key,
    monthLabel: 'September 2026',
    previousMonthLabel: 'August',
    supportPositions: [],
    agentsNeedingAttention: [],
    keyKpis: [],
    positionActionPlans: [],
    actionsByPosition: { items: [] },
  } as unknown as CallCenterDeepDiveData;
}

describe('role cards by branch', () => {
  it('splits one role into a card per branch and keeps an unbranched role together', () => {
    const csr = dive('csr', 'CSR');
    const cards = resolveRoleCards(csr, [
      person('d1', 'Dana', 50, ['dubai']),
      person('d2', 'Omar', 54, ['dubai']),
      person('a1', 'Lina', 70, ['ajman']),
      person('s1', 'Hana', 92, ['sharjah']),
      person('both', 'Nour', 60, ['dubai', 'sharjah']),
    ]);

    expect(cards.map((card) => [card.roleSlug, card.branchLabel, card.headcount, card.score])).toEqual([
      ['csr-dubai', 'Dubai', 3, 54.7],
      ['csr-ajman', 'Ajman', 1, 70],
      ['csr-sharjah', 'Sharjah (Sharqa)', 2, 76],
    ]);

    const marketing = dive('marketing', 'Marketing');
    const designers = resolveRoleCards(marketing, [
      person('g1', 'Ada', 80, [], 'Marketing', 'Graphic Designer'),
      person('g2', 'Bea', 88, [], 'Marketing', 'Graphic Designer'),
    ]);
    expect(designers).toHaveLength(1);
    expect(designers[0]).toMatchObject({ roleSlug: 'graphic-designer', roleTitle: 'Graphic Designer', headcount: 2, branchLabel: undefined });

    render(createElement(FunctionRoleBoard, {
      roles: cards,
      previousMonthLabel: 'August',
      onSelectRole: () => undefined,
    }));
    const dubai = screen.getByRole('button', { name: 'Open CSR Dubai role detail' });
    expect(dubai).toHaveTextContent('Dubai');
    expect(dubai).toHaveTextContent('View role');
    expect(dubai.querySelector('span.w-full')).toHaveClass('justify-center', 'rounded-lg');
    expect(screen.getByRole('button', { name: 'Open CSR Ajman role detail' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Open CSR Sharjah (Sharqa) role detail' })).toBeInTheDocument();
  });

  it('opens only the people in the selected branch', () => {
    const csr = dive('csr', 'CSR');
    const records = [
      person('d1', 'Dana', 50, ['dubai']),
      person('d2', 'Omar', 54, ['dubai']),
      person('a1', 'Lina', 70, ['ajman']),
    ];
    const detail = buildRoleDetail(csr, 'csr-dubai', [], records);
    expect(detail.branchLabel).toBe('Dubai');
    expect(detail.roleTitle).toBe('CSR');
    expect(detail.members.map((member) => member.personName)).toEqual(['Dana', 'Omar']);
    expect(detail.headcount).toBe(2);
    expect(detail.diagnosis).toContain('in Dubai');
    expect(detail.accountabilityGaps[0]?.ownership).toBe('Accountable owner: CSR · Dubai · 2 people');
    expect(detail.accountabilityGaps.every((gap) => !gap.ownership.includes('Dana') && !gap.ownership.includes('Omar'))).toBe(true);
  });
});
