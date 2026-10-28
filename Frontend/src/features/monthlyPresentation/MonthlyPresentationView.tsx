import { useCallback, useEffect, useMemo, useState } from 'react';
import './macCursor.css';
import { Navigate, useLocation, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { FileBarChart } from 'lucide-react';
import { useAuth } from '../../context/auth';
import { useUserRole } from '../../context/RoleContext';
import { directorScope } from '../../lib/directorScope';
import { redirectsToFunctionSummary } from '../../lib/access';
import { composeExecutiveSummary, normalizeRegion, toExecRecords } from '../executive/compose';
import { useSummaryRecords } from '../executive/useSummaryRecords';
import { useActionStore } from '../../hooks/useActionStore';
import { apiFetch } from '../../lib/apiClient';
import {
  adaptSummaryToMonthlyOverview,
  type FunctionOverviewItem,
  type MonthlyOverviewData,
} from './monthlyOverviewData';
import {
  buildFunctionDeepDiveFromRecords,
  normalizeFunctionSlug,
  slugifyIdentifier,
  type CallCenterDeepDiveData,
} from './callCenterDeepDiveData';
import {
  buildTeamDeepDiveFromRecords,
  type IndividualActionPlanCard,
  type TeamDeepDiveData,
} from './teamDeepDiveData';
import { buildRoleDetail, isRoleBasedFunction, resolveRoleCards, type RoleActionDraft } from './roleDetailData';
import {
  FunctionsOverviewSection,
  GradeDistributionSection,
  MonthlyOverviewHeader,
  OverallCompanyPerformanceCard,
  ScoreDriversSection,
  SixMonthTrendCard,
  TeamsAtRiskSection,
} from './components/MonthlyOverviewSections';
import CallCenterDeepDiveView from './components/CallCenterDeepDiveView';
import FunctionDeepDiveView from './components/FunctionDeepDiveView';
import {
  PresentationControlBar,
  type AgendaTimelineFunction,
} from './components/PresentationControlBar';
import { PresentationSectionFrame } from './components/SectionRail';
import RoleDetailView from './components/RoleDetailView';
import TeamDeepDiveView from './components/TeamDeepDiveView';
import { isMonthAvailable, periodFromKey } from './model';
import { presentationMonthOptions, stepPresentation } from './presentationControls';

export type MonthlyRegionFilter = 'EGY' | 'UAE';

export interface MonthlyPresentationViewProps {
  /** Optional API-adapted or custom data override */
  data?: MonthlyOverviewData;
  /** Optional Call Center Deep Dive data override */
  callCenterDeepDiveData?: CallCenterDeepDiveData;
  /** Optional Team Deep Dive data override */
  teamDeepDiveData?: TeamDeepDiveData;
  /** Optional handler invoked when a Function card is clicked */
  onSelectFunction?: (fn: FunctionOverviewItem) => void;
  today?: Date;
}

function EgyptFlag({ className = 'size-4 shrink-0 rounded-xs' }: { className?: string }) {
  return (
    <svg viewBox="0 0 640 480" className={className} aria-hidden="true">
      <g fillRule="evenodd" strokeWidth="1pt">
        <path fill="#e4312b" d="M0 0h640v160H0z" />
        <path fill="#ffffff" d="M0 160h640v160H0z" />
        <path fill="#000000" d="M0 320h640v160H0z" />
        <path fill="#c09300" d="M295 195h50v90h-50z" />
      </g>
    </svg>
  );
}

function UaeFlag({ className = 'size-4 shrink-0 rounded-xs' }: { className?: string }) {
  return (
    <svg viewBox="0 0 640 480" className={className} aria-hidden="true">
      <g fillRule="evenodd">
        <path fill="#00732f" d="M0 0h640v160H0z" />
        <path fill="#ffffff" d="M0 160h640v160H0z" />
        <path fill="#000000" d="M0 320h640v160H0z" />
        <path fill="#e4312b" d="M0 0h175v480H0z" />
      </g>
    </svg>
  );
}

export default function MonthlyPresentationView(props: MonthlyPresentationViewProps) {
  const { role } = useUserRole();
  // Same rule as /executive: function roles open Function Summary, not the company review.
  if (redirectsToFunctionSummary(role)) return <Navigate to="/function-summary" replace />;
  return <MonthlyPresentationScreen {...props} />;
}

function MonthlyPresentationScreen({
  data,
  callCenterDeepDiveData,
  teamDeepDiveData,
  onSelectFunction,
  today,
}: MonthlyPresentationViewProps) {
  useEffect(() => {
    document.body.classList.add('mp-mac-cursor');
    return () => {
      document.body.classList.remove('mp-mac-cursor');
    };
  }, []);

  const { role } = useUserRole();
  const { currentUser } = useAuth();
  const assigned = directorScope(role, currentUser);
  const [searchParams, setSearchParams] = useSearchParams();
  const params = useParams<{ functionSlug?: string; teamSlug?: string }>();
  const location = useLocation();
  const navigate = useNavigate();

  // Connect to real performance summary records & corrective actions store
  const summaryRecordsQuery = useSummaryRecords(true);
  const execRecords = useMemo(
    () => toExecRecords(summaryRecordsQuery.data ?? []),
    [summaryRecordsQuery.data],
  );
  const { getAllActions, saveAction } = useActionStore();
  const storedActions = getAllActions();

  const rawRegion = searchParams.get('region');
  const normalizedUrlRegion = normalizeRegion(rawRegion);
  const periodParam = searchParams.get('period') || searchParams.get('month') || undefined;

  const activeRegion: MonthlyRegionFilter = useMemo(() => {
    if (assigned.regionLocked && assigned.region) {
      return (normalizeRegion(assigned.region) as MonthlyRegionFilter) || 'EGY';
    }
    if (normalizedUrlRegion === 'UAE' || normalizedUrlRegion === 'EGY') return normalizedUrlRegion;
    if (data?.regionCode === 'UAE' || data?.regionCode === 'EGY') return data.regionCode;
    const accessible = currentUser?.accessible_regions || [];
    if (accessible.length === 1 && normalizeRegion(accessible[0]) === 'UAE') {
      return 'UAE';
    }
    return 'EGY';
  }, [
    assigned.regionLocked,
    assigned.region,
    data?.regionCode,
    normalizedUrlRegion,
    currentUser?.accessible_regions,
  ]);

  const handleRegionChange = useCallback(
    (nextRegion: MonthlyRegionFilter) => {
      const next = new URLSearchParams(searchParams);
      next.set('region', nextRegion.toLowerCase());
      setSearchParams(next, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const clock = useMemo(() => today ?? new Date(), [today]);
  const parsedUrlPeriod = periodFromKey(periodParam);
  const requestedPeriodKey = parsedUrlPeriod && isMonthAvailable(parsedUrlPeriod.key, clock)
    ? parsedUrlPeriod.key
    : undefined;

  const overviewData: MonthlyOverviewData = useMemo(() => {
    if (data && data.regionCode === activeRegion) return data;
    const summary = composeExecutiveSummary({
      view: 'corporate',
      role,
      records: execRecords,
      filters: { region: activeRegion },
      today: clock,
      requestedPeriodKey,
    });
    return adaptSummaryToMonthlyOverview(summary, activeRegion);
  }, [activeRegion, clock, data, execRecords, requestedPeriodKey, role]);

  const rawDeepDive = (searchParams.get('deepDive') || params.functionSlug || '').trim();
  const functionSlug = rawDeepDive ? normalizeFunctionSlug(rawDeepDive) : '';
  const rawTeamParam = (searchParams.get('team') || params.teamSlug || '').trim();
  const activeTeamSlug = rawTeamParam ? slugifyIdentifier(rawTeamParam) : '';
  const rawRoleParam = (searchParams.get('role') || '').trim();
  const activeRoleSlug = rawRoleParam ? slugifyIdentifier(rawRoleParam) : '';

  const handleFunctionClick = useCallback(
    (fn: FunctionOverviewItem) => {
      onSelectFunction?.(fn);
      const next = new URLSearchParams(searchParams);
      next.set('deepDive', fn.slug);
      next.delete('team');
      next.delete('role');
      setSearchParams(next);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },
    [onSelectFunction, searchParams, setSearchParams],
  );

  const handleBackToOverview = useCallback(() => {
    const next = new URLSearchParams(searchParams);
    next.delete('deepDive');
    next.delete('team');
    next.delete('role');
    if (params.functionSlug) {
      const basePath = location.pathname.startsWith('/monthly-view')
        ? '/monthly-view'
        : '/monthly-presentation';
      const query = next.toString();
      navigate(`${basePath}${query ? `?${query}` : ''}`);
    } else {
      setSearchParams(next);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [location.pathname, navigate, params.functionSlug, searchParams, setSearchParams]);

  const handleSelectAgentTeam = useCallback(
    (teamSlug: string, functionName?: string) => {
      const next = new URLSearchParams(searchParams);
      const targetFunction = functionName
        ? normalizeFunctionSlug(functionName)
        : functionSlug || 'call-center';
      next.set('deepDive', targetFunction);
      next.set('team', slugifyIdentifier(teamSlug));
      next.delete('role');
      setSearchParams(next);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },
    [functionSlug, searchParams, setSearchParams],
  );

  const handleSelectRole = useCallback(
    (roleSlug: string) => {
      if (!functionSlug) return;
      const next = new URLSearchParams(searchParams);
      next.set('deepDive', functionSlug);
      next.set('role', roleSlug);
      next.delete('team');
      setSearchParams(next);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },
    [functionSlug, searchParams, setSearchParams],
  );

  const handleBackToFunction = useCallback(() => {
    const next = new URLSearchParams(searchParams);
    if (functionSlug) next.set('deepDive', functionSlug);
    next.delete('team');
    next.delete('role');
    setSearchParams(next);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [functionSlug, searchParams, setSearchParams]);

  const resolvedFunctionData: CallCenterDeepDiveData | null = useMemo(() => {
    if (!functionSlug) return null;
    if (functionSlug === 'call-center' && callCenterDeepDiveData) return callCenterDeepDiveData;
    return buildFunctionDeepDiveFromRecords(
      functionSlug,
      execRecords,
      storedActions,
      activeRegion,
      periodParam,
    );
  }, [activeRegion, callCenterDeepDiveData, execRecords, functionSlug, periodParam, storedActions]);

  const roleCards = useMemo(() => {
    if (!resolvedFunctionData || !isRoleBasedFunction(resolvedFunctionData.functionSlug)) return [];
    return resolveRoleCards(resolvedFunctionData, execRecords);
  }, [execRecords, resolvedFunctionData]);

  const resolvedTeamData: TeamDeepDiveData | null = useMemo(() => {
    if (!activeTeamSlug || activeRoleSlug) return null;
    if (teamDeepDiveData && teamDeepDiveData.teamSlug === activeTeamSlug) {
      return teamDeepDiveData;
    }
    return buildTeamDeepDiveFromRecords(
      activeTeamSlug,
      execRecords,
      storedActions,
      activeRegion,
      periodParam,
    );
  }, [activeRegion, activeRoleSlug, activeTeamSlug, execRecords, periodParam, storedActions, teamDeepDiveData]);

  const resolvedRoleData = useMemo(() => {
    if (!activeRoleSlug || !resolvedFunctionData) return null;
    return buildRoleDetail(resolvedFunctionData, activeRoleSlug, storedActions, execRecords);
  }, [activeRoleSlug, execRecords, resolvedFunctionData, storedActions]);

  const handleSaveRoleAction = useCallback(
    async (draft: RoleActionDraft) => {
      await saveAction({
        employee_id: draft.employeeId,
        employee_name: draft.personName,
        team: draft.team,
        month: draft.month,
        action_type: 'Coaching',
        action_text: draft.description,
        root_cause_note: `Owner: ${draft.owner}. Status: ${draft.status}. Expected impact: ${draft.expectedImpact || 'Not specified'}.`,
        due_date: draft.dueDate || null,
        linked_kpi_key: draft.linkedKpiKey,
      });
    },
    [saveAction],
  );

  const handleSaveIndividualAction = useCallback(
    async (card: IndividualActionPlanCard) => {
      if (!resolvedTeamData) return;
      const monthName = resolvedTeamData.monthLabel.split(' ')[0] || 'September';
      await saveAction({
        employee_id: card.employeeId,
        employee_name: card.agentName,
        team: resolvedTeamData.canonicalTeam,
        month: monthName,
        action_type: 'Coaching',
        action_text: card.actionText,
        root_cause_note: card.mainIssue,
        linked_kpi_key: card.linkedKpiKey,
      });
    },
    [resolvedTeamData, saveAction],
  );

  const [downloadingPptx, setDownloadingPptx] = useState(false);
  const [presentationMode, setPresentationMode] = useState(false);
  const handleDownloadPptx = useCallback(async () => {
    const exportRegion = overviewData.regionCode;
    const [yearStr] = overviewData.periodKey.split('-');
    const year = Number(yearStr) || 2026;
    const monthName = overviewData.monthLabel.split(' ')[0] || 'September';
    try {
      setDownloadingPptx(true);
      const res = await apiFetch<{
        success: boolean;
        data?: { download_url?: string; file_name?: string };
      }>('/api/reports/generate', {
        method: 'POST',
        headers: {
          'Idempotency-Key': `pptx-${exportRegion}-${overviewData.periodKey}-${Date.now()}`,
        },
        body: JSON.stringify({
          report_name: `${overviewData.regionName} Monthly Performance Review`,
          report_type: exportRegion === 'EGY' ? 'monthly_egypt' : 'monthly_uae',
          output_format: 'pptx',
          region: exportRegion,
          start_year: year,
          start_month: monthName,
          end_year: year,
          end_month: monthName,
          included_sections: ['summary'],
        }),
      });
      const downloadUrl = res.data?.download_url;
      if (downloadUrl) {
        const link = document.createElement('a');
        link.href = downloadUrl;
        link.download =
          res.data?.file_name ||
          `Monthly_Presentation_${exportRegion}_${overviewData.periodKey}.pptx`;
        document.body.appendChild(link);
        link.click();
        link.remove();
      }
    } catch (err) {
      console.error('Failed to export Monthly PPTX:', err);
      window.alert('Monthly report PPTX could not be generated.');
    } finally {
      setDownloadingPptx(false);
    }
  }, [overviewData]);

  const headerToolbar = (
    <>
      {!assigned.regionLocked && (
        <div
          role="tablist"
          aria-label="Region filter"
          className="inline-flex h-9 items-center rounded-xl border border-slate-200 bg-slate-100 p-0.5 shadow-2xs"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeRegion === 'EGY'}
            data-testid="region-egy"
            onClick={() => handleRegionChange('EGY')}
            className={`compact-control inline-flex h-8 !min-h-0 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition-all ${
              activeRegion === 'EGY'
                ? 'bg-white font-bold text-blue-600 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <EgyptFlag className="size-3.5" />
            <span>Egypt (EGY)</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeRegion === 'UAE'}
            data-testid="region-uae"
            onClick={() => handleRegionChange('UAE')}
            className={`compact-control inline-flex h-8 !min-h-0 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold transition-all ${
              activeRegion === 'UAE'
                ? 'bg-white font-bold text-blue-600 shadow-xs'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <UaeFlag className="size-3.5" />
            <span>UAE</span>
          </button>
        </div>
      )}

      <button
        type="button"
        disabled={downloadingPptx}
        onClick={handleDownloadPptx}
        className="compact-control inline-flex h-9 !min-h-0 items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-3 text-xs font-semibold text-slate-700 shadow-2xs transition-all hover:border-slate-300 hover:bg-slate-50 disabled:opacity-50"
        title="Download Monthly Executive PPTX"
      >
        <FileBarChart size={15} className="text-blue-600" />
        <span>{downloadingPptx ? 'Exporting…' : 'Export PPTX'}</span>
      </button>

    </>
  );

  const displayedPeriodKey = requestedPeriodKey ?? overviewData.periodKey;
  const monthOptions = useMemo(
    () => presentationMonthOptions(
      execRecords.map((record) => ({ region: record.region, periodKey: record.period.key })),
      activeRegion,
      clock,
      displayedPeriodKey,
    ),
    [activeRegion, clock, displayedPeriodKey, execRecords],
  );
  const selectedPeriodKey = monthOptions.some((option) => option.key === displayedPeriodKey)
    ? displayedPeriodKey
    : (monthOptions[0]?.key ?? overviewData.periodKey);
  const insideDetail = Boolean(activeTeamSlug || activeRoleSlug);
  const functionSlugs = overviewData.functions.map((fn) => fn.slug);
  const previousDisabled = !functionSlug && !insideDetail;
  const nextDisabled = !insideDetail && (
    functionSlugs.length === 0 || functionSlug === functionSlugs[functionSlugs.length - 1]
  );

  const handlePeriodChange = useCallback((key: string) => {
    const next = new URLSearchParams(searchParams);
    if (!searchParams.has('period') && searchParams.has('month')) next.set('month', key);
    else next.set('period', key);
    setSearchParams(next, { replace: true });
  }, [searchParams, setSearchParams]);

  const handleStep = useCallback((direction: 'next' | 'previous') => {
    if (direction === 'previous' && previousDisabled) return;
    if (direction === 'next' && nextDisabled) return;
    const result = stepPresentation({
      slugs: functionSlugs,
      currentSlug: functionSlug,
      direction,
      insideDetail,
    });
    const next = new URLSearchParams(searchParams);
    if (result.slug) next.set('deepDive', result.slug);
    else next.delete('deepDive');
    if (result.clearDetail || result.slug === null) {
      next.delete('team');
      next.delete('role');
    }
    if (!result.slug && params.functionSlug) {
      const basePath = location.pathname.startsWith('/monthly-view')
        ? '/monthly-view'
        : '/monthly-presentation';
      const query = next.toString();
      navigate(`${basePath}${query ? `?${query}` : ''}`);
    } else {
      setSearchParams(next);
    }
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }, [
    functionSlug,
    functionSlugs,
    insideDetail,
    location.pathname,
    navigate,
    nextDisabled,
    params.functionSlug,
    previousDisabled,
    searchParams,
    setSearchParams,
  ]);

  const renderActiveView = () => {
    if (activeRoleSlug && resolvedRoleData) {
      return (
        <RoleDetailView
          key={resolvedRoleData.roleSlug}
          data={resolvedRoleData}
          onNavigateToOverview={handleBackToOverview}
          onNavigateToFunction={handleBackToFunction}
          onSaveAction={handleSaveRoleAction}
          toolbar={headerToolbar}
          presentationMode={presentationMode}
        />
      );
    }

    if (activeTeamSlug && resolvedTeamData) {
      return (
        <TeamDeepDiveView
          data={resolvedTeamData}
          onNavigateToOverview={handleBackToOverview}
          onNavigateToCallCenter={handleBackToFunction}
          onSwitchTeam={handleSelectAgentTeam}
          onSaveIndividualAction={handleSaveIndividualAction}
          toolbar={headerToolbar}
          presentationMode={presentationMode}
        />
      );
    }

    if (functionSlug && resolvedFunctionData) {
      if (isRoleBasedFunction(resolvedFunctionData.functionSlug)) {
        return (
          <FunctionDeepDiveView
            data={resolvedFunctionData}
            roles={roleCards}
            onBackToOverview={handleBackToOverview}
            onSelectRole={handleSelectRole}
            toolbar={headerToolbar}
            presentationMode={presentationMode}
          />
        );
      }
      return (
        <CallCenterDeepDiveView
          data={resolvedFunctionData}
          onBackToOverview={handleBackToOverview}
          onSelectAgentTeam={handleSelectAgentTeam}
          onSelectRole={handleSelectRole}
          toolbar={headerToolbar}
        />
      );
    }

    // Level 1: Monthly Overview
    return (
      <div
        data-testid="monthly-overview-page"
        className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:px-8"
      >
        {/* 1. Header */}
        <MonthlyOverviewHeader
          title={overviewData.title}
          flowName={overviewData.FlowName}
          regionName={overviewData.regionName}
          monthLabel={overviewData.monthLabel}
          regionCode={overviewData.regionCode}
          pageIndicatorLabel={overviewData.pageIndicator.label}
          toolbar={headerToolbar}
        />

        {/* 2. Overall Company Performance & 3. 6-Month Score Trend */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
          <div className="lg:col-span-7">
            <OverallCompanyPerformanceCard
              overall={overviewData.overall}
              previousMonthLabel={overviewData.previousMonthLabel}
            />
          </div>
          <div className="lg:col-span-5">
            <SixMonthTrendCard trend={overviewData.trend} />
          </div>
        </div>

        {/* 4. Grade Distribution */}
        <GradeDistributionSection
          totalEmployees={overviewData.gradeDistribution.totalEmployees}
          rows={overviewData.gradeDistribution.rows}
          takeaway={overviewData.gradeDistribution.takeaway}
          previousMonthLabel={overviewData.previousMonthLabel}
        />

        {/* 5. What Moved the Score vs August */}
        <ScoreDriversSection
          previousMonthLabel={overviewData.previousMonthLabel}
          negativeDrivers={overviewData.drivers.negative}
          positiveDrivers={overviewData.drivers.positive}
        />

        {/* 6. Functions Overview */}
        <FunctionsOverviewSection
          functions={overviewData.functions}
          previousMonthLabel={overviewData.previousMonthLabel}
          onSelectFunction={handleFunctionClick}
        />

        {/* 7. Teams at Risk (Summary) */}
        <TeamsAtRiskSection
          teams={overviewData.teamsAtRisk}
          onSelectTeam={(row) => {
            const match = overviewData.functions.find((fn) => fn.functionName === row.functionName);
            handleSelectAgentTeam(slugifyIdentifier(row.team), match?.slug || row.functionName);
          }}
        />
      </div>
    );
  };

  const agendaTimeline = useMemo<AgendaTimelineFunction[]>(() => {
    const sorted = [...overviewData.functions].sort((a, b) => a.score - b.score);
    return sorted.map((fn) => {
      const fnDeepDive =
        fn.slug === 'call-center' && callCenterDeepDiveData
          ? callCenterDeepDiveData
          : buildFunctionDeepDiveFromRecords(
              fn.slug,
              execRecords,
              storedActions,
              activeRegion,
              periodParam,
            );

      if (isRoleBasedFunction(fn.slug)) {
        const cards = resolveRoleCards(fnDeepDive, execRecords).sort(
          (a, b) => a.score - b.score,
        );
        const withIssues = cards.filter((c) => c.score < 90);
        const displayCards = withIssues.length > 0 ? withIssues : cards.slice(0, 3);
        return {
          slug: fn.slug,
          functionName: fn.functionName,
          score: fn.score,
          subKindLabel: 'Roles',
          subItems: displayCards.map((c) => ({
            slug: c.roleSlug,
            name: c.roleTitle,
            score: c.score,
            kind: 'role' as const,
            hasIssue: c.score < 90,
          })),
          allUnits: cards.map((c) => ({
            slug: c.roleSlug,
            name: c.roleTitle,
            score: c.score,
            kind: 'role' as const,
            hasIssue: c.score < 90,
          })),
        };
      }

      const teams = [...(fnDeepDive.agentTeams ?? [])].sort((a, b) => a.score - b.score);
      const withIssues = teams.filter((t) => t.score < 90 || t.roleTone === 'warning');
      const displayTeams = withIssues.length > 0 ? withIssues : teams;
      return {
        slug: fn.slug,
        functionName: fn.functionName,
        score: fn.score,
        subKindLabel: 'Teams',
        subItems: displayTeams.map((t) => ({
          slug: t.teamSlug,
          name: t.teamName,
          score: t.score,
          kind: 'team' as const,
          hasIssue: t.score < 90 || t.roleTone === 'warning',
        })),
        allUnits: teams.map((t) => ({
          slug: t.teamSlug,
          name: t.teamName,
          score: t.score,
          kind: 'team' as const,
          hasIssue: t.score < 90 || t.roleTone === 'warning',
        })),
      };
    });
  }, [
    activeRegion,
    callCenterDeepDiveData,
    execRecords,
    overviewData.functions,
    periodParam,
    storedActions,
  ]);

  const sectionViewKey = [
    activeRegion,
    selectedPeriodKey,
    functionSlug,
    activeTeamSlug,
    activeRoleSlug,
    presentationMode ? 'present' : 'edit',
  ].join('|');

  return (
    <>
      <PresentationSectionFrame viewKey={sectionViewKey}>
        <div className="pb-28">{renderActiveView()}</div>
      </PresentationSectionFrame>
      <PresentationControlBar
        region={activeRegion}
        periodKey={selectedPeriodKey}
        monthOptions={monthOptions}
        onPeriodChange={handlePeriodChange}
        presentationMode={presentationMode}
        onPresentationModeChange={setPresentationMode}
        onPrevious={() => handleStep('previous')}
        onNext={() => handleStep('next')}
        previousDisabled={previousDisabled}
        nextDisabled={nextDisabled}
        functions={overviewData.functions}
        timelineItems={agendaTimeline}
        drivers={overviewData.drivers}
        overallScore={overviewData.overall.score}
        activeFunctionSlug={functionSlug}
        activeTeamSlug={activeTeamSlug}
        activeRoleSlug={activeRoleSlug}
        onSelectOverview={handleBackToOverview}
        onSelectFunctionSlug={(slug) => {
          const match = overviewData.functions.find((fn) => fn.slug === slug);
          if (match) {
            handleFunctionClick(match);
          }
        }}
        onSelectSubItem={(fnSlug, sub) => {
          if (sub.kind === 'team') {
            handleSelectAgentTeam(sub.slug, fnSlug);
          } else {
            const next = new URLSearchParams(searchParams);
            next.set('deepDive', fnSlug);
            next.set('role', sub.slug);
            next.delete('team');
            setSearchParams(next);
            window.scrollTo({ top: 0, behavior: 'smooth' });
          }
        }}
      />
    </>
  );
}
