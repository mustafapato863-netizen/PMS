import { describe, expect, it } from 'vitest';
import type { AgentRecord } from '../../types';
import type { MarketingKpiConfig } from './types';
import { aggregateMarketingKpis, definitionsWithStoredKpis } from './marketingAnalytics';

const config: MarketingKpiConfig[] = [
  { key: 'sms_response_rate', label: 'Response rate (%)', unit: '%', weight: .4, direction: 'higher_better', display_order: 1, perspective: 'Customer', color: '#2563EB' },
  { key: 'sms_channel_growth', label: 'Channels growth rate', unit: '%', weight: .2, direction: 'higher_better', display_order: 2, perspective: 'Customer', color: '#2563EB' },
  { key: 'sms_response_time', label: 'Response Time', unit: 'min', weight: .4, direction: 'lower_better', display_order: 3, perspective: 'Internal Process', color: '#2563EB' },
];

function record(month: string, weights: number[], extra = true): AgentRecord {
  const actuals = [.8727, .0125, 208, .9, .97];
  const targets = [1, .01, 31, 1, 1];
  const definitions: Array<Pick<MarketingKpiConfig, 'key' | 'label' | 'unit' | 'direction'>> = [...config,
    { key: 'mkt_social_media_specialist_reporting', label: 'Reporting', unit: '%', direction: 'higher_better' as const },
    { key: 'mkt_social_media_specialist_content_calen_afe3843e', label: 'Content calendar adherence', unit: '%', direction: 'higher_better' as const },
  ].slice(0, extra ? 5 : 3);
  return {
    identity: { name: 'Synthetic Only', employee_id: 'SYN-1', team: 'Marketing', month },
    year: 2026, position: 'Social Media Specialist',
    calls: { inbound: 0, outbound: 0, total_handled: 0, abandoned: 0, aht_raw: '00:00:00' },
    geo: {
      bookings: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
      attended: { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 },
    },
    actual: { booking_rate: 0, attend_rate: 0, abandon_rate: 0 },
    achievement: { booking_ach: 0, attend_ach: 0 },
    evaluation: { score: .738, grade: 'D' },
    kpi_values: definitions.map((d, i) => ({
      kpi_key: d.key, label: d.label, unit: d.unit, direction: d.direction,
      actual_value: actuals[i], target_value: targets[i], weight_applied: weights[i],
      achievement_ratio: Math.min(d.direction === 'lower_better' ? targets[i] / actuals[i] : actuals[i] / targets[i], 1),
      contribution: Math.min(d.direction === 'lower_better' ? targets[i] / actuals[i] : actuals[i] / targets[i], 1) * weights[i],
    })),
  };
}

function cards(records: AgentRecord[]) {
  return aggregateMarketingKpis(records, [], definitionsWithStoredKpis(config, records));
}

describe('Marketing cards use the selected records, not old configured weights', () => {
  it('keeps September at 30/20/30/10/10 and uses stored contributions', () => {
    const source = record('September', [.3, .2, .3, .1, .1]);
    const result = cards([source]);
    expect(result.map(k => k.weight)).toEqual([.3, .2, .3, .1, .1]);
    expect(result.reduce((n, k) => n + k.weight, 0)).toBeCloseTo(1);
    expect(result[0].averageContribution).toBeCloseTo(.8727 * .3 * 100);
    expect(result.reduce((n, k) => n + (k.averageContribution ?? 0), 0))
      .toBeCloseTo(source.kpi_values!.reduce((n, k) => n + k.contribution * 100, 0));
    expect(config.map(k => k.weight)).toEqual([.4, .2, .4]);
  });

  it('keeps August at 40/20/40 without inventing September KPIs', () => {
    expect(cards([record('August', [.4, .2, .4], false)]).map(k => k.weight)).toEqual([.4, .2, .4]);
  });

  it('uses cohort-average weights with missing KPIs contributing zero, independent of order', () => {
    const august = record('August', [.4, .2, .4], false);
    const september = record('September', [.3, .2, .3, .1, .1]);
    const result = cards([august, september]);
    expect(result.map(k => k.weight)).toEqual([.35, .2, .35, .05, .05]);
    expect(result.reduce((n, k) => n + k.weight, 0)).toBeCloseTo(1);
    expect(result.find(k => k.label === 'Reporting')?.averageContribution).toBeCloseTo(4.5);
    expect(result.find(k => k.label === 'Reporting')?.weightVaries).toBe(true);
    expect(cards([september, august]).map(k => [k.key, k.weight, k.averageContribution]))
      .toEqual(result.map(k => [k.key, k.weight, k.averageContribution]));
  });

  it('keeps a zero-weight source KPI outside the score', () => {
    const result = cards([record('September', [.4, .2, .3, 0, .1])]);
    const reporting = result.find(k => k.label === 'Reporting');
    expect(reporting?.weight).toBe(0);
    expect(reporting?.averageContribution).toBe(0);
  });

  it('takes known KPI labels/units from saved evidence without mutating config', () => {
    const source = record('September', [.3, .2, .3, .1, .1]);
    source.kpi_values![0].label = 'Uploaded response rate';
    expect(cards([source])[0].label).toBe('Uploaded response rate');
    expect(config[0].label).toBe('Response rate (%)');
  });

  it('does not add a catalog-only KPI weight to a source scorecard', () => {
    const source = record('September', [.3, .2, .3, .1, .1]);
    source.kpi_values = source.kpi_values!.filter(k => k.kpi_key !== 'sms_channel_growth');
    const missing = cards([source]).find(k => k.key === 'sms_channel_growth');
    expect(missing?.weight).toBe(0);
    expect(missing?.averageActual).toBeNull();
    expect(missing?.averageContribution).toBeNull();
  });

  it('does not replace canonical contributions with a pooled ratio calculation', () => {
    const source = record('September', [.3, .2, .3, .1, .1]);
    source.kpi_values![0].contribution = .123;
    expect(cards([source])[0].averageContribution).toBeCloseTo(12.3);
    expect(source.evaluation.score).toBe(.738);
  });
});
