import { useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowLeft,
  ArrowUpRight,
  Check,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Edit3,
  Flame,
  Gauge,
  Layers,
  Plus,
  Sparkles,
  Target,
  TrendingUp,
  UserCheck,
  Users,
} from 'lucide-react';
import {
  ProfileKpiSixMonthTrend,
  type SixMonthKpiSeriesItem,
} from '../../../components/employee/ScoreTrendChart';
import { KpiTrendMovement, SelectableKpiCard } from './SelectableKpiCard';
import { GRADE_STYLES, type GradeLetter } from '../monthlyOverviewData';
import type { FullGradeLabel } from '../callCenterDeepDiveData';
import { showActionSection, showPresentationControl, showStoredPlaceholder } from '../presentationMode';
import {
  teamActionDueLabel,
  type IndividualActionPlanCard,
  type TeamDeepDiveData,
  type TeamLevelActionPlanCard,
  type TeamSlug,
} from '../teamDeepDiveData';

const TEAM_KPI_CARDS_PER_ROW = 4;

export interface TeamDeepDiveViewProps {
  data: TeamDeepDiveData;
  onNavigateToOverview: () => void;
  onNavigateToCallCenter: () => void;
  onSwitchTeam?: (teamSlug: TeamSlug) => void;
  onSaveIndividualAction?: (card: IndividualActionPlanCard) => Promise<void> | void;
  toolbar?: ReactNode;
  presentationMode?: boolean;
}

/**
 * Full-word Grade Badge (never single letters, per Team Deep Dive requirements)
 */
export function FullWordGradeBadge({
  grade,
  gradeFullLabel,
  size = 'md',
}: {
  grade: GradeLetter;
  gradeFullLabel: FullGradeLabel;
  size?: 'sm' | 'md' | 'lg';
}) {
  const style = GRADE_STYLES[grade];
  const sizeClass =
    size === 'lg'
      ? 'px-3.5 py-1 text-sm font-bold rounded-xl'
      : size === 'sm'
      ? 'px-2.5 py-0.5 text-xs font-bold rounded-md'
      : 'px-3 py-1 text-xs font-bold rounded-lg';

  return (
    <span
      className={`inline-flex items-center justify-center border ${style.badgeBg} ${style.badgeText} ${style.badgeBorder} ${sizeClass}`}
    >
      {gradeFullLabel}
    </span>
  );
}

export default function TeamDeepDiveView({
  data,
  onNavigateToOverview,
  onNavigateToCallCenter,
  onSwitchTeam,
  onSaveIndividualAction,
  toolbar,
  presentationMode = false,
}: TeamDeepDiveViewProps) {
  const summaryGradeStyle = GRADE_STYLES[data.summary.grade];
  const isPositiveChange = data.summary.changeVsPrev >= 0;

  // Enrich & sort team KPIs from worst to best (lowest achievement / highest points lost first)
  const enrichedKpis = useMemo(() => {
    const count = data.kpis.length;
    const weights =
      count === 1
        ? [100]
        : count === 2
        ? [50, 50]
        : count === 3
        ? [40, 30, 30]
        : [30, 30, 20, 20];
    const items = data.kpis.map((kpi, idx) => {
      const weightPct = weights[idx] ?? Math.round(100 / Math.max(1, count));
      const cappedPct = Math.min(
        100,
        Math.max(0, Number.isFinite(kpi.achievementPct) ? kpi.achievementPct : 0),
      );
      const contributionPct = Math.round(((cappedPct / 100) * weightPct) * 10) / 10;
      const pointsLost = Math.max(0, Math.round((weightPct - contributionPct) * 10) / 10);
      const statusBadge: 'On Target' | 'Needs Attention' | 'Below Target' =
        cappedPct >= 99.95 || kpi.verdictBadge === 'Target Met'
          ? 'On Target'
          : cappedPct >= 80
          ? 'Needs Attention'
          : 'Below Target';
      return {
        ...kpi,
        weightPct,
        cappedPct,
        contributionPct,
        pointsLost,
        statusBadge,
      };
    });

    items.sort(
      (a, b) => a.cappedPct - b.cappedPct || b.pointsLost - a.pointsLost,
    );

    let maxLost = 0;
    let maxIdx = -1;
    items.forEach((item, idx) => {
      if (item.pointsLost > maxLost) {
        maxLost = item.pointsLost;
        maxIdx = idx;
      }
    });

    return items.map((item, idx) => ({
      ...item,
      isBiggestGap: idx === maxIdx && maxLost > 0.1,
    }));
  }, [data.kpis]);

  const biggestGapKpi = useMemo(
    () =>
      enrichedKpis.find((k) => k.isBiggestGap && k.pointsLost > 0) ??
      enrichedKpis.filter((k) => k.pointsLost > 0).sort((a, b) => b.pointsLost - a.pointsLost)[0] ??
      null,
    [enrichedKpis],
  );

  // Selected KPI in the KPI Trend Explorer
  const [selectedKpiKey, setSelectedKpiKey] = useState<string>(
    data.kpis[0]?.kpiKey ?? 'AHT',
  );
  const [carouselStart, setCarouselStart] = useState(0);

  // Editable Individual Action Plans state
  const [individualCards, setIndividualCards] = useState<IndividualActionPlanCard[]>(
    data.individualActionPlans,
  );
  const [editingIndividualId, setEditingIndividualId] = useState<string | null>(null);
  const [draftActionText, setDraftActionText] = useState<string>('');
  const [draftOwner, setDraftOwner] = useState<string>('');
  const [draftImpact, setDraftImpact] = useState<string>('');

  // Editable Team-Level Action Plans state
  const [teamCards, setTeamCards] = useState<TeamLevelActionPlanCard[]>(
    data.teamActionPlans,
  );
  const [isAddingTeamAction, setIsAddingTeamAction] = useState(false);
  const [newTeamTitle, setNewTeamTitle] = useState('');
  const [newTeamTargetKpi, setNewTeamTargetKpi] = useState('');
  const [newTeamOwner, setNewTeamOwner] = useState(`${data.canonicalTeam} Team Leader`);
  const [newTeamImpact, setNewTeamImpact] = useState('+1.0% team score lift');

  useEffect(() => {
    setSelectedKpiKey(data.kpis[0]?.kpiKey ?? 'AHT');
    setCarouselStart(0);
    setIndividualCards(data.individualActionPlans);
    setTeamCards(data.teamActionPlans);
    setEditingIndividualId(null);
  }, [data]);

  const maxCarouselStart = Math.max(0, enrichedKpis.length - TEAM_KPI_CARDS_PER_ROW);
  const safeCarouselStart = Math.min(carouselStart, maxCarouselStart);
  const visibleKpis = enrichedKpis.slice(
    safeCarouselStart,
    safeCarouselStart + TEAM_KPI_CARDS_PER_ROW,
  );

  const handleSelectTeamKpi = (kpiKey: string) => {
    setSelectedKpiKey(kpiKey);
    const idx = enrichedKpis.findIndex((k) => k.kpiKey === kpiKey);
    if (idx >= 0) {
      if (idx < safeCarouselStart) {
        setCarouselStart(idx);
      } else if (idx >= safeCarouselStart + TEAM_KPI_CARDS_PER_ROW) {
        setCarouselStart(Math.min(maxCarouselStart, idx - TEAM_KPI_CARDS_PER_ROW + 1));
      }
    }
  };

  const activeExplorerKpi =
    enrichedKpis.find((k) => k.kpiKey === selectedKpiKey) ?? enrichedKpis[0];

  const profileTrendKpis = useMemo<SixMonthKpiSeriesItem[]>(
    () =>
      enrichedKpis.map((kpi) => ({
        id: kpi.kpiKey,
        kpiKey: kpi.kpiKey,
        name: kpi.label,
        shortName: kpi.shortLabel,
        unit: kpi.unit,
        betterDirection: kpi.betterDirection,
        actualDisplay: kpi.actualFormatted,
        targetDisplay: kpi.targetFormatted,
        achievementPct: kpi.achievementPct,
        gapLabel:
          kpi.statusBadge === 'On Target'
            ? 'On target'
            : `${kpi.actualFormatted} vs ${kpi.targetFormatted}`,
        diagnosis: kpi.explorerDiagnosis,
        trend6Mo: kpi.trend6Mo,
      })),
    [enrichedKpis],
  );
  const isCallCenter = (data.functionSlug ?? 'call-center') === 'call-center' && data.functionName === 'Call Center';
  const siblings = data.siblingTeams?.length
    ? data.siblingTeams
    : isCallCenter
      ? [
          { slug: 'inbound', label: 'Inbound Agents' },
          { slug: 'outbound', label: 'Outbound Agents' },
        ]
      : [];
  const peopleLabel = isCallCenter ? 'agents' : 'people';

  const startEditIndividual = (card: IndividualActionPlanCard) => {
    setEditingIndividualId(card.id);
    setDraftActionText(card.actionText);
    setDraftOwner(card.owner);
    setDraftImpact(card.expectedImpact);
  };

  const saveEditIndividual = async (card: IndividualActionPlanCard) => {
    const updated: IndividualActionPlanCard = {
      ...card,
      actionText: draftActionText.trim() || card.actionText,
      owner: draftOwner.trim() || card.owner,
      expectedImpact: draftImpact.trim() || card.expectedImpact,
      isSavedToStore: true,
    };
    setIndividualCards((prev) =>
      prev.map((item) => (item.id === card.id ? updated : item)),
    );
    setEditingIndividualId(null);
    if (onSaveIndividualAction) {
      await onSaveIndividualAction(updated);
    }
  };

  const handleAddTeamAction = () => {
    if (!newTeamTitle.trim()) return;
    const created: TeamLevelActionPlanCard = {
      id: `team-act-custom-${Date.now()}`,
      title: newTeamTitle.trim(),
      targetKpi: newTeamTargetKpi.trim() || `${ activeExplorerKpi?.label ?? 'Team KPI' }`,
      scopeDescription: `All ${data.summary.headcount} ${data.teamDisplayName}`,
      owner: newTeamOwner.trim() || `${data.canonicalTeam} Team Leader`,
      expectedTeamImpact: newTeamImpact.trim() || '+1.0% team score lift',
      status: 'Open',
      dueDate: null,
    };
    setTeamCards((prev) => [created, ...prev]);
    setNewTeamTitle('');
    setNewTeamTargetKpi('');
    setIsAddingTeamAction(false);
  };

  return (
    <div
      data-testid="team-deep-dive-page"
      className="mx-auto max-w-7xl space-y-7 px-4 py-6 sm:px-6 lg:px-8"
    >
      {/* ================================================================== */}
      {/* 1. HEADER WITH BREADCRUMB                                          */}
      {/* ================================================================== */}
      <header
        aria-label="Team Deep Dive Header"
        className="rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
      >
        {/* Top Row: Breadcrumb + Toolbar */}
        <div className="flex min-w-0 flex-col gap-3 border-b border-slate-100 pb-4">
          <nav
            aria-label="Breadcrumb"
            data-testid="team-deep-dive-breadcrumb"
            className="flex flex-wrap items-center gap-1.5 text-xs font-semibold text-slate-500"
          >
            <button
              type="button"
              data-testid="breadcrumb-overview"
              onClick={onNavigateToOverview}
              className="rounded-lg px-2 py-1 text-slate-600 transition-colors hover:bg-slate-100 hover:text-blue-600"
            >
              Overview
            </button>
            <ChevronRight className="size-3.5 text-slate-400" />
            <button
              type="button"
              data-testid={isCallCenter ? 'breadcrumb-call-center' : 'breadcrumb-function'}
              onClick={onNavigateToCallCenter}
              className="rounded-lg px-2 py-1 text-slate-600 transition-colors hover:bg-slate-100 hover:text-blue-600"
            >
              {data.functionName}
            </button>
            <ChevronRight className="size-3.5 text-slate-400" />
            <span className="rounded-lg bg-blue-50 px-2.5 py-1 font-bold text-blue-700">
              {data.teamDisplayName}
            </span>
          </nav>

          <div className="flex w-full min-w-0 max-w-full flex-wrap items-center gap-2">
            <button
              type="button"
              data-testid="back-to-call-center-deep-dive"
              onClick={onNavigateToCallCenter}
              className="inline-flex h-9 items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3 text-xs font-bold text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700"
            >
              <ArrowLeft className="size-3.5" />
              <span>Back to {data.functionName} Deep Dive</span>
            </button>

            {onSwitchTeam && siblings.length > 1 && (
              <div
                role="tablist"
                aria-label={`Switch ${data.functionName} team`}
                className="inline-flex h-9 items-center rounded-xl border border-slate-200 bg-slate-100 p-0.5"
              >
                {siblings.map((sibling) => (
                  <button
                    key={sibling.slug}
                    type="button"
                    role="tab"
                    aria-selected={data.teamSlug === sibling.slug}
                    data-testid={`switch-team-${sibling.slug}`}
                    onClick={() => onSwitchTeam(sibling.slug)}
                    className={`h-full rounded-lg px-3 text-xs font-semibold transition-all ${
                      data.teamSlug === sibling.slug
                        ? 'bg-white font-bold text-blue-600 shadow-2xs'
                        : 'text-slate-600 hover:text-slate-900'
                    }`}
                  >
                    {sibling.label}
                  </button>
                ))}
              </div>
            )}

            {toolbar}
          </div>
        </div>

        {/* Team Hero Summary: Name, Score, Full-Word Grade, Gap, Diagnosis */}
        <div className="mt-5 flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-2.5 py-0.5 text-[11px] font-bold tracking-wider text-white uppercase">
                Team Deep Dive
              </span>
              <span className="text-xs font-semibold text-slate-500">
                {data.regionName} · {data.monthLabel}
              </span>
              <span className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-semibold text-slate-700">
                <Users className="size-3.5 text-slate-400" />
                {data.summary.headcount} measured {peopleLabel} ({data.summary.averageOrBelowCount} Average or below)
              </span>
            </div>

            <h1 className="text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
              {data.teamDisplayName}
            </h1>

            <p
              data-testid="team-header-diagnosis"
              className="max-w-3xl text-sm leading-relaxed text-slate-600"
            >
              {data.summary.diagnosis}
            </p>
          </div>

          {/* Score + Full-Word Grade + Gap + Movement */}
          <div className="flex shrink-0 flex-wrap items-center gap-4 rounded-2xl border border-slate-200/80 bg-slate-50/70 p-4 sm:p-5">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                Team Score
              </div>
              <div className="mt-1 flex items-baseline gap-3">
                <span
                  data-testid="team-deep-dive-score"
                  className={`text-4xl font-extrabold tracking-tight sm:text-5xl ${summaryGradeStyle.scoreText}`}
                >
                  {data.summary.score.toFixed(1)}%
                </span>
                <FullWordGradeBadge
                  grade={data.summary.grade}
                  gradeFullLabel={data.summary.gradeFullLabel}
                  size="lg"
                />
              </div>
            </div>

            <div className="h-12 w-px bg-slate-200 hidden sm:block" />

            <div className="flex flex-col gap-1.5 text-xs">
              <span className="inline-flex items-center gap-1 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1 font-bold text-rose-700">
                <Target className="size-3.5" />
                {data.summary.gap.toFixed(1)}% gap to 100% target
              </span>

              <span
                className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 font-bold ${
                  isPositiveChange
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                    : 'border-rose-200 bg-rose-50 text-rose-700'
                }`}
              >
                {isPositiveChange ? (
                  <ArrowUpRight className="size-3.5" />
                ) : (
                  <ArrowDownRight className="size-3.5" />
                )}
                {isPositiveChange
                  ? `+${data.summary.changeVsPrev.toFixed(1)}%`
                  : `${data.summary.changeVsPrev.toFixed(1)}%`}{' '}
                vs {data.previousMonthLabel}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* ================================================================== */}
      {/* 2. KEY TEAM KPIS — Compact Single-Row Carousel (Worst to Best)     */}
      {/* ================================================================== */}
      <section id="presentation-section-team-kpis" data-section-label="KPIs" aria-labelledby="key-team-kpis-heading" data-testid="team-kpis-section" className="scroll-mt-24 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2.5 px-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex size-7 items-center justify-center rounded-lg border border-blue-200/80 bg-blue-50 text-blue-600">
              <Gauge className="size-3.5" aria-hidden />
            </span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 id="key-team-kpis-heading" className="text-sm font-bold tracking-tight text-slate-900 sm:text-base">
                  Key Team KPIs
                </h2>
                <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-500">
                  {enrichedKpis.length} {enrichedKpis.length === 1 ? 'measure' : 'measures'} · sorted worst to best
                </span>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {biggestGapKpi && (
              <div
                data-testid="team-biggest-gap-summary-pill"
                className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200/90 bg-rose-50/80 px-2.5 py-1 text-[11px] font-semibold text-rose-900 shadow-2xs"
              >
                <Flame className="size-3.5 shrink-0 text-rose-600" aria-hidden />
                <span>
                  Biggest Gap Driver:{' '}
                  <strong className="font-extrabold text-rose-700">
                    {biggestGapKpi.shortLabel}
                  </strong>{' '}
                  (−{biggestGapKpi.pointsLost.toFixed(1)} pts ·{' '}
                  {biggestGapKpi.contributionPct.toFixed(1)}% of{' '}
                  {Math.round(biggestGapKpi.weightPct)}% weight)
                </span>
              </div>
            )}

            {enrichedKpis.length > 0 && (
              <div
                data-testid="team-kpi-carousel-controls"
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200/90 bg-white px-2 py-1 shadow-2xs"
              >
                <span className="px-1 text-[11px] font-bold text-slate-500 tabular-nums">
                  {safeCarouselStart + 1}–
                  {Math.min(enrichedKpis.length, safeCarouselStart + TEAM_KPI_CARDS_PER_ROW)} of{' '}
                  {enrichedKpis.length}
                </span>
                <button
                  type="button"
                  data-testid="team-kpi-carousel-prev"
                  aria-label="Previous team KPI cards"
                  disabled={safeCarouselStart === 0}
                  onClick={() => setCarouselStart((prev) => Math.max(0, prev - 1))}
                  className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-35"
                >
                  <ChevronLeft className="size-3.5" aria-hidden />
                </button>
                <button
                  type="button"
                  data-testid="team-kpi-carousel-next"
                  aria-label="Next team KPI cards"
                  disabled={safeCarouselStart >= maxCarouselStart}
                  onClick={() =>
                    setCarouselStart((prev) => Math.min(maxCarouselStart, prev + 1))
                  }
                  className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-35"
                >
                  <ChevronRight className="size-3.5" aria-hidden />
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {visibleKpis.map((kpi) => (
            <SelectableKpiCard
              key={kpi.kpiKey}
              selected={activeExplorerKpi?.kpiKey === kpi.kpiKey}
              status={kpi.statusBadge}
              title={kpi.label}
              betterDirection={kpi.betterDirection}
              actual={kpi.actualFormatted}
              target={kpi.targetFormatted}
              achievementPct={kpi.cappedPct}
              movement={
                <KpiTrendMovement
                  label={kpi.movementFormatted}
                  betterDirection={kpi.betterDirection}
                />
              }
              biggestGap={kpi.isBiggestGap}
              weightPct={kpi.weightPct}
              contributionPct={kpi.contributionPct}
              pointsLost={kpi.pointsLost}
              testId={`team-kpi-card-${kpi.kpiKey}`}
              onSelect={() => handleSelectTeamKpi(kpi.kpiKey)}
            />
          ))}
        </div>
      </section>

      {/* ================================================================== */}
      {/* 3. KPI TREND EXPLORER (360-Profile Interactive 6-Month Line Chart) */}
      {/* ================================================================== */}
      {activeExplorerKpi && (
        <section
          id="presentation-section-team-trend"
          data-section-label="Trend"
          aria-labelledby="role-trend-heading"
          data-testid="kpi-trend-explorer"
          className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
        >
          {/* Reused 360-Profile Interactive 6-Month Line Chart (includes single KPI switcher) */}
          <ProfileKpiSixMonthTrend
            kpis={profileTrendKpis}
            selectedId={activeExplorerKpi.kpiKey}
            onSelectKpi={handleSelectTeamKpi}
          />

          {/* Diagnostic Answer: Is the target unrealistic or is execution the issue? */}
          <div
            data-testid="trend-explorer-diagnosis"
            className="mt-5 flex flex-wrap items-start justify-between gap-3 rounded-xl border border-blue-200/80 bg-blue-50/50 p-4"
          >
            <div className="flex items-start gap-3">
              <Sparkles className="mt-0.5 size-4 shrink-0 text-blue-600" />
              <div className="text-xs leading-relaxed text-slate-800 sm:text-sm">
                <span className="font-bold text-blue-950">
                  Target vs. Execution Diagnosis:{' '}
                </span>
                {activeExplorerKpi.explorerDiagnosis}
              </div>
            </div>

            <div className="flex shrink-0 flex-wrap items-center gap-2">
              <span
                className={`rounded-full border px-2.5 py-0.5 text-[11px] font-bold ${
                  activeExplorerKpi.verdictBadge === 'Target Met'
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                    : activeExplorerKpi.verdictBadge === 'Execution Issue'
                    ? 'border-amber-200 bg-amber-50 text-amber-800'
                    : 'border-rose-200 bg-rose-50 text-rose-700'
                }`}
              >
                Verdict: {activeExplorerKpi.verdictBadge}
              </span>
              <span className="rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-[11px] font-semibold text-slate-600">
                {activeExplorerKpi.agentsMeetingTarget} of {activeExplorerKpi.totalAgents} {peopleLabel} met target
              </span>
            </div>
          </div>
        </section>
      )}

      {/* ================================================================== */}
      {/* 4. AGENTS — AVERAGE AND BELOW (Grade C or Lower, Full Words Only)  */}
      {/* ================================================================== */}
      <section
        id="presentation-section-team-agents"
        data-section-label="Agents"
        aria-labelledby="agents-average-below-heading"
        className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-4">
          <div>
            <span className="text-xs font-semibold tracking-wider text-amber-700 uppercase">
              Focus Cohort (Score &lt; 90%)
            </span>
            <h2
              id="agents-average-below-heading"
              className="mt-0.5 text-lg font-bold text-slate-900"
            >
              Agents — Average and Below
            </h2>
          </div>

          <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-bold text-amber-800">
            {data.agentsAverageOrBelow.length} of {data.summary.headcount} agents require action
          </span>
        </div>

        <div className="mt-4 overflow-x-auto">
          <table
            data-testid="agents-average-below-table"
            className="w-full border-collapse text-left text-sm"
          >
            <thead>
              <tr className="border-b border-slate-200 text-xs font-semibold tracking-wider text-slate-500 uppercase">
                <th className="py-3 pr-4">Agent</th>
                <th className="px-4 py-3 text-right">Score</th>
                {data.kpis.slice(0, 4).map((kpi) => (
                  <th key={kpi.kpiKey} className="px-4 py-3 text-right">
                    {kpi.shortLabel}
                    <span className="block text-[10px] font-normal text-slate-400 normal-case">
                      Target: {kpi.targetFormatted}
                    </span>
                  </th>
                ))}
                <th className="py-3 pl-4 text-center">Grade</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.agentsAverageOrBelow.map((agent) => {
                const gradeStyle = GRADE_STYLES[agent.grade];
                return (
                  <tr
                    key={agent.employeeId}
                    data-testid={`low-agent-row-${agent.employeeId}`}
                    className="transition-colors hover:bg-slate-50/80"
                  >
                    <td className="py-3.5 pr-4">
                      <div className="font-bold text-slate-900">{agent.agentName}</div>
                      <div className="mt-0.5 text-xs text-slate-500">{agent.mainIssue}</div>
                    </td>

                    <td className="px-4 py-3.5 text-right">
                      <div className={`text-base font-extrabold ${gradeStyle.scoreText}`}>
                        {agent.score.toFixed(1)}%
                      </div>
                      {agent.changeVsPrev !== null && (
                        <div
                          className={`text-[11px] font-semibold ${
                            agent.changeVsPrev >= 0 ? 'text-emerald-600' : 'text-rose-600'
                          }`}
                        >
                          {agent.changeVsPrev >= 0
                            ? `+${agent.changeVsPrev.toFixed(1)}%`
                            : `${agent.changeVsPrev.toFixed(1)}%`}{' '}
                          vs {data.previousMonthLabel}
                        </div>
                      )}
                    </td>

                    {agent.kpiCells.map((cell) => (
                      <td key={cell.kpiKey} className="px-4 py-3.5 text-right">
                        <span
                          className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-bold ${
                            cell.metTarget
                              ? 'bg-emerald-50 text-emerald-700'
                              : cell.achievementPct < 75
                              ? 'bg-rose-50 text-rose-700'
                              : 'bg-amber-50 text-amber-800'
                          }`}
                        >
                          {cell.actualFormatted}
                        </span>
                      </td>
                    ))}

                    <td className="py-3.5 pl-4 text-center">
                      <FullWordGradeBadge
                        grade={agent.grade}
                        gradeFullLabel={agent.gradeFullLabel}
                        size="sm"
                      />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* ================================================================== */}
      {/* 5. INDIVIDUAL ACTION PLAN (Card Layout, Editable)                  */}
      {/* ================================================================== */}
      {showActionSection(individualCards.length, presentationMode) && (
      <section
        id="presentation-section-team-coaching"
        data-section-label="Coaching"
        aria-labelledby="individual-action-plan-heading"
        className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-4">
          <div>
            <span className="text-xs font-semibold tracking-wider text-blue-600 uppercase">
              1-on-1 Coaching & Remediation
            </span>
            <h2
              id="individual-action-plan-heading"
              className="mt-0.5 text-lg font-bold text-slate-900"
            >
              Individual Action Plan
            </h2>
          </div>
          {showPresentationControl(presentationMode) && (
            <p className="text-xs font-medium text-slate-500">
              One action card per agent shown above · Click &ldquo;Edit&rdquo; on any card to customize & save
            </p>
          )}
        </div>

        <div className="mt-5 grid grid-cols-1 gap-4 md:grid-cols-2">
          {individualCards.map((card) => {
            const isEditing = showPresentationControl(presentationMode) && editingIndividualId === card.id;
            const gradeStyle = GRADE_STYLES[card.grade];

            return (
              <article
                key={card.id}
                data-testid={`individual-action-card-${card.employeeId}`}
                className="flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-slate-50/50 p-5 transition-all hover:bg-white hover:shadow-xs"
              >
                <div>
                  {/* Card Header: Agent Name + Score + Full-Word Grade + Edit Button */}
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-base font-bold text-slate-900">
                          {card.agentName}
                        </h3>
                        <span className={`text-sm font-extrabold ${gradeStyle.scoreText}`}>
                          {card.score.toFixed(1)}%
                        </span>
                        <FullWordGradeBadge
                          grade={card.grade}
                          gradeFullLabel={card.gradeFullLabel}
                          size="sm"
                        />
                      </div>
                    </div>

                    {!isEditing && showPresentationControl(presentationMode) && (
                      <button
                        type="button"
                        onClick={() => startEditIndividual(card)}
                        className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:border-blue-300 hover:text-blue-600"
                      >
                        <Edit3 className="size-3" />
                        <span>Edit</span>
                      </button>
                    )}
                  </div>

                  {/* Main Issue */}
                  <div className="mt-3 rounded-xl border border-rose-200/70 bg-rose-50/50 px-3.5 py-2.5 text-xs text-slate-700">
                    <span className="font-bold text-rose-800">
                      <AlertTriangle className="mr-1 inline size-3.5 text-rose-600" />
                      Main Issue:{' '}
                    </span>
                    {card.mainIssue}
                  </div>

                  {/* Action Text (View or Edit Mode) */}
                  {isEditing ? (
                    <div className="mt-3 space-y-2.5 rounded-xl border border-blue-200 bg-white p-3">
                      <div>
                        <label className="block text-[11px] font-bold text-slate-600">
                          Corrective Action
                        </label>
                        <textarea
                          rows={2}
                          value={draftActionText}
                          onChange={(e) => setDraftActionText(e.target.value)}
                          className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                        />
                      </div>
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                        <div>
                          <label className="block text-[11px] font-bold text-slate-600">
                            Owner
                          </label>
                          <input
                            type="text"
                            value={draftOwner}
                            onChange={(e) => setDraftOwner(e.target.value)}
                            className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                          />
                        </div>
                        <div>
                          <label className="block text-[11px] font-bold text-slate-600">
                            Expected Impact
                          </label>
                          <input
                            type="text"
                            value={draftImpact}
                            onChange={(e) => setDraftImpact(e.target.value)}
                            className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                          />
                        </div>
                      </div>
                      <div className="flex justify-end gap-2 pt-1">
                        <button
                          type="button"
                          onClick={() => setEditingIndividualId(null)}
                          className="rounded-lg border border-slate-200 px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50"
                        >
                          Cancel
                        </button>
                        <button
                          type="button"
                          onClick={() => saveEditIndividual(card)}
                          className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1 text-xs font-bold text-white hover:bg-blue-700"
                        >
                          <Check className="size-3.5" />
                          <span>Save Action</span>
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="mt-3">
                      <div className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
                        Action Plan
                      </div>
                      <p
                        data-testid={`individual-action-text-${card.employeeId}`}
                        className="mt-1 text-xs font-medium leading-relaxed text-slate-800 sm:text-sm"
                      >
                        {card.actionText}
                      </p>
                    </div>
                  )}
                </div>

                {/* Footer: Owner + Expected Impact */}
                <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200/70 pt-3 text-xs">
                  <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 font-semibold text-slate-700">
                    <UserCheck className="size-3.5 text-blue-600" />
                    <span>Owner: {card.owner}</span>
                  </span>

                  <span className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1 font-bold text-emerald-700">
                    <TrendingUp className="size-3.5" />
                    <span>{card.expectedImpact}</span>
                  </span>
                </div>
              </article>
            );
          })}
        </div>
      </section>
      )}

      {/* ================================================================== */}
      {/* 6. TEAM-LEVEL ACTION PLAN (Systemic Actions for Whole Team)        */}
      {/* ================================================================== */}
      {showActionSection(teamCards.length, presentationMode) && (
      <section
        id="presentation-section-team-actions"
        data-section-label="Actions"
        aria-labelledby="team-level-action-plan-heading"
        className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-4">
          <div>
            <span className="text-xs font-semibold tracking-wider text-emerald-600 uppercase">
              Cohort-Wide Interventions
            </span>
            <h2
              id="team-level-action-plan-heading"
              className="mt-0.5 text-lg font-bold text-slate-900"
            >
              Team-Level Action Plan
            </h2>
          </div>

          {showPresentationControl(presentationMode) && (
            <button
              type="button"
              data-testid="add-team-action-btn"
              onClick={() => setIsAddingTeamAction((prev) => !prev)}
              className="inline-flex items-center gap-1.5 rounded-xl border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-bold text-blue-700 transition-colors hover:bg-blue-100"
            >
              <Plus className="size-3.5" />
              <span>Add Team Action</span>
            </button>
          )}
        </div>

        {isAddingTeamAction && showPresentationControl(presentationMode) && (
          <div className="mt-4 rounded-2xl border border-blue-200 bg-blue-50/30 p-4 space-y-3">
            <div className="text-xs font-bold text-slate-900">
              New Team-Level Action for {data.teamDisplayName}
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="sm:col-span-2">
                <label className="block text-[11px] font-semibold text-slate-600">
                  Action Description
                </label>
                <input
                  type="text"
                  placeholder="Describe the team-wide workflow, scheduling, or training action..."
                  value={newTeamTitle}
                  onChange={(e) => setNewTeamTitle(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slate-600">
                  Target KPI
                </label>
                <input
                  type="text"
                  placeholder="e.g. AHT · 3.01 min → 2.50 min"
                  value={newTeamTargetKpi}
                  onChange={(e) => setNewTeamTargetKpi(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slate-600">
                  Owner
                </label>
                <input
                  type="text"
                  value={newTeamOwner}
                  onChange={(e) => setNewTeamOwner(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-slate-600">
                  Expected Team-Level Impact
                </label>
                <input
                  type="text"
                  value={newTeamImpact}
                  onChange={(e) => setNewTeamImpact(e.target.value)}
                  className="mt-1 w-full rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                />
              </div>
              <div className="flex items-end justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsAddingTeamAction(false)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-600"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleAddTeamAction}
                  className="rounded-lg bg-blue-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-blue-700"
                >
                  Save Team Action
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-3">
          {teamCards.map((card) => (
            <article
              key={card.id}
              data-testid={`team-action-card-${card.id}`}
              className="flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-slate-50/50 p-5 transition-all hover:bg-white hover:shadow-xs"
            >
              <div>
                <div className="flex items-center justify-between gap-2">
                  <span className="inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-2.5 py-0.5 text-[11px] font-bold text-blue-700">
                    <Layers className="size-3" />
                    Whole-Team Action
                  </span>
                  <span
                    data-testid={`team-action-status-${card.id}`}
                    className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                      card.status === 'In Progress'
                        ? 'bg-amber-100 text-amber-800'
                        : card.status === 'Completed'
                        ? 'bg-emerald-100 text-emerald-800'
                        : card.status === 'Planned'
                        ? 'bg-sky-100 text-sky-800'
                        : 'bg-slate-200 text-slate-700'
                    }`}
                  >
                    {card.status}
                  </span>
                </div>

                <h3 className="mt-3 text-sm font-bold leading-snug text-slate-900">
                  {card.title}
                </h3>

                <div className="mt-3 space-y-1.5 rounded-xl border border-slate-200/80 bg-white p-3 text-xs">
                  <div className="font-semibold text-slate-800">
                    <Target className="mr-1 inline size-3.5 text-blue-600" />
                    {card.targetKpi}
                  </div>
                  <div className="text-slate-500">{card.scopeDescription}</div>
                </div>
              </div>

              <div className="mt-4 flex flex-col gap-2 border-t border-slate-200/70 pt-3 text-xs">
                <div className="flex items-center justify-between text-slate-700">
                  <span className="font-medium text-slate-400">Owner</span>
                  <span data-testid={`team-action-owner-${card.id}`} className="font-bold text-slate-800">
                    {card.owner}
                  </span>
                </div>
                {showStoredPlaceholder(teamActionDueLabel(card.dueDate), presentationMode) && (
                  <div className="flex items-center justify-between text-slate-700">
                    <span className="font-medium text-slate-400">Due</span>
                    <span data-testid={`team-action-due-${card.id}`} className="font-semibold text-slate-800">
                      {teamActionDueLabel(card.dueDate)}
                    </span>
                  </div>
                )}
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-400">Expected Impact</span>
                  <span className="inline-flex items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-extrabold text-emerald-700">
                    <CheckCircle2 className="size-3" />
                    {card.expectedTeamImpact}
                  </span>
                </div>
              </div>
            </article>
          ))}
        </div>
      </section>
      )}
    </div>
  );
}
