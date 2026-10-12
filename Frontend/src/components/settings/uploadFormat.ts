/** The string entries of a list, or none when the value is not a list. */
export function asArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];
}

/** A locale date and time, or the raw text when it does not parse. */
export function formatDate(value?: string | null) {
  if (!value) return 'Unknown date';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
