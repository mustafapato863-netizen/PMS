import type { CSSProperties } from 'react';
import type { BscKpiRow, BscPerson } from '../../hooks/api/useBalancedScorecard';
import { ck, initials, pc, scoreClass, statusClass, statusLabel } from './types';

interface ManagerKpiHighlightsProps {
  manager: BscPerson | null;
  kpis: BscKpiRow[];
  selectedKpi: string | null;
  selectedPerspective: string | null;
  onSelectKpi: (kpiKey: string) => void;
  onClearPerspective: () => void;
}

function formatMetric(value?: number | null, unit?: string) {
  if (value == null || !Number.isFinite(value)) return '—';

  const digits = Number.isInteger(value) ? 0 : Math.abs(value) < 10 ? 1 : 0;
  const formatted = value.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: 1,
  });

  if (unit === '%' || unit === 'percent') return `${formatted}%`;
  if (unit === 'currency') return formatted;
  if (unit === 'min') return `${formatted} min`;
  return unit ? `${formatted} ${unit}` : formatted;
}

function InfoIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5" />
      <path d="M12 8h.01" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

function ArrowIcon({ direction }: { direction: 'up' | 'down' | 'flat' }) {
  if (direction === 'flat') {
    return (
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.7" strokeLinecap="round" aria-hidden="true">
        <path d="M5 12h14" />
      </svg>
    );
  }

  return direction === 'up' ? (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 19V5" />
      <path d="m6 11 6-6 6 6" />
    </svg>
  ) : (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 5v14" />
      <path d="m18 13-6 6-6-6" />
    </svg>
  );
}

function KpiCard({ kpi, isSelected, onSelect }: { kpi: BscKpiRow; isSelected: boolean; onSelect: () => void }) {
  const color = pc(kpi.perspective);
  const scoreTone = scoreClass(kpi.score);
  const statusTone = statusClass(kpi.status) === 'na' ? scoreTone : statusClass(kpi.status);
  const gap = kpi.score == null ? null : kpi.score - 100;
  const direction = gap == null ? 'flat' : gap > 0 ? 'up' : gap < 0 ? 'down' : 'flat';
  const meter = kpi.score == null ? 0 : Math.min(Math.max(kpi.score, 0), 100);
  const customStyle = { '--manager-kpi-color': color } as CSSProperties;

  return (
    <button
      type="button"
      className={`bsc-manager-kpi-card ${ck(kpi.perspective)} ${isSelected ? 'selected' : ''}`}
      style={customStyle}
      onClick={onSelect}
      aria-pressed={isSelected}
      aria-label={`Inspect ${kpi.kpi_label}`}
    >
      <div className="bsc-manager-kpi-card-top">
        <span className="bsc-manager-kpi-perspective">{kpi.perspective}</span>
        <span className="bsc-manager-kpi-info" title="KPI performance for the selected manager"><InfoIcon /></span>
      </div>

      <div className="bsc-manager-kpi-title" title={kpi.kpi_label}>{kpi.kpi_label}</div>

      <div className="bsc-manager-kpi-score-row">
        <span className={`bsc-manager-kpi-score ${scoreTone}`}>{kpi.score == null ? 'N/A' : `${kpi.score.toFixed(1)}%`}</span>
        {gap != null && (
          <span className={`bsc-manager-kpi-gap ${direction}`}>
            <ArrowIcon direction={direction} />
            {gap > 0 ? '+' : gap < 0 ? '−' : ''}{Math.abs(gap).toFixed(1)}%
          </span>
        )}
      </div>

      <div className="bsc-manager-kpi-measurements">
        <span>Actual <strong>{formatMetric(kpi.actual_value, kpi.unit)}</strong></span>
        <span>Target <strong>{formatMetric(kpi.target_value, kpi.unit)}</strong></span>
      </div>

      <div className="bsc-manager-kpi-meter" aria-hidden="true"><span style={{ width: `${meter}%` }} /></div>

      <div className="bsc-manager-kpi-bottom">
        <span className={`bsc-status-pill ${statusTone}`}><i />{statusLabel(kpi.status || statusTone)}</span>
        {kpi.weight != null && (
          <span className="bsc-manager-kpi-weight">{(kpi.weight * 100).toFixed(0)}% weight</span>
        )}
      </div>
    </button>
  );
}

export function ManagerKpiHighlights({
  manager,
  kpis,
  selectedKpi,
  selectedPerspective,
  onSelectKpi,
  onClearPerspective,
}: ManagerKpiHighlightsProps) {
  const visibleKpis = kpis.filter((kpi) =>
    kpi.state !== 'not_configured'
    && [kpi.score, kpi.actual_value, kpi.target_value, kpi.weighted_contribution]
      .some((value) => typeof value === 'number' && Number.isFinite(value)),
  );

  return (
    <section className="bsc-panel bsc-panel-pad bsc-manager-kpi-highlights" aria-label="Selected manager KPI highlights">
      <div className="bsc-manager-kpi-heading">
        <div>
          <div className="bsc-manager-kpi-eyebrow">Manager KPI highlights</div>
          <h2>KPIs tailored to the selected manager</h2>
          <p>KPI cards refresh when you choose a different manager from the roster below.</p>
        </div>
        {selectedPerspective && (
          <button type="button" className="bsc-manager-filter-chip" onClick={onClearPerspective}>
            Filtered: {selectedPerspective}<span aria-hidden="true">×</span>
          </button>
        )}
      </div>

      <div className="bsc-manager-selected-strip">
        <span className="bsc-manager-avatar" aria-hidden="true">{manager ? initials(manager.employee_name) : '—'}</span>
        <div className="bsc-manager-selected-copy">
          <span className="bsc-manager-selected-label">Selected manager</span>
          <strong>{manager?.employee_name ?? 'Choose a manager below'}</strong>
          <span>{manager?.role || 'Management performance view'}{manager?.team_name ? ` · ${manager.team_name}` : ''}</span>
        </div>
        <span className="bsc-manager-selected-status"><i />Live selection</span>
      </div>

      {visibleKpis.length ? (
        <div className="bsc-manager-kpi-grid">
          {visibleKpis.map((kpi) => (
            <KpiCard
              key={kpi.kpi_key}
              kpi={kpi}
              isSelected={selectedKpi === kpi.kpi_key}
              onSelect={() => onSelectKpi(kpi.kpi_key)}
            />
          ))}
        </div>
      ) : (
        <div className="bsc-manager-kpi-empty">
          <strong>No KPI cards are available for this manager and filter.</strong>
          <span>Choose another manager or clear the active perspective filter.</span>
        </div>
      )}
    </section>
  );
}

export default ManagerKpiHighlights;
