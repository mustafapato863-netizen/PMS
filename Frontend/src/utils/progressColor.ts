const clamp = (n: number, min = 0, max = 100) => Math.min(max, Math.max(min, n));

const mix = (a: number, b: number, t: number) => Math.round(a + (b - a) * t);

const hexToRgb = (hex: string) => {
  const clean = hex.replace('#', '');
  const full = clean.length === 3
    ? clean.split('').map((c) => c + c).join('')
    : clean;
  const value = parseInt(full, 16);
  return {
    r: (value >> 16) & 255,
    g: (value >> 8) & 255,
    b: value & 255,
  };
};

const rgbToHex = (r: number, g: number, b: number) => `#${[r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('')}`;

const lerpHex = (from: string, to: string, t: number) => {
  const a = hexToRgb(from);
  const b = hexToRgb(to);
  return rgbToHex(mix(a.r, b.r, t), mix(a.g, b.g, t), mix(a.b, b.b, t));
};

export const getProgressColor = (achievementPercentage: number) => {
  const pct = clamp(achievementPercentage);
  if (pct >= 100) return '#7c3aed';
  if (pct >= 75) return lerpHex('#22c55e', '#7c3aed', (pct - 75) / 25);
  if (pct >= 50) return lerpHex('#eab308', '#22c55e', (pct - 50) / 25);
  if (pct >= 25) return lerpHex('#f97316', '#eab308', (pct - 25) / 25);
  return lerpHex('#ef4444', '#f97316', pct / 25);
};

export const getProgressFill = (achievementPercentage: number) => clamp(achievementPercentage);
