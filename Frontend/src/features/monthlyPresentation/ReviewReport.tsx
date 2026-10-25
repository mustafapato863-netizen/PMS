/**
 * The five sections of the Monthly Performance Review.
 * Executive cards are reused so the scores stay the ones compose already produces.
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { GRADE_CLASSES, GRADE_PALETTE, type GradeClass } from '../../constants/grades';
import DriversCard from '../../components/executive/v1/DriversCard';
import ExecutiveHero from '../../components/executive/v1/ExecutiveHero';
import FunctionCards from '../../components/executive/v1/FunctionCards';
import GradeDistributionCard from '../../components/executive/v1/GradeDistributionCard';
import TeamKpiTable from '../../components/executive/v1/TeamKpiTable';
import TeamsAtRiskCard from '../../components/executive/v1/TeamsAtRiskCard';
import { TeamLeaderboardCard } from '../../components/executive/v1/FunctionTeamsCards';
import { fmtScore, fmtSigned } from '../executive/format';
import { summaryTeamMatches } from '../executive/functions';
import type { ExecutiveSummary } from '../executive/types';
import { MASKED_DETAILS_LABEL } from './model';
import {
  maskedDetail, type BranchRow, type DecisionStatus, type MonthlyReview, type RegisterRow,
} from './reviewModel';

const PAGE_SIZE = 8;
const PREVIEW = 5;
const STATUS_LABEL: Record<DecisionStatus, string> = {
  overdue: 'Overdue', no_decision: 'No decision yet', open: 'Open', in_progress: 'In progress', completed: 'Completed', cancelled: 'Cancelled',
};
const STATUS_ORDER: DecisionStatus[] = ['overdue', 'no_decision', 'open', 'in_progress', 'completed', 'cancelled'];

type SortKey = 'name' | 'team' | 'score' | 'change' | 'worst' | 'cause' | 'decision' | 'owner' | 'priority' | 'status' | 'due' | 'evidence';

export interface ReviewReportProps {
  review: MonthlyReview;
  summary: ExecutiveSummary;
  mask: (name: string | null | undefined) => string;
  masked: boolean;
  trendNote: { tone: 'status' | 'alert'; text: string; retry?: () => void } | null;
  actionsNote: { tone: 'status' | 'alert'; text: string; retry?: () => void } | null;
  onOpenFunction?: (name: string) => void;
  onOpenTeam?: (team: string, fn?: string | null, asPosition?: boolean) => void;
}

export function ReviewSections(props: ReviewReportProps): ReactNode[] {
  return [
    <Results key="s01" {...props} />,
    <Problems key="s02" {...props} />,
    <Recognition key="s03" {...props} />,
    <Decisions key="s04" {...props} />,
    <MonthClose key="s05" {...props} />,
  ];
}

function Section({ id, title, kicker, children }: { id: string; title: string; kicker: string; children: ReactNode }) {
  return (
    <section id={id} className="mp-section" aria-label={title}>
      <p className="mp-kicker">{kicker}</p>
      <h2 className="mp-title">{title}</h2>
      <div className="mp-stack">{children}</div>
    </section>
  );
}

function Note({ note }: { note: ReviewReportProps['trendNote'] }) {
  if (!note) return null;
  return (
    <p className={note.tone === 'alert' ? 'mp-slide-state mp-slide-error' : 'mp-muted'} role={note.tone === 'alert' ? 'alert' : 'status'}>
      {note.text}
      {note.retry && <button type="button" className="mp-btn mp-btn-ghost" onClick={note.retry}>Retry</button>}
    </p>
  );
}

function person(mask: ReviewReportProps['mask'], name: string) {
  return mask(name);
}

function Results({ review, summary, mask, trendNote, onOpenFunction, onOpenTeam }: ReviewReportProps) {
  const view = summary.scope.view;
  const openTeam = (team: string, fn?: string | null, asPosition?: boolean) => onOpenTeam?.(team, fn, asPosition);
  return (
    <Section id="s01" kicker="01 · Results" title="Results">
      <div className="mp-quality" data-testid="data-quality">
        <span>{review.people} people evaluated</span>
      </div>
      <Note note={trendNote} />
      <ExecutiveHero summary={summary} />
      {view === 'corporate' && (
        <FunctionCards
          cards={summary.functions}
          previous={summary.period.previous}
          linkable={false}
          onSelectFunction={onOpenFunction}
          onSelectTeam={(team, fn) => openTeam(team, fn)}
        />
      )}
      {view === 'corporate' && <TeamsAtRiskCard teams={summary.teams} onSelectTeam={openTeam} />}
      {view === 'function' && <FunctionTeamGrid review={review} onOpenTeam={openTeam} />}
      {view === 'function' && (
        <TeamLeaderboardCard
          teams={summary.teams}
          fn={summary.scope.function ?? 'Function'}
          effective={summary.period.effective}
          previous={summary.period.previous}
          onSelectTeam={(name) => {
            const card = summary.teams.find((item) => item.team === name);
            openTeam(name, summary.scope.function, Boolean(card?.position));
          }}
        />
      )}
      <GradeDistributionCard distribution={summary.grade_distribution} previous={summary.period.previous} />
      {view !== 'corporate' && (
        <TeamKpiTable rows={summary.kpis} effective={summary.period.effective} previous={summary.period.previous} score={summary.hero.score} showTeams={view === 'function'} />
      )}
      <GradeMovement review={review} mask={mask} />
      {review.branches.length > 0 && <Branches rows={review.branches} />}
    </Section>
  );
}

function FunctionTeamGrid({ review, onOpenTeam }: { review: MonthlyReview; onOpenTeam: (team: string, fn?: string | null, asPosition?: boolean) => void }) {
  const fn = review.summary.scope.function ?? 'this function';
  const roles = fn === 'Marketing';
  const teams = review.summary.teams;
  return (
    <div className="mp-card" data-testid="team-grid">
      <div className="mp-label">{roles ? 'Roles in Marketing' : `Teams in ${fn}`}</div>
      {teams.length === 0 ? <p>No teams with data in this function.</p> : (
        <div className="mp-team-grid">
          {teams.map((team) => {
            const people = review.rows.filter((row) => (roles && team.position ? row.position === team.position : summaryTeamMatches(row.team, team.team)));
            const withDecision = people.filter((row) => row.status !== 'no_decision').length;
            const overdue = people.filter((row) => row.status === 'overdue').length;
            const coverage = !review.actionsReady || people.length === 0 ? null : Math.round((1000 * withDecision) / people.length) / 10;
            const overdueLabel = review.actionsReady ? `${overdue} ${overdue === 1 ? 'person' : 'people'} overdue` : 'Decisions loading';
            return (
              <button key={team.position ?? team.team} type="button" className="mp-team-card" onClick={() => onOpenTeam(team.team, review.summary.scope.function, Boolean(roles && team.position))}>
                <span className="mp-team-card-name">{team.team}</span>
                <span className="mp-team-card-score">{fmtScore(team.score)} <GradeBadge grade={team.grade} /></span>
                <span className="mp-muted mp-small">Change {fmtSigned(team.change)} · {team.employees} people</span>
                <span className="mp-muted mp-small">{people.length} below target · Coverage {coverage == null ? '—' : `${coverage.toFixed(1)}%`} · {overdueLabel}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function GradeBadge({ grade }: { grade: GradeClass | null }) {
  if (!grade) return <>—</>;
  const tone = GRADE_PALETTE[grade];
  return <span className="mp-badge" style={{ color: tone.text, background: tone.background, borderColor: tone.border }}>{grade}</span>;
}

function Clip({ value }: { value: string }) {
  if (!value || value === '—') return <>—</>;
  return <span className="mp-clip" title={value}>{value}</span>;
}

function StatusBadge({ status }: { status: DecisionStatus }) {
  return <span className={`mp-badge mp-act-${status === 'no_decision' ? 'pending' : status === 'in_progress' ? 'in-progress' : status}`}>{STATUS_LABEL[status]}</span>;
}

function PriorityBadge({ value }: { value: string | null }) {
  if (!value) return <>—</>;
  const key = value.toLowerCase();
  const tone = key === 'high' || key === 'critical' ? 'mp-ca-high' : key === 'low' ? 'mp-act-cancelled' : 'mp-act-open';
  return <span className={`mp-badge ${tone}`}>{value}</span>;
}

function OutcomeBadge({ outcome }: { outcome: string }) {
  const label = outcome === 'not_scored' ? 'Not scored' : outcome;
  const tone = outcome === 'Improved' ? 'mp-act-completed' : outcome === 'Declined' ? 'mp-act-overdue' : 'mp-act-cancelled';
  return <span className={`mp-badge ${tone}`}>{label}</span>;
}

function GradeMovement({ review, mask }: { review: MonthlyReview; mask: ReviewReportProps['mask'] }) {
  const total = GRADE_CLASSES.reduce((sum, from) => sum + GRADE_CLASSES.reduce((inner, to) => inner + review.matrix[from][to], 0), 0);
  return (
    <div className="mp-stack">
      <div className="mp-card">
        <div className="mp-label">Grade movement</div>
        {total === 0 ? <p className="mp-muted">Nobody was scored in both this month and last month.</p> : (
          <table className="mp-table mp-matrix" aria-label="Grade movement">
            <thead>
              <tr><th>From \ to</th>{GRADE_CLASSES.map((grade) => <th key={grade}>{grade}</th>)}</tr>
            </thead>
            <tbody>
              {GRADE_CLASSES.map((from) => (
                <tr key={from}>
                  <th scope="row">{from}</th>
                  {GRADE_CLASSES.map((to) => <td key={to} className={from === to ? 'mp-matrix-stay' : review.matrix[from][to] ? 'mp-matrix-move' : ''}>{review.matrix[from][to]}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="mp-grid2">
        <PeopleTable title="Moved up" rows={review.up} rowKey={(row) => row.employeeId} empty="No grade changes." columns={['Employee', 'Team', 'From', 'To']} render={(row) => [
          person(mask, row.name), row.team, <GradeBadge key="from" grade={row.from} />, <GradeBadge key="to" grade={row.to} />,
        ]} />
        <PeopleTable title="Moved down" rows={review.down} rowKey={(row) => row.employeeId} empty="No grade changes." columns={['Employee', 'Team', 'From', 'To']} render={(row) => [
          person(mask, row.name), row.team, <GradeBadge key="from" grade={row.from} />, <GradeBadge key="to" grade={row.to} />,
        ]} />
      </div>
    </div>
  );
}

function PeopleTable<T>({ title, rows, empty, columns, render, rowKey, embedded = false }: {
  title: string;
  rows: T[];
  empty: string;
  columns: string[];
  render: (row: T) => ReactNode[];
  rowKey: (row: T) => string;
  embedded?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const shown = open ? rows : rows.slice(0, PREVIEW);
  const body = rows.length === 0 ? <p className="mp-muted">{empty}</p> : (
    <>
      <table className="mp-table">
        <thead><tr>{columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
        <tbody>
          {shown.map((row) => (
            <tr key={rowKey(row)}>{render(row).map((cell, cellIndex) => <td key={columns[cellIndex] ?? cellIndex}>{cell}</td>)}</tr>
          ))}
        </tbody>
      </table>
      {rows.length > PREVIEW && (
        <button type="button" className="mp-linkbtn" onClick={() => setOpen((value) => !value)}>{open ? 'Show less' : `Show all (${rows.length})`}</button>
      )}
    </>
  );
  if (embedded) return body;
  return <div className="mp-card">{title ? <div className="mp-label">{title}</div> : null}{body}</div>;
}

function Branches({ rows }: { rows: BranchRow[] }) {
  return (
    <div className="mp-card">
      <div className="mp-label">Branch comparison</div>
      <table className="mp-table">
        <thead><tr><th>Branch</th><th>Score</th><th>Vs last month</th><th>People</th></tr></thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.value}><td>{row.label}</td><td>{fmtScore(row.score)}</td><td>{fmtSigned(row.change)}</td><td>{row.employees}</td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Problems({ review, summary, mask, masked, actionsNote }: ReviewReportProps) {
  const [openId, setOpenId] = useState<string | null>(null);
  const open = review.rows.find((row) => row.employeeId === openId) ?? null;
  return (
    <Section id="s02" kicker="02 · Problems" title="Problems">
      <DriversCard summary={summary} viewAllHref={null} title="What moved the score" />
      <div className="mp-card" data-testid="below-target">
        <div className="mp-label">Below target · {review.rows.length}</div>
        <p className="mp-muted mp-small">Grade C, D and E. The same people as the decisions register.</p>
        {!review.actionsReady && <Note note={actionsNote} />}
        {review.rows.length === 0 ? <p>Nobody is below target in this selection.</p> : (
          <div className="mp-table-wrap">
            <table className="mp-table">
              <thead><tr><th>Employee</th><th>Team</th><th>Score</th><th>Grade</th><th>Worst KPI</th><th>Decision</th></tr></thead>
              <tbody>
                {review.rows.map((row) => (
                  <tr key={row.employeeId}>
                    <td><button type="button" className="mp-linkbtn" onClick={() => setOpenId(row.employeeId)}>{person(mask, row.name)}</button></td>
                    <td>{row.team}</td>
                    <td>{fmtScore(row.score)}</td>
                    <td><GradeBadge grade={row.grade} /></td>
                    <td>{row.worst ? row.worst.label : '—'}</td>
                    <td>{review.actionsReady ? <StatusBadge status={row.status} /> : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      {open && <Detail row={open} mask={mask} masked={masked} onClose={() => setOpenId(null)} />}
      <div className="mp-card">
        <div className="mp-label">Repeat underperformers</div>
        <p className="mp-muted mp-small">Grade C or lower in this month and the month before. Three months is the longer run.</p>
        {review.repeats.length === 0 ? <p>Nobody has been below target for two months in a row.</p> : (
          <PeopleTable embedded title="" rows={review.repeats} rowKey={(row) => row.employeeId} empty="" columns={['Employee', 'Team', 'Months', 'Scores']} render={(row) => [
            person(mask, row.name), row.team, String(row.streak), row.scores.map((score) => `${score.label} ${fmtScore(score.score)}`).join(', '),
          ]} />
        )}
      </div>
    </Section>
  );
}

function Recognition({ review, mask, masked }: ReviewReportProps) {
  return (
    <Section id="s03" kicker="03 · Recognition" title="Recognition">
      <div className="mp-card">
        <div className="mp-label">Top performers · grade A and B</div>
        {review.top.length === 0 ? <p>No grade A or B performers in this selection.</p> : (
          <PeopleTable embedded title="" rows={review.top} rowKey={(row) => row.employeeId} empty="" columns={['Employee', 'Team', 'Score', 'Grade']} render={(row) => [
            person(mask, row.name), row.team, fmtScore(row.score), <GradeBadge key="grade" grade={row.grade} />,
          ]} />
        )}
      </div>
      <div className="mp-card">
        <div className="mp-label">Reward and promotion decisions</div>
        {review.rewards.length === 0 ? <p>No reward or promotion decisions this month.</p> : (
          <PeopleTable embedded title="" rows={review.rewards} rowKey={(action) => action.id} empty="" columns={['Employee', 'Type', 'Decision']} render={(action) => [
            person(mask, action.employeeName ?? 'Team decision'),
            action.actionType ?? 'Decision',
            <Clip key="text" value={maskedDetail(action.actionText, masked)} />,
          ]} />
        )}
      </div>
    </Section>
  );
}

function Decisions(props: ReviewReportProps) {
  const { review, actionsNote } = props;
  return (
    <Section id="s04" kicker="04 · Decisions" title="Decisions">
      <Note note={actionsNote} />
      {review.actionsReady && (
        <>
          <Effectiveness review={review} mask={props.mask} />
          {review.coverage && <CoverageStrip coverage={review.coverage} />}
          <DecisionsRegister {...props} />
          <Owners review={review} mask={props.mask} />
        </>
      )}
    </Section>
  );
}

function Effectiveness({ review, mask }: { review: MonthlyReview; mask: ReviewReportProps['mask'] }) {
  return (
    <div className="mp-card">
      <div className="mp-label">Last month&apos;s decisions</div>
      <p className="mp-muted mp-small">Score last month, then this month. Unscored rows stay out of the success rate.</p>
      {review.effects.byType.length > 0 && (
        <div className="mp-strip">
          {review.effects.byType.map((row) => (
            <span key={row.type}>{row.type}: {row.scored ? `${row.improved} of ${row.scored} improved (${row.rate?.toFixed(1)}%)` : 'no scored outcome'}</span>
          ))}
        </div>
      )}
      {review.effects.rows.length === 0 ? <p>No decisions were taken last month.</p> : (
        <table className="mp-table">
          <thead><tr><th>Employee</th><th>Type</th><th>Before</th><th>After</th><th>Outcome</th></tr></thead>
          <tbody>
            {review.effects.rows.map((row) => (
              <tr key={row.id}>
                <td>{person(mask, row.name)}</td><td>{row.type}</td><td>{fmtScore(row.before)}</td><td>{fmtScore(row.after)}</td><td><OutcomeBadge outcome={row.outcome} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function CoverageStrip({ coverage }: { coverage: NonNullable<MonthlyReview['coverage']> }) {
  const cells: Array<[string, string]> = [
    ['Total decisions', String(coverage.total)],
    ['People with a decision', String(coverage.peopleWithDecision)],
    ['Open', String(coverage.open)],
    ['In progress', String(coverage.inProgress)],
    ['Completed', String(coverage.completed)],
    ['Overdue', String(coverage.overdue)],
    ['Below target with no decision', String(coverage.noDecision)],
    ['Coverage', coverage.coveragePercent == null ? '—' : `${coverage.coveragePercent.toFixed(1)}%`],
  ];
  return (
    <div className="mp-strip" aria-label="Decision coverage">
      {cells.map(([label, value]) => <span key={label}><b>{value}</b><small>{label}</small></span>)}
    </div>
  );
}

function Owners({ review, mask }: { review: MonthlyReview; mask: ReviewReportProps['mask'] }) {
  return (
    <div className="mp-card">
      <div className="mp-label">Owner accountability</div>
      {review.owners.length === 0 ? <p>No decisions this month.</p> : (
        <table className="mp-table">
          <thead><tr><th>Owner</th><th>Decisions</th><th>Closed on time</th><th>Overdue</th><th>Average days to close</th></tr></thead>
          <tbody>
            {review.owners.map((row) => (
              <tr key={row.owner}>
                <td>{row.owner === 'Unassigned' ? row.owner : person(mask, row.owner)}</td>
                <td>{row.decisions}</td><td>{row.closedOnTime}</td><td>{row.overdue}</td>
                <td>{row.averageDays == null ? '—' : row.averageDays.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function MonthClose({ review }: ReviewReportProps) {
  const columns: Array<[string, string[]]> = [
    ['Key results', review.close.results],
    ['Key problems', review.close.problems],
    ['Decisions taken', review.close.decisions],
  ];
  return (
    <Section id="s05" kicker="05 · Month close" title="Month close">
      <div className="mp-cols3" data-testid="month-close">
        {columns.map(([title, lines]) => (
          <div key={title} className="mp-card">
            <div className="mp-label">{title}</div>
            <ul className="mp-plain">{lines.map((line) => <li key={line}>{line}</li>)}</ul>
          </div>
        ))}
      </div>
    </Section>
  );
}

function DecisionsRegister({ review, mask, masked }: ReviewReportProps) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<'all' | DecisionStatus>('all');
  const [type, setType] = useState('all');
  const [sort, setSort] = useState<{ key: SortKey; dir: 'asc' | 'desc' }>({ key: 'status', dir: 'asc' });
  const [page, setPage] = useState(0);
  const [openId, setOpenId] = useState<string | null>(null);
  const types = useMemo(() => [...new Set(review.rows.map((row) => row.decisionType).filter((value): value is string => Boolean(value)))].sort((a, b) => a.localeCompare(b)), [review.rows]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const rows = review.rows.filter((row) => {
      if (status !== 'all' && row.status !== status) return false;
      if (type === 'none' && row.status !== 'no_decision') return false;
      if (type !== 'all' && type !== 'none' && (row.decisionType ?? '') !== type) return false;
      if (!needle) return true;
      return mask(row.name).toLowerCase().includes(needle) || row.employeeId.toLowerCase().includes(needle);
    });
    const directed = [...rows].sort((left, right) => {
      const cmp = compareRows(left, right, sort.key, mask);
      return sort.dir === 'asc' ? cmp : -cmp;
    });
    return directed;
  }, [mask, query, review.rows, sort.dir, sort.key, status, type]);
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const pageIndex = Math.min(page, pages - 1);
  const visible = filtered.slice(pageIndex * PAGE_SIZE, pageIndex * PAGE_SIZE + PAGE_SIZE);
  const open = review.rows.find((row) => row.employeeId === openId) ?? null;
  const onSort = (key: SortKey) => {
    setPage(0);
    setSort((current) => current.key === key ? { key, dir: current.dir === 'asc' ? 'desc' : 'asc' } : { key, dir: 'asc' });
  };
  return (
    <div className="mp-card" data-testid="decisions-register">
      <div className="mp-row mp-gap">
        <label className="mp-label">Employee decisions
          <input aria-label="Search by name or ID" value={query} onChange={(event) => { setQuery(event.target.value); setPage(0); }} placeholder="Name or ID" />
        </label>
        <label className="mp-label">Status
          <select aria-label="Filter by status" value={status} onChange={(event) => { setStatus(event.target.value as 'all' | DecisionStatus); setPage(0); }}>
            <option value="all">All statuses</option>
            {STATUS_ORDER.map((item) => <option key={item} value={item}>{STATUS_LABEL[item]}</option>)}
          </select>
        </label>
        <label className="mp-label">Decision type
          <select aria-label="Filter by decision type" value={type} onChange={(event) => { setType(event.target.value); setPage(0); }}>
            <option value="all">All types</option>
            <option value="none">No decision yet</option>
            {types.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <button type="button" className="mp-btn mp-btn-ghost" onClick={() => downloadCsv(filtered, mask, masked)}>Export CSV</button>
      </div>
      <p className="mp-muted mp-small">Grade C, D and E only. Grade A and B are excluded.</p>
      <div className="mp-table-wrap">
        <table className="mp-table mp-register">
          <thead>
            <tr>
              {COLUMNS.map((column) => (
                <th key={column.key} aria-sort={sort.key === column.key ? (sort.dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
                  <button type="button" className="mp-sort" onClick={() => onSort(column.key)}>{column.label}</button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visible.length === 0 && <tr><td colSpan={COLUMNS.length}>No employees match these filters.</td></tr>}
            {visible.map((row) => (
              <tr key={row.employeeId} className={row.status === 'no_decision' ? 'mp-row-pending' : ''} tabIndex={0}
                onClick={() => setOpenId(row.employeeId)}
                onKeyDown={(event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setOpenId(row.employeeId); } }}>
                <td>{person(mask, row.name)}<div className="mp-muted mp-small">{row.employeeId}</div></td>
                <td>{row.team}</td>
                <td>{fmtScore(row.score)} <GradeBadge grade={row.grade} /></td>
                <td>{fmtSigned(row.change)}</td>
                <td>{row.worst ? <Clip value={`${row.worst.label} · ${row.worst.actual} vs ${row.worst.target}`} /> : '—'}</td>
                <td><Clip value={maskedDetail(row.rootCause, masked)} /></td>
                <td>{row.status === 'no_decision' ? <StatusBadge status="no_decision" /> : <><span className="mp-badge mp-ca-type">{row.decisionType ?? 'Decision'}</span>{row.decisionText ? <Clip value={maskedDetail(row.decisionText, masked)} /> : null}</>}</td>
                <td>{row.owner ? person(mask, row.owner) : '—'}</td>
                <td><PriorityBadge value={row.priority} /></td>
                <td><StatusBadge status={row.status} /></td>
                <td>{row.dueDate?.slice(0, 10) ?? '—'}</td>
                <td><Clip value={maskedDetail(row.evidence, masked)} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mp-row mp-end">
        <span className="mp-muted mp-small">{filtered.length} {filtered.length === 1 ? 'employee' : 'employees'} · page {pageIndex + 1} of {pages}</span>
        <button type="button" className="mp-btn mp-btn-ghost" disabled={pageIndex === 0} onClick={() => setPage(pageIndex - 1)}>Previous</button>
        <button type="button" className="mp-btn mp-btn-ghost" disabled={pageIndex >= pages - 1} onClick={() => setPage(pageIndex + 1)}>Next</button>
      </div>
      {open && <Detail row={open} mask={mask} masked={masked} onClose={() => setOpenId(null)} />}
    </div>
  );
}

const COLUMNS: Array<{ key: SortKey; label: string }> = [
  { key: 'name', label: 'Employee' },
  { key: 'team', label: 'Team' },
  { key: 'score', label: 'Score & grade' },
  { key: 'change', label: 'Change vs last month' },
  { key: 'worst', label: 'Worst KPI' },
  { key: 'cause', label: 'Root cause' },
  { key: 'decision', label: 'Decision' },
  { key: 'owner', label: 'Owner' },
  { key: 'priority', label: 'Priority' },
  { key: 'status', label: 'Status' },
  { key: 'due', label: 'Due date' },
  { key: 'evidence', label: 'Evidence' },
];

function compareRows(left: RegisterRow, right: RegisterRow, key: SortKey, mask: ReviewReportProps['mask']): number {
  const text = (value: string | null | undefined) => (value ?? '').toLowerCase();
  switch (key) {
    case 'name': return mask(left.name).localeCompare(mask(right.name));
    case 'team': return left.team.localeCompare(right.team);
    case 'score': return left.score - right.score;
    case 'change': return (left.change ?? Number.NEGATIVE_INFINITY) - (right.change ?? Number.NEGATIVE_INFINITY);
    case 'worst': return (left.worst?.ratio ?? Number.POSITIVE_INFINITY) - (right.worst?.ratio ?? Number.POSITIVE_INFINITY);
    case 'cause': return text(left.rootCause).localeCompare(text(right.rootCause));
    case 'decision': return text(left.decisionType).localeCompare(text(right.decisionType));
    case 'owner': return text(left.owner).localeCompare(text(right.owner));
    case 'priority': return text(left.priority).localeCompare(text(right.priority));
    case 'status': return STATUS_ORDER.indexOf(left.status) - STATUS_ORDER.indexOf(right.status);
    case 'due': return text(left.dueDate).localeCompare(text(right.dueDate));
    case 'evidence': return text(left.evidence).localeCompare(text(right.evidence));
    default: return 0;
  }
}

function downloadCsv(rows: RegisterRow[], mask: ReviewReportProps['mask'], masked: boolean) {
  const header = ['Employee', 'ID', 'Team', 'Score', 'Grade', 'Change', 'Worst KPI', 'Root cause', 'Decision type', 'Decision', 'Owner', 'Priority', 'Status', 'Due date', 'Evidence'];
  const lines = rows.map((row) => [
    mask(row.name), row.employeeId, row.team, String(row.score), row.grade, row.change == null ? '' : String(row.change),
    row.worst ? `${row.worst.label} ${row.worst.actual} vs ${row.worst.target}` : '',
    maskedDetail(row.rootCause, masked), row.decisionType ?? '', masked ? (row.decisionText ? MASKED_DETAILS_LABEL : '') : (row.decisionText ?? ''),
    row.owner ? mask(row.owner) : '', row.priority ?? '', STATUS_LABEL[row.status], row.dueDate?.slice(0, 10) ?? '', maskedDetail(row.evidence, masked),
  ].map(csvCell).join(','));
  const blob = new Blob([[header.join(','), ...lines].join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'decisions.csv';
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value: string) {
  return `"${value.replace(/"/g, '""')}"`;
}

function Detail({ row, mask, masked, onClose }: { row: RegisterRow; mask: ReviewReportProps['mask']; masked: boolean; onClose: () => void }) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { closeRef.current?.focus(); }, []);
  return (
    <div className="mp-drawer" role="dialog" aria-modal="true" aria-label={`${person(mask, row.name)} decisions`}
      onKeyDown={(event) => { if (event.key === 'Escape') onClose(); }}>
      <div className="mp-row"><h3>{person(mask, row.name)}</h3><button ref={closeRef} type="button" className="mp-btn mp-btn-ghost" onClick={onClose}>Close</button></div>
      <p className="mp-muted">{row.team} · {row.employeeId}</p>
      <div className="mp-label">KPI breakdown</div>
      {row.kpis.length === 0 ? <p>No scored KPIs for this month.</p> : (
        <table className="mp-table">
          <thead><tr><th>KPI</th><th>Actual</th><th>Target</th><th>Achievement</th></tr></thead>
          <tbody>
            {row.kpis.map((kpi) => {
              const ratio = Math.max(0, Math.min(1, Number(kpi.achievement_ratio) || 0));
              return (
                <tr key={kpi.kpi_key}>
                  <td>{kpi.label || kpi.kpi_key}</td>
                  <td>{kpi.actual_value}</td>
                  <td>{kpi.target_value}</td>
                  <td>
                    <div className="mp-meter" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(ratio * 100)} aria-label={`${kpi.label || kpi.kpi_key} achievement`}>
                      <span style={{ width: `${ratio * 100}%` }} />
                    </div>
                    <span className="mp-small">{(ratio * 100).toFixed(0)}%</span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      <div className="mp-label">Last 3 months</div>
      <div className="mp-mini-trend" aria-label="Score history">
        {row.history.map((item) => (
          <div key={item.key} className="mp-mini-col">
            <div className="mp-mini-track"><span style={{ height: `${Math.max(item.score == null ? 0 : item.score, item.score == null ? 0 : 8)}%` }} /></div>
            <span>{item.label}</span>
            <strong>{item.score == null ? '—' : fmtScore(item.score)}</strong>
            <GradeBadge grade={item.grade} />
          </div>
        ))}
      </div>
      <div className="mp-label">Decisions this month</div>
      <ActionList actions={row.actions} mask={mask} masked={masked} empty="No decision yet." />
      <div className="mp-label">Earlier decisions (previous month)</div>
      <ActionList actions={row.earlier} mask={mask} masked={masked} empty="No decision in the previous month." />
    </div>
  );
}

function ActionList({ actions, mask, masked, empty }: { actions: RegisterRow['actions']; mask: ReviewReportProps['mask']; masked: boolean; empty: string }) {
  if (!actions.length) return <p>{empty}</p>;
  return (
    <ul className="mp-plain">
      {actions.map((action) => (
        <li key={action.id}>
          {action.actionType ?? 'Decision'} · {maskedDetail(action.actionText, masked)} · {action.status ?? '—'}
          {action.ownerName ? ` · ${person(mask, action.ownerName)}` : ''} · {maskedDetail(action.evidence, masked)}
        </li>
      ))}
    </ul>
  );
}
