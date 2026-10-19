import { describe, expect, it } from 'vitest';
import type { AgentRecord } from '../../types';
import type { TeamConfig } from '../../schemas/teamConfig.schema';
import { aggregateConfiguredTeamKpis } from './teamKpiAggregator';

// Synthetic Marketing employee. "Reporting" is a stored KPI the Marketing config does not list.
const storedReporting = {
  kpi_key: 'mkt_media_buyer_reporting',
  label: 'Reporting',
  perspective: 'Internal Process',
  unit: '%',
  direction: 'higher_better',
  actual_value: 1,
  target_value: 1,
  achievement_ratio: 1,
  weight_applied: 0.1,
  contribution: 0.1,
};

const agent = {
  identity: { name: 'Synthetic Employee', employee_id: 'SYN001', team: 'Marketing', month: 'September', year: 2026 },
  position: 'Media Buyer',
  kpi_values: [storedReporting],
} as unknown as AgentRecord;

const marketingConfig = {
  team: 'Marketing',
  db_name: 'Marketing',
  region: 'EGY',
  employee_id_col: 'Employee ID',
  employee_name_col: 'Employee Name',
  grade_thresholds: { A: 95, B: 90, C: 80, D: 70 },
  kpis: [
    { key: 'mb_cpl', label: 'CPL', weight: 0.2, direction: 'lower_better', unit: 'AED', perspective: 'Financial' },
  ],
} as unknown as TeamConfig;

describe('team KPI aggregation of stored KPIs the config does not know', () => {
  it('keeps a stored Marketing KPI with its stored label and unit', () => {
    const aggregated = Array.from(aggregateConfiguredTeamKpis([agent], marketingConfig).values());

    const reporting = aggregated.find((kpi) => kpi.label === 'Reporting');
    expect(reporting).toBeDefined();
    expect(reporting?.unit).toBe('%');
    expect(reporting?.weight).toBeCloseTo(0.1);
  });

  it('still skips a stored KPI the config does not know for other teams', () => {
    const inboundConfig = { ...marketingConfig, team: 'Inbound' } as unknown as TeamConfig;
    const inboundAgent = {
      ...agent,
      identity: { ...agent.identity, team: 'Inbound' },
    } as unknown as AgentRecord;

    const aggregated = Array.from(aggregateConfiguredTeamKpis([inboundAgent], inboundConfig).values());

    expect(aggregated.find((kpi) => kpi.label === 'Reporting')).toBeUndefined();
  });
});
