import { useState, type ReactNode } from 'react';
import {
  ArrowDownRight,
  ArrowLeft,
  ArrowUpRight,
  BarChart3,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Sparkles,
  Target,
  TrendingUp,
  UserCheck,
} from 'lucide-react';
import { GRADE_STYLES } from '../monthlyOverviewData';
import type {
  AgentKeyKpiItem,
  CallCenterDeepDiveData,
  PositionActionPlanItem,
} from '../callCenterDeepDiveData';
import type { FunctionRoleCard } from '../roleDetailData';
import FunctionRoleBoard from './FunctionRoleBoard';
import { KpiTrendMovement, SelectableKpiCard } from './SelectableKpiCard';
import { showActionSection } from '../presentationMode';
import { FullWordGradeBadge } from './TeamDeepDiveView';

export interface FunctionDeepDiveViewProps {
  data: CallCenterDeepDiveData;
  roles: FunctionRoleCard[];
  onBackToOverview: () => void;
  onSelectRole: (roleSlug: string) => void;
  toolbar?: ReactNode;
  presentationMode?: boolean;
}

function gapCopy(gap: number, target: number): string {
  if (gap < 0) return `${Math.abs(gap).toFixed(1)}% below ${target.toFixed(0)}% target`;
  if (gap > 0) return `${gap.toFixed(1)}% above ${target.toFixed(0)}% target`;
  return `On the ${target.toFixed(0)}% target`;
}

/* -------------------------------------------------------------------------- */
/*  Section 4 Card: Structured Key Function KPI Card                          */
/* -------------------------------------------------------------------------- */

function FunctionKpiCard({
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
  const cappedPct = Math.min(100, Math.max(0, Number.isFinite(kpi.achievementPct) ? kpi.achievementPct : 0));
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
      testId={`function-kpi-card-${kpi.id}`}
      onSelect={onToggleTrend}
      accessory={
        kpi.trend6Mo.length > 0 ? (
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
        ) : null
      }
    >
      {isTrendOpen && kpi.trend6Mo.length > 0 && (
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
/*  Section 5 Card: Priority Action Card (Prototype Style)                    */
/* -------------------------------------------------------------------------- */

function ActionCard({ item }: { item: PositionActionPlanItem }) {
  return (
    <article
      data-testid={`position-action-${item.id}`}
      className="flex flex-col justify-between rounded-2xl border border-slate-200/90 bg-slate-50/50 p-5 shadow-2xs transition-all hover:border-slate-300 hover:bg-white hover:shadow-xs"
    >
      <div>
        {/* Top Row: Owner Badge + Expected Lift Pill */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 rounded-lg border border-blue-200/80 bg-blue-50/80 px-2.5 py-1 text-xs font-bold text-blue-800">
            <UserCheck className="size-3.5 text-blue-600" aria-hidden />
            Owner: {item.owningPosition}
          </span>

          <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-0.5 text-xs font-extrabold text-emerald-700 tabular-nums">
            <TrendingUp className="size-3" aria-hidden />+{item.expectedImpactPct.toFixed(1)}%
            expected lift
          </span>
        </div>

        {/* Action Title */}
        <h3
          data-testid={`action-diagnosis-${item.id}`}
          title={item.actionTitle}
          className="mt-3.5 line-clamp-2 text-sm font-bold leading-snug text-slate-900"
        >
          {item.actionTitle}
        </h3>
      </div>

      {/* Affected KPI & Expected Outcome Footer */}
      <dl className="mt-4 grid grid-cols-1 gap-2.5 border-t border-slate-200/80 pt-3.5 text-xs sm:grid-cols-2">
        <div className="rounded-lg border border-slate-200/70 bg-white px-3 py-2">
          <dt className="text-[10px] font-bold tracking-wider text-slate-400 uppercase">
            KPI Affected
          </dt>
          <dd className="mt-0.5 font-semibold text-slate-800">{item.targetScope}</dd>
        </div>

        <div className="rounded-lg border border-emerald-200/60 bg-emerald-50/40 px-3 py-2">
          <dt className="text-[10px] font-bold tracking-wider text-emerald-700 uppercase">
            Expected Outcome
          </dt>
          <dd className="mt-0.5 inline-flex items-center gap-1 font-semibold text-emerald-800">
            <CheckCircle2 className="size-3.5 shrink-0 text-emerald-600" aria-hidden />
            <span title={item.expectedKpiOutcome} className="line-clamp-2">
              {item.expectedKpiOutcome}
            </span>
          </dd>
        </div>
      </dl>
    </article>
  );
}

/* -------------------------------------------------------------------------- */
/*  Main Function Deep Dive View (Role-Based Functions)                       */
/* -------------------------------------------------------------------------- */

export default function FunctionDeepDiveView({
  data,
  roles,
  onBackToOverview,
  onSelectRole,
  toolbar,
  presentationMode = false,
}: FunctionDeepDiveViewProps) {
  const gradeStyle = GRADE_STYLES[data.headline.grade];
  const up = data.headline.changeVsPrev >= 0;
  const [openKpiTrends, setOpenKpiTrends] = useState<Record<string, boolean>>({});

  const draggingCount = roles.filter((r) => r.score < 90).length;
  const carryingCount = roles.filter((r) => r.score >= 90).length;

  const toggleKpiTrend = (id: string) => {
    setOpenKpiTrends((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  return (
    <div
      data-testid="function-deep-dive-page"
      className="mx-auto max-w-7xl space-y-7 px-4 py-6 sm:px-6 lg:px-8"
    >
      {/* 1. Header Card */}
      <header
        aria-label={`${data.functionName} Deep Dive Header`}
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
              <ArrowLeft className="size-3.5" aria-hidden />
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

        {toolbar ? (
          <div className="flex w-full min-w-0 max-w-full flex-wrap items-center gap-2">{toolbar}</div>
        ) : null}
      </header>

      {/* 2. Diagnostic Headline Card (Dominant Score + Narrative Balance) */}
      <section
        id="presentation-section-function-score"
        data-section-label="Score"
        aria-labelledby="function-diagnostic-heading"
        className="relative scroll-mt-24 overflow-hidden rounded-2xl border border-slate-200/90 bg-gradient-to-br from-white via-white to-blue-50/40 p-6 shadow-xs sm:p-7"
      >
        <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
          {/* Left: Dominant Score + Full-Word Grade + Movement + Gap */}
          <div className="flex flex-col gap-3.5 sm:flex-row sm:items-center sm:gap-6">
            <div>
              <div className="text-[11px] font-bold tracking-wider text-slate-400 uppercase">
                Function Score
              </div>
              <div className="mt-1 flex items-baseline gap-3.5">
                <p
                  data-testid="deep-dive-function-score"
                  className={`text-5xl font-extrabold tracking-tight tabular-nums sm:text-6xl ${gradeStyle.scoreText}`}
                >
                  {data.headline.score.toFixed(1)}%
                </p>
                <FullWordGradeBadge
                  grade={data.headline.grade}
                  gradeFullLabel={data.headline.gradeLabel}
                  size="lg"
                />
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2.5 sm:flex-col sm:items-start sm:gap-1.5">
              <span
                className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs font-bold tabular-nums ${
                  up
                    ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                    : 'border-rose-200 bg-rose-50 text-rose-700'
                }`}
              >
                {up ? (
                  <ArrowUpRight className="size-3.5" aria-hidden />
                ) : (
                  <ArrowDownRight className="size-3.5" aria-hidden />
                )}
                {up ? '+' : ''}
                {data.headline.changeVsPrev.toFixed(1)}% vs {data.previousMonthLabel}
              </span>

              <span className="inline-flex items-center gap-1.5 rounded-lg border border-amber-200 bg-amber-50/80 px-2.5 py-1 text-xs font-bold text-amber-800">
                <Target className="size-3.5 text-amber-600" aria-hidden />
                {gapCopy(data.headline.gap, data.headline.target)}
              </span>
            </div>
          </div>

          {/* Right: Executive Narrative Box */}
          <div className="max-w-2xl flex-1 rounded-2xl border border-blue-200/80 bg-white/95 p-4 shadow-2xs lg:p-5">
            <div className="flex items-center gap-2 text-xs font-bold tracking-wider text-blue-600 uppercase">
              <Sparkles className="size-3.5" aria-hidden />
              <h2 id="function-diagnostic-heading">Executive Diagnostic</h2>
            </div>
            <p
              data-testid="diagnostic-narrative"
              className="mt-1.5 text-sm font-medium leading-relaxed text-slate-800 sm:text-[15px]"
            >
              {data.headline.narrative}
            </p>
            <div className="mt-3.5 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3 text-[11px] font-semibold text-slate-600">
              <span className="inline-flex items-center gap-1.5 rounded-md border border-rose-200/80 bg-rose-50/70 px-2.5 py-0.5 text-rose-800">
                <span className="size-1.5 rounded-full bg-rose-500" />
                {draggingCount} {draggingCount === 1 ? 'role' : 'roles'} dragging (&lt; 90%)
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-md border border-emerald-200/80 bg-emerald-50/70 px-2.5 py-0.5 text-emerald-800">
                <span className="size-1.5 rounded-full bg-emerald-500" />
                {carryingCount} {carryingCount === 1 ? 'role' : 'roles'} carrying (≥ 90%)
              </span>
              <span className="ml-auto text-slate-400">
                {roles.length} evaluated {roles.length === 1 ? 'role' : 'roles'}
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* 3. Roles Dragging vs Roles Carrying Performance */}
      <FunctionRoleBoard
        roles={roles}
        previousMonthLabel={data.previousMonthLabel}
        onSelectRole={onSelectRole}
      />

      {/* 4. Key Function KPIs (Structured Card Group) */}
      <section id="presentation-section-function-kpis" data-section-label="KPIs" aria-labelledby="function-kpis-heading" className="scroll-mt-24 space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-2 px-1">
          <div>
            <span className="text-xs font-semibold tracking-wider text-slate-400 uppercase">
              Operational Drivers
            </span>
            <h2
              id="function-kpis-heading"
              className="mt-0.5 text-lg font-bold tracking-tight text-slate-900 sm:text-xl"
            >
              Key Function KPIs
            </h2>
          </div>
        </div>

        {data.keyKpis.length ? (
          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
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
                const w = weights[idx] ?? Math.round(100 / count);
                const capped = Math.min(100, Math.max(0, kpi.achievementPct || 0));
                const lost = w - (capped / 100) * w;
                return { kpi, w, lost };
              });
              enriched.sort(
                (a, b) =>
                  (a.kpi.achievementPct || 0) - (b.kpi.achievementPct || 0) ||
                  b.lost - a.lost
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
                <FunctionKpiCard
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
        ) : (
          <div className="rounded-2xl border border-slate-200/80 bg-white p-6 text-sm text-slate-600">
            No function KPIs available for this month.
          </div>
        )}
      </section>

      {/* 5. Priority Actions (Prototype Card Style with Overall Expected Impact) */}
      {showActionSection(data.actionsByPosition.items.length, presentationMode) && (
      <section
        id="presentation-section-function-actions"
        data-section-label="Actions"
        aria-labelledby="function-actions-heading"
        className="scroll-mt-24 rounded-2xl border border-slate-200/90 bg-white p-6 shadow-xs sm:p-7"
      >
        <div className="flex flex-col gap-3 border-b border-slate-100 pb-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <span className="text-xs font-semibold tracking-wider text-emerald-600 uppercase">
              Accountability & Next-Month Lift
            </span>
            <h2
              id="function-actions-heading"
              className="mt-0.5 text-lg font-bold tracking-tight text-slate-900 sm:text-xl"
            >
              Priority Actions
            </h2>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3.5 py-1 text-xs font-bold text-emerald-700 tabular-nums">
              <TrendingUp className="size-3.5" aria-hidden />+
              {data.actionsByPosition.totalExpectedLiftPct.toFixed(1)}% expected lift
            </span>
            <span className="inline-flex items-center gap-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-bold text-slate-700 tabular-nums">
              <span>Projected next month:</span>
              <span className="text-emerald-700">
                {data.headline.score.toFixed(1)}% →{' '}
                {data.actionsByPosition.projectedNextMonthScore.toFixed(1)}%
              </span>
            </span>
          </div>
        </div>

        {data.actionsByPosition.items.length ? (
          <div className="mt-5 grid grid-cols-1 gap-4 lg:grid-cols-2">
            {data.actionsByPosition.items.map((item) => (
              <ActionCard key={item.id} item={item} />
            ))}
          </div>
        ) : (
          <p className="mt-5 text-sm text-slate-600">
            No priority actions recorded for this month.
          </p>
        )}
      </section>
      )}
    </div>
  );
}
