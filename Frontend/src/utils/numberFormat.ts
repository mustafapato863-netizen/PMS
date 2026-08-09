export function formatReportNumber(
  value: number | string | null | undefined,
  unit?: string
): string {
  if (value === null || value === undefined) return 'N/A';

  let numericValue: number;
  if (typeof value === 'string') {
    const parsed = parseFloat(value.replace(/,/g, ''));
    if (isNaN(parsed)) return value;
    numericValue = parsed;
  } else {
    numericValue = value;
  }

  const absValue = Math.abs(numericValue);
  let formatted = absValue >= 1_000_000_000
    ? (numericValue / 1_000_000_000).toFixed(2) + 'B'
    : absValue >= 1_000_000
      ? (numericValue / 1_000_000).toFixed(2) + 'M'
      : absValue >= 1_000
        ? (numericValue / 1_000).toFixed(2) + 'K'
        : numericValue % 1 !== 0 ? numericValue.toFixed(2) : numericValue.toString();

  // Remove unnecessary trailing zeros
  formatted = formatted.replace(/\.00([KMB])?$/, '$1').replace(/(\.\d)0([KMB])?$/, '$1$2');
  if (formatted.endsWith('.00')) {
     formatted = formatted.replace('.00', '');
  } else if (formatted.match(/\.\d0$/)) {
     formatted = formatted.slice(0, -1);
  }

  if (unit) {
    if (unit.trim().toLowerCase() === '%') {
      return `${formatted}%`;
    }
    if (/^[a-zA-Z]{2,3}$/.test(unit.trim())) {
      return `${unit.trim()} ${formatted}`;
    }
    return `${formatted} ${unit.trim()}`;
  }

  return formatted;
}
