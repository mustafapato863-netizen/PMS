/**
 * A KPI counts in a performance score when its stored weight is above zero.
 * Tracking-only indicators (weight 0) and KPIs that do not apply to a month stay
 * out of score lists, counts and footers. Use this one rule everywhere.
 */
export function kpiCountsInScore(weight: number | null | undefined): boolean {
  return typeof weight === 'number' && Number.isFinite(weight) && weight > 0;
}
