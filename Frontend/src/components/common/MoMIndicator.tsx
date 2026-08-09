import { Minus, TrendingDown, TrendingUp } from 'lucide-react';

interface MoMIndicatorProps {
  delta: number | null | undefined;
  lowerIsBetter?: boolean;
  showStable?: boolean;
  className?: string;
}

const MoMIndicator = ({
  delta,
  lowerIsBetter = false,
  showStable = false,
  className = '',
}: MoMIndicatorProps) => {
  if (delta === null || delta === undefined || !Number.isFinite(delta)) return null;

  const stable = delta === 0;
  if (stable && !showStable) return null;

  const down = delta < 0;
  const good = lowerIsBetter ? down : !down;
  const Icon = stable ? Minus : down ? TrendingDown : TrendingUp;

  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold ${
      stable
        ? 'text-[var(--text-muted)]'
        : good
          ? 'text-emerald-600 dark:text-emerald-400'
          : 'text-rose-600 dark:text-rose-500'
    } ${className}`}>
      <Icon size={12} />
      <span>{delta > 0 ? '+' : ''}{delta.toFixed(1)}% MoM</span>
    </span>
  );
};

export default MoMIndicator;
