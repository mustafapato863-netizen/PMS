import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  GRADE_CLASSES,
  GRADE_PALETTE,
  GRADE_THRESHOLDS,
  getGradeClass,
  getGradeClassOrNull,
  getGradeTone,
  gradeTokenVar,
  type GradeClass,
} from './grades';

// Approved palette (pms-grade-palette/tokens.json, light UI).
// Grade B updated to light green by Figma csZO4wbWLnLOcHHmGUnQ0X ("PMS grade palette", node 2:3),
// fill deepened to #5C992B for WCAG AA non-text contrast.
const APPROVED: Record<GradeClass, { label: string; text: string; gauge: string }> = {
  A: { label: 'Excellent', text: '#0A6B3C', gauge: '#0E8749' },
  B: { label: 'Meet Expectations', text: '#3F6F20', gauge: '#5C992B' },
  C: { label: 'Average', text: '#8A5200', gauge: '#A66800' },
  D: { label: 'Below Average', text: '#A84808', gauge: '#C35410' },
  E: { label: 'Unsatisfactory', text: '#B42318', gauge: '#D92D20' },
};

const indexCss = readFileSync(resolve(__dirname, '../index.css'), 'utf8');

/** Values declared in the first (light) `:root` block of index.css. */
function lightRootTokens(): Record<string, string> {
  const start = indexCss.indexOf(':root {');
  const end = indexCss.indexOf('\n}', start);
  const block = indexCss.slice(start, end);
  const tokens: Record<string, string> = {};
  for (const match of block.matchAll(/(--pms-grade-[a-z]+-[a-z-]+):\s*([^;]+);/g)) {
    tokens[match[1]] = match[2].trim();
  }
  return tokens;
}

/** Grade tokens declared in the `.dark` block of index.css. */
function darkTokens(): Record<string, string> {
  const start = indexCss.indexOf('.dark {');
  const end = indexCss.indexOf('\n}', start);
  const block = indexCss.slice(start, end);
  const tokens: Record<string, string> = {};
  for (const match of block.matchAll(/(--pms-grade-[a-z]+-[a-z-]+):\s*([^;]+);/g)) {
    tokens[match[1]] = match[2].trim();
  }
  return tokens;
}

type Rgba = [number, number, number, number];

function parseColor(value: string): Rgba {
  const hex = value.match(/^#([0-9a-f]{6})$/i);
  if (hex) return [0, 2, 4].map((i) => parseInt(hex[1].slice(i, i + 2), 16)).concat(1) as Rgba;
  const rgba = value.match(/^rgba?\(([^)]+)\)$/i);
  if (!rgba) throw new Error(`Unsupported colour ${value}`);
  const [r, g, b, a = '1'] = rgba[1].split(',').map((part) => part.trim());
  return [Number(r), Number(g), Number(b), Number(a)];
}

function composite(color: string, base: Rgba): Rgba {
  const [r, g, b, a] = parseColor(color);
  return [r * a + base[0] * (1 - a), g * a + base[1] * (1 - a), b * a + base[2] * (1 - a), 1];
}

function luminance([r, g, b]: Rgba) {
  const channel = (v: number) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** WCAG 2.x contrast of `fg` over `bg`, with translucent colours composited over `surface`. */
function contrast(fg: string, bg: string, surface = '#FFFFFF') {
  const background = composite(bg, parseColor(surface));
  const foreground = composite(fg, background);
  const [high, low] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
  return (high + 0.05) / (low + 0.05);
}

describe('grade thresholds', () => {
  it('uses the Frontend 95 / 90 / 80 / 70 cutoffs', () => {
    expect(GRADE_THRESHOLDS).toEqual({ A: 95, B: 90, C: 80, D: 70 });
  });

  it.each([
    [100, 'A'],
    [95, 'A'],
    [94.999, 'B'],
    [90, 'B'],
    [89.99, 'C'],
    [80, 'C'],
    [79.99, 'D'],
    [70.3, 'D'],
    [70, 'D'],
    [69.999, 'E'],
    [0, 'E'],
  ] as const)('grades %s as %s (inclusive lower bounds)', (score, grade) => {
    expect(getGradeClass(score)).toBe(grade);
  });

  it('returns null for missing or non-finite scores', () => {
    expect(getGradeClassOrNull(null)).toBeNull();
    expect(getGradeClassOrNull(undefined)).toBeNull();
    expect(getGradeClassOrNull(Number.NaN)).toBeNull();
    expect(getGradeClassOrNull(Number.POSITIVE_INFINITY)).toBeNull();
    expect(getGradeClassOrNull(70.3)).toBe('D');
  });
});

describe('grade labels', () => {
  it.each(GRADE_CLASSES)('labels grade %s per the approved scale', (grade) => {
    expect(GRADE_PALETTE[grade].label).toBe(APPROVED[grade].label);
  });

  it('uses "Excellent" (not "Excellence") for grade A', () => {
    expect(GRADE_PALETTE.A.label).toBe('Excellent');
    expect(JSON.stringify(GRADE_PALETTE)).not.toMatch(/Excellence/);
  });

  it('never labels a score "Good"', () => {
    for (const score of [99, 92, 85, 75, 70.3, 60, 10]) {
      expect(getGradeTone(score).label).not.toBe('Good');
    }
  });
});

describe('grade color mapping', () => {
  it.each(GRADE_CLASSES)('grade %s text / gauge hex match the approved tokens', (grade) => {
    expect(GRADE_PALETTE[grade].text).toBe(APPROVED[grade].text);
    expect(GRADE_PALETTE[grade].gauge).toBe(APPROVED[grade].gauge);
  });

  it('keeps GRADE_PALETTE in lock-step with --pms-grade-* in index.css', () => {
    const css = lightRootTokens();
    for (const grade of GRADE_CLASSES) {
      const g = grade.toLowerCase();
      const p = GRADE_PALETTE[grade];
      expect(css[`--pms-grade-${g}-text`]).toBe(p.text);
      expect(css[`--pms-grade-${g}-badge-bg`]).toBe(p.background);
      expect(css[`--pms-grade-${g}-badge-text`]).toBe(p.text);
      expect(css[`--pms-grade-${g}-border`]).toBe(p.border);
      expect(css[`--pms-grade-${g}-solid`]).toBe(p.solid);
      expect(css[`--pms-grade-${g}-solid-text`]).toBe(p.solidText);
      expect(css[`--pms-grade-${g}-gauge`]).toBe(p.gauge);
      expect(css[`--pms-grade-${g}-glow`]).toBe(p.glow);
    }
  });

  it('aliases legacy --grade-* variables to the palette tokens', () => {
    for (const g of ['a', 'b', 'c', 'd', 'e']) {
      expect(indexCss).toContain(`--grade-${g}-text: var(--pms-grade-${g}-text);`);
      expect(indexCss).toContain(`--grade-${g}-bg: var(--pms-grade-${g}-badge-bg);`);
      expect(indexCss).toContain(`--grade-${g}-border: var(--pms-grade-${g}-border);`);
    }
  });

  it('builds CSS variable references for grade tokens', () => {
    expect(gradeTokenVar('D', 'gauge')).toBe('var(--pms-grade-d-gauge)');
    expect(gradeTokenVar('A', 'badge-bg')).toBe('var(--pms-grade-a-badge-bg)');
    expect(gradeTokenVar(null, 'text')).toBe('var(--pms-grade-na-text)');
  });

  it('uses Figma light green for grade B with dark (AA) solid text', () => {
    expect(GRADE_PALETTE.B).toMatchObject({
      text: '#3F6F20',
      background: '#EFF8E8',
      solid: '#5C992B',
      solidText: '#14240A',
      gauge: '#5C992B',
    });
  });

  it('keeps every grade B pair WCAG AA in light and dark mode', () => {
    const light = lightRootTokens();
    const dark = darkTokens();
    const lightSurfaces = ['#FFFFFF', '#F3F7FA', '#F8FBFE', '#F8FAFC', '#E9F0F5'];
    const darkSurfaces = ['#0F1A2E', '#0B132B', '#10203A', '#131D2F'];
    const darkSolid = dark['--pms-grade-b-solid'] ?? light['--pms-grade-b-solid'];
    const darkSolidText = dark['--pms-grade-b-solid-text'] ?? light['--pms-grade-b-solid-text'];

    // Text (normal size) ≥ 4.5:1.
    expect(contrast(light['--pms-grade-b-badge-text'], light['--pms-grade-b-badge-bg'])).toBeGreaterThanOrEqual(4.5);
    expect(contrast(light['--pms-grade-b-solid-text'], light['--pms-grade-b-solid'])).toBeGreaterThanOrEqual(4.5);
    for (const surface of lightSurfaces) {
      expect(contrast(light['--pms-grade-b-text'], surface)).toBeGreaterThanOrEqual(4.5);
      // Solid / gauge fills ≥ 3:1 against the surface they sit on.
      expect(contrast(light['--pms-grade-b-solid'], surface)).toBeGreaterThanOrEqual(3);
      expect(contrast(light['--pms-grade-b-gauge'], surface)).toBeGreaterThanOrEqual(3);
    }
    expect(contrast(darkSolidText, darkSolid)).toBeGreaterThanOrEqual(4.5);
    for (const surface of darkSurfaces) {
      expect(contrast(dark['--pms-grade-b-badge-text'], dark['--pms-grade-b-badge-bg'], surface)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(dark['--pms-grade-b-text'], surface)).toBeGreaterThanOrEqual(4.5);
      expect(contrast(dark['--pms-grade-b-gauge'], surface)).toBeGreaterThanOrEqual(3);
      expect(contrast(darkSolid, surface)).toBeGreaterThanOrEqual(3);
    }
  });

  it('maps 70.3% to the D / Below Average orange tokens', () => {
    const tone = getGradeTone(70.3);
    expect(tone.grade).toBe('D');
    expect(tone.label).toBe('Below Average');
    expect(tone.text).toBe('var(--pms-grade-d-text)');
    expect(tone.gauge).toBe('var(--pms-grade-d-gauge)');
    expect(tone.badgeBg).toBe('var(--pms-grade-d-badge-bg)');
  });

  it('maps missing scores to the N/A tokens', () => {
    const tone = getGradeTone(null);
    expect(tone.grade).toBeNull();
    expect(tone.label).toBe('No data');
    expect(tone.gauge).toBe('var(--pms-grade-na-gauge)');
  });
});
