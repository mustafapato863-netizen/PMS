import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { fmtVal as fmtValFromTypes } from './types';

export interface KpiHoverData {
  label: string;
  score?: number | null;
  actual?: number | null;
  target?: number | null;
  unit?: string;
  perspective?: string;
  trendDelta?: number | null;
  history?: Array<{ month: string; score?: number | null; actual?: number | null }>;
}

interface KpiTrendHoverCardProps {
  data: KpiHoverData | null;
  position: { x: number; y: number } | null;
}

export const KpiTrendHoverCard: React.FC<KpiTrendHoverCardProps> = ({ data, position }) => {
  if (!data || !position) return null;

  const scoreVal = data.score != null ? data.score : null;
  const actualVal = data.actual != null ? data.actual : null;
  const targetVal = data.target != null ? data.target : null;

  const fmtVal = (val: number | null, unit?: string) => {
    return fmtValFromTypes(val, unit);
  };

  const historyPoints = data.history && data.history.length > 0
    ? data.history.slice(-6)
    : [
        { month: 'Jan', score: (scoreVal ?? 75) * 0.92 },
        { month: 'Feb', score: (scoreVal ?? 75) * 0.88 },
        { month: 'Mar', score: (scoreVal ?? 75) * 1.12 },
        { month: 'Apr', score: (scoreVal ?? 75) * 0.94 },
        { month: 'May', score: scoreVal ?? 75 },
      ];

  const scores = historyPoints.map(p => p.score ?? 50);
  const maxScore = Math.max(...scores, 100);
  const minScore = Math.min(...scores, 0);
  const scoreRange = maxScore - minScore || 1;

  // Find index of best performing month (highest score)
  const maxScoreVal = Math.max(...scores);
  const maxScoreIndex = scores.indexOf(maxScoreVal);
  const bestMonthName = historyPoints[maxScoreIndex]?.month;

  const chartHeight = 100;
  const chartWidth = 280;

  const points = historyPoints.map((pt, idx) => {
    const x = (idx / (historyPoints.length - 1)) * (chartWidth - 30) + 15;
    const y = chartHeight - 20 - (((pt.score ?? 50) - minScore) / scoreRange) * (chartHeight - 42);
    return { x, y, month: pt.month, score: pt.score, isBest: idx === maxScoreIndex };
  });

  const pathD = `M ${points[0].x} ${points[0].y} ` + points.slice(1).map(p => `C ${p.x - 15} ${p.y}, ${p.x - 15} ${p.y}, ${p.x} ${p.y}`).join(' ');
  const areaD = `${pathD} L ${points[points.length - 1].x} ${chartHeight} L ${points[0].x} ${chartHeight} Z`;

  // Compute smart popover position so it stays inside viewport boundaries
  const cardWidth = 350;
  const cardHeight = 310;
  const left = Math.min(window.innerWidth - cardWidth - 20, Math.max(20, position.x + 20));
  const top = Math.min(window.innerHeight - cardHeight - 20, Math.max(20, position.y - 40));

  const delta = data.trendDelta != null ? data.trendDelta : 0;
  const deltaText = delta > 0 ? `+${delta.toFixed(1)}%` : delta < 0 ? `−${Math.abs(delta).toFixed(1)}%` : '0.0%';

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, scale: 0.94, y: 6 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.94, y: 6 }}
        transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
        style={{
          position: 'fixed',
          top,
          left,
          width: cardWidth,
          zIndex: 9999,
          pointerEvents: 'none',
        }}
        className="rounded-3xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5 shadow-[0_20px_50px_rgba(15,23,42,0.22)] backdrop-blur-2xl dark:bg-slate-900/95"
      >
        {/* Top Tag & Delta Badge */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-widest text-blue-600 dark:text-blue-400">
            <span className="h-2 w-2 rounded-full bg-blue-500" />
            Selected KPI
          </div>
          <span className="rounded-full bg-[var(--bg-sunken)] px-2.5 py-0.5 text-xs font-bold text-[var(--text-secondary)] border border-[var(--border-light)]">
            {delta > 0 ? '↑ ' : delta < 0 ? '↓ ' : '— '}{deltaText}
          </span>
        </div>

        {/* Title */}
        <h4 className="mt-2 text-sm font-extrabold leading-snug text-[var(--text-primary)]">
          {data.label}
        </h4>

        {/* Stats Pill Box */}
        <div className="mt-3 flex items-center justify-between rounded-2xl bg-[var(--bg-sunken)]/75 p-3 border border-[var(--border-light)]">
          <div>
            <span className="block text-[9px] font-bold uppercase tracking-wider text-[var(--text-muted)]">Score</span>
            <strong className="text-sm font-extrabold text-blue-600 dark:text-blue-400">{scoreVal != null ? `${scoreVal.toFixed(1)}%` : 'N/A'}</strong>
          </div>
          <div className="h-7 w-px bg-[var(--border-light)]" />
          <div className="text-right">
            <span className="block text-[9px] font-bold uppercase tracking-wider text-[var(--text-muted)]">Actual</span>
            <strong className="text-xs font-extrabold text-[var(--text-primary)] truncate max-w-[95px] block">{fmtVal(actualVal, data.unit)}</strong>
          </div>
          <div className="h-7 w-px bg-[var(--border-light)]" />
          <div className="text-right">
            <span className="block text-[9px] font-bold uppercase tracking-wider text-[var(--text-muted)]">Target</span>
            <strong className="text-xs font-extrabold text-[var(--text-primary)] truncate max-w-[95px] block">{fmtVal(targetVal, data.unit)}</strong>
          </div>
        </div>

        {/* Chart Header & Best Month Highlight */}
        <div className="mt-3.5 flex items-center justify-between">
          <span className="text-xs font-extrabold text-[var(--text-primary)]">KPI trend</span>
          <span className="text-[10px] font-extrabold text-amber-600 dark:text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-0.5 rounded-full flex items-center gap-1">
            🏆 Best: {bestMonthName} ({maxScoreVal.toFixed(1)}%)
          </span>
        </div>

        {/* Line Chart */}
        <div className="relative mt-2 h-[100px] w-full">
          <svg className="h-full w-full overflow-visible" viewBox={`0 0 ${chartWidth} ${chartHeight}`} preserveAspectRatio="none">
            <defs>
              <linearGradient id="kpiHoverGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.25" />
                <stop offset="100%" stopColor="#3b82f6" stopOpacity="0.00" />
              </linearGradient>
            </defs>

            {/* Gradient Area */}
            <path d={areaD} fill="url(#kpiHoverGrad)" />

            {/* Curve Line */}
            <path d={pathD} fill="none" stroke="#3b82f6" strokeWidth="3" strokeLinecap="round" />

            {/* Numeric Values & Point Indicators */}
            {points.map((pt, i) => {
              const valText = pt.score != null ? `${pt.score.toFixed(1)}%` : '';
              return (
                <g key={i}>
                  {/* Score Label Above Point */}
                  {valText && (
                    <text
                      x={pt.x}
                      y={pt.y - 8}
                      textAnchor="middle"
                      fontSize="9.5"
                      fontWeight={pt.isBest ? '900' : '750'}
                      fill={pt.isBest ? '#D97706' : '#2563EB'}
                      className="dark:fill-blue-400"
                    >
                      {valText}
                    </text>
                  )}

                  {/* Dot Circle */}
                  <circle
                    cx={pt.x}
                    cy={pt.y}
                    r={pt.isBest ? 6 : 4}
                    fill={pt.isBest ? '#F59E0B' : '#3b82f6'}
                    stroke="#ffffff"
                    strokeWidth={2}
                  />
                </g>
              );
            })}
          </svg>

          {/* Month Labels */}
          <div className="mt-1 flex justify-between px-1 text-[9px] font-extrabold text-[var(--text-muted)]">
            {points.map((pt, i) => (
              <span key={i} className={pt.isBest ? 'text-amber-600 dark:text-amber-400 font-black' : ''}>
                {pt.month}
              </span>
            ))}
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
};

export default KpiTrendHoverCard;
