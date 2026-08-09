import React from 'react';
import type { BscPerspective } from '../../hooks/api/useBalancedScorecard';
import { ck } from './types';
import PerspCard from './PerspCard';

interface StrategyMapViewProps {
  positionTitle: string;
  personName?: string | null;
  perspectives: BscPerspective[];
  selectedPerspective: string | null;
  onSelectPerspective: (key: string | null) => void;
  onPerspHover: (pKey: string, e: React.MouseEvent) => void;
  onPerspLeave: () => void;
  onVisionHover: (e: React.MouseEvent) => void;
  onVisionLeave: () => void;
  hoveredPersp: string | null;
}

export function StrategyMapView({
  positionTitle,
  personName,
  perspectives,
  selectedPerspective,
  onSelectPerspective,
  onPerspHover,
  onPerspLeave,
  onVisionHover,
  onVisionLeave,
  hoveredPersp,
}: StrategyMapViewProps) {
  const activeColorKey = (() => {
    const active = hoveredPersp ?? selectedPerspective;
    if (!active) return null;
    return ck(active);
  })();

  const pathCls = (c: string) => `${c} ${activeColorKey === c ? 'lit' : ''}`;

  const primaryTitle = personName || positionTitle || 'Balanced Scorecard';
  const badgeTitle = personName ? positionTitle : 'Strategic Leadership';
  const initialLetter = primaryTitle.trim().charAt(0).toUpperCase();

  const makeSlot = (colorKey: 'financial' | 'customer' | 'internal' | 'learning', slot: string) =>
    perspectives.filter(p => ck(p.key) === colorKey).map(p => (
      <div key={p.key} className={slot}>
        <PerspCard
          perspective={p} isStrategy
          isSelected={selectedPerspective === p.key}
          isDimmed={!!(hoveredPersp ? hoveredPersp !== p.key : selectedPerspective && selectedPerspective !== p.key)}
          onSelect={() => onSelectPerspective(selectedPerspective === p.key ? null : p.key)}
          onHover={(e) => onPerspHover(p.key, e)}
          onLeave={onPerspLeave}
        />
      </div>
    ));

  return (
    <div className="bsc-panel bsc-panel-pad">
      <div className="bsc-panel-head" style={{ marginBottom: 20, paddingBottom: 14, borderBottom: '1px solid var(--bsc-border, #E5E7EB)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <div style={{
            position: 'relative',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 46,
            height: 46,
            borderRadius: 14,
            background: 'linear-gradient(135deg, rgba(46, 111, 224, 0.15) 0%, rgba(124, 92, 224, 0.15) 100%)',
            border: '1px solid rgba(46, 111, 224, 0.3)',
            color: '#2E6FE0',
            fontWeight: 800,
            fontSize: 20,
            boxShadow: '0 3px 10px rgba(46, 111, 224, 0.12)',
            flexShrink: 0,
          }}>
            {initialLetter}
            <div style={{
              position: 'absolute',
              bottom: -2,
              right: -2,
              width: 12,
              height: 12,
              borderRadius: '50%',
              backgroundColor: '#10B981',
              border: '2px solid white',
            }} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
              <h2 style={{ fontSize: 19, fontWeight: 700, margin: 0, letterSpacing: '-0.01em', color: 'var(--bsc-panel-text, #111827)' }}>
                {primaryTitle}
              </h2>
              {badgeTitle && (
                <span style={{
                  fontSize: 11,
                  fontWeight: 600,
                  padding: '3px 12px',
                  borderRadius: 99,
                  background: 'rgba(46, 111, 224, 0.08)',
                  color: '#2E6FE0',
                  border: '1px solid rgba(46, 111, 224, 0.2)',
                  letterSpacing: '0.01em',
                }}>
                  {badgeTitle}
                </span>
              )}
            </div>
            <div className="bsc-sub" style={{ marginTop: 3, fontSize: 12, fontWeight: 500, color: '#6B7280' }}>
              Balanced Scorecard • Strategic Performance Overview
            </div>
          </div>
        </div>
      </div>
      <div className="bsc-strategy-stage">
        {/* Connector lines */}
        <svg className="bsc-connector-svg" viewBox="0 0 1000 560" preserveAspectRatio="none">
          <path className={pathCls('fin')}   d="M 330 110 C 420 150, 440 200, 500 270"/>
          <path className={pathCls('cus')}   d="M 670 110 C 580 150, 560 200, 500 270"/>
          <path className={pathCls('int')}   d="M 330 450 C 420 410, 440 360, 500 290"/>
          <path className={pathCls('learn')} d="M 670 450 C 580 410, 560 360, 500 290"/>
        </svg>

        <div className="bsc-strategy-quadrants">
          {makeSlot('financial', 'bsc-sq-fin')}
          {makeSlot('customer',  'bsc-sq-cus')}

          {/* Vision Node */}
          <button
            className="bsc-vision-node"
            onClick={() => onSelectPerspective(null)}
            onMouseEnter={onVisionHover}
            onMouseLeave={onVisionLeave}
            style={{ cursor: 'pointer' }}
          >
            Vision &<br/><span>Strategy</span>
          </button>

          {makeSlot('internal', 'bsc-sq-int')}
          {makeSlot('learning', 'bsc-sq-learn')}
        </div>
      </div>
    </div>
  );
}

export default StrategyMapView;
