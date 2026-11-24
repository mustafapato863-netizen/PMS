import { useState } from 'react';
import { AlertTriangle, TrendingDown, Users } from 'lucide-react';
import { Link, useSearchParams } from 'react-router-dom';
import type { ExecutiveTeam } from '../../../features/executive/types';
import { teamPath, withTeamQuery } from '../../../types';
import { sharedTeamRoute } from '../../../features/team/countryTeamIdentity';
import { MONTHS } from '../../../features/executive/compose';
import { executiveTeamDisplayName, FLAG_LABEL, FLAG_ORDER, formatShare } from './execModel';
import { arrow, fmtScore, fmtSigned } from '../../../features/executive/format';
import { ExecCard, ExecCardHeader, GradeSquare, ScoreText, SoftEmpty, Sparkline, StatusPill } from './ExecPrimitives';
import BasisComparisonNote from '../../../features/evaluation/BasisComparisonNote';

const TEAM_BRANCHES = new Set(['dubai', 'sharjah', 'ajman', 'clinics']);
const TEAM_LEVELS = new Set(['All', 'Employee', 'Managerial', 'Corporate']);

export default function TeamsAtRiskCard({ teams, rangeLabel = null, onSelectTeam }: { teams: ExecutiveTeam[]; rangeLabel?: string | null; onSelectTeam?: (team: string) => void }) {
  const [showAllTeams, setShowAllTeams] = useState(false);
  const [searchParams] = useSearchParams();
  // Worst score first; unscored teams last. Ties break on the larger gap share, then alphabetically.
  const rows = (showAllTeams ? [...teams] : teams.filter((team) => team.score !== null && team.score < 90)).sort((left, right) => {
      if (left.score === null) return right.score === null ? left.team.localeCompare(right.team) : 1;
      if (right.score === null) return -1;
      return left.score - right.score
        || (right.gap_share_percent ?? 0) - (left.gap_share_percent ?? 0)
        || left.team.localeCompare(right.team);
    });
  const teamHref = (team: ExecutiveTeam) => {
    const params = new URLSearchParams();
    const branch = searchParams.get('branch')?.trim().toLowerCase();
    const level = searchParams.get('level');
    const region = searchParams.get('region')?.trim();
    const month = searchParams.get('month')?.trim();
    const year = searchParams.get('year')?.trim();
    const period = searchParams.get('period')?.trim();
    if (branch && TEAM_BRANCHES.has(branch)) params.set('branch', branch);
    if (level && TEAM_LEVELS.has(level)) params.set('performance_level', level);
    if (region && region.toLowerCase() !== 'all') params.set('region', region);
    else if (team.regions.length === 1) params.set('region', team.regions[0]);
    if (month) params.set('month', month);
    if (year) params.set('year', year);
    if (period && /^\d{4}-(0[1-9]|1[0-2])$/.test(period)) {
      const [pYear, pMonth] = period.split('-');
      params.set('year', pYear);
      params.set('month', MONTHS[Number(pMonth) - 1]);
    }
    const sourceTeam = team.source_team || team.team;
    if (sharedTeamRoute(sourceTeam)) params.delete('region');
    return withTeamQuery(teamPath(sourceTeam), params);
  };

  return (
    <ExecCard aria-labelledby="exec-risk-title">
      <ExecCardHeader
        titleId="exec-risk-title"
        icon={showAllTeams ? Users : AlertTriangle}
        iconBg={showAllTeams ? 'var(--insights-accent-soft)' : 'var(--pms-grade-d-badge-bg)'}
        iconColor={showAllTeams ? 'var(--insights-accent-text)' : 'var(--pms-grade-d-text)'}
        title={showAllTeams ? 'All teams' : 'Teams at risk'}
        subtitle={`${showAllTeams ? 'Every team in the selected scope, ranked from worst score' : 'Score under 90%, ranked from worst score'}${rangeLabel ? ` · ${rangeLabel}` : ''}`}
        action={<button type="button" aria-expanded={showAllTeams} onClick={() => setShowAllTeams((value) => !value)} className="inline-flex shrink-0 items-center rounded-[8px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-[10px] py-[6px] text-[12px] font-semibold text-[var(--insights-accent-text)]">{showAllTeams ? 'Show at-risk teams' : 'Show all teams'}</button>}
      />
      {rows.length ? (
        <>
        {!showAllTeams && (
          <p className="text-[13px] leading-[1.5] text-[var(--text-secondary)]">
            {rows.length === 1 ? '1 team is under 90.' : `${rows.length} teams are under 90.`}
            {rows[0].score !== null ? <span>{` ${rows[0].team} is the lowest-scoring team at ${fmtScore(rows[0].score)}.`}</span> : ''}
          </p>
        )}
        <div role="table" aria-label={showAllTeams ? 'All teams' : 'Teams at risk'} className="pms-glass-stage flex flex-col overflow-hidden rounded-[14px]">
          <div className="px-[14px] pt-[8px]"><BasisComparisonNote messages={rows.map((team) => team.basis_context?.message)} /></div>
          <div role="row" className="flex items-center gap-[12px] border-b border-[var(--insights-row-border)] bg-[var(--exec-table-head-bg)] px-[14px] py-[10px]">
            <span role="columnheader" className="min-w-0 flex-1 text-[11px] font-bold uppercase tracking-wider text-[var(--text-muted)]">Team</span>
            <span role="columnheader" className="w-[62px] text-right text-[11px] font-bold uppercase tracking-wider text-[var(--text-muted)]">Score</span>
            <span role="columnheader" className="w-[40px] text-center text-[11px] font-bold uppercase tracking-wider text-[var(--text-muted)]">Grade</span>
            <span role="columnheader" className="w-[70px] text-right text-[11px] font-bold uppercase tracking-wider text-[var(--text-muted)]">vs 100</span>
            <span role="columnheader" className="hidden w-[84px] text-[11px] font-bold uppercase tracking-wider text-[var(--text-muted)] lg:block">6-mo trend</span>
            <span role="columnheader" className="hidden w-[168px] text-[11px] font-bold uppercase tracking-wider text-[var(--text-muted)] md:block">Why flagged</span>
          </div>
          {rows.map((team, index) => {
            const lead = !showAllTeams && index === 0;
            return (
            <div role="row" key={team.team} className={`flex items-center gap-[12px] border-b border-[var(--insights-row-border)] px-[14px] py-[12px] transition-colors last:border-b-0 hover:bg-white/60 dark:hover:bg-slate-800/35 ${lead ? 'border-l-[3px] border-l-rose-500' : ''}`} style={lead ? { background: 'var(--pms-grad-panel-neg)' } : undefined} data-testid="risk-row">
              <div role="cell" className="flex min-w-0 flex-1 flex-col gap-[2px]">
                {onSelectTeam ? (
                  <button type="button" title={`Review ${executiveTeamDisplayName(team.team, searchParams.get('region'))} on this page`} className="text-left text-[13.5px] font-bold leading-[1.3] text-[var(--insights-heading)] hover:text-sky-600 hover:underline dark:hover:text-sky-400" onClick={() => onSelectTeam(team.team)}>{executiveTeamDisplayName(team.team, searchParams.get('region'))}</button>
                ) : (
                  <Link to={teamHref(team)} title={`View ${executiveTeamDisplayName(team.team, searchParams.get('region'))} team details`} className="text-[13.5px] font-bold leading-[1.3] text-[var(--insights-heading)] hover:text-sky-600 hover:underline dark:hover:text-sky-400">{executiveTeamDisplayName(team.team, searchParams.get('region'))}</Link>
                )}
                <span className="truncate text-xs text-[var(--text-muted)]">{[team.function, team.regions.join(' + '), team.score_basis === 'leader_scorecard' ? 'Leader scorecard' : null].filter(Boolean).join(' · ')}</span>
                {team.gap_share_percent != null && team.gap_share_percent > 0 && (
                  <span className="text-xs font-semibold text-[var(--text-secondary)]">{formatShare(team.gap_share_percent)}% of the gap</span>
                )}
                {team.flag_detail?.text && <span className="text-xs leading-[1.4] text-[var(--text-secondary)]">{team.flag_detail.text}</span>}
              </div>
              <span role="cell" className="w-[62px] text-right"><ScoreText score={team.score} className="text-[14px]">{fmtScore(team.score)}</ScoreText></span>
              <span role="cell" className="flex w-[40px] justify-center"><GradeSquare score={team.score} /></span>
              <span role="cell" className="w-[70px] text-right text-[12px] font-bold text-[var(--insights-negative)]">{arrow(team.gap)} {fmtSigned(team.gap)}</span>
              <span role="cell" className="hidden w-[84px] lg:block"><Sparkline values={team.trend.map((point) => point.score)} height={24} width={84} /></span>
              <span role="cell" className="hidden w-[168px] flex-wrap gap-[4px] md:flex">
                {FLAG_ORDER.filter((flag) => team.flags.includes(flag)).slice(0, 2).map((flag) => (
                  <StatusPill key={flag} tone="danger" icon={flag.startsWith('grade') ? AlertTriangle : TrendingDown}>{FLAG_LABEL[flag]}</StatusPill>
                ))}
                {showAllTeams && team.flags.length === 0 && <span className="text-xs text-[var(--text-muted)]">No active risk flags</span>}
              </span>
            </div>
            );
          })}
        </div>
        </>
      ) : <SoftEmpty>{showAllTeams ? 'No teams found in the selected scope.' : 'No team is at risk this month.'}</SoftEmpty>}
    </ExecCard>
  );
}
