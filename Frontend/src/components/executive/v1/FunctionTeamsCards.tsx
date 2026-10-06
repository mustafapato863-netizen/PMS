import { AlertTriangle, BarChart3, TrendingDown } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { ExecutiveTeam, ExecutivePeriod } from '../../../features/executive/types';
import { arrow, fmtKpiValue, fmtScore, fmtSigned, isLowerBetter, scoreTone } from '../../../features/executive/format';
import { teamPath } from '../../../features/executive/functions';
import { ExecCard, ExecCardHeader, Footnote, GradeSquare, ScoreText, SoftEmpty, Sparkline, StatusPill, ToneText } from './ExecPrimitives';
import { FLAG_LABEL, FLAG_ORDER } from './execModel';

/** Function Summary (Figma 48:3): teams ranked by score. */
export function TeamLeaderboardCard({ teams, fn, effective, previous }: { teams: ExecutiveTeam[]; fn: string; effective: ExecutivePeriod | null; previous: ExecutivePeriod | null }) {
  const rows = [...teams].sort((l, r) => (r.score ?? -1) - (l.score ?? -1));
  const head = 'text-[10px] font-semibold uppercase tracking-[0.6px] text-[var(--text-muted)]';
  const vs = previous ? `vs ${previous.month.slice(0, 3)}` : 'vs last';
  return (
    <ExecCard aria-labelledby="fs-leaderboard-title">
      <ExecCardHeader titleId="fs-leaderboard-title" icon={BarChart3} iconBg="var(--exec-info-bg)" iconColor="var(--exec-info-text)" title="Team leaderboard" subtitle={`${fn} teams ranked by ${effective?.month ?? 'latest'} score`} />
      {rows.length ? (
        <div role="table" aria-label="Team leaderboard" className="flex flex-col">
          <div role="row" className="flex items-center gap-[10px] rounded-[8px] bg-[var(--exec-table-head-bg)] px-[12px] py-[9px]">
            <span role="columnheader" className={`${head} w-[24px]`}>#</span>
            <span role="columnheader" className={`${head} min-w-0 flex-1`}>Team</span>
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
                <Link to={teamPath(team.team)} className="text-[13px] font-semibold leading-[1.3] text-[var(--insights-heading)] hover:underline">{team.team}</Link>
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
      <Footnote>Click a team to open its Team Dashboard (read-only for Function Viewers).</Footnote>
    </ExecCard>
  );
}

/** Function Summary: Grade D/E, falling 2 months, or furthest below the function average. */
export function TeamsNeedingAttentionCard({ teams, fn }: { teams: ExecutiveTeam[]; fn: string }) {
  const rows = teams.filter((team) => team.flags.length).sort((l, r) => (l.score ?? 0) - (r.score ?? 0)).slice(0, 3);
  return (
    <ExecCard aria-labelledby="fs-attention-title">
      <ExecCardHeader titleId="fs-attention-title" icon={AlertTriangle} iconBg="var(--pms-grade-d-badge-bg)" iconColor="var(--pms-grade-d-text)" title="Teams needing attention" subtitle="Grade D/E, falling 2 months, or furthest below function average" />
      {rows.length ? (
        <ul className="flex flex-col gap-[10px]">
          {rows.map((team) => {
            const detail = team.flag_detail;
            return (
              <li key={team.team} className="flex flex-col gap-[6px] rounded-[10px] border border-[var(--exec-card-border)] bg-[var(--exec-tile-bg)] p-[12px]" data-testid="attention-team">
                <div className="flex items-start gap-[8px]">
                  <span className="flex min-w-0 flex-1 flex-col">
                    <Link to={teamPath(team.team)} className="text-[13px] font-semibold text-[var(--insights-heading)] hover:underline">{team.team}</Link>
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
      ) : <SoftEmpty>No team in {fn} needs attention this month.</SoftEmpty>}
    </ExecCard>
  );
}
