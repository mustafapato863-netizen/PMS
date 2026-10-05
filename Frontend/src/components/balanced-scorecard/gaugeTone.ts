import { getGradeTone, type GradeClass } from '../../constants/grades';

/**
 * Score tone for BSC gauges and the Overall Performance card.
 * Maps score → getGradeClass(score) → `--pms-grade-*` tokens (A–E palette).
 * All values are CSS-variable references so light/dark themes both apply.
 */
export interface GaugeTone {
  /** A–E grade, or null when there is no usable score. */
  grade: GradeClass | null;
  /** Gauge arc / fill / accent color (`--pms-grade-*-gauge`). */
  color: string;
  /** Score % and label text color (`--pms-grade-*-text`). */
  text: string;
  /** Glow used for arc halo and panel shadow (`--pms-grade-*-glow`). */
  glow: string;
  /** Grade label, e.g. "Below Average"; "No data" when score is missing. */
  label: string;
  /** Soft badge background (`--pms-grade-*-badge-bg`). */
  background: string;
  /** Soft badge text (`--pms-grade-*-badge-text`). */
  badgeText: string;
  /** Soft badge border (`--pms-grade-*-border`). */
  border: string;
}

export function getGaugeTone(score: number | null | undefined): GaugeTone {
  const tone = getGradeTone(score);
  return {
    grade: tone.grade,
    color: tone.gauge,
    text: tone.text,
    glow: tone.glow,
    label: tone.label,
    background: tone.badgeBg,
    badgeText: tone.badgeText,
    border: tone.border,
  };
}
