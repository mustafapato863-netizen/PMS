import { AlertTriangle, ArrowDownRight, ArrowUpRight, CheckCircle2, Minus } from 'lucide-react';
import type { AiSpotlightMetricTile } from '../../../features/ai/types';

interface ExecutiveKpiStripProps {
  tiles: AiSpotlightMetricTile[];
  compact?: boolean;
}

const TONE_STYLES: Record<
  AiSpotlightMetricTile['tone'],
  {
    card: string;
    badge: string;
    value: string;
    Icon: typeof CheckCircle2;
  }
> = {
  good: {
    card: 'border-emerald-200/70 bg-emerald-50/35',
    badge: 'text-emerald-700',
    value: 'text-slate-900',
    Icon: ArrowUpRight,
  },
  warning: {
    card: 'border-amber-200/80 bg-amber-50/40',
    badge: 'text-amber-800',
    value: 'text-slate-900',
    Icon: AlertTriangle,
  },
  critical: {
    card: 'border-rose-200/80 bg-rose-50/40',
    badge: 'text-rose-700',
    value: 'text-rose-950',
    Icon: ArrowDownRight,
  },
  neutral: {
    card: 'border-slate-200/80 bg-slate-50/60',
    badge: 'text-slate-600',
    value: 'text-slate-900',
    Icon: Minus,
  },
};

export default function ExecutiveKpiStrip({ tiles, compact = false }: ExecutiveKpiStripProps) {
  if (!tiles || tiles.length === 0) return null;

  const gridColsClass = compact
    ? 'grid-cols-2'
    : tiles.length === 1
      ? 'grid-cols-1 sm:grid-cols-2'
      : tiles.length === 2
        ? 'grid-cols-2'
        : tiles.length === 3
          ? 'grid-cols-1 sm:grid-cols-3'
          : 'grid-cols-2 lg:grid-cols-4';

  return (
    <div
      data-testid="ai-executive-kpi-strip"
      className={`mt-3 grid gap-2.5 ${gridColsClass}`}
    >
      {tiles.map((tile, index) => {
        const style = TONE_STYLES[tile.tone] ?? TONE_STYLES.neutral;
        const StatusIcon = style.Icon;
        return (
          <div
            key={`${tile.label}-${index}`}
            className={`flex flex-col justify-between rounded-xl border px-3 py-2.5 transition-colors ${style.card}`}
          >
            <div className="flex items-center justify-between gap-1.5">
              <span className="truncate text-xs font-semibold text-slate-500">
                {tile.label}
              </span>
              <StatusIcon className={`size-3.5 shrink-0 ${style.badge}`} aria-hidden="true" />
            </div>
            <div
              className={`mt-1 font-extrabold tracking-tight tabular-nums ${
                compact ? 'text-base' : 'text-lg sm:text-xl'
              } ${style.value}`}
            >
              {tile.value}
            </div>
            {tile.sublabel && (
              <div className={`mt-0.5 truncate text-xs font-medium ${style.badge}`}>
                {tile.sublabel}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
