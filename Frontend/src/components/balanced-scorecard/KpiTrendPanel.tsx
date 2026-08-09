import type { BscKpiRow } from '../../hooks/api/useBalancedScorecard';
import { fmtScore, fmtVal, fmtVariance, scoreClass } from './types';
import StatusPill from './StatusPill';

interface KpiHistoryPoint {
  month: string;
  year: number;
  score?: number | null;
  actual_value?: number | null;
  target_value?: number | null;
}

interface KpiTrendPanelProps {
  kpiRow: BscKpiRow;
  history: KpiHistoryPoint[];
}

export function KpiTrendPanel({
  kpiRow,
  history,
}: KpiTrendPanelProps) {
  if (!kpiRow) return null;

  if (history.length < 2) {
    return (
      <div className="bsc-panel bsc-panel-pad bsc-kpi-trend-panel">
        <div className="bsc-panel-head">
          <div>
            <h2>KPI Trend Analysis</h2>
            <div className="bsc-sub">{kpiRow.kpi_label}</div>
          </div>
        </div>
        <div className="bsc-kpi-trend-table-shell" role="status" style={{ padding: 24, textAlign: 'center' }}>
          <strong>Not enough data for a real trend</strong>
          <div className="bsc-sub" style={{ marginTop: 6 }}>
            At least two measured periods for this KPI are required.
          </div>
        </div>
      </div>
    );
  }

  const latest  = history[history.length - 1];
  const prev    = history[history.length - 2];
  const latestScore  = latest?.score ?? null;
  const prevScore    = prev?.score ?? null;
  const latestActual = latest?.actual_value ?? null;

  const vsLastMonth = latestScore != null && prevScore != null
    ? `${latestScore - prevScore > 0 ? '+' : ''}${(latestScore - prevScore).toFixed(1)}%`
    : 'N/A';

  const monthsAtTarget = history.filter(h => {
    if (h.actual_value == null || h.target_value == null) return false;
    return kpiRow.direction === 'lower_better'
      ? h.actual_value <= h.target_value
      : h.actual_value >= h.target_value;
  }).length;

  const measuredScores = history
    .map(item => item.score)
    .filter((score): score is number => typeof score === 'number' && Number.isFinite(score));
  const avg = measuredScores.length
    ? measuredScores.reduce((sum, score) => sum + score, 0) / measuredScores.length
    : null;

  const trendUp = (latestScore ?? 0) >= (prevScore ?? 0);
  const targetMet =
    latestActual != null && kpiRow.target_value != null
      ? (kpiRow.direction === 'lower_better'
          ? latestActual <= kpiRow.target_value
          : latestActual >= kpiRow.target_value)
      : null;
  const momentumLabel =
    latestScore == null || prevScore == null
      ? 'Awaiting trend signal'
      : latestScore - prevScore >= 3
        ? 'Building momentum'
        : latestScore - prevScore >= 0
          ? 'Holding steady'
          : 'Needs recovery';
  const momentumTone = latestScore == null || prevScore == null
    ? 'neutral'
    : latestScore - prevScore >= 0
      ? 'positive'
      : 'negative';

  const stats = [
    { label: 'Latest Score',      value: fmtScore(latestScore),   color: '#2E6FE0' },
    { label: 'vs Last Month',     value: vsLastMonth,             color: trendUp ? '#1A8C53' : '#D03B3B' },
    { label: '6-Month Avg',       value: fmtScore(avg, 1),        color: '#7C5CE0' },
    { label: 'Months at Target',  value: `${monthsAtTarget}/${history.length}`, color: '#E0832E' },
    { label: 'Latest Actual',     value: fmtVal(latestActual, kpiRow.unit), color: '#5B616E' },
  ];

  return (
    <div className="bsc-panel bsc-panel-pad bsc-kpi-trend-panel">
      <div className="bsc-panel-head">
        <div>
          <h2>KPI Trend Analysis</h2>
          <div className="bsc-sub">{kpiRow.kpi_label}</div>
        </div>
      </div>

      <div className="bsc-kpi-trend-hero">
        <div className="bsc-kpi-trend-hero-copy">
          <div className={`bsc-kpi-trend-badge ${momentumTone}`}>
            <span className="dot" />
            {momentumLabel}
          </div>
          <div className="bsc-kpi-trend-summary">
            {latestScore != null ? fmtScore(latestScore) : 'N/A'}
            <span>
              {targetMet == null
                ? 'Latest measured score'
                : targetMet
                  ? 'Tracking at or above target'
                  : 'Below target and needs attention'}
            </span>
          </div>
        </div>
        <div className="bsc-kpi-trend-hero-side">
          <div className="bsc-kpi-trend-side-label">Current Target</div>
          <div className="bsc-kpi-trend-side-value">
            {fmtVal(kpiRow.target_value, kpiRow.unit)}
          </div>
        </div>
      </div>

      <div className="bsc-kpi-trend-table-shell" style={{ overflowX:'auto' }}>
        <table className="bsc-table">
          <thead>
            <tr>
              <th>Month</th>
              <th>Actual</th>
              <th>Target</th>
              <th>Score</th>
              <th>Variance</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {[...history].reverse().map((h, i) => {
              const unit = (kpiRow.unit ?? '').replace(/\bcount\b/gi, '').trim();
              const isPctOrRatio = !unit || unit === '%';

              const actualVal = h.actual_value;
              const targetVal = h.target_value;

              let variance: number | null = null;
              if (actualVal != null && targetVal != null) {
                if (isPctOrRatio) {
                  const actualPct = actualVal <= 1 ? actualVal * 100 : actualVal;
                  const targetPct = targetVal <= 1 ? targetVal * 100 : targetVal;
                  variance = kpiRow.direction === 'lower_better' ? targetPct - actualPct : actualPct - targetPct;
                } else {
                  variance = kpiRow.direction === 'lower_better' ? targetVal - actualVal : actualVal - targetVal;
                }
              }

              return (
                <tr key={i}>
                  <td style={{ fontWeight: 600 }}>{h.month} {h.year}</td>
                  <td>{fmtVal(h.actual_value, kpiRow.unit)}</td>
                  <td>{fmtVal(h.target_value, kpiRow.unit)}</td>
                  <td><span className={`bsc-score-val ${scoreClass(h.score)}`}>{fmtScore(h.score)}</span></td>
                  <td style={{ fontWeight: 700, color: variance != null ? (variance >= 0 ? '#1A8C53' : '#D03B3B') : '#8A8F99' }}>
                    {fmtVariance(variance, kpiRow.unit)}
                  </td>
                  <td><StatusPill status={scoreClass(h.score)} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* 5 Stat Cards */}
      <div className="bsc-kpi-trend-stats">
        {stats.map((s, i) => (
          <div
            key={i}
            className="bsc-stat-card bsc-kpi-trend-stat-card"
            style={{
              ['--bsc-stat-accent' as string]: s.color,
              ['--bsc-stat-bg' as string]: `color-mix(in srgb, ${s.color} 14%, var(--bsc-panel-bg-soft) 86%)`,
            }}
          >
            <div className="bsc-kpi-trend-stat-copy">
              <div className="bsc-stat-num" style={{ color: s.color }}>{s.value}</div>
              <div className="bsc-stat-lbl">{s.label}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default KpiTrendPanel;
