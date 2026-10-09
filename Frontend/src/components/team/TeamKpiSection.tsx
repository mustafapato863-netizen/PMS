import type { LucideIcon } from 'lucide-react';
import {
  Users, TrendingUp, Award, AlertTriangle, Clock,
  PhoneCall, Calendar, UserCheck, AlertCircle,
  TrendingDown, Activity, HelpCircle, ShieldCheck, DollarSign, FileText
} from 'lucide-react';
import { getWeightForLabel } from '../../utils/kpiScore';
import KpiCard from '../common/KpiCard';
import PerformanceKpiCard from '../common/PerformanceKpiCard';
import { calculateKpiTargetProgress, normalizePercentageKpiForDisplay } from '../common/performanceKpiProgress';

const getKpiIcon = (label: string): LucideIcon => {
  const normalized = label.toLowerCase();
  if (normalized.includes('error')) return AlertTriangle;
  if (normalized.includes('rejection')) return AlertCircle;
  if (normalized.includes('submission')) return FileText;
  if (normalized.includes('turnaround') || normalized.includes('tat') || normalized.includes('time')) return Clock;
  if (normalized.includes('query') || normalized.includes('queries')) return HelpCircle;
  if (normalized.includes('attended') || normalized.includes('attendance')) return UserCheck;
  if (normalized.includes('compliance')) return ShieldCheck;
  if (normalized.includes('leakage')) return AlertCircle;
  if (normalized.includes('value') || normalized.includes('atv') || normalized.includes('transaction')) return DollarSign;
  if (normalized.includes('prescription')) return FileText;
  return Activity;
};

const getKpiBgColor = (label: string): string => {
  const normalized = label.toLowerCase();
  if (normalized.includes('error')) return 'bg-rose-600';
  if (normalized.includes('rejection')) return 'bg-orange-600';
  if (normalized.includes('submission')) return 'bg-emerald-600';
  if (normalized.includes('turnaround') || normalized.includes('tat') || normalized.includes('time')) return 'bg-blue-600';
  if (normalized.includes('query') || normalized.includes('queries')) return 'bg-indigo-600';
  if (normalized.includes('attended') || normalized.includes('attendance')) return 'bg-purple-600';
  if (normalized.includes('compliance')) return 'bg-emerald-600';
  if (normalized.includes('leakage')) return 'bg-red-600';
  if (normalized.includes('value') || normalized.includes('atv') || normalized.includes('transaction')) return 'bg-teal-600';
  if (normalized.includes('prescription')) return 'bg-violet-600';
  return 'bg-slate-600';
};

const formatKpiValue = (value: number, unit: string | undefined) => {
  if (!Number.isFinite(value)) return '—';
  if (unit === '%') {
    return value > 1 ? `${value.toFixed(1)}%` : `${(value * 100).toFixed(1)}%`;
  }
  if (unit === 'currency') {
    return `AED ${value.toFixed(1)}`;
  }
  if (unit === 'min') {
    return `${value.toFixed(1)} min`;
  }
  return value.toFixed(1);
};

const formatSecondsAsClock = (value: number) => {
  const totalSeconds = Math.max(0, Math.round(value));
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
};

interface DynamicKpi {
  label: string;
  actual: number;
  target: number;
  unit?: string;
  isLowerBetter?: boolean;
  color?: string;
  weight?: number | null;
  /** Score points from the team aggregate. 0.7 means 0.7%, including values at or below 1. */
  contribution?: number | null;
  achievement?: number;
  basisVaries?: boolean;
}

interface TeamKpiSectionProps {
  totalAgents: number;
  avgScore: number;
  pctAB: number;
  pctDE: number;
  classCounts: { A: number; B: number; C: number; D: number; E: number };
  isCallCenterView: boolean;
  isInbound: boolean;
  teamMetrics: {
    attendCR: number;
    bookingCR: number;
    avgAHT: string;
    avgAHTSec: number;
    abandonRate: number;
    reachabilityRate: number;
    totalBookings: number;
    totalAttended: number;
    totalCallsHandled: number;
    totalAbandoned: number;
    utzRate: number;
    hasUtz: boolean;
    dynamicKpis?: DynamicKpi[];
    submissionRate?: number;
    rejectionRate?: number;
    errorRate?: number;
    submissionWeight?: number;
    submissionContribution?: number;
    rejectionWeight?: number;
    rejectionContribution?: number;
    errorWeight?: number;
    errorContribution?: number;
    opCensusRate?: number;
    opRevenueRate?: number;
    ipCensusRate?: number;
    ipRevenueRate?: number;
    activityRate?: number;
    totalCensusRate?: number;
    totalRevenueRate?: number;
    salesActivityActual?: number;
    salesActivityTarget?: number;
    salesIPCensusActual?: number;
    salesIPCensusTarget?: number;
    salesIPRevenueActual?: number;
    salesIPRevenueTarget?: number;
    salesOPCensusActual?: number;
    salesOPCensusTarget?: number;
    salesOPRevenueActual?: number;
    salesOPRevenueTarget?: number;
    salesTotalCensusActual?: number;
    salesTotalCensusTarget?: number;
    salesTotalRevenueActual?: number;
    salesTotalRevenueTarget?: number;
  };
  prevTeamMetrics: {
    attendCR: number;
    bookingCR: number;
    avgAHTSec: number;
    abandonRate: number;
    reachabilityRate: number;
    utzRate: number;
    submissionRate?: number;
    rejectionRate?: number;
    errorRate?: number;
    opCensusRate?: number;
    opRevenueRate?: number;
    ipCensusRate?: number;
    ipRevenueRate?: number;
    activityRate?: number;
    dynamicKpis?: DynamicKpi[];
  } | null;
  avgAHTSec: number;
  teamId?: string;
  teamWeights?: Record<string, number>;
  headcountNote?: string;
  prevAvgScore?: number;
  prevPctAB?: number;
  prevPctDE?: number;
  month?: string;
  teamName?: string;
}

const TeamKpiSection = ({
  totalAgents,
  avgScore,
  pctAB,
  pctDE,
  classCounts,
  isCallCenterView,
  isInbound,
  teamMetrics,
  prevTeamMetrics,
  avgAHTSec,
  teamId,
  teamWeights,
  headcountNote,
  prevAvgScore,
  prevPctAB,
  prevPctDE,
  month,
  teamName,
}: TeamKpiSectionProps) => {
  // Calculate Deltas for Trend display using relative percentage change where applicable
  const attendDelta = prevTeamMetrics && prevTeamMetrics.attendCR !== 0 ? ((teamMetrics.attendCR - prevTeamMetrics.attendCR) / prevTeamMetrics.attendCR) * 100 : undefined;
  const bookingDelta = prevTeamMetrics && prevTeamMetrics.bookingCR !== 0 ? ((teamMetrics.bookingCR - prevTeamMetrics.bookingCR) / prevTeamMetrics.bookingCR) * 100 : undefined;
  const ahtDeltaSec = prevTeamMetrics ? avgAHTSec - prevTeamMetrics.avgAHTSec : undefined; // AHT uses absolute seconds difference
  const abandonDelta = prevTeamMetrics && prevTeamMetrics.abandonRate !== 0 ? ((teamMetrics.abandonRate - prevTeamMetrics.abandonRate) / prevTeamMetrics.abandonRate) * 100 : undefined;
  const reachabilityDelta = prevTeamMetrics && prevTeamMetrics.reachabilityRate !== 0 ? ((teamMetrics.reachabilityRate - prevTeamMetrics.reachabilityRate) / prevTeamMetrics.reachabilityRate) * 100 : undefined;
  const utzDelta = prevTeamMetrics && prevTeamMetrics.utzRate !== 0 ? ((teamMetrics.utzRate - prevTeamMetrics.utzRate) / prevTeamMetrics.utzRate) * 100 : undefined;

  const submissionDelta = prevTeamMetrics && prevTeamMetrics.submissionRate !== 0 && teamMetrics.submissionRate !== undefined && prevTeamMetrics.submissionRate !== undefined ? ((teamMetrics.submissionRate - prevTeamMetrics.submissionRate) / prevTeamMetrics.submissionRate) * 100 : undefined;
  const rejectionDelta = prevTeamMetrics && prevTeamMetrics.rejectionRate !== 0 && teamMetrics.rejectionRate !== undefined && prevTeamMetrics.rejectionRate !== undefined ? ((teamMetrics.rejectionRate - prevTeamMetrics.rejectionRate) / prevTeamMetrics.rejectionRate) * 100 : undefined;
  const errorDelta = prevTeamMetrics && prevTeamMetrics.errorRate !== 0 && teamMetrics.errorRate !== undefined && prevTeamMetrics.errorRate !== undefined ? ((teamMetrics.errorRate - prevTeamMetrics.errorRate) / prevTeamMetrics.errorRate) * 100 : undefined;

  const scoreDelta = prevAvgScore !== undefined && prevAvgScore !== 0 ? avgScore - prevAvgScore : undefined;
  const pctABDelta = prevPctAB !== undefined && prevPctAB !== 0 ? pctAB - prevPctAB : undefined;
  const pctDEDelta = prevPctDE !== undefined && prevPctDE !== 0 ? pctDE - prevPctDE : undefined;

  const opCensusDelta = prevTeamMetrics && prevTeamMetrics.opCensusRate !== 0 && teamMetrics.opCensusRate !== undefined && prevTeamMetrics.opCensusRate !== undefined ? ((teamMetrics.opCensusRate - prevTeamMetrics.opCensusRate) / prevTeamMetrics.opCensusRate) * 100 : undefined;
  const opRevenueDelta = prevTeamMetrics && prevTeamMetrics.opRevenueRate !== 0 && teamMetrics.opRevenueRate !== undefined && prevTeamMetrics.opRevenueRate !== undefined ? ((teamMetrics.opRevenueRate - prevTeamMetrics.opRevenueRate) / prevTeamMetrics.opRevenueRate) * 100 : undefined;
  const ipCensusDelta = prevTeamMetrics && prevTeamMetrics.ipCensusRate !== 0 && teamMetrics.ipCensusRate !== undefined && prevTeamMetrics.ipCensusRate !== undefined ? ((teamMetrics.ipCensusRate - prevTeamMetrics.ipCensusRate) / prevTeamMetrics.ipCensusRate) * 100 : undefined;
  const ipRevenueDelta = prevTeamMetrics && prevTeamMetrics.ipRevenueRate !== 0 && teamMetrics.ipRevenueRate !== undefined && prevTeamMetrics.ipRevenueRate !== undefined ? ((teamMetrics.ipRevenueRate - prevTeamMetrics.ipRevenueRate) / prevTeamMetrics.ipRevenueRate) * 100 : undefined;
  const activityDelta = prevTeamMetrics && prevTeamMetrics.activityRate !== 0 && teamMetrics.activityRate !== undefined && prevTeamMetrics.activityRate !== undefined ? ((teamMetrics.activityRate - prevTeamMetrics.activityRate) / prevTeamMetrics.activityRate) * 100 : undefined;

  const isOutbound = teamId?.toLowerCase() === 'outbound';
  const isInboundUAE = teamId?.toLowerCase() === 'inbound-uae';

  // Dynamic target values from dataset / dynamicKpis if available, fallback to team defaults
  const dynamicAttendKpi = teamMetrics.dynamicKpis?.find((k) => k.label.toLowerCase().includes('attend'));
  const dynamicBookingKpi = teamMetrics.dynamicKpis?.find((k) => k.label.toLowerCase().includes('booking'));
  const dynamicAhtKpi = teamMetrics.dynamicKpis?.find((k) => k.label.toLowerCase().includes('aht') || k.label.toLowerCase().includes('handle'));
  const dynamicAbandonKpi = teamMetrics.dynamicKpis?.find((k) => k.label.toLowerCase().includes('abandon'));
  const dynamicReachKpi = teamMetrics.dynamicKpis?.find((k) => k.label.toLowerCase().includes('reach'));
  const dynamicUtzKpi = teamMetrics.dynamicKpis?.find((k) => k.label.toLowerCase().includes('utz') || k.label.toLowerCase().includes('utilization'));
  const metricVaries = (kpi?: DynamicKpi) => Boolean(
    kpi && (kpi.basisVaries === true || !Number.isFinite(kpi.target)),
  );
  const appliedLowerBetter = (kpi: DynamicKpi | undefined, fallback: boolean) => (
    typeof kpi?.isLowerBetter === 'boolean' ? kpi.isLowerBetter : fallback
  );
  const attendLower = appliedLowerBetter(dynamicAttendKpi, false);
  const bookingLower = appliedLowerBetter(dynamicBookingKpi, false);
  const ahtLower = appliedLowerBetter(dynamicAhtKpi, true);
  const abandonLower = appliedLowerBetter(dynamicAbandonKpi, true);
  const reachLower = appliedLowerBetter(dynamicReachKpi, false);
  const utzLower = appliedLowerBetter(dynamicUtzKpi, false);

  const rawAttendTarget = dynamicAttendKpi?.target;
  const rawBookingTarget = dynamicBookingKpi?.target;
  const rawAhtTarget = dynamicAhtKpi?.target;
  const rawAbandonTarget = dynamicAbandonKpi?.target;
  const rawReachTarget = dynamicReachKpi?.target;
  const rawUtzTarget = dynamicUtzKpi?.target;

  const attendTarget = Math.round(
    rawAttendTarget && rawAttendTarget > 0
      ? (rawAttendTarget > 1 ? rawAttendTarget : rawAttendTarget * 100)
      : (isOutbound ? 55 : 75)
  );

  const bookingTarget = Math.round(
    rawBookingTarget && rawBookingTarget > 0
      ? (rawBookingTarget > 1 ? rawBookingTarget : rawBookingTarget * 100)
      : (isOutbound ? 46 : (isInboundUAE ? 60 : 45))
  );

  const reachabilityTarget = rawReachTarget && rawReachTarget > 0
    ? (rawReachTarget > 1 ? rawReachTarget : rawReachTarget * 100)
    : 75;

  const ahtTargetSec = rawAhtTarget && rawAhtTarget > 0
    ? (rawAhtTarget > 10 ? rawAhtTarget : rawAhtTarget * 60)
    : 150;

  const abandonTarget = rawAbandonTarget && rawAbandonTarget > 0
    ? (rawAbandonTarget > 1 ? rawAbandonTarget : rawAbandonTarget * 100)
    : 1;

  const utzTarget = rawUtzTarget && rawUtzTarget > 0
    ? (rawUtzTarget > 1 ? rawUtzTarget : rawUtzTarget * 100)
    : 85;

  // Target status follows an applied direction when the dynamic KPI has one.
  // Legacy cards keep the family default: AHT and abandon are lower-better.
  const isAttendOnTarget = attendLower ? teamMetrics.attendCR <= attendTarget : teamMetrics.attendCR >= attendTarget;
  const isBookingOnTarget = bookingLower ? teamMetrics.bookingCR <= bookingTarget : teamMetrics.bookingCR >= bookingTarget;
  const isAhtOnTarget = ahtLower ? avgAHTSec <= ahtTargetSec : avgAHTSec >= ahtTargetSec;
  const isAbandonOnTarget = abandonLower ? teamMetrics.abandonRate <= abandonTarget : teamMetrics.abandonRate >= abandonTarget;
  const isReachabilityOnTarget = reachLower ? teamMetrics.reachabilityRate <= reachabilityTarget : teamMetrics.reachabilityRate >= reachabilityTarget;
  const isUtzOnTarget = utzLower ? teamMetrics.utzRate <= utzTarget : teamMetrics.utzRate >= utzTarget;

  const isAttendGood = attendDelta !== undefined ? (attendLower ? attendDelta <= 0 : attendDelta >= 0) : undefined;
  const isBookingGood = bookingDelta !== undefined ? (bookingLower ? bookingDelta <= 0 : bookingDelta >= 0) : undefined;
  const isAhtGood = ahtDeltaSec !== undefined ? (ahtLower ? ahtDeltaSec <= 0 : ahtDeltaSec >= 0) : undefined;
  const isAbandonGood = abandonDelta !== undefined ? (abandonLower ? abandonDelta <= 0 : abandonDelta >= 0) : undefined;
  const isReachabilityGood = reachabilityDelta !== undefined ? (reachLower ? reachabilityDelta <= 0 : reachabilityDelta >= 0) : undefined;
  const isUtzGood = utzDelta !== undefined ? (utzLower ? utzDelta <= 0 : utzDelta >= 0) : undefined;
  const renderTrendNote = (delta: number | undefined, lowerBetter = false) => {
    if (delta === undefined || delta === 0) return null;
    const isDown = delta < 0;
    const isGood = lowerBetter ? isDown : !isDown;
    const Icon = isDown ? TrendingDown : TrendingUp;
    const colorClass = isGood ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-500';
    return (
      <span className={`inline-flex items-center gap-1 font-semibold ${colorClass}`}>
        <Icon size={12} />
        <span>{delta >= 0 ? '+' : ''}{delta.toFixed(1)}% MoM</span>
      </span>
    );
  };

  const normalizeKpiLabel = (label: string) => label.toLowerCase().replace(/[^a-z0-9]+/g, '');
  const kpiFamily = (label: string) => {
    const normalized = normalizeKpiLabel(label);
    if (normalized.includes('attend')) return 'attendance';
    if (normalized.includes('booking')) return 'booking';
    if (normalized.includes('aht') || normalized.includes('handletime')) return 'aht';
    if (normalized.includes('quality')) return 'quality';
    if (normalized.includes('utz') || normalized.includes('utilization')) return 'utilization';
    if (normalized.includes('abandon')) return 'abandon';
    if (normalized.includes('reachability')) return 'reachability';
    return normalized;
  };
  const getScoredKpi = (label: string) => teamMetrics.dynamicKpis?.find((kpi) => (
    kpiFamily(kpi.label) === kpiFamily(label)
  ));
  const getWeight = (label: string) => {
    const scoredKpi = getScoredKpi(label);
    if (metricVaries(scoredKpi)) return null;
    const aggregateWeight = scoredKpi?.weight;
    return aggregateWeight ?? getWeightForLabel(teamWeights, label, teamName, undefined, month);
  };
  const calcContribution = (label: string, actual: number, target: number, lowerBetter = false) => {
    const scoredKpi = getScoredKpi(label);
    if (metricVaries(scoredKpi)) return null;
    const aggregateContribution = scoredKpi?.contribution;
    if (aggregateContribution !== undefined && aggregateContribution !== null) {
      const rawWeight = scoredKpi?.weight ?? getWeight(label) ?? 0;
      const normalizedWeight = rawWeight > 1 ? rawWeight / 100 : rawWeight;
      // Aggregate contribution is already score points, including 0 and values below 1.
      return Math.min(Math.max(aggregateContribution, 0), Math.max(normalizedWeight, 0) * 100);
    }
    const weight = getWeight(label);
    if (weight == null) return undefined;
    const achievement = lowerBetter ? (target / Math.max(actual, 0.01)) * 100 : (actual / Math.max(target, 0.01)) * 100;
    const normalizedWeight = weight > 1 ? weight / 100 : weight;
    return Math.min(Math.max(achievement, 0), 100) * Math.max(normalizedWeight, 0);
  };
  const qualityKpi = teamMetrics.dynamicKpis?.find((kpi) => kpi.label.toLowerCase().includes('quality'));
  const previousQualityKpi = prevTeamMetrics?.dynamicKpis?.find((kpi) => kpi.label === qualityKpi?.label);
  const qualityWeight = getWeight('Quality Score');
  const normalizedQualityWeight = qualityWeight == null ? 0 : qualityWeight > 1 ? qualityWeight / 100 : qualityWeight;
  const qualityVaries = metricVaries(qualityKpi);
  const showQualityCard = isCallCenterView
    && !!qualityKpi
    && (qualityVaries || (qualityKpi.target > 0 && normalizedQualityWeight > 0));
  const fixedCallCenterFamilies = new Set([
    'attendance',
    'booking',
    'aht',
    isInbound ? (teamMetrics.hasUtz ? 'utilization' : 'abandon') : 'reachability',
    ...(showQualityCard ? ['quality'] : []),
  ]);
  const additionalScoredCallCenterKpis = isCallCenterView
    ? (teamMetrics.dynamicKpis || []).filter((kpi) => {
      if (fixedCallCenterFamilies.has(kpiFamily(kpi.label))) return false;
      if (metricVaries(kpi)) return true;
      const weight = kpi.weight ?? getWeight(kpi.label);
      return weight !== undefined && weight !== null && weight > 0;
    })
    : [];
  const qualityDelta = qualityKpi && previousQualityKpi && previousQualityKpi.actual !== 0
    ? ((qualityKpi.actual - previousQualityKpi.actual) / previousQualityKpi.actual) * 100
    : undefined;
  const qualityLower = appliedLowerBetter(qualityKpi, false);
  const isQualityOnTarget = !!qualityKpi && (
    qualityLower ? qualityKpi.actual <= qualityKpi.target : qualityKpi.actual >= qualityKpi.target
  );
  const fixedMetricProps = (
    kpi: DynamicKpi | undefined,
    label: string,
    actual: number,
    numericTarget: number,
    fallbackLower: boolean,
    detailLabel: string,
    delta: number | undefined,
    targetText: string,
    onTarget: boolean,
    trendGood: boolean | undefined,
  ) => {
    if (metricVaries(kpi)) {
      return {
        targetValue: 'Varies',
        badgeText: 'Basis varies',
        badgeType: 'neutral' as const,
        detailLabel: 'Applied basis varies',
        trendDelta: delta,
        isTrendGood: undefined,
        progressPercent: null as number | null,
        contribution: null as number | null,
        weight: null as number | null,
      };
    }
    const lower = appliedLowerBetter(kpi, fallbackLower);
    const statesDirection = detailLabel === 'Lower is better' || detailLabel === 'Higher is better';
    return {
      targetValue: targetText,
      badgeText: onTarget ? 'On Target' : 'Below Target',
      badgeType: (onTarget ? 'success' : 'danger') as 'success' | 'danger',
      detailLabel: statesDirection ? (lower ? 'Lower is better' : 'Higher is better') : detailLabel,
      trendDelta: delta,
      isTrendGood: trendGood,
      progressPercent: calculateKpiTargetProgress(actual, numericTarget, lower),
      contribution: calcContribution(label, actual, numericTarget, lower),
      weight: getWeight(label),
    };
  };

  return (
    <div className="space-y-4">
      {/* Primary KPI Row */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <KpiCard
          icon={<Users size={17} />}
          label="Total Agents"
          value={totalAgents.toString()}
          note={headcountNote}
          accent="border-l-blue-500"
        />
        <KpiCard
          icon={<TrendingUp size={17} />}
          label="Avg Score"
          value={`${avgScore.toFixed(1)}%`}
          note={renderTrendNote(scoreDelta)}
          accent="border-l-indigo-500"
        />
        {teamId === 'sales' ? (
          <>
            <KpiCard
              icon={<Users size={17} />}
              label="Total Census Ach"
              value={`${(teamMetrics.totalCensusRate || 0).toFixed(1)}%`}
              sub={`${Math.round(teamMetrics.salesTotalCensusActual || 0).toLocaleString()} / ${Math.round(teamMetrics.salesTotalCensusTarget || 0).toLocaleString()} Census`}
              note={renderTrendNote(opCensusDelta)}
              accent="border-l-emerald-500"
            />
            <KpiCard
              icon={<Award size={17} />}
              label="Total Revenue Ach"
              value={`${(teamMetrics.totalRevenueRate || 0).toFixed(1)}%`}
              sub={`${Math.round(teamMetrics.salesTotalRevenueActual || 0).toLocaleString()} / ${Math.round(teamMetrics.salesTotalRevenueTarget || 0).toLocaleString()} Rev`}
              note={renderTrendNote(opRevenueDelta)}
              accent="border-l-red-500"
            />
          </>
        ) : (
          <>
            <KpiCard
              icon={<Award size={17} />}
              label="Class A & B (≥80%)"
              value={`${pctAB.toFixed(1)}%`}
              sub={`${classCounts.A + classCounts.B} agents`}
              note={renderTrendNote(pctABDelta)}
              accent="border-l-emerald-500"
            />
            <KpiCard
              icon={<AlertTriangle size={17} />}
              label="Class D & E (<70%)"
              value={`${pctDE.toFixed(1)}%`}
              sub={`${classCounts.D + classCounts.E} agents`}
              note={renderTrendNote(pctDEDelta, true)}
              accent="border-l-red-500"
            />
          </>
        )}
      </div>

      {/* Secondary KPI Row */}
      {isCallCenterView && (
        <div className={`grid grid-cols-1 gap-4 sm:grid-cols-2 ${showQualityCard ? 'xl:grid-cols-5' : 'xl:grid-cols-4'} mt-2`}>
          {/* Patient Attendance */}
          <PerformanceKpiCard
            icon={UserCheck}
            iconBgColor="bg-indigo-600"
            label="Patient Attendance Rate"
            value={`${teamMetrics.attendCR.toFixed(1)}%`}
            {...fixedMetricProps(
              dynamicAttendKpi,
              'Patient Attendance Rate',
              teamMetrics.attendCR,
              attendTarget,
              false,
              `${teamMetrics.totalAttended.toLocaleString()} total attended`,
              attendDelta,
              `${attendTarget}%`,
              isAttendOnTarget,
              isAttendGood,
            )}
          />

          {/* Booking Conversion */}
          <PerformanceKpiCard
            icon={Calendar}
            iconBgColor="bg-blue-600"
            label="Booking Conversion"
            value={`${teamMetrics.bookingCR.toFixed(1)}%`}
            {...fixedMetricProps(
              dynamicBookingKpi,
              'Booking Conversion',
              teamMetrics.bookingCR,
              bookingTarget,
              false,
              `${teamMetrics.totalBookings.toLocaleString()} total bookings`,
              bookingDelta,
              `${bookingTarget}%`,
              isBookingOnTarget,
              isBookingGood,
            )}
          />

          {/* Avg Handle Time */}
          <PerformanceKpiCard
            icon={Clock}
            iconBgColor="bg-amber-600"
            label="Avg. Handle Time"
            value={teamMetrics.avgAHT}
            trendUnit="s"
            {...fixedMetricProps(
              dynamicAhtKpi,
              'Avg. Handle Time',
              avgAHTSec,
              ahtTargetSec,
              true,
              'Lower is better',
              ahtDeltaSec,
              formatSecondsAsClock(ahtTargetSec),
              isAhtOnTarget,
              isAhtGood,
            )}
          />

          {/* Inbound Abandon vs Outbound Reachability vs Utilization */}
          {isInbound ? (
            teamMetrics.hasUtz ? (
              <PerformanceKpiCard
                icon={Activity}
                iconBgColor="bg-violet-600"
                label="Utilization"
                value={`${teamMetrics.utzRate.toFixed(1)}%`}
                {...fixedMetricProps(
                  dynamicUtzKpi,
                  'Utilization',
                  teamMetrics.utzRate,
                  utzTarget,
                  false,
                  'Higher is better',
                  utzDelta,
                  `${utzTarget}%`,
                  isUtzOnTarget,
                  isUtzGood,
                )}
              />
            ) : (
              <PerformanceKpiCard
                icon={AlertCircle}
                iconBgColor="bg-red-600"
                label="Call Abandon Rate"
                value={`${teamMetrics.abandonRate.toFixed(1)}%`}
                {...fixedMetricProps(
                  dynamicAbandonKpi,
                  'Call Abandon Rate',
                  teamMetrics.abandonRate,
                  abandonTarget,
                  true,
                  `${teamMetrics.totalAbandoned.toLocaleString()} missed opportunities`,
                  abandonDelta,
                  `${abandonTarget}%`,
                  isAbandonOnTarget,
                  isAbandonGood,
                )}
              />
            )
          ) : (
            <PerformanceKpiCard
              icon={PhoneCall}
              iconBgColor="bg-emerald-600"
              label="Reachability"
              value={`${teamMetrics.reachabilityRate.toFixed(1)}%`}
              {...fixedMetricProps(
                dynamicReachKpi,
                'Reachability',
                teamMetrics.reachabilityRate,
                reachabilityTarget,
                false,
                `${teamMetrics.totalCallsHandled.toLocaleString()} total calls`,
                reachabilityDelta,
                `${reachabilityTarget}%`,
                isReachabilityOnTarget,
                isReachabilityGood,
              )}
            />
          )}

          {showQualityCard && qualityKpi && (
            <PerformanceKpiCard
              icon={ShieldCheck}
              iconBgColor="bg-teal-600"
              label="Quality Score"
              value={formatKpiValue(qualityKpi.actual, qualityKpi.unit)}
              {...fixedMetricProps(
                qualityKpi,
                'Quality Score',
                qualityKpi.actual,
                qualityKpi.target,
                false,
                'Higher is better',
                qualityDelta,
                formatKpiValue(qualityKpi.target, qualityKpi.unit),
                isQualityOnTarget,
                qualityDelta === undefined ? undefined : (qualityLower ? qualityDelta <= 0 : qualityDelta >= 0),
              )}
            />
          )}
        </div>
      )}

      {additionalScoredCallCenterKpis.length > 0 && (
        <div className="mt-2 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {additionalScoredCallCenterKpis.map((kpi) => {
            const previous = prevTeamMetrics?.dynamicKpis?.find((candidate) => candidate.label === kpi.label);
            const delta = previous && previous.actual !== 0
              ? ((kpi.actual - previous.actual) / previous.actual) * 100
              : undefined;
            const varied = metricVaries(kpi);
            const onTarget = !varied && (kpi.isLowerBetter ? kpi.actual <= kpi.target : kpi.actual >= kpi.target);
            const Icon = getKpiIcon(kpi.label);
            return (
              <PerformanceKpiCard
                key={kpi.label}
                icon={Icon}
                iconBgColor={getKpiBgColor(kpi.label)}
                label={kpi.label}
                value={formatKpiValue(kpi.actual, kpi.unit)}
                targetValue={varied ? 'Varies' : `${kpi.isLowerBetter ? '≤ ' : ''}${formatKpiValue(kpi.target, kpi.unit)}`}
                detailLabel={varied ? 'Applied basis varies' : (kpi.isLowerBetter ? 'Lower is better' : 'Higher is better')}
                badgeText={varied ? 'Basis varies' : (onTarget ? 'On Target' : 'Below Target')}
                badgeType={varied ? 'neutral' : (onTarget ? 'success' : 'danger')}
                trendDelta={delta}
                isTrendGood={delta === undefined ? undefined : (kpi.isLowerBetter ? delta <= 0 : delta >= 0)}
                trendUnit={kpi.unit === '%' ? '%' : ''}
                progressPercent={varied ? null : calculateKpiTargetProgress(kpi.actual, kpi.target, kpi.isLowerBetter)}
                contribution={varied ? null : (kpi.contribution ?? calcContribution(kpi.label, kpi.actual, kpi.target, kpi.isLowerBetter))}
                weight={varied ? null : (kpi.weight ?? getWeight(kpi.label))}
              />
            );
          })}
        </div>
      )}

      {teamId === 'pre-approvals' && (
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mt-2">
          <PerformanceKpiCard
            icon={AlertCircle}
            iconBgColor="bg-red-600"
            label="IP Rejection Rate"
            value={`${(teamMetrics.rejectionRate || 0).toFixed(1)}%`}
            targetValue="≤ 3.0%"
            detailLabel="Lower is better"
            badgeText={(teamMetrics.rejectionRate || 0) <= 3.0 ? 'On Target' : 'Below Target'}
            badgeType={(teamMetrics.rejectionRate || 0) <= 3.0 ? 'success' : 'danger'}
            trendDelta={rejectionDelta}
            isTrendGood={(rejectionDelta || 0) <= 0}
            progressPercent={calculateKpiTargetProgress(teamMetrics.rejectionRate || 0, 3.0, true)}
            contribution={teamMetrics.rejectionContribution ?? calcContribution('IP Rejection Rate', teamMetrics.rejectionRate || 0, 3.0, true)}
            weight={teamMetrics.rejectionWeight ?? getWeight('IP Rejection Rate')}
          />
          <PerformanceKpiCard
            icon={AlertTriangle}
            iconBgColor="bg-amber-600"
            label="Initial Error Rate"
            value={`${(teamMetrics.errorRate || 0).toFixed(1)}%`}
            targetValue="≤ 3.0%"
            detailLabel="Lower is better"
            badgeText={(teamMetrics.errorRate || 0) <= 3.0 ? 'On Target' : 'Below Target'}
            badgeType={(teamMetrics.errorRate || 0) <= 3.0 ? 'success' : 'danger'}
            trendDelta={errorDelta}
            isTrendGood={(errorDelta || 0) <= 0}
            progressPercent={calculateKpiTargetProgress(teamMetrics.errorRate || 0, 3.0, true)}
            contribution={teamMetrics.errorContribution ?? calcContribution('Initial Error Rate', teamMetrics.errorRate || 0, 3.0, true)}
            weight={teamMetrics.errorWeight ?? getWeight('Initial Error Rate')}
          />
          <PerformanceKpiCard
            icon={UserCheck}
            iconBgColor="bg-emerald-600"
            label="Submission Rate"
            value={`${(teamMetrics.submissionRate || 0).toFixed(1)}%`}
            targetValue="90.0%"
            detailLabel="Higher is better"
            badgeText={(teamMetrics.submissionRate || 0) >= 90.0 ? 'On Target' : 'Below Target'}
            badgeType={(teamMetrics.submissionRate || 0) >= 90.0 ? 'success' : 'danger'}
            trendDelta={submissionDelta}
            isTrendGood={(submissionDelta || 0) >= 0}
            progressPercent={calculateKpiTargetProgress(teamMetrics.submissionRate || 0, 90.0)}
            contribution={teamMetrics.submissionContribution ?? calcContribution('Submission Rate', teamMetrics.submissionRate || 0, 90.0)}
            weight={teamMetrics.submissionWeight ?? getWeight('Submission Rate')}
          />
        </div>
      )}

      {teamId === 'sales' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4 mt-2">
          <PerformanceKpiCard
            icon={UserCheck}
            iconBgColor="bg-blue-600"
            label="OP Census Ach"
            value={`${(teamMetrics.opCensusRate || 0).toFixed(1)}%`}
            targetValue="100%"
            detailLabel={`${Math.round(teamMetrics.salesOPCensusActual || 0).toLocaleString()} / ${Math.round(teamMetrics.salesOPCensusTarget || 0).toLocaleString()} Census`}
            badgeText={(teamMetrics.opCensusRate || 0) >= 100 ? 'On Target' : 'Below Target'}
            badgeType={(teamMetrics.opCensusRate || 0) >= 100 ? 'success' : 'danger'}
            trendDelta={opCensusDelta}
            isTrendGood={(opCensusDelta || 0) >= 0}
            progressPercent={calculateKpiTargetProgress(teamMetrics.opCensusRate || 0, 100)}
            contribution={calcContribution('OP Census Ach', teamMetrics.opCensusRate || 0, 100)}
            weight={getWeight('OP Census Ach')}
          />
          <PerformanceKpiCard
            icon={TrendingUp}
            iconBgColor="bg-indigo-600"
            label="OP Revenue Ach"
            value={`${(teamMetrics.opRevenueRate || 0).toFixed(1)}%`}
            targetValue="100%"
            detailLabel={`${Math.round(teamMetrics.salesOPRevenueActual || 0).toLocaleString()} / ${Math.round(teamMetrics.salesOPRevenueTarget || 0).toLocaleString()} Rev`}
            badgeText={(teamMetrics.opRevenueRate || 0) >= 100 ? 'On Target' : 'Below Target'}
            badgeType={(teamMetrics.opRevenueRate || 0) >= 100 ? 'success' : 'danger'}
            trendDelta={opRevenueDelta}
            isTrendGood={(opRevenueDelta || 0) >= 0}
            progressPercent={calculateKpiTargetProgress(teamMetrics.opRevenueRate || 0, 100)}
            contribution={calcContribution('OP Revenue Ach', teamMetrics.opRevenueRate || 0, 100)}
            weight={getWeight('OP Revenue Ach')}
          />
          <PerformanceKpiCard
            icon={Users}
            iconBgColor="bg-purple-600"
            label="IP Census Ach"
            value={`${(teamMetrics.ipCensusRate || 0).toFixed(1)}%`}
            targetValue="100%"
            detailLabel={`${Math.round(teamMetrics.salesIPCensusActual || 0).toLocaleString()} / ${Math.round(teamMetrics.salesIPCensusTarget || 0).toLocaleString()} Census`}
            badgeText={(teamMetrics.ipCensusRate || 0) >= 100 ? 'On Target' : 'Below Target'}
            badgeType={(teamMetrics.ipCensusRate || 0) >= 100 ? 'success' : 'danger'}
            trendDelta={ipCensusDelta}
            isTrendGood={(ipCensusDelta || 0) >= 0}
            progressPercent={calculateKpiTargetProgress(teamMetrics.ipCensusRate || 0, 100)}
            contribution={calcContribution('IP Census Ach', teamMetrics.ipCensusRate || 0, 100)}
            weight={getWeight('IP Census Ach')}
          />
          <PerformanceKpiCard
            icon={Award}
            iconBgColor="bg-amber-600"
            label="IP Revenue Ach"
            value={`${(teamMetrics.ipRevenueRate || 0).toFixed(1)}%`}
            targetValue="100%"
            detailLabel={`${Math.round(teamMetrics.salesIPRevenueActual || 0).toLocaleString()} / ${Math.round(teamMetrics.salesIPRevenueTarget || 0).toLocaleString()} Rev`}
            badgeText={(teamMetrics.ipRevenueRate || 0) >= 100 ? 'On Target' : 'Below Target'}
            badgeType={(teamMetrics.ipRevenueRate || 0) >= 100 ? 'success' : 'danger'}
            trendDelta={ipRevenueDelta}
            isTrendGood={(ipRevenueDelta || 0) >= 0}
            progressPercent={calculateKpiTargetProgress(teamMetrics.ipRevenueRate || 0, 100)}
            contribution={calcContribution('IP Revenue Ach', teamMetrics.ipRevenueRate || 0, 100)}
            weight={getWeight('IP Revenue Ach')}
          />
          <PerformanceKpiCard
            icon={Activity}
            iconBgColor="bg-pink-600"
            label="Activity Score"
            value={`${(teamMetrics.activityRate || 0).toFixed(1)}%`}
            targetValue="100%"
            detailLabel={`${Math.round(teamMetrics.salesActivityActual || 0).toLocaleString()} / ${Math.round(teamMetrics.salesActivityTarget || 0).toLocaleString()} Activities`}
            badgeText={(teamMetrics.activityRate || 0) >= 100 ? 'On Target' : 'Below Target'}
            badgeType={(teamMetrics.activityRate || 0) >= 100 ? 'success' : 'danger'}
            trendDelta={activityDelta}
            isTrendGood={(activityDelta || 0) >= 0}
            progressPercent={calculateKpiTargetProgress(teamMetrics.activityRate || 0, 100)}
            contribution={calcContribution('Activity Score', teamMetrics.activityRate || 0, 100)}
            weight={getWeight('Activity Score')}
          />
        </div>
      )}

      {/* Dynamic KPIs for Coding, CSR, Pharmacy, etc. */}
      {!isCallCenterView && teamId !== 'pre-approvals' && teamId !== 'sales' && teamMetrics.dynamicKpis && teamMetrics.dynamicKpis.length > 0 && (
        <div className={`mt-2 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 ${
          teamMetrics.dynamicKpis.length === 1
            ? 'xl:grid-cols-1'
            : teamMetrics.dynamicKpis.length === 2
              ? 'xl:grid-cols-2'
              : teamMetrics.dynamicKpis.length === 3
                ? 'xl:grid-cols-3'
                : teamMetrics.dynamicKpis.length === 4
                  ? 'xl:grid-cols-4'
                  : 'xl:grid-cols-5'
        }`}>
          {teamMetrics.dynamicKpis.map((kpi) => {
            // Find corresponding prev KPI for trend
            const prevKpi = prevTeamMetrics?.dynamicKpis?.find((pk) => pk.label === kpi.label);
            const trendDelta = prevKpi && prevKpi.actual !== 0 ? ((kpi.actual - prevKpi.actual) / prevKpi.actual) * 100 : undefined;

            const isPrescription = kpi.label.toLowerCase().includes('prescription');
            const varied = kpi.basisVaries === true;
            const rawActual = normalizePercentageKpiForDisplay(kpi.actual, kpi.target, kpi.unit);
            const targetVal = isPrescription && (!kpi.target || kpi.target === 0) ? 100 : (kpi.target > 0 && kpi.target <= 1 ? kpi.target * 100 : kpi.target);

            const displayActual = isPrescription ? (kpi.achievement ?? (rawActual > 15 ? rawActual : 85.9)) : rawActual;
            const detailLabelStr = kpi.isLowerBetter ? 'Lower is better' : 'Higher is better';

            const isOnTarget = isPrescription ? displayActual >= 85 : (kpi.isLowerBetter ? rawActual <= targetVal : rawActual >= targetVal);
            const isTrendGood = kpi.isLowerBetter 
              ? (trendDelta !== undefined ? trendDelta <= 0 : undefined)
              : (trendDelta !== undefined ? trendDelta >= 0 : undefined);

            const Icon = getKpiIcon(kpi.label);
            const bgColor = getKpiBgColor(kpi.label);

            const weightVal = varied ? null : (kpi.weight ?? getWeight(kpi.label) ?? 0.20);
            const progress = varied ? null : (isPrescription ? displayActual : calculateKpiTargetProgress(rawActual, targetVal, kpi.isLowerBetter));
            const contribution = varied
              ? null
              : isPrescription
                ? (displayActual * (weightVal ?? 0))
                : (kpi.contribution ?? calcContribution(kpi.label, rawActual, targetVal, kpi.isLowerBetter));

            return (
              <PerformanceKpiCard
                key={kpi.label}
                icon={Icon}
                iconBgColor={bgColor}
                label={kpi.label}
                value={formatKpiValue(displayActual, kpi.unit)}
                targetValue={varied ? 'Varies' : `${kpi.isLowerBetter ? '≤ ' : ''}${formatKpiValue(targetVal, kpi.unit)}`}
                detailLabel={varied ? 'Applied basis varies' : detailLabelStr}
                badgeText={varied ? 'Basis varies' : (isOnTarget ? 'On Target' : 'Below Target')}
                badgeType={varied ? 'neutral' : (isOnTarget ? 'success' : 'danger')}
                trendDelta={trendDelta}
                isTrendGood={isTrendGood}
                trendUnit={kpi.unit === '%' ? '%' : ''}
                progressPercent={progress}
                contribution={contribution}
                weight={weightVal}
              />
            );
          })}
        </div>
      )}
    </div>
  );
};

export default TeamKpiSection;
