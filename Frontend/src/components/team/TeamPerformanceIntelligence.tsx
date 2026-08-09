import { useState } from 'react';
import { AlertTriangle, Award, CheckCircle2, ChevronDown, ChevronUp, Gauge, Lightbulb, Target, TrendingDown, TrendingUp, Users, Hash } from 'lucide-react';
import type { TeamKpiAnalysis } from '../../features/team/teamKpiAnalysis';
import { buildTeamKpiRecommendation, formatTeamKpiValue } from '../../features/team/teamKpiAnalysis';

interface TeamPerformanceIntelligenceProps {
  displayName: string;
  month: string;
  averageScore: number;
  atRiskEmployees: number;
  kpis: TeamKpiAnalysis[];
}

const tone = {
  critical: 'border-rose-300 bg-rose-500/[0.055] dark:border-rose-500/30',
  attention: 'border-amber-300 bg-amber-500/[0.055] dark:border-amber-500/30',
  on_target: 'border-emerald-300 bg-emerald-500/[0.055] dark:border-emerald-500/30',
  configuration_requires_review: 'border-slate-300 bg-slate-500/[0.055] dark:border-slate-500/30',
};

const statusLabel = { critical: 'Critical gap', attention: 'Needs attention', on_target: 'On target', configuration_requires_review: 'Configuration review' };

export const TeamPerformanceIntelligence = ({ displayName, month, averageScore, atRiskEmployees, kpis }: TeamPerformanceIntelligenceProps) => {
  const [showAll, setShowAll] = useState(false);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const visible = showAll ? kpis : kpis.slice(0, 4);

  const visibleKeys = visible.map(k => k.key);
  const allExpanded = visibleKeys.length > 0 && visibleKeys.every(key => !!expanded[key]);

  const toggleAllExpanded = () => {
    if (allExpanded) {
      const nextExpanded = { ...expanded };
      visibleKeys.forEach(key => {
        nextExpanded[key] = false;
      });
      setExpanded(nextExpanded);
    } else {
      const nextExpanded = { ...expanded };
      visibleKeys.forEach(key => {
        nextExpanded[key] = true;
      });
      setExpanded(nextExpanded);
    }
  };
  const attention = kpis.filter((kpi) => !kpi.targetMet);
  const strongest = kpis.filter((kpi) => kpi.achievement !== null).sort((left, right) => (right.achievement ?? 0) - (left.achievement ?? 0))[0];
  const scoreFactors = kpis
    .filter((kpi) => kpi.weight !== null && kpi.weight > 0)
    .sort((left, right) => (right.weight ?? 0) - (left.weight ?? 0));
  const overallResult = averageScore >= 85 ? 'Exceeds expectations' : averageScore >= 75 ? 'Meets expectations' : 'Needs attention';

  const summaryRows = [
    { label: 'Overall result', value: `${overallResult} · ${averageScore.toFixed(1)}%`, icon: Gauge, color: 'text-blue-600 bg-blue-500/10' },
    { label: 'Strongest KPI', value: strongest && strongest.achievement !== null ? `${strongest.label} (${strongest.achievement.toFixed(1)}%)` : 'Unavailable', icon: Award, color: 'text-emerald-600 bg-emerald-500/10' },
    { label: 'KPIs needing attention', value: String(attention.length), icon: AlertTriangle, color: 'text-amber-600 bg-amber-500/10' },
    { label: 'Employees at risk', value: String(atRiskEmployees), icon: Users, color: 'text-emerald-600 bg-emerald-500/10' },
    { label: 'Main score factors', value: scoreFactors.slice(0, 4).map((kpi) => kpi.label).join(', ') || 'No weighted KPI factors available', icon: TrendingDown, color: 'text-orange-600 bg-orange-500/10' },
  ];

  return (
    <section className="grid grid-cols-1 gap-4 xl:grid-cols-[0.68fr_1.5fr]" aria-label={`${displayName} performance intelligence`}>
      <div className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5 shadow-sm">
        <h3 className="flex items-center gap-2 text-base font-extrabold text-[var(--text-primary)]">
          <Target size={18} className="text-blue-600 dark:text-blue-400" /> {displayName} Performance Summary
        </h3>
        <div className="mt-4 space-y-2.5">
          {summaryRows.map((row) => {
            const Icon = row.icon;
            return (
              <div key={row.label} className="flex items-center gap-3 rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/35 p-3">
                <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${row.color}`}><Icon size={16} /></span>
                <div className="min-w-0">
                  <p className="text-[10px] font-extrabold uppercase tracking-wide text-[var(--text-muted)]">{row.label}</p>
                  <p className="mt-0.5 text-xs font-extrabold text-[var(--text-primary)]">{row.value}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-5 shadow-sm">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <h3 className="flex items-center gap-2 text-base font-extrabold text-[var(--text-primary)]">
            <Lightbulb size={18} className="text-violet-600 dark:text-violet-400" /> Performance Analysis
          </h3>
          <div className="flex items-center gap-2">
            {visible.length > 0 && (
              <button
                type="button"
                onClick={toggleAllExpanded}
                className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-[var(--border-medium)] px-3 text-[10px] font-extrabold text-[var(--text-secondary)] hover:bg-[var(--bg-sunken)] transition-colors"
              >
                {allExpanded ? 'Collapse all' : 'Expand all'}
              </button>
            )}
            {kpis.length > 4 && (
              <button type="button" onClick={() => setShowAll((value) => !value)} className="inline-flex min-h-9 items-center gap-1.5 rounded-lg border border-[var(--border-medium)] px-3 text-[10px] font-extrabold text-[var(--text-secondary)]">
                {showAll ? <ChevronUp size={13} /> : <ChevronDown size={13} />}{showAll ? 'Show priority only' : `Show all ${kpis.length}`}
              </button>
            )}
          </div>
        </div>
        <div className="mt-4 space-y-2.5">
          {visible.map((kpi) => {
            const isExpanded = !!expanded[kpi.key];
            const trendUp = (kpi.movementPercent ?? 0) >= 0;
            const TrendIcon = trendUp ? TrendingUp : TrendingDown;
            const isImprovingOffTarget = kpi.movementPositive === true && !kpi.targetMet;
            const absoluteMovement = kpi.previousActual === null ? null : Math.abs(kpi.actual - kpi.previousActual);
            const movementAmount = absoluteMovement === null
              ? ''
              : kpi.unit === '%'
                ? `${(absoluteMovement * 100).toFixed(1)}%`
                : formatTeamKpiValue(absoluteMovement, kpi.unit);
            const movementText = kpi.previousActual === null
              ? 'Previous-period value unavailable'
              : kpi.movementPositive === null
                ? `No change · ${formatTeamKpiValue(kpi.actual, kpi.unit)}`
                : `${kpi.movementPositive ? 'Improved' : 'Declined'} by ${movementAmount} · ${formatTeamKpiValue(kpi.previousActual, kpi.unit)} → ${formatTeamKpiValue(kpi.actual, kpi.unit)}`;
            const movementTone = kpi.movementPositive === true
              ? 'text-emerald-600 dark:text-emerald-300'
              : kpi.movementPositive === false
                ? 'text-rose-600 dark:text-rose-300'
                : 'text-[var(--text-muted)]';
            const baselineAvailable = kpi.baselineActual !== null && Number.isFinite(kpi.baselineActual);
            const baselineGap = baselineAvailable ? Math.abs(kpi.actual - kpi.baselineActual!) : 0;
            const baselineGapLabel = kpi.unit === '%'
              ? `${(baselineGap * 100).toFixed(1)}%`
              : formatTeamKpiValue(baselineGap, kpi.unit);
            const previousBaselineAvailable = kpi.previousBaselineActual !== null && Number.isFinite(kpi.previousBaselineActual);
            const newBaselineGain = previousBaselineAvailable ? Math.abs(kpi.actual - kpi.previousBaselineActual!) : 0;
            const newBaselineGainLabel = kpi.unit === '%'
              ? `${(newBaselineGain * 100).toFixed(1)}%`
              : formatTeamKpiValue(newBaselineGain, kpi.unit);
            const matchesBest = baselineAvailable && baselineGap < 1e-9;
            const currentIsBetter = baselineAvailable && !matchesBest && (kpi.lowerBetter ? kpi.actual < kpi.baselineActual! : kpi.actual > kpi.baselineActual!);
            const baselinePosition = !baselineAvailable
              ? 'Not available'
              : kpi.isNewBaseline
                ? `+${newBaselineGainLabel} · New Baseline`
              : matchesBest
                ? previousBaselineAvailable ? 'Matches Baseline' : 'Baseline established'
                : currentIsBetter
                  ? `New best by ${baselineGapLabel}`
                  : `${baselineGapLabel} ${kpi.lowerBetter ? 'above' : 'below'} best`;
            const movementStory = kpi.previousActual === null
              ? `No previous-period result is available for comparison with ${month}.`
              : `${month} moved from ${formatTeamKpiValue(kpi.previousActual, kpi.unit)} to ${formatTeamKpiValue(kpi.actual, kpi.unit)}, ${kpi.movementPositive === null ? 'with no material change' : `a ${kpi.movementPositive ? 'positive' : 'negative'} movement of ${movementAmount}`}.`;
            const baselineStory = !baselineAvailable
              ? 'No historical result is available to establish a baseline.'
              : kpi.isNewBaseline && previousBaselineAvailable
                ? `Previous Baseline: ${formatTeamKpiValue(kpi.previousBaselineActual!, kpi.unit)} (${kpi.previousBaselineMonth}). ${month} +${newBaselineGainLabel} From Last Baseline. ${month} is the New Baseline.`
              : `Best historical result: ${formatTeamKpiValue(kpi.baselineActual!, kpi.unit)} (${kpi.baselineMonth}). ${month} - ${baselineGapLabel} From Baseline.`;
            return (
              <article key={kpi.key} className={`overflow-hidden rounded-xl border ${tone[kpi.severity]}`}>
                <button type="button" onClick={() => setExpanded((prev) => ({ ...prev, [kpi.key]: !prev[kpi.key] }))} aria-expanded={isExpanded} className="block w-full p-3.5 text-left">
                  <span className="flex items-start gap-3">
                    <span className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${kpi.targetMet ? 'bg-emerald-500/10 text-emerald-600' : 'bg-rose-500/10 text-rose-600'}`}>
                      {kpi.targetMet ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-center gap-2 text-sm font-extrabold text-[var(--text-primary)]">
                        {kpi.label}<small className="rounded-full bg-[var(--bg-surface)]/75 px-2 py-0.5 text-[9px] font-bold text-[var(--text-muted)]">{kpi.lowerBetter ? 'Lower is better' : 'Higher is better'}</small>
                      </span>
                      <span className={`mt-1.5 flex flex-wrap items-center gap-1.5 text-[10px] font-bold ${movementTone}`}>
                        <TrendIcon size={12} />{movementText}{kpi.movementPercent !== null && kpi.movementPositive !== null && <strong className="rounded-full bg-current/10 px-1.5 py-0.5">{Math.abs(kpi.movementPercent).toFixed(1)}% {kpi.movementPositive ? 'improvement' : 'decline'}</strong>}
                      </span>
                    </span>
                    <span className="flex shrink-0 items-center gap-2">
                      {isImprovingOffTarget ? (
                        <span className="hidden items-center gap-1 rounded-full bg-slate-500/10 px-2.5 py-1 text-[9px] font-extrabold uppercase sm:inline-flex">
                          <span className="text-emerald-600 dark:text-emerald-300">Improving</span><span className="text-[var(--text-muted)]">·</span><span className="text-rose-600 dark:text-rose-300">Still {kpi.lowerBetter ? 'above' : 'below'} target</span>
                        </span>
                      ) : (
                        <span className="hidden rounded-full bg-current/10 px-2.5 py-1 text-[9px] font-extrabold uppercase sm:inline-flex">{statusLabel[kpi.severity]}</span>
                      )}
                      {isExpanded ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                    </span>
                  </span>

                  <span className="mt-2.5 flex flex-wrap items-center gap-x-2 gap-y-1 border-t border-current/10 pt-2 text-[10px] font-bold text-[var(--text-muted)]">
                    <span className="rounded-md bg-[var(--bg-surface)]/75 px-2 py-1 text-[var(--text-secondary)]">{month}</span>
                    <span>Actual <strong className="text-blue-700 dark:text-blue-300">{formatTeamKpiValue(kpi.actual, kpi.unit)}</strong></span>
                    <span aria-hidden="true">·</span>
                    <span>Best <strong className="text-[var(--text-primary)]">{baselineAvailable ? formatTeamKpiValue(kpi.baselineActual!, kpi.unit) : 'N/A'}</strong>{kpi.baselineMonth && <small className="ml-1 text-[9px] text-[var(--text-faint)]"> {'('}{kpi.baselineMonth}{')'}</small>}</span>
                    <span aria-hidden="true">·</span>
                    <strong className={!baselineAvailable ? 'text-amber-600 dark:text-amber-300' : matchesBest || currentIsBetter ? 'text-emerald-600 dark:text-emerald-300' : 'text-rose-600 dark:text-rose-300'}>{baselinePosition}</strong>
                  </span>
                </button>
                {isExpanded && (
                  <div className="space-y-1.5 border-t border-current/10 bg-[var(--bg-surface)]/35 px-4 py-3 text-[11px] font-medium leading-relaxed text-[var(--text-secondary)]">
                    <p><strong className="text-[var(--text-primary)]">Movement:</strong> {movementStory}</p>
                    <p className={baselineAvailable ? matchesBest || currentIsBetter ? 'text-emerald-600 dark:text-emerald-300' : 'text-rose-600 dark:text-rose-300' : 'text-amber-600 dark:text-amber-300'}><strong>Baseline:</strong> {baselineStory}</p>
                    {kpi.target > 0 && <p><strong className="text-[var(--text-primary)]">Target:</strong> {kpi.lowerBetter ? 'Maximum' : 'Minimum'} {formatTeamKpiValue(kpi.target, kpi.unit)} · Current result is {kpi.targetMet ? 'on target' : 'off target'}.</p>}
                    {kpi.achievement === null && <p className="text-amber-600 dark:text-amber-300">Target is missing or zero. Achievement and weighted gap are unavailable until the configuration is corrected.</p>}
                    {kpi.contribution !== null && kpi.weight !== null && kpi.gapPoints !== null && <p><strong className="text-[var(--text-primary)]">Score impact:</strong> {kpi.contribution.toFixed(1)}% of {(kpi.weight * 100).toFixed(1)}% · Gap {kpi.gapPoints.toFixed(1)}%.</p>}
                    {kpi.volumeData && (() => {
                      const v = kpi.volumeData!;
                      const isBookingRate = kpi.key === 'booking_rate';
                      const currentTotal = isBookingRate ? v.totalBookings : v.totalAttended;
                      const prevTotal = isBookingRate ? v.prevTotalBookings : v.prevTotalAttended;
                      const bestTotal = isBookingRate ? v.bestTotalBookings : v.bestTotalAttended;
                      const bestMonth = isBookingRate ? v.bestTotalBookingsMonth : v.bestTotalAttendedMonth;
                      const delta = prevTotal !== null ? currentTotal - prevTotal : null;
                      const deltaPositive = delta !== null ? delta > 0 : null;
                      const currentTotalOther = isBookingRate ? v.totalAttended : v.totalBookings;
                      const prevTotalOther = isBookingRate ? v.prevTotalAttended : v.prevTotalBookings;
                      const bestTotalOther = isBookingRate ? v.bestTotalAttended : v.bestTotalBookings;
                      const bestMonthOther = isBookingRate ? v.bestTotalAttendedMonth : v.bestTotalBookingsMonth;
                      const deltaOther = prevTotalOther !== null ? currentTotalOther - prevTotalOther : null;
                      const deltaOtherPositive = deltaOther !== null ? deltaOther > 0 : null;
                      const primaryLabel = isBookingRate ? 'Total Bookings' : 'Total Attended';
                      const secondaryLabel = isBookingRate ? 'Total Attended' : 'Total Bookings';
                      return (
                        <div className="mt-2 rounded-lg border border-[var(--border-light)] bg-[var(--bg-sunken)]/50 p-3 space-y-2">
                          <p className="flex items-center gap-1.5 text-[10px] font-extrabold uppercase tracking-wide text-[var(--text-muted)]">
                            <Hash size={10} />
                            Actual Volume Numbers
                          </p>
                          {/* Primary metric row */}
                          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5">
                            <div className="flex flex-col gap-0.5">
                              <span className="text-[9px] font-bold uppercase text-[var(--text-muted)]">{primaryLabel}</span>
                              <span className="text-base font-extrabold tabular-nums text-[var(--text-primary)]">{currentTotal.toLocaleString()}</span>
                              {delta !== null && (
                                <span className={`flex items-center gap-1 text-[10px] font-bold ${deltaPositive ? 'text-emerald-600 dark:text-emerald-400' : delta < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-[var(--text-muted)]'}`}>
                                  {deltaPositive ? <TrendingUp size={10} /> : delta! < 0 ? <TrendingDown size={10} /> : null}
                                  {delta! > 0 ? '+' : ''}{delta!.toLocaleString()} vs last month
                                </span>
                              )}
                              {bestTotal !== null && (
                                <span className="text-[9px] text-[var(--text-muted)]">Best: <strong className="text-[var(--text-secondary)]">{bestTotal.toLocaleString()}</strong>{bestMonth && <span className="ml-1 text-[var(--text-faint)]">{bestMonth}</span>}{bestTotal > 0 && currentTotal > 0 && <span className={`ml-1.5 font-bold ${currentTotal >= bestTotal ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>{currentTotal >= bestTotal ? '🏆 New best' : `${(currentTotal - bestTotal).toLocaleString()} vs best`}</span>}</span>
                              )}
                            </div>
                            <div className="w-px self-stretch bg-[var(--border-light)]" aria-hidden="true" />
                            {/* Secondary metric */}
                            <div className="flex flex-col gap-0.5">
                              <span className="text-[9px] font-bold uppercase text-[var(--text-muted)]">{secondaryLabel}</span>
                              <span className="text-base font-extrabold tabular-nums text-[var(--text-primary)]">{currentTotalOther.toLocaleString()}</span>
                              {deltaOther !== null && (
                                <span className={`flex items-center gap-1 text-[10px] font-bold ${deltaOtherPositive ? 'text-emerald-600 dark:text-emerald-400' : deltaOther! < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-[var(--text-muted)]'}`}>
                                  {deltaOtherPositive ? <TrendingUp size={10} /> : deltaOther! < 0 ? <TrendingDown size={10} /> : null}
                                  {deltaOther! > 0 ? '+' : ''}{deltaOther!.toLocaleString()} vs last month
                                </span>
                              )}
                              {bestTotalOther !== null && (
                                <span className="text-[9px] text-[var(--text-muted)]">Best: <strong className="text-[var(--text-secondary)]">{bestTotalOther.toLocaleString()}</strong>{bestMonthOther && <span className="ml-1 text-[var(--text-faint)]">{bestMonthOther}</span>}{bestTotalOther > 0 && currentTotalOther > 0 && <span className={`ml-1.5 font-bold ${currentTotalOther >= bestTotalOther ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}`}>{currentTotalOther >= bestTotalOther ? '🏆 New best' : `${(currentTotalOther - bestTotalOther).toLocaleString()} vs best`}</span>}</span>
                              )}
                            </div>
                          </div>
                        </div>
                      );
                    })()}
                  </div>
                )}
              </article>
            );
          })}
        </div>
        {attention.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-violet-500/15 bg-violet-500/[0.055] p-3">
            <span className="mr-1 text-[10px] font-extrabold text-violet-700 dark:text-violet-300">Recommended focus</span>
            {attention.slice(0, 3).map((kpi) => <span key={kpi.key} className="rounded-md border border-violet-500/20 bg-[var(--bg-surface)] px-2.5 py-1 text-[9px] font-extrabold text-violet-700 dark:text-violet-300">{buildTeamKpiRecommendation(kpi)}</span>)}
          </div>
        )}
      </div>
    </section>
  );
};
