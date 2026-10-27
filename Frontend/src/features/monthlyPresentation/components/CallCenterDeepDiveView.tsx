import { useState, type ReactNode } from 'react';
import {
  Activity,
  AlertCircle,
  ArrowDownRight,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  Layers,
  ShieldCheck,
  Sparkles,
  Target,
  TrendingUp,
  UserCheck,
  Users,
} from 'lucide-react';
import { GRADE_STYLES } from '../monthlyOverviewData';
import {
  IMPACT_LEVEL_STYLES,
  type AgentKeyKpiItem,
  type AgentNeedingAttentionItem,
  type AgentTeamPerformanceItem,
  type CallCenterDeepDiveData,
  type PositionActionPlanItem,
  slugifyIdentifier,
  type SupportPositionItem,
} from '../callCenterDeepDiveData';
import type { TeamSlug } from '../teamDeepDiveData';
import { KpiTrendMovement, SelectableKpiCard } from './SelectableKpiCard';
import { FullWordGradeBadge } from './TeamDeepDiveView';

const CARDS_PER_ROW = 4;

export interface CallCenterDeepDiveViewProps {
  data: CallCenterDeepDiveData;
  onBackToOverview: () => void;
  onSelectAgentTeam: (teamSlug: TeamSlug) => void;
  onSelectRole?: (roleSlug: string) => void;
  toolbar?: ReactNode;
}

const POSITION_BADGE_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  Trainer: {
    bg: 'bg-emerald-50',
    text: 'text-emerald-700',
    border: 'border-emerald-200',
  },
  'Quality Specialist': {
    bg: 'bg-amber-50',
    text: 'text-amber-700',
    border: 'border-amber-200',
  },
  'Team Leader': {
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    border: 'border-blue-200',
  },
  'Workforce Analyst': {
    bg: 'bg-rose-50',
    text: 'text-rose-700',
    border: 'border-rose-200',
  },
};

function positionBadge(name: string) {
  return (
    POSITION_BADGE_STYLES[name] ?? {
      bg: 'bg-slate-50',
      text: 'text-slate-700',
      border: 'border-slate-200',
    }
  );
}

/* -------------------------------------------------------------------------- */
/*  Layer 1 Card: Directly Measured Agent Team (Compact Single-Row Card)      */
/* -------------------------------------------------------------------------- */

function AgentTeamCard({
  team,
  previousMonthLabel,
  onSelectTeam,
}: {
  team: AgentTeamPerformanceItem;
  previousMonthLabel: string;
  onSelectTeam: (slug: TeamSlug) => void;
}) {
  const gradeStyle = GRADE_STYLES[team.grade];
  const isPositiveCarrier = team.roleTone === 'positive';
  const isUp = team.changeVsPrev >= 0;

  return (
    <button
      type="button"
      data-testid={`agent-team-card-${team.id}`}
      onClick={() => onSelectTeam(team.teamSlug)}
      className={`group relative flex h-full w-full flex-col justify-between overflow-hidden rounded-xl border bg-white p-4 text-left shadow-2xs transition-all duration-150 hover:-translate-y-0.5 hover:shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
        isPositiveCarrier
          ? 'border-emerald-200/90 ring-1 ring-emerald-100/70 hover:border-emerald-300'
          : 'border-amber-300/90 ring-1 ring-amber-100/70 hover:border-amber-400'
      }`}
    >
      {/* Top Accent Bar */}
      <div
        className={`absolute inset-x-0 top-0 h-1 ${
          isPositiveCarrier ? 'bg-emerald-500' : 'bg-amber-500'
        }`}
      />

      <div className="w-full">
        {/* Top Row: Headcount Badge + Role Tag */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1 rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-[10px] font-bold tracking-wide text-slate-600 uppercase">
            <Users className="size-2.5 text-blue-600" />
            {team.headcount} {team.memberUnitLabel ?? 'agents'}
          </span>

          <span
            className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[10px] font-bold ${
              isPositiveCarrier
                ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                : 'border-rose-200 bg-rose-50 text-rose-700'
            }`}
          >
            <span
              className={`size-1.5 rounded-full ${
                isPositiveCarrier ? 'bg-emerald-500' : 'bg-rose-500'
              }`}
            />
            {team.roleTag}
          </span>
        </div>

        {/* Team Title & Subtitle */}
        <div className="mt-2">
          <h3 className="truncate text-base font-bold tracking-tight text-slate-900 transition-colors group-hover:text-blue-600">
            {team.teamName}
          </h3>
        </div>

        {/* Compact Score + Grade + Metrics Strip */}
        <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2.5 rounded-lg border border-slate-100 bg-slate-50/70 px-3 py-2">
          <div className="flex items-baseline gap-2">
            <span
              className={`text-2xl font-extrabold tracking-tight tabular-nums sm:text-3xl ${gradeStyle.scoreText}`}
            >
              {team.score.toFixed(1)}%
            </span>
            <FullWordGradeBadge grade={team.grade} gradeFullLabel={team.gradeLabel} size="sm" />
          </div>

          <div className="flex items-center gap-2.5 text-[11px]">
            <div className="text-right">
              <div className="text-[9px] font-medium text-slate-400">Gap</div>
              <div className="font-bold text-rose-600 tabular-nums">
                {team.gap.toFixed(1)}%
              </div>
            </div>
            <div className="h-5 w-px bg-slate-200" />
            <div className="text-right">
              <div className="text-[9px] font-medium text-slate-400">
                vs {previousMonthLabel.slice(0, 3)}
              </div>
              <div
                className={`inline-flex items-center gap-0.5 font-bold tabular-nums ${
                  isUp ? 'text-emerald-700' : 'text-rose-700'
                }`}
              >
                {isUp ? (
                  <ArrowUpRight className="size-3" />
                ) : (
                  <ArrowDownRight className="size-3" />
                )}
                {isUp ? `+${team.changeVsPrev.toFixed(1)}%` : `${team.changeVsPrev.toFixed(1)}%`}
              </div>
            </div>
          </div>
        </div>

        {/* Short Diagnosis */}
        <div
          className={`mt-2.5 line-clamp-2 w-full rounded-lg border px-2.5 py-1.5 text-[11px] leading-snug ${
            isPositiveCarrier
              ? 'border-emerald-200/60 bg-emerald-50/40 text-slate-700'
              : 'border-amber-200/70 bg-amber-50/40 text-slate-700'
          }`}
          title={team.diagnosis}
        >
          <span className="font-bold text-slate-900">Diagnosis: </span>
          {team.diagnosis}
        </div>
      </div>

      {/* Interactive Footer CTA */}
      <div className="mt-2.5 flex w-full items-center justify-end border-t border-slate-100 pt-2 text-[11px] font-semibold">
        <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-blue-50/70 px-2.5 py-1 text-[11px] font-semibold text-blue-700 transition-[background-color,color,transform] duration-200 group-hover:translate-x-0.5 group-hover:bg-blue-100 group-hover:text-blue-950 motion-reduce:transition-none">
          Open Team
          <ArrowRight className="size-3 shrink-0 transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none" aria-hidden />
        </span>
      </div>
    </button>
  );
}

/* -------------------------------------------------------------------------- */
/*  Layer 2 Card: Support Position Enablement (Compact Card)                  */
/* -------------------------------------------------------------------------- */

function SupportPositionCard({
  position,
  onSelectRole,
}: {
  position: SupportPositionItem;
  onSelectRole?: (roleSlug: string) => void;
}) {
  const impactStyle = IMPACT_LEVEL_STYLES[position.impactLevel];
  const slug = slugifyIdentifier(position.positionName);

  return (
    <button
      type="button"
      data-testid={`support-position-card-${position.id}`}
      onClick={() => onSelectRole?.(slug)}
      className={`group relative flex h-full w-full flex-col justify-between overflow-hidden rounded-xl border bg-slate-50/50 p-3.5 text-left shadow-2xs transition-all hover:-translate-y-0.5 hover:bg-white hover:shadow-xs focus:outline-none focus:ring-2 focus:ring-blue-500 ${impactStyle.cardBorder}`}
    >
      {/* Top Color Bar */}
      <div className={`absolute inset-x-0 top-0 h-1 ${impactStyle.topBar}`} />

      <div>
        {/* Header: Position Name + Impact Pill */}
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <h3 className="truncate text-sm font-bold text-slate-900">
              {position.positionName}
            </h3>
            {position.holderName && (
              <p className="truncate text-[11px] font-medium text-slate-500">
                {position.holderName}
              </p>
            )}
          </div>

          <span
            data-testid={`impact-badge-${position.id}`}
            className={`inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-bold ${impactStyle.badgeBg} ${impactStyle.badgeText} ${impactStyle.badgeBorder}`}
          >
            <span className={`size-1.5 rounded-full ${impactStyle.dotColor}`} />
            {position.impactLevel} Impact
          </span>
        </div>

        {/* Evidence Stat */}
        <p
          className="mt-2 line-clamp-1 rounded-lg border border-slate-200/80 bg-white px-2.5 py-1.5 text-[11px] font-semibold text-slate-700"
          title={position.evidenceStat}
        >
          {position.evidenceStat}
        </p>

        <p
          data-testid={`support-diagnosis-${position.id}`}
          className="mt-2 line-clamp-2 text-[11px] leading-snug text-slate-600"
          title={position.explanation}
        >
          {position.explanation}
        </p>
      </div>

      {/* Linked Agent KPIs + Footer */}
      <div className="mt-2.5 border-t border-slate-200/70 pt-2">
        <div className="flex flex-wrap gap-1">
          {position.linkedKpis.slice(0, 3).map((kpi) => (
            <span
              key={kpi}
              className="inline-flex items-center rounded border border-slate-200 bg-white px-1.5 py-0.5 text-[10px] font-semibold text-slate-700"
            >
              {kpi}
            </span>
          ))}
        </div>
        <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-blue-50/70 px-2.5 py-1 text-[11px] font-semibold text-blue-700 transition-[background-color,color,transform] duration-200 group-hover:translate-x-0.5 group-hover:bg-blue-100 group-hover:text-blue-950 motion-reduce:transition-none">
          Open role detail
          <ArrowRight className="size-3 shrink-0 transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none" aria-hidden />
        </span>
      </div>
    </button>
  );
}

/* -------------------------------------------------------------------------- */
/*  Section 5 Card: Compact Key Agent KPI with Contribution & Biggest Gap     */
/* -------------------------------------------------------------------------- */

function KeyAgentKpiCard({
  kpi,
  weightPct,
  isBiggestGap,
  isTrendOpen,
  onToggleTrend,
}: {
  kpi: AgentKeyKpiItem;
  weightPct: number;
  isBiggestGap: boolean;
  isTrendOpen: boolean;
  onToggleTrend: () => void;
}) {
  const cappedPct = Math.min(
    100,
    Math.max(0, Number.isFinite(kpi.achievementPct) ? kpi.achievementPct : 0),
  );
  const contributionPct = Math.round(((cappedPct / 100) * weightPct) * 10) / 10;
  const pointsLost = Math.max(0, Math.round((weightPct - contributionPct) * 10) / 10);

  const statusBadge =
    cappedPct >= 99.95
      ? 'On Target'
      : cappedPct >= 80
      ? 'Needs Attention'
      : 'Below Target';

  return (
    <SelectableKpiCard
      selected={isTrendOpen}
      status={statusBadge}
      title={kpi.name}
      betterDirection={kpi.betterDirection}
      actual={kpi.actualDisplay}
      target={kpi.targetDisplay}
      achievementPct={cappedPct}
      movement={<KpiTrendMovement label={kpi.trendLabel} betterDirection={kpi.betterDirection} />}
      biggestGap={isBiggestGap}
      weightPct={weightPct}
      contributionPct={contributionPct}
      pointsLost={pointsLost}
      testId={`agent-kpi-card-${kpi.id}`}
      onSelect={onToggleTrend}
      accessory={
        <button
          type="button"
          data-testid={`toggle-kpi-trend-${kpi.id}`}
          onClick={onToggleTrend}
          className="mt-3 inline-flex items-center gap-1 text-[12px] font-medium text-slate-600 hover:text-slate-950"
        >
          <BarChart3 className="size-3.5" aria-hidden />
          6-Mo Trend
          {isTrendOpen ? <ChevronUp className="size-3.5" aria-hidden /> : <ChevronDown className="size-3.5" aria-hidden />}
        </button>
      }
    >
      {isTrendOpen && (
        <div data-testid={`kpi-trend-panel-${kpi.id}`} className="mt-3 rounded-xl bg-slate-50 px-3 py-3">
          <div className="flex items-center justify-between text-[12px] text-slate-600">
            <span className="font-medium text-slate-800">6-Month Actual vs Target ({kpi.shortName})</span>
            <span>{kpi.betterDirection === 'lower' ? 'Target ceiling' : 'Target floor'}</span>
          </div>
          <div className="mt-2.5 grid grid-cols-6 gap-1 text-center">
            {kpi.trend6Mo.map((pt) => (
              <div key={pt.periodKey} className="rounded-lg bg-white px-1 py-1.5">
                <span className="text-[10px] font-medium text-slate-400">{pt.month}</span>
                <span
                  className={`mt-0.5 block text-[11px] font-semibold tabular-nums ${
                    pt.metTarget === true ? 'text-emerald-700' : pt.metTarget === false ? 'text-amber-700' : 'text-slate-500'
                  }`}
                >
                  {pt.actualFormatted}
                </span>
                <span className="text-[9px] text-slate-400 tabular-nums">T: {pt.targetFormatted}</span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[12px] leading-5 text-slate-600">
            <span className="font-medium text-slate-800">Target vs Execution: </span>
            {kpi.targetRealismDiagnosis}
          </p>
        </div>
      )}
    </SelectableKpiCard>
  );
}

/* -------------------------------------------------------------------------- */
/*  Main Call Center Deep Dive View                                           */
/* -------------------------------------------------------------------------- */

export default function CallCenterDeepDiveView({
  data,
  onBackToOverview,
  onSelectAgentTeam,
  onSelectRole,
  toolbar,
}: CallCenterDeepDiveViewProps) {
  const headlineGradeStyle = GRADE_STYLES[data.headline.grade];
  const isPositiveChange = data.headline.changeVsPrev >= 0;
  const [openKpiTrends, setOpenKpiTrends] = useState<Record<string, boolean>>({});
  const [teamsStart, setTeamsStart] = useState(0);
  const [supportStart, setSupportStart] = useState(0);

  const toggleKpiTrend = (id: string) => {
    setOpenKpiTrends((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const sortedTeams = [...data.agentTeams].sort(
    (a, b) => a.score - b.score || a.teamName.localeCompare(b.teamName),
  );
  const maxTeamsStart = Math.max(0, sortedTeams.length - CARDS_PER_ROW);
  const safeTeamsStart = Math.min(teamsStart, maxTeamsStart);
  const visibleTeams = sortedTeams.slice(safeTeamsStart, safeTeamsStart + CARDS_PER_ROW);

  const maxSupportStart = Math.max(0, data.supportPositions.length - CARDS_PER_ROW);
  const safeSupportStart = Math.min(supportStart, maxSupportStart);
  const visibleSupport = data.supportPositions.slice(
    safeSupportStart,
    safeSupportStart + CARDS_PER_ROW,
  );

  return (
    <div
      data-testid="call-center-deep-dive-page"
      className="mx-auto max-w-7xl space-y-7 px-4 py-6 sm:px-6 lg:px-8"
    >
      {/* 1. Header */}
      <header
        aria-label="Call Center Deep Dive Header"
        className="flex min-w-0 flex-col gap-4 rounded-2xl border border-slate-200/90 bg-white p-4 shadow-xs sm:p-5"
      >
        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2.5">
            <button
              type="button"
              data-testid="back-to-monthly-overview"
              onClick={onBackToOverview}
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs font-bold text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-700"
            >
              <ArrowLeft className="size-3.5" />
              <span>Back to Monthly Overview</span>
            </button>

            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-0.5 text-xs font-semibold text-emerald-700">
              <span className="size-1.5 rounded-full bg-emerald-500" />
              {data.regionName}
            </span>

            <span className="inline-flex items-center rounded-full border border-slate-200 bg-slate-50 px-3 py-0.5 text-xs font-semibold text-slate-600">
              {data.pageIndicator}
            </span>
          </div>

          <div className="min-w-0 pt-0.5">
            <h1 className="text-2xl font-bold tracking-tight text-balance text-slate-900 sm:text-[28px]">
              {data.title}
            </h1>
            <p className="mt-1 text-sm font-medium text-slate-500">
              {data.regionName} · {data.monthLabel}
            </p>
          </div>
        </div>

        {toolbar && (
          <div className="flex w-full min-w-0 max-w-full flex-wrap items-center gap-2">{toolbar}</div>
        )}
      </header>

      {/* 2. Diagnostic Headline */}
      <section
        id="presentation-section-cc-score"
        data-section-label="Score"
        aria-labelledby="diagnostic-headline-title"
        className="relative scroll-mt-24 overflow-hidden rounded-2xl border border-slate-200/90 bg-gradient-to-br from-white via-white to-blue-50/40 p-6 shadow-xs sm:p-7"
      >
        <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          {/* Left: Score + Grade + Movement + Gap */}
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-6">
            <div className="flex items-baseline gap-3.5">
              <span
                data-testid="deep-dive-function-score"
                className={`text-5xl font-extrabold tracking-tight sm:text-6xl ${headlineGradeStyle.scoreText}`}
              >
                {data.headline.score.toFixed(1)}%
              </span>
              <FullWordGradeBadge
                grade={data.headline.grade}
                gradeFullLabel={data.headline.gradeLabel}
                size="lg"
              />
            </div>

            <div className="flex flex-wrap items-center gap-2.5 sm:flex-col sm:items-start sm:gap-1.5">
              <span
                className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs font-bold ${
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
                  ? `+${data.headline.changeVsPrev.toFixed(1)}%`
                  : `${data.headline.changeVsPrev.toFixed(1)}%`}{' '}
                vs {data.previousMonthLabel}
              </span>

              <span className="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50/80 px-2.5 py-1 text-xs font-bold text-amber-800">
                <Target className="size-3.5 text-amber-600" />
                {Math.abs(data.headline.gap).toFixed(1)}% below {data.headline.target.toFixed(0)}% target
              </span>
            </div>
          </div>

          {/* Right: Narrative Callout */}
          <div className="max-w-2xl flex-1 rounded-2xl border border-blue-200/80 bg-white/90 p-4 shadow-2xs lg:p-5">
            <div className="flex items-center gap-2 text-xs font-bold tracking-wider text-blue-600 uppercase">
              <Sparkles className="size-3.5" />
              <h2 id="diagnostic-headline-title">Executive Diagnostic</h2>
            </div>
            <p
              data-testid="diagnostic-narrative"
              className="mt-1.5 text-sm font-medium leading-relaxed text-slate-800 sm:text-[15px]"
            >
              {data.headline.narrative}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] font-semibold text-slate-500">
              <span className="rounded-md bg-slate-100 px-2 py-0.5 text-slate-700">
                Layer 1: {data.headline.measuredTeamsCount} teams ({data.headline.measuredAgentsCount} people)
              </span>
              <span>→</span>
              <span className="rounded-md bg-slate-100 px-2 py-0.5 text-slate-700">
                Layer 2: {data.headline.supportPositionsCount} support positions
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* 3. Layer 1 — Directly measured teams (Compact Single-Row Carousel, Worst to Best) */}
      <section
        id="presentation-section-cc-teams"
        data-section-label="Teams"
        aria-labelledby="layer-1-agents-heading"
        className="scroll-mt-24 rounded-2xl border-2 border-blue-100 bg-white p-5 shadow-xs"
      >
        <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-slate-100 pb-3.5">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 rounded-md bg-blue-600 px-2 py-0.5 text-[10px] font-bold tracking-wider text-white uppercase">
                <Layers className="size-3" />
                Layer 1 · Primary Measurement
              </span>
            </div>
            <h2
              id="layer-1-agents-heading"
              className="mt-1 text-base font-bold text-slate-900 sm:text-lg"
            >
              {data.functionSlug === 'call-center'
                ? 'Agent Performance — Directly Measured Teams'
                : 'Directly Measured Teams'}
            </h2>
          </div>

          {sortedTeams.length > CARDS_PER_ROW && (
            <div
              data-testid="agent-teams-carousel"
              className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-2 py-1 shadow-2xs"
            >
              <span className="px-1 text-[11px] font-bold text-slate-500 tabular-nums">
                {safeTeamsStart + 1}–
                {Math.min(sortedTeams.length, safeTeamsStart + CARDS_PER_ROW)} of{' '}
                {sortedTeams.length}
              </span>
              <button
                type="button"
                aria-label="Previous teams"
                disabled={safeTeamsStart === 0}
                onClick={() => setTeamsStart((prev) => Math.max(0, prev - 1))}
                className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-35"
              >
                <ChevronLeft className="size-3.5" aria-hidden />
              </button>
              <button
                type="button"
                aria-label="Next teams"
                disabled={safeTeamsStart >= maxTeamsStart}
                onClick={() =>
                  setTeamsStart((prev) => Math.min(maxTeamsStart, prev + 1))
                }
                className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-35"
              >
                <ChevronRight className="size-3.5" aria-hidden />
              </button>
            </div>
          )}
        </div>

        <div
          className={`mt-4 grid grid-cols-1 gap-3.5 ${
            sortedTeams.length <= 2
              ? 'lg:grid-cols-2'
              : sortedTeams.length === 3
              ? 'lg:grid-cols-3'
              : 'sm:grid-cols-2 lg:grid-cols-4'
          }`}
        >
          {visibleTeams.map((team) => (
            <AgentTeamCard
              key={team.id}
              team={team}
              previousMonthLabel={data.previousMonthLabel}
              onSelectTeam={onSelectAgentTeam}
            />
          ))}
        </div>
      </section>

      {/* 4. Layer 2 — Support Positions (Compact Single-Row Carousel) */}
      <section
        id="presentation-section-cc-support"
        data-section-label="Support"
        aria-labelledby="layer-2-support-heading"
        className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-5 shadow-xs"
      >
        <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-slate-100 pb-3.5">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-slate-100 px-2 py-0.5 text-[10px] font-bold tracking-wider text-slate-700 uppercase">
                <ShieldCheck className="size-3 text-slate-600" />
                Layer 2 · Enablement & Governance
              </span>
              <span className="text-xs font-medium text-slate-500">
                Evaluated by linkage to Agent KPIs
              </span>
            </div>
            <h2
              id="layer-2-support-heading"
              className="mt-1 text-base font-bold text-slate-900 sm:text-lg"
            >
              Support Positions — Impact on Agent Results
            </h2>
          </div>

          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
              <span className="size-1.5 rounded-full bg-emerald-500" /> Strong
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-700">
              <span className="size-1.5 rounded-full bg-amber-500" /> Partial / Mixed
            </span>
            <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2 py-0.5 text-[11px] font-semibold text-rose-700">
              <span className="size-1.5 rounded-full bg-rose-500" /> Limited
            </span>

            {data.supportPositions.length > CARDS_PER_ROW && (
              <div className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-white px-2 py-1 shadow-2xs">
                <span className="px-1 text-[11px] font-bold text-slate-500 tabular-nums">
                  {safeSupportStart + 1}–
                  {Math.min(
                    data.supportPositions.length,
                    safeSupportStart + CARDS_PER_ROW,
                  )}{' '}
                  of {data.supportPositions.length}
                </span>
                <button
                  type="button"
                  aria-label="Previous support positions"
                  disabled={safeSupportStart === 0}
                  onClick={() => setSupportStart((prev) => Math.max(0, prev - 1))}
                  className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-35"
                >
                  <ChevronLeft className="size-3.5" aria-hidden />
                </button>
                <button
                  type="button"
                  aria-label="Next support positions"
                  disabled={safeSupportStart >= maxSupportStart}
                  onClick={() =>
                    setSupportStart((prev) => Math.min(maxSupportStart, prev + 1))
                  }
                  className="inline-flex size-6 items-center justify-center rounded-lg border border-slate-200 bg-slate-50 text-slate-700 transition-colors hover:border-blue-300 hover:bg-blue-50 hover:text-blue-600 disabled:cursor-not-allowed disabled:opacity-35"
                >
                  <ChevronRight className="size-3.5" aria-hidden />
                </button>
              </div>
            )}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {visibleSupport.map((pos) => (
            <SupportPositionCard key={pos.id} position={pos} onSelectRole={onSelectRole} />
          ))}
        </div>
      </section>

      {/* 5. Key Function KPIs (Compact Single-Row Cards, Sorted Worst to Best) */}
      <section id="presentation-section-cc-kpis" data-section-label="KPIs" aria-labelledby="key-agent-kpis-heading" className="scroll-mt-24 space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 px-1">
          <div>
            <span className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
              Operational Drivers
            </span>
            <h2 id="key-agent-kpis-heading" className="mt-0.5 text-base font-bold text-slate-900 sm:text-lg">
              Key Agent KPIs
            </h2>
          </div>
        </div>

        <div
          className={`grid grid-cols-1 gap-3.5 ${
            data.keyKpis.length >= 4
              ? 'sm:grid-cols-2 lg:grid-cols-4'
              : 'lg:grid-cols-3'
          }`}
        >
          {(() => {
            const count = data.keyKpis.length;
            const weights =
              count === 1
                ? [100]
                : count === 2
                ? [50, 50]
                : count === 3
                ? [40, 30, 30]
                : [30, 30, 20, 20];
            const enriched = data.keyKpis.map((kpi, idx) => {
              const w = weights[idx] ?? Math.round(100 / Math.max(1, count));
              const capped = Math.min(100, Math.max(0, kpi.achievementPct || 0));
              const lost = w - (capped / 100) * w;
              return { kpi, w, lost };
            });
            enriched.sort(
              (a, b) =>
                (a.kpi.achievementPct || 0) - (b.kpi.achievementPct || 0) ||
                b.lost - a.lost,
            );
            let maxLost = 0;
            let maxIdx = -1;
            enriched.forEach((item, idx) => {
              if (item.lost > maxLost) {
                maxLost = item.lost;
                maxIdx = idx;
              }
            });
            return enriched.map((item, idx) => (
              <KeyAgentKpiCard
                key={item.kpi.id}
                kpi={item.kpi}
                weightPct={item.w}
                isBiggestGap={idx === maxIdx && maxLost > 0.1}
                isTrendOpen={Boolean(openKpiTrends[item.kpi.id])}
                onToggleTrend={() => toggleKpiTrend(item.kpi.id)}
              />
            ));
          })()}
        </div>
      </section>

      {/* 6. Bottom Split: Agents Needing Attention & Actions by Position */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left Column: Agents Needing Attention */}
        <section
          id="presentation-section-cc-attention"
          data-section-label="Attention"
          aria-labelledby="agents-needing-attention-heading"
          className="flex scroll-mt-24 flex-col justify-between rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs lg:col-span-6"
        >
          <div>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-4">
              <div>
                <span className="text-xs font-semibold tracking-wider text-rose-600 uppercase">
                  Targeted Coaching Roster
                </span>
                <h2
                  id="agents-needing-attention-heading"
                  className="mt-0.5 text-lg font-bold text-slate-900"
                >
                  Agents Needing Attention
                </h2>
              </div>
              <span className="rounded-full border border-rose-200 bg-rose-50 px-3 py-0.5 text-xs font-bold text-rose-700">
                {data.agentsNeedingAttention.length} priority agents
              </span>
            </div>

            <div className="mt-4 divide-y divide-slate-100">
              {data.agentsNeedingAttention.map((agent: AgentNeedingAttentionItem) => {
                const ownerStyle = positionBadge(agent.owningPosition);
                const gradeStyle = GRADE_STYLES[agent.grade];
                return (
                  <div
                    key={agent.id}
                    data-testid={`attention-agent-${agent.id}`}
                    className="flex flex-col gap-2 py-3.5 first:pt-1 last:pb-1"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        <span className="text-sm font-bold text-slate-900">
                          {agent.agentName}
                        </span>
                        <button
                          type="button"
                          onClick={() => onSelectAgentTeam(agent.teamSlug)}
                          className="rounded-md bg-slate-100 px-2 py-0.5 text-[11px] font-semibold text-slate-700 hover:bg-blue-50 hover:text-blue-700 transition-colors"
                        >
                          {agent.team} →
                        </button>
                      </div>

                      <div className="flex items-center gap-2">
                        <span className={`text-sm font-extrabold ${gradeStyle.scoreText}`}>
                          {agent.score.toFixed(1)}%
                        </span>
                        <FullWordGradeBadge grade={agent.grade} gradeFullLabel={agent.gradeLabel} size="sm" />
                      </div>
                    </div>

                    <div className="flex flex-col justify-between gap-2 sm:flex-row sm:items-center">
                      <p className="text-xs text-slate-600">
                        <AlertCircle className="mr-1 inline size-3.5 text-rose-500" />
                        {agent.reason}
                      </p>

                      <span
                        className={`inline-flex shrink-0 items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-bold ${ownerStyle.bg} ${ownerStyle.text} ${ownerStyle.border}`}
                      >
                        <UserCheck className="size-3" />
                        Owner: {agent.owningPosition}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>


        </section>

        <section
          id="presentation-section-cc-actions"
          data-section-label="Actions"
          aria-labelledby="actions-by-position-heading"
          className="flex scroll-mt-24 flex-col justify-between rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs lg:col-span-6"
        >
          <div>
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 pb-4">
              <div>
                <span className="text-xs font-semibold tracking-wider text-emerald-600 uppercase">
                  Accountability & Next-Month Lift
                </span>
                <h2
                  id="actions-by-position-heading"
                  className="mt-0.5 text-lg font-bold text-slate-900"
                >
                  Actions by Position
                </h2>
              </div>
              <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-0.5 text-xs font-bold text-emerald-700">
                <TrendingUp className="size-3.5" />
                +{data.actionsByPosition.totalExpectedLiftPct.toFixed(1)}% expected lift
              </span>
            </div>

            <div className="mt-4 space-y-3">
              {data.actionsByPosition.items.map((item: PositionActionPlanItem) => {
                const ownerStyle = positionBadge(item.owningPosition);
                return (
                  <div
                    key={item.id}
                    data-testid={`position-action-${item.id}`}
                    className="rounded-xl border border-slate-200/80 bg-slate-50/60 p-3.5 transition-colors hover:bg-white"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span
                        className={`inline-flex items-center gap-1 rounded-md border px-2.5 py-0.5 text-xs font-bold ${ownerStyle.bg} ${ownerStyle.text} ${ownerStyle.border}`}
                      >
                        {item.owningPosition}
                      </span>

                      <span className="inline-flex items-center gap-1 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-xs font-extrabold text-emerald-700">
                        +{item.expectedImpactPct.toFixed(1)}% next month
                      </span>
                    </div>

                    <p
                      data-testid={`action-diagnosis-${item.id}`}
                      title={item.actionTitle}
                      className="mt-2 line-clamp-2 text-xs font-bold leading-snug text-slate-900 sm:text-sm"
                    >
                      {item.actionTitle}
                    </p>

                    <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-500">
                      <span className="font-medium text-slate-600">
                        Target: {item.targetScope}
                      </span>
                      <span
                        title={item.expectedKpiOutcome}
                        className="inline-flex min-w-0 items-center gap-1 font-semibold text-emerald-700"
                      >
                        <CheckCircle2 className="size-3 shrink-0" />
                        <span className="line-clamp-2">{item.expectedKpiOutcome}</span>
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Projected Next Month Score Footer */}
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50/70 px-4 py-3">
            <div className="flex items-center gap-2 text-xs font-semibold text-emerald-900">
              <Activity className="size-4 text-emerald-600" />
              <span>Projected next-month score</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-medium text-emerald-700">
                {data.headline.score.toFixed(1)}% →
              </span>
              <span
                data-testid="projected-next-month-score"
                className="rounded-lg bg-emerald-600 px-2.5 py-1 text-sm font-extrabold text-white"
              >
                {data.actionsByPosition.projectedNextMonthScore.toFixed(1)}%
              </span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
