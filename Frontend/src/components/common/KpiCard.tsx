import React from 'react';
import { Minus, TrendingDown, TrendingUp } from 'lucide-react';
import MoMIndicator from './MoMIndicator';

interface KpiCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  note?: React.ReactNode; // ponytail: secondary muted line, e.g. headcount context
  trendDelta?: number;
  /** Replaces the default "+1.2% MoM" line, e.g. "−0.94 pts vs Aug". */
  trendText?: string;
  /** Muted line shown when there is no change, so the card keeps its layout. */
  trendEmptyText?: string;
  lowerTrendIsBetter?: boolean;
  showStableTrend?: boolean;
  accent: string;
  variant?: 'gradient' | 'flat';
}

export function KpiCard({
  icon,
  label,
  value,
  sub,
  note,
  trendDelta,
  trendText,
  trendEmptyText,
  lowerTrendIsBetter = false,
  showStableTrend = false,
  accent,
  variant = 'gradient',
}: KpiCardProps) {

  const isIndigo = accent.includes('indigo');
  const isEmerald = accent.includes('emerald');
  const isRed = accent.includes('red');
  const isOrange = accent.includes('orange');

  let lightStart = '#E6F1FB';
  let iconColor = 'text-blue-600';

  if (isIndigo) {
    lightStart = '#EEEDFE';
    iconColor = 'text-indigo-600';
  } else if (isEmerald) {
    lightStart = '#EAF3DE';
    iconColor = 'text-emerald-600';
  } else if (isRed) {
    lightStart = '#FCEBEB';
    iconColor = 'text-red-600';
  } else if (isOrange) {
    lightStart = '#FFF1E6';
    iconColor = 'text-orange-600';
  }

  const backgroundStyle = variant === 'gradient'
    ? { background: `linear-gradient(135deg, ${lightStart} 0%, var(--bg-surface) 60%)` }
    : { background: 'var(--bg-surface)' };

  return (
    <div
      style={backgroundStyle}
      className={`rounded-xl border border-[var(--border-light)] p-4 shadow-sm flex flex-col justify-between transition-all duration-[180ms] ease-out hover:-translate-y-0.5 hover:shadow-md ${variant === 'flat' ? `border-l-4 ${accent}` : ''}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-[var(--text-muted)] mb-1.5">{label}</p>
          <div className="text-display-card font-bold text-[var(--text-primary)] leading-none tracking-tight">{value}</div>
        </div>
        <div
          style={{ backgroundColor: lightStart }}
          className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
        >
          <span className={iconColor}>{icon}</span>
        </div>
      </div>
      <div className="mt-2.5">
        {sub && (
          <p className="text-xs text-[var(--text-secondary)] font-medium leading-snug">{sub}</p>
        )}
        {trendText !== undefined && trendDelta !== undefined && Number.isFinite(trendDelta) ? (
          <span className={`mt-1 inline-flex items-center gap-1 text-xs font-semibold ${
            trendDelta === 0
              ? 'text-[var(--text-muted)]'
              : (lowerTrendIsBetter ? trendDelta < 0 : trendDelta > 0)
                ? 'text-emerald-600'
                : 'text-rose-600'
          }`}>
            {trendDelta === 0 ? <Minus size={12} /> : trendDelta < 0 ? <TrendingDown size={12} /> : <TrendingUp size={12} />}
            <span>{trendText}</span>
          </span>
        ) : trendEmptyText ? (
          <span className="mt-1 block text-xs font-semibold text-[var(--text-muted)]">{trendEmptyText}</span>
        ) : (
          <MoMIndicator
            delta={trendDelta}
            lowerIsBetter={lowerTrendIsBetter}
            showStable={showStableTrend}
            className="mt-1"
          />
        )}
        {note && (
          <p className="text-xs text-[var(--text-muted)] font-medium mt-1 leading-snug">{note}</p>
        )}
      </div>
    </div>
  );
}

export default KpiCard;
