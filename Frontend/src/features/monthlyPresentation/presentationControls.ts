import { normalizeRegion } from '../executive/compose';
import { isMonthAvailable, periodFromKey } from './model';

export function presentationMonthOptions(
  records: Array<{ region: string | null; periodKey: string }>,
  region: 'EGY' | 'UAE',
  today: Date,
  displayedKey: string,
): Array<{ key: string; label: string }> {
  const keys = new Set<string>();
  const include = (key: string | null | undefined) => {
    const period = periodFromKey(key);
    if (!period || !isMonthAvailable(period.key, today)) return;
    keys.add(period.key);
  };

  for (const record of records) {
    if (normalizeRegion(record.region) !== region) continue;
    include(record.periodKey);
  }
  include(displayedKey);

  return [...keys]
    .sort((left, right) => right.localeCompare(left))
    .map((key) => ({ key, label: periodFromKey(key)!.label }));
}

export function stepPresentation(input: {
  slugs: string[];
  currentSlug: string;
  direction: 'next' | 'previous';
  insideDetail: boolean;
}): { slug: string | null; clearDetail: boolean } {
  const { slugs, currentSlug, direction, insideDetail } = input;
  const index = slugs.indexOf(currentSlug);

  // Prev/Next never walks into a team or role. Leaving a detail returns to the function line.
  if (insideDetail && currentSlug) {
    if (direction === 'previous' || index < 0 || index >= slugs.length - 1) {
      return { slug: currentSlug, clearDetail: true };
    }
    return { slug: slugs[index + 1], clearDetail: true };
  }

  if (direction === 'previous') {
    return { slug: index > 0 ? slugs[index - 1] : null, clearDetail: false };
  }
  if (index < 0) return { slug: slugs[0] ?? null, clearDetail: false };
  if (index >= slugs.length - 1) return { slug: slugs[index], clearDetail: false };
  return { slug: slugs[index + 1], clearDetail: false };
}
