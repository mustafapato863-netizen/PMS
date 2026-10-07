/**
 * /function-summary[/:functionSlug] — Function Summary v1 (Figma 48:3).
 *
 * Access (ROUTE_ROLES.functionSummary): Admin, GM, Function Viewer. A
 * Function Viewer only sees functions in /auth/me `accessible_functions`;
 * an unknown or disallowed slug redirects to the first allowed function. Function Viewer is
 * read-only. The backend must enforce the same scope on its data endpoints.
 */
import { useCallback, useMemo, type ReactNode } from 'react';
import { Navigate, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '../context/auth';
import { useUserRole } from '../context/RoleContext';
import InsightsHeader, { type FilterOption } from '../components/insights/overview/InsightsHeader';
import { ExecutiveViewSkeleton } from '../components/common/SkeletonLoader';
import ExecutiveDashboard from '../components/executive/v1/ExecutiveDashboard';
import AffectedAgentKpiBreakdown from '../components/executive/v1/AffectedAgentKpiBreakdown';
import FunctionSwitcher from '../components/executive/v1/FunctionSwitcher';
import { ExecutiveEmptyState, ReadOnlyBadge, ScopeBanner } from '../components/executive/v1/ExecutiveStates';
import { canAccessCorrectiveActions, canAccessInsights, canAccessSettingsContent, isFunctionViewerRole, readAccessibleFunctions } from '../lib/access';
import { canEditActionFollowUp } from '../components/actions/dueBadge';
import { MONTHS, SUMMARY_BRANCHES, SUMMARY_LEVELS } from '../features/executive/compose';
import { allowedFunctionsFor, functionFromSlug, functionSlug } from '../features/executive/functions';
import { currentPeriodKey, periodOptionsFor, subtitleFor } from '../features/executive/viewModel';
import { useExecutiveSummary, type ExecutiveFilterState } from '../features/executive/useExecutiveSummary';
import type { ExecutiveFunction } from '../features/executive/types';

const PARAM: Record<Exclude<keyof ExecutiveFilterState, 'teamFunction'>, string> = {
  periodKey: 'period', region: 'region', branch: 'branch', team: 'team', position: 'position', performanceLevel: 'level',
};

const toOptions = (values: string[]): FilterOption[] => values.map((value) => ({ value, label: value }));

function FunctionSummaryPage({ fn, allowed }: { fn: ExecutiveFunction; allowed: ExecutiveFunction[] }) {
  const { role } = useUserRole();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const readOnly = isFunctionViewerRole(role);

  const filters: ExecutiveFilterState = useMemo(() => {
    const read = (key: keyof typeof PARAM) => searchParams.get(PARAM[key]) || undefined;
    return { periodKey: read('periodKey'), region: read('region'), branch: read('branch'), team: read('team'), position: read('position'), performanceLevel: read('performanceLevel') };
  }, [searchParams]);

  const update = useCallback((patch: Partial<ExecutiveFilterState>) => {
    const next = new URLSearchParams(searchParams);
    (Object.keys(patch) as Array<keyof typeof PARAM>).forEach((key) => {
      const value = patch[key];
      if (value) next.set(PARAM[key], value);
      else next.delete(PARAM[key]);
    });
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const switchFunction = useCallback((next: ExecutiveFunction) => {
    const params = new URLSearchParams();
    if (filters.periodKey) params.set('period', filters.periodKey);
    if (filters.performanceLevel) params.set('level', filters.performanceLevel);
    const query = params.toString();
    navigate(`/function-summary/${functionSlug(next)}${query ? `?${query}` : ''}`);
  }, [filters.performanceLevel, filters.periodKey, navigate]);

  const { summary, options, isLoading, error, source } = useExecutiveSummary({
    view: 'function',
    role,
    filters,
    functionName: fn,
    accessibleFunctions: allowed,
  });

  const focusPeriod = useCallback(() => {
    document.querySelector<HTMLElement>('[aria-label="Function period"]')?.focus();
  }, []);

  const header = (
    <InsightsHeader
      title="Function Summary"
      subtitle={subtitleFor(summary, 'function')}
      titleBadge={readOnly ? <ReadOnlyBadge /> : null}
      groupLabel="Function filters"
      periodAriaLabel="Function period"
      rowFrom="2xl"
      period={filters.periodKey ?? summary?.period.effective?.key ?? ''}
      periodOptions={periodOptionsFor(summary, filters.periodKey)}
      onPeriodChange={(value) => update({ periodKey: value })}
      region={filters.region ?? ''}
      regionOptions={toOptions(options.regions)}
      onRegionChange={(value) => update({ region: value, branch: undefined, team: undefined, position: undefined })}
      branch={filters.branch ?? ''}
      branchOptions={SUMMARY_BRANCHES}
      onBranchChange={(value) => update({ branch: value, team: undefined, position: undefined })}
      functionValue={fn}
      functionOptions={toOptions(allowed)}
      onFunctionChange={(value) => switchFunction(value as ExecutiveFunction)}
      functionSlot={<FunctionSwitcher functions={allowed} value={fn} onChange={switchFunction} assigned={readOnly} />}
      team={fn === 'Marketing' ? filters.position ?? '' : filters.team ?? ''}
      teamOptions={toOptions(fn === 'Marketing' ? options.roles ?? [] : options.teams)}
      teamLabel={fn === 'Marketing' ? 'Roles' : 'Teams'}
      teamAllLabel={fn === 'Marketing' ? 'All Marketing roles' : `All ${fn} teams`}
      onTeamChange={(value) => update(fn === 'Marketing' ? { position: value, team: undefined } : { team: value })}
      level={filters.performanceLevel ?? ''}
      levelOptions={toOptions([...SUMMARY_LEVELS])}
      onLevelChange={(value) => update({ performanceLevel: value, position: undefined })}
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
      <>
        {readOnly && (
          <ScopeBanner icon="eye">
            Read-only view of {allowed.length > 1 ? `your functions (${allowed.join(', ')})` : `the ${fn} function`}. You can drill into their teams and employee profiles; uploads, edits, corrective actions and other functions are hidden.
          </ScopeBanner>
        )}
        <ExecutiveDashboard
          summary={summary}
          permissions={{ canOpenFunctions: false, canOpenInsights: canAccessInsights(role), canSeeActions: canAccessCorrectiveActions(role), canCreateActions: canEditActionFollowUp(role) }}
          functionBreakdownSlot={<AffectedAgentKpiBreakdown summary={summary} source={source} performanceLevel={filters.performanceLevel ?? 'All'} teamFunctions={options.team_functions} />}
        />
      </>
    );
  }

  return (
    <div className="app-page-shell rf-page rf-page--executive executive-v1 [--app-section-gap:16px] [--rf-page-gap:16px]">
      {header}
      {body}
    </div>
  );
}

const FunctionSummaryView = () => {
  const { role } = useUserRole();
  const { currentUser } = useAuth();
  const { functionSlug: slug } = useParams<{ functionSlug?: string }>();
  const [searchParams] = useSearchParams();
  const allowed = useMemo(() => allowedFunctionsFor(role, readAccessibleFunctions(currentUser)), [currentUser, role]);
  const requested = functionFromSlug(slug);
  if (!allowed.length) {
    return (
      <div className="app-page-shell rf-page">
        <div role="alert" className="rounded-[12px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-[16px] text-[13px] text-[var(--text-secondary)]">
          No functions are assigned to your account yet. Ask an admin to assign at least one function.
        </div>
      </div>
    );
  }
  if (!requested || !allowed.includes(requested)) {
    const query = searchParams.toString();
    return <Navigate to={`/function-summary/${functionSlug(allowed[0])}${query ? `?${query}` : ''}`} replace />;
  }
  return <FunctionSummaryPage key={requested} fn={requested} allowed={allowed} />;
};

export default FunctionSummaryView;
