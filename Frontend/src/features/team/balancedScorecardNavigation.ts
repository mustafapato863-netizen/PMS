/** Balanced Scorecard mode is the Corporate level only. Employee and Managerial rows use the department dashboard. */
export function isCorporateBalancedScorecard(
  teamName: string | null | undefined,
  performanceLevel: string | null | undefined,
): boolean {
  return Boolean(teamName) && performanceLevel === 'Corporate';
}
