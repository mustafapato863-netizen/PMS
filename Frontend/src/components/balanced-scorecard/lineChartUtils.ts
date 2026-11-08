/** Keep percentage score charts within a readable range when scores exceed 100. */
export function percentageScoreAxisMax(highest: number): number {
  if (!Number.isFinite(highest) || highest <= 100) return 100;
  const step = 5;
  const rounded = Math.ceil(highest / step) * step;
  return rounded > highest ? rounded : rounded + step;
}
