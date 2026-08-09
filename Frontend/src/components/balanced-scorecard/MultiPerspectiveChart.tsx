import React, { useMemo, useState, useRef } from 'react';
import type { BscPerspective } from '../../hooks/api/useBalancedScorecard';
import { pc, fmtScore } from './types';

interface MultiPerspectiveChartProps {
  history: Array<{ month: string; year: number; perspective_scores?: Record<string, number | null> }>;
  perspectives: BscPerspective[];
  height?: number;
  hideSummary?: boolean;
}

interface MultiChartTooltipState {
  x: number;
  y: number;
  month: string;
  scores: Array<{ label: string; val: number | null; color: string }>;
  guideX: number;
}

export function MultiPerspectiveChart({
  history,
  perspectives,
  height = 138,
  hideSummary = false,
}: MultiPerspectiveChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [activeTooltip, setActiveTooltip] = useState<MultiChartTooltipState | null>(null);

  const W = 328, H = height, PAD_X = 22, PAD_Y = height < 120 ? 8 : 16, PAD_RIGHT = 34;
  const inner_W = W - PAD_X - PAD_RIGHT, inner_H = H - PAD_Y * 2;

  const validHistory = useMemo(() => history.filter(h => h.perspective_scores != null), [history]);

  if (!validHistory.length || !perspectives.length) return (
    <div style={{ height: H, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--bsc-panel-muted)', fontSize: 11 }}>
      No history
    </div>
  );

  const allScores = validHistory.flatMap(h =>
    perspectives.map(p => h.perspective_scores?.[p.key] ?? null).filter((v): v is number => v != null)
  );
  const minVal = Math.max(0, Math.min(...allScores) - 5);
  const maxVal = Math.min(115, Math.max(...allScores) + 5);
  const range  = maxVal - minVal || 1;

  const toX = (i: number) => PAD_X + (i / Math.max(validHistory.length - 1, 1)) * inner_W;
  const toY = (v: number) => PAD_Y + inner_H - ((v - minVal) / range) * inner_H;

  const handleHover = (idx: number, e: React.MouseEvent) => {
    if (!containerRef.current) return;
    const parentRect = containerRef.current.getBoundingClientRect();
    const x = toX(idx);
    
    // Relative coordinates
    const mouseX = e.clientX - parentRect.left;
    const mouseY = e.clientY - parentRect.top;
    
    const h = validHistory[idx];
    const tooltipScores = perspectives.map(p => ({
      label: p.label,
      val: h.perspective_scores?.[p.key] ?? null,
      color: pc(p.key),
    }));

    setActiveTooltip({
      x: mouseX,
      y: mouseY - 12,
      month: `${h.month} ${h.year}`,
      scores: tooltipScores,
      guideX: x,
    });
  };

  const stepW = inner_W / Math.max(validHistory.length - 1, 1);
  const latestPeriod = validHistory[validHistory.length - 1];
  const latestScores = perspectives
    .map((p) => ({
      key: p.key,
      label: p.label,
      color: pc(p.key),
      value: latestPeriod?.perspective_scores?.[p.key] ?? null,
    }))
    .filter((item) => item.value != null)
    .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));
  const strongestTrend = latestScores[0] ?? null;

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      {!hideSummary && (
        <div className="bsc-persp-trend-summary">
          <div className="bsc-persp-trend-pill">
            <span className="bsc-persp-trend-pill-label">Top</span>
            <span style={{ color: strongestTrend?.color ?? '#15181E' }}>
              {strongestTrend ? `${strongestTrend.label.split(' ')[0]} ${fmtScore(strongestTrend.value)}` : 'N/A'}
            </span>
          </div>
          <div className="bsc-persp-trend-pill muted">
            <span className="bsc-persp-trend-pill-label">Latest</span>
            <span>
              {latestPeriod ? `${latestPeriod.month} ${String(latestPeriod.year).slice(-2)}` : 'N/A'}
            </span>
          </div>
        </div>
      )}
      <svg width="100%" height={H} viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" style={{ overflow: 'visible' }}>
        {[minVal + range / 2].map((v, i) => (
          <line key={i} x1={PAD_X} y1={toY(v)} x2={W - 4} y2={toY(v)} stroke="var(--bsc-chart-grid)" strokeWidth="1"/>
        ))}

        {/* Hover vertical guide line */}
        {activeTooltip && (
          <line
            x1={activeTooltip.guideX} y1={PAD_Y} x2={activeTooltip.guideX} y2={H - PAD_Y}
            stroke="var(--bsc-border-strong)" strokeWidth="1.2" strokeDasharray="3 3"
          />
        )}

        {/* Curved lines for each perspective */}
        {perspectives.map(p => {
          const color = pc(p.key);
          const pts = validHistory.map((h, i) => {
            const v = h.perspective_scores?.[p.key];
            return v != null ? { x: toX(i), y: toY(v) } : null;
          }).filter((pt): pt is { x: number; y: number } => pt != null);

          if (pts.length < 2) return null;

          // Generate smooth bezier curve path
          let d = `M ${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`;
          for (let i = 1; i < pts.length; i++) {
            const prev = pts[i - 1];
            const curr = pts[i];
            const cp1x = prev.x + (curr.x - prev.x) / 3;
            const cp1y = prev.y;
            const cp2x = curr.x - (curr.x - prev.x) / 3;
            const cp2y = curr.y;
            d += ` C ${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${curr.x.toFixed(1)},${curr.y.toFixed(1)}`;
          }

          return (
            <path
              key={p.key}
              d={d}
              fill="none"
              stroke={color}
              strokeWidth="1.8"
              strokeLinejoin="round"
              strokeLinecap="round"
              style={{ transition: 'stroke-width 0.15s ease' }}
            />
          );
        })}

        {perspectives.map((p) => {
          const latestValue = latestPeriod?.perspective_scores?.[p.key];
          if (latestValue == null) return null;

          const x = toX(validHistory.length - 1);
          const y = toY(latestValue);

          return (
            <g key={`label-${p.key}`}>
              <circle
                cx={x}
                cy={y}
                r="2.6"
                fill={pc(p.key)}
                stroke="var(--bsc-panel-bg-solid)"
                strokeWidth="1.2"
              />
              <text
                x={x + 8}
                y={y + 3}
                fontSize="9"
                fontWeight="800"
                fill={pc(p.key)}
              >
                {`${Math.round(latestValue)}%`}
              </text>
            </g>
          );
        })}

        {/* Month labels */}
        {validHistory.map((h, i) => (
          <text key={i} x={toX(i)} y={H - 1} fontSize="8.5" fill="var(--bsc-panel-muted)" textAnchor="middle" fontWeight="600">
            {`${h.month}`.slice(0, 1)}
          </text>
        ))}

        {/* Invisible vertical overlay bars for interactive hover zones */}
        {validHistory.map((_h, i) => {
          const x = toX(i);
          return (
            <rect
              key={i}
              x={x - stepW / 2}
              y={0}
              width={stepW}
              height={H}
              fill="transparent"
              style={{ cursor: 'pointer' }}
              onMouseEnter={(e) => handleHover(i, e)}
              onMouseMove={(e) => handleHover(i, e)}
              onMouseLeave={() => setActiveTooltip(null)}
            />
          );
        })}
      </svg>

      {/* Hover Multi-perspective detailed Tooltip */}
      {activeTooltip && (
        <div
          style={{
            position: 'absolute',
            left: activeTooltip.x,
            top: activeTooltip.y,
            transform: 'translate(-50%, -100%)',
            background: 'color-mix(in srgb, var(--bsc-tooltip-bg) 86%, transparent)',
            border: '1px solid var(--bsc-border)',
            borderRadius: '12px',
            boxShadow: 'var(--bsc-shadow-lg)',
            padding: '10px 12px',
            zIndex: 250,
            pointerEvents: 'none',
            fontFamily: 'inherit',
            minWidth: 160,
            transition: 'all 0.1s ease-out',
            animation: 'bscFadeIn 0.12s ease',
            backdropFilter: 'blur(14px)',
            WebkitBackdropFilter: 'blur(14px)',
          }}
        >
          <div
            style={{
              fontSize: 10,
              fontWeight: 800,
              color: 'var(--bsc-panel-muted)',
              textTransform: 'uppercase',
              letterSpacing: '0.04em',
              borderBottom: '1px solid var(--bsc-table-row)',
              paddingBottom: 5,
              marginBottom: 5,
            }}
          >
            {activeTooltip.month}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {activeTooltip.scores.map((s, idx) => (
              <div key={idx} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: 11.5 }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: 'var(--bsc-panel-subtle)', fontWeight: 600 }}>
                  <span style={{ width: 6.5, height: 6.5, borderRadius: '50%', background: s.color }} />
                  {s.label.split(' ')[0]}:
                </span>
                <span style={{ fontWeight: 800, color: s.color }}>
                  {fmtScore(s.val)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default MultiPerspectiveChart;
