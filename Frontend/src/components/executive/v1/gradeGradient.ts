import { getGradeClassOrNull } from '../../../constants/grades';

/** Grade-gradient CSS variable for a score (95/90/80/70 palette). */
export function gradeGradientVar(score: number | null | undefined): string {
  const grade = getGradeClassOrNull(score ?? null);
  return `var(--pms-grad-grade-${grade ? grade.toLowerCase() : 'na'})`;
}
