/**
 * Body of the Executive Summary per view (Figma 47:2 corporate, 47:3051
 * managerial). The Function Summary (PR B) reuses the same sections.
 */
import { memo, type ReactNode } from 'react';
import type { ExecutiveSummary } from '../../../features/executive/types';
import { teamPath } from '../../../types';
import { coveredPeriodLabel } from '../../../features/executive/periodLabels';
import ExecutiveHero from './ExecutiveHero';
import FunctionCards from './FunctionCards';
import DriversCard from './DriversCard';
import RegionSplitCard from './RegionSplitCard';
import TeamsAtRiskCard from './TeamsAtRiskCard';
import GradeDistributionCard from './GradeDistributionCard';
import CorrectiveActionInsightsCard from './CorrectiveActionInsightsCard';
import TeamKpiTable from './TeamKpiTable';
import { PeopleToReviewCard, TopPerformersCard } from './PeopleCards';
import LevelBreakdownCard from './LevelBreakdownCard';
import { TeamLeaderboardCard, TeamsNeedingAttentionCard } from './FunctionTeamsCards';
import { FallbackNotice, ScopeBanner } from './ExecutiveStates';
import EmployeesBelowTargetCard from './EmployeesBelowTargetCard';
import BasisComparisonNote from '../../../features/evaluation/BasisComparisonNote';

export interface ExecutiveDashboardPermissions {
  /** Function cards link to /function-summary/:slug. */
  canOpenFunctions: boolean;
  /** A single function may link to Insights. The company summary of every function does not. */
  canOpenInsights: boolean;
  /** Corrective actions section is shown (follow-up endpoint roles). */
  canSeeActions: boolean;
  canCreateActions: boolean;
}

const ExecutiveDashboard = memo(function ExecutiveDashboard({
  summary,
  permissions,
  functionBreakdownSlot = null,
  hideRegionSplit = false,
}: {
  summary: ExecutiveSummary;
  permissions: ExecutiveDashboardPermissions;
  functionBreakdownSlot?: ReactNode;
  hideRegionSplit?: boolean;
}) {
  const { period, scope } = summary;
  const previous = period.previous;
  // Region split only makes sense when comparing multiple regions (never when scoped/filtered to a single country/region)
  const showRegionSplit = !hideRegionSplit && summary.regions.length > 1 && !scope.region;
  // Range mode: the cards name the range ("Jun – Sep 2026") instead of the last month. Month mode is unchanged.
  const range = period.range ?? null;
  const rangeLabel = range ? coveredPeriodLabel(period.effective, range) : null;
  const levelSubtitle = rangeLabel ? `Score, grade and headcount by performance level · ${rangeLabel}` : undefined;
  // Fallback month and evaluation-basis notes sit above the hero in every layout.
  const notices = (
    <>
      {period.fallback_applied && period.notice ? <FallbackNotice notice={period.notice} /> : null}
      <BasisComparisonNote messages={[summary.basis_context?.message]} />
    </>
  );

  if (scope.view === 'managerial') {
    const fn = scope.function;
    const comparisonKnown = !summary.meta.unavailable.includes('function_average');
    const team = scope.team;
    return (
      <div className="flex flex-col gap-[16px]" data-testid="executive-managerial">
        <ScopeBanner>
          Scoped to your {team ? 'team' : 'teams'}. {comparisonKnown && fn
            ? `Comparisons use the ${fn} function average. Other teams are not named.`
            : 'This page shows your team only. Other teams are not named.'} {team ? 'Region, function and team filters are fixed by your role.' : 'Region and function are fixed by your role; the team filter lists your assigned teams.'}
        </ScopeBanner>
        {notices}
        <ExecutiveHero summary={summary} />
        <TeamKpiTable rows={summary.kpis} effective={period.effective} previous={previous} range={range} score={summary.hero.score} reportHref={team ? teamPath(team) : null} />
        <EmployeesBelowTargetCard summary={summary} />
        <div className="grid gap-[16px] xl:grid-cols-[minmax(0,1fr)_minmax(0,360px)]">
          <PeopleToReviewCard people={summary.people} team={team} previous={previous} range={range} rosterHref={team ? teamPath(team) : null} />
          <TopPerformersCard people={summary.people} previous={previous} range={range} />
        </div>
        <LevelBreakdownCard levels={summary.levels} subtitle={levelSubtitle} />
        {permissions.canSeeActions && <CorrectiveActionInsightsCard data={summary.corrective_actions} effective={period.effective} scopeLabel={team ?? 'Your teams'} range={range} workspaceHref={team ? `/corrective-actions?team=${encodeURIComponent(team)}` : '/corrective-actions'} />}
      </div>
    );
  }

  if (scope.view === 'function') {
    const fn = scope.function ?? summary.hero.label;
    const vs = previous ? ` vs ${previous.month.slice(0, 3)}` : '';
    return (
      <div className="flex flex-col gap-[16px]" data-testid="executive-function">
        {notices}
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
        <EmployeesBelowTargetCard summary={summary} />
        {functionBreakdownSlot}
        {showRegionSplit ? (
          <div className="grid gap-[16px] xl:grid-cols-[minmax(0,1fr)_minmax(0,400px)]">
            <DriversCard summary={summary} viewAllHref={permissions.canOpenInsights ? `/insights?function=${encodeURIComponent(fn)}${period.effective ? `&period=${period.effective.key}` : ''}` : null} title={`What moved ${fn}${vs}`} />
            <RegionSplitCard regions={summary.regions} previous={previous} />
          </div>
        ) : (
          <DriversCard summary={summary} viewAllHref={permissions.canOpenInsights ? `/insights?function=${encodeURIComponent(fn)}${period.effective ? `&period=${period.effective.key}` : ''}` : null} title={`What moved ${fn}${vs}`} />
        )}
        <LevelBreakdownCard levels={summary.levels} title="Level split" subtitle={`${fn} score by performance level`} />
        {permissions.canSeeActions && <CorrectiveActionInsightsCard data={summary.corrective_actions} effective={period.effective} scopeLabel={fn} workspaceHref={`/corrective-actions?function=${encodeURIComponent(fn)}`} />}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-[16px]" data-testid="executive-corporate">
      {notices}
      <ExecutiveHero summary={summary} includeDecision={false} />
      {summary.functions.length > 0 && (
        <FunctionCards cards={summary.functions} previous={previous} range={range} linkable={permissions.canOpenFunctions} classic />
      )}
      {/* Figma Row 4: Left = What Moved the Score | Right = Region Comparison + Grade Mix */}
      <div className="grid gap-[16px] xl:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)]">
        <DriversCard summary={summary} viewAllHref={null} />
        <div className="flex min-w-0 flex-col gap-[16px]">
          {showRegionSplit && (
            <RegionSplitCard regions={summary.regions} previous={previous} range={range} />
          )}
          <GradeDistributionCard distribution={summary.grade_distribution} previous={previous} range={range} compact={showRegionSplit} />
        </div>
      </div>
      {/* Figma Row 5: Full-Width Priority Teams Needing Attention */}
      <div id="exec-risk-section" style={{ contentVisibility: 'auto', containIntrinsicSize: 'auto 380px' }}>
        <TeamsAtRiskCard key={JSON.stringify([scope, period.effective?.key, range?.start.key])} teams={summary.teams} rangeLabel={rangeLabel} />
      </div>
      {/* Figma Row 6: Full-Width Corrective Actions & Coaching Pulse */}
      {permissions.canSeeActions && (
        <div style={{ contentVisibility: 'auto', containIntrinsicSize: 'auto 240px' }}>
          <CorrectiveActionInsightsCard
            data={summary.corrective_actions}
            effective={period.effective}
            scopeLabel={scope.team ?? scope.function ?? 'Company-wide'}
            range={range}
            workspaceHref={
              scope.team
                ? `/corrective-actions?team=${encodeURIComponent(scope.team)}`
                : scope.function
                  ? `/corrective-actions?function=${encodeURIComponent(scope.function)}`
                  : '/corrective-actions'
            }
          />
        </div>
      )}
    </div>
  );
});

export default ExecutiveDashboard;
