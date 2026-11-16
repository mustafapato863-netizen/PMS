/** Keep percentage score charts within a readable range when scores exceed 100. */
export function percentageScoreAxisMax(highest: number): number {
  if (!Number.isFinite(highest) || highest <= 100) return 100;
  const step = 5;
  const rounded = Math.ceil(highest / step) * step;
  return rounded > highest ? rounded : rounded + step;
}

/** Return the 0%, 25%, 50%, 75%, and 100% Y-axis ticks for a percentage score scale. */
export function percentageScoreAxisTicks(axisMax: number): number[] {
  const safeMax = Number.isFinite(axisMax) && axisMax > 0 ? axisMax : 100;
  return [0, 0.25, 0.5, 0.75, 1].map((fraction) => Math.round(safeMax * fraction));
}
