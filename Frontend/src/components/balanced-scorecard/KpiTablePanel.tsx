import { useMemo } from 'react';
import type { BscKpiRow } from '../../hooks/api/useBalancedScorecard';
import { ck, fmtScore, statusClass, scoreClass, fmtVal } from './types';
import StatusPill from './StatusPill';

interface KpiTablePanelProps {
  kpiTable: BscKpiRow[];
  selectedKpi: string | null;
  selectedPerspective: string | null;
  onSelectKpi: (key: string) => void;
  onKpiHover?: (row: BscKpiRow, e: React.MouseEvent) => void;
  onKpiLeave?: () => void;
}

export function KpiTablePanel({
  kpiTable, selectedKpi, selectedPerspective, onSelectKpi, onKpiHover, onKpiLeave,
}: KpiTablePanelProps) {
  const totalScore = useMemo(() => {
    const measuredRows = kpiTable.filter((r) => r.state !== 'not_configured' && r.score != null);
    if (measuredRows.length === 0) return null;
    const totalWeight = measuredRows.reduce((s, r) => {
      const w = r.measured_weight ?? r.weight ?? 0;
      return s + (w <= 1 ? w * 100 : w);
    }, 0);
    if (!totalWeight) return null;
    const totalWeightedContrib = measuredRows.reduce((s, r) => {
      const w = r.measured_weight ?? r.weight ?? 0;
      const pctW = w <= 1 ? w * 100 : w;
      const scoreVal = r.score ?? 0;
      // BSC Capping Rule: KPI contribution capped at 100% max achievement for scorecard weighting
      const cappedScore = Math.min(scoreVal, 100);
      return s + (cappedScore * (pctW / 100));
    }, 0);
    return Math.min(100, totalWeightedContrib / (totalWeight / 100));
  }, [kpiTable]);

  const fmtCell = (val?: number | null, unit?: string) => {
    return fmtVal(val, unit);
  };

  return (
    <div className="bsc-panel bsc-panel-pad">
      <div className="bsc-panel-head">
        <div>
          <h2>KPI Performance Details</h2>
          <div className="bsc-sub">Click a row to view its trend analysis below</div>
        </div>
        {selectedPerspective && (
          <span style={{ fontSize: 11, fontWeight: 700, color: '#8A8F99', background: '#EEF0F3', padding: '3px 9px', borderRadius: 99 }}>
            Filtered: {selectedPerspective}
          </span>
        )}
      </div>
      {kpiTable.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '32px 0', color: '#8A8F99', fontSize: 13 }}>
          No KPI data available for this selection.
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table className="bsc-table">
            <thead>
              <tr>
                <th>Perspective</th>
                <th>KPI</th>
                <th style={{ width: 64 }}>Weight</th>
                <th>Direction</th>
                <th>Target</th>
                <th>Actual</th>
                <th>Score</th>
                <th style={{ width: 72 }}></th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {kpiTable.map((row) => {
                const colorKey = ck(row.perspective);
                const pill = statusClass(row.state ?? row.status);
                const statusValue = row.state === 'not_configured'
                  ? row.state
                  : row.score != null
                    ? scoreClass(row.score)
                    : row.status ?? row.state;
                const isDimmed = !!(selectedPerspective && selectedPerspective !== row.perspective);
                const isSel = row.kpi_key === selectedKpi;
                const barPct = row.score != null ? Math.min(100, row.score) : 0;
                const barColor = { excellent: '#1A8C53', good: '#1A9E72', attention: '#C2740A', poor: '#D03B3B', na: '#8A8F99' }[pill] ?? '#8A8F99';
                return (
                  <tr
                    key={row.kpi_key}
                    className={`${isSel ? 'row-selected' : ''} ${isDimmed ? 'row-dimmed' : ''}`}
                    onClick={() => onSelectKpi(row.kpi_key)}
                    onMouseEnter={(e) => onKpiHover?.(row, e)}
                    onMouseLeave={onKpiLeave}
                    style={{ cursor: 'pointer' }}
                  >
                    <td><span className={`bsc-tag ${colorKey}`}>{row.perspective}</span></td>
                    <td style={{ fontWeight: 600, maxWidth: 220 }}>{row.kpi_label}</td>
                    <td>
                      {(() => {
                        const rawW = row.measured_weight ?? row.weight;
                        if (rawW == null) return 'N/A';
                        if (rawW <= 0.0001) return 'View';
                        const num = rawW <= 1 ? rawW * 100 : rawW;
                        return `${num.toFixed(0)}%`;
                      })()}
                    </td>
                    <td>
                      <span style={{ fontSize: 10, fontWeight: 700, color: row.direction === 'lower_better' ? '#C2740A' : '#1A8C53' }}>
                        {row.direction === 'lower_better' ? '↓ Lower' : '↑ Higher'}
                      </span>
                    </td>
                    <td>{fmtCell(row.target_value, row.unit)}</td>
                    <td style={{ fontWeight: 700 }}>{fmtCell(row.actual_value, row.unit)}</td>
                    <td>
                      <span className={`bsc-score-val ${pill}`}>
                        {row.state === 'not_configured' ? 'N/A' : fmtScore(row.score)}
                      </span>
                    </td>
                    <td>
                      {row.state !== 'not_configured' && (
                        <div className="bsc-mini-bar-track">
                          <div className="bsc-mini-bar-fill" style={{ width: `${barPct}%`, background: barColor }} />
                        </div>
                      )}
                    </td>
                    <td><StatusPill status={statusValue} /></td>
                  </tr>
                );
              })}
            </tbody>
            {totalScore != null && (
              <tfoot>
                <tr>
                  <td colSpan={6}>Total Weighted Score</td>
                  <td>
                    <span className={`bsc-score-val ${scoreClass(totalScore)}`}>
                      {fmtScore(totalScore)}
                    </span>
                  </td>
                  <td /><td />
                </tr>
              </tfoot>
            )}
          </table>
        </div>
      )}
    </div>
  );
}

export default KpiTablePanel;
