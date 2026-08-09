
interface SparklineProps {
  points: (number | null)[];
  up: boolean;
}

export function Sparkline({ points, up }: SparklineProps) {
  const valid = points.filter((p): p is number => p != null);
  if (valid.length < 2) return <svg className="bsc-spark"/>;
  const min = Math.min(...valid);
  const max = Math.max(...valid);
  const range = max - min || 1;
  const W = 64, H = 24, P = 2;
  const xs = points.map((_, i) => P + (i / (points.length - 1)) * (W - P * 2));
  const ys = points.map(p => p == null ? null : H - P - ((p - min) / range) * (H - P * 2));
  const d  = xs.reduce((acc, x, i) => {
    const y = ys[i]; if (y == null) return acc;
    return acc + (acc === '' ? `M${x},${y}` : ` L${x},${y}`);
  }, '');

  return (
    <svg width={W} height={H} className="bsc-spark" viewBox={`0 0 ${W} ${H}`}>
      <path d={d} fill="none" stroke={up ? '#1A8C53' : '#D03B3B'} strokeWidth="1.5" strokeLinejoin="round"/>
    </svg>
  );
}

export default Sparkline;
