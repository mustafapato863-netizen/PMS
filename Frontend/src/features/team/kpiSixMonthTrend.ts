import type { KpiTrendSeriesPoint } from '../../components/common/PerformanceKpiCard';
import {
  hasRealActivity,
  parseAHTtoSeconds,
} from '../../hooks/usePerformanceData';
import type { TeamConfig } from '../../schemas/teamConfig.schema';
import {
  inboundCallCount,
  type AgentRecord,
  type GeoBreakdown,
  type LocationKey,
} from '../../types';
import { percentPointsFromRatio } from '../../utils/percentForm';
import { aggregatePreApprovalsIpMetrics } from './preApprovalsIpMetrics';
import {
  aggregateConfiguredTeamKpis,
  calculateAggregatedTeamPerformance,
} from './teamKpiAggregator';

function getGeoValue(geo: GeoBreakdown, loc: LocationKey): number {
  if (loc === 'all') return geo.dubai + geo.sharjah + geo.ajman + geo.clinics;
  return geo[loc] || 0;
}

function normalizeKey(label: string): string {
  return label.trim().toLowerCase().replace(/[^a-z0-9]+/g, '');
}

function selectSixMonthWindow(dashboardMonths: string[], activeMonth?: string): string[] {
  if (!dashboardMonths.length) return [];
  if (activeMonth && activeMonth !== 'All') {
    const idx = dashboardMonths.findIndex((m) => m.toLowerCase() === activeMonth.toLowerCase());
    if (idx >= 0) {
      return dashboardMonths.slice(Math.max(0, idx - 5), idx + 1);
    }
  }
  return dashboardMonths.slice(-6);
}

export interface BuildTeamKpiSixMonthTrendsInput {
  agents: AgentRecord[];
  dashboardMonths: string[];
  activeMonth?: string;
  teamConfig: TeamConfig | null;
  location: LocationKey;
  teamId?: string;
  isMergedTeam: boolean;
  isEgyptInbound: boolean;
  isOutbound: boolean;
}

/**
 * Computes a last-6-months Actual vs Target trend map keyed by KPI card label
 * for every KPI card rendered inside TeamKpiSection.
 */
export function buildTeamKpiSixMonthTrends({
  agents,
  dashboardMonths,
  activeMonth,
  teamConfig,
  location,
  teamId,
  isMergedTeam,
  isEgyptInbound,
  isOutbound,
}: BuildTeamKpiSixMonthTrendsInput): Record<string, KpiTrendSeriesPoint[]> {
  const windowMonths = selectSixMonthWindow(dashboardMonths, activeMonth);
  if (!windowMonths.length) return {};

  const seriesMap: Record<string, KpiTrendSeriesPoint[]> = {};
  const ensureSeries = (label: string) => {
    if (!seriesMap[label]) {
      seriesMap[label] = windowMonths.map((m) => ({
        month: m.slice(0, 3),
        actual: null,
        target: null,
      }));
    }
    return seriesMap[label];
  };

  const setPoint = (label: string, monthIndex: number, actual: number | null, target: number | null) => {
    const arr = ensureSeries(label);
    arr[monthIndex] = {
      month: windowMonths[monthIndex].slice(0, 3),
      actual: actual !== null && Number.isFinite(actual) ? actual : null,
      target: target !== null && Number.isFinite(target) ? target : null,
    };
  };

  windowMonths.forEach((monthName, monthIndex) => {
    const monthAgents = agents.filter(
      (agent) => agent.identity.month === monthName && hasRealActivity(agent),
    );
    if (!monthAgents.length) return;

    const configuredKpis =
      calculateAggregatedTeamPerformance(monthAgents, teamConfig, {
        location,
        preferConfiguredWeights: isMergedTeam,
      })?.kpis ??
      aggregateConfiguredTeamKpis(monthAgents, teamConfig, {
        location,
        preferConfiguredWeights: isMergedTeam,
      });

    const configuredByNorm = new Map(
      [...configuredKpis.values()].map((kpi) => [normalizeKey(kpi.label), kpi]),
    );
    const configuredActual = (label: string) => configuredByNorm.get(normalizeKey(label))?.actual;
    const configuredTarget = (label: string) => configuredByNorm.get(normalizeKey(label))?.target;
    const configuredPercent = (label: string) => {
      const value = configuredActual(label);
      return value === undefined ? undefined : percentPointsFromRatio(value);
    };

    // Dynamic KPIs (Coding, CSR, Pharmacy, RCM, Quality Score, additional call-center KPIs, etc.)
    for (const kpi of configuredKpis.values()) {
      if (kpi.basisVaries === true || !Number.isFinite(kpi.target)) continue;
      const isPrescription = kpi.label.toLowerCase().includes('prescription');
      const targetRaw = isPrescription && (!kpi.target || kpi.target === 0) ? 1 : kpi.target;
      const actualVal = isPrescription
        ? (kpi.achievement ?? (percentPointsFromRatio(kpi.actual) > 15 ? percentPointsFromRatio(kpi.actual) : 85.9))
        : kpi.unit === '%'
          ? percentPointsFromRatio(kpi.actual)
          : kpi.actual;
      const targetVal = isPrescription
        ? 85
        : kpi.unit === '%'
          ? percentPointsFromRatio(targetRaw)
          : targetRaw;
      setPoint(kpi.label, monthIndex, actualVal, targetVal);
    }

    // Aggregate raw metrics for Call Center / Pre-Approvals / Sales cards
    let totalBookings = 0;
    let totalAttended = 0;
    let totalCallsHandled = 0;
    let totalInboundCalls = 0;
    let totalAbandoned = 0;
    let totalAHTSeconds = 0;
    let totalReachability = 0;
    let agentsWithReachability = 0;
    let totalUTZ = 0;
    let agentsWithUTZ = 0;
    let totalSubmission = 0;
    let agentsWithSubmission = 0;
    let totalRejection = 0;
    let agentsWithRejection = 0;
    let totalError = 0;
    let agentsWithError = 0;

    let totalOPCensus = 0;
    let agentsWithOPCensus = 0;
    let totalOPRevenue = 0;
    let agentsWithOPRevenue = 0;
    let totalIPCensus = 0;
    let agentsWithIPCensus = 0;
    let totalIPRevenue = 0;
    let agentsWithIPRevenue = 0;
    let totalActivity = 0;
    let agentsWithActivity = 0;

    let salesOPCensusActual = 0;
    let salesOPCensusTarget = 0;
    let salesOPRevenueActual = 0;
    let salesOPRevenueTarget = 0;
    let salesIPCensusActual = 0;
    let salesIPCensusTarget = 0;
    let salesIPRevenueActual = 0;
    let salesIPRevenueTarget = 0;
    let salesActivityActual = 0;
    let salesActivityTarget = 0;

    monthAgents.forEach((agent) => {
      const geoB = agent.geo?.bookings || { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 };
      const geoA = agent.geo?.attended || { dubai: 0, sharjah: 0, ajman: 0, clinics: 0 };
      totalBookings += getGeoValue(geoB, location);
      totalAttended += getGeoValue(geoA, location);

      const calls = agent.calls || { total_handled: 0, inbound: 0, abandoned: 0, aht_raw: '00:00:00' };
      totalCallsHandled += calls.total_handled;
      totalInboundCalls += inboundCallCount(agent);
      totalAbandoned += calls.abandoned;
      totalAHTSeconds += parseAHTtoSeconds(calls.aht_raw || '00:00:00');

      const actual = agent.actual || {};
      if (actual.reachability_rate !== undefined) {
        totalReachability += actual.reachability_rate;
        agentsWithReachability += 1;
      }
      if (actual.utz_rate !== undefined && actual.utz_rate > 0) {
        totalUTZ += actual.utz_rate;
        agentsWithUTZ += 1;
      }
      if (actual.submission_rate !== undefined) {
        totalSubmission += actual.submission_rate;
        agentsWithSubmission += 1;
      }
      if (actual.rejection_rate !== undefined) {
        totalRejection += actual.rejection_rate;
        agentsWithRejection += 1;
      }
      if (actual.initial_error_rate !== undefined) {
        totalError += actual.initial_error_rate;
        agentsWithError += 1;
      }

      const ach = agent.achievement || {};
      if (ach.op_census_ach !== undefined && ach.op_census_ach > 0) {
        totalOPCensus += ach.op_census_ach;
        agentsWithOPCensus += 1;
      } else if (agent.raw_data?.['OPCensusAch%'] !== undefined) {
        totalOPCensus += parseFloat(agent.raw_data['OPCensusAch%']) / 100.0 || 0;
        agentsWithOPCensus += 1;
      }
      if (ach.op_revenue_ach !== undefined && ach.op_revenue_ach > 0) {
        totalOPRevenue += ach.op_revenue_ach;
        agentsWithOPRevenue += 1;
      }
      if (ach.ip_census_ach !== undefined && ach.ip_census_ach > 0) {
        totalIPCensus += ach.ip_census_ach;
        agentsWithIPCensus += 1;
      }
      if (ach.ip_revenue_ach !== undefined && ach.ip_revenue_ach > 0) {
        totalIPRevenue += ach.ip_revenue_ach;
        agentsWithIPRevenue += 1;
      }
      if (ach.activity_ach !== undefined && ach.activity_ach > 0) {
        totalActivity += ach.activity_ach;
        agentsWithActivity += 1;
      }

      if (agent.raw_data) {
        const rd = agent.raw_data;
        salesOPCensusActual += parseFloat(rd['A.OPCensus']) || 0;
        salesOPCensusTarget += parseFloat(rd['T.OPCensus']) || 0;
        salesOPRevenueActual += parseFloat(rd['A.OPRevenue']) || 0;
        salesOPRevenueTarget += parseFloat(rd['T.OPRevenue']) || 0;
        salesIPCensusActual += parseFloat(rd['A.IPCensus']) || 0;
        salesIPCensusTarget += parseFloat(rd['T.IPCensus']) || 0;
        salesIPRevenueActual += parseFloat(rd['A.IPRevenue']) || 0;
        salesIPRevenueTarget += parseFloat(rd['T.IPRevenue']) || 0;
        salesActivityActual +=
          (parseFloat(rd['A.ClinicActivity/AgentActivity']) || 0) +
          (parseFloat(rd['A.CorporateActivity(HealthCheckup)']) || 0) +
          (parseFloat(rd['A.CBDTour']) || 0) +
          (parseFloat(rd['A.ReqularVisits']) || 0);
        salesActivityTarget +=
          (parseFloat(rd['T.ClinicActivity/AgentActivity']) || 0) +
          (parseFloat(rd['T.CorporateActivity(HealthCheckup)']) || 0) +
          (parseFloat(rd['T.CBDTour']) || 0) +
          (parseFloat(rd['T.ReqularVisits']) || 0);
      }
    });

    // Call Center cards
    const dynAttendTgt = configuredTarget('Attendance Rate');
    const attendTarget = Math.round(dynAttendTgt && dynAttendTgt > 0 ? percentPointsFromRatio(dynAttendTgt) : isOutbound ? 55 : 75);
    const attendCR = configuredPercent('Attendance Rate') ?? (totalBookings > 0 ? (totalAttended / totalBookings) * 100 : 0);
    setPoint('Patient Attendance Rate', monthIndex, attendCR, attendTarget);

    const dynBookingTgt = configuredTarget('Booking Rate');
    const bookingTarget = Math.round(dynBookingTgt && dynBookingTgt > 0 ? percentPointsFromRatio(dynBookingTgt) : isOutbound ? 46 : 45);
    const bookingCR = isEgyptInbound
      ? (totalInboundCalls > 0 ? (totalBookings / totalInboundCalls) * 100 : 0)
      : configuredPercent('Booking Rate') ?? (totalCallsHandled > 0 ? (totalBookings / totalCallsHandled) * 100 : 0);
    setPoint('Booking Conversion', monthIndex, bookingCR, bookingTarget);

    const dynAhtMin = configuredActual('AHT (Handle Time)');
    const dynAhtTgt = configuredTarget('AHT (Handle Time)');
    const avgAHTSec = dynAhtMin !== undefined ? dynAhtMin * 60 : totalAHTSeconds / monthAgents.length;
    const ahtTargetSec = dynAhtTgt && dynAhtTgt > 0 ? (dynAhtTgt > 10 ? dynAhtTgt : dynAhtTgt * 60) : 150;
    setPoint('Avg. Handle Time', monthIndex, avgAHTSec, ahtTargetSec);

    const dynAbandonTgt = configuredTarget('Abandon Rate');
    const abandonTarget = dynAbandonTgt && dynAbandonTgt > 0 ? percentPointsFromRatio(dynAbandonTgt) : 1;
    const abandonRate = configuredPercent('Abandon Rate') ?? (totalCallsHandled > 0 ? (totalAbandoned / totalCallsHandled) * 100 : 0);
    setPoint('Call Abandon Rate', monthIndex, abandonRate, abandonTarget);

    const dynReachTgt = configuredTarget('Reachability');
    const reachTarget = dynReachTgt && dynReachTgt > 0 ? percentPointsFromRatio(dynReachTgt) : 75;
    const reachRate = configuredPercent('Reachability') ?? (agentsWithReachability > 0 ? (totalReachability / agentsWithReachability) * 100 : 0);
    setPoint('Reachability', monthIndex, reachRate, reachTarget);

    if (agentsWithUTZ > 0) {
      const dynUtzTgt = configuredTarget('Utilization');
      const utzTarget = dynUtzTgt && dynUtzTgt > 0 ? percentPointsFromRatio(dynUtzTgt) : 85;
      setPoint('Utilization', monthIndex, (totalUTZ / agentsWithUTZ) * 100, utzTarget);
    }

    const qualityKpi = [...configuredKpis.values()].find((k) => k.label.toLowerCase().includes('quality'));
    if (qualityKpi && Number.isFinite(qualityKpi.target)) {
      setPoint(
        'Quality Score',
        monthIndex,
        qualityKpi.unit === '%' ? percentPointsFromRatio(qualityKpi.actual) : qualityKpi.actual,
        qualityKpi.unit === '%' ? percentPointsFromRatio(qualityKpi.target) : qualityKpi.target,
      );
    }

    // Pre-Approvals IP cards
    if (teamId === 'pre-approvals') {
      const preIp = aggregatePreApprovalsIpMetrics(monthAgents);
      const rejectionRate = configuredPercent('Rejection Rate') ?? preIp?.rejectionRate ?? (agentsWithRejection > 0 ? (totalRejection / agentsWithRejection) * 100 : 0);
      const errorRate = configuredPercent('Initial Error Rate') ?? preIp?.errorRate ?? (agentsWithError > 0 ? (totalError / agentsWithError) * 100 : 0);
      const submissionRate = configuredPercent('Submission Rate') ?? preIp?.submissionRate ?? (agentsWithSubmission > 0 ? (totalSubmission / agentsWithSubmission) * 100 : 0);
      setPoint('IP Rejection Rate', monthIndex, rejectionRate, 3.0);
      setPoint('Initial Error Rate', monthIndex, errorRate, 3.0);
      setPoint('Submission Rate', monthIndex, submissionRate, 90.0);
    }

    // Sales cards
    if (teamId === 'sales') {
      const opCensusRate = configuredPercent('OP Census Ach') ?? (salesOPCensusTarget > 0 ? (salesOPCensusActual / salesOPCensusTarget) * 100 : agentsWithOPCensus > 0 ? (totalOPCensus / agentsWithOPCensus) * 100 : 0);
      const opRevenueRate = configuredPercent('OP Revenue Ach') ?? (salesOPRevenueTarget > 0 ? (salesOPRevenueActual / salesOPRevenueTarget) * 100 : agentsWithOPRevenue > 0 ? (totalOPRevenue / agentsWithOPRevenue) * 100 : 0);
      const ipCensusRate = configuredPercent('IP Census Ach') ?? (salesIPCensusTarget > 0 ? (salesIPCensusActual / salesIPCensusTarget) * 100 : agentsWithIPCensus > 0 ? (totalIPCensus / agentsWithIPCensus) * 100 : 0);
      const ipRevenueRate = configuredPercent('IP Revenue Ach') ?? (salesIPRevenueTarget > 0 ? (salesIPRevenueActual / salesIPRevenueTarget) * 100 : agentsWithIPRevenue > 0 ? (totalIPRevenue / agentsWithIPRevenue) * 100 : 0);
      const activityRate = configuredPercent('Activity Score') ?? (salesActivityTarget > 0 ? (salesActivityActual / salesActivityTarget) * 100 : agentsWithActivity > 0 ? (totalActivity / agentsWithActivity) * 100 : 0);

      setPoint('OP Census Ach', monthIndex, opCensusRate, 100);
      setPoint('OP Revenue Ach', monthIndex, opRevenueRate, 100);
      setPoint('IP Census Ach', monthIndex, ipCensusRate, 100);
      setPoint('IP Revenue Ach', monthIndex, ipRevenueRate, 100);
      setPoint('Activity Score', monthIndex, activityRate, 100);
    }
  });

  return seriesMap;
}
