import { Activity, TrendingDown, TrendingUp } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ExecutiveDriver, ExecutiveSummary } from '../../../features/executive/types';
import { arrow, fmtKpiDelta, fmtKpiValue, fmtSigned, kpiChangeDelta, kpiMovementTone, toneColor } from '../../../features/executive/format';
import { driverImpact } from './execModel';
import { comparisonName, coveredPeriodLabel, vsLabel } from '../../../features/executive/periodLabels';
import { DirectionTag, ExecCard, ExecCardHeader, Footnote, SoftEmpty } from './ExecPrimitives';

type Metric = ExecutiveSummary['meta']['driver_metric'];


function leadWithFunction(drivers: ExecutiveDriver[], focus: string | null): ExecutiveDriver[] {
  if (!focus) return drivers;
  const index = drivers.findIndex((driver) => driver.function === focus);
  if (index <= 0) return drivers;
  return [drivers[index], ...drivers.slice(0, index), ...drivers.slice(index + 1)];
}

function DriverRow({ driver, side, metric, max, note }: { driver: ExecutiveDriver; side: 'negative' | 'positive'; metric: Metric; max: number; note?: string | null }) {
  const impact = driverImpact(driver, side, metric);
  const movement = kpiMovementTone(driver);
  const changeDelta = kpiChangeDelta(driver);
  const barColor = side === 'negative' ? 'var(--insights-negative)' : 'var(--insights-positive)';
  const width = impact === null || max <= 0 ? 0 : Math.max(6, Math.round((Math.abs(impact) / max) * 100));
  const sub = [driver.team, driver.function].filter(Boolean).join(' · ');
  return (
    <li className="flex flex-col gap-[6px]" data-testid={`driver-${side}`}>
      <div className="flex items-start gap-[10px]">
        <div className="flex min-w-0 flex-1 flex-col gap-[3px]">
          {note && <span className="text-[11px] font-semibold text-[var(--insights-negative)]">{note}</span>}
          <span className="truncate text-[13px] font-semibold text-[var(--insights-heading)]">{driver.kpi_label}</span>
          {sub && <span className="truncate text-xs text-[var(--text-muted)]">{sub}</span>}
          <div className="flex flex-wrap items-center gap-[6px]">
            <DirectionTag direction={driver.kpi_direction} />
            {driver.current_value !== null && <span className="text-[12px] font-bold text-[var(--insights-heading)]">{fmtKpiValue(driver.current_value, driver.unit)}</span>}
            {changeDelta !== null && (
              <span data-tone={movement} className="text-xs font-semibold" style={{ color: toneColor(movement) }}>
                {arrow(changeDelta)} {fmtKpiDelta(changeDelta, driver.unit)}
              </span>
            )}
          </div>
        </div>
        <div className="flex w-[64px] shrink-0 flex-col items-end">
          <span className="text-[14px] font-bold" style={{ color: barColor }}>{fmtSigned(impact, '%', 2)}</span>
        </div>
      </div>
      <div aria-hidden="true" className="h-[6px] w-full rounded-[3px] bg-[var(--insights-track)]">
        <div className="h-full rounded-[3px]" style={{ width: `${width}%`, background: barColor }} />
      </div>
    </li>
  );
}

function Panel({ side, drivers, metric, caption, focus }: { side: 'negative' | 'positive'; drivers: ExecutiveDriver[]; metric: Metric; caption: string; focus: string | null }) {
  const negative = side === 'negative';
  const ordered = negative ? leadWithFunction(drivers, focus) : drivers;
  const max = Math.max(0, ...ordered.map((driver) => Math.abs(driverImpactOrZero(driver, side, metric))));
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
      <p className="-mt-[6px] text-[11px] leading-[1.4] text-[var(--text-muted)]">{caption}</p>
      {ordered.length ? (
        <ul className="flex flex-col gap-[14px]">
          {ordered.map((driver, index) => (
            <DriverRow
              key={`${driver.kpi_label}-${driver.team}`}
              driver={driver}
              side={side}
              metric={metric}
              max={max}
              note={negative && index === 0 && focus && driver.function === focus ? 'Explains the headline' : null}
            />
          ))}
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

export default function DriversCard({ summary, viewAllHref, title }: { summary: ExecutiveSummary; viewAllHref: string | null; title?: string }) {
  const { drivers, meta, period } = summary;
  const previous = period.previous ? period.previous.month : 'last month';
  const range = period.range ?? null;
  const unavailable = meta.unavailable.includes('drivers');
  const metric = meta.driver_metric;
  const focus = summary.scope.view === 'corporate' ? summary.hero.story?.biggest_drag?.function ?? null : null;
  const defaultTitle = range ? `What moved the score ${vsLabel(period.previous, range, '')}` : `What moved the score vs ${previous.slice(0, 3)}`;
  const subtitle = range
    ? `Direction-aware: colour shows good/bad, arrow shows the KPI's actual movement · ${coveredPeriodLabel(period.effective, range)}`
    : "Direction-aware: colour shows good/bad, arrow shows the KPI's actual movement";
  return (
    <ExecCard aria-labelledby="exec-drivers-title">
      <ExecCardHeader
        titleId="exec-drivers-title"
        icon={Activity}
        iconBg="var(--exec-neg-bg)"
        iconColor="var(--insights-negative)"
        title={title ?? defaultTitle}
        subtitle={subtitle}
        action={viewAllHref ? <Link to={viewAllHref} className="inline-flex shrink-0 items-center rounded-[8px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-[10px] py-[6px] text-[12px] font-semibold text-[var(--insights-accent-text)]">View all drivers</Link> : null}
      />
      {unavailable ? (
        <SoftEmpty>{range ? 'KPI drivers are not defined for a range. The function order above still shows who carries the gap. Switch to a single month for the KPI list.' : 'Driver analysis isn\'t available for this view yet.'}</SoftEmpty>
      ) : (
        <div className="grid gap-[12px] md:grid-cols-2">
          <Panel side="negative" drivers={drivers.negative} metric={metric} focus={focus} caption={metric === 'weighted_gap' ? 'KPI weight × gap to target' : 'Change in weighted contribution'} />
          <Panel side="positive" drivers={drivers.positive} metric={metric} focus={null} caption={`Change in weighted contribution vs ${range ? (comparisonName(period.previous, range) ?? 'the previous range') : previous}`} />
        </div>
      )}
      {!unavailable && (
        <Footnote>
          {metric === 'weighted_gap'
            ? `Red is KPI weight × gap to target (%). Green is the change in weighted contribution vs ${range ? (comparisonName(period.previous, range) ?? 'the previous range') : previous} (%).`
            : `Impact = change in the KPI's weighted contribution to the score vs ${range ? (comparisonName(period.previous, range) ?? 'the previous range') : previous} (%). Ranking switches to weight × gap once the backend sends it.`}
        </Footnote>
      )}
    </ExecCard>
  );
}
