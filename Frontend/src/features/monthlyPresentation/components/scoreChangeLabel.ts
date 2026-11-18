export function formatScoreChangeLabel(
  changeVsPrev: number | null | undefined,
  previousPeriodLabel: string | null | undefined,
): string {
  if (changeVsPrev === null || changeVsPrev === undefined || !Number.isFinite(changeVsPrev)) {
    return 'No prior period score';
  }
  const signed = `${changeVsPrev >= 0 ? '+' : ''}${changeVsPrev.toFixed(1)} pts`;
  return previousPeriodLabel ? `${signed} vs ${previousPeriodLabel}` : `${signed} vs prior period`;
}
