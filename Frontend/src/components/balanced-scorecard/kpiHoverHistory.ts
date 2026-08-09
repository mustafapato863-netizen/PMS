import type { KpiHoverData } from './KpiTrendHoverCard';

export function resolveKpiHoverHistory(
  hoveredHistory: KpiHoverData['history'] | undefined,
  selectedHistory: KpiHoverData['history'] | undefined,
): KpiHoverData['history'] | undefined {
  if (hoveredHistory && hoveredHistory.length > 0) return hoveredHistory;
  if (selectedHistory && selectedHistory.length > 0) return selectedHistory;
  return undefined;
}
