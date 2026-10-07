/**
 * /executive — Executive Summary v1 (Figma 44:2).
 *
 * View by role (access.ts): Admin / GM / Executive / Viewer → Corporate
 * (Executive + Viewer read-only), Manager → Managerial (team-scoped, filters
 * locked), Function Viewer → /function-summary.
 */
import { useCallback, useMemo, type ReactNode } from 'react';
import { Navigate, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/auth';
import { useUserRole } from '../context/RoleContext';
import InsightsHeader, { type FilterOption } from '../components/insights/overview/InsightsHeader';
import { ExecutiveViewSkeleton } from '../components/common/SkeletonLoader';
import ExecutiveDashboard from '../components/executive/v1/ExecutiveDashboard';
import { ExecutiveEmptyState, ReadOnlyBadge } from '../components/executive/v1/ExecutiveStates';
import { canEditActionFollowUp } from '../components/actions/dueBadge';
import {
  canAccessCorrectiveActions,
  canAccessFunctionSummary,
  canAccessInsights,
  canAccessSettingsContent,
  executiveViewForRole,
  isCorporateReadOnly,
} from '../lib/access';
import { MONTHS, SUMMARY_BRANCHES, SUMMARY_LEVELS } from '../features/executive/compose';
import { currentPeriodKey, periodOptionsFor, subtitleFor } from '../features/executive/viewModel';
import { useExecutiveSummary, type ExecutiveFilterState } from '../features/executive/useExecutiveSummary';
import type { ExecutiveView as ExecutiveViewKind } from '../features/executive/types';
import { teamBelongsToFunction, teamOptionsFor } from '../features/insights/filterCascade';
import { executiveFunctionForTeam } from '../features/executive/functions';

const PARAM: Record<keyof ExecutiveFilterState, string> = {
  periodKey: 'period', region: 'region', branch: 'branch', teamFunction: 'function', team: 'team', position: 'position', performanceLevel: 'level',
};

const toOptions = (values: string[]): FilterOption[] => values.map((value) => ({ value, label: value }));

function ExecutiveSummaryPage({ view }: { view: Exclude<ExecutiveViewKind, 'function'> }) {
  const { role } = useUserRole();
  const { currentUser } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const filters: ExecutiveFilterState = useMemo(() => {
    const read = (key: keyof ExecutiveFilterState) => searchParams.get(PARAM[key]) || undefined;
    return view === 'managerial'
      ? { periodKey: read('periodKey'), branch: read('branch'), performanceLevel: read('performanceLevel') }
      : { periodKey: read('periodKey'), region: read('region'), branch: read('branch'), teamFunction: read('teamFunction'), team: read('team'), performanceLevel: read('performanceLevel') };
  }, [searchParams, view]);

  const update = useCallback((patch: Partial<ExecutiveFilterState>) => {
    const next = new URLSearchParams(searchParams);
    (Object.keys(patch) as Array<keyof ExecutiveFilterState>).forEach((key) => {
      const value = patch[key];
      if (value) next.set(PARAM[key], value);
      else next.delete(PARAM[key]);
    });
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const { summary, options, isLoading, error, managerTeam } = useExecutiveSummary({
    view,
    role,
    filters,
    managerTeams: currentUser?.accessible_teams,
  });

  const focusPeriod = useCallback(() => {
    document.querySelector<HTMLElement>('[aria-label="Executive period"]')?.focus();
  }, []);

  const clearFilters = useCallback(() => update({
    region: undefined,
    branch: undefined,
    teamFunction: undefined,
    team: undefined,
    position: undefined,
    performanceLevel: undefined,
  }), [update]);

  const scope = summary?.scope;
  const managerial = view === 'managerial';
  const teamValues = managerial
    ? [managerTeam ?? scope?.team ?? ''].filter(Boolean)
    : teamOptionsFor(options.teams, filters.teamFunction, options.team_functions);
  const header = (
    <InsightsHeader
      title="Executive Summary"
      subtitle={subtitleFor(summary, view)}
      titleBadge={managerial
        ? <span className="rounded-full bg-[var(--insights-accent-tag)] px-[8px] py-[2px] text-[11px] font-semibold text-[var(--insights-accent-text)]">Team scope</span>
        : isCorporateReadOnly(role) ? <ReadOnlyBadge /> : null}
      groupLabel="Executive filters"
      onClearFilters={clearFilters}
      periodAriaLabel="Executive period"
      rowFrom="2xl"
      period={filters.periodKey ?? summary?.period.effective?.key ?? ''}
      periodOptions={periodOptionsFor(summary, filters.periodKey)}
      onPeriodChange={(value) => update({ periodKey: value })}
      region={managerial ? scope?.region ?? '' : filters.region ?? ''}
      regionOptions={toOptions(managerial ? [scope?.region ?? ''].filter(Boolean) : options.regions)}
      onRegionChange={(value) => update({ region: value, branch: undefined, team: undefined })}
      branch={filters.branch ?? ''}
      branchOptions={SUMMARY_BRANCHES}
      onBranchChange={(value) => update({ branch: value, team: undefined })}
      functionValue={managerial ? scope?.function ?? '' : filters.teamFunction ?? ''}
      functionOptions={toOptions(managerial ? [scope?.function ?? ''].filter(Boolean) : options.functions)}
      onFunctionChange={(value) => update({ teamFunction: value, team: undefined })}
      team={managerial ? managerTeam ?? '' : filters.team ?? ''}
      teamOptions={toOptions(teamValues)}
      onTeamChange={(value) => {
        const primaryFunction = executiveFunctionForTeam(value, options.team_functions);
        const mappedFunction = primaryFunction && options.functions.includes(primaryFunction)
          ? primaryFunction
          : options.functions.find((candidate) => teamBelongsToFunction(value, candidate, options.team_functions));
        update(mappedFunction ? { teamFunction: mappedFunction, team: value } : { team: value });
      }}
      level={filters.performanceLevel ?? ''}
      levelOptions={toOptions([...SUMMARY_LEVELS])}
      onLevelChange={(value) => update({ performanceLevel: value })}
      locked={managerial ? { region: true, function: true, team: true } : undefined}
    />
  );

  let body: ReactNode;
  if (isLoading && !summary) body = <ExecutiveViewSkeleton />;
  else if (error && !summary?.data_status.has_data) {
    body = <div role="alert" className="rounded-[12px] border border-[var(--insights-negative-panel-border)] bg-[var(--insights-negative-panel-bg)] p-[16px] text-[13px] text-[var(--insights-negative)]">Performance data could not be loaded: {error}</div>;
  } else if (!summary || !summary.data_status.has_data) {
    const key = filters.periodKey ?? currentPeriodKey();
    const [year, month] = key.split('-').map(Number);
    body = (
      <ExecutiveEmptyState
        monthLabel={`${MONTHS[(month || 1) - 1]} ${year}`}
        canUpload={canAccessSettingsContent(role)}
        dataStatus={summary?.data_status ?? { has_data: false, last_upload: null }}
        onPickMonth={focusPeriod}
      />
    );
  } else {
    body = (
      <ExecutiveDashboard
        summary={summary}
        permissions={{
          canOpenFunctions: canAccessFunctionSummary(role),
          canOpenInsights: canAccessInsights(role),
          canSeeActions: canAccessCorrectiveActions(role),
          canCreateActions: canEditActionFollowUp(role),
        }}
      />
    );
  }

  return (
    <div className="app-page-shell rf-page rf-page--executive executive-v1 [--app-section-gap:16px] [--rf-page-gap:16px]">
      {header}
      {body}
    </div>
  );
}

const ExecutiveView = () => {
  const { role } = useUserRole();
  const view = executiveViewForRole(role);
  if (view === 'function') return <Navigate to="/function-summary" replace />;
  return <ExecutiveSummaryPage view={view} />;
};

export default ExecutiveView;
