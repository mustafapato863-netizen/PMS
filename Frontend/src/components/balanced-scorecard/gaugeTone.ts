export interface GaugeTone {
  color: string;
  glow: string;
  label: string;
  background: string;
}

export function getGaugeTone(score: number | null | undefined): GaugeTone {
  if (score == null || !Number.isFinite(score)) {
    return { color: '#8C96A5', glow: 'rgba(140, 150, 165, 0.14)', label: 'No data', background: 'var(--bsc-na-bg)' };
  }
  if (score >= 90) {
    return { color: '#1A8C53', glow: 'rgba(26, 140, 83, 0.18)', label: 'Excellent', background: 'var(--bsc-excellent-bg)' };
  }
  if (score >= 70) {
    return { color: '#1A9E72', glow: 'rgba(26, 158, 114, 0.16)', label: 'Good', background: 'var(--bsc-good-bg)' };
  }
  if (score >= 50) {
    return { color: '#C2740A', glow: 'rgba(194, 116, 10, 0.16)', label: 'Needs attention', background: 'var(--bsc-attention-bg)' };
  }
  return { color: '#D03B3B', glow: 'rgba(208, 59, 59, 0.16)', label: 'Poor', background: 'var(--bsc-poor-bg)' };
}
