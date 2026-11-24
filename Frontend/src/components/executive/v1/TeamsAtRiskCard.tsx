import { useState } from 'react';
import { AlertTriangle, ArrowRight, Users } from 'lucide-react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import type { ExecutiveTeam, ExecutiveTeamFlag } from '../../../features/executive/types';
import { teamPath, withTeamQuery } from '../../../types';
import { sharedTeamRoute } from '../../../features/team/countryTeamIdentity';
import { MONTHS } from '../../../features/executive/compose';
import { executiveTeamDisplayName, FLAG_LABEL, FLAG_ORDER, formatShare } from './execModel';
import { arrow, fmtKpiValue, fmtScore, fmtSigned } from '../../../features/executive/format';
import { ExecCard, ExecCardHeader, GradePill, ScoreText, SoftEmpty, StatusPill } from './ExecPrimitives';

const TEAM_BRANCHES = new Set(['dubai', 'sharjah', 'ajman', 'clinics']);
const TEAM_LEVELS = new Set(['All', 'Employee', 'Managerial', 'Corporate']);

/** 6 Figma columns: Team & Scope | Score & Grade | Gap Share | Primary Bottleneck KPI | Status | Action */
const GRID_COLUMNS = 'md:grid-cols-[minmax(0,1.45fr)_156px_118px_minmax(0,1.65fr)_132px_114px]';
const HEAD_CELL = 'text-[12px] font-semibold text-[var(--text-muted)]';

function statusBadgeLabel(team: ExecutiveTeam, primaryFlag: ExecutiveTeamFlag | undefined): string | null {
  if (team.flags.includes('grade_e') || (team.score !== null && team.score < 70)) {
    return 'Critical <70%';
  }
  if (team.flags.includes('falling_2_months')) {
    return 'Falling 2 mo';
  }
  if (primaryFlag === 'grade_d' || primaryFlag === 'grade_c' || (team.score !== null && team.score < 90)) {
    return 'Below 90%';
  }
  return primaryFlag ? FLAG_LABEL[primaryFlag] : null;
}

function bottleneckLabel(team: ExecutiveTeam): string {
  const detail = team.flag_detail;
  if (detail) {
    if (detail.kpi_label && detail.current_value !== null && detail.target_value !== null) {
      return `${detail.kpi_label} (${fmtKpiValue(detail.current_value, detail.unit)} vs ${fmtKpiValue(detail.target_value, detail.unit)})`;
    }
    if (detail.text) return detail.text;
    if (detail.kpi_label) return detail.kpi_label;
  }
  return team.score !== null && team.score >= 90 ? 'On track (≥90%)' : '—';
}

export default function TeamsAtRiskCard({ teams, rangeLabel = null, onSelectTeam }: { teams: ExecutiveTeam[]; rangeLabel?: string | null; onSelectTeam?: (team: string) => void }) {
  const [showAllTeams, setShowAllTeams] = useState(false);
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

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
        action={
          <button
            type="button"
            aria-expanded={showAllTeams}
            onClick={() => setShowAllTeams((value) => !value)}
            className="inline-flex shrink-0 items-center rounded-[10px] border border-[var(--insights-accent-border)] px-[12px] py-[6px] text-[12px] font-semibold text-[var(--insights-accent-text)] transition-all hover:brightness-95"
            style={{ background: 'var(--pms-grad-panel-info)' }}
          >
            {showAllTeams ? 'Show at-risk teams' : 'Show all teams'}
          </button>
        }
      />
      {rows.length ? (
        <>
          {!showAllTeams && (
            <p className="text-[13px] leading-[1.5] text-[var(--text-secondary)]">
              {rows.length === 1 ? '1 team is under 90.' : `${rows.length} teams are under 90.`}
              {rows[0].score !== null ? <span>{` ${rows[0].team} is the lowest-scoring team at ${fmtScore(rows[0].score)}.`}</span> : ''}
            </p>
          )}
          <div role="table" aria-label={showAllTeams ? 'All teams' : 'Teams at risk'} className="flex flex-col gap-[8px]">
            {/* Figma 6-Column Header */}
            <div role="row" className={`hidden items-center gap-[12px] px-[16px] py-[6px] md:grid ${GRID_COLUMNS}`}>
              <span role="columnheader" className={HEAD_CELL}>Team &amp; Scope</span>
              <span role="columnheader" className={HEAD_CELL}>Score &amp; Grade</span>
              <span role="columnheader" className={HEAD_CELL}>Gap Share</span>
              <span role="columnheader" className={HEAD_CELL}>Primary Bottleneck KPI</span>
              <span role="columnheader" className={HEAD_CELL}>Status</span>
              <span role="columnheader" className={`${HEAD_CELL} text-right`}>Action</span>
            </div>

            {rows.map((team, index) => {
              const lead = !showAllTeams && index === 0;
              const displayName = executiveTeamDisplayName(team.team, searchParams.get('region'));
              const href = teamHref(team);
              const primaryFlag = FLAG_ORDER.find((flag) => team.flags.includes(flag));
              const statusLabel = statusBadgeLabel(team, primaryFlag);
              const scopeMeta = [
                team.function,
                team.regions.join(' + '),
                team.employees > 0 ? `${team.employees} ${team.employees === 1 ? 'person' : 'people'}` : null,
                team.score_basis === 'leader_scorecard' ? 'Leader scorecard' : null,
              ].filter(Boolean).join(' · ');

              return (
                <div
                  role="row"
                  key={team.team}
                  data-testid="risk-row"
                  className={`flex flex-col gap-[10px] rounded-[14px] border px-[16px] py-[13px] transition-all hover:shadow-sm md:grid md:items-center md:gap-[12px] ${GRID_COLUMNS} ${
                    lead
                      ? 'border-[var(--pms-grad-panel-neg-border)]'
                      : 'border-[var(--pms-glass-stage-border)] bg-[var(--pms-glass-stage-bg)]'
                  }`}
                  style={lead ? { background: 'var(--pms-grad-panel-neg)' } : undefined}
                >
                  {/* Col 1: Team & Scope */}
                  <div role="cell" className="flex min-w-0 flex-col gap-[2px]">
                    {onSelectTeam ? (
                      <button
                        type="button"
                        title={`Review ${displayName} on this page`}
                        className="truncate text-left text-[13.5px] font-bold leading-[1.3] text-[var(--insights-heading)] hover:text-sky-600 hover:underline dark:hover:text-sky-400"
                        onClick={() => onSelectTeam(team.team)}
                      >
                        {displayName}
                      </button>
                    ) : (
                      <Link
                        to={href}
                        title={`View ${displayName} team details`}
                        className="truncate text-[13.5px] font-bold leading-[1.3] text-[var(--insights-heading)] hover:text-sky-600 hover:underline dark:hover:text-sky-400"
                      >
                        {displayName}
                      </Link>
                    )}
                    <span className="truncate text-[12px] text-[var(--text-muted)]">{scopeMeta}</span>
                  </div>

                  {/* Col 2: Score & Grade */}
                  <div role="cell" className="flex items-center gap-[8px]">
                    <ScoreText score={team.score} className="text-[15px] tabular-nums">
                      {fmtScore(team.score)}
                    </ScoreText>
                    <GradePill score={team.score} className="!px-[8px] !py-[2px]" />
                  </div>

                  {/* Col 3: Gap Share */}
                  <div role="cell" className="text-[12.5px] font-semibold tabular-nums text-[var(--text-secondary)]">
                    <span className="md:hidden text-[var(--text-muted)]">Gap Share: </span>
                    {team.gap_share_percent != null && team.gap_share_percent > 0
                      ? `${formatShare(team.gap_share_percent)}% of gap`
                      : team.gap !== null
                        ? `${arrow(team.gap)} ${fmtSigned(team.gap)}`
                        : '—'}
                  </div>

                  {/* Col 4: Primary Bottleneck KPI */}
                  <div role="cell" className="min-w-0 text-[12.5px] font-medium text-[var(--insights-heading)]">
                    <span className="md:hidden text-[var(--text-muted)]">Bottleneck: </span>
                    <span className="block truncate" title={bottleneckLabel(team)}>
                      {bottleneckLabel(team)}
                    </span>
                  </div>

                  {/* Col 5: Status */}
                  <div role="cell" className="flex flex-wrap items-center gap-[4px]">
                    {statusLabel ? (
                      <StatusPill tone="danger">{statusLabel}</StatusPill>
                    ) : showAllTeams ? (
                      <span className="text-xs font-medium text-[var(--text-muted)]">No active risk flags</span>
                    ) : (
                      <span className="text-xs text-[var(--text-muted)]">—</span>
                    )}
                  </div>

                  {/* Col 6: Action */}
                  <div role="cell" className="flex items-center md:justify-end">
                    <button
                      type="button"
                      onClick={() => (onSelectTeam ? onSelectTeam(team.team) : navigate(href))}
                      className="inline-flex items-center gap-[4px] whitespace-nowrap text-[12.5px] font-bold text-[var(--insights-accent-text)] transition-colors hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent)]"
                    >
                      Review Team
                      <ArrowRight aria-hidden="true" className="size-[13px]" strokeWidth={2.2} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      ) : (
        <SoftEmpty>{showAllTeams ? 'No teams found in the selected scope.' : 'No team is at risk this month.'}</SoftEmpty>
      )}
    </ExecCard>
  );
}
