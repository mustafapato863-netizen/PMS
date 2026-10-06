import { AlertTriangle, Award, TrendingDown, TrendingUp, UserRound } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ExecutivePeople, ExecutivePerson, ExecutivePeriod } from '../../../features/executive/types';
import { arrow, fmtScore, fmtSigned, scoreTone, toneColor } from '../../../features/executive/format';
import { ExecCard, ExecCardHeader, GradeSquare, ScoreText, SoftEmpty } from './ExecPrimitives';

const initials = (name: string) => name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join('');

function PersonRow({ person, vs }: { person: ExecutivePerson; vs: string }) {
  const tone = scoreTone(person.change);
  return (
    <li>
      <Link to={`/employee/${encodeURIComponent(person.employee_id)}`} className="flex items-center gap-[10px] rounded-[8px] px-[4px] py-[6px] hover:bg-[var(--exec-tile-bg)]">
        <span aria-hidden="true" className="flex size-[30px] shrink-0 items-center justify-center rounded-full bg-[var(--exec-info-bg)] text-[11px] font-semibold text-[var(--exec-info-text)]">{initials(person.name)}</span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="truncate text-[13px] font-semibold text-[var(--insights-heading)]">{person.name}</span>
          <span className="truncate text-[11px] text-[var(--text-muted)]">{person.position ?? '—'}</span>
        </span>
        <span className="flex flex-col items-end">
          <ScoreText score={person.score} className="text-[13px]">{fmtScore(person.score)}</ScoreText>
          <span className="text-[11px] font-medium" style={{ color: toneColor(tone) }}>{person.change === null ? 'new' : `${arrow(person.change)} ${fmtSigned(person.change)} ${vs}`}</span>
        </span>
        <GradeSquare score={person.score} />
      </Link>
    </li>
  );
}

export function PeopleToReviewCard({ people, team, previous, rosterHref }: { people: ExecutivePeople | null; team: string | null; previous: ExecutivePeriod | null; rosterHref?: string | null }) {
  const vs = previous ? `vs ${previous.month.slice(0, 3)}` : '';
  return (
    <ExecCard aria-labelledby="exec-people-title">
      <ExecCardHeader
        titleId="exec-people-title"
        icon={UserRound}
        iconBg="var(--exec-neg-bg)"
        iconColor="var(--insights-negative)"
        title="People to review"
        subtitle={`Lowest scores and largest month-on-month drops${team ? ` in ${team}` : ''}`}
        action={rosterHref ? <Link to={rosterHref} className="inline-flex items-center rounded-[8px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-[10px] py-[6px] text-[12px] font-semibold text-[var(--insights-accent-text)]">View roster</Link> : null}
      />
      {people && people.bottom.length ? (
        <div className="grid gap-[16px] md:grid-cols-2">
          <div className="flex flex-col gap-[6px]">
            <h3 className="flex items-center gap-[6px] text-[12px] font-bold text-[var(--insights-negative)]"><TrendingDown aria-hidden="true" className="size-[13px]" />Bottom performers</h3>
            <ul>{people.bottom.map((person) => <PersonRow key={person.employee_id} person={person} vs={vs} />)}</ul>
          </div>
          <div className="flex flex-col gap-[6px]">
            <h3 className="flex items-center gap-[6px] text-[12px] font-bold text-[var(--exec-warning)]"><AlertTriangle aria-hidden="true" className="size-[13px]" />Biggest drops {vs}</h3>
            {people.biggest_drops.length
              ? <ul>{people.biggest_drops.map((person) => <PersonRow key={person.employee_id} person={person} vs={vs} />)}</ul>
              : <p className="text-[12px] text-[var(--text-muted)]">Nobody dropped month-on-month.</p>}
          </div>
        </div>
      ) : <SoftEmpty>No employee scores for this month.</SoftEmpty>}
    </ExecCard>
  );
}

export function TopPerformersCard({ people, previous }: { people: ExecutivePeople | null; previous: ExecutivePeriod | null }) {
  const vs = previous ? `vs ${previous.month.slice(0, 3)}` : '';
  return (
    <ExecCard aria-labelledby="exec-top-title">
      <ExecCardHeader titleId="exec-top-title" icon={Award} iconBg="var(--exec-pos-bg)" iconColor="var(--insights-positive)" title="Top performers" subtitle="Recognise and use as peer coaches" />
      {people && people.top.length ? (
        <div className="flex flex-col gap-[6px]">
          <h3 className="flex items-center gap-[6px] text-[12px] font-bold text-[var(--insights-positive)]"><TrendingUp aria-hidden="true" className="size-[13px]" />Top {people.top.length} this month</h3>
          <ul>{people.top.map((person) => <PersonRow key={person.employee_id} person={person} vs={vs} />)}</ul>
        </div>
      ) : <SoftEmpty>No employee scores for this month.</SoftEmpty>}
    </ExecCard>
  );
}
