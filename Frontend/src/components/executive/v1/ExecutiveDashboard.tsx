/**
 * Body of the Executive Summary per view (Figma 47:2 corporate, 47:3051
 * managerial). The Function Summary (PR B) reuses the same sections.
 */
import type { ReactNode } from 'react';
import type { ExecutiveSummary } from '../../../features/executive/types';
import ExecutiveHero from './ExecutiveHero';
import FunctionCards from './FunctionCards';
import DriversCard from './DriversCard';
import RegionSplitCard from './RegionSplitCard';
import TeamsAtRiskCard from './TeamsAtRiskCard';
import GradeDistributionCard from './GradeDistributionCard';
import CorrectiveActionsCard from './CorrectiveActionsCard';
import TeamKpiTable from './TeamKpiTable';
import { PeopleToReviewCard, TopPerformersCard } from './PeopleCards';
import LevelBreakdownCard from './LevelBreakdownCard';
import { TeamLeaderboardCard, TeamsNeedingAttentionCard } from './FunctionTeamsCards';
import { FallbackNotice, ScopeBanner } from './ExecutiveStates';

export interface ExecutiveDashboardPermissions {
  /** Function cards link to /function-summary/:slug. */
  canOpenFunctions: boolean;
  /** "View all drivers" → Insights. */
  canOpenInsights: boolean;
  /** Corrective actions section is shown (follow-up endpoint roles). */
  canSeeActions: boolean;
  canCreateActions: boolean;
}

export default function ExecutiveDashboard({ summary, permissions, exportSlot = null, functionBreakdownSlot = null }: { summary: ExecutiveSummary; permissions: ExecutiveDashboardPermissions; exportSlot?: ReactNode; functionBreakdownSlot?: ReactNode }) {
  const { period, scope } = summary;
  const previous = period.previous;
  const notice = period.fallback_applied && period.notice ? <FallbackNotice notice={period.notice} /> : null;

  if (scope.view === 'managerial') {
    const fn = scope.function;
    const comparisonKnown = !summary.meta.unavailable.includes('function_average');
    const team = scope.team;
    return (
      <div className="flex flex-col gap-[16px]" data-testid="executive-managerial">
        <ScopeBanner>
          Scoped to your team. {comparisonKnown && fn
            ? `Comparisons use the ${fn} function average — other teams are never named.`
            : 'The function-average comparison appears once the backend summary endpoint is live — other teams are never named.'} Region, function and team filters are fixed by your role.
        </ScopeBanner>
        {notice}
        <ExecutiveHero summary={summary} />
        <TeamKpiTable rows={summary.kpis} effective={period.effective} previous={previous} score={summary.hero.score} reportHref={team ? `/team/${encodeURIComponent(team)}` : null} />
        <div className="grid gap-[16px] xl:grid-cols-[minmax(0,1fr)_minmax(0,360px)]">
          <PeopleToReviewCard people={summary.people} team={team} previous={previous} rosterHref={team ? `/team/${encodeURIComponent(team)}` : null} />
          <TopPerformersCard people={summary.people} previous={previous} />
        </div>
        <div className="grid gap-[16px] xl:grid-cols-2">
          <LevelBreakdownCard levels={summary.levels} />
          {permissions.canSeeActions && <CorrectiveActionsCard data={summary.corrective_actions} effective={period.effective} variant="team" canCreate={permissions.canCreateActions} />}
        </div>
      </div>
    );
  }

  if (scope.view === 'function') {
    const fn = scope.function ?? summary.hero.label;
    const vs = previous ? ` vs ${previous.month.slice(0, 3)}` : '';
    return (
      <div className="flex flex-col gap-[16px]" data-testid="executive-function">
        {notice}
        <ExecutiveHero summary={summary} />
        <div className="grid gap-[16px] xl:grid-cols-[minmax(0,1fr)_minmax(0,360px)]">
          <TeamLeaderboardCard teams={summary.teams} fn={fn} effective={period.effective} previous={previous} />
          <TeamsNeedingAttentionCard teams={summary.teams} fn={fn} />
        </div>
        <TeamKpiTable
          rows={summary.kpis}
          effective={period.effective}
          previous={previous}
          score={summary.hero.score}
          title="Function KPI rollup — worst first"
          subtitle={`Headcount-weighted across ${fn} teams${period.effective ? ` · ${period.effective.month} ${period.effective.year}` : ''}`}
          showTeams
        />
        {functionBreakdownSlot}
        <div className="grid gap-[16px] xl:grid-cols-[minmax(0,1fr)_minmax(0,400px)]">
          <DriversCard summary={summary} viewAllHref={permissions.canOpenInsights ? `/insights?function=${encodeURIComponent(fn)}${period.effective ? `&period=${period.effective.key}` : ''}` : null} title={`What moved ${fn}${vs}`} />
          <RegionSplitCard regions={summary.regions} previous={previous} />
        </div>
        <div className="grid gap-[16px] xl:grid-cols-2">
          <LevelBreakdownCard levels={summary.levels} title="Level split" subtitle={`${fn} score by performance level`} />
          {exportSlot}
        </div>
      </div>
    );
  }

  const insightsHref = permissions.canOpenInsights
    ? `/insights${period.effective ? `?period=${period.effective.key}` : ''}`
    : null;
  return (
    <div className="flex flex-col gap-[16px]" data-testid="executive-corporate">
      {notice}
      <ExecutiveHero summary={summary} />
      {summary.functions.length > 0 && (
        <FunctionCards cards={summary.functions} previous={previous} linkable={permissions.canOpenFunctions} />
      )}
      <div className="grid gap-[16px] xl:grid-cols-[minmax(0,1fr)_minmax(0,400px)]">
        <DriversCard summary={summary} viewAllHref={insightsHref} />
        <RegionSplitCard regions={summary.regions} previous={previous} />
      </div>
      <div className="grid gap-[16px] xl:grid-cols-[minmax(0,1fr)_minmax(0,400px)]">
        <TeamsAtRiskCard teams={summary.teams} viewAllHref="/team/all" />
        <GradeDistributionCard distribution={summary.grade_distribution} previous={previous} />
      </div>
      {permissions.canSeeActions && (
        <CorrectiveActionsCard data={summary.corrective_actions} effective={period.effective} variant="company" />
      )}
    </div>
  );
}
