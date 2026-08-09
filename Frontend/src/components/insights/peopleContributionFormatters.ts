export function formatContributionMetric(
  value: number | null,
  target: number | null,
  unit: string | null,
  signed = false,
) {
  if (value === null) return 'N/A';

  const percentageScale = unit === '%' && target !== null && target > 0 && target <= 1;
  const display = percentageScale ? value * 100 : value;
  const prefix = signed && display > 0 ? '+' : '';

  if (unit === '%') return `${prefix}${display.toFixed(1)}%`;

  const formattedValue = display.toLocaleString(undefined, { maximumFractionDigits: 2 });
  return `${prefix}${formattedValue}${unit ? ` ${unit}` : ''}`;
}
