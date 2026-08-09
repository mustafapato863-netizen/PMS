/**
 * Unified Grade Thresholds
 * Single source of truth for all grade calculations across Frontend and Backend.
 * These thresholds are used in:
 * - Frontend: type definitions, UI badge colors, analytics calculations
 * - Backend: kpi_service.py performance score grading
 */

export const GRADE_THRESHOLDS = {
  A: 95,
  B: 90,
  C: 80,
  D: 70,
} as const;

export type GradeClass = 'A' | 'B' | 'C' | 'D' | 'E';

export const GRADE_PALETTE: Record<GradeClass, {
  label: string;
  statusLabel: string;
  text: string;
  background: string;
  border: string;
}> = {
  A: { label: 'Excellent', statusLabel: 'Excellent', text: '#0F8A4B', background: '#E9F9EF', border: '#B7E8C8' },
  B: { label: 'Meet Expectations', statusLabel: 'Meet', text: '#2563EB', background: '#EAF2FF', border: '#BED6FF' },
  C: { label: 'Average', statusLabel: 'Average', text: '#B7791F', background: '#FFF7E6', border: '#F3D59B' },
  D: { label: 'Below Average', statusLabel: 'Below', text: '#C56A1A', background: '#FFF1E8', border: '#F6C8A6' },
  E: { label: 'Unsatisfactory', statusLabel: 'Critical', text: '#D92D20', background: '#FEECEC', border: '#F6C1BE' },
};

/**
 * Determine grade class based on score.
 * @param score - Performance score (0-100 scale)
 * @returns Grade class (A, B, C, D, or E)
 */
export function getGradeClass(score: number): GradeClass {
  if (score >= GRADE_THRESHOLDS.A) return 'A';
  if (score >= GRADE_THRESHOLDS.B) return 'B';
  if (score >= GRADE_THRESHOLDS.C) return 'C';
  if (score >= GRADE_THRESHOLDS.D) return 'D';
  return 'E';
}
