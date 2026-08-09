import type { MouseEvent } from 'react';
import type { BscPerspective } from '../../hooks/api/useBalancedScorecard';
import { ck, fmtScore, fmtWeightedContribution, PERSP_SVG, pc } from './types';
import StatusPill from './StatusPill';

interface PerspCardProps {
  perspective: BscPerspective;
  isSelected: boolean;
  isDimmed: boolean;
  isStrategy?: boolean;
  onSelect: () => void;
  onHover?: (e: MouseEvent) => void;
  onLeave?: () => void;
}

export function PerspCard({
  perspective, isSelected, isDimmed, isStrategy, onSelect, onHover, onLeave,
}: PerspCardProps) {
  const colorKey = ck(perspective.key);
  const color    = pc(perspective.key);
  const score    = perspective.score;
  const trend    = perspective.trend_vs_previous;
  const target   = perspective.target_score ?? 95;
  const barPct   = score != null && target != null
    ? Math.min(100, (score / target) * 100)
    : score != null ? Math.min(100, score) : 0;
  const isNA = score == null;

  return (
    <button
      className={`bsc-persp-card ${colorKey} ${isSelected ? 'selected' : ''} ${isDimmed ? 'dimmed' : ''} ${isStrategy ? 'bsc-strategy-card' : ''}`}
      onClick={onSelect}
      onMouseEnter={onHover}
      onMouseLeave={onLeave}
    >
      {/* Corner radial glow orb decoration */}
      <div
        aria-hidden="true"
        style={{
          position: 'absolute',
          top: -32, right: -32,
          width: 96, height: 96,
          borderRadius: '50%',
          background: `radial-gradient(circle, ${color}30 0%, transparent 70%)`,
          pointerEvents: 'none',
          transition: 'opacity 0.25s ease',
          opacity: isSelected ? 1 : 0.55,
        }}
      />

      <div className="bsc-persp-top">
        <div className="bsc-persp-id">
          <div className="bsc-persp-icon">
            {PERSP_SVG[perspective.key] ?? PERSP_SVG['Financial']}
          </div>
          <div>
            <div className="bsc-persp-name">{perspective.label}</div>
            <div className="bsc-persp-focus">{perspective.focus || 'No focus defined'}</div>
          </div>
        </div>
        <StatusPill status={perspective.state ?? perspective.status}/>
      </div>

      <div className="bsc-score-row">
        <span className={`bsc-score-num ${isNA ? 'na' : ''}`} style={isNA ? undefined : { color }}>
          {fmtScore(score)}
        </span>
        {!isNA && trend != null && (
          <span className={`bsc-trend ${trend > 0 ? 'up' : trend < 0 ? 'down' : 'flat'}`}>
            {trend > 0 ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M5 15l5-5 4 4 5-7"/></svg>
            ) : trend < 0 ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><path d="M5 9l5 5 4-4 5 7"/></svg>
            ) : null}
            {Math.abs(trend).toFixed(1)}%
          </span>
        )}
      </div>
      <div className="bsc-vs-target">vs Target {target != null ? `${target}%` : 'N/A'}</div>

      {!isStrategy && (
        <div className="bsc-bar-track">
          <div className="bsc-bar-fill" style={{ width:`${barPct}%` }}/>
        </div>
      )}

      <div className="bsc-meta-row">
        <span className="lbl">Weighted Score</span>
        <span className="val">
          {fmtWeightedContribution(
            perspective.weighted_contribution,
            perspective.configured_weight,
            perspective.measured_weight,
          )}
        </span>
      </div>

      <div className="bsc-kpi-block">
        <div className="bsc-kpi-block-label">{isStrategy ? 'Primary KPI Driver' : 'Top KPI'}</div>
        <div className="bsc-kpi-block-name">
          {perspective.primary_driver?.kpi_label || 'No KPIs defined yet'}
        </div>
      </div>
    </button>
  );
}

export default PerspCard;
