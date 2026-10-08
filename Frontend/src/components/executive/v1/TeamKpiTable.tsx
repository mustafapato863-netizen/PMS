import { useId, useState, type ReactNode } from 'react';
import { ChevronLeft, ChevronRight, Target } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ExecutiveKpiRow, ExecutivePeriod } from '../../../features/executive/types';
import { arrow, fmtKpiDelta, fmtKpiValue, fmtScore, kpiChangeDelta, kpiGapDelta, kpiMovementTone, toneColor } from '../../../features/executive/format';
import { gapTone } from './execModel';
import { DirectionTag, ExecCard, ExecCardHeader, GradeSquare, ScoreText, SoftEmpty } from './ExecPrimitives';

const PAGE_SIZE = 8;

type TeamKpiTableProps = {
  rows: ExecutiveKpiRow[]; effective: ExecutivePeriod | null; previous: ExecutivePeriod | null; score: number | null; reportHref?: string | null;
  title?: string; subtitle?: string; showTeams?: boolean; headerAction?: ReactNode; emptyMessage?: ReactNode; scoreLabel?: string;
};

export default function TeamKpiTable(props: TeamKpiTableProps) {
  // New periods, scopes or ordering start on page one; value-only refreshes
  // retain the page. Navigation only slices the already loaded rollup.
  const contextKey = JSON.stringify([props.effective?.key, props.title, props.showTeams,
    props.rows.map((row) => [row.kpi_key, row.teams])]);
  return <PaginatedKpiTable key={contextKey} {...props} />;
}

function PaginatedKpiTable({ rows, effective, previous, score, reportHref, title = 'Team KPIs — worst first', subtitle, showTeams = false, headerAction = null, emptyMessage = 'No KPI breakdown for this month.', scoreLabel = 'Team score' }: TeamKpiTableProps) {
  const titleId = useId();
  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  const pageIndex = Math.min(page, pageCount - 1);
  const offset = pageIndex * PAGE_SIZE;
  const pageRows = rows.slice(offset, offset + PAGE_SIZE);
  const head = 'text-[10px] font-semibold uppercase tracking-[0.6px] text-[var(--text-muted)]';
  const vs = previous ? `vs ${previous.month.slice(0, 3)}` : 'vs last';
  return (
    <ExecCard aria-labelledby={titleId}>
      <ExecCardHeader
        titleId={titleId}
        icon={Target}
        iconBg="var(--exec-info-bg)"
        iconColor="var(--exec-info-text)"
        title={title}
        subtitle={subtitle ?? `Sorted by achievement${effective ? ` · ${effective.month} ${effective.year}` : ''}`}
        action={(
          <div className="flex flex-wrap items-center justify-end gap-[8px]">
            {headerAction}
            <span className="rounded-full bg-[var(--exec-chip-bg)] px-[8px] py-[2px] text-[11px] font-semibold text-[var(--exec-chip-text)]">{rows.length} KPIs</span>
            {reportHref && <Link to={reportHref} className="inline-flex items-center rounded-[8px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-[10px] py-[6px] text-[12px] font-semibold text-[var(--insights-accent-text)]">Open team report</Link>}
          </div>
        )}
      />
      {rows.length ? (
        <div className="overflow-x-auto">
          <div role="table" aria-label={title} className={`flex flex-col ${showTeams ? 'min-w-[760px]' : 'min-w-[640px]'}`}>
            <div role="row" className="flex items-center gap-[12px] rounded-[8px] bg-[var(--exec-table-head-bg)] px-[12px] py-[9px]">
              {showTeams && <span role="columnheader" className={`${head} w-[150px]`}>Teams</span>}
              <span role="columnheader" className={`${head} min-w-0 flex-1`}>KPI</span>
              <span role="columnheader" className={`${head} w-[84px]`}>Direction</span>
              <span role="columnheader" className={`${head} w-[72px] text-right`}>Actual</span>
              <span role="columnheader" className={`${head} w-[64px] text-right`}>Target</span>
              <span role="columnheader" className={`${head} w-[80px] text-right`}>Gap</span>
              <span role="columnheader" className={`${head} w-[80px] text-right`}>{vs}</span>
              <span role="columnheader" className={`${head} hidden w-[56px] text-right lg:block`}>Weight</span>
              <span role="columnheader" className={`${head} w-[96px] text-right`}>Achievement</span>
            </div>
            {pageRows.map((row, index) => {
              const movement = kpiMovementTone(row);
              const gapDelta = kpiGapDelta(row);
              const changeDelta = kpiChangeDelta(row);
              const gap = gapTone(row);
              return (
                <div role="row" key={row.kpi_key} className="flex items-center gap-[12px] border-b border-[var(--insights-row-border)] px-[12px] py-[10px] last:border-b-0" data-testid="kpi-row">
                  {showTeams && <span role="cell" className="w-[150px] truncate text-[12px] text-[var(--text-secondary)]" title={row.teams.join(', ')}>{row.teams.join(', ')}</span>}
                  <span role="cell" className="flex min-w-0 flex-1 items-center gap-[10px]">
                    <span className="w-[14px] text-[12px] text-[var(--text-muted)]">{offset + index + 1}</span>
                    <span className="truncate text-[13px] font-semibold text-[var(--insights-heading)]">{row.kpi_label}</span>
                  </span>
                  <span role="cell" className="w-[84px]"><DirectionTag direction={row.kpi_direction} /></span>
                  <span role="cell" className="w-[72px] text-right text-[13px] font-bold text-[var(--insights-heading)]">{fmtKpiValue(row.actual, row.unit)}</span>
                  <span role="cell" className="w-[64px] text-right text-[12px] text-[var(--text-secondary)]">{fmtKpiValue(row.target, row.unit)}</span>
                  <span role="cell" data-tone={gap} className="w-[80px] text-right text-[12px] font-semibold" style={{ color: toneColor(gap) }}>{gapDelta === null ? '—' : `${arrow(gapDelta)} ${fmtKpiDelta(gapDelta, row.unit)}`}</span>
                  <span role="cell" data-tone={movement} className="w-[80px] text-right text-[12px] font-semibold" style={{ color: toneColor(movement) }}>{changeDelta === null ? '—' : `${arrow(changeDelta)} ${fmtKpiDelta(changeDelta, row.unit)}`}</span>
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
      ) : <SoftEmpty>{emptyMessage}</SoftEmpty>}
      {pageCount > 1 && (
        <nav aria-label={`${title} pages`} className="flex flex-wrap items-center justify-between gap-[12px] border-t border-[var(--insights-row-border)] px-[6px] pt-[12px]">
          <span aria-live="polite" className="text-[12px] text-[var(--text-muted)]">
            Showing {offset + 1}–{Math.min(offset + PAGE_SIZE, rows.length)} of {rows.length} · Page {pageIndex + 1} of {pageCount}
          </span>
          <span className="flex items-center gap-[8px]">
            <button type="button" aria-label="Previous page" onClick={() => setPage(pageIndex - 1)} disabled={pageIndex === 0} className="inline-flex size-[44px] items-center justify-center rounded-[8px] border border-[var(--exec-card-border)] text-[var(--text-secondary)] enabled:hover:bg-[var(--exec-tile-bg)] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-[var(--insights-accent)]">
              <ChevronLeft aria-hidden="true" className="size-[16px]" />
            </button>
            <button type="button" aria-label="Next page" onClick={() => setPage(pageIndex + 1)} disabled={pageIndex >= pageCount - 1} className="inline-flex size-[44px] items-center justify-center rounded-[8px] border border-[var(--exec-card-border)] text-[var(--text-secondary)] enabled:hover:bg-[var(--exec-tile-bg)] disabled:cursor-not-allowed disabled:opacity-40 focus-visible:outline-2 focus-visible:outline-[var(--insights-accent)]">
              <ChevronRight aria-hidden="true" className="size-[16px]" />
            </button>
          </span>
        </nav>
      )}
      <div className="flex flex-wrap items-center justify-between gap-[8px] text-[11px] text-[var(--text-muted)]">
        <span className="flex flex-wrap items-center gap-[8px]">
          <DirectionTag direction="higher_better" /> higher is better
          <DirectionTag direction="lower_better" /> lower is better
          <span>· Gap, change, colour and arrows are adjusted to each KPI&apos;s direction (positive = better).</span>
        </span>
        {score !== null && !showTeams && <span>{scoreLabel} = Σ weight × achievement (capped 100%) = {fmtScore(score)}</span>}
        {showTeams && <span>Headcount-weighted across the function&apos;s teams.</span>}
      </div>
    </ExecCard>
  );
}
