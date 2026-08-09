import { describe, expect, it } from 'vitest';
import { readdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { validateTeamConfig } from './teamConfig.schema';

describe('TeamConfigSchema', () => {
  it('accepts a config-first position-scoped employee team without root KPIs', () => {
    const config = validateTeamConfig({
      team: 'Future UAE Team',
      db_name: 'Future UAE Team',
      region: 'UAE',
      employee_id_col: 'EmployeeID',
      employee_name_col: 'EmployeeName',
      grade_thresholds: { A: 95, B: 85, C: 75, D: 65 },
      performance_levels: {
        Employee: {
          positions: {
            Operations: {
              capping: 'capped_at_100',
              kpis: [{
                key: 'quality',
                label: 'Quality',
                weight: 1,
                direction: 'higher_better',
                unit: '%',
                color: '#10B981',
                actual_col: 'A.Quality',
                target_col: 'T.Quality',
              }],
            },
          },
        },
      },
    });

    expect(config.region).toBe('UAE');
    expect(config.kpis).toEqual([]);
    expect(config.performance_levels?.Employee.positions?.Operations.kpis).toHaveLength(1);
  });

  it('accepts every production team config, including its aggregation contract', () => {
    const configDirectory = resolve(process.cwd(), '../Backend/config/teams');
    const configs = readdirSync(configDirectory)
      .filter((fileName) => fileName.endsWith('.json'))
      .map((fileName) => JSON.parse(readFileSync(resolve(configDirectory, fileName), 'utf8')));

    expect(configs.map((config) => validateTeamConfig(config).team)).toHaveLength(16);
  });
});
