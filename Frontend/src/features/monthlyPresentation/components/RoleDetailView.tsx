import { useMemo, useRef, useState, type ReactNode } from 'react';
import {
  AlertCircle,
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
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  UserCheck,
  Users,
} from 'lucide-react';
import { ProfileKpiSixMonthTrend } from '../../../components/employee/ScoreTrendChart';
import { GRADE_STYLES } from '../monthlyOverviewData';
import { IMPACT_LEVEL_STYLES } from '../callCenterDeepDiveData';
import type {
  RoleActionDraft,
  RoleAssignedAction,
  RoleDetailData,
  RoleIndividualActionPlan,
  RoleMemberItem,
} from '../roleDetailData';
import { showActionSection, showPresentationControl, showStoredPlaceholder } from '../presentationMode';
import { memberPageWindow } from '../roleMemberPages';
import { SelectableKpiCard } from './SelectableKpiCard';
import { FullWordGradeBadge } from './TeamDeepDiveView';

const KPI_CARDS_PER_ROW = 4;

export interface RoleDetailViewProps {
  data: RoleDetailData;
  onNavigateToOverview: () => void;
  onNavigateToFunction: () => void;
  onSaveAction: (draft: RoleActionDraft) => Promise<void> | void;
  toolbar?: ReactNode;
  presentationMode?: boolean;
}

const fieldClass =
  'mt-1.5 w-full rounded-xl border border-slate-200/90 bg-white px-3.5 text-sm text-slate-900 outline-none transition-colors focus:border-blue-500 focus:ring-2 focus:ring-blue-100';

export default function RoleDetailView({
  data,
  onNavigateToOverview,
  onNavigateToFunction,
  onSaveAction,
  toolbar,
  presentationMode = false,
}: RoleDetailViewProps) {
  const [selectedId, setSelectedId] = useState(data.kpis[0]?.id ?? '');
  const [carouselStart, setCarouselStart] = useState(0);
  const [showAllMembers, setShowAllMembers] = useState(false);
  const [memberPage, setMemberPage] = useState(0);
  const [description, setDescription] = useState('');
  const [owner, setOwner] = useState(data.roleTitle);
  const [dueDate, setDueDate] = useState('');
  const [status, setStatus] = useState<RoleActionDraft['status']>('Open');
  const [expectedImpact, setExpectedImpact] = useState('');
  const [targetKpiKey, setTargetKpiKey] = useState<string>(data.kpis[0]?.kpiKey ?? '');
  const [affectedPerson, setAffectedPerson] = useState<string>('ALL_LOW');
  const [addedActions, setAddedActions] = useState<RoleAssignedAction[]>([]);
  const [saving, setSaving] = useState(false);

  // 1-on-1 Individual Action Plan inline editing state
  const [editingIndividualId, setEditingIndividualId] = useState<string | null>(null);
  const [draftIndAction, setDraftIndAction] = useState('');
  const [draftIndOwner, setDraftIndOwner] = useState('');
  const [draftIndImpact, setDraftIndImpact] = useState('');
  const [individualOverrides, setIndividualOverrides] = useState<
    Record<string, Partial<RoleIndividualActionPlan>>
  >({});

  const selected = useMemo(
    () => data.kpis.find((kpi) => kpi.id === selectedId) ?? data.kpis[0],
    [data.kpis, selectedId],
  );

  const biggestGapKpi = useMemo(
    () => data.kpis.find((kpi) => kpi.isBiggestGap && kpi.pointsLost > 0) ?? null,
    [data.kpis],
  );

  // People in this Role: Average or below (score < 90) by default
  const below90Members = useMemo(
    () => data.members.filter((member) => member.score < 90),
    [data.members],
  );

  const displayedMembers = useMemo(
    () => (showAllMembers ? data.members : below90Members),
    [below90Members, data.members, showAllMembers],
  );

  const pageCache = useRef(new Map<string, readonly RoleMemberItem[]>());
  const listIdentity = useRef(displayedMembers);
  const listGeneration = useRef(0);
  // A new member array drops cached pages. The same array keeps the next page warm.
  if (listIdentity.current !== displayedMembers) {
    listIdentity.current = displayedMembers;
    listGeneration.current += 1;
    pageCache.current.clear();
  }
  const memberListKey = `${data.roleSlug}|${listGeneration.current}`;
  const [seenMemberList, setSeenMemberList] = useState(memberListKey);
  let page = memberPage;
  if (seenMemberList !== memberListKey) {
    pageCache.current.clear();
    setSeenMemberList(memberListKey);
    setMemberPage(0);
    page = 0;
  }

  const memberPages = useMemo(
    () => memberPageWindow(displayedMembers, page, pageCache.current, memberListKey),
    [displayedMembers, page, memberListKey],
  );
  const visibleMembers = memberPages.visible;

  const displayedIndividualCards = useMemo(() => {
    const displayedIds = new Set(visibleMembers.map((m) => m.employeeId));
    const base = (data.individualActionPlans ?? []).filter((c) =>
      displayedIds.has(c.employeeId),
    );
    return base.map((card) => ({
      ...card,
      ...(individualOverrides[card.id] ?? {}),
    }));
  }, [data.individualActionPlans, visibleMembers, individualOverrides]);

  const startEditIndividual = (card: RoleIndividualActionPlan) => {
    setEditingIndividualId(card.id);
    setDraftIndAction(card.actionText);
    setDraftIndOwner(card.owner);
    setDraftIndImpact(card.expectedImpact);
  };

  const saveEditIndividual = async (card: RoleIndividualActionPlan) => {
    const nextText = draftIndAction.trim() || card.actionText;
    const nextOwner = draftIndOwner.trim() || card.owner;
    const nextImpact = draftIndImpact.trim() || card.expectedImpact;
    setIndividualOverrides((prev) => ({
      ...prev,
      [card.id]: {
        actionText: nextText,
        owner: nextOwner,
        expectedImpact: nextImpact,
      },
    }));
    setEditingIndividualId(null);
    await onSaveAction({
      employeeId: card.employeeId,
      personName: card.personName,
      team: data.roleTitle,
      month: data.monthLabel.split(' ')[0] || data.periodKey,
      description: nextText,
      owner: nextOwner,
      dueDate: '',
      status: 'Open',
      expectedImpact: nextImpact,
      linkedKpiKey: card.linkedKpiKey,
    });
  };

  const localActions = useMemo(
    () => [...addedActions, ...data.actions],
    [addedActions, data.actions],
  );

  const gradeStyle = GRADE_STYLES[data.grade];
  const impact = IMPACT_LEVEL_STYLES[data.impactLevel];
  const up = (data.changeVsPrev ?? 0) >= 0;
  const isProblemRole = data.score < 90;
  const monthName = data.monthLabel.split(' ')[0] || data.periodKey;

  const maxCarouselStart = Math.max(0, data.kpis.length - KPI_CARDS_PER_ROW);
  const safeCarouselStart = Math.min(carouselStart, maxCarouselStart);
  const visibleKpis = useMemo(
    () => data.kpis.slice(safeCarouselStart, safeCarouselStart + KPI_CARDS_PER_ROW),
    [data.kpis, safeCarouselStart],
  );
  const hasCarousel = data.kpis.length > KPI_CARDS_PER_ROW;

  const handleSelectKpi = (kpiId: string) => {
    setSelectedId(kpiId);
    const idx = data.kpis.findIndex((k) => k.id === kpiId);
    if (idx >= 0) {
      if (idx < safeCarouselStart) {
        setCarouselStart(idx);
      } else if (idx >= safeCarouselStart + KPI_CARDS_PER_ROW) {
        setCarouselStart(Math.min(maxCarouselStart, idx - KPI_CARDS_PER_ROW + 1));
      }
    }
  };

  const kpiGridColsClass =
    visibleKpis.length === 1
      ? 'grid-cols-1'
      : visibleKpis.length === 2
      ? 'grid-cols-1 sm:grid-cols-2'
      : visibleKpis.length === 3
      ? 'grid-cols-1 sm:grid-cols-3'
      : 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4';

  const save = async () => {
    const text = description.trim();
    if (!text) return;
    const chosenKpi =
      data.kpis.find((k) => k.kpiKey === targetKpiKey) ?? selected ?? data.kpis[0];
    const resolvedPeople =
      affectedPerson === 'ALL_LOW'
        ? below90Members.length > 0
          ? below90Members.map((m) => m.personName)
          : data.members.map((m) => m.personName)
        : [affectedPerson];

    const draft: RoleActionDraft = {
      employeeId: data.employeeId,
      personName: data.personName,
      team: data.roleTitle,
      month: monthName,
      description: text,
      owner: owner.trim() || data.roleTitle,
      dueDate,
      status,
      expectedImpact: expectedImpact.trim(),
      linkedKpiKey: chosenKpi?.kpiKey ?? null,
    };
    setSaving(true);
    try {
      await onSaveAction(draft);
      setAddedActions((current) => [
        {
          id: `local-${Date.now()}`,
          title: `${data.roleTitle} Corrective Action`,
          description: draft.description,
          owner: draft.owner,
          dueDate: draft.dueDate || null,
          status: draft.status,
          expectedImpact: draft.expectedImpact || 'Impact to be confirmed',
          linkedKpiName: chosenKpi?.shortName || 'Role Execution',
          affectedPeople: resolvedPeople,
        },
        ...current,
      ]);
      setDescription('');
      setExpectedImpact('');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      data-testid="role-detail-page"
      className="mx-auto max-w-6xl space-y-7 px-4 py-8 sm:px-6 lg:px-8"
    >
      {/* ================================================================== */}
      {/* 1. HEADER — Calm Executive Hierarchy                               */}
      {/* ================================================================== */}
      <header className="rounded-2xl border border-slate-200/85 bg-white p-6 shadow-2xs sm:p-8">
        {/* Top Bar: Breadcrumb + Back Action */}
        <div className="flex min-w-0 flex-col gap-3 border-b border-slate-100 pb-5">
          <nav
            aria-label="Breadcrumb"
            data-testid="role-detail-breadcrumb"
            className="flex flex-wrap items-center gap-1.5 text-xs font-medium text-slate-500"
          >
            <button
              type="button"
              onClick={onNavigateToOverview}
              className="rounded-md px-2 py-1 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
            >
              Overview
            </button>
            <ChevronRight className="size-3.5 text-slate-300" aria-hidden />
            <button
              type="button"
              data-testid="breadcrumb-function"
              onClick={onNavigateToFunction}
              className="rounded-md px-2 py-1 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
            >
              {data.functionName}
            </button>
            <ChevronRight className="size-3.5 text-slate-300" aria-hidden />
            <span className="rounded-md bg-slate-100 px-2.5 py-1 font-semibold text-slate-900">
              {data.roleTitle}
              {data.branchLabel ? ` · ${data.branchLabel}` : ''}
            </span>
          </nav>

          <div className="flex w-full min-w-0 max-w-full flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onNavigateToFunction}
              className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200/90 bg-white px-3 text-xs font-semibold text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50"
            >
              <ArrowLeft className="size-3.5 text-slate-500" aria-hidden />
              <span>Back to {data.functionName}</span>
            </button>
            {toolbar}
          </div>
        </div>

        {/* Main Header Content: Role Title, Person/Count Underneath, Score & Diagnosis */}
        <div className="mt-6 flex flex-col justify-between gap-6 lg:flex-row lg:items-center">
          <div className="max-w-2xl">
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span className="font-medium">
                {data.regionName} · {data.monthLabel}
              </span>
              <span className="text-slate-300" aria-hidden>
                ·
              </span>
              <span
                data-testid="role-impact-badge"
                className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${impact.badgeBg} ${impact.badgeText} ${impact.badgeBorder}`}
              >
                <span className={`size-1.5 rounded-full ${impact.dotColor}`} />
                {data.impactLevel} Impact
              </span>
            </div>

            {/* Role Name as Main Title */}
            <h1 className="mt-2 text-2xl font-bold tracking-tight text-slate-900 sm:text-3xl">
              {data.roleTitle}
              {data.branchLabel ? (
                <span className="font-semibold text-slate-500"> · {data.branchLabel}</span>
              ) : null}
            </h1>

            {/* Person Name Underneath (or Count if Multiple) */}
            {data.members.length <= 1 ? (
              <p className="mt-1 text-base font-medium text-slate-600">
                {data.personName}
              </p>
            ) : (
              <p className="mt-1.5 inline-flex items-center gap-1.5 text-sm font-medium text-slate-600">
                <Users className="size-4 text-slate-400" aria-hidden />
                <span>
                  {data.headcount} people in {data.branchLabel ?? 'this role'} · {data.below90Count} Average or below
                </span>
              </p>
            )}

            {/* Concise Executive Diagnosis Sentence */}
            <p
              data-testid="role-diagnosis"
              className="mt-3 text-sm leading-relaxed text-slate-600 sm:text-[15px]"
            >
              {data.diagnosis}
            </p>
          </div>

          {/* Right Metric Cluster: Dominant Score, Full-Word Grade, Movement & Gap */}
          <div className="flex shrink-0 flex-wrap items-center gap-5 rounded-2xl border border-slate-200/80 bg-slate-50/60 px-5 py-4 sm:px-6 sm:py-5">
            <div>
              <div className="text-[11px] font-bold tracking-wider text-slate-400 uppercase">
                {data.headcount > 1 ? 'Combined Score' : 'Role Score'}
              </div>
              <div className="mt-1 flex items-baseline gap-3">
                <p
                  data-testid="role-detail-score"
                  className={`text-4xl font-extrabold tracking-tight tabular-nums sm:text-5xl ${
                    isProblemRole ? 'text-rose-600' : gradeStyle.scoreText
                  }`}
                >
                  {data.score.toFixed(1)}%
                </p>
                <FullWordGradeBadge
                  grade={data.grade}
                  gradeFullLabel={data.gradeFullLabel}
                  size="lg"
                />
              </div>
            </div>

            <div className="hidden h-12 w-px bg-slate-200/80 sm:block" />

            <div className="flex flex-col gap-1.5 text-xs">
              <span
                className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 font-semibold tabular-nums ${
                  isProblemRole
                    ? 'border-rose-200/80 bg-rose-50/70 text-rose-700'
                    : 'border-slate-200 bg-white text-slate-700'
                }`}
              >
                <Target
                  className={`size-3.5 ${
                    isProblemRole ? 'text-rose-500' : 'text-slate-400'
                  }`}
                  aria-hidden
                />
                Gap {data.gap.toFixed(1)}%
              </span>

              <span
                className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 font-semibold tabular-nums ${
                  data.changeVsPrev === null
                    ? 'border-slate-200 bg-white text-slate-400'
                    : up
                    ? 'border-emerald-200/80 bg-emerald-50/70 text-emerald-700'
                    : 'border-rose-200/80 bg-rose-50/70 text-rose-700'
                }`}
              >
                {data.changeVsPrev === null ? (
                  `No ${data.previousMonthLabel} baseline`
                ) : (
                  <>
                    {up ? (
                      <ArrowUpRight className="size-3.5" aria-hidden />
                    ) : (
                      <ArrowDownRight className="size-3.5" aria-hidden />
                    )}
                    {up ? '+' : ''}
                    {data.changeVsPrev.toFixed(1)}% vs {data.previousMonthLabel}
                  </>
                )}
              </span>
            </div>
          </div>
        </div>
      </header>

      {/* ================================================================== */}
      {/* 2. KEY ROLE KPIs — Compact Single-Row Carousel (Worst to Best)     */}
      {/* ================================================================== */}
      <section
        id="presentation-section-role-kpis"
        data-section-label="KPIs"
        aria-labelledby="role-kpis-heading"
        data-testid="role-kpis"
        className="scroll-mt-24 space-y-3"
      >
        <div className="flex flex-wrap items-center justify-between gap-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex size-7 items-center justify-center rounded-lg border border-blue-200/80 bg-blue-50 text-blue-600">
              <Gauge className="size-3.5" aria-hidden />
            </span>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2
                  id="role-kpis-heading"
                  className="text-sm font-bold tracking-tight text-slate-900 sm:text-base"
                >
                  {data.roleTitle} KPIs
                </h2>
                <span className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-[10px] font-semibold text-slate-500">
                  {data.kpis.length} {data.kpis.length === 1 ? 'measure' : 'measures'} · sorted worst to best
                </span>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {biggestGapKpi && (
              <div
                data-testid="biggest-gap-summary-pill"
                className="inline-flex items-center gap-1.5 rounded-lg border border-rose-200/90 bg-rose-50/80 px-2.5 py-1 text-[11px] font-semibold text-rose-900 shadow-2xs"
              >
                <Flame className="size-3.5 shrink-0 text-rose-600" aria-hidden />
                <span>
                  Biggest Gap Driver:{' '}
                  <strong className="font-extrabold text-rose-700">
                    {biggestGapKpi.shortName}
                  </strong>{' '}
                  (−{biggestGapKpi.pointsLost.toFixed(1)} pts ·{' '}
                  {biggestGapKpi.contributionPct.toFixed(1)}% of{' '}
                  {Math.round(biggestGapKpi.weightPct)}% weight)
                </span>
              </div>
            )}

            {data.kpis.length > 0 && (
              <div
                data-testid="kpi-carousel-controls"
                className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200/90 bg-white px-2 py-1 shadow-2xs"
              >
                <span className="px-1 text-[11px] font-bold text-slate-500 tabular-nums">
                  {safeCarouselStart + 1}–
                  {Math.min(data.kpis.length, safeCarouselStart + KPI_CARDS_PER_ROW)} of{' '}
                  {data.kpis.length}
                </span>
                <button
                  type="button"
                  data-testid="kpi-carousel-prev"
                  aria-label="Previous KPI cards"
                  disabled={safeCarouselStart === 0}
                  onClick={() =>
                    setCarouselStart((prev) => Math.max(0, prev - 1))
                  }
                  className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-35"
                >
                  <ChevronLeft className="size-3.5" aria-hidden />
                </button>
                <button
                  type="button"
                  data-testid="kpi-carousel-next"
                  aria-label="Next KPI cards"
                  disabled={safeCarouselStart >= maxCarouselStart}
                  onClick={() =>
                    setCarouselStart((prev) =>
                      Math.min(maxCarouselStart, prev + 1),
                    )
                  }
                  className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-35"
                >
                  <ChevronRight className="size-3.5" aria-hidden />
                </button>
              </div>
            )}
          </div>
        </div>

        {data.kpis.length === 0 ? (
          <div className="rounded-2xl border border-slate-200/80 bg-white p-5 text-sm text-slate-500">
            No KPI series available for this role in the selected month.
          </div>
        ) : (
          <div>
            <div
              role="tablist"
              aria-label="Key Role KPIs"
              className={`grid gap-3 ${kpiGridColsClass}`}
            >
              {visibleKpis.map((kpi) => (
                <SelectableKpiCard
                  key={kpi.id}
                  selected={selected?.id === kpi.id}
                  status={kpi.statusBadge}
                  title={kpi.shortName}
                  titleTooltip={kpi.name}
                  betterDirection={kpi.betterDirection}
                  actual={kpi.actualDisplay}
                  target={kpi.targetDisplay}
                  achievementPct={kpi.achievementPct}
                  gapLabel={kpi.gapLabel}
                  movement={
                    kpi.momDeltaPct !== null ? (
                      <span
                        className={`inline-flex shrink-0 items-center gap-0.5 font-medium tabular-nums ${
                          kpi.isMomGood === true
                            ? 'text-emerald-700'
                            : kpi.isMomGood === false
                            ? 'text-rose-700'
                            : 'text-slate-500'
                        }`}
                      >
                        {kpi.momDeltaPct > 0 ? (
                          <ArrowUpRight className="size-3.5" aria-hidden />
                        ) : kpi.momDeltaPct < 0 ? (
                          <ArrowDownRight className="size-3.5" aria-hidden />
                        ) : null}
                        {kpi.momDeltaPct > 0 ? '+' : ''}
                        {kpi.momDeltaPct.toFixed(1)}% MoM
                      </span>
                    ) : null
                  }
                  biggestGap={kpi.isBiggestGap}
                  biggestGapTestId={`biggest-gap-badge-${kpi.kpiKey}`}
                  weightPct={kpi.weightPct}
                  contributionPct={kpi.contributionPct}
                  pointsLost={kpi.pointsLost}
                  testId={`role-kpi-tab-${kpi.kpiKey}`}
                  onSelect={() => handleSelectKpi(kpi.id)}
                  asTab
                />
              ))}
            </div>

            {/* Carousel Step Dots when > 4 KPIs */}
            {hasCarousel && (
              <div className="mt-2.5 flex items-center justify-center gap-1.5">
                {Array.from({ length: maxCarouselStart + 1 }, (_, stepIdx) => {
                  const isCurrent = stepIdx === safeCarouselStart;
                  return (
                    <button
                      key={stepIdx}
                      type="button"
                      aria-label={`Show KPIs starting at ${stepIdx + 1}`}
                      onClick={() => setCarouselStart(stepIdx)}
                      className={`h-1.5 rounded-full transition-all ${
                        isCurrent
                          ? 'w-5 bg-blue-600'
                          : 'w-1.5 bg-slate-300 hover:bg-slate-400'
                      }`}
                    />
                  );
                })}
              </div>
            )}
          </div>
        )}
      </section>

      {/* ================================================================== */}
      {/* 3. 6-MONTH TREND — Reused 360 Profile Interactive Trend Component  */}
      {/* ================================================================== */}
      {selected && (
        <section
          id="presentation-section-role-trend"
          data-section-label="Trend"
          aria-labelledby="role-trend-heading"
          className="scroll-mt-24 rounded-2xl border border-slate-200/85 bg-white p-6 shadow-2xs sm:p-8"
        >
          <ProfileKpiSixMonthTrend
            kpis={data.kpis}
            selectedId={selected.id}
            onSelectKpi={handleSelectKpi}
          />

          {/* Short, Precise Structural Diagnosis Under the Chart */}
          <div
            data-testid="role-kpi-structural-diagnosis"
            className="mt-5 rounded-xl border border-slate-200/80 bg-slate-50/60 px-4 py-3.5 text-xs leading-relaxed text-slate-700 sm:text-sm"
          >
            <div className="flex items-start gap-2.5">
              <Sparkles
                className="mt-0.5 size-4 shrink-0 text-blue-600"
                aria-hidden
              />
              <div className="space-y-1">
                <p className="font-semibold text-slate-900">{selected.diagnosis}</p>
                {selected.structuralDiagnosis && (
                  <p className="text-slate-600">{selected.structuralDiagnosis}</p>
                )}
              </div>
            </div>
          </div>

          {/* Clean, Non-Repetitive Accountability & Ownership Bar */}
          <div
            data-testid="role-accountability"
            className="mt-4 flex flex-col justify-between gap-3 rounded-xl border border-slate-200/75 bg-white px-4 py-3 text-xs sm:flex-row sm:items-center"
          >
            <div className="flex items-center gap-2 text-slate-600">
              <ShieldCheck className="size-4 shrink-0 text-slate-400" aria-hidden />
              <span className="font-semibold text-slate-800">
                {data.accountabilityGaps[0]?.ownership ||
                  `Accountable owner: ${data.roleTitle} inside ${data.functionName}`}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-1.5">
              {data.accountabilityGaps.slice(0, 3).map((gap) => (
                <span
                  key={gap.id}
                  className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium ${
                    isProblemRole
                      ? 'border-rose-200/80 bg-rose-50/60 text-rose-700'
                      : 'border-slate-200 bg-slate-50 text-slate-600'
                  }`}
                >
                  <AlertCircle className="size-3 shrink-0" aria-hidden />
                  {gap.statement}
                </span>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ================================================================== */}
      {/* 4. FOCUS COHORT TABLE — People in This Role (Multi-KPI Breakdown)  */}
      {/* ================================================================== */}
      <section
        id="presentation-section-role-members"
        data-section-label="People"
        aria-labelledby="role-members-heading"
        data-testid="role-members-section"
        className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs sm:p-7"
      >
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-4">
          <div>
            <span className="text-xs font-semibold tracking-wider text-amber-700 uppercase">
              Focus Cohort (Score &lt; 90%)
            </span>
            <h2
              id="role-members-heading"
              className="mt-0.5 text-lg font-bold tracking-tight text-slate-900"
            >
              People in This Role — Average and Below
            </h2>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <span className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-xs font-bold text-amber-800">
              {below90Members.length} of {data.members.length}{' '}
              {data.members.length === 1 ? 'person requires' : 'people require'} action
            </span>

            {data.members.length > below90Members.length && (
              <button
                type="button"
                data-testid="toggle-show-all-members"
                onClick={() => setShowAllMembers((prev) => !prev)}
                className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-slate-200/90 bg-slate-50 px-3 text-xs font-bold text-slate-700 transition-colors hover:border-blue-300 hover:bg-white hover:text-blue-600"
              >
                <Users className="size-3.5 text-slate-500" aria-hidden />
                <span>
                  {showAllMembers
                    ? `Show Average & Below Only (${below90Members.length})`
                    : `View All (${data.members.length})`}
                </span>
              </button>
            )}
          </div>
        </div>

        {displayedMembers.length === 0 ? (
          <div className="mt-4 flex flex-col items-center justify-between gap-3 rounded-xl border border-emerald-200/70 bg-emerald-50/40 px-4 py-4 sm:flex-row">
            <div className="flex items-center gap-2.5 text-xs font-medium text-emerald-900 sm:text-sm">
              <CheckCircle2 className="size-4 shrink-0 text-emerald-600" aria-hidden />
              <span>
                No people in this role are Average or below — all {data.members.length}{' '}
                {data.members.length === 1 ? 'person is' : 'people are'} Meeting Expectations
                or Excellent.
              </span>
            </div>
            <button
              type="button"
              onClick={() => setShowAllMembers(true)}
              className="shrink-0 rounded-lg border border-emerald-300 bg-white px-3 py-1.5 text-xs font-bold text-emerald-800 transition-colors hover:bg-emerald-50"
            >
              View All ({data.members.length})
            </button>
          </div>
        ) : (
          <div className="mt-4 overflow-x-auto">
            <table
              data-testid="role-members-table"
              className="w-full border-collapse text-left text-sm"
            >
              <thead>
                <tr className="border-b border-slate-200 text-xs font-semibold tracking-wider text-slate-500 uppercase">
                  <th className="py-3 pr-4">Employee</th>
                  <th className="px-4 py-3 text-right">Score</th>
                  {data.kpis.slice(0, 4).map((kpi) => (
                    <th key={kpi.kpiKey} className="px-4 py-3 text-right">
                      {kpi.shortName}
                      <span className="block text-[10px] font-normal text-slate-400 normal-case">
                        Target: {kpi.targetDisplay}
                      </span>
                    </th>
                  ))}
                  <th className="py-3 pl-4 text-center">Grade</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {visibleMembers.map((member) => {
                  const memberGradeStyle = GRADE_STYLES[member.grade];
                  return (
                    <tr
                      key={member.employeeId}
                      data-testid={`role-member-${member.employeeId}`}
                      className="transition-colors hover:bg-slate-50/80"
                    >
                      {/* Employee Name + Root-Cause Main Issue */}
                      <td className="py-3.5 pr-4">
                        <div className="font-bold text-slate-900">{member.personName}</div>
                        <div className="mt-0.5 max-w-md text-xs text-slate-500">
                          {member.signal}
                        </div>
                      </td>

                      {/* Score + MoM movement */}
                      <td className="px-4 py-3.5 text-right tabular-nums">
                        <div
                          className={`text-base font-extrabold ${memberGradeStyle.scoreText}`}
                        >
                          {member.score.toFixed(1)}%
                        </div>
                        {member.changeVsPrev !== null && (
                          <div
                            className={`text-[11px] font-semibold ${
                              member.changeVsPrev >= 0 ? 'text-emerald-600' : 'text-rose-600'
                            }`}
                          >
                            {member.changeVsPrev >= 0
                              ? `+${member.changeVsPrev.toFixed(1)}%`
                              : `${member.changeVsPrev.toFixed(1)}%`}{' '}
                            vs {data.previousMonthLabel}
                          </div>
                        )}
                      </td>

                      {/* Per-KPI Actual Cells with Diagnostic Coloring */}
                      {(member.kpiCells ?? []).map((cell) => (
                        <td
                          key={cell.kpiKey}
                          className="px-4 py-3.5 text-right tabular-nums"
                        >
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

                      {/* Full-Word Grade */}
                      <td className="py-3.5 pl-4 text-center">
                        <FullWordGradeBadge
                          grade={member.grade}
                          gradeFullLabel={member.gradeFullLabel}
                          size="sm"
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {memberPages.pageCount > 1 && (
              <nav
                data-testid="role-members-pager"
                aria-label="People pages"
                className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3"
              >
                <p className="text-xs font-semibold text-slate-500 tabular-nums" aria-live="polite">
                  {memberPages.rangeStart}–{memberPages.rangeEnd} of {displayedMembers.length}
                </p>
                <div className="inline-flex items-center gap-1.5">
                  <button
                    type="button"
                    data-testid="role-members-prev"
                    aria-label="Previous people"
                    disabled={memberPages.page === 0}
                    onClick={() => setMemberPage((current) => Math.max(0, current - 1))}
                    className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-bold text-slate-700 transition-colors hover:border-slate-300 hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    <ChevronLeft className="size-3.5" aria-hidden />
                    Previous
                  </button>
                  <span className="px-1 text-xs font-bold text-slate-500 tabular-nums">
                    {memberPages.page + 1} / {memberPages.pageCount}
                  </span>
                  <button
                    type="button"
                    data-testid="role-members-next"
                    aria-label="Next people"
                    disabled={memberPages.page >= memberPages.pageCount - 1}
                    onClick={() =>
                      setMemberPage((current) => Math.min(memberPages.pageCount - 1, current + 1))
                    }
                    className="inline-flex h-8 items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-bold text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    Next
                    <ChevronRight className="size-3.5" aria-hidden />
                  </button>
                </div>
              </nav>
            )}
          </div>
        )}
      </section>

      {/* ================================================================== */}
      {/* 5A. 1-ON-1 COACHING & REMEDIATION — Individual Action Plan         */}
      {/* ================================================================== */}
      {showActionSection(displayedIndividualCards.length, presentationMode) && displayedIndividualCards.length > 0 && (
        <section
          id="presentation-section-role-coaching"
          data-section-label="Coaching"
          aria-labelledby="role-individual-action-plan-heading"
          data-testid="role-individual-action-plan-section"
          className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs sm:p-7"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-4">
            <div>
              <span className="text-xs font-semibold tracking-wider text-blue-600 uppercase">
                1-on-1 Coaching &amp; Remediation
              </span>
              <h2
                id="role-individual-action-plan-heading"
                className="mt-0.5 text-lg font-bold text-slate-900"
              >
                Individual Action Plan
              </h2>
            </div>
            {showPresentationControl(presentationMode) && (
              <p className="text-xs font-medium text-slate-500">
                One action card per employee shown above · Click &ldquo;Edit&rdquo; on any card to customize &amp; save
              </p>
            )}
          </div>

          <div
            className={`mt-5 grid grid-cols-1 gap-4 ${
              displayedIndividualCards.length > 1 ? 'md:grid-cols-2' : 'md:grid-cols-1'
            }`}
          >
            {displayedIndividualCards.map((card) => {
              const isEditing =
                showPresentationControl(presentationMode) && editingIndividualId === card.id;
              const cardGradeStyle = GRADE_STYLES[card.grade];

              return (
                <article
                  key={card.id}
                  data-testid={`role-individual-action-card-${card.employeeId}`}
                  className="flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-slate-50/50 p-5 transition-all hover:bg-white hover:shadow-xs"
                >
                  <div>
                    {/* Card Header: Employee Name + Score + Full-Word Grade + Edit Button */}
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-base font-bold text-slate-900">
                          {card.personName}
                        </h3>
                        <span
                          className={`text-sm font-extrabold tabular-nums ${cardGradeStyle.scoreText}`}
                        >
                          {card.score.toFixed(1)}%
                        </span>
                        <FullWordGradeBadge
                          grade={card.grade}
                          gradeFullLabel={card.gradeFullLabel}
                          size="sm"
                        />
                      </div>

                      {!isEditing && showPresentationControl(presentationMode) && (
                        <button
                          type="button"
                          onClick={() => startEditIndividual(card)}
                          className="inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 transition-colors hover:border-blue-300 hover:text-blue-600"
                        >
                          <Edit3 className="size-3" aria-hidden />
                          <span>Edit</span>
                        </button>
                      )}
                    </div>

                    {/* Main Issue Box */}
                    <div className="mt-3 rounded-xl border border-rose-200/70 bg-rose-50/50 px-3.5 py-2.5 text-xs text-slate-700">
                      <span className="font-bold text-rose-800">
                        <AlertTriangle
                          className="mr-1 inline size-3.5 text-rose-600"
                          aria-hidden
                        />
                        Main Issue:{' '}
                      </span>
                      {card.mainIssue}
                    </div>

                    {/* Action Plan (View or Inline Edit Mode) */}
                    {isEditing ? (
                      <div className="mt-3 space-y-2.5 rounded-xl border border-blue-200 bg-white p-3">
                        <div>
                          <label className="block text-[11px] font-bold text-slate-600">
                            Corrective Action
                          </label>
                          <textarea
                            rows={2}
                            value={draftIndAction}
                            onChange={(e) => setDraftIndAction(e.target.value)}
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
                              value={draftIndOwner}
                              onChange={(e) => setDraftIndOwner(e.target.value)}
                              className="mt-1 w-full rounded-lg border border-slate-200 px-2.5 py-1 text-xs text-slate-900 focus:border-blue-500 focus:outline-none"
                            />
                          </div>
                          <div>
                            <label className="block text-[11px] font-bold text-slate-600">
                              Expected Impact
                            </label>
                            <input
                              type="text"
                              value={draftIndImpact}
                              onChange={(e) => setDraftIndImpact(e.target.value)}
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
                            onClick={() => void saveEditIndividual(card)}
                            className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1 text-xs font-bold text-white hover:bg-blue-700"
                          >
                            <Check className="size-3.5" aria-hidden />
                            <span>Save Action</span>
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="mt-3">
                        <div className="text-[11px] font-bold tracking-wider text-slate-400 uppercase">
                          Action Plan
                        </div>
                        <p className="mt-1 text-xs font-medium leading-relaxed text-slate-800 sm:text-sm">
                          {card.actionText}
                        </p>
                      </div>
                    )}
                  </div>

                  {/* Footer: Owner + Expected Impact */}
                  <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-200/70 pt-3 text-xs">
                    <span className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-2.5 py-1 font-semibold text-slate-700">
                      <UserCheck className="size-3.5 text-blue-600" aria-hidden />
                      <span>Owner: {card.owner}</span>
                    </span>

                    <span className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1 font-bold text-emerald-700">
                      <TrendingUp className="size-3.5" aria-hidden />
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
      {/* 5. COHORT-WIDE INTERVENTIONS — Role-Level Action Plan              */}
      {/* ================================================================== */}
      {showActionSection(localActions.length, presentationMode) ? (
      <section
        id="presentation-section-role-actions"
        data-section-label="Actions"
        aria-labelledby="role-actions-heading"
        data-testid="role-actions-section"
        className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs sm:p-8"
      >
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-5">
          <div>
            <span className="text-xs font-semibold tracking-wider text-emerald-600 uppercase">
              Cohort-Wide Interventions
            </span>
            <h2
              id="role-actions-heading"
              className="mt-0.5 text-lg font-bold tracking-tight text-slate-900 sm:text-xl"
            >
              Role-Level Action Plan
            </h2>
            <p className="mt-0.5 text-xs text-slate-500">
              Systemic interventions linked directly to the affected KPIs and people in {data.roleTitle}
            </p>
          </div>
          <span className="rounded-full border border-slate-200/80 bg-slate-50 px-3 py-1 text-xs font-bold text-slate-700">
            {localActions.length} {localActions.length === 1 ? 'action' : 'actions'}
          </span>
        </div>

        {/* Existing Actions as Cohort-Wide Intervention Cards */}
        {localActions.length === 0 ? (
          <p className="mt-5 text-sm text-slate-500">
            No corrective actions recorded for this role yet.
          </p>
        ) : (
          <ul
            className={`mt-6 grid grid-cols-1 gap-4 ${
              localActions.length > 2
                ? 'lg:grid-cols-3'
                : localActions.length > 1
                ? 'lg:grid-cols-2'
                : 'lg:grid-cols-1'
            }`}
          >
            {localActions.map((action) => {
              const linkedKpiLabel =
                action.linkedKpiName ||
                selected?.shortName ||
                data.accountableKpis[0] ||
                'Role Execution';
              const peopleList =
                action.affectedPeople && action.affectedPeople.length > 0
                  ? action.affectedPeople
                  : below90Members.length > 0
                  ? below90Members.map((m) => m.personName)
                  : data.members.map((m) => m.personName);

              return (
                <li
                  key={action.id}
                  data-testid={`role-action-${action.id}`}
                  className="flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-slate-50/50 p-5 transition-all hover:bg-white hover:shadow-xs"
                >
                  <div>
                    {/* Card Top: Whole-Role Action Badge + Status Pill */}
                    <div className="flex items-center justify-between gap-2">
                      <span className="inline-flex items-center gap-1 rounded-md border border-blue-200 bg-blue-50 px-2.5 py-0.5 text-[11px] font-bold text-blue-700">
                        <Layers className="size-3" aria-hidden />
                        Whole-Role Action
                      </span>

                      <span
                        className={`rounded-full px-2.5 py-0.5 text-[11px] font-bold ${
                          action.status === 'In Progress'
                            ? 'bg-amber-100 text-amber-800'
                            : action.status === 'Completed'
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-slate-200 text-slate-700'
                        }`}
                      >
                        {action.status}
                      </span>
                    </div>

                    {/* Action Title */}
                    <h3 className="mt-3 text-sm font-bold leading-snug text-slate-900">
                      {action.title || action.description}
                    </h3>

                    {/* Inner Target KPI & Scope Box (matches Team-Level Action Plan) */}
                    <div className="mt-3 space-y-1.5 rounded-xl border border-slate-200/80 bg-white p-3 text-xs">
                      <div
                        data-testid={`action-linked-kpi-${action.id}`}
                        className="font-semibold text-slate-800"
                      >
                        <Target
                          className="mr-1 inline size-3.5 text-blue-600"
                          aria-hidden
                        />
                        <span>Affects KPI: {linkedKpiLabel}</span>
                      </div>
                      {peopleList.length > 0 && (
                        <div
                          data-testid={`action-affected-people-${action.id}`}
                          className="text-slate-500"
                        >
                          People: {peopleList.join(', ')}
                        </div>
                      )}
                      {action.title && action.description !== action.title && (
                        <div className="border-t border-slate-100 pt-1.5 text-[11px] leading-relaxed text-slate-500">
                          {action.description}
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Metadata Footer: Owner & Expected Impact */}
                  <dl className="mt-4 flex flex-col gap-2 border-t border-slate-200/70 pt-3 text-xs">
                    <div className="flex items-center justify-between text-slate-700">
                      <dt className="font-medium text-slate-400">Owner</dt>
                      <dd className="font-bold text-slate-800">{action.owner}</dd>
                    </div>
                    {showStoredPlaceholder(action.dueDate?.trim() || 'No due date', presentationMode) && (
                      <div className="flex items-center justify-between text-slate-700">
                        <dt className="font-medium text-slate-400">Due</dt>
                        <dd className="font-bold text-slate-800">{action.dueDate?.trim() || 'No due date'}</dd>
                      </div>
                    )}
                    <div className="flex items-center justify-between">
                      <dt className="font-medium text-slate-400">Expected Impact</dt>
                      <dd className="inline-flex items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50 px-2 py-0.5 font-extrabold text-emerald-700">
                        <CheckCircle2 className="size-3" aria-hidden />
                        {action.expectedImpact}
                      </dd>
                    </div>
                  </dl>
                </li>
              );
            })}
          </ul>
        )}

        {showPresentationControl(presentationMode) && (
        <form
          data-testid="role-action-form"
          className="mt-6 rounded-2xl border border-slate-200/85 bg-slate-50/50 p-5"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="text-xs font-bold tracking-wider text-slate-700 uppercase">
              Add Corrective Action
            </h3>
            <span className="text-xs font-medium text-slate-500">
              Links directly to KPI &amp; people in {data.roleTitle}
            </span>
          </div>

          <div className="mt-3.5 grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-3">
            <label className="block text-xs font-semibold text-slate-700 sm:col-span-2 lg:col-span-3">
              Description
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                required
                rows={2}
                placeholder="Describe the corrective action and target workflow adjustment..."
                className={`${fieldClass} py-2`}
              />
            </label>

            <label className="block text-xs font-semibold text-slate-700">
              Target KPI
              <select
                value={targetKpiKey || selected?.kpiKey || ''}
                onChange={(event) => setTargetKpiKey(event.target.value)}
                className={`${fieldClass} h-9`}
              >
                {data.kpis.map((kpi) => (
                  <option key={kpi.kpiKey} value={kpi.kpiKey}>
                    {kpi.shortName} ({kpi.actualDisplay} vs {kpi.targetDisplay})
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-xs font-semibold text-slate-700">
              Affected person
              <select
                value={affectedPerson}
                onChange={(event) => setAffectedPerson(event.target.value)}
                className={`${fieldClass} h-9`}
              >
                <option value="ALL_LOW">
                  {below90Members.length > 0
                    ? `All Average & Below (${below90Members.map((m) => m.personName).join(', ')})`
                    : `All in ${data.roleTitle}`}
                </option>
                {data.members.map((member) => (
                  <option key={member.employeeId} value={member.personName}>
                    {member.personName} ({member.score.toFixed(1)}%)
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-xs font-semibold text-slate-700">
              Owner
              <input
                value={owner}
                onChange={(event) => setOwner(event.target.value)}
                className={`${fieldClass} h-9`}
              />
            </label>

            <label className="block text-xs font-semibold text-slate-700">
              Due date
              <input
                type="date"
                value={dueDate}
                onChange={(event) => setDueDate(event.target.value)}
                className={`${fieldClass} h-9`}
              />
            </label>

            <label className="block text-xs font-semibold text-slate-700">
              Status
              <select
                value={status}
                onChange={(event) =>
                  setStatus(event.target.value as RoleActionDraft['status'])
                }
                className={`${fieldClass} h-9`}
              >
                <option>Open</option>
                <option>In Progress</option>
                <option>Completed</option>
              </select>
            </label>

            <label className="block text-xs font-semibold text-slate-700">
              Expected impact
              <input
                value={expectedImpact}
                onChange={(event) => setExpectedImpact(event.target.value)}
                placeholder="e.g., +2.5% role score lift"
                className={`${fieldClass} h-9`}
              />
            </label>
          </div>

          <div className="mt-4 flex justify-end">
            <button
              type="submit"
              data-testid="save-role-action"
              disabled={saving || !description.trim()}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-blue-600 px-4 text-xs font-bold text-white shadow-2xs transition-colors hover:bg-blue-700 disabled:opacity-40"
            >
              <Plus className="size-3.5" aria-hidden />
              <span>{saving ? 'Saving…' : 'Add action'}</span>
            </button>
          </div>
        </form>
        )}
      </section>
      ) : null}
    </div>
  );
}
