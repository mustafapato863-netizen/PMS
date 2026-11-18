import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  ChevronDown,
  ChevronUp,
  Lightbulb,
  ShieldAlert,
  Target,
  TrendingUp,
} from 'lucide-react';
import { LineChart } from '../../balanced-scorecard/LineChart';
import {
  GRADE_STYLES,
  gradeForScore,
  type GradeLetter,
} from '../../../features/monthlyPresentation/monthlyOverviewData';
import type { StructuredVisualCard } from '../../../features/ai/types';
import { formatManagerReadableText } from './responseFormatting';

const MAX_INLINE_ITEMS = 5;

const MONTH_NAME_TO_NUMBER: Record<string, string> = {
  january: '1',
  february: '2',
  march: '3',
  april: '4',
  may: '5',
  june: '6',
  july: '7',
  august: '8',
  september: '9',
  october: '10',
  november: '11',
  december: '12',
};

const SEVERITY_DOT_CLASSES: Record<string, string> = {
  critical: 'bg-rose-500 ring-2 ring-rose-500/20',
  warning: 'bg-amber-500 ring-2 ring-amber-500/20',
  good: 'bg-emerald-500 ring-2 ring-emerald-500/20',
  info: 'bg-sky-500 ring-2 ring-sky-500/20',
  neutral: 'bg-slate-400',
};

const SEVERITY_BADGE_CLASSES: Record<string, string> = {
  critical: 'border border-rose-200 bg-rose-50 text-rose-700',
  warning: 'border border-amber-200 bg-amber-50 text-amber-800',
  good: 'border border-emerald-200 bg-emerald-50 text-emerald-700',
  info: 'border border-sky-200 bg-sky-50 text-sky-700',
  neutral: 'border border-slate-200 bg-slate-100 text-slate-700',
};

const BAR_GRADIENT_CLASSES: Record<string, string> = {
  critical: 'from-rose-500 via-orange-500 to-amber-400',
  warning: 'from-amber-500 via-amber-400 to-yellow-400',
  good: 'from-emerald-600 via-emerald-500 to-teal-400',
  neutral: 'from-blue-600 via-sky-500 to-cyan-400',
};

const PRIORITY_BADGE_CLASSES: Record<string, string> = {
  immediate: 'border border-rose-200 bg-rose-50 text-rose-700',
  high: 'border border-amber-200 bg-amber-50 text-amber-800',
  coaching: 'border border-sky-200 bg-sky-50 text-sky-700',
  strategic: 'border border-emerald-200 bg-emerald-50 text-emerald-700',
};

interface VisualEvidenceCardProps {
  card: StructuredVisualCard;
}

export default function VisualEvidenceCard({ card }: VisualEvidenceCardProps) {
  const [showAllRows, setShowAllRows] = useState(false);

  if (card.card_type === 'guardrail_notice') {
    return (
      <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50/80 p-3.5 text-sm text-slate-900">
        <div className="flex items-center gap-2 text-sm font-bold text-amber-900">
          <ShieldAlert size={15} className="shrink-0 text-amber-600" />
          <span>{card.title}</span>
        </div>
        {card.notice_text && (
          <p className="mt-1 text-sm leading-relaxed text-slate-700">{card.notice_text}</p>
        )}
      </div>
    );
  }

  /* ------------------------------------------------------------------------ */
  /*  Agent / Team Spotlight & Multi-Month Score Trend Card                   */
  /* ------------------------------------------------------------------------ */
  if (card.card_type === 'trend_spotlight' && card.spotlight) {
    const sp = card.spotlight;
    const grade = (sp.grade in GRADE_STYLES ? sp.grade : gradeForScore(sp.score)) as GradeLetter;
    const gradeStyle = GRADE_STYLES[grade];
    const hasPrevChange = sp.change_vs_prev !== null && sp.change_vs_prev !== undefined;
    const isPositiveChange = (sp.change_vs_prev ?? 0) >= 0;
    const formattedChange = hasPrevChange
      ? `${isPositiveChange ? '+' : ''}${sp.change_vs_prev!.toFixed(1)} pts`
      : null;

    const chartHistory = sp.trend_points.map((pt) => {
      const mNorm = pt.month.trim().toLowerCase();
      return {
        month: MONTH_NAME_TO_NUMBER[mNorm] || pt.month,
        year: pt.year || 2026,
        score: pt.score,
      };
    });

    const firstPoint = sp.trend_points[0];
    const sixMoDelta = sp.six_month_delta ?? 0;

    return (
      <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200/90 bg-slate-50/40 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="inline-block rounded-md bg-blue-50 px-2 py-0.5 text-xs font-bold uppercase tracking-wider text-blue-800">
                {sp.kicker}
              </span>
              {sp.rank_label && (
                <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-xs font-bold text-emerald-700">
                  {sp.rank_label}
                </span>
              )}
            </div>
            <h3 className="mt-1 text-base font-extrabold text-slate-900">
              {sp.entity_name}
              {sp.entity_id ? (
                <span className="ml-1.5 text-xs font-semibold text-slate-400">
                  ({sp.entity_id})
                </span>
              ) : null}
            </h3>
          </div>

          <div className="flex items-center gap-2.5">
            <span
              className={`text-2xl font-extrabold tracking-tight tabular-nums sm:text-3xl ${gradeStyle.scoreText}`}
            >
              {sp.score.toFixed(1)}%
            </span>
            <div className="flex flex-col items-end gap-1">
              <span
                className={`inline-flex items-center justify-center rounded-lg border px-2 py-0.5 text-xs font-extrabold ${gradeStyle.badgeBg} ${gradeStyle.badgeText} ${gradeStyle.badgeBorder}`}
              >
                Grade {grade}
              </span>
              {formattedChange && (
                <span
                  className={`inline-flex items-center gap-0.5 rounded-lg border px-2 py-0.5 text-xs font-bold ${
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
                  {formattedChange} vs {sp.previous_month_label.slice(0, 3)}
                </span>
              )}
            </div>
          </div>
        </div>

        {sp.tiles.length > 0 && (
          <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-3">
            {sp.tiles.map((tile, idx) => {
              const tileToneClass =
                tile.tone === 'good'
                  ? 'border-emerald-200/80 bg-emerald-50/40 text-emerald-950'
                  : tile.tone === 'warning'
                    ? 'border-amber-200/80 bg-amber-50/40 text-amber-950'
                    : tile.tone === 'critical'
                      ? 'border-rose-200/80 bg-rose-50/40 text-rose-950'
                      : 'border-slate-200/80 bg-white text-slate-900';
              return (
                <div
                  key={`${tile.label}-${idx}`}
                  className={`rounded-xl border px-3 py-2 ${tileToneClass}`}
                >
                  <div className="text-xs font-semibold text-slate-500">{tile.label}</div>
                  <div className="mt-0.5 text-base font-extrabold tabular-nums">{tile.value}</div>
                  {tile.sublabel && (
                    <div className="truncate text-xs font-medium text-slate-500">
                      {formatManagerReadableText(tile.sublabel)}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {chartHistory.length > 0 && (
          <div className="mt-3 rounded-xl border border-slate-200/85 bg-white p-3.5">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-sm font-bold text-slate-900">
                {chartHistory.length}-Month Score Trend
              </span>

              <div className="flex items-center gap-2.5 text-xs font-semibold text-slate-500">
                <span className="inline-flex items-center gap-1">
                  <span className="h-0.5 w-3 border-t-2 border-dashed border-emerald-600" />
                  Target {(sp.target || 100).toFixed(0)}%
                </span>
                {firstPoint && chartHistory.length >= 2 && (
                  <span
                    className={`rounded-md px-2 py-0.5 text-xs font-bold ${
                      sixMoDelta >= 0
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-rose-50 text-rose-700'
                    }`}
                  >
                    {sixMoDelta >= 0 ? `+${sixMoDelta.toFixed(1)} pts` : `${sixMoDelta.toFixed(1)} pts`}{' '}
                    since {firstPoint.month.slice(0, 3)}
                  </span>
                )}
              </div>
            </div>

            <div className="mt-1.5">
              <LineChart
                history={chartHistory}
                targetValue={sp.target || 100}
                height={136}
                showTarget
              />
            </div>
          </div>
        )}

        {sp.kpi_chips.length > 0 && (
          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
            {sp.kpi_chips.map((chip, idx) => {
              const ach = chip.achievement_percent ?? 100;
              const chipGrade = gradeForScore(ach);
              const chipStyle = GRADE_STYLES[chipGrade];
              return (
                <div
                  key={`${chip.kpi_key}-${idx}`}
                  className="rounded-xl border border-slate-200/80 bg-white px-2.5 py-2"
                >
                  <div
                    className="truncate text-xs font-semibold text-slate-600"
                    title={chip.kpi_label}
                  >
                    {chip.kpi_label.replace(' (Patient Attended / Bookings)', '')}
                  </div>
                  <div className="mt-1 flex items-baseline justify-between gap-1">
                    <span className="text-sm font-extrabold tabular-nums text-slate-900">
                      {chip.actual_display}
                    </span>
                    <span className={`text-xs font-bold tabular-nums ${chipStyle.scoreText}`}>
                      {ach.toFixed(0)}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {card.items && card.items.length > 0 && (
          <div className="mt-3 space-y-2 border-t border-slate-200/80 pt-3">
            {card.items.map((item, idx) => (
              <div
                key={`${item.id}-${idx}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-slate-200/80 bg-white px-3 py-2 text-sm"
              >
                <div className="min-w-0">
                  <span className="font-bold text-slate-900">{item.title}</span>
                  {item.subtitle && (
                    <span className="ml-2 text-xs text-slate-500">
                      {formatManagerReadableText(item.subtitle)}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {item.badge_text && (
                    <span className="rounded-md border border-slate-200 bg-slate-50 px-2 py-0.5 text-xs font-bold text-slate-700">
                      {item.badge_text}
                    </span>
                  )}
                  {item.route_link && (
                    <Link
                      to={item.route_link}
                      className="text-xs font-bold text-blue-600 hover:underline"
                    >
                      Inspect →
                    </Link>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  /* ------------------------------------------------------------------------ */
  /*  Horizontal Bar Comparison Card (Top 5 inline + progressive disclosure)  */
  /* ------------------------------------------------------------------------ */
  if (card.card_type === 'horizontal_bar' && card.bars.length > 0) {
    const maxVal = Math.max(
      ...card.bars.map((b) => (b.value === null ? 1 : Math.max(b.value, 1))),
      100,
    );
    const hasMore = card.bars.length > MAX_INLINE_ITEMS;
    const displayedBars = showAllRows ? card.bars : card.bars.slice(0, MAX_INLINE_ITEMS);

    return (
      <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200/90 bg-slate-50/50 p-3.5">
        <div className="mb-2.5 flex items-baseline justify-between gap-2">
          <div>
            <p className="text-sm font-bold text-slate-900">{card.title}</p>
            {card.subtitle && (
              <p className="text-xs font-medium text-slate-500">{card.subtitle}</p>
            )}
          </div>
        </div>
        <div className="space-y-2">
          {displayedBars.map((bar, idx) => {
            const widthPct =
              bar.value === null
                ? 0
                : Math.max(8, Math.min(100, Math.round((bar.value / maxVal) * 100)));
            const grad = BAR_GRADIENT_CLASSES[bar.severity] || BAR_GRADIENT_CLASSES.neutral;
            const badgeStyle =
              SEVERITY_BADGE_CLASSES[bar.severity] || SEVERITY_BADGE_CLASSES.neutral;
            return (
              <div
                key={`${bar.label}-${idx}`}
                className="rounded-xl border border-slate-200/80 bg-white px-3 py-2.5"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                  <span className="font-semibold text-slate-900">{bar.label}</span>
                  <div className="flex items-center gap-2">
                    {bar.secondary_label && (
                      <span className="text-xs font-medium text-slate-500">
                        {formatManagerReadableText(bar.secondary_label)}
                      </span>
                    )}
                    <span
                      className={`rounded-md px-2 py-0.5 text-xs font-bold tabular-nums ${badgeStyle}`}
                    >
                      {bar.display_value}
                    </span>
                  </div>
                </div>
                <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full bg-gradient-to-r ${grad} transition-all duration-300`}
                    style={{ width: `${widthPct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
        {hasMore && (
          <button
            type="button"
            onClick={() => setShowAllRows((prev) => !prev)}
            className="mt-2.5 inline-flex items-center gap-1 text-xs font-bold text-blue-600 hover:text-blue-700"
          >
            <span>
              {showAllRows ? 'Show top 5' : `Show all ${card.bars.length} items`}
            </span>
            {showAllRows ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>
        )}
      </div>
    );
  }

  /* ------------------------------------------------------------------------ */
  /*  Entity List Card                                                        */
  /* ------------------------------------------------------------------------ */
  if (card.card_type === 'entity_list' && card.items.length > 0) {
    const hasMore = card.items.length > MAX_INLINE_ITEMS;
    const displayedItems = showAllRows ? card.items : card.items.slice(0, MAX_INLINE_ITEMS);

    return (
      <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200/90 bg-slate-50/50 p-3.5">
        <div className="mb-2.5">
          <p className="text-sm font-bold text-slate-900">{card.title}</p>
          {card.subtitle && (
            <p className="text-xs font-medium text-slate-500">{card.subtitle}</p>
          )}
        </div>
        <div className="space-y-2">
          {displayedItems.map((item, idx) => {
            const dotClass = SEVERITY_DOT_CLASSES[item.severity] || SEVERITY_DOT_CLASSES.warning;
            const badgeClass =
              SEVERITY_BADGE_CLASSES[item.severity] || SEVERITY_BADGE_CLASSES.warning;
            const inner = (
              <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200/85 bg-white px-3 py-2.5 transition-colors hover:border-blue-300 hover:bg-sky-50/20">
                <div className="flex min-w-0 items-center gap-2.5">
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${dotClass}`}
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-slate-900">{item.title}</p>
                    <p className="truncate text-xs font-medium text-slate-500">
                      {formatManagerReadableText(item.subtitle)}
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {item.metric_value && (
                    <span className="text-xs font-bold tabular-nums text-slate-700">
                      {item.metric_value}
                    </span>
                  )}
                  {item.badge_text && (
                    <span
                      className={`rounded-md px-2 py-0.5 text-xs font-bold tabular-nums ${badgeClass}`}
                    >
                      {item.badge_text}
                    </span>
                  )}
                  {item.route_link && <ArrowRight size={14} className="text-slate-400" />}
                </div>
              </div>
            );
            return item.route_link ? (
              <Link key={`${item.id}-${idx}`} to={item.route_link} className="block">
                {inner}
              </Link>
            ) : (
              <div key={`${item.id}-${idx}`}>{inner}</div>
            );
          })}
        </div>
        {hasMore && (
          <button
            type="button"
            onClick={() => setShowAllRows((prev) => !prev)}
            className="mt-2.5 inline-flex items-center gap-1 text-xs font-bold text-blue-600 hover:text-blue-700"
          >
            <span>
              {showAllRows ? 'Show top 5' : `Show all ${card.items.length} items`}
            </span>
            {showAllRows ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
          </button>
        )}
      </div>
    );
  }

  /* ------------------------------------------------------------------------ */
  /*  KPI Breakdown Table + Mobile Stacked Cards Fallback                     */
  /* ------------------------------------------------------------------------ */
  if (card.card_type === 'kpi_table' && card.kpi_rows.length > 0) {
    const hasMore = card.kpi_rows.length > MAX_INLINE_ITEMS;
    const displayedRows = showAllRows ? card.kpi_rows : card.kpi_rows.slice(0, MAX_INLINE_ITEMS);

    return (
      <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200/90 bg-white">
        <div className="border-b border-slate-200/80 bg-slate-50/70 px-4 py-2.5">
          <p className="text-sm font-bold text-slate-900">{card.title}</p>
          {card.subtitle && (
            <p className="text-xs font-medium text-slate-500">{card.subtitle}</p>
          )}
        </div>

        {/* Mobile Stacked Cards (< 640px) */}
        <div className="divide-y divide-slate-100 sm:hidden">
          {displayedRows.map((row, idx) => {
            const badgeClass =
              SEVERITY_BADGE_CLASSES[row.status] || SEVERITY_BADGE_CLASSES.neutral;
            return (
              <div key={`mobile-${row.kpi_key}-${idx}`} className="space-y-1.5 p-3 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="inline-flex items-center gap-1.5 font-semibold text-slate-900">
                    <span
                      className={`h-2 w-2 shrink-0 rounded-full ${
                        SEVERITY_DOT_CLASSES[row.status] || SEVERITY_DOT_CLASSES.neutral
                      }`}
                    />
                    <span>{row.kpi_label}</span>
                  </span>
                  <span className={`rounded-md px-2 py-0.5 text-xs font-bold ${badgeClass}`}>
                    {row.achievement_percent !== null && row.achievement_percent !== undefined
                      ? `${row.achievement_percent.toFixed(1)}%`
                      : '—'}
                  </span>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-slate-600">
                  <span>
                    Actual <strong className="text-slate-900">{row.actual_display}</strong> / Target{' '}
                    {row.target_display}
                  </span>
                  <span>
                    Weight {row.weight_percent}% · {row.people_below_target} below
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        {/* Desktop & Tablet Table (>= 640px) */}
        <div className="hidden overflow-x-auto sm:block">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200/80 bg-slate-50/50 text-xs uppercase tracking-wider text-slate-500">
              <tr>
                <th className="px-4 py-2.5 font-bold">KPI</th>
                <th className="px-3 py-2.5 font-bold">Weight</th>
                <th className="px-3 py-2.5 font-bold">Actual / Target</th>
                <th className="px-3 py-2.5 font-bold">Achievement</th>
                <th className="px-4 py-2.5 text-right font-bold">Below Target</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {displayedRows.map((row, idx) => {
                const badgeClass =
                  SEVERITY_BADGE_CLASSES[row.status] || SEVERITY_BADGE_CLASSES.neutral;
                return (
                  <tr
                    key={`${row.kpi_key}-${row.kpi_label}-${idx}`}
                    className="transition-colors hover:bg-slate-50/70"
                  >
                    <td className="px-4 py-2.5 font-semibold text-slate-900">
                      <span className="inline-flex items-center gap-2">
                        <span
                          className={`h-2 w-2 shrink-0 rounded-full ${
                            SEVERITY_DOT_CLASSES[row.status] || SEVERITY_DOT_CLASSES.neutral
                          }`}
                        />
                        <span>{row.kpi_label}</span>
                        {row.tracking_only_badge && (
                          <span className="rounded border border-slate-200 bg-slate-100 px-1.5 py-0.5 text-xs font-semibold text-slate-600">
                            {row.tracking_only_badge}
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="px-3 py-2.5 text-xs font-semibold tabular-nums text-slate-600">
                      {row.weight_percent}%
                    </td>
                    <td className="px-3 py-2.5 font-semibold tabular-nums text-slate-800">
                      {row.actual_display}{' '}
                      <span className="font-normal text-slate-400">/ {row.target_display}</span>
                    </td>
                    <td className="px-3 py-2.5 tabular-nums">
                      <span
                        className={`inline-block rounded-md px-2 py-0.5 text-xs font-bold ${badgeClass}`}
                      >
                        {row.achievement_percent !== null && row.achievement_percent !== undefined
                          ? `${row.achievement_percent.toFixed(1)}%`
                          : '—'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right font-bold tabular-nums text-slate-800">
                      {row.people_below_target}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {hasMore && (
          <div className="border-t border-slate-100 px-4 py-2">
            <button
              type="button"
              onClick={() => setShowAllRows((prev) => !prev)}
              className="inline-flex items-center gap-1 text-xs font-bold text-blue-600 hover:text-blue-700"
            >
              <span>
                {showAllRows ? 'Show top 5 KPIs' : `Show all ${card.kpi_rows.length} KPIs`}
              </span>
              {showAllRows ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
            </button>
          </div>
        )}
      </div>
    );
  }

  /* ------------------------------------------------------------------------ */
  /*  Recommended Decisions Playbook Card                                     */
  /* ------------------------------------------------------------------------ */
  if (card.card_type === 'decision_playbook' && card.decisions && card.decisions.length > 0) {
    return (
      <div className="mt-3 overflow-hidden rounded-2xl border border-sky-200/90 bg-sky-50/30 p-4">
        <div className="mb-3 flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-600 text-white">
            <Lightbulb size={14} />
          </div>
          <div>
            <p className="text-sm font-bold text-slate-900">{card.title}</p>
            {card.subtitle && (
              <p className="text-xs font-medium text-slate-500">{card.subtitle}</p>
            )}
          </div>
        </div>

        <div className="space-y-2.5">
          {card.decisions.map((dec, idx) => {
            const pBadge = PRIORITY_BADGE_CLASSES[dec.priority] || PRIORITY_BADGE_CLASSES.high;
            return (
              <div
                key={`${dec.id}-${idx}`}
                className="rounded-xl border border-slate-200/85 bg-white p-3.5 transition-colors hover:border-sky-300"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                      {idx + 1}
                    </span>
                    <h4 className="text-sm font-bold text-slate-900">{dec.title}</h4>
                  </div>
                  <span className={`rounded-md px-2 py-0.5 text-xs font-bold ${pBadge}`}>
                    {dec.priority_label}
                  </span>
                </div>

                <p className="mt-1.5 text-sm leading-relaxed text-slate-600">{dec.rationale}</p>

                <div className="mt-2.5 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-emerald-200 bg-emerald-50/70 px-3 py-2 text-xs">
                  <div className="flex items-center gap-1.5 font-semibold text-emerald-900">
                    <TrendingUp size={14} className="shrink-0 text-emerald-600" />
                    <span>{dec.expected_impact}</span>
                  </div>
                  {dec.route_link && (
                    <Link
                      to={dec.route_link}
                      className="inline-flex items-center gap-1 rounded-full bg-blue-600 px-3 py-1 text-xs font-bold text-white transition-colors hover:bg-blue-700"
                    >
                      <span>{dec.cta_label || 'Take Action →'}</span>
                    </Link>
                  )}
                </div>

                <div className="mt-2 flex items-center gap-1.5 text-xs font-medium text-slate-500">
                  <Target size={12} className="shrink-0 text-blue-600" />
                  <span>Target: {dec.target_label}</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return null;
}
