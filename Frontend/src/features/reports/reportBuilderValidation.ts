import type { ReportConfiguration, ReportPeriod } from './types';

const MONTH_INDEX = new Map([
  ['january', 0], ['february', 1], ['march', 2], ['april', 3], ['may', 4], ['june', 5],
  ['july', 6], ['august', 7], ['september', 8], ['october', 9], ['november', 10], ['december', 11],
]);

export type ScopeValidationErrors = Partial<Record<'report_name' | 'primary_period' | 'comparison_period', string>>;

export function periodOrdinal(year?: number | null, month?: string | null): number | null {
  if (!year || !month) return null;
  const monthIndex = MONTH_INDEX.get(month.toLowerCase());
  return monthIndex === undefined ? null : year * 12 + monthIndex;
}

export function isComparisonBeforePrimary(configuration: Partial<ReportConfiguration>): boolean {
  const primary = periodOrdinal(configuration.start_year, configuration.start_month);
  const comparison = periodOrdinal(configuration.end_year, configuration.end_month);
  return primary !== null && comparison !== null && comparison < primary;
}

export function validateReportScope(configuration: Partial<ReportConfiguration>): ScopeValidationErrors {
  const errors: ScopeValidationErrors = {};
  if (!configuration.report_name?.trim()) errors.report_name = 'Enter a clear report name to continue.';
  if (periodOrdinal(configuration.start_year, configuration.start_month) === null) {
    errors.primary_period = 'Select the reporting period.';
  }
  if (periodOrdinal(configuration.end_year, configuration.end_month) === null) {
    errors.comparison_period = 'Select a comparison period.';
  } else if (!isComparisonBeforePrimary(configuration)) {
    errors.comparison_period = 'The comparison period must be earlier than the reporting period.';
  }
  return errors;
}

export function previousAvailablePeriod(periods: ReportPeriod[], primary: ReportPeriod): ReportPeriod | undefined {
  const primaryOrdinal = periodOrdinal(primary.year, primary.month);
  return periods.find((period) => {
    const candidate = periodOrdinal(period.year, period.month);
    return candidate !== null && primaryOrdinal !== null && candidate < primaryOrdinal;
  });
}

export function generatedReportName(period: Pick<ReportPeriod, 'month' | 'year'>): string {
  return `${period.month} ${period.year} Monthly Performance Review`;
}

export function isGeneratedReportName(value?: string | null): boolean {
  return !value?.trim() || /^[A-Za-z]+\s+\d{4}\s+Monthly Performance Review$/.test(value.trim());
}
