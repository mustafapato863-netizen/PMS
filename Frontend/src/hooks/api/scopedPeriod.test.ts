import { describe, expect, it } from 'vitest';
import {
  filterByReportingPeriod,
  monthNameFromPeriodKey,
  overviewPeriodSelector,
  previousReportingSelector,
  resolveScopedPeriod,
} from './scopedPeriod';

const periods = [
  { key: '2025-06', month: 'June', year: 2025 },
  { key: '2025-07', month: 'July', year: 2025 },
  { key: '2025-12', month: 'December', year: 2025 },
  { key: '2026-01', month: 'January', year: 2026 },
  { key: '2026-07', month: 'July', year: 2026 },
];

describe('resolveScopedPeriod', () => {
  it('keeps an exact period and the previous period across the year boundary', () => {
    expect(resolveScopedPeriod(periods, '2025-07')).toEqual({
      active: { key: '2025-07', month: 'July', year: 2025 },
      previous: { key: '2025-06', month: 'June', year: 2025 },
    });
    expect(resolveScopedPeriod(periods, '2026-01').previous).toEqual({
      key: '2025-12', month: 'December', year: 2025,
    });
  });

  it('treats a month name as the latest year and leaves All on the latest period', () => {
    expect(resolveScopedPeriod(periods, 'July').active?.key).toBe('2026-07');
    expect(resolveScopedPeriod(periods, 'All').active?.key).toBe('2026-07');
    expect(resolveScopedPeriod(periods, '').active?.key).toBe('2026-07');
  });

  it('requests an exact key that is not in the catalog', () => {
    expect(resolveScopedPeriod(periods, '2024-03').active).toEqual({
      key: '2024-03', month: 'March', year: 2024,
    });
  });
});

describe('reporting period records', () => {
  const records = periods.map((period) => ({ id: period.key, month: period.month, year: period.year }));

  it('does not merge two years that share a month name', () => {
    expect(filterByReportingPeriod(records, '2025-07', (record) => record).map((record) => record.id)).toEqual(['2025-07']);
    expect(filterByReportingPeriod(records, 'July', (record) => record).map((record) => record.id)).toEqual(['2026-07']);
    expect(previousReportingSelector(records, '2026-01')).toBe('2025-12');
    expect(previousReportingSelector(records, '2026-07')).toBe('2026-01');
  });
});

describe('overview period selector', () => {
  it('prefers a valid exact period over the month name', () => {
    expect(overviewPeriodSelector('2025-07', 'July')).toBe('2025-07');
    expect(overviewPeriodSelector('2026-13', 'June')).toBe('June');
    expect(overviewPeriodSelector(null, 'All')).toBe('All');
    expect(monthNameFromPeriodKey('2025-07')).toBe('July');
  });
});
