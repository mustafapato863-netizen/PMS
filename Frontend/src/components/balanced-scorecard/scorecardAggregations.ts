type ScoreHistoryPoint = {
  year?: number | null;
  score?: number | null;
};

/** Return the mean of measured monthly scores for one selected year. */
export function averageScoreForYear(
  history: readonly ScoreHistoryPoint[],
  year: number | string | null | undefined,
): number | null {
  const selectedYear = Number(year);
  if (!Number.isFinite(selectedYear)) return null;

  const scores = history
    .filter((point) => point.year === selectedYear)
    .map((point) => point.score)
    .filter((score): score is number => typeof score === 'number' && Number.isFinite(score));

  if (!scores.length) return null;
  return scores.reduce((total, score) => total + score, 0) / scores.length;
}
