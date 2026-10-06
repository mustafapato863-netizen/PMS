import { Target } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ExecutiveKpiRow, ExecutivePeriod } from '../../../features/executive/types';
import { arrow, fmtKpiDelta, fmtKpiValue, fmtScore, kpiMovementTone, toneColor } from '../../../features/executive/format';
import { gapTone } from './execModel';
import { DirectionTag, ExecCard, ExecCardHeader, GradeSquare, ScoreText, SoftEmpty } from './ExecPrimitives';


export default function TeamKpiTable({ rows, effective, previous, score, reportHref }: {
  rows: ExecutiveKpiRow[]; effective: ExecutivePeriod | null; previous: ExecutivePeriod | null; score: number | null; reportHref?: string | null;
}) {
  const head = 'text-[10px] font-semibold uppercase tracking-[0.6px] text-[var(--text-muted)]';
  const vs = previous ? `vs ${previous.month.slice(0, 3)}` : 'vs last';
  return (
    <ExecCard aria-labelledby="exec-kpis-title">
      <ExecCardHeader
        titleId="exec-kpis-title"
        icon={Target}
        iconBg="var(--exec-info-bg)"
        iconColor="var(--exec-info-text)"
        title="Team KPIs — worst first"
        subtitle={`Sorted by achievement${effective ? ` · ${effective.month} ${effective.year}` : ''}`}
        action={(
          <div className="flex items-center gap-[8px]">
            <span className="rounded-full bg-[var(--exec-chip-bg)] px-[8px] py-[2px] text-[11px] font-semibold text-[var(--exec-chip-text)]">{rows.length} KPIs</span>
            {reportHref && <Link to={reportHref} className="inline-flex items-center rounded-[8px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-[10px] py-[6px] text-[12px] font-semibold text-[var(--insights-accent-text)]">Open team report</Link>}
          </div>
        )}
      />
      {rows.length ? (
        <div className="overflow-x-auto">
          <div role="table" aria-label="Team KPIs" className="flex min-w-[640px] flex-col">
            <div role="row" className="flex items-center gap-[12px] rounded-[8px] bg-[var(--exec-table-head-bg)] px-[12px] py-[9px]">
              <span role="columnheader" className={`${head} min-w-0 flex-1`}>KPI</span>
              <span role="columnheader" className={`${head} w-[84px]`}>Direction</span>
              <span role="columnheader" className={`${head} w-[72px] text-right`}>Actual</span>
              <span role="columnheader" className={`${head} w-[64px] text-right`}>Target</span>
              <span role="columnheader" className={`${head} w-[80px] text-right`}>Gap</span>
              <span role="columnheader" className={`${head} w-[80px] text-right`}>{vs}</span>
              <span role="columnheader" className={`${head} hidden w-[56px] text-right lg:block`}>Weight</span>
              <span role="columnheader" className={`${head} w-[96px] text-right`}>Achievement</span>
            </div>
            {rows.map((row, index) => {
              const movement = kpiMovementTone(row);
              const gap = gapTone(row);
              return (
                <div role="row" key={row.kpi_key} className="flex items-center gap-[12px] border-b border-[var(--insights-row-border)] px-[12px] py-[10px] last:border-b-0" data-testid="kpi-row">
                  <span role="cell" className="flex min-w-0 flex-1 items-center gap-[10px]">
                    <span className="w-[14px] text-[12px] text-[var(--text-muted)]">{index + 1}</span>
                    <span className="truncate text-[13px] font-semibold text-[var(--insights-heading)]">{row.kpi_label}</span>
                  </span>
                  <span role="cell" className="w-[84px]"><DirectionTag direction={row.kpi_direction} /></span>
                  <span role="cell" className="w-[72px] text-right text-[13px] font-bold text-[var(--insights-heading)]">{fmtKpiValue(row.actual, row.unit)}</span>
                  <span role="cell" className="w-[64px] text-right text-[12px] text-[var(--text-secondary)]">{fmtKpiValue(row.target, row.unit)}</span>
                  <span role="cell" data-tone={gap} className="w-[80px] text-right text-[12px] font-semibold" style={{ color: toneColor(gap) }}>{arrow(row.raw_gap)} {fmtKpiDelta(row.raw_gap, row.unit)}</span>
                  <span role="cell" data-tone={movement} className="w-[80px] text-right text-[12px] font-semibold" style={{ color: toneColor(movement) }}>{row.raw_change === null ? '—' : `${arrow(row.raw_change)} ${fmtKpiDelta(row.raw_change, row.unit)}`}</span>
                  <span role="cell" className="hidden w-[56px] text-right text-[12px] text-[var(--text-secondary)] lg:block">{row.weight === null ? '—' : `${Math.round(row.weight <= 1 ? row.weight * 100 : row.weight)}%`}</span>
                  <span role="cell" className="flex w-[96px] items-center justify-end gap-[6px]">
                    <ScoreText score={row.achievement_percent} className="text-[13px]">{fmtScore(row.achievement_percent)}</ScoreText>
                    <GradeSquare score={row.achievement_percent} />
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      ) : <SoftEmpty>No KPI breakdown for this month.</SoftEmpty>}
      <div className="flex flex-wrap items-center justify-between gap-[8px] text-[11px] text-[var(--text-muted)]">
        <span className="flex flex-wrap items-center gap-[8px]">
          <DirectionTag direction="higher_better" /> higher is better
          <DirectionTag direction="lower_better" /> lower is better
          <span>· Colour = good / bad for that KPI; arrow = actual movement.</span>
        </span>
        {score !== null && <span>Team score = Σ weight × achievement (capped 100%) = {fmtScore(score)}</span>}
      </div>
    </ExecCard>
  );
}
