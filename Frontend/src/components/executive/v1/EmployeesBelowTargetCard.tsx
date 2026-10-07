import { ArrowUpRight, UserRound } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ExecutiveSummary } from '../../../features/executive/types';
import { employeeProfilePath } from '../../../features/executive/viewModel';
import { fmtScore } from '../../../features/executive/format';
import { ExecCard, ExecCardHeader, GradeSquare, ScoreText, SoftEmpty } from './ExecPrimitives';

export default function EmployeesBelowTargetCard({ summary }: { summary: ExecutiveSummary }) {
  const people = summary.people?.below_90 ?? summary.people?.bottom.filter((person) => person.score !== null && person.score < 90) ?? [];
  return (
    <ExecCard aria-labelledby="exec-employees-below-title">
      <ExecCardHeader titleId="exec-employees-below-title" icon={UserRound} iconBg="var(--exec-neg-bg)" iconColor="var(--insights-negative)" title="Employees below 90%" subtitle={`${people.length} ${people.length === 1 ? 'person' : 'people'} in the selected scope · open a name for their 360 profile`} />
      {people.length ? (
        <div className="max-h-[420px] overflow-y-auto">
          <ul className="grid gap-x-[24px] lg:grid-cols-2">
            {people.map((person) => (
              <li key={`${person.employee_id}:${person.performance_level ?? ''}`}>
                <Link to={employeeProfilePath(person, summary.period.effective)} className="flex items-center gap-[10px] rounded-[8px] border-b border-[var(--insights-row-border)] px-[6px] py-[10px] hover:bg-[var(--exec-tile-bg)] focus-visible:outline-2 focus-visible:outline-[var(--insights-accent)]">
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
        </div>
      ) : <SoftEmpty>No employees below 90% in this filtered scope.</SoftEmpty>}
    </ExecCard>
  );
}
