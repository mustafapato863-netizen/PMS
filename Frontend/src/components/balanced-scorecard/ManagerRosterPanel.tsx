import { useMemo } from 'react';
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';
import type { BscContributor, BscPerson } from '../../hooks/api/useBalancedScorecard';
import { avatarColor, initials, scoreClass, statusLabel } from './types';
import { buildSnapshots } from './managerSnapshots';

interface ManagerRosterPanelProps {
  people: BscPerson[];
  contributors: BscContributor[];
  selectedManagerId: string | null;
  teamName: string | null;
  search: string;
  onSearchChange: (value: string) => void;
  onSelectManager: (employeeId: string) => void;
}

function SearchIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="11" cy="11" r="6.5" />
      <path d="m16 16 4.5 4.5" strokeLinecap="round" />
    </svg>
  );
}

function ArrowTrend({ value }: { value: number | null }) {
  if (value == null || Math.abs(value) < 0.05) {
    return <span className="bsc-manager-roster-trend neutral"><Minus size={12} aria-hidden="true" />Stable</span>;
  }
  const up = value > 0;
  const TrendIcon = up ? ArrowUpRight : ArrowDownRight;
  return <span className={`bsc-manager-roster-trend ${up ? 'up' : 'down'}`}><TrendIcon size={12} aria-hidden="true" />{up ? '+' : ''}{value.toFixed(1)}%</span>;
}

export function ManagerRosterPanel({
  people,
  contributors,
  selectedManagerId,
  teamName,
  search,
  onSearchChange,
  onSelectManager,
}: ManagerRosterPanelProps) {
  const managers = useMemo(() => buildSnapshots(people, contributors), [people, contributors]);
  const normalizedSearch = search.trim().toLowerCase();
  const filteredManagers = normalizedSearch
    ? managers.filter((manager) => `${manager.employeeName} ${manager.employeeId} ${manager.role ?? ''} ${manager.teamName ?? ''}`.toLowerCase().includes(normalizedSearch))
    : managers;

  return (
    <section id="management-roster" className="bsc-panel bsc-panel-pad bsc-manager-roster-panel" aria-label="Manager roster">
      <div className="bsc-manager-roster-head">
        <div>
          <h2>Management roster</h2>
          <p>Select a manager to refresh KPI cards, score details, and trend analysis.</p>
        </div>
        <div className="bsc-manager-roster-tools">
          <span className="bsc-manager-roster-count">{filteredManagers.length} {filteredManagers.length === 1 ? 'manager' : 'managers'}</span>
          <label className="bsc-manager-roster-search">
            <SearchIcon />
            <input
              type="search"
              value={search}
              onChange={(event) => onSearchChange(event.target.value)}
              placeholder="Search managers..."
              aria-label="Search managers"
            />
          </label>
        </div>
      </div>

      <div className="bsc-manager-roster-table-wrap">
        <table className="bsc-manager-roster-table">
          <thead>
            <tr>
              <th>Manager</th>
              <th>Team</th>
              <th>Overall score</th>
              <th>Weighted contribution</th>
              <th>Primary KPI</th>
              <th>Trend</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {filteredManagers.map((manager, index) => {
              const selected = manager.employeeId === selectedManagerId;
              const tone = scoreClass(manager.score);
              const select = () => onSelectManager(manager.employeeId);

              return (
                <tr
                  key={manager.employeeId}
                  className={selected ? 'is-selected' : ''}
                  role="radio"
                  aria-label={`Select ${manager.employeeName}`}
                  aria-checked={selected}
                  tabIndex={0}
                  onClick={select}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault();
                      select();
                    }
                  }}
                >
                  <td>
                    <div className="bsc-manager-roster-person">
                      <span className={`bsc-manager-radio ${selected ? 'checked' : ''}`} aria-hidden="true"><i /></span>
                      <span className="bsc-emp-avatar" style={{ background: avatarColor(index) }}>{initials(manager.employeeName)}</span>
                      <div className="flex flex-col justify-center">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <strong className="text-sm font-extrabold text-[var(--text-primary)]">{manager.employeeName}</strong>
                          {manager.role && (
                            <span style={{
                              fontSize: 10,
                              fontWeight: 600,
                              padding: '1px 8px',
                              borderRadius: 99,
                              background: 'rgba(46, 111, 224, 0.08)',
                              color: '#2E6FE0',
                              border: '1px solid rgba(46, 111, 224, 0.2)',
                              whiteSpace: 'nowrap',
                              lineHeight: 1.4,
                            }}>
                              {manager.role}
                            </span>
                          )}
                        </div>
                        <small style={{ color: 'var(--text-muted, #9CA3AF)', fontSize: 11, fontWeight: 500 }}>{manager.employeeId}</small>
                      </div>
                    </div>
                  </td>
                  <td><span className="bsc-manager-roster-team">{manager.teamName || teamName || 'All teams'}</span></td>
                  <td><strong className={`bsc-manager-roster-score ${tone}`}>{manager.score == null ? 'N/A' : `${manager.score.toFixed(1)}%`}</strong></td>
                  <td><span className="bsc-manager-roster-contribution">{manager.contribution == null ? '—' : `${(manager.contribution * 100).toFixed(1)}%`}</span></td>
                  <td><span className="bsc-manager-roster-top-kpi" title={manager.topKpi ?? undefined}>{manager.topKpi || '—'}</span></td>
                  <td><ArrowTrend value={manager.trend} /></td>
                  <td><span className={`bsc-status-pill ${tone}`}><i />{statusLabel(tone)}</span></td>
                </tr>
              );
            })}
            {!filteredManagers.length && (
              <tr><td colSpan={7} className="bsc-manager-roster-empty">No managers match this search.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default ManagerRosterPanel;
