import { Activity, TrendingDown, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ExecutiveDriver, ExecutiveSummary } from '../../../features/executive/types';
import { arrow, fmtKpiDelta, fmtKpiValue, kpiMovementTone, toneColor } from '../../../features/executive/format';
import { driverImpact } from './execModel';
import { DirectionTag, ExecCard, ExecCardHeader, Footnote, SoftEmpty } from './ExecPrimitives';

type Metric = ExecutiveSummary['meta']['driver_metric'];


const fmtPts = (value: number | null) => (value === null ? '—' : `${value > 0 ? '+' : value < 0 ? '\u2212' : ''}${Math.abs(value).toFixed(2)}`);

function DriverRow({ driver, side, metric, max }: { driver: ExecutiveDriver; side: 'negative' | 'positive'; metric: Metric; max: number }) {
  const impact = driverImpact(driver, side, metric);
  const movement = kpiMovementTone(driver);
  const barColor = side === 'negative' ? 'var(--insights-negative)' : 'var(--insights-positive)';
  const width = impact === null || max <= 0 ? 0 : Math.max(6, Math.round((Math.abs(impact) / max) * 100));
  const sub = [driver.team, driver.function].filter(Boolean).join(' · ');
  return (
    <li className="flex flex-col gap-[6px]" data-testid={`driver-${side}`}>
      <div className="flex items-start gap-[10px]">
        <div className="flex min-w-0 flex-1 flex-col gap-[3px]">
          <span className="truncate text-[13px] font-semibold text-[var(--insights-heading)]">{driver.kpi_label}</span>
          {sub && <span className="truncate text-[11px] text-[var(--text-muted)]">{sub}</span>}
          <div className="flex flex-wrap items-center gap-[6px]">
            <DirectionTag direction={driver.kpi_direction} />
            {driver.current_value !== null && <span className="text-[12px] font-bold text-[var(--insights-heading)]">{fmtKpiValue(driver.current_value, driver.unit)}</span>}
            {driver.raw_change !== null && (
              <span data-tone={movement} className="text-[11px] font-semibold" style={{ color: toneColor(movement) }}>
                {arrow(driver.raw_change)} {fmtKpiDelta(driver.raw_change, driver.unit)}
              </span>
            )}
          </div>
        </div>
        <div className="flex w-[64px] shrink-0 flex-col items-end">
          <span className="text-[14px] font-bold" style={{ color: barColor }}>{fmtPts(impact)}</span>
          <span className="text-[10px] text-[var(--text-muted)]">pts</span>
        </div>
      </div>
      <div aria-hidden="true" className="h-[6px] w-full rounded-[3px] bg-[var(--insights-track)]">
        <div className="h-full rounded-[3px]" style={{ width: `${width}%`, background: barColor }} />
      </div>
    </li>
  );
}

function Panel({ side, drivers, metric }: { side: 'negative' | 'positive'; drivers: ExecutiveDriver[]; metric: Metric }) {
  const negative = side === 'negative';
  const max = Math.max(0, ...drivers.map((driver) => Math.abs(driverImpactOrZero(driver, side, metric))));
  const Icon = negative ? TrendingDown : TrendingUp;
  return (
    <div
      className="flex min-w-0 flex-col gap-[12px] rounded-[10px] border p-[14px]"
      style={{
        background: negative ? 'var(--insights-negative-panel-bg)' : 'var(--insights-positive-panel-bg)',
        borderColor: negative ? 'var(--insights-negative-panel-border)' : 'var(--insights-positive-panel-border)',
      }}
    >
      <h3 className="flex items-center gap-[6px] text-[13px] font-bold" style={{ color: negative ? 'var(--insights-negative)' : 'var(--insights-positive)' }}>
        <Icon aria-hidden="true" className="size-[14px]" strokeWidth={2} />
        {negative ? 'Top negative drivers' : 'Top positive drivers'}
      </h3>
      {drivers.length ? (
        <ul className="flex flex-col gap-[14px]">
          {drivers.map((driver) => <DriverRow key={`${driver.kpi_label}-${driver.team}`} driver={driver} side={side} metric={metric} max={max} />)}
        </ul>
      ) : (
        <p className="text-[12px] text-[var(--text-muted)]">{negative ? 'No KPI pulled the score down.' : 'No KPI closed its gap this month.'}</p>
      )}
    </div>
  );
}

function driverImpactOrZero(driver: ExecutiveDriver, side: 'negative' | 'positive', metric: Metric) {
  return driverImpact(driver, side, metric) ?? 0;
}

export default function DriversCard({ summary, viewAllHref }: { summary: ExecutiveSummary; viewAllHref: string | null }) {
  const { drivers, meta, period } = summary;
  const previous = period.previous ? period.previous.month : 'last month';
  const unavailable = meta.unavailable.includes('drivers');
  const metric = meta.driver_metric;
  return (
    <ExecCard aria-labelledby="exec-drivers-title">
      <ExecCardHeader
        titleId="exec-drivers-title"
        icon={Activity}
        iconBg="var(--exec-neg-bg)"
        iconColor="var(--insights-negative)"
        title={`What moved the score vs ${previous.slice(0, 3)}`}
        subtitle="Direction-aware: colour shows good/bad, arrow shows the KPI's actual movement"
        action={viewAllHref ? <Link to={viewAllHref} className="inline-flex shrink-0 items-center rounded-[8px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-[10px] py-[6px] text-[12px] font-semibold text-[var(--insights-accent-text)]">View all drivers</Link> : null}
      />
      {unavailable ? (
        <SoftEmpty>Driver analysis isn&apos;t available for this view yet.</SoftEmpty>
      ) : (
        <div className="grid gap-[12px] md:grid-cols-2">
          <Panel side="negative" drivers={drivers.negative} metric={metric} />
          <Panel side="positive" drivers={drivers.positive} metric={metric} />
        </div>
      )}
      {!unavailable && (
        <Footnote>
          {metric === 'weighted_gap'
            ? 'Impact = KPI weight × gap to target, in score points.'
            : `Impact = change in the KPI's weighted contribution to the score vs ${previous} (pts). Ranking switches to weight × gap once the backend sends it.`}
        </Footnote>
      )}
    </ExecCard>
  );
}
