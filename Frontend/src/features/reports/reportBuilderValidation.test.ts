import { describe, expect, it } from 'vitest';
import {
  generatedReportName,
  previousAvailablePeriod,
  validateReportScope,
} from './reportBuilderValidation';

const periods = [
  { year: 2026, month: 'June', key: '2026-06' },
  { year: 2026, month: 'May', key: '2026-05' },
  { year: 2026, month: 'April', key: '2026-04' },
];

describe('report builder scope validation', () => {
  it('accepts a named report with an earlier explicit comparison period', () => {
    expect(validateReportScope({
      report_name: 'June Operations Review', start_month: 'June', start_year: 2026,
      end_month: 'May', end_year: 2026,
    })).toEqual({});
  });

  it('explains every blocked field instead of silently ignoring Next', () => {
    expect(validateReportScope({
      report_name: ' ', start_month: 'May', start_year: 2026,
      end_month: 'June', end_year: 2026,
    })).toEqual({
      report_name: 'Enter a clear report name to continue.',
      comparison_period: 'The comparison period must be earlier than the reporting period.',
    });
  });

  it('selects the closest available earlier period and creates a useful default name', () => {
    expect(previousAvailablePeriod(periods, periods[0])).toEqual(periods[1]);
    expect(generatedReportName(periods[0])).toBe('June 2026 Monthly Performance Review');
  });
});
