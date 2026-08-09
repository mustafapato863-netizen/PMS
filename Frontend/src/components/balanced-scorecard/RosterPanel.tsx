import { useMemo } from 'react';
import type { BscContributor, BscPerson, BscPerspective } from '../../hooks/api/useBalancedScorecard';
import { fmtScore, scoreClass, initials, avatarColor } from './types';
import Sparkline from './Sparkline';
import StatusPill from './StatusPill';

interface RosterPanelProps {
  people: BscPerson[];
  contributors: BscContributor[];
  selectedPerspectiveRow: BscPerspective | null;
  peopleSearch: string;
  onSearchChange: (v: string) => void;
}

export function RosterPanel({
  people, contributors, selectedPerspectiveRow, peopleSearch, onSearchChange,
}: RosterPanelProps) {
  const perspKey = selectedPerspectiveRow?.key ?? '';

  const filtered = useMemo(() => {
    const q = peopleSearch.trim().toLowerCase();
    let list = people;
    if (perspKey) {
      list = list.filter(p => {
        const c = contributors.find((contributor) => contributor.employee_id === p.employee_id);
        return c?.perspectives?.[perspKey] != null;
      });
    }
    if (q) {
      list = list.filter(p =>
        p.employee_name.toLowerCase().includes(q) || p.employee_id.toLowerCase().includes(q)
      );
    }
    return list;
  }, [people, contributors, perspKey, peopleSearch]);

  return (
    <div className="bsc-panel bsc-panel-pad">
      <div className="bsc-panel-head">
        <div>
          <h2>{selectedPerspectiveRow?.label || 'All Perspectives'} Contributor Roster</h2>
          <div className="bsc-sub">People driving or impacting this perspective</div>
        </div>
        <span style={{ fontSize: 11, fontWeight: 700, color: '#8A8F99', background: '#EEF0F3', padding: '3px 9px', borderRadius: 99 }}>
          {filtered.length} People
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <div style={{ display:'flex', alignItems:'center', gap:7, border:'1px solid #E6E8EC', borderRadius:9, padding:'7px 12px', flex:1, background:'#FAFAFB' }}>
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#8A8F99" strokeWidth="2">
            <circle cx="11" cy="11" r="7"/><path d="M21 21l-4.3-4.3"/>
          </svg>
          <input
            value={peopleSearch}
            onChange={e => onSearchChange(e.target.value)}
            placeholder="Search people..."
            style={{ border:'none', background:'none', outline:'none', fontSize:12.5, color:'#15181E', flex:1, fontFamily:'inherit' }}
          />
        </div>
      </div>

      {filtered.length === 0 ? (
        <div style={{ textAlign:'center', padding:'32px 0', color:'#8A8F99', fontSize:13 }}>
          No contributors found for {selectedPerspectiveRow?.label ?? 'this perspective'}.
        </div>
      ) : (
        <div style={{ overflowX:'auto' }}>
          <table className="bsc-table">
            <thead>
              <tr>
                <th>Employee</th>
                <th>Perspective Score</th>
                <th>Weighted Contribution</th>
                <th>Top KPI</th>
                <th>Trend</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, 8).map((person, idx) => {
                const contrib   = contributors.find((contributor) => contributor.employee_id === person.employee_id);
                const perspData = contrib?.perspectives?.[perspKey];
                const score     = perspData?.score;
                const cls       = scoreClass(score);
                const trendUp   = (perspData?.trend ?? 0) >= 0;
                const pts: (number | null)[] = score != null
                  ? [score * 0.92, score * 0.95, score * 0.97, score * 0.99, score]
                  : [null, null, null, null, null];

                return (
                  <tr key={person.employee_id}>
                    <td>
                      <div className="bsc-emp-cell">
                        <div className="bsc-emp-avatar" style={{ background: avatarColor(idx) }}>
                          {initials(person.employee_name)}
                        </div>
                        <div>
                          <div className="bsc-emp-name">{person.employee_name}</div>
                          <div className="bsc-emp-role">{person.employee_id}</div>
                        </div>
                      </div>
                    </td>
                    <td><span className={`bsc-score-val ${cls}`}>{fmtScore(score)}</span></td>
                    <td>
                      {perspData?.weighted_contribution != null && perspData?.measured_weight != null
                        ? `${(perspData.weighted_contribution * 100).toFixed(1)}% of ${(perspData.measured_weight * 100).toFixed(0)}%`
                        : '—'}
                    </td>
                    <td style={{ fontSize:12, fontWeight:600 }}>{perspData?.top_kpi_label ?? '—'}</td>
                    <td><Sparkline points={pts} up={trendUp}/></td>
                    <td><StatusPill status={score == null ? 'na' : score >= 90 ? 'excellent' : score >= 75 ? 'good' : score >= 60 ? 'attention' : 'poor'}/></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default RosterPanel;
