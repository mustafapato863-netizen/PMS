import { AlertTriangle, TrendingDown, Users } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import type { ExecutiveTeam } from '../../../features/executive/types';
import { teamPath } from '../../../features/executive/functions';
import { FLAG_LABEL, FLAG_ORDER, atRiskTeams } from './execModel';
import { arrow, fmtScore, fmtSigned } from '../../../features/executive/format';
import { ExecCard, ExecCardHeader, GradeSquare, ScoreText, SoftEmpty, Sparkline, StatusPill } from './ExecPrimitives';

const TEAM_BRANCHES = new Set(['dubai', 'sharjah', 'ajman', 'clinics']);
const TEAM_LEVELS = new Set(['All', 'Employee', 'Managerial', 'Corporate']);

export default function TeamsAtRiskCard({ teams, viewAllHref, limit = 4, showAllTeams = false }: { teams: ExecutiveTeam[]; viewAllHref?: string | null; limit?: number; showAllTeams?: boolean }) {
  const [searchParams] = useSearchParams();
  const rows = showAllTeams
    ? [...teams].sort((left, right) => {
      if (left.score === null) return right.score === null ? left.team.localeCompare(right.team) : 1;
      if (right.score === null) return -1;
      return left.score - right.score || left.team.localeCompare(right.team);
    })
    : atRiskTeams(teams, limit);
  const head = 'text-[10px] font-semibold uppercase tracking-[0.6px] text-[var(--text-muted)]';
  const teamHref = (team: string) => {
    const params = new URLSearchParams();
    const branch = searchParams.get('branch')?.trim().toLowerCase();
    const level = searchParams.get('level');
    if (branch && TEAM_BRANCHES.has(branch)) params.set('branch', branch);
    if (level && TEAM_LEVELS.has(level)) params.set('performance_level', level);
    const query = params.toString();
    return `${teamPath(team)}${query ? `?${query}` : ''}`;
  };

  return (
    <ExecCard aria-labelledby="exec-risk-title">
      <ExecCardHeader
        titleId="exec-risk-title"
        icon={showAllTeams ? Users : AlertTriangle}
        iconBg={showAllTeams ? 'var(--insights-accent-soft)' : 'var(--pms-grade-d-badge-bg)'}
        iconColor={showAllTeams ? 'var(--insights-accent-text)' : 'var(--pms-grade-d-text)'}
        title={showAllTeams ? 'All teams' : 'Teams at risk'}
        subtitle={showAllTeams ? 'Every team in the selected scope, including healthy grades' : 'Grade C/D/E, or score falling 2 consecutive months'}
        action={viewAllHref ? <Link to={viewAllHref} className="inline-flex shrink-0 items-center rounded-[8px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-[10px] py-[6px] text-[12px] font-semibold text-[var(--insights-accent-text)]">View all teams</Link> : null}
      />
      {rows.length ? (
        <div role="table" aria-label={showAllTeams ? 'All teams' : 'Teams at risk'} className="flex flex-col">
          <div role="row" className="flex items-center gap-[10px] rounded-[8px] bg-[var(--exec-table-head-bg)] px-[12px] py-[9px]">
            <span role="columnheader" className={`${head} min-w-0 flex-1`}>Team</span>
            <span role="columnheader" className={`${head} w-[56px] text-right`}>Score</span>
            <span role="columnheader" className={`${head} w-[36px] text-center`}>Grade</span>
            <span role="columnheader" className={`${head} w-[64px] text-right`}>Gap</span>
            <span role="columnheader" className={`${head} hidden w-[72px] lg:block`}>6-mo trend</span>
            <span role="columnheader" className={`${head} hidden w-[150px] md:block`}>Why flagged</span>
          </div>
          {rows.map((team) => (
            <div role="row" key={team.team} className="flex items-center gap-[10px] border-b border-[var(--insights-row-border)] px-[12px] py-[10px] last:border-b-0" data-testid="risk-row">
              <div role="cell" className="flex min-w-0 flex-1 flex-col gap-[2px]">
                <Link to={teamHref(team.team)} title={`View ${team.team} team details`} className="text-[13px] font-semibold leading-[1.3] text-[var(--insights-heading)] hover:underline">{team.team}</Link>
                <span className="truncate text-[11px] text-[var(--text-muted)]">{[team.function, team.regions.join(' + ')].filter(Boolean).join(' · ')}</span>
              </div>
              <span role="cell" className="w-[56px] text-right"><ScoreText score={team.score} className="text-[13px]">{fmtScore(team.score)}</ScoreText></span>
              <span role="cell" className="flex w-[36px] justify-center"><GradeSquare score={team.score} /></span>
              <span role="cell" className="w-[64px] text-right text-[12px] font-semibold text-[var(--insights-negative)]">{arrow(team.gap)} {fmtSigned(team.gap)}</span>
              <span role="cell" className="hidden w-[72px] lg:block"><Sparkline values={team.trend.map((point) => point.score)} height={22} width={72} /></span>
              <span role="cell" className="hidden w-[150px] flex-wrap gap-[4px] md:flex">
                {FLAG_ORDER.filter((flag) => team.flags.includes(flag)).slice(0, 2).map((flag) => (
                  <StatusPill key={flag} tone="danger" icon={flag.startsWith('grade') ? AlertTriangle : TrendingDown}>{FLAG_LABEL[flag]}</StatusPill>
                ))}
                {showAllTeams && team.flags.length === 0 && <span className="text-[11px] text-[var(--text-muted)]">No active risk flags</span>}
              </span>
            </div>
          ))}
        </div>
      ) : <SoftEmpty>{showAllTeams ? 'No teams found in the selected scope.' : 'No team is at risk this month.'}</SoftEmpty>}
    </ExecCard>
  );
}
