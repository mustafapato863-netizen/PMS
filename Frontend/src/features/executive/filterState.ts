/** Older dashboards encode an unfiltered selection as "All" in their URLs. */
export function summaryFilterValue(value: string | null): string | undefined {
  const trimmed = value?.trim();
  return !trimmed || trimmed.toLowerCase() === 'all' ? undefined : trimmed;
}
