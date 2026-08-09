import { useState, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'framer-motion';
import { ArrowLeft, User, Plus, AlertTriangle, Loader2 } from 'lucide-react';
import Breadcrumb from '../components/common/Breadcrumb';
import { PageLoadingSkeleton } from '../components/common/SkeletonLoader';
import { usePerformanceData, useTeamData } from '../hooks/usePerformanceData';
import { useActionStore } from '../hooks/useActionStore';
import { useMonthParam } from '../hooks/useMonthParam';
import { usePerformanceLevelParam } from '../hooks/usePerformanceLevelParam';
import { useUserRole } from '../context/RoleContext';
import ScoreTrendChart from '../components/employee/ScoreTrendChart';
import KpiBreakdownPanel from '../components/employee/KpiBreakdownPanel';
import ActionTimeline from '../components/employee/ActionTimeline';
import EmployeeActionModal from '../components/team/EmployeeActionModal';
import type { TeamAgentRow, TeamWeightConfig } from '../hooks/usePerformanceData';
import { getKPIsForAgent, isPreApprovalsIpElectiveTeam, resolvePreApprovalsWorkstream } from '../types';
import type { ActionType, AgentRecord } from '../types';
import { getGradeClass } from '../constants/grades';
import { apiFetch } from '../lib/apiClient';
import { EmployeeStatsSummary } from '../components/employee/EmployeeStatsSummary';
import { calculateRank, calculatePercentile, calculateStability, getPerformanceArchetype, generateRootCauseNarrative } from '../services/employeeAnalytics';
import { normalizeScore } from '../hooks/usePerformanceData';
import { matchesTeamConfig } from '../hooks/api/useKpiWeights';
import { getWeightForLabel, resolveDisplayScore } from '../utils/kpiScore';
import {
  compareEmployeePeriods,
  mergeEmployeeHistory,
  type EmployeeHistoryRecord,
} from '../features/employee/employeeProfileHistory';

interface BackendProfile {
  employee: { id: string; name: string; team: string; status: string };
  performance_history: PerformanceHistoryRecord[];
  corrective_action_history: Array<{
    id?: string;
    manager_action: string;
    manager_notes?: string;
    timestamp?: string;
    month?: string;
  }>;
}

type PerformanceHistoryRecord = EmployeeHistoryRecord;

const getKpiActualVolumes = (label: string, agent: AgentRecord | undefined): string => {
  if (!agent) return '';
  const bookings = (agent.geo?.bookings?.dubai || 0) +
    (agent.geo?.bookings?.sharjah || 0) +
    (agent.geo?.bookings?.ajman || 0) +
    (agent.geo?.bookings?.clinics || 0);
  const attended = (agent.geo?.attended?.dubai || 0) +
    (agent.geo?.attended?.sharjah || 0) +
    (agent.geo?.attended?.ajman || 0) +
    (agent.geo?.attended?.clinics || 0);
  const totalCalls = agent.calls?.total_handled || 0;
  const abandoned = agent.calls?.abandoned || 0;
  const raw = agent.raw_data || {};

  if (label.includes('Attendance')) {
    return `${attended.toLocaleString()} / ${bookings.toLocaleString()}`;
  }
  if (label.includes('Booking')) {
    return `${bookings.toLocaleString()} / ${totalCalls.toLocaleString()}`;
  }
  if (label.includes('Abandon')) {
    const inbound = agent.calls?.inbound || raw['InboundCalls'] || raw['InboundCalls '] || totalCalls;
    return `${abandoned.toLocaleString()} / ${inbound.toLocaleString()}`;
  }
  if (label.includes('Reachability')) {
    const reached = agent.calls?.total_handled || raw['Reached'] || 0;
    const leads = raw['NumOfLeads'] || raw['NumOfLeads '] || 0;
    return `${Number(reached).toLocaleString()} / ${Number(leads).toLocaleString()}`;
  }
  if (label.includes('Rejection')) {
    const rejected = Number(raw['RejectedRequests'] || 0) - Number(raw['PolicyRej'] || 0);
    const assigned = raw['AssignedRequest'] || raw['SubmittedClaims'] || 0;
    return `${Number(rejected).toLocaleString()} / ${Number(assigned).toLocaleString()}`;
  }
  if (label.includes('Initial Error')) {
    const errors = raw['ErrosClaims'] || 0;
    const submitted = raw['SubmittedClaims'] || 0;
    return `${Number(errors).toLocaleString()} / ${Number(submitted).toLocaleString()}`;
  }
  if (label.includes('Submission')) {
    const timely = raw['ApprovalWithin48HR'] || raw['ApprovalWithin48hrs'] || 0;
    const approved = raw['ApprovedRequests'] || 0;
    return `${Number(timely).toLocaleString()} / ${Number(approved).toLocaleString()}`;
  }
  if (label.includes('UTZ')) {
    const prodRaw = raw['ProductiveTime'] || 0;
    const paidRaw = raw['PaidHours'] || 0;
    const convertToHours = (val: number): number => {
      if (val > 1000) return val / 3600;
      if (val > 0 && val <= 24) return val * 24;
      return val;
    };
    const prod = convertToHours(Number(prodRaw));
    const paid = convertToHours(Number(paidRaw));
    if (paid > 0) {
      return `${prod.toFixed(1)} hrs / ${paid.toFixed(1)} hrs`;
    }
    return '';
  }
  // Sales KPIs — derive actual/target from raw_data
  if (label.includes('Total Census')) {
    const a = Number(raw['A.OPCensus'] || 0) + Number(raw['A.IPCensus'] || 0);
    const t = Number(raw['T.OPCensus'] || 0) + Number(raw['T.IPCensus'] || 0);
    return `${Math.round(a).toLocaleString()} / ${Math.round(t).toLocaleString()} Census`;
  }
  if (label.includes('Total Revenue')) {
    const a = Number(raw['A.OPRevenue'] || 0) + Number(raw['A.IPRevenue'] || 0);
    const t = Number(raw['T.OPRevenue'] || 0) + Number(raw['T.IPRevenue'] || 0);
    return `${Math.round(a).toLocaleString()} / ${Math.round(t).toLocaleString()} Rev`;
  }
  if (label.includes('OP Census')) {
    const a = Number(raw['A.OPCensus'] || 0);
    const t = Number(raw['T.OPCensus'] || 0);
    return `${Math.round(a).toLocaleString()} / ${Math.round(t).toLocaleString()} Census`;
  }
  if (label.includes('OP Revenue')) {
    const a = Number(raw['A.OPRevenue'] || 0);
    const t = Number(raw['T.OPRevenue'] || 0);
    return `${Math.round(a).toLocaleString()} / ${Math.round(t).toLocaleString()} Rev`;
  }
  if (label.includes('IP Census')) {
    const a = Number(raw['A.IPCensus'] || 0);
    const t = Number(raw['T.IPCensus'] || 0);
    return `${Math.round(a).toLocaleString()} / ${Math.round(t).toLocaleString()} Census`;
  }
  if (label.includes('IP Revenue')) {
    const a = Number(raw['A.IPRevenue'] || 0);
    const t = Number(raw['T.IPRevenue'] || 0);
    return `${Math.round(a).toLocaleString()} / ${Math.round(t).toLocaleString()} Rev`;
  }
  if (label.includes('Activity Score')) {
    const a = (Number(raw['A.ClinicActivity/AgentActivity'] || 0)) +
      (Number(raw['A.CorporateActivity(HealthCheckup)'] || 0)) +
      (Number(raw['A.CBDTour'] || 0)) +
      (Number(raw['A.ReqularVisits'] || 0));
    const t = (Number(raw['T.ClinicActivity/AgentActivity'] || 0)) +
      (Number(raw['T.CorporateActivity(HealthCheckup)'] || 0)) +
      (Number(raw['T.CBDTour'] || 0)) +
      (Number(raw['T.ReqularVisits'] || 0));
    return `${Math.round(a).toLocaleString()} / ${Math.round(t).toLocaleString()} Activities`;
  }
  return '';
};

const EmployeeProfileView = () => {
  const { employeeId } = useParams<{ employeeId: string }>();
  const navigate = useNavigate();
  const { month } = useMonthParam('All');
  const { performanceLevel } = usePerformanceLevelParam('All');
  const { role } = useUserRole();

  const [weightsList, setWeightsList] = useState<TeamWeightConfig[]>([]);
  useEffect(() => {
    apiFetch<{ success: boolean; data: TeamWeightConfig[] }>('/api/settings/weights')
      .then((res) => {
        if (res?.success) setWeightsList(res.data);
      })
      .catch(() => { });
  }, [role]);

  const { rows } = useTeamData(null, month, 'All', 'all', weightsList, performanceLevel);
  const { agents: allPerformanceAgents } = usePerformanceData('All', 'all', 'All', performanceLevel);
  const employee = useMemo(() => {
    const empRows = rows.filter((r) => r.id === employeeId);
    if (empRows.length === 0) return undefined;

    if (month === 'All') {
      const MONTH_ORDER: Record<string, number> = {
        January: 1, February: 2, March: 3, April: 4, May: 5, June: 6,
        July: 7, August: 8, September: 9, October: 10, November: 11, December: 12
      };
      return [...empRows].sort((a, b) => (MONTH_ORDER[b.month] || 0) - (MONTH_ORDER[a.month] || 0))[0];
    }
    return empRows.find((r) => r.month === month) || empRows[0];
  }, [rows, employeeId, month]);

  const teamWeights = useMemo(() => {
    const teamName = (employee?.team || '').toLowerCase();
    return (
      weightsList.find((w) => {
        return matchesTeamConfig({ team: String(w.team || w.db_name || w.name || '') , weights: w.weights }, teamName);
      })?.weights || {}
    );
  }, [weightsList, employee?.team]);

  const { getActionsForEmployee, deleteAction } = useActionStore();
  const [refreshKey, setRefreshKey] = useState(0);
  const triggerRefresh = () => setRefreshKey((k) => k + 1);

  const localActions = employeeId ? getActionsForEmployee(employeeId) : [];

  const [backendProfile, setBackendProfile] = useState<BackendProfile | null>(null);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [editingAction, setEditingAction] = useState<{
    id: string;
    action_type: ActionType;
    action_text: string;
    root_cause_note: string;
  } | null>(null);

  const [comparisonMode, setComparisonMode] = useState<'actuals' | 'team_avg' | 'team_best' | 'personal_best'>('actuals');

  const comparisonAgent = useMemo(() => {
    if (comparisonMode === 'actuals' || !employee) return undefined;

    if (comparisonMode === 'team_best') {
      const teamMates = rows.filter(r => r.team === employee.team && r.id !== employee.id && r.month === employee.month);
      const sortedMates = [...teamMates].sort((a, b) => b.score - a.score);
      if (sortedMates.length > 0) {
        return sortedMates[0].raw;
      }
    } else if (comparisonMode === 'team_avg') {
      const teamMates = rows.filter(r => r.team === employee.team && r.month === employee.month);
      if (teamMates.length === 0) return undefined;
      const avgScore = teamMates.reduce((acc, r) => acc + r.score, 0) / teamMates.length;

      const syntheticAgent = JSON.parse(JSON.stringify(employee.raw)) as AgentRecord;
      syntheticAgent.identity.name = 'Team Average';
      syntheticAgent.identity.employee_id = 'AVG';
      syntheticAgent.evaluation.score = avgScore / 100;
      syntheticAgent.evaluation.grade = 'Avg';

      const syntheticActual = syntheticAgent.actual as Record<string, number | undefined>;
      Object.keys(syntheticActual).forEach(key => {
        let sum = 0, count = 0;
        teamMates.forEach(m => {
          const actual = m.raw.actual as Record<string, number | undefined>;
          if (actual[key] !== undefined) {
            sum += actual[key] ?? 0;
            count++;
          }
        });
        syntheticActual[key] = count > 0 ? sum / count : 0;
      });

      const syntheticAchievement = syntheticAgent.achievement as Record<string, number | undefined>;
      Object.keys(syntheticAchievement).forEach(key => {
        let sum = 0, count = 0;
        teamMates.forEach(m => {
          const achievement = m.raw.achievement as Record<string, number | undefined>;
          if (achievement[key] !== undefined) {
            sum += achievement[key] ?? 0;
            count++;
          }
        });
        syntheticAchievement[key] = count > 0 ? sum / count : 0;
      });

      return syntheticAgent as AgentRecord;
    } else if (comparisonMode === 'personal_best') {
      const otherMonths = allPerformanceAgents.filter((history) =>
        history.identity.employee_id === employee.id && history.identity.month !== employee.month
      );
      if (otherMonths.length === 0) return undefined;
      const sortedHistory = [...otherMonths].sort((a, b) => {
        const sA = resolveDisplayScore(a, teamWeights);
        const sB = resolveDisplayScore(b, teamWeights);
        return sB - sA;
      });
      return sortedHistory[0];
    }
    return undefined;
  }, [allPerformanceAgents, comparisonMode, employee, rows, teamWeights]);

  // Fetch full profile from backend
  useEffect(() => {
    if (!employeeId) return;
    queueMicrotask(() => setLoadingProfile(true));
    apiFetch<{ success: boolean; data: BackendProfile }>(`/api/employee/${employeeId}`)
      .then((res) => {
        if (res?.success) setBackendProfile(res.data);
      })
      .catch(() => { })
      .finally(() => setLoadingProfile(false));
  }, [employeeId, role, refreshKey]);

  const [benchmarkProfile, setBenchmarkProfile] = useState<BackendProfile | null>(null);

  useEffect(() => {
    if (comparisonMode === 'team_best' && comparisonAgent) {
      const bId = comparisonAgent.identity?.employee_id;
      if (bId) {
        apiFetch<{ success: boolean; data: BackendProfile }>(`/api/employee/${bId}`)
          .then(res => setBenchmarkProfile(res?.data || null))
          .catch(() => { });
      }
    }
  }, [comparisonMode, comparisonAgent, role]);

  const orderedProfileHistory = useMemo(
    () => mergeEmployeeHistory(employeeId, allPerformanceAgents, backendProfile?.performance_history || []),
    [allPerformanceAgents, backendProfile, employeeId],
  );
  const profileHistory = orderedProfileHistory;
  const recentProfileHistory = useMemo(() => orderedProfileHistory.slice(0, 6), [orderedProfileHistory]);
  const currentProfileRecord = useMemo(() => {
    if (!employee || profileHistory.length === 0) return null;
    if (month !== 'All') return profileHistory.find((h) => h.month === month) || null;
    return orderedProfileHistory[0] || null;
  }, [employee, month, orderedProfileHistory, profileHistory]);

  const displayScore = useMemo(() => {
    if (currentProfileRecord) return resolveDisplayScore(currentProfileRecord, teamWeights);
    if (employee) return resolveDisplayScore(employee.raw, teamWeights);
    return 0;
  }, [currentProfileRecord, employee, teamWeights]);

  // The profile endpoint is the canonical historical source when available;
  // the feed row is the safe fallback while it is still loading.
  const profileAgent = currentProfileRecord || employee?.raw;
  const profileScopeLabel = profileAgent && isPreApprovalsIpElectiveTeam(profileAgent.identity.team)
    ? (resolvePreApprovalsWorkstream(profileAgent) === 'er' ? 'ER / IP Approval' : 'IP Elective')
    : currentProfileRecord?.performance_level || employee?.performanceLevel || 'Employee';

  const calculateConsistencyScore = (history: PerformanceHistoryRecord[]) => {
    if (!history.length) return 0;
    const gradePoints: Record<string, number> = {
      A: 100,
      B: 85,
      C: 70,
      D: 55,
      E: 40,
    };
    const total = history.reduce((sum, h) => {
      const grade = String(h?.evaluation?.grade || '').trim().charAt(0).toUpperCase();
      return sum + (gradePoints[grade] ?? 0);
    }, 0);
    return Math.round(total / history.length);
  };

  // Analytics Calculation
  const analytics = useMemo(() => {
    if (!employee || !rows) return null;
    const teamRows = rows.filter(r => r.team === employee.team && r.month === employee.month);
    const rank = calculateRank(employee.id, teamRows);
    const percentile = calculatePercentile(rank, teamRows.length);
    const history = orderedProfileHistory;
    const chronologicalHistory = [...history].sort(compareEmployeePeriods);
    const canonicalHistory = chronologicalHistory.map((record) => ({
      ...record,
      evaluation: {
        ...record.evaluation,
        score: resolveDisplayScore(record, teamWeights),
      },
    }));
    const stability = calculateStability(canonicalHistory);
    const consecutiveGrades = (() => {
      let current = 0;
      for (const record of history) {
        const grade = getGradeClass(resolveDisplayScore(record, teamWeights));
        if (grade === 'A') {
          current += 1;
        } else {
          break;
        }
      }
      return current;
    })();
    const archetype = getPerformanceArchetype(employee, canonicalHistory);

    const gradeDistribution = { A: 0, B: 0, C: 0, D: 0, E: 0 };
    history.forEach(h => {
      const score = resolveDisplayScore(h, teamWeights);
      const g = getGradeClass(score);
      if (gradeDistribution[g as keyof typeof gradeDistribution] !== undefined) {
        gradeDistribution[g as keyof typeof gradeDistribution]++;
      }
    });

    const peakMonth = history.length
      ? history.reduce((best, record) => {
          const currentScore = resolveDisplayScore(record, teamWeights);
          const bestScore = resolveDisplayScore(best, teamWeights);
          return currentScore > bestScore ? record : best;
        }, history[0])
      : null;

    const recentScores = recentProfileHistory.map((h) => resolveDisplayScore(h, teamWeights));
    const avgLast6 = recentScores.length > 0 ? recentScores.reduce((a, b) => a + b, 0) / recentScores.length : displayScore;

    const consistencyScore = calculateConsistencyScore(history);

    const rootCauseNarrative = generateRootCauseNarrative(
      employee,
      comparisonAgent ?? null,
      comparisonMode === 'actuals' ? 'none' : comparisonMode
    );

    return { rank, percentile, teamCount: teamRows.length, stability, consecutiveGrades, peakMonth: peakMonth ? { month: peakMonth.month, score: resolveDisplayScore(peakMonth, teamWeights), grade: getGradeClass(resolveDisplayScore(peakMonth, teamWeights)) } : null, archetype, gradeDistribution, avgLast6, consistencyScore, rootCauseNarrative };
  }, [employee, rows, orderedProfileHistory, recentProfileHistory, comparisonAgent, comparisonMode, teamWeights, displayScore]);

  // Build score trend data from backend history
  const trendData = useMemo(() => {
    const history = orderedProfileHistory;
    return [...history]
      .sort(compareEmployeePeriods)
      .map((h) => {
        const score = resolveDisplayScore(h, teamWeights);
        const isPeak = comparisonMode === 'personal_best' && analytics?.peakMonth?.month === h.month;
        const benchmarkScore =
          comparisonMode === 'team_best' && benchmarkProfile
            ? (() => {
                const bHistory = benchmarkProfile.performance_history.find((bh) => bh.month === h.month);
                return bHistory ? resolveDisplayScore(bHistory, teamWeights) : undefined;
              })()
            : comparisonMode === 'team_avg' && comparisonAgent
              ? resolveDisplayScore(comparisonAgent, teamWeights)
              : comparisonMode === 'personal_best' && comparisonAgent
                ? resolveDisplayScore(comparisonAgent, teamWeights)
                : undefined;

        return {
          month: h.month.slice(0, 3),
          score,
          benchmarkScore,
          isPeak
        };
    });
  }, [orderedProfileHistory, comparisonMode, benchmarkProfile, comparisonAgent, analytics, teamWeights]);
  const gradeColor = (g: TeamAgentRow['gradeClass']) =>
    g === 'A' ? 'text-emerald-600 dark:text-emerald-400' : g === 'B' ? 'text-blue-600 dark:text-blue-400' : g === 'C' ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400';

  const statusColor = (s: string) =>
    s === 'Meet' ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border border-blue-500/20' : s === 'Average' ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20' : 'bg-red-500/10 text-red-500 dark:text-red-400 border border-red-500/20';

  const activeMonth = month === 'All'
    ? (orderedProfileHistory[0]?.month || 'January')
    : month;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.35 }}
      className="max-w-[1600px] mx-auto space-y-6 w-full min-w-0"
    >
      {/* Header */}
      <div className="flex items-center gap-3">
        <button
          onClick={() => navigate(-1)}
          aria-label="Go back"
          className="p-2 hover:bg-[var(--bg-sunken)] rounded-lg text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors cursor-pointer shrink-0"
        >
          <ArrowLeft size={20} />
        </button>
        <div className="flex flex-col gap-1">
          <h2 className="heading-2 leading-tight">Employee Profile</h2>
          <Breadcrumb
            items={[
              { label: 'Dashboard', href: '/executive', icon: 'home' },
              { label: 'Team Performance', href: employee ? `/team/${employee.team.toLowerCase().replace(/\s+/g, '-')}` : '/executive', icon: 'teams' },
              { label: employee?.team || 'Team', icon: 'team' },
              { label: employee?.name || 'Employee', icon: 'employee' },
            ]}
          />
        </div>
      </div>

      {/* Loading state when employee not found yet */}
      {!employee && loadingProfile && (
        <PageLoadingSkeleton variant="detail" label="Loading employee profile" compact />
      )}

      {!employee && !loadingProfile && (
        <div className="glass-panel rounded-xl p-10 text-center">
          <AlertTriangle size={32} className="mx-auto text-amber-400 mb-3" />
          <h3 className="text-lg font-bold text-[var(--text-primary)]">Employee not found</h3>
          <p className="text-sm text-[var(--text-secondary)] mt-1">No data for ID: {employeeId} in selected month.</p>
          <button onClick={() => navigate(-1)} className="mt-4 text-blue-600 dark:text-blue-400 font-semibold text-sm hover:underline cursor-pointer">
            Go back
          </button>
        </div>
      )}

      {employee && (
        <motion.div layout className="grid grid-cols-1 lg:grid-cols-4 gap-6 items-start relative">
          {/* LEFT: Profile Card + KPI Panel */}
          <motion.div layout className="lg:col-span-1 space-y-5">
            {/* Profile Card */}
            <div className="glass-panel rounded-xl p-6 shadow-sm text-center">
              <div className={`w-20 h-20 rounded-full mx-auto mb-4 flex items-center justify-center text-white text-2xl font-extrabold shadow-lg ${employee.gradeClass === 'A' ? 'bg-gradient-to-br from-emerald-400 to-emerald-600'
                : employee.gradeClass === 'B' ? 'bg-gradient-to-br from-blue-400 to-blue-600'
                  : employee.gradeClass === 'C' ? 'bg-gradient-to-br from-amber-400 to-amber-600'
                    : 'bg-gradient-to-br from-red-400 to-red-600'
                }`}>
                {employee.name.charAt(0).toUpperCase()}
              </div>
              <h3 className="mx-auto max-w-[18rem] break-words text-balance text-xl font-bold leading-tight text-[var(--text-primary)]">{employee.name}</h3>
              <p className="text-sm text-[var(--text-secondary)] font-medium mt-1 leading-snug">{employee.team}</p>
              <span className="inline-flex mt-2 rounded-full bg-blue-500/10 px-2.5 py-1 text-xs font-bold text-blue-600 dark:text-blue-400">
                {profileScopeLabel}
              </span>
              <p className="text-xs text-[var(--text-faint)] font-semibold mt-0.5">ID: {employee.id}</p>

              <div className="flex items-center justify-center gap-3 mt-4">
                <div className="text-center">
                  <div className={`text-2xl font-extrabold ${gradeColor(employee.gradeClass)}`}>
                    {displayScore.toFixed(1)}%
                  </div>
                  <div className="text-xs text-[var(--text-secondary)] font-semibold">Score</div>
                </div>
                <div className="w-px h-10 bg-[var(--border-medium)]" />
                <div className="text-center">
                  <div className={`grade-badge grade-${employee.gradeClass} mx-auto text-lg w-10 h-10`}>
                    {employee.gradeClass}
                  </div>
                  <div className="text-xs text-[var(--text-secondary)] font-semibold mt-1">Grade</div>
                </div>
                <div className="w-px h-10 bg-[var(--border-medium)]" />
                <div className="text-center">
                  <span className={`text-xs font-bold px-2.5 py-1 rounded-full ${statusColor(employee.status)}`}>
                    {employee.status}
                  </span>
                  <div className="text-xs text-[var(--text-secondary)] font-semibold mt-1.5">Status</div>
                </div>
              </div>

              {employee.team === 'Sales' && (
                <div className="mt-5 grid grid-cols-2 gap-3">
                  <div className="bg-[var(--bg-sunken)] rounded-lg p-3">
                    <div className="text-xs text-[var(--text-secondary)] font-medium mb-1">Total Census</div>
                    <div className="text-lg font-bold text-[var(--text-primary)]">
                      {Math.round(Number(employee.raw?.raw_data?.['A.TotalCensus'] || employee.raw?.raw_data?.['T.TotalCensus'] || 0)).toLocaleString()}
                    </div>
                  </div>
                  <div className="bg-[var(--bg-sunken)] rounded-lg p-3">
                    <div className="text-xs text-[var(--text-secondary)] font-medium mb-1">Total Revenue</div>
                    <div className="text-lg font-bold text-[var(--text-primary)]">
                      {Math.round(Number(employee.raw?.raw_data?.['A.TotalRevenue'] || employee.raw?.raw_data?.['T.TotalRevenue'] || 0)).toLocaleString()}
                    </div>
                  </div>
                </div>
              )}

              {/* Add Action Button */}
              {(role === 'Admin' || role === 'Manager') && (
                <button
                  onClick={() => setShowModal(true)}
                  className="mt-5 w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-bold py-2.5 px-4 rounded-xl text-sm transition-colors shadow-sm cursor-pointer"
                >
                  <Plus size={16} /> Add Action
                </button>
              )}
            </div>

            {/* KPI Breakdown */}
            <div className="glass-panel rounded-xl p-5 shadow-sm">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-wider">KPI Breakdown</h3>
                  <p className="mt-1 text-[11px] font-medium text-[var(--text-faint)]">Canonical employee score and weighted contribution</p>
                </div>
                {profileAgent && isPreApprovalsIpElectiveTeam(profileAgent.identity.team) && (
                  <span className="shrink-0 rounded-full border border-blue-500/20 bg-blue-500/10 px-2 py-1 text-[10px] font-bold text-blue-600 dark:text-blue-400">Scoped KPIs</span>
                )}
              </div>
              <KpiBreakdownPanel
                score={displayScore}
                agent={profileAgent || employee.raw}
                teamWeights={teamWeights}
              />
            </div>
          </motion.div>

          {/* CENTER: Score Trend + Root Cause */}
          <motion.div
            layout
            className={`${comparisonMode === 'actuals' ? 'lg:col-span-2' : 'lg:col-span-3'} space-y-5`}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
          >
            {/* Football Stats Card Placement */}
            {comparisonMode === 'actuals' && analytics && (
              <EmployeeStatsSummary
                score={displayScore}
                rank={analytics.rank}
                totalEmployees={analytics.teamCount}
                percentile={analytics.percentile}
                bestMonth={analytics.peakMonth?.month}
                bestScore={analytics.peakMonth?.score}
                avgLast6={analytics.avgLast6}
                consecutiveGrades={analytics.consecutiveGrades}
                gradeDistribution={analytics.gradeDistribution}
                stability={analytics.stability}
                consistencyScore={analytics.consistencyScore}
                archetype={analytics.archetype}
              />
            )}

            {/* Comparison Controls */}
            <div className="glass-panel rounded-2xl p-1 shadow-sm flex items-center justify-center max-w-max mx-auto h-[42px] bg-[var(--bg-sunken)] border border-[var(--border-medium)]">
              <div className="flex items-center gap-0.5 w-full h-full">
                {(['actuals', 'team_avg', 'team_best', 'personal_best'] as const).map((mode) => {
                  const label = mode === 'actuals' ? '📊 Actuals' : mode === 'team_avg' ? '📈 Team Avg' : mode === 'team_best' ? '🏆 Team Best' : '⭐ Personal';
                  const isActive = comparisonMode === mode;
                  return (
                    <button
                      key={mode}
                      onClick={() => setComparisonMode(mode)}
                      className={`relative z-10 px-2 sm:px-3 md:px-3.5 py-1 text-[10px] sm:text-[11px] md:text-xs font-extrabold rounded-xl transition-all duration-200 cursor-pointer h-full flex items-center justify-center gap-1 ${isActive
                        ? 'text-blue-600 dark:text-blue-400 bg-white dark:bg-slate-800 shadow-sm border border-[var(--border-light)]'
                        : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-transparent border border-transparent'
                        }`}
                    >
                      <span className="relative z-20 whitespace-nowrap">{label}</span>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Comparison Premium Banner */}
            <AnimatePresence>
              {comparisonAgent && comparisonMode !== 'actuals' && (
                <motion.div
                  initial={{ opacity: 0, y: -10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -10 }}
                  className="p-5 rounded-2xl border bg-gradient-to-r from-blue-500/10 via-indigo-500/5 to-transparent border-blue-500/20 shadow-md backdrop-blur-sm relative overflow-hidden flex flex-col md:flex-row md:items-center justify-between gap-4"
                >
                  <div className="absolute right-0 top-0 w-32 h-32 bg-blue-500/5 rounded-full blur-2xl pointer-events-none" />

                  <div className="flex items-center gap-4 z-10">
                    <div className="w-12 h-12 rounded-xl bg-gradient-to-tr from-blue-500 to-indigo-600 flex items-center justify-center text-white shadow-lg shadow-blue-500/20">
                      <User size={24} />
                    </div>
                    <div>
                      <div className="text-[10px] font-extrabold text-blue-500 uppercase tracking-widest">
                        {comparisonMode === 'personal_best' ? 'Personal Peak Performance' : comparisonMode === 'team_avg' ? 'Team Average Benchmark' : 'Team Elite Benchmark'}
                      </div>
                      <h4 className="text-base font-bold text-[var(--text-primary)] flex items-center gap-2 mt-0.5">
                        {comparisonMode === 'personal_best'
                          ? `${employee.name} (${comparisonAgent.identity?.month || analytics?.peakMonth?.month})`
                          : comparisonAgent.identity?.name || 'Average'}
                        <span className="text-xs font-semibold text-[var(--text-muted)] bg-[var(--bg-sunken)] px-2 py-0.5 rounded">
                          ID: {comparisonAgent.identity?.employee_id || employee.id}
                        </span>
                      </h4>
                      <p className="text-xs text-[var(--text-secondary)] mt-0.5">
                        {comparisonMode === 'personal_best'
                          ? 'Comparing current metrics with your highest-ever performance month'
                          : comparisonMode === 'team_avg'
                            ? `Comparing performance against the average metrics of ${employee.team}`
                            : `Comparing performance against the top performer in ${employee.team}`}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 z-10 border-t md:border-t-0 pt-3 md:pt-0 border-[var(--border-light)] self-end md:self-auto">
                    <div className="text-right">
                      <div className="text-xs text-[var(--text-muted)] font-semibold uppercase">Benchmark Score</div>
                      <div className="text-xl font-extrabold text-indigo-600 dark:text-indigo-400">
                        {(() => {
                          const score = comparisonAgent.evaluation?.score || 0;
                          return normalizeScore(score).toFixed(1);
                        })()}%
                      </div>
                    </div>
                    {comparisonMode !== 'team_avg' && (
                      <>
                        <div className="h-8 w-px bg-[var(--border-medium)]" />
                        <div className="text-center">
                          <div className="text-xs text-[var(--text-muted)] font-semibold uppercase">Grade</div>
                          <div className="grade-badge grade-A text-sm px-2.5 py-0.5 mt-0.5 inline-block">
                            {comparisonAgent.evaluation?.grade?.charAt(0) || 'A'}
                          </div>
                        </div>
                      </>
                    )}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Score Trend Chart */}
            <div className="glass-panel rounded-xl p-5 shadow-sm">
              <h3 className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-wider mb-4">
                Performance Trend
                {loadingProfile && <Loader2 size={12} className="inline ml-2 animate-spin" />}
              </h3>
              <ScoreTrendChart
                data={trendData}
                mode={comparisonMode}
                benchmarkName={comparisonMode === 'team_avg' ? 'Team Average' : comparisonMode === 'team_best' ? 'Team Leader' : 'Peak Score'}
              />
            </div>

            {/* Root Cause Analysis */}
            <div className="glass-panel rounded-xl p-5 shadow-sm">
              <h3 className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-wider mb-4">Root Cause Analysis</h3>

              {comparisonMode !== 'actuals' && (analytics?.rootCauseNarrative?.length ?? 0) > 0 && (
                <div className="mb-5 space-y-2">
                  {analytics?.rootCauseNarrative?.map((narrative: string, idx: number) => (
                    <div key={idx} className="p-3 bg-blue-500/10 border border-blue-500/20 text-blue-700 dark:text-blue-300 rounded-lg text-sm font-medium">
                      {narrative}
                    </div>
                  ))}
                </div>
              )}

              {comparisonMode === 'actuals' && employee.rootCauseAuto && (
                <div className={`p-4 rounded-xl border mb-4 ${employee.rootCauseAuto.includes('good')
                  ? 'bg-emerald-500/10 border-emerald-500/20'
                  : 'bg-amber-500/10 border-amber-500/20'
                  }`}>
                  <div className="text-xs font-bold uppercase tracking-wider text-[var(--text-secondary)] mb-1">Auto Detected</div>
                  <p className={`text-sm font-bold ${employee.rootCauseAuto.includes('good') ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}`}>
                    {employee.rootCauseAuto}
                  </p>
                </div>
              )}

              <div className="space-y-3 text-sm">
                {getKPIsForAgent(profileAgent || employee.raw).map((kpi) => {
                  const isPrescription = kpi.label.toLowerCase().includes('prescription');
                  const targetRequiresReview = !isPrescription && kpi.target === 0;
                  const isMet = !targetRequiresReview && (kpi.isLowerBetter ? kpi.actual <= kpi.target : (isPrescription ? (kpi.achievement ?? kpi.actual) >= 85 : kpi.actual >= kpi.target));
                  const formatVal = (v: number) => {
                    if (kpi.unit === 'min') return `${v.toFixed(1)} min`;
                    if (kpi.unit === 'currency' || kpi.unit === 'number') return v.toLocaleString(undefined, { maximumFractionDigits: 1 });
                    return v > 1 ? `${v.toFixed(1)}%` : `${(v * 100).toFixed(1)}%`;
                  };
                  const formatTarget = (v: number) => {
                    if (kpi.unit === 'min') return `${v.toFixed(1)} min`;
                    if (kpi.unit === 'currency' || kpi.unit === 'number') return v.toLocaleString(undefined, { maximumFractionDigits: 1 });
                    return v > 1 ? `${v.toFixed(1)}%` : `${(v * 100).toFixed(1)}%`;
                  };
                  const weight = kpi.weight ?? getWeightForLabel(teamWeights, kpi.label, (profileAgent || employee.raw).identity.team, (profileAgent || employee.raw).raw_data, (profileAgent || employee.raw).identity.month);
                  const actualVol = getKpiActualVolumes(kpi.label, profileAgent || employee.raw);

                  let compBadge = null;
                  if (comparisonAgent) {
                    const compKpis = getKPIsForAgent(comparisonAgent);
                    const cKpi = compKpis.find(c => c.label === kpi.label);
                    if (cKpi) {
                      const delta = kpi.actual - cKpi.actual;
                      const absDelta = Math.abs(delta);

                      if (absDelta > 0.0001) {
                        const isPositive = kpi.isLowerBetter ? delta < 0 : delta > 0;
                        const formattedDelta = kpi.unit === 'min'
                          ? `${delta > 0 ? '+' : ''}${delta.toFixed(1)} min`
                          : (kpi.unit === 'currency' || kpi.unit === 'number')
                            ? `${delta > 0 ? '+' : ''}${delta.toLocaleString(undefined, { maximumFractionDigits: 1 })}`
                          : `${delta > 0 ? '+' : ''}${(delta * 100).toFixed(1)}%`;

                        const icon = isPositive ? '▲' : '▼';
                        compBadge = (
                          <motion.span
                            initial={{ opacity: 0, scale: 0.9 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className={`inline-flex items-center gap-1 text-[10px] font-extrabold px-2 py-0.5 rounded-full border ${isPositive
                              ? 'bg-emerald-500/10 text-emerald-600 border-emerald-500/20 dark:bg-emerald-500/20 dark:text-emerald-400 dark:border-emerald-500/30'
                              : 'bg-rose-500/10 text-rose-600 border-rose-500/20 dark:bg-rose-500/20 dark:text-rose-400 dark:border-rose-500/30'
                              }`}
                          >
                            <span>{icon}</span>
                            <span className="font-mono">{formattedDelta}</span>
                            <span className="opacity-75 font-normal">vs Best</span>
                          </motion.span>
                        );
                      } else {
                        compBadge = (
                          <motion.span
                            initial={{ opacity: 0, scale: 0.9 }}
                            animate={{ opacity: 1, scale: 1 }}
                            className="inline-flex items-center gap-1 text-[10px] font-extrabold px-2 py-0.5 rounded-full border bg-slate-500/10 text-slate-600 border-slate-500/20 dark:bg-slate-500/20 dark:text-slate-400 dark:border-slate-500/30 font-mono"
                          >
                            <span>Equal</span>
                          </motion.span>
                        );
                      }
                    }
                  }

                  return (
                    <div key={kpi.label} className="flex items-center justify-between py-1 border-b border-[var(--border-light)] last:border-none">
                      <div className="flex flex-col">
                        <span className="text-[var(--text-secondary)] font-semibold">{kpi.label}</span>
                        {weight !== undefined && weight !== null && (
                          <span className="text-[10px] text-[var(--text-faint)] font-medium">
                            Weight: {(weight * 100).toFixed(0)}%
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3">
                        {compBadge && <div className="hidden sm:block">{compBadge}</div>}
                        <div className="flex flex-col items-end gap-0.5">
                          <div className="flex items-center gap-2">
                            <span className={`text-xs font-bold px-2 py-0.5 rounded-md ${
                              targetRequiresReview
                                ? 'border border-slate-500/20 bg-slate-500/10 text-slate-600 dark:text-slate-300'
                                : isMet
                                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                                  : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                            }`}>
                              {formatVal(kpi.actual)}
                            </span>
                            <span className="text-xs text-[var(--text-faint)]">
                              / {formatTarget(kpi.target)}{targetRequiresReview ? ' · Review target' : ''}
                            </span>
                          </div>
                          {actualVol && (
                            <span className="text-[10px] text-[var(--text-muted)] font-bold font-mono">
                              ({actualVol})
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Sales Totals & Team */}
              {employee.team?.toLowerCase() === 'sales' && (
                (() => {
                  const raw = employee.raw?.raw_data || {};
                  const aOPC = Number(raw['A.OPCensus'] || 0);
                  const tOPC = Number(raw['T.OPCensus'] || 0);
                  const aIPC = Number(raw['A.IPCensus'] || 0);
                  const tIPC = Number(raw['T.IPCensus'] || 0);

                  const aOPR = Number(raw['A.OPRevenue'] || 0);
                  const tOPR = Number(raw['T.OPRevenue'] || 0);
                  const aIPR = Number(raw['A.IPRevenue'] || 0);
                  const tIPR = Number(raw['T.IPRevenue'] || 0);

                  const aTotalCensus = aOPC + aIPC;
                  const tTotalCensus = tOPC + tIPC;
                  const aTotalRevenue = aOPR + aIPR;
                  const tTotalRevenue = tOPR + tIPR;

                  const totalCensusAch = tTotalCensus > 0 ? (aTotalCensus / tTotalCensus) * 100 : 0;
                  const totalRevenueAch = tTotalRevenue > 0 ? (aTotalRevenue / tTotalRevenue) * 100 : 0;
                  const territoryTeam = raw['Team'] || raw['Out Team'] || 'N/A';

                  return (
                    <div className="mt-5 pt-4 border-t border-[var(--border-light)] space-y-3">
                      <div className="flex items-center justify-between py-1.5 border-b border-[var(--border-light)] last:border-none">
                        <span className="text-[var(--text-secondary)] font-bold text-xs uppercase tracking-wider">Territory Team</span>
                        <span className="text-xs font-extrabold px-2.5 py-1 rounded-full bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20">
                          {territoryTeam}
                        </span>
                      </div>
                      <div className="flex items-center justify-between py-1 border-b border-[var(--border-light)] last:border-none">
                        <div className="flex flex-col">
                          <span className="text-[var(--text-secondary)] font-bold text-xs uppercase tracking-wider">Total Census</span>
                        </div>
                        <div className="flex flex-col items-end gap-0.5">
                          <div className="flex items-center gap-2">
                            <span className={`text-xs font-bold px-2 py-0.5 rounded-md ${totalCensusAch >= 100
                              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                              : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                              }`}>
                              {totalCensusAch.toFixed(1)}%
                            </span>
                            <span className="text-xs text-[var(--text-faint)]">/ 100%</span>
                          </div>
                          <span className="text-[10px] text-[var(--text-muted)] font-bold font-mono">
                            {Math.round(aTotalCensus).toLocaleString()} / {Math.round(tTotalCensus).toLocaleString()} Census
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center justify-between py-1 border-b border-[var(--border-light)] last:border-none">
                        <div className="flex flex-col">
                          <span className="text-[var(--text-secondary)] font-bold text-xs uppercase tracking-wider">Total Revenue</span>
                        </div>
                        <div className="flex flex-col items-end gap-0.5">
                          <div className="flex items-center gap-2">
                            <span className={`text-xs font-bold px-2 py-0.5 rounded-md ${totalRevenueAch >= 100
                              ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                              : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border border-rose-500/20'
                              }`}>
                              {totalRevenueAch.toFixed(1)}%
                            </span>
                            <span className="text-xs text-[var(--text-faint)]">/ 100%</span>
                          </div>
                          <span className="text-[10px] text-[var(--text-muted)] font-bold font-mono">
                            {Math.round(aTotalRevenue).toLocaleString()} / {Math.round(tTotalRevenue).toLocaleString()} Rev
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })()
              )}

              {employee.rootCauseNote && (
                <div className="mt-4 p-3 bg-[var(--bg-sunken)] border border-[var(--border-light)] rounded-xl">
                  <div className="text-xs font-bold text-[var(--text-muted)] uppercase mb-1">Leader Note</div>
                  <p className="text-sm text-[var(--text-secondary)] font-medium italic">"{employee.rootCauseNote}"</p>
                </div>
              )}
            </div>
          </motion.div>

          {/* RIGHT: Action History */}
          <AnimatePresence mode="popLayout">
            {comparisonMode === 'actuals' && (
              <motion.div
                key="action-history"
                layout
                initial={{ opacity: 0, scale: 0.95, x: 20 }}
                animate={{ opacity: 1, scale: 1, x: 0 }}
                exit={{ opacity: 0, scale: 0.95, x: 20 }}
                transition={{ duration: 0.25 }}
                className="lg:col-span-1 glass-panel rounded-xl p-5 shadow-sm flex flex-col"
              >
                <div className="flex items-center justify-between mb-5">
                  <h3 className="text-sm font-bold text-[var(--text-muted)] uppercase tracking-wider">Action History</h3>
                  {(role === 'Admin' || role === 'Manager') && (
                    <button
                      onClick={() => setShowModal(true)}
                      className="flex items-center gap-1 text-xs font-bold text-blue-600 dark:text-blue-400 hover:underline transition-colors cursor-pointer"
                    >
                      <Plus size={13} /> Add
                    </button>
                  )}
                </div>
                <div className="overflow-y-auto custom-scrollbar flex-1" style={{ maxHeight: '65vh' }}>
                  <ActionTimeline
                    employeeId={employee.id}
                    activeMonth={activeMonth}
                    localActions={localActions}
                    backendActions={backendProfile?.corrective_action_history || []}
                    isLoading={loadingProfile}
                    onEditAction={(action) => {
                      setEditingAction(action);
                      setShowModal(true);
                    }}
                    onDeleteAction={async (actionId) => {
                      await deleteAction(actionId, employee.id);
                      triggerRefresh();
                    }}
                  />
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      )}

      {/* Action Modal */}
      {showModal && employee && (
        <EmployeeActionModal
          employee={employee}
          month={activeMonth}
          teamWeights={teamWeights}
          editAction={editingAction}
          onClose={() => {
            setShowModal(false);
            setEditingAction(null);
          }}
          onSaved={triggerRefresh}
        />
      )}
    </motion.div>
  );
};

export default EmployeeProfileView;
