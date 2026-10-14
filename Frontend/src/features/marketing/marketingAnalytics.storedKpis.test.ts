import { describe, expect, it } from 'vitest';
import type { AgentRecord } from '../../types';
import { aggregateMarketingKpis, definitionsWithStoredKpis } from './marketingAnalytics';
import type { MarketingKpiConfig } from './types';

// Synthetic records. "Reporting" stands in for a KPI the sheet added that the config does not list.
const configuredCpl: MarketingKpiConfig = {
  key: 'mb_cpl',
  label: 'CPL',
  perspective: 'Financial',
  weight: 0.2,
  direction: 'lower_better',
  unit: 'AED',
  color: '#2563EB',
  display_order: 1,
  aggregation: { method: 'weighted_average', weight_col: 'Target Value' },
};

function record(employeeId: string, kpis: Array<Record<string, unknown>>): AgentRecord {
  return {
    identity: { name: employeeId, employee_id: employeeId, team: 'Marketing', month: 'September', year: 2026 },
    kpi_values: kpis,
  } as unknown as AgentRecord;
}

const reporting = {
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

describe('Marketing KPIs the config does not list', () => {
  it('adds a definition for a stored KPI the config does not know, from the stored row', () => {
    const definitions = definitionsWithStoredKpis([configuredCpl], [record('SYN001', [reporting])]);

    const added = definitions.find((definition) => definition.key === 'mkt_media_buyer_reporting');
    expect(added).toMatchObject({ label: 'Reporting', unit: '%', direction: 'higher_better', weight: 0.1 });
    expect(added!.display_order).toBeGreaterThan(configuredCpl.display_order);
    expect(definitions[0]).toBe(configuredCpl);
  });

  it('keeps the configured definitions unchanged and adds each unknown KPI once', () => {
    const definitions = definitionsWithStoredKpis(
      [configuredCpl],
      [record('SYN001', [reporting]), record('SYN002', [reporting])],
    );

    expect(definitions.map((definition) => definition.key)).toEqual(['mb_cpl', 'mkt_media_buyer_reporting']);
  });

  it('renders an unknown KPI in the position breakdown with its stored label and unit', () => {
    const records = [record('SYN001', [reporting])];
    const aggregates = aggregateMarketingKpis(records, [], definitionsWithStoredKpis([configuredCpl], records), {});

    const entry = aggregates.find((aggregate) => aggregate.key === 'mkt_media_buyer_reporting');
    expect(entry).toMatchObject({ label: 'Reporting', unit: '%' });
    expect(entry!.averageActual).toBe(1);
  });
});
