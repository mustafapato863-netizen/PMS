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

  it.each(['ER Dr', 'Radiologist', 'Qlty&Case-Mngt'])('shows published clinical achievement on the %s team page', (team) => {
    const clinical = {
      ...agent,
      identity: { ...agent.identity, team },
      kpi_values: [{ ...storedReporting, label: 'Audit achievement', actual_value: 0,
        achievement_ratio: 0, weight_applied: 0, contribution: 0, view_only: true }],
    } as AgentRecord;
    const config = { ...marketingConfig, team };
    const rows = [...aggregateConfiguredTeamKpis([clinical], config).values()];
    expect(rows).toMatchObject([{ label: 'Audit achievement', actual: 0, weight: 0, viewOnly: true }]);
  });

  it('aggregates recomputed clinical KPIs with effective weights and skips PerformanceScore/penalties', () => {
    const erDoctor = {
      ...agent,
      identity: { ...agent.identity, team: 'ER Dr' },
      kpi_values: [
        { kpi_key: 'PerformanceScore', label: 'Performance Score', unit: '%', direction: 'higher_better', actual_value: 0.9, target_value: 1, achievement_ratio: 0.9, weight_applied: 1, contribution: 0.9 },
        { kpi_key: 'admission_rate', label: 'Admission rate', unit: '%', direction: 'higher_better', actual_value: 0.9, target_value: 1, achievement_ratio: 0.9, weight_applied: 0.5, contribution: 0.45 },
        { kpi_key: 'valid_complaints', label: 'Valid complaints penalty', unit: '%', direction: 'lower_better', actual_value: 0.05, target_value: 0, achievement_ratio: 0, weight_applied: 0, contribution: -0.05, is_penalty: true },
      ],
    } as AgentRecord;
    const erConfig = {
      ...marketingConfig,
      team: 'ER Dr',
      kpis: [{ key: 'PerformanceScore', label: 'Performance Score', weight: 1.0, direction: 'higher_better', unit: '%' }],
    } as unknown as TeamConfig;
    const rows = [...aggregateConfiguredTeamKpis([erDoctor], erConfig).values()];
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ label: 'Admission rate', actual: 0.9, weight: 0.5 });
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
