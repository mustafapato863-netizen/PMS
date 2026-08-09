import React from 'react';
import { useTheme } from '../../context/ThemeContext';
import MoMIndicator from './MoMIndicator';

interface KpiCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
  note?: React.ReactNode; // ponytail: secondary muted line, e.g. headcount context
  trendDelta?: number;
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
  lowerTrendIsBetter = false,
  showStableTrend = false,
  accent,
  variant = 'gradient',
}: KpiCardProps) {
  const { theme } = useTheme();
  const isDark = theme === 'dark';

  const isIndigo = accent.includes('indigo');
  const isEmerald = accent.includes('emerald');
  const isRed = accent.includes('red');
  const isOrange = accent.includes('orange');

  let lightStart = '#E6F1FB';
  let darkStart = '#172554'; // dark blue
  let iconColor = 'text-blue-600 dark:text-blue-400';

  if (isIndigo) {
    lightStart = '#EEEDFE';
    darkStart = '#311042'; // dark purple
    iconColor = 'text-indigo-600 dark:text-indigo-400';
  } else if (isEmerald) {
    lightStart = '#EAF3DE';
    darkStart = '#064e3b'; // dark green
    iconColor = 'text-emerald-600 dark:text-emerald-400';
  } else if (isRed) {
    lightStart = '#FCEBEB';
    darkStart = '#450a0a'; // dark red
    iconColor = 'text-red-600 dark:text-red-400';
  } else if (isOrange) {
    lightStart = '#FFF1E6';
    darkStart = '#431407';
    iconColor = 'text-orange-600 dark:text-orange-400';
  }

  const startColor = isDark ? darkStart : lightStart;

  const backgroundStyle = variant === 'gradient'
    ? { background: `linear-gradient(135deg, ${startColor} 0%, var(--bg-surface) 60%)` }
    : { background: 'var(--bg-surface)' };

  return (
    <div
      style={backgroundStyle}
      className={`rounded-xl border border-[var(--border-light)] p-4 shadow-sm flex flex-col justify-between min-h-[96px] transition-all duration-[180ms] ease-out hover:-translate-y-0.5 hover:shadow-md ${variant === 'flat' ? `border-l-4 ${accent}` : ''}`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.08em] text-[var(--text-muted)] mb-1.5">{label}</p>
          <div className="text-[22px] font-extrabold text-[var(--text-primary)] leading-none tracking-tight">{value}</div>
        </div>
        <div
          style={{ backgroundColor: startColor }}
          className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0"
        >
          <span className={iconColor}>{icon}</span>
        </div>
      </div>
      <div className="mt-2.5">
        {sub && (
          <p className="text-[11px] text-[var(--text-secondary)] font-medium leading-snug">{sub}</p>
        )}
        <MoMIndicator
          delta={trendDelta}
          lowerIsBetter={lowerTrendIsBetter}
          showStable={showStableTrend}
          className="mt-1"
        />
        {note && (
          <p className="text-[10px] text-[var(--text-muted)] font-medium mt-1 leading-snug">{note}</p>
        )}
      </div>
    </div>
  );
}

export default KpiCard;
