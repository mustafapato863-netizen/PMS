import { TrendingDown, TrendingUp, Minus } from 'lucide-react';
import type { AgentRecord } from '../../types';
import { getKPIsForAgent, isPreApprovalsIpElectiveTeam, resolvePreApprovalsWorkstream } from '../../types';
import { getProgressColor, getProgressFill } from '../../utils/progressColor';
import { getWeightForLabel, resolveDisplayScore } from '../../utils/kpiScore';

interface KpiBreakdownPanelProps {
  score: number;          // 0-100
  agent: AgentRecord;
  teamWeights?: Record<string, number>;
}

interface KpiBarProps {
  label: string;
  actual: number;
  target: number;
  unit: string;
  isLowerBetter?: boolean;
  color: string;
  achievement?: number;
  actualVolume?: number;
  targetVolume?: number;
  volumeUnit?: string;
  weight?: number;
  contribution?: number;
  targetRequiresReview?: boolean;
}

const KPI_ISSUE_THRESHOLD = 80;

const calculateAchievementPercent = (
  actual: number,
  target: number,
  isLowerBetter: boolean,
  achievementProp?: number,
): number => {
  if (actual === 0 && target === 0) return 0;
  // Use DB-stored achievement ratio when available (already multiplied by 100 in types.ts)
  if (achievementProp !== undefined && Number.isFinite(achievementProp) && achievementProp >= 0) {
    if (isLowerBetter && actual > 0 && target > 0) {
      const numAct = actual > 0 && actual <= 1.0 && target > 1.0 ? actual * 100 : actual;
      const numTgt = target > 0 && target <= 1.0 && actual > 1.0 ? target * 100 : target;
      if (numAct <= numTgt) {
        return Math.max(100, achievementProp);
      }
    }
    return achievementProp;
  }
  if (target <= 0) return 0;
  if (actual === 0 && !isLowerBetter) return 0;
  let numActual = actual;
  let numTarget = target;
  if (numActual > 0 && numActual <= 1.0 && numTarget > 1.0) {
    numActual = numActual * 100;
  } else if (numTarget > 0 && numTarget <= 1.0 && numActual > 1.0) {
    numTarget = numTarget * 100;
  }
  if (isLowerBetter) {
    return numActual <= 0 ? 100 : (numTarget / numActual) * 100;
  }
  return (numActual / numTarget) * 100;
};

const KpiBar = ({ label, actual, target, unit, isLowerBetter = false, color, achievement: achievementProp, actualVolume, targetVolume, volumeUnit, weight, contribution: contributionProp, targetRequiresReview = false }: KpiBarProps) => {
  const achievement = calculateAchievementPercent(actual, target, isLowerBetter, achievementProp);
  const pct = getProgressFill(achievement);
  // Use DB-stored contribution when available (already multiplied by 100 in types.ts), else calculate
  const contribution = contributionProp !== undefined
    ? contributionProp
    : weight !== undefined ? (Math.min(100, achievement) / 100) * weight * 100 : undefined;
  const isMet = !targetRequiresReview && achievement >= 100;

  const statusIcon = targetRequiresReview
    ? <Minus size={12} className="text-slate-500" />
    : isMet
      ? <TrendingUp size={12} className="text-emerald-600" />
      : <TrendingDown size={12} className="text-red-600" />;

  const formatVal = (v: number) => {
    if (unit === 'min') return `${v.toFixed(1)} min`;
    if (unit === 'currency') return `AED ${Math.round(v).toLocaleString()}`;
    if (unit === 'number') return Math.round(v).toLocaleString();
    return v > 1 ? `${v.toFixed(1)}%` : `${(v * 100).toFixed(1)}%`;
  };

  const formatTarget = (v: number) => {
    if (unit === 'min') return `${v.toFixed(1)} min`;
    if (unit === 'currency') return `AED ${Math.round(v).toLocaleString()}`;
    if (unit === 'number') return Math.round(v).toLocaleString();
    return v > 1 ? `${v.toFixed(1)}%` : `${(v * 100).toFixed(1)}%`;
  };

  const displayColor = targetRequiresReview
    ? 'var(--text-muted)'
    : isMet
      ? '#10B981'
      : (color || '#EF4444');

  const barColor = getProgressColor(achievement);

  return (
    <div className="space-y-2.5 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-3">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5 font-bold text-[var(--text-primary)]">
          {statusIcon}
          {label}
        </div>
        <div className="text-right">
          <span className="block font-extrabold text-sm" style={{ color: displayColor }}>{targetRequiresReview ? '—' : `${achievement.toFixed(1)}%`}</span>
          <span className="text-[10px] text-[var(--text-muted)] font-semibold">Achievement</span>
        </div>
      </div>
      <div className="h-2.5 bg-[var(--bg-sunken)] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full"
          style={{ transform: `scaleX(${pct / 100})`, transformOrigin: 'left', transition: 'transform 0.7s', background: barColor }}
        />
      </div>
      <div className="grid grid-cols-2 gap-2 text-[11px]">
        <div className="rounded-lg bg-[var(--bg-sunken)] px-2.5 py-2">
          <div className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] font-bold">Actual</div>
          <div className="font-extrabold text-[var(--text-primary)]">{formatVal(actual)}</div>
          {actualVolume !== undefined && <div className="text-[10px] text-[var(--text-muted)] font-semibold">{actualVolume.toLocaleString()} {volumeUnit || ''}</div>}
        </div>
        <div className="rounded-lg bg-[var(--bg-sunken)] px-2.5 py-2">
          <div className="text-[10px] uppercase tracking-wider text-[var(--text-muted)] font-bold">Target</div>
          <div className="font-extrabold text-[var(--text-primary)]">{formatTarget(target)}</div>
          {targetVolume !== undefined && <div className="text-[10px] text-[var(--text-muted)] font-semibold">{targetVolume.toLocaleString()} {volumeUnit || ''}</div>}
        </div>
      </div>
      <div className="flex items-center justify-between text-[11px]">
        <div className="text-[var(--text-secondary)] font-semibold">
          Contribution
          <span className="ml-1 font-extrabold text-[var(--text-primary)]">{contribution !== undefined ? `${contribution.toFixed(1)}%` : '-'}</span>
        </div>
        {weight !== undefined && (
          <div className="text-[var(--text-secondary)] font-semibold">
            Weight
            <span className="ml-1 font-extrabold text-[var(--text-primary)]">{(weight * 100).toFixed(0)}%</span>
          </div>
        )}
      </div>
    </div>
  );
};

const KpiBreakdownPanel = ({ score: propScore, agent, teamWeights }: KpiBreakdownPanelProps) => {
  const kpis = getKPIsForAgent(agent);

  const calculatedScore = resolveDisplayScore(agent, teamWeights);
  const isScopedPreApprovalsTeam = isPreApprovalsIpElectiveTeam(agent.identity.team);
  const displayScore = isScopedPreApprovalsTeam ? calculatedScore : (calculatedScore || propScore);
  const scoreColor = displayScore >= 90 ? 'var(--color-exceeds)' : displayScore >= 80 ? 'var(--color-meet)' : displayScore >= 70 ? 'var(--color-average)' : 'var(--color-sip)';

  // Dynamic root cause / issue detection
  const issues = Array.from(
    new Set(
      kpis
        .filter((kpi) => {
          const weight = kpi.weight ?? getWeightForLabel(teamWeights, kpi.label, agent.identity.team, agent.raw_data, agent.identity.month);
          if (weight === 0) return false;
          if (kpi.target === 0) return true;
          const ach = calculateAchievementPercent(kpi.actual, kpi.target, !!kpi.isLowerBetter, kpi.achievement);
          return ach < KPI_ISSUE_THRESHOLD;
        })
        .map((kpi) => {
          if (kpi.target === 0) return `Review ${kpi.label} Target`;
          if (kpi.label.includes('Attendance')) return 'Low Attendance';
          if (kpi.label.includes('Booking')) return 'Low Booking Rate';
          if (kpi.label.includes('AHT')) return 'High AHT';
          if (kpi.label.includes('Rejection')) return 'High Rejection';
          if (kpi.label.includes('Error')) return 'High Error Rate';
          if (kpi.label.includes('Submission')) return 'Low Submission Rate';
          if (kpi.label.includes('Quality')) return 'Low Quality Score';
          if (kpi.label.includes('UTZ')) return 'Low UTZ';
          return `Low ${kpi.label}`;
        }),
    ),
  );

  return (
    <div className="space-y-5">
      {isScopedPreApprovalsTeam && (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-blue-500/15 bg-blue-500/5 px-3 py-2.5">
          <div className="min-w-0">
            <div className="text-[10px] font-extrabold uppercase tracking-wider text-blue-600 dark:text-blue-400">Employee workstream</div>
            <div className="truncate text-sm font-bold text-[var(--text-primary)]">{resolvePreApprovalsWorkstream(agent) === 'er' ? 'ER / IP Approval' : 'IP Elective'}</div>
          </div>
          <span className="shrink-0 rounded-full bg-white/70 px-2 py-1 text-[10px] font-bold text-[var(--text-secondary)] dark:bg-slate-800/60">2 KPIs · 60/40</span>
        </div>
      )}
      {/* Overall Score */}
      <div className="flex items-center gap-4">
        <div className="relative w-20 h-20 shrink-0">
          <svg className="w-20 h-20 -rotate-90" viewBox="0 0 36 36">
            <circle cx="18" cy="18" r="15.9" fill="none" stroke="var(--border-light)" strokeWidth="3" />
            <circle
              cx="18" cy="18" r="15.9" fill="none"
              stroke={scoreColor} strokeWidth="3"
              strokeDasharray={`${displayScore} 100`}
              strokeLinecap="round"
            />
          </svg>
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-sm font-extrabold text-[var(--text-primary)]">
              {displayScore.toFixed(0)}%
            </span>
          </div>
        </div>
        <div>
          <div className="text-xs font-bold uppercase tracking-wider text-[var(--text-muted)] mb-1">Performance Score</div>
          <div className="text-2xl font-extrabold" style={{ color: scoreColor }}>{displayScore.toFixed(1)}%</div>
          {issues.length === 0
            ? <div className="text-xs text-emerald-600 dark:text-emerald-400 font-semibold mt-1 flex items-center gap-1"><Minus size={10} /> All KPIs on target</div>
            : <div className="text-xs text-red-500 dark:text-red-400 font-semibold mt-1">⚠ {issues.join(' · ')}</div>
          }
        </div>
      </div>

      <div className="border-t border-[var(--border-light)] pt-4 space-y-4">
        {kpis.map((kpi) => {
          const w = kpi.weight ?? getWeightForLabel(teamWeights, kpi.label, agent.identity.team, agent.raw_data, agent.identity.month);
          return (
            <KpiBar
              key={kpi.label}
              label={kpi.label}
              actual={kpi.actual}
              target={kpi.target}
              unit={kpi.unit}
              isLowerBetter={kpi.isLowerBetter}
              color={kpi.color}
              achievement={kpi.achievement}
              actualVolume={kpi.actualVolume}
              targetVolume={kpi.targetVolume}
              volumeUnit={kpi.volumeUnit}
              weight={w}
              contribution={kpi.contribution}
              targetRequiresReview={kpi.target === 0}
            />
          );
        })}
      </div>
    </div>
  );
};

export default KpiBreakdownPanel;
