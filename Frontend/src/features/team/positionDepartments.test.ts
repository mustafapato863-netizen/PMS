import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import type { TeamConfig } from '../../schemas/teamConfig.schema';
import { TEAM_DB_NAME_MAP, TEAM_ID_MAP, TEAM_NAME_MAP, teamPath, type AgentRecord } from '../../types';
import { teamBelongsToFunction } from '../insights/filterCascade';
import { isCorporateBalancedScorecard } from './balancedScorecardNavigation';
import { aggregateConfiguredTeamKpis, calculateAggregatedTeamPerformance } from './teamKpiAggregator';

const POSITION_LISTS: Record<string, string[]> = {
  'finance.json': [
    'General Accountant',
    'FP&A Manager',
    'Finance Controller',
    'Head of Accounts Payable',
    'Head of Accounts Receivable',
    'Head of Taxation',
    'Head of Treasury',
  ],
  'human_resources.json': ['HR Specialist', 'Assessment Center Lead', 'HR Operation Supervisor'],
  'it.json': ['IT Technical Support'],
  'offshore_admin_management.json': ['Offshore PMO', 'Admin Supervisor'],
  'call_center.json': [
    'Call Center trainer',
    'Quality Assurance',
    'Workforce analyst',
    'Inbound Team Leader',
    'Outbound Team Leader',
  ],
  'rcm.json': [
    'Group Claims Operations Manager',
    'Group Clinical Revenue Manager',
    'Pre-Authorization Supervisor',
    'RCM Manager SHJ, AJM',
  ],
  'pharmacy.json': ['AJM Pharmacy Manager', 'Dubai Pharmacy Manager', 'SHJ Pharmacy Manager'],
};

const MARKETING_POSITIONS = [
  'Creative Director',
  'Media Buyer & SEO Manager',
  'Social Media Head',
];

function readPositions(fileName: string): Record<string, { kpis: Array<{ weight: number }> }> {
  const parsed = JSON.parse(readFileSync(
    resolve(process.cwd(), '../Backend/config/teams', fileName),
    'utf8',
  )) as { performance_levels: { Employee: { positions: Record<string, { kpis: Array<{ weight: number }> }> } } };
  return parsed.performance_levels.Employee.positions;
}

function agent(position: string, kpis: AgentRecord['kpi_values']): AgentRecord {
  return {
    identity: { name: position, month: 'August', team: 'Pharmacy', employee_id: position, position },
    position,
    calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
    geo: {
      bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
      attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
    },
    actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0, quality_rate: 0 },
    achievement: { booking_ach: 0, attend_ach: 0 },
    evaluation: { score: 0, grade: 'E' },
    raw_data: {},
    kpi_values: kpis,
  };
}

function kpiRow(
  label: string,
  weight: number,
  actual: number,
  pinned: boolean,
): NonNullable<AgentRecord['kpi_values']>[number] {
  return {
    kpi_key: label.replace(/[^a-z0-9]+/gi, ''),
    label,
    unit: '%',
    direction: 'higher_better',
    actual_value: actual,
    target_value: 100,
    achievement_ratio: actual / 100,
    weight_applied: weight,
    contribution: (actual / 100) * weight,
    evaluation_pinned: pinned,
  };
}

const waitingKpi = {
  key: 'WaitingTime',
  label: 'Waiting Time',
  weight: 0.2,
  direction: 'higher_better' as const,
  unit: '%' as const,
  color: '#F59E0B',
};

const pharmacyConfig = {
  team: 'Pharmacy',
  db_name: 'Pharmacy',
  region: 'UAE',
  kpis: [waitingKpi],
  performance_levels: {
    Employee: {
      positions: {
        'Dubai Pharmacy Manager': {
          kpis: [{ key: 'PharmacyRevenue', label: 'Pharmacy Revenue', weight: 1, direction: 'higher_better', unit: '%', color: '#10B981' }],
        },
        'AJM Pharmacy Manager': {
          kpis: [{ key: 'AjmRevenue', label: 'AJM Revenue', weight: 0.4, direction: 'higher_better', unit: '%', color: '#10B981' }],
        },
      },
    },
  },
} as unknown as TeamConfig;

describe('position department routes', () => {
  it('maps the four departments to finance, human-resources, it, and administration', () => {
    expect(TEAM_ID_MAP.Finance).toBe('finance');
    expect(TEAM_ID_MAP['Human Resources']).toBe('human-resources');
    expect(TEAM_ID_MAP.IT).toBe('it');
    expect(TEAM_ID_MAP['Offshore Admin & Management']).toBe('administration');
    expect(TEAM_NAME_MAP.administration).toBe('Administration');
    expect(TEAM_DB_NAME_MAP.administration).toBe('Offshore Admin & Management');
    expect(teamPath('Finance')).toBe('/team/finance');
    expect(teamPath('Human Resources')).toBe('/team/human-resources');
    expect(teamPath('IT')).toBe('/team/it');
    expect(teamPath('Offshore Admin & Management')).toBe('/team/administration');
    expect(teamPath('Administration')).toBe('/team/administration');
  });

  it('treats Offshore Admin & Management as the Administration function', () => {
    expect(teamBelongsToFunction('Offshore Admin & Management', 'Administration')).toBe(true);
    expect(teamBelongsToFunction('Administration', 'Administration')).toBe(true);
    expect(teamBelongsToFunction('Finance', 'Finance')).toBe(true);
    expect(teamBelongsToFunction('IT', 'IT')).toBe(true);
    expect(teamBelongsToFunction('Human Resources', 'Human Resources')).toBe(true);
  });

  it('opens the balanced scorecard only for Corporate', () => {
    expect(isCorporateBalancedScorecard('Finance', 'Corporate')).toBe(true);
    expect(isCorporateBalancedScorecard('Finance', 'Employee')).toBe(false);
    expect(isCorporateBalancedScorecard('Finance', 'Managerial')).toBe(false);
    expect(isCorporateBalancedScorecard('', 'Corporate')).toBe(false);
  });
});

describe('position lists in team config', () => {
  it.each(Object.entries(POSITION_LISTS))('%s lists the department positions', (fileName, names) => {
    const positions = readPositions(fileName);
    expect(Object.keys(positions)).toEqual(names);
    for (const [name, definition] of Object.entries(positions)) {
      const total = definition.kpis.reduce((sum, kpi) => sum + kpi.weight, 0);
      expect(Math.abs(total - 1), name).toBeLessThanOrEqual(0.001);
    }
  });

  it('adds the three Marketing managerial positions', () => {
    const positions = readPositions('marketing.json');
    for (const name of MARKETING_POSITIONS) expect(positions).toHaveProperty(name);
    for (const [name, definition] of Object.entries(positions)) {
      const total = definition.kpis.reduce((sum, kpi) => sum + kpi.weight, 0);
      expect(Math.abs(total - 1), name).toBeLessThanOrEqual(0.001);
    }
  });
});

describe('position headcount score', () => {
  it('weights each position by headcount and ignores root KPIs for a matched position', () => {
    const dubai = agent('Dubai Pharmacy Manager', [
      kpiRow('Pharmacy Revenue', 1, 100, true),
      kpiRow('Waiting Time', 0.2, 100, false),
    ]);
    const ajm = agent('AJM Pharmacy Manager', [
      kpiRow('AJM Revenue', 0.4, 100, true),
      kpiRow('Waiting Time', 0.2, 100, false),
    ]);
    const result = calculateAggregatedTeamPerformance([dubai, ajm], pharmacyConfig);

    expect(result?.groupCount).toBe(2);
    expect(result?.score).toBe(70);
  });

  it('keeps identical pin signatures in separate position groups', () => {
    const shared = {
      team: 'Pharmacy',
      db_name: 'Pharmacy',
      region: 'UAE',
      kpis: [waitingKpi],
      performance_levels: {
        Employee: {
          positions: {
            'Dubai Pharmacy Manager': {
              kpis: [{ key: 'PharmacyRevenue', label: 'Pharmacy Revenue', weight: 1, direction: 'higher_better', unit: '%', color: '#10B981' }],
            },
            'AJM Pharmacy Manager': {
              kpis: [{ key: 'PharmacyRevenue', label: 'Pharmacy Revenue', weight: 0.4, direction: 'higher_better', unit: '%', color: '#10B981' }],
            },
          },
        },
      },
    } as unknown as TeamConfig;
    const dubai = agent('Dubai Pharmacy Manager', [
      kpiRow('Pharmacy Revenue', 1, 100, true),
      kpiRow('Waiting Time', 0.2, 100, false),
    ]);
    const ajm = agent('AJM Pharmacy Manager', [
      kpiRow('Pharmacy Revenue', 1, 40, true),
      kpiRow('Waiting Time', 0.2, 100, false),
    ]);
    const result = calculateAggregatedTeamPerformance([dubai, ajm], shared);

    expect(result?.groupCount).toBe(2);
    expect(result?.score).toBe(70);
  });

  it('keeps an unconfigured KPI only when the department has positions and no root KPIs', () => {
    const positionsOnly = {
      team: 'Finance',
      db_name: 'Finance',
      region: 'All',
      kpis: [],
      performance_levels: {
        Employee: {
          positions: {
            'General Accountant': {
              kpis: [{ key: 'Close', label: 'Close Accuracy', weight: 1, direction: 'higher_better', unit: '%', color: '#10B981' }],
            },
          },
        },
      },
    } as unknown as TeamConfig;
    const row = agent('General Accountant', [
      kpiRow('Close Accuracy', 1, 100, true),
      kpiRow('Reporting', 0.1, 100, false),
    ]);
    row.identity.team = 'Finance';

    expect(aggregateConfiguredTeamKpis([row], positionsOnly).has('reporting')).toBe(true);
    expect(aggregateConfiguredTeamKpis([
      agent('Dubai Pharmacy Manager', [
        kpiRow('Pharmacy Revenue', 1, 100, true),
        kpiRow('Reporting', 0.1, 100, false),
      ]),
    ], pharmacyConfig).has('reporting')).toBe(false);
  });
});
