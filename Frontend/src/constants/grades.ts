/**
 * Unified Grade Thresholds
 * Single source of truth for all grade calculations across Frontend and Backend.
 * These thresholds are used in:
 * - Frontend: type definitions, UI badge colors, analytics calculations
 * - Backend: kpi_service.py performance score grading
 *
 * Grade colors come from the PMS grade palette tokens (`--pms-grade-*`,
 * defined in `src/index.css`, source: pms-grade-palette/tokens.json).
 * Every score-colored surface (gauges, score %, badges, pills, fills) maps
 * score → getGradeClass(score) → grade tokens. Do not introduce parallel
 * "Excellent / Good / Needs attention / Poor" score-color schemes.
 */

export const GRADE_THRESHOLDS = {
  A: 95,
  B: 90,
  C: 80,
  D: 70,
} as const;

export type GradeClass = 'A' | 'B' | 'C' | 'D' | 'E';

export const GRADE_CLASSES: readonly GradeClass[] = ['A', 'B', 'C', 'D', 'E'] as const;

export interface GradePresentation {
  /** Employee-facing grade label, e.g. "Excellent", "Below Average". */
  label: string;
  /** Short status vocabulary used in compact status badges. */
  statusLabel: string;
  /** Score % / soft badge text color (`--pms-grade-*-text`). */
  text: string;
  /** Soft badge background (`--pms-grade-*-badge-bg`). */
  background: string;
  /** Soft badge border (`--pms-grade-*-border`). */
  border: string;
  /** Solid badge fill (`--pms-grade-*-solid`). */
  solid: string;
  /** Text on solid badge (`--pms-grade-*-solid-text`). */
  solidText: string;
  /** Gauge arcs, bars, chart fills (`--pms-grade-*-gauge`). */
  gauge: string;
  /** Gauge / panel glow (`--pms-grade-*-glow`). */
  glow: string;
}

/**
 * Hex mirror of the light-theme `--pms-grade-*` tokens for consumers that
 * cannot resolve CSS variables (chart libraries, alpha math, exports).
 * Kept in lock-step with `src/index.css` by `grades.test.ts`.
 * Grade B is light green per Figma csZO4wbWLnLOcHHmGUnQ0X ("PMS grade palette"),
 * with the fill deepened from #A3D977 to #5C992B so it reaches 3:1 on light
 * surfaces; its solid-text is near-black green #14240A (white fails AA on it).
 * Prefer `getGradeTone()` / `gradeTokenVar()` for DOM styling so dark mode applies.
 */
export const GRADE_PALETTE: Record<GradeClass, GradePresentation> = {
  A: { label: 'Excellent', statusLabel: 'Excellent', text: '#0A6B3C', background: '#E3F6EC', border: '#8FD6AE', solid: '#0E8749', solidText: '#FFFFFF', gauge: '#0E8749', glow: 'rgba(14, 135, 73, 0.16)' },
  B: { label: 'Meet Expectations', statusLabel: 'Meet', text: '#3F6F20', background: '#EFF8E8', border: '#B8D99A', solid: '#5C992B', solidText: '#14240A', gauge: '#5C992B', glow: 'rgba(92, 153, 43, 0.16)' },
  C: { label: 'Average', statusLabel: 'Average', text: '#8A5200', background: '#FFF4DC', border: '#E6C06A', solid: '#A66800', solidText: '#FFFFFF', gauge: '#A66800', glow: 'rgba(166, 104, 0, 0.16)' },
  D: { label: 'Below Average', statusLabel: 'Below', text: '#A84808', background: '#FFEDE0', border: '#E8A878', solid: '#C35410', solidText: '#FFFFFF', gauge: '#C35410', glow: 'rgba(195, 84, 16, 0.16)' },
  E: { label: 'Unsatisfactory', statusLabel: 'Critical', text: '#B42318', background: '#FEECEC', border: '#F0A0A0', solid: '#D92D20', solidText: '#FFFFFF', gauge: '#D92D20', glow: 'rgba(217, 45, 32, 0.16)' },
};

/**
 * Determine grade class based on score.
 * Thresholds are inclusive lower bounds (70.0 → D, 69.999 → E).
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

const isScore = (score: number | null | undefined): score is number =>
  typeof score === 'number' && Number.isFinite(score);

/** Grade class for a possibly-missing score; `null` when there is no usable score. */
export function getGradeClassOrNull(score: number | null | undefined): GradeClass | null {
  return isScore(score) ? getGradeClass(score) : null;
}

export type GradeTokenRole =
  | 'text'
  | 'badge-bg'
  | 'badge-text'
  | 'solid'
  | 'solid-text'
  | 'gauge'
  | 'border'
  | 'glow';

/** `var(--pms-grade-<a..e|na>-<role>)` reference for inline styles / SVG. */
export function gradeTokenVar(grade: GradeClass | null, role: GradeTokenRole): string {
  const key = grade ? grade.toLowerCase() : 'na';
  return `var(--pms-grade-${key}-${role})`;
}

export interface GradeTone {
  grade: GradeClass | null;
  label: string;
  statusLabel: string;
  text: string;
  badgeBg: string;
  badgeText: string;
  border: string;
  solid: string;
  solidText: string;
  gauge: string;
  glow: string;
}

/**
 * Score → grade tone as CSS-variable references (theme aware).
 * Null / non-finite scores return the N/A tone labelled "No data".
 */
export function getGradeTone(score: number | null | undefined): GradeTone {
  const grade = getGradeClassOrNull(score);
  return {
    grade,
    label: grade ? GRADE_PALETTE[grade].label : 'No data',
    statusLabel: grade ? GRADE_PALETTE[grade].statusLabel : 'No data',
    text: gradeTokenVar(grade, 'text'),
    badgeBg: gradeTokenVar(grade, 'badge-bg'),
    badgeText: gradeTokenVar(grade, 'badge-text'),
    border: gradeTokenVar(grade, 'border'),
    solid: gradeTokenVar(grade, 'solid'),
    solidText: gradeTokenVar(grade, 'solid-text'),
    gauge: gradeTokenVar(grade, 'gauge'),
    glow: gradeTokenVar(grade, 'glow'),
  };
}
