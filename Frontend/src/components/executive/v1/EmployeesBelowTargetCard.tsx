import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowUpRight, ChevronLeft, ChevronRight, UserRound } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiFetch } from '../../../lib/apiClient';
import { performanceSessionKey } from '../../../lib/performanceSessionKey';
import type { ExecutivePerson, ExecutiveSummary } from '../../../features/executive/types';
import { executivePersonPath } from '../../../features/executive/viewModel';
import { fmtScore } from '../../../features/executive/format';
import { ExecCard, ExecCardHeader, GradeSquare, ScoreText, SoftEmpty } from './ExecPrimitives';

const PAGE_SIZE = 8;
const FETCH_BATCH_SIZE = 100;

interface BelowTargetRecord {
  employee_id: string;
  employee_name: string;
  team: string;
  region: string | null;
  performance_level: string;
  position: string | null;
  score: number;
}

interface RecordsPage {
  items: BelowTargetRecord[];
  page_size: number;
  next_cursor: string | null;
  has_more: boolean;
  total: number | null;
}

interface ApiEnvelope<T> {
  success: boolean;
  data: T;
  message?: string;
}

function pageParams(summary: ExecutiveSummary): URLSearchParams {
  const params = new URLSearchParams();
  const period = summary.period.effective?.key;
  if (period) params.set('period', period);

  const { scope } = summary;
  const teamOrFunction = scope.team || scope.function;
  if (teamOrFunction) params.set('team', teamOrFunction);
  if (scope.region && scope.region !== 'All') params.set('region', scope.region);
  if (scope.branch && scope.branch !== 'All') params.set('branch', scope.branch);
  if (scope.position && scope.position !== 'All') params.set('position', scope.position);
  if (scope.performance_level && scope.performance_level !== 'All') {
    params.set('performance_level', scope.performance_level);
  }

  params.set('score_lt', '90');
  params.set('sort', 'score_asc');
  params.set('detail', 'table');
  return params;
}

async function loadRoster(filterKey: string, signal: AbortSignal): Promise<BelowTargetRecord[]> {
  const params = new URLSearchParams(filterKey);
  params.set('page_size', String(FETCH_BATCH_SIZE));
  // Once all bounded batches are cached, their length is the exact roster total.
  params.set('include_total', 'false');
  const items: BelowTargetRecord[] = [];
  const cursors = new Set<string>();

  while (true) {
    const response = await apiFetch<ApiEnvelope<RecordsPage>>(`/api/performance/records?${params.toString()}`, { signal });
    if (!response.success || !Array.isArray(response.data?.items)) {
      throw new Error(response.message || 'Employees below target could not be loaded.');
    }
    items.push(...response.data.items);
    if (!response.data.has_more) return items;

    const cursor = response.data.next_cursor;
    if (!cursor || cursors.has(cursor) || response.data.items.length === 0) {
      throw new Error('Employees below target could not be loaded. Please try again.');
    }
    cursors.add(cursor);
    params.set('cursor', cursor);
  }
}

function toExecutivePerson(record: BelowTargetRecord): ExecutivePerson {
  return {
    employee_id: record.employee_id,
    name: record.employee_name,
    position: record.position,
    team: record.team,
    region: record.region,
    performance_level: record.performance_level,
    score: record.score,
    previous_score: null,
    change: null,
    grade: null,
  };
}

export default function EmployeesBelowTargetCard({ summary }: { summary: ExecutiveSummary }) {
  const filterKey = pageParams(summary).toString();
  // A different scope resets the displayed page without borrowing another scope's rows.
  return <EmployeeRoster key={`${performanceSessionKey()}:${filterKey}`} summary={summary} filterKey={filterKey} />;
}

function EmployeeRoster({ summary, filterKey }: { summary: ExecutiveSummary; filterKey: string }) {
  const [page, setPage] = useState(0);
  const pageQuery = useQuery({
    queryKey: ['performance', 'executive', 'employees-below-90', 'roster', filterKey, performanceSessionKey()],
    queryFn: ({ signal }) => loadRoster(filterKey, signal),
    enabled: Boolean(summary.period.effective?.key),
    retry: false,
    staleTime: 5 * 60_000,
    gcTime: 10 * 60_000,
    refetchOnWindowFocus: false,
  });

  const roster = pageQuery.data ?? [];
  const total = roster.length;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const pageIndex = Math.min(page, pageCount - 1);
  const items = roster.slice(pageIndex * PAGE_SIZE, (pageIndex + 1) * PAGE_SIZE);
  const firstItem = total === 0 ? 0 : pageIndex * PAGE_SIZE + 1;
  const lastItem = Math.min((pageIndex + 1) * PAGE_SIZE, total);
  const people = items.map(toExecutivePerson);

  const goToNextPage = () => {
    setPage(Math.min(pageIndex + 1, pageCount - 1));
  };

  const goToPreviousPage = () => {
    if (pageIndex === 0) return;
    setPage(pageIndex - 1);
  };

  const subtitle = pageQuery.isLoading
    ? `Loading results · ${PAGE_SIZE} per page`
    : `${total} ${total === 1 ? 'person' : 'people'} in the selected scope · ${PAGE_SIZE} per page · Corporate-level names open their BSC; others open their 360 profile`;

  return (
    <ExecCard aria-labelledby="exec-employees-below-title">
      <ExecCardHeader
        titleId="exec-employees-below-title"
        icon={UserRound}
        iconBg="var(--exec-neg-bg)"
        iconColor="var(--insights-negative)"
        title="Employees below 90%"
        subtitle={subtitle}
      />
      {pageQuery.isLoading ? (
        <div role="status" aria-live="polite" className="px-[6px] py-[24px] text-[13px] text-[var(--text-muted)]">
          Loading employees below 90%…
        </div>
      ) : pageQuery.isError && !pageQuery.data ? (
        <div className="flex flex-wrap items-center justify-between gap-[12px] px-[6px] py-[18px]">
          <p role="alert" className="text-[13px] text-[var(--insights-negative)]">
            {pageQuery.error instanceof Error ? pageQuery.error.message : 'Employees below target could not be loaded.'}
          </p>
          <button type="button" onClick={() => void pageQuery.refetch()} className="rounded-[8px] border border-[var(--exec-card-border)] px-[12px] py-[7px] text-[12px] font-semibold text-[var(--insights-accent)] hover:bg-[var(--exec-tile-bg)]">
            Try again
          </button>
        </div>
      ) : people.length ? (
        <>
          <ul className="grid gap-x-[24px] lg:grid-cols-2">
            {people.map((person) => (
              <li key={`${person.employee_id}:${person.performance_level ?? ''}`}>
                <Link to={executivePersonPath(person, summary.period.effective, summary.scope.branch)} className="flex items-center gap-[10px] rounded-[8px] border-b border-[var(--insights-row-border)] px-[6px] py-[10px] hover:bg-[var(--exec-tile-bg)] focus-visible:outline-2 focus-visible:outline-[var(--insights-accent)]">
                  <span className="flex min-w-0 flex-1 flex-col gap-[3px]">
                    <span className="truncate text-[13px] font-semibold text-[var(--insights-heading)]">{person.name}</span>
                    <span className="truncate text-[11px] text-[var(--text-muted)]">{[person.team, person.position, person.performance_level].filter(Boolean).join(' · ')}</span>
                  </span>
                  <ScoreText score={person.score} className="text-[14px]">{fmtScore(person.score)}</ScoreText>
                  <GradeSquare score={person.score} />
                  <ArrowUpRight aria-hidden="true" className="size-[14px] shrink-0 text-[var(--insights-accent)]" />
                </Link>
              </li>
            ))}
          </ul>
          {pageCount > 1 && (
            <nav aria-label="Employees below 90% pages" className="mt-[12px] flex items-center justify-between border-t border-[var(--insights-row-border)] px-[6px] pt-[12px]">
              <span aria-live="polite" className="text-[12px] text-[var(--text-muted)]">
                Showing {firstItem}–{lastItem} of {total} · Page {pageIndex + 1} of {pageCount}
              </span>
              <span className="flex items-center gap-[8px]">
                <button type="button" aria-label="Previous page" onClick={goToPreviousPage} disabled={pageIndex === 0} className="inline-flex size-[34px] items-center justify-center rounded-[8px] border border-[var(--exec-card-border)] text-[var(--text-secondary)] enabled:hover:bg-[var(--exec-tile-bg)] disabled:cursor-not-allowed disabled:opacity-40">
                  <ChevronLeft aria-hidden="true" className="size-[16px]" />
                </button>
                <button type="button" aria-label="Next page" onClick={goToNextPage} disabled={pageIndex >= pageCount - 1} className="inline-flex size-[34px] items-center justify-center rounded-[8px] border border-[var(--exec-card-border)] text-[var(--text-secondary)] enabled:hover:bg-[var(--exec-tile-bg)] disabled:cursor-not-allowed disabled:opacity-40">
                  <ChevronRight aria-hidden="true" className="size-[16px]" />
                </button>
              </span>
            </nav>
          )}
        </>
      ) : (
        <SoftEmpty>No employees below 90% in this filtered scope.</SoftEmpty>
      )}
    </ExecCard>
  );
}
