import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronUp,
  Lightbulb,
  ShieldAlert,
  Sparkles,
  Target,
  TrendingUp,
  X,
} from 'lucide-react';
import { LineChart } from '../balanced-scorecard/LineChart';
import {
  GRADE_STYLES,
  gradeForScore,
  type GradeLetter,
} from '../../features/monthlyPresentation/monthlyOverviewData';
import type { AiChatResponsePayload, StructuredVisualCard } from '../../features/ai/types';
import { apiFetch } from '../../lib/apiClient';

interface AiResponseCardProps {
  response: AiChatResponsePayload;
  onSelectPrompt?: (prompt: string) => void;
}

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
  good: 'from-blue-600 via-sky-500 to-cyan-400',
  neutral: 'from-blue-600 via-sky-500 to-cyan-400',
};

const PRIORITY_BADGE_CLASSES: Record<string, string> = {
  immediate: 'border border-rose-200 bg-rose-50 text-rose-700',
  high: 'border border-amber-200 bg-amber-50 text-amber-800',
  coaching: 'border border-sky-200 bg-sky-50 text-sky-700',
  strategic: 'border border-emerald-200 bg-emerald-50 text-emerald-700',
};

function VisualBlock({ card }: { card: StructuredVisualCard }) {
  if (card.card_type === 'guardrail_notice') {
    return (
      <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50/80 p-3 text-xs text-slate-900">
        <div className="flex items-center gap-1.5 text-xs font-extrabold text-amber-800">
          <ShieldAlert size={14} className="shrink-0 text-amber-600" />
          <span>{card.title}</span>
        </div>
        {card.notice_text && (
          <p className="mt-1 text-[11px] leading-relaxed text-slate-700">{card.notice_text}</p>
        )}
      </div>
    );
  }

  /* ------------------------------------------------------------------------ */
  /*  Compact Agent / Team Spotlight & 6-Month Score Trend Card               */
  /* ------------------------------------------------------------------------ */
  if (card.card_type === 'trend_spotlight' && card.spotlight) {
    const sp = card.spotlight;
    const grade = (sp.grade in GRADE_STYLES ? sp.grade : gradeForScore(sp.score)) as GradeLetter;
    const gradeStyle = GRADE_STYLES[grade];
    const hasPrevChange = sp.change_vs_prev !== null && sp.change_vs_prev !== undefined;
    const isPositiveChange = (sp.change_vs_prev ?? 0) >= 0;
    const formattedChange = hasPrevChange
      ? `${isPositiveChange ? '+' : ''}${sp.change_vs_prev!.toFixed(1)}%`
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
      <div className="mt-3 overflow-hidden rounded-2xl border border-sky-200/80 bg-gradient-to-b from-sky-50/50 via-white to-white p-3.5 shadow-2xs">
        {/* Compact Top Row: Name + Hero Score + Grade + Rank */}
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <div className="flex items-center gap-1.5">
              <span className="inline-block rounded bg-sky-100/90 px-2 py-0.5 text-[9px] font-extrabold uppercase tracking-wider text-sky-800">
                {sp.kicker}
              </span>
              {sp.rank_label && (
                <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-[10px] font-extrabold text-emerald-700">
                  {sp.rank_label}
                </span>
              )}
            </div>
            <h3 className="mt-1 text-sm font-extrabold text-slate-900">
              {sp.entity_name}
              {sp.entity_id ? (
                <span className="ml-1 text-xs font-semibold text-slate-400">
                  ({sp.entity_id})
                </span>
              ) : null}
            </h3>
          </div>

          <div className="flex items-center gap-2">
            <span
              className={`text-2xl font-extrabold tracking-tight tabular-nums sm:text-3xl ${gradeStyle.scoreText}`}
            >
              {sp.score.toFixed(1)}%
            </span>
            <div className="flex flex-col items-end gap-1">
              <span
                className={`inline-flex items-center justify-center rounded-lg border px-2 py-0.5 text-[10px] font-extrabold ${gradeStyle.badgeBg} ${gradeStyle.badgeText} ${gradeStyle.badgeBorder}`}
              >
                Grade {grade}
              </span>
              {formattedChange && (
                <span
                  className={`inline-flex items-center gap-0.5 rounded-lg border px-2 py-0.5 text-[10px] font-extrabold ${
                    isPositiveChange
                      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                      : 'border-rose-200 bg-rose-50 text-rose-700'
                  }`}
                >
                  {isPositiveChange ? (
                    <ArrowUpRight className="size-3" />
                  ) : (
                    <ArrowDownRight className="size-3" />
                  )}
                  {formattedChange} vs {sp.previous_month_label.slice(0, 3)}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Compact 3-Tile Strip */}
        {sp.tiles.length > 0 && (
          <div className="mt-2.5 grid grid-cols-3 gap-2">
            {sp.tiles.map((tile, idx) => {
              const tileToneClass =
                tile.tone === 'good'
                  ? 'border-emerald-200/80 bg-emerald-50/40 text-emerald-900'
                  : tile.tone === 'warning'
                  ? 'border-amber-200/80 bg-amber-50/40 text-amber-900'
                  : tile.tone === 'critical'
                  ? 'border-rose-200/80 bg-rose-50/40 text-rose-900'
                  : 'border-slate-200/80 bg-slate-50/70 text-slate-900';
              return (
                <div
                  key={`${tile.label}-${idx}`}
                  className={`rounded-xl border px-2.5 py-1.5 ${tileToneClass}`}
                >
                  <div className="text-[10px] font-bold text-slate-500">{tile.label}</div>
                  <div className="text-sm font-extrabold tabular-nums">{tile.value}</div>
                  {tile.sublabel && (
                    <div className="truncate text-[10px] font-medium text-slate-500">
                      {tile.sublabel}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Compact 6-Month Score Trend Chart */}
        {chartHistory.length > 0 && (
          <div className="mt-2.5 rounded-xl border border-slate-200/85 bg-white p-3 shadow-2xs">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-extrabold text-slate-900">
                {chartHistory.length}-Month Score Trend
              </span>

              <div className="flex items-center gap-2.5 text-[11px] font-semibold text-slate-500">
                <span className="inline-flex items-center gap-1">
                  <span className="h-0.5 w-3 border-t-2 border-dashed border-emerald-600" />
                  Target {(sp.target || 100).toFixed(0)}%
                </span>
                {firstPoint && chartHistory.length >= 2 && (
                  <span
                    className={`rounded-md px-2 py-0.5 text-[10px] font-extrabold ${
                      sixMoDelta >= 0
                        ? 'bg-emerald-50 text-emerald-700'
                        : 'bg-rose-50 text-rose-700'
                    }`}
                  >
                    {sixMoDelta >= 0 ? `+${sixMoDelta.toFixed(1)}%` : `${sixMoDelta.toFixed(1)}%`}{' '}
                    since {firstPoint.month.slice(0, 3)}
                  </span>
                )}
              </div>
            </div>

            <div className="mt-1">
              <LineChart
                history={chartHistory}
                targetValue={sp.target || 100}
                height={128}
                showTarget
              />
            </div>
          </div>
        )}

        {/* Compact Agent KPI Breakdown Chips */}
        {sp.kpi_chips.length > 0 && (
          <div className="mt-2.5 grid grid-cols-2 gap-1.5 sm:grid-cols-5">
            {sp.kpi_chips.map((chip, idx) => {
              const ach = chip.achievement_percent ?? 100;
              const chipGrade = gradeForScore(ach);
              const chipStyle = GRADE_STYLES[chipGrade];
              return (
                <div
                  key={`${chip.kpi_key}-${idx}`}
                  className="rounded-lg border border-slate-200/80 bg-white px-2.5 py-1.5 shadow-2xs"
                >
                  <div
                    className="truncate text-[10px] font-bold text-slate-600"
                    title={chip.kpi_label}
                  >
                    {chip.kpi_label.replace(' (Patient Attended / Bookings)', '')}
                  </div>
                  <div className="mt-0.5 flex items-baseline justify-between gap-1">
                    <span className="text-[11px] font-extrabold tabular-nums text-slate-900">
                      {chip.actual_display}
                    </span>
                    <span className={`text-[10px] font-extrabold tabular-nums ${chipStyle.scoreText}`}>
                      {ach.toFixed(0)}%
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Optional Top-3 Entity List when plural ranking requested */}
        {card.items && card.items.length > 0 && (
          <div className="mt-2.5 space-y-1.5 border-t border-slate-200/80 pt-2.5">
            {card.items.map((item, idx) => (
              <div
                key={`${item.id}-${idx}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200/80 bg-white px-2.5 py-1.5 text-xs"
              >
                <div className="min-w-0">
                  <span className="font-bold text-slate-900">{item.title}</span>
                  {item.subtitle && (
                    <span className="ml-1.5 text-[10px] text-slate-500">{item.subtitle}</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {item.badge_text && (
                    <span className="rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[10px] font-bold text-slate-700">
                      {item.badge_text}
                    </span>
                  )}
                  {item.route_link && (
                    <Link
                      to={item.route_link}
                      className="text-[10px] font-bold text-blue-600 hover:underline"
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
  /*  Compact Horizontal Bar Card                                             */
  /* ------------------------------------------------------------------------ */
  if (card.card_type === 'horizontal_bar' && card.bars.length > 0) {
    const maxVal = Math.max(...card.bars.map((b) => Math.max(b.value, 1)), 100);
    return (
      <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200/90 bg-slate-50/70 p-3 shadow-2xs">
        <div className="mb-2">
          <p className="text-xs font-extrabold text-slate-900">{card.title}</p>
          {card.subtitle && (
            <p className="text-[10px] font-medium text-slate-500">{card.subtitle}</p>
          )}
        </div>
        <div className="space-y-2">
          {card.bars.map((bar, idx) => {
            const widthPct = Math.max(8, Math.min(100, Math.round((bar.value / maxVal) * 100)));
            const grad = BAR_GRADIENT_CLASSES[bar.severity] || BAR_GRADIENT_CLASSES.neutral;
            const badgeStyle =
              SEVERITY_BADGE_CLASSES[bar.severity] || SEVERITY_BADGE_CLASSES.neutral;
            return (
              <div
                key={`${bar.label}-${idx}`}
                className="rounded-xl border border-slate-200/80 bg-white px-3 py-2 shadow-2xs"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                  <span className="font-extrabold text-slate-900">{bar.label}</span>
                  <div className="flex items-center gap-2">
                    {bar.secondary_label && (
                      <span className="text-[10px] font-medium text-slate-500">
                        {bar.secondary_label}
                      </span>
                    )}
                    <span
                      className={`rounded-md px-2 py-0.5 text-[11px] font-extrabold tabular-nums ${badgeStyle}`}
                    >
                      {bar.display_value}
                    </span>
                  </div>
                </div>
                <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full bg-gradient-to-r ${grad} transition-all duration-500`}
                    style={{ width: `${widthPct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  /* ------------------------------------------------------------------------ */
  /*  Compact Entity List Card                                                */
  /* ------------------------------------------------------------------------ */
  if (card.card_type === 'entity_list' && card.items.length > 0) {
    return (
      <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200/90 bg-slate-50/70 p-3 shadow-2xs">
        <div className="mb-2">
          <p className="text-xs font-extrabold text-slate-900">{card.title}</p>
          {card.subtitle && (
            <p className="text-[10px] font-medium text-slate-500">{card.subtitle}</p>
          )}
        </div>
        <div className="space-y-1.5">
          {card.items.map((item, idx) => {
            const dotClass = SEVERITY_DOT_CLASSES[item.severity] || SEVERITY_DOT_CLASSES.warning;
            const badgeClass =
              SEVERITY_BADGE_CLASSES[item.severity] || SEVERITY_BADGE_CLASSES.warning;
            const inner = (
              <div className="flex items-center justify-between gap-2.5 rounded-xl border border-slate-200/85 bg-white px-3 py-2 shadow-2xs transition-all hover:border-blue-400 hover:bg-sky-50/30">
                <div className="flex min-w-0 items-center gap-2.5">
                  <span
                    className={`h-2 w-2 shrink-0 rounded-full ${dotClass}`}
                    aria-hidden="true"
                  />
                  <div className="min-w-0">
                    <p className="truncate text-xs font-extrabold text-slate-900">{item.title}</p>
                    <p className="truncate text-[11px] font-medium text-slate-500">
                      {item.subtitle}
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {item.badge_text && (
                    <span
                      className={`rounded-md px-2 py-0.5 text-[11px] font-extrabold tabular-nums ${badgeClass}`}
                    >
                      {item.badge_text}
                    </span>
                  )}
                  {item.route_link && <ArrowRight size={13} className="text-slate-400" />}
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
      </div>
    );
  }

  /* ------------------------------------------------------------------------ */
  /*  Compact KPI Table Card                                                  */
  /* ------------------------------------------------------------------------ */
  if (card.card_type === 'kpi_table' && card.kpi_rows.length > 0) {
    return (
      <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200/90 bg-white shadow-2xs">
        <div className="border-b border-slate-200/80 bg-slate-50/80 px-3.5 py-2.5">
          <p className="text-xs font-extrabold text-slate-900">{card.title}</p>
          {card.subtitle && (
            <p className="text-[10px] font-medium text-slate-500">{card.subtitle}</p>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200/80 bg-slate-50/50 text-[11px] text-slate-600">
              <tr>
                <th className="px-3 py-2 font-extrabold">KPI</th>
                <th className="px-2.5 py-2 font-extrabold">Weight</th>
                <th className="px-2.5 py-2 font-extrabold">Actual / Target</th>
                <th className="px-2.5 py-2 font-extrabold">Ach %</th>
                <th className="px-3 py-2 text-right font-extrabold">Below</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {card.kpi_rows.map((row, idx) => {
                const badgeClass =
                  SEVERITY_BADGE_CLASSES[row.status] || SEVERITY_BADGE_CLASSES.neutral;
                return (
                  <tr
                    key={`${row.kpi_key}-${row.kpi_label}-${idx}`}
                    className="transition-colors hover:bg-sky-50/30"
                  >
                    <td className="px-3 py-2 font-bold text-slate-900">
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className={`h-2 w-2 shrink-0 rounded-full ${
                            SEVERITY_DOT_CLASSES[row.status] || SEVERITY_DOT_CLASSES.neutral
                          }`}
                        />
                        <span>{row.kpi_label}</span>
                        {row.tracking_only_badge && (
                          <span className="rounded border border-slate-200 bg-slate-100 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-slate-600">
                            {row.tracking_only_badge}
                          </span>
                        )}
                      </span>
                    </td>
                    <td className="px-2.5 py-2 font-semibold tabular-nums text-slate-600">
                      {row.weight_percent}%
                    </td>
                    <td className="px-2.5 py-2 font-bold tabular-nums text-slate-800">
                      {row.actual_display}{' '}
                      <span className="font-normal text-slate-400">/ {row.target_display}</span>
                    </td>
                    <td className="px-2.5 py-2 tabular-nums">
                      <span
                        className={`inline-block rounded-md px-2 py-0.5 text-[11px] font-extrabold ${badgeClass}`}
                      >
                        {row.achievement_percent !== null && row.achievement_percent !== undefined
                          ? `${row.achievement_percent.toFixed(1)}%`
                          : '—'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-extrabold tabular-nums text-slate-800">
                      {row.people_below_target}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  /* ------------------------------------------------------------------------ */
  /*  Compact Decision Playbook Card                                          */
  /* ------------------------------------------------------------------------ */
  if (card.card_type === 'decision_playbook' && card.decisions && card.decisions.length > 0) {
    return (
      <div className="mt-3 overflow-hidden rounded-2xl border border-sky-200/90 bg-gradient-to-b from-sky-50/50 via-white to-white p-3.5 shadow-2xs">
        <div className="mb-2.5 flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500 to-blue-600 text-white shadow-2xs">
            <Lightbulb size={13} />
          </div>
          <div>
            <p className="text-xs font-extrabold text-slate-900">{card.title}</p>
            {card.subtitle && (
              <p className="text-[10px] font-medium text-slate-500">{card.subtitle}</p>
            )}
          </div>
        </div>

        <div className="space-y-2.5">
          {card.decisions.map((dec, idx) => {
            const pBadge = PRIORITY_BADGE_CLASSES[dec.priority] || PRIORITY_BADGE_CLASSES.high;
            return (
              <div
                key={`${dec.id}-${idx}`}
                className="rounded-xl border border-slate-200/85 bg-white p-3 shadow-2xs transition-all hover:border-sky-300"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-blue-600 text-[10px] font-extrabold text-white">
                      {idx + 1}
                    </span>
                    <h4 className="text-xs font-extrabold text-slate-900">{dec.title}</h4>
                  </div>
                  <span className={`rounded-md px-2 py-0.5 text-[10px] font-extrabold ${pBadge}`}>
                    {dec.priority_label}
                  </span>
                </div>

                <p className="mt-1.5 text-[11px] leading-relaxed text-slate-600">{dec.rationale}</p>

                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-emerald-200 bg-emerald-50/80 px-2.5 py-1.5 text-[11px]">
                  <div className="flex items-center gap-1.5 font-bold text-emerald-900">
                    <TrendingUp size={13} className="shrink-0 text-emerald-600" />
                    <span>{dec.expected_impact}</span>
                  </div>
                  {dec.route_link && (
                    <Link
                      to={dec.route_link}
                      className="inline-flex items-center gap-1 rounded-full bg-blue-600 px-2.5 py-0.5 text-[10px] font-extrabold text-white shadow-2xs transition-colors hover:bg-blue-700"
                    >
                      <span>{dec.cta_label || 'Take Action →'}</span>
                    </Link>
                  )}
                </div>

                <div className="mt-1.5 flex items-center gap-1 text-[10px] font-medium text-slate-500">
                  <Target size={11} className="shrink-0 text-blue-600" />
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

export default function AiResponseCard({ response, onSelectPrompt }: AiResponseCardProps) {
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const primaryCards = response.visual_cards.filter((c) => c.card_type !== 'decision_playbook');
  const playbookCards = response.visual_cards.filter((c) => c.card_type === 'decision_playbook');
  const totalDecisionsCount = playbookCards.reduce(
    (acc, c) => acc + (c.decisions?.length ?? 0),
    0,
  );
  const [showPlaybook, setShowPlaybook] = useState<boolean>(primaryCards.length === 0);
  const [detailsExpanded, setDetailsExpanded] = useState<boolean>(
    response.answer_detail !== 'brief',
  );

  useEffect(() => {
    setDetailsExpanded(response.answer_detail !== 'brief');
  }, [response.answer_detail, response.trace_id]);

  const primarySourceLink = response.primary_source_link || response.deep_links[0] || null;
  const secondaryDeepLinks = primarySourceLink
    ? response.deep_links.filter((d) => d.route !== primarySourceLink.route)
    : response.deep_links;
  const hasExpandableDetails =
    primaryCards.length > 0 ||
    playbookCards.length > 0 ||
    secondaryDeepLinks.length > 0 ||
    response.narrative_bullets.length > 1;

  const visibleBullets = detailsExpanded
    ? response.narrative_bullets
    : response.narrative_bullets.slice(0, 1);

  const handleFeedback = async (rating: 'up' | 'down') => {
    if (submitting) return;
    setSubmitting(true);
    setFeedback(rating);
    try {
      await apiFetch('/api/ai/feedback', {
        method: 'POST',
        body: JSON.stringify({
          trace_id: response.trace_id,
          rating,
        }),
      });
    } catch {
      // Keep local feedback state visible even if network call fails
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex items-start gap-2.5">
      {/* Compact Assistant Avatar Badge */}
      <div
        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-sky-400 via-blue-600 to-indigo-700 text-white shadow-sm shadow-blue-500/25"
        aria-hidden="true"
      >
        <Sparkles size={15} />
      </div>

      {/* Main Compact Response Card */}
      <div className="min-w-0 flex-1 rounded-2xl border border-slate-200/90 bg-white p-4 shadow-[0_6px_24px_rgb(15,23,42,0.05)]">
        {/* Executive Headline (1-2 sentences) */}
        <p dir="auto" className="text-xs font-extrabold leading-relaxed text-slate-900 sm:text-[13px]">
          {response.headline}
        </p>

        {/* Compact Executive Scope Banner + Primary Source Link + Show Details Toggle */}
        <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-1.5">
            {response.scope_banner && (
              <span
                data-testid="ai-scope-banner"
                className="inline-flex items-center rounded-md border border-slate-200/90 bg-slate-50 px-2 py-0.5 text-[10px] font-bold text-slate-600"
              >
                {response.scope_banner}
              </span>
            )}
            {primarySourceLink && (
              <Link
                to={primarySourceLink.route}
                data-testid="ai-primary-source-link"
                className="inline-flex items-center gap-1 rounded-full border border-sky-200 bg-sky-50/90 px-2.5 py-0.5 text-[11px] font-extrabold text-blue-700 transition-all hover:bg-blue-600 hover:text-white"
              >
                <span>{primarySourceLink.label}</span>
              </Link>
            )}
          </div>

          {hasExpandableDetails && (
            <button
              type="button"
              aria-expanded={detailsExpanded}
              onClick={() => setDetailsExpanded((prev) => !prev)}
              className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-[11px] font-extrabold text-slate-700 transition-colors hover:border-blue-400 hover:text-blue-600"
            >
              <span>{detailsExpanded ? 'Hide details' : 'Show details'}</span>
              {detailsExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            </button>
          )}
        </div>

        {/* Supporting Takeaway Bullets (primary driver in Brief mode; all bullets in Details mode) */}
        {visibleBullets.length > 0 && (
          <div className="mt-2 rounded-xl border border-sky-200/80 bg-sky-50/60 px-3 py-2">
            <ul
              dir="auto"
              className="space-y-1 text-[11px] font-medium leading-relaxed text-slate-700"
            >
              {visibleBullets.map((bullet, idx) => (
                <li key={idx} className="flex items-start gap-1.5">
                  <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-blue-600" />
                  <span>{bullet}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Interactive Clarification Options (when outcome === 'clarification') */}
        {response.outcome === 'clarification' && response.clarification && (
          <div className="mt-2.5 rounded-xl border border-sky-200 bg-sky-50/70 p-3">
            <p className="text-xs font-extrabold text-slate-900">
              {response.clarification.question}
            </p>
            {response.clarification.choices.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {response.clarification.choices.map((choice) => (
                  <button
                    key={choice.id}
                    type="button"
                    onClick={() => onSelectPrompt?.(choice.prompt_to_send || choice.label)}
                    className="inline-flex items-center gap-1 rounded-full border border-sky-300 bg-white px-3 py-1 text-[11px] font-extrabold text-blue-700 shadow-2xs transition-all hover:bg-blue-600 hover:text-white"
                  >
                    <span>{choice.label}</span>
                    <ArrowRight size={11} />
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Basis Shift Warning if present */}
        {response.basis_warning && (
          <div className="mt-2.5 flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-1.5 text-[11px] font-medium text-amber-900">
            <AlertTriangle size={13} className="shrink-0 text-amber-600" />
            <span>{response.basis_warning}</span>
          </div>
        )}

        {/* Expandable Details Region (Zero additional model calls on toggle) */}
        {detailsExpanded && (
          <>
            {/* Primary Visual Cards */}
            {primaryCards.map((card, index) => (
              <VisualBlock key={`${card.card_type}-${index}`} card={card} />
            ))}

            {/* Collapsible Decision Playbook Button */}
            {playbookCards.length > 0 && (
              <div className="mt-3">
                {primaryCards.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setShowPlaybook((prev) => !prev)}
                    className="inline-flex items-center gap-1.5 rounded-full border border-sky-200 bg-sky-50/80 px-3 py-1 text-[11px] font-extrabold text-blue-700 transition-all hover:border-blue-400 hover:bg-blue-600 hover:text-white"
                  >
                    <Lightbulb size={12} />
                    <span>
                      {showPlaybook
                        ? 'Hide Recommended Decisions'
                        : `View Recommended Decisions (${totalDecisionsCount})`}
                    </span>
                    {showPlaybook ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                  </button>
                )}
                {showPlaybook &&
                  playbookCards.map((card, index) => (
                    <VisualBlock key={`playbook-${index}`} card={card} />
                  ))}
              </div>
            )}

            {/* Additional Deep-Link CTA Buttons */}
            {secondaryDeepLinks.length > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-1.5">
                {secondaryDeepLinks.map((cta) => (
                  <Link
                    key={cta.route}
                    to={cta.route}
                    className="inline-flex items-center gap-1 rounded-full border border-sky-200 bg-sky-50/80 px-3 py-1 text-[11px] font-extrabold text-blue-700 transition-all hover:bg-blue-600 hover:text-white"
                  >
                    <span>{cta.label}</span>
                  </Link>
                ))}
              </div>
            )}
          </>
        )}

        {/* Bottom Footer: Source Citation Pills + ✓/✕ Distillation Feedback */}
        <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-2.5">
          <div className="flex flex-wrap items-center gap-1">
            {response.citations.map((pill) => (
              <span
                key={pill.label}
                className={`inline-flex items-center rounded-md px-2 py-0.5 text-[10px] font-bold ${
                  pill.warning
                    ? 'border border-amber-200 bg-amber-50 text-amber-800'
                    : 'border border-sky-100 bg-sky-50/70 text-sky-800'
                }`}
              >
                {pill.label}
              </span>
            ))}
          </div>

          <div className="flex items-center gap-1">
            {feedback === 'up' && (
              <span className="mr-1 text-[11px] font-bold text-emerald-600">Verified ✓</span>
            )}
            <button
              type="button"
              onClick={() => void handleFeedback('up')}
              aria-label="Approve response for AI training"
              title="Approve response (adds to verified local model training set)"
              className={`flex h-6 w-6 items-center justify-center rounded-md border text-xs transition-colors ${
                feedback === 'up'
                  ? 'border-emerald-400 bg-emerald-50 text-emerald-700'
                  : 'border-slate-200 bg-slate-50 text-slate-500 hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-700'
              }`}
            >
              <Check size={12} />
            </button>
            <button
              type="button"
              onClick={() => void handleFeedback('down')}
              aria-label="Flag response as inaccurate"
              title="Flag response"
              className={`flex h-6 w-6 items-center justify-center rounded-md border text-xs transition-colors ${
                feedback === 'down'
                  ? 'border-rose-400 bg-rose-50 text-rose-700'
                  : 'border-slate-200 bg-slate-50 text-slate-500 hover:border-rose-300 hover:bg-rose-50 hover:text-rose-700'
              }`}
            >
              <X size={12} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
