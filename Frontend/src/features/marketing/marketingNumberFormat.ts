const PERCENT_UNITS = new Set(['%', 'percent', 'percentage']);
const COUNT_UNITS = new Set(['count', 'visits']);
const CURRENCY_UNITS = new Set(['aed', 'currency']);
const INVALID_UNIT = /^(none|null|undefined|nan)$/i;

export const cleanUnit = (unit: string | null | undefined): string => {
  const trimmed = String(unit ?? '').trim();
  return INVALID_UNIT.test(trimmed) ? '' : trimmed;
};

const normalizePercent = (value: number) => (Math.abs(value) <= 1 ? value * 100 : value);

const trimZeros = (value: string) => (
  value.includes('.') ? value.replace(/\.?0+$/, '') : value
);

const compactNumber = (value: number): string => {
  const absolute = Math.abs(value);
  const scale = absolute >= 1_000_000_000
    ? { divisor: 1_000_000_000, suffix: 'B' }
    : absolute >= 1_000_000
      ? { divisor: 1_000_000, suffix: 'M' }
      : absolute >= 1_000
        ? { divisor: 1_000, suffix: 'K' }
        : null;
  if (!scale) {
    return trimZeros(value.toFixed(Number.isInteger(value) ? 0 : 2));
  }
  return `${trimZeros((value / scale.divisor).toFixed(2))}${scale.suffix}`;
};

const fullNumber = (value: number, minimumFractionDigits: number, maximumFractionDigits: number) => (
  new Intl.NumberFormat('en-US', { minimumFractionDigits, maximumFractionDigits }).format(value)
);

export interface MarketingFormattedValue {
  display: string;
  exact: string;
}

export const formatMarketingValue = (
  value: number | null,
  unit: string | null | undefined,
): MarketingFormattedValue => {
  if (value === null || !Number.isFinite(value)) return { display: '—', exact: 'Unavailable' };
  const cleaned = cleanUnit(unit);
  const normalizedUnit = cleaned.toLowerCase();
  if (!normalizedUnit || PERCENT_UNITS.has(normalizedUnit)) {
    const percentage = normalizePercent(value);
    return {
      display: `${trimZeros(percentage.toFixed(2))}%`,
      exact: `${fullNumber(percentage, 2, 2)}%`,
    };
  }
  if (CURRENCY_UNITS.has(normalizedUnit)) {
    return {
      display: `AED ${compactNumber(value)}`,
      exact: `AED ${fullNumber(value, 2, 2)}`,
    };
  }
  if (COUNT_UNITS.has(normalizedUnit)) {
    return {
      display: compactNumber(value),
      exact: fullNumber(value, Number.isInteger(value) ? 0 : 2, 2),
    };
  }
  const suffix = cleaned;
  return {
    display: `${compactNumber(value)}${suffix ? ` ${suffix}` : ''}`,
    exact: `${fullNumber(value, 2, 2)}${suffix ? ` ${suffix}` : ''}`,
  };
};

export const formatMarketingGapValue = (value: number, unit: string | null | undefined): string => {
  const cleaned = cleanUnit(unit);
  if (!cleaned || PERCENT_UNITS.has(cleaned.toLowerCase())) {
    return `${trimZeros(normalizePercent(value).toFixed(2))}%`;
  }
  return formatMarketingValue(value, cleaned).display;
};
