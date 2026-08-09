import type { AgentRecord } from '../../types';

const MONTH_ORDER: Record<string, number> = {
  January: 1,
  February: 2,
  March: 3,
  April: 4,
  May: 5,
  June: 6,
  July: 7,
  August: 8,
  September: 9,
  October: 10,
  November: 11,
  December: 12,
};

export type EmployeeHistoryRecord = AgentRecord & { month: string };

const periodKey = (record: EmployeeHistoryRecord): string =>
  `${record.year ?? 0}:${record.month}`;

export const compareEmployeePeriods = (
  left: EmployeeHistoryRecord,
  right: EmployeeHistoryRecord,
): number => {
  const yearDifference = (left.year ?? 0) - (right.year ?? 0);
  if (yearDifference !== 0) return yearDifference;
  return (MONTH_ORDER[left.month] ?? 0) - (MONTH_ORDER[right.month] ?? 0);
};

/**
 * Merges the SQL profile response with the already-cached performance feed.
 * The profile endpoint wins for duplicate periods because it contains the
 * canonical persisted KPI breakdown; the feed keeps history visible during
 * a transient profile request failure or a rolling frontend/backend deploy.
 */
export const mergeEmployeeHistory = (
  employeeId: string | undefined,
  feedRecords: AgentRecord[],
  profileRecords: EmployeeHistoryRecord[],
): EmployeeHistoryRecord[] => {
  if (!employeeId) return [];

  const recordsByPeriod = new Map<string, EmployeeHistoryRecord>();
  feedRecords
    .filter((record) => String(record.identity.employee_id ?? '') === String(employeeId))
    .forEach((record) => {
      const normalized = {
        ...record,
        month: record.identity.month,
      } as EmployeeHistoryRecord;
      recordsByPeriod.set(periodKey(normalized), normalized);
    });

  profileRecords.forEach((record) => recordsByPeriod.set(periodKey(record), record));

  return [...recordsByPeriod.values()].sort((left, right) => compareEmployeePeriods(right, left));
};
