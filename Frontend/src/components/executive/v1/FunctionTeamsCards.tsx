import { AlertTriangle, BarChart3, TrendingDown } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import type { ExecutiveTeam, ExecutivePeriod } from '../../../features/executive/types';
import { arrow, fmtKpiValue, fmtScore, fmtSigned, isLowerBetter, scoreTone } from '../../../features/executive/format';
import { teamPath } from '../../../features/executive/functions';
import { MONTHS } from '../../../features/executive/compose';
import { ExecCard, ExecCardHeader, Footnote, GradeSquare, ScoreText, SoftEmpty, Sparkline, StatusPill, ToneText } from './ExecPrimitives';
import { FLAG_LABEL, FLAG_ORDER } from './execModel';

function leaderboardPath(team: ExecutiveTeam, params: URLSearchParams) {
  // Summary and sheet routes use different date/level keys. Carry only context,
  // never stale summary team, sub-team, function or position selections.
  const next = new URLSearchParams();
  for (const key of ['month', 'year', 'region', 'branch', 'location']) {
    const value = params.get(key);
    if (value) next.set(key, value);
  }
  const period = params.get('period');
  if (period && /^\d{4}-(0[1-9]|1[0-2])$/.test(period)) {
    const [year, month] = period.split('-');
    next.set('year', year);
    next.set('month', MONTHS[Number(month) - 1]);
  }
  const level = params.get('level') || params.get('performance_level');
  if (level && ['Employee', 'Managerial', 'Corporate'].includes(level)) {
    next.set('performance_level', level);
  }
  const sourceTeam = team.source_team || (team.position ? 'Marketing' : team.team);
  if (team.position) {
    const employeeMarketingSheet = sourceTeam.toLowerCase() === 'marketing'
      && level !== 'Managerial' && level !== 'Corporate';
    next.set(employeeMarketingSheet ? 'position_view' : 'position', team.position);
  }
  const query = next.toString();
  return `${teamPath(sourceTeam)}${query ? `?${query}` : ''}`;
}

/** Function Summary (Figma 48:3): teams ranked by score. */
export function TeamLeaderboardCard({ teams, fn, effective, previous }: { teams: ExecutiveTeam[]; fn: string; effective: ExecutivePeriod | null; previous: ExecutivePeriod | null }) {
  const rows = [...teams].sort((l, r) => (r.score ?? -1) - (l.score ?? -1));
  const [params] = useSearchParams();
  const roleMode = fn === 'Marketing';
  const head = 'text-[10px] font-semibold uppercase tracking-[0.6px] text-[var(--text-muted)]';
  const vs = previous ? `vs ${previous.month.slice(0, 3)}` : 'vs last';
  return (
    <ExecCard aria-labelledby="fs-leaderboard-title">
      <ExecCardHeader titleId="fs-leaderboard-title" icon={BarChart3} iconBg="var(--exec-info-bg)" iconColor="var(--exec-info-text)" title="Team leaderboard" subtitle={`${fn} ${roleMode ? 'roles' : 'teams'} ranked by ${effective?.month ?? 'latest'} score — highest first`} />
      {rows.length ? (
        <div role="table" aria-label="Team leaderboard" className="flex flex-col">
          <div role="row" className="flex items-center gap-[10px] rounded-[8px] bg-[var(--exec-table-head-bg)] px-[12px] py-[9px]">
            <span role="columnheader" className={`${head} w-[24px]`}>#</span>
            <span role="columnheader" className={`${head} min-w-0 flex-1`}>{roleMode ? 'Role' : 'Team'}</span>
            <span role="columnheader" className={`${head} w-[56px] text-right`}>Score</span>
            <span role="columnheader" className={`${head} w-[36px] text-center`}>Grade</span>
            <span role="columnheader" className={`${head} w-[64px] text-right`}>Gap</span>
            <span role="columnheader" className={`${head} w-[64px] text-right`}>{vs}</span>
            <span role="columnheader" className={`${head} hidden w-[72px] lg:block`}>6-mo trend</span>
          </div>
          {rows.map((team, index) => (
            <div role="row" key={team.team} className="flex items-center gap-[10px] border-b border-[var(--insights-row-border)] px-[12px] py-[10px] last:border-b-0" data-testid="leaderboard-row">
              <span role="cell" className="flex w-[24px]"><span className="flex size-[22px] items-center justify-center rounded-full bg-[var(--exec-chip-bg)] text-[11px] font-bold text-[var(--exec-chip-text)]">{index + 1}</span></span>
              <span role="cell" className="flex min-w-0 flex-1 flex-col gap-[2px]">
                <Link to={leaderboardPath(team, params)} className="text-[13px] font-semibold leading-[1.3] text-[var(--insights-heading)] hover:underline">{team.team}</Link>
                <span className="truncate text-[11px] text-[var(--text-muted)]">{[team.regions.join(' + '), `${team.employees} people`].filter(Boolean).join(' · ')}</span>
              </span>
              <span role="cell" className="w-[56px] text-right"><ScoreText score={team.score} className="text-[13px]">{fmtScore(team.score)}</ScoreText></span>
              <span role="cell" className="flex w-[36px] justify-center"><GradeSquare score={team.score} /></span>
              <span role="cell" className="w-[64px] text-right"><ToneText tone={team.gap !== null && team.gap < 0 ? 'bad' : 'good'} className="text-[12px] font-semibold">{arrow(team.gap)} {fmtSigned(team.gap)}</ToneText></span>
              <span role="cell" className="w-[64px] text-right"><ToneText tone={scoreTone(team.change)} className="text-[12px] font-semibold">{arrow(team.change)} {fmtSigned(team.change)}</ToneText></span>
              <span role="cell" className="hidden w-[72px] lg:block"><Sparkline values={team.trend.map((point) => point.score)} height={22} width={72} /></span>
            </div>
          ))}
        </div>
      ) : <SoftEmpty>No teams with data in this function.</SoftEmpty>}
      <Footnote>{roleMode ? 'Click a role to open its own dashboard, KPIs and people.' : 'Click a team to open its Team Dashboard (read-only for Function Viewers).'}</Footnote>
    </ExecCard>
  );
}

/** Function Summary: Grade C/D/E, falling 2 months, or furthest below the function average. */
export function TeamsNeedingAttentionCard({ teams, fn }: { teams: ExecutiveTeam[]; fn: string }) {
  const [params] = useSearchParams();
  const rows = teams.filter((team) => team.flags.length).sort((l, r) => (l.score ?? 0) - (r.score ?? 0)).slice(0, 3);
  return (
    <ExecCard aria-labelledby="fs-attention-title">
      <ExecCardHeader titleId="fs-attention-title" icon={AlertTriangle} iconBg="var(--pms-grade-d-badge-bg)" iconColor="var(--pms-grade-d-text)" title={fn === 'Marketing' ? 'Roles needing attention' : 'Teams needing attention'} subtitle="Grade C/D/E, falling 2 months, or furthest below function average" />
      {rows.length ? (
        <ul className="flex flex-col gap-[10px]">
          {rows.map((team) => {
            const detail = team.flag_detail;
            return (
              <li key={team.team} className="flex flex-col gap-[6px] rounded-[10px] border border-[var(--exec-card-border)] bg-[var(--exec-tile-bg)] p-[12px]" data-testid="attention-team">
                <div className="flex items-start gap-[8px]">
                  <span className="flex min-w-0 flex-1 flex-col">
                    <Link to={leaderboardPath(team, params)} className="text-[13px] font-semibold text-[var(--insights-heading)] hover:underline">{team.team}</Link>
                    <span className="text-[11px] text-[var(--text-muted)]">{team.regions.join(' + ')}</span>
                  </span>
                  <ScoreText score={team.score} className="text-[14px]">{fmtScore(team.score)}</ScoreText>
                  <GradeSquare score={team.score} />
                </div>
                <div className="flex flex-wrap gap-[4px]">
                  {FLAG_ORDER.filter((flag) => team.flags.includes(flag)).map((flag) => (
                    <StatusPill key={flag} tone="danger" icon={flag.startsWith('grade') ? AlertTriangle : TrendingDown}>
                      {flag === 'lowest_in_function' ? `Lowest in ${fn}` : flag === 'below_function_avg' && team.vs_function_avg !== null ? `${fmtSigned(team.vs_function_avg)} vs ${fn} avg` : FLAG_LABEL[flag]}
                    </StatusPill>
                  ))}
                </div>
                {detail && (
                  <p className="text-[11px] text-[var(--text-secondary)]">
                    {detail.kpi_label} at {fmtKpiValue(detail.current_value, detail.unit)}
                    {detail.target_value !== null ? ` vs ${fmtKpiValue(detail.target_value, detail.unit)} target` : ''} ({isLowerBetter(detail.kpi_direction) ? '↓' : '↑'} better)
                  </p>
                )}
              </li>
            );
          })}
        </ul>
      ) : <SoftEmpty>No {fn === 'Marketing' ? 'role' : 'team'} in {fn} needs attention this month.</SoftEmpty>}
    </ExecCard>
  );
}
