import React from 'react';
import type { BscPerspective } from '../../hooks/api/useBalancedScorecard';
import PerspCard from './PerspCard';

interface PerspectiveSummaryViewProps {
  perspectives: BscPerspective[];
  selectedPerspective: string | null;
  onSelectPerspective: (key: string | null) => void;
  onPerspHover: (pKey: string, e: React.MouseEvent) => void;
  onPerspLeave: () => void;
  hoveredPersp: string | null;
}

export function PerspectiveSummaryView({
  perspectives,
  selectedPerspective,
  onSelectPerspective,
  onPerspHover,
  onPerspLeave,
  hoveredPersp,
}: PerspectiveSummaryViewProps) {
  return (
    <div className="bsc-panel bsc-panel-pad">
      <div className="bsc-panel-head">
        <div>
          <h2>Balanced Scorecard — Management Overview</h2>
          <div className="bsc-sub">Click a perspective to filter KPIs and Roster below</div>
        </div>
        {selectedPerspective && (
          <button
            onClick={() => onSelectPerspective(null)}
            style={{ border:'1px solid #E6E8EC', borderRadius:8, padding:'4px 10px', background:'#fff', fontSize:11, fontWeight:700, cursor:'pointer', color:'#5B616E' }}
          >
            Clear filter ×
          </button>
        )}
      </div>
      <div className="bsc-persp-grid">
        {perspectives.map(p => (
          <PerspCard
            key={p.key}
            perspective={p}
            isSelected={selectedPerspective === p.key}
            isDimmed={!!(hoveredPersp ? hoveredPersp !== p.key : selectedPerspective && selectedPerspective !== p.key)}
            onSelect={() => onSelectPerspective(selectedPerspective === p.key ? null : p.key)}
            onHover={(e) => onPerspHover(p.key, e)}
            onLeave={onPerspLeave}
          />
        ))}
      </div>
    </div>
  );
}

export default PerspectiveSummaryView;
