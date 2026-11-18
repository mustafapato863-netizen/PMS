import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronUp,
  Copy,
  Lightbulb,
  RefreshCw,
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
import type {
  AiChatResponsePayload,
  FeedbackCategoryType,
  StructuredVisualCard,
} from '../../features/ai/types';
import { apiFetch } from '../../lib/apiClient';

interface AiResponseCardProps {
  response: AiChatResponsePayload;
  onSelectPrompt?: (prompt: string, choiceId?: string) => void;
  onRegenerateAngle?: (nextSeed: number) => void;
  variationSeed?: number;
  isSending?: boolean;
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
          <p className="mt-1 text-xs leading-relaxed text-slate-700">{card.notice_text}</p>
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
              <span className="inline-block rounded bg-sky-100/90 px-2 py-0.5 text-xs font-extrabold uppercase tracking-wider text-sky-800">
                {sp.kicker}
              </span>
              {sp.rank_label && (
                <span className="rounded-full border border-emerald-200 bg-emerald-50 px-2 py-0.5 text-xs font-extrabold text-emerald-700">
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
                className={`inline-flex items-center justify-center rounded-lg border px-2 py-0.5 text-xs font-extrabold ${gradeStyle.badgeBg} ${gradeStyle.badgeText} ${gradeStyle.badgeBorder}`}
              >
                Grade {grade}
              </span>
              {formattedChange && (
                <span
                  className={`inline-flex items-center gap-0.5 rounded-lg border px-2 py-0.5 text-xs font-extrabold ${
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
                  <div className="text-xs font-bold text-slate-500">{tile.label}</div>
                  <div className="text-sm font-extrabold tabular-nums">{tile.value}</div>
                  {tile.sublabel && (
                    <div className="truncate text-xs font-medium text-slate-500">
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

              <div className="flex items-center gap-2.5 text-xs font-semibold text-slate-500">
                <span className="inline-flex items-center gap-1">
                  <span className="h-0.5 w-3 border-t-2 border-dashed border-emerald-600" />
                  Target {(sp.target || 100).toFixed(0)}%
                </span>
                {firstPoint && chartHistory.length >= 2 && (
                  <span
                    className={`rounded-md px-2 py-0.5 text-xs font-extrabold ${
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
                    className="truncate text-xs font-bold text-slate-600"
                    title={chip.kpi_label}
                  >
                    {chip.kpi_label.replace(' (Patient Attended / Bookings)', '')}
                  </div>
                  <div className="mt-0.5 flex items-baseline justify-between gap-1">
                    <span className="text-xs font-extrabold tabular-nums text-slate-900">
                      {chip.actual_display}
                    </span>
                    <span className={`text-xs font-extrabold tabular-nums ${chipStyle.scoreText}`}>
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
                    <span className="ml-1.5 text-xs text-slate-500">{item.subtitle}</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {item.badge_text && (
                    <span className="rounded-md border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-xs font-bold text-slate-700">
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
  /*  Compact Horizontal Bar Card                                             */
  /* ------------------------------------------------------------------------ */
  if (card.card_type === 'horizontal_bar' && card.bars.length > 0) {
    // Null bars carry no value and must not influence the scale (nor render
    // the 8% minimum-width stub a fake 0.0 used to get).
    const maxVal = Math.max(...card.bars.map((b) => (b.value === null ? 1 : Math.max(b.value, 1))), 100);
    return (
      <div className="mt-3 overflow-hidden rounded-2xl border border-slate-200/90 bg-slate-50/70 p-3 shadow-2xs">
        <div className="mb-2">
          <p className="text-xs font-extrabold text-slate-900">{card.title}</p>
          {card.subtitle && (
            <p className="text-xs font-medium text-slate-500">{card.subtitle}</p>
          )}
        </div>
        <div className="space-y-2">
          {card.bars.map((bar, idx) => {
            const widthPct = bar.value === null ? 0 : Math.max(8, Math.min(100, Math.round((bar.value / maxVal) * 100)));
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
                      <span className="text-xs font-medium text-slate-500">
                        {bar.secondary_label}
                      </span>
                    )}
                    <span
                      className={`rounded-md px-2 py-0.5 text-xs font-extrabold tabular-nums ${badgeStyle}`}
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
            <p className="text-xs font-medium text-slate-500">{card.subtitle}</p>
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
                    <p className="truncate text-xs font-medium text-slate-500">
                      {item.subtitle}
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-1.5">
                  {item.badge_text && (
                    <span
                      className={`rounded-md px-2 py-0.5 text-xs font-extrabold tabular-nums ${badgeClass}`}
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
            <p className="text-xs font-medium text-slate-500">{card.subtitle}</p>
          )}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200/80 bg-slate-50/50 text-xs text-slate-600">
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
                          <span className="rounded border border-slate-200 bg-slate-100 px-1.5 py-0.5 text-xs font-bold uppercase tracking-wide text-slate-600">
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
                        className={`inline-block rounded-md px-2 py-0.5 text-xs font-extrabold ${badgeClass}`}
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
                className="rounded-xl border border-slate-200/85 bg-white p-3 shadow-2xs transition-all hover:border-sky-300"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-extrabold text-white">
                      {idx + 1}
                    </span>
                    <h4 className="text-xs font-extrabold text-slate-900">{dec.title}</h4>
                  </div>
                  <span className={`rounded-md px-2 py-0.5 text-xs font-extrabold ${pBadge}`}>
                    {dec.priority_label}
                  </span>
                </div>

                <p className="mt-1.5 text-xs leading-relaxed text-slate-600">{dec.rationale}</p>

                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-emerald-200 bg-emerald-50/80 px-2.5 py-1.5 text-xs">
                  <div className="flex items-center gap-1.5 font-bold text-emerald-900">
                    <TrendingUp size={13} className="shrink-0 text-emerald-600" />
                    <span>{dec.expected_impact}</span>
                  </div>
                  {dec.route_link && (
                    <Link
                      to={dec.route_link}
                      className="inline-flex items-center gap-1 rounded-full bg-blue-600 px-2.5 py-0.5 text-xs font-extrabold text-white shadow-2xs transition-colors hover:bg-blue-700"
                    >
                      <span>{dec.cta_label || 'Take Action →'}</span>
                    </Link>
                  )}
                </div>

                <div className="mt-1.5 flex items-center gap-1 text-xs font-medium text-slate-500">
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

export default function AiResponseCard({
  response,
  onSelectPrompt,
  onRegenerateAngle,
  variationSeed = 0,
  isSending = false,
}: AiResponseCardProps) {
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);
  const [showFlagForm, setShowFlagForm] = useState(false);
  const [flagCategory, setFlagCategory] = useState<FeedbackCategoryType>('wrong_data');
  const [flagReason, setFlagReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [feedbackError, setFeedbackError] = useState(false);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);

  const primaryCards = response.visual_cards.filter((c) => c.card_type !== 'decision_playbook');
  const playbookCards = response.visual_cards.filter((c) => c.card_type === 'decision_playbook');
  const totalDecisionsCount = playbookCards.reduce(
    (acc, c) => acc + (c.decisions?.length ?? 0),
    0,
  );
  const [showPlaybook, setShowPlaybook] = useState<boolean>(primaryCards.length === 0);
  const [detailsOverride, setDetailsOverride] = useState<{
    traceId: string;
    answerDetail: AiChatResponsePayload['answer_detail'];
    expanded: boolean;
  } | null>(null);
  const detailsExpanded =
    detailsOverride?.traceId === (response.trace_id ?? '') &&
    detailsOverride.answerDetail === response.answer_detail
      ? detailsOverride.expanded
      : response.answer_detail !== 'brief';

  const primarySourceLink = response.primary_source_link || response.deep_links[0] || null;
  const secondaryDeepLinks = primarySourceLink
    ? response.deep_links.filter((d) => d.route !== primarySourceLink.route)
    : response.deep_links;
  const detailBullets = response.detail_bullets ?? [];
  const hasExpandableDetails =
    primaryCards.length > 0 ||
    playbookCards.length > 0 ||
    secondaryDeepLinks.length > 0 ||
    detailBullets.length > 0;

  // Brief answers must already be complete in headline + narrative_bullets; never hide
  // narrative_bullets by array index or prefix. Supporting evidence lives in detail_bullets / visual_cards.
  const visibleBullets = response.narrative_bullets;

  const handleFeedback = async (
    rating: 'up' | 'down',
    category?: FeedbackCategoryType,
    reason?: string,
  ) => {
    if (submitting) return;
    setSubmitting(true);
    setFeedbackError(false);
    try {
      await apiFetch('/api/ai/feedback', {
        method: 'POST',
        body: JSON.stringify({
          trace_id: response.trace_id,
          rating,
          category: category || (rating === 'up' ? 'helpful' : flagCategory),
          ...(reason?.trim() ? { reason: reason.trim() } : {}),
        }),
      });
      setFeedback(rating);
      if (rating === 'down') {
        setShowFlagForm(false);
      }
    } catch {
      setFeedbackError(true);
    } finally {
      setSubmitting(false);
    }
  };

  const handleCopySummary = async () => {
    const lines = [response.headline, ...response.narrative_bullets.map((b) => `- ${b}`)].filter(Boolean);
    const text = lines.join('\n');
    setCopyError(false);
    try {
      if (typeof navigator === 'undefined' || typeof navigator.clipboard?.writeText !== 'function') {
        throw new Error('Clipboard API unavailable');
      }
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // In insecure contexts or when clipboard permission is denied, never claim success.
      setCopied(false);
      setCopyError(true);
    }
  };

  const isLiveSynthesis =
    (response.provider_used === 'cloudflare' || response.provider_used === 'gemini') &&
    response.answer_source !== 'fallback' &&
    response.answer_source !== 'deterministic';
  const capabilityMode = response.capability_mode ?? 'performance_query';
  const isPerformanceAnswer =
    capabilityMode === 'performance_query' && response.outcome === 'answer';
  const showScopeBanner = Boolean(
    response.scope_banner && capabilityMode !== 'greeting' && capabilityMode !== 'off_topic',
  );
  const showCopyButton =
    response.outcome === 'answer' &&
    capabilityMode !== 'greeting' &&
    capabilityMode !== 'off_topic';
  const showHeaderMetaRow =
    isPerformanceAnswer ||
    showScopeBanner ||
    Boolean(primarySourceLink) ||
    showCopyButton ||
    hasExpandableDetails;

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
        <p dir="auto" className="text-sm font-extrabold leading-relaxed text-slate-900">
          {response.headline}
        </p>

        {/* Compact Executive Scope Banner + Provenance + Primary Source Link + Actions */}
        {showHeaderMetaRow && (
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-1.5">
              {isPerformanceAnswer && (
                <span
                  data-testid="ai-provenance-badge"
                  className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-bold ${
                    isLiveSynthesis
                      ? 'border-indigo-200 bg-indigo-50 text-indigo-700'
                      : 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  }`}
                >
                  {isLiveSynthesis ? 'Verified PMS · Live Synthesis' : 'Verified PMS · Deterministic'}
                </span>
              )}
              {showScopeBanner && (
                <span
                  data-testid="ai-scope-banner"
                  className="inline-flex items-center rounded-md border border-slate-200/90 bg-slate-50 px-2 py-0.5 text-xs font-bold text-slate-600"
                >
                  {response.scope_banner}
                </span>
              )}
              {primarySourceLink && (
                <Link
                  to={primarySourceLink.route}
                  data-testid="ai-primary-source-link"
                  className="inline-flex items-center gap-1 rounded-full border border-sky-200 bg-sky-50/90 px-2.5 py-0.5 text-xs font-extrabold text-blue-700 transition-all hover:bg-blue-600 hover:text-white"
                >
                  <span>{primarySourceLink.label}</span>
                </Link>
              )}
              {isPerformanceAnswer && response.suggested_followups.length > 0 && (
                <button
                  type="button"
                  data-testid="ai-primary-drilldown"
                  onClick={() => onSelectPrompt?.(response.suggested_followups[0])}
                  className="inline-flex items-center gap-1 rounded-full border border-slate-200/90 bg-white px-2.5 py-0.5 text-xs font-bold text-slate-700 transition-colors hover:border-blue-400 hover:text-blue-600"
                >
                  <span>Drill down: {response.suggested_followups[0]}</span>
                  <ArrowRight size={12} />
                </button>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-1.5">
              {isPerformanceAnswer && onRegenerateAngle && (
                <button
                  type="button"
                  data-testid="ai-regenerate-angle-btn"
                  aria-label="Get a different reply angle"
                  disabled={isSending}
                  onClick={() => onRegenerateAngle((variationSeed ?? 0) + 1)}
                  className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-xs font-bold text-slate-700 transition-colors hover:border-blue-400 hover:text-blue-600 disabled:opacity-50"
                >
                  <RefreshCw size={12} />
                  <span>Different angle</span>
                </button>
              )}
              {showCopyButton && (
                <button
                  type="button"
                  data-testid="ai-copy-summary-btn"
                  aria-label={copied ? 'Summary copied' : 'Copy summary'}
                  onClick={() => void handleCopySummary()}
                  className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-xs font-bold text-slate-700 transition-colors hover:border-blue-400 hover:text-blue-600"
                >
                  {copied ? <Check size={12} className="text-emerald-600" /> : <Copy size={12} />}
                  <span>{copied ? 'Copied' : 'Copy'}</span>
                </button>
              )}
              {copyError && (
                <span role="status" className="text-xs font-medium text-amber-700">
                  Copy unavailable. Select the text to copy manually.
                </span>
              )}
              {copied && (
                <span role="status" className="sr-only">Summary copied to clipboard.</span>
              )}
              {hasExpandableDetails && (
                <button
                  type="button"
                  aria-expanded={detailsExpanded}
                  onClick={() =>
                    setDetailsOverride({
                      traceId: response.trace_id ?? '',
                      answerDetail: response.answer_detail,
                      expanded: !detailsExpanded,
                    })
                  }
                  className="inline-flex items-center gap-1 rounded-full border border-slate-200 bg-white px-2.5 py-0.5 text-xs font-extrabold text-slate-700 transition-colors hover:border-blue-400 hover:text-blue-600"
                >
                  <span>{detailsExpanded ? 'Hide details' : 'View details'}</span>
                  {detailsExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                </button>
              )}
            </div>
          </div>
        )}

        {/* Supporting Takeaway Bullets (primary driver in Brief mode; all bullets in Details mode) */}
        {visibleBullets.length > 0 && (
          <div className="mt-2 rounded-xl border border-sky-200/80 bg-sky-50/60 px-3 py-2">
            <ul
              dir="auto"
              className="space-y-1 text-xs font-medium leading-relaxed text-slate-700"
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
                    data-testid={`ai-clarification-choice-${choice.id}`}
                    onClick={() => onSelectPrompt?.(choice.prompt_to_send || choice.label, choice.id)}
                    className="inline-flex items-center gap-1 rounded-full border border-sky-300 bg-white px-3 py-1 text-xs font-extrabold text-blue-700 shadow-2xs transition-all hover:bg-blue-600 hover:text-white"
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
          <div className="mt-2.5 flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-900">
            <AlertTriangle size={13} className="shrink-0 text-amber-600" />
            <span>{response.basis_warning}</span>
          </div>
        )}

        {/* Expandable Details Region (Zero additional model calls on toggle) */}
        {detailsExpanded && (
          <>
            {detailBullets.length > 0 && (
              <div
                data-testid="ai-detail-bullets"
                className="mt-2.5 rounded-xl border border-slate-200/80 bg-slate-50/70 px-3 py-2"
              >
                <ul
                  dir="auto"
                  className="space-y-1 text-xs font-medium leading-relaxed text-slate-600"
                >
                  {detailBullets.map((bullet, idx) => (
                    <li key={idx} className="flex items-start gap-1.5">
                      <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-slate-400" />
                      <span>{bullet}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

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
                    className="inline-flex items-center gap-1.5 rounded-full border border-sky-200 bg-sky-50/80 px-3 py-1 text-xs font-extrabold text-blue-700 transition-all hover:border-blue-400 hover:bg-blue-600 hover:text-white"
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
                    className="inline-flex items-center gap-1 rounded-full border border-sky-200 bg-sky-50/80 px-3 py-1 text-xs font-extrabold text-blue-700 transition-all hover:bg-blue-600 hover:text-white"
                  >
                    <span>{cta.label}</span>
                  </Link>
                ))}
              </div>
            )}
          </>
        )}

        {/* Helpful Next-Step Chips for non-performance capability modes (greeting, help, navigation, off-topic) */}
        {!isPerformanceAnswer &&
          response.outcome !== 'clarification' &&
          response.suggested_followups.length > 0 && (
            <div
              data-testid="ai-next-step-chips"
              className="mt-2.5 flex flex-wrap items-center gap-1.5"
            >
              {response.suggested_followups.map((followup) => (
                <button
                  key={followup}
                  type="button"
                  disabled={isSending}
                  onClick={() => onSelectPrompt?.(followup)}
                  className="inline-flex items-center gap-1 rounded-full border border-slate-200/90 bg-slate-50/70 px-3 py-1 text-xs font-bold text-slate-700 transition-colors hover:border-blue-400 hover:bg-blue-50 hover:text-blue-700 disabled:opacity-50"
                >
                  <span>{followup}</span>
                  <ArrowRight size={12} className="shrink-0 text-blue-600" />
                </button>
              ))}
            </div>
          )}

        {/* Bottom Footer: Source Citation Pills + ✓/✕ Distillation Feedback */}
        {(response.citations.length > 0 || Boolean(response.trace_id)) && (
          <div className="mt-3 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-2.5">
          <div className="flex flex-wrap items-center gap-1">
            {response.citations.map((pill) => (
              <span
                key={pill.label}
                className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-bold ${
                  pill.warning
                    ? 'border border-amber-200 bg-amber-50 text-amber-800'
                    : 'border border-sky-100 bg-sky-50/70 text-sky-800'
                }`}
              >
                {pill.label}
              </span>
            ))}
          </div>

          {response.trace_id && (
            <div className="flex flex-wrap items-center gap-1.5">
              {feedback === 'up' && (
                <span className="mr-1 text-xs font-bold text-emerald-600">Feedback saved</span>
              )}
              {feedback === 'down' && (
                <span className="mr-1 text-xs font-bold text-rose-600">Feedback saved</span>
              )}
              {feedbackError && (
                <span role="alert" className="mr-1 text-xs font-semibold text-rose-600">
                  Could not save feedback. Try again.
                </span>
              )}
              <button
                type="button"
                onClick={() => {
                  setShowFlagForm(false);
                  void handleFeedback('up', 'helpful');
                }}
                aria-label="Mark response as useful"
                title="Mark response as useful (pending administrator review)"
                disabled={submitting}
                className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-bold transition-colors disabled:opacity-50 ${
                  feedback === 'up'
                    ? 'border-emerald-400 bg-emerald-50 text-emerald-700'
                    : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-emerald-300 hover:bg-emerald-50 hover:text-emerald-700'
                }`}
              >
                <Check size={12} />
                <span>Helpful</span>
              </button>
              <button
                type="button"
                onClick={() => setShowFlagForm((prev) => !prev)}
                aria-label="Flag response as inaccurate"
                aria-expanded={showFlagForm}
                title="Flag response with failure tag"
                disabled={submitting}
                className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-bold transition-colors disabled:opacity-50 ${
                  feedback === 'down' || showFlagForm
                    ? 'border-rose-400 bg-rose-50 text-rose-700'
                    : 'border-slate-200 bg-slate-50 text-slate-600 hover:border-rose-300 hover:bg-rose-50 hover:text-rose-700'
                }`}
              >
                <X size={12} />
                <span>Not helpful</span>
              </button>
            </div>
          )}
        </div>
        )}

        {response.trace_id && showFlagForm && (
          <div
            data-testid="ai-feedback-flag-panel"
            className="mt-2.5 rounded-xl border border-rose-200/80 bg-rose-50/40 p-3"
          >
            <p className="text-xs font-bold text-slate-800">
              What went wrong? Select a tag for Admin review:
            </p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(
                [
                  { key: 'wrong_data', label: 'Wrong data' },
                  { key: 'misunderstood_question', label: 'Misunderstood question' },
                  { key: 'lost_context', label: 'Lost context' },
                  { key: 'too_long', label: 'Too long' },
                ] as const
              ).map((tag) => {
                const selected = flagCategory === tag.key;
                return (
                  <button
                    key={tag.key}
                    type="button"
                    aria-pressed={selected}
                    onClick={() => setFlagCategory(tag.key)}
                    className={`rounded-full border px-2.5 py-1 text-xs font-bold transition-colors ${
                      selected
                        ? 'border-rose-500 bg-rose-600 text-white'
                        : 'border-slate-200 bg-white text-slate-700 hover:border-rose-300 hover:text-rose-700'
                    }`}
                  >
                    {tag.label}
                  </button>
                );
              })}
            </div>
            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              <input
                type="text"
                value={flagReason}
                onChange={(e) => setFlagReason(e.target.value)}
                maxLength={120}
                aria-label="Optional feedback note"
                placeholder="Optional short note (max 120 chars)"
                className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-800 placeholder:text-slate-400 focus:border-rose-400 focus:outline-none"
              />
              <button
                type="button"
                disabled={submitting}
                onClick={() => void handleFeedback('down', flagCategory, flagReason)}
                className="rounded-full bg-rose-600 px-3 py-1.5 text-xs font-bold text-white transition-colors hover:bg-rose-700 disabled:opacity-50"
              >
                {submitting ? 'Sending…' : 'Send feedback'}
              </button>
              <button
                type="button"
                disabled={submitting}
                onClick={() => setShowFlagForm(false)}
                className="rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-bold text-slate-600 hover:bg-slate-100"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
