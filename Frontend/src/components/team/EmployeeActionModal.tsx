import { useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { X, Save, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useActionStore } from '../../hooks/useActionStore';
import { useAuth } from '../../context/auth';
import type { ActionType } from '../../types';
import { getKPIsForAgent } from '../../types';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import { getWeightForLabel } from '../../utils/kpiScore';
import { extractKpiMentions, formatKpiMentions } from '../../utils/rootCauseInsights';
import OverlayPortal from '../common/OverlayPortal';

interface EmployeeActionModalProps {
  employee: TeamAgentRow | null;
  month: string;
  teamWeights?: Record<string, number>;
  onClose: () => void;
  onSaved?: () => void;
  editAction?: {
    id: string;
    action_type: ActionType;
    action_text: string;
    root_cause_note: string;
  } | null;
}

const ACTION_TYPES: { value: ActionType; label: string; emoji: string; color: string }[] = [
  { value: 'Training',  label: 'Training',  emoji: '📚', color: 'blue' },
  { value: 'Reward',    label: 'Reward',    emoji: '🏆', color: 'emerald' },
  { value: 'PIP',       label: 'PIP',       emoji: '⚠️',  color: 'red' },
  { value: 'Monitor',   label: 'Monitor',   emoji: '👀', color: 'amber' },
  { value: 'Coaching',  label: 'Coaching',  emoji: '💬', color: 'purple' },
];

const COLOR_MAP: Record<string, string> = {
  blue:    'border-blue-500 bg-blue-500/15 text-blue-700 dark:text-blue-400',
  emerald: 'border-emerald-500 bg-emerald-500/15 text-emerald-700 dark:text-emerald-400',
  red:     'border-red-500 bg-red-500/15 text-red-700 dark:text-red-400',
  amber:   'border-amber-500 bg-amber-500/15 text-amber-700 dark:text-amber-400',
  purple:  'border-purple-500 bg-purple-500/15 text-purple-700 dark:text-purple-400',
};

const KPI_ISSUE_THRESHOLD = 80;

type KpiIssue =
  | 'Attendance'
  | 'Booking'
  | 'AHT'
  | 'Rejection'
  | 'Error'
  | 'Submission'
  | 'Quality'
  | 'UTZ'
  | 'Other';

const getKpiIssue = (label: string): KpiIssue | null => {
  if (label.includes('Attendance')) return 'Attendance';
  if (label.includes('Attended')) return 'Attendance';
  if (label.includes('Booking')) return 'Booking';
  if (label.includes('AHT')) return 'AHT';
  if (label.includes('Rejection')) return 'Rejection';
  if (label.includes('Error')) return 'Error';
  if (label.includes('Submission')) return 'Submission';
  if (label.includes('Quality')) return 'Quality';
  if (label.includes('UTZ')) return 'UTZ';
  return null;
};

const getAchievementPercent = (kpi: ReturnType<typeof getKPIsForAgent>[number]): number => {
  if (kpi.achievement !== undefined && Number.isFinite(kpi.achievement)) {
    return kpi.achievement;
  }
  const denominator = Math.max(kpi.target, 0.01);
  return kpi.isLowerBetter
    ? (kpi.target / Math.max(kpi.actual, 0.01)) * 100
    : (kpi.actual / denominator) * 100;
};

const formatKpiValue = (label: string, actual: number, target: number, unit: string) => {
  if (unit === 'min') return `${actual.toFixed(1)} min / ${target.toFixed(1)} min`;
  if (label.includes('Time')) return `${actual.toFixed(1)} / ${target.toFixed(1)}`;
  if (unit === '%') {
    const normalizePercent = (value: number) => Math.abs(value) <= 1 ? value * 100 : value;
    return `${normalizePercent(actual).toFixed(1)}% / ${normalizePercent(target).toFixed(1)}%`;
  }
  const formattedActual = actual.toLocaleString(undefined, { maximumFractionDigits: 1 });
  const formattedTarget = target.toLocaleString(undefined, { maximumFractionDigits: 1 });
  return `${formattedActual} / ${formattedTarget}`;
};

const EmployeeActionModal = ({ employee, month, teamWeights, onClose, onSaved, editAction }: EmployeeActionModalProps) => {
  const { saveAction, updateAction, isSaving } = useActionStore();
  const { currentUser } = useAuth();
  const [actionType, setActionType] = useState<ActionType>(editAction ? editAction.action_type : 'Coaching');
  const [actionText, setActionText] = useState(editAction ? editAction.action_text : '');
  const [rootCauseNote, setRootCauseNote] = useState(editAction ? editAction.root_cause_note : '');
  const [result, setResult] = useState<{ success: boolean; message: string; synced?: boolean } | null>(null);

  const getScoreColor = (s: number) =>
    s >= 90 ? 'text-emerald-600 dark:text-emerald-400' : s >= 80 ? 'text-blue-600 dark:text-blue-400' : s >= 70 ? 'text-amber-600 dark:text-amber-400' : 'text-red-600 dark:text-red-400';

  const kpis = useMemo(() => (employee ? getKPIsForAgent(employee.raw) : []), [employee]);
  const detectedRootCauseKpis = useMemo(() => extractKpiMentions(rootCauseNote), [rootCauseNote]);
  const failedKpis = useMemo(
    () => {
      if (!employee) return [];
      return kpis.filter((kpi) => {
        const weight = kpi.weight
          ?? getWeightForLabel(teamWeights, kpi.label, employee.team, employee.raw.raw_data, employee.month);
        if (weight === 0) return false;
        return getAchievementPercent(kpi) < KPI_ISSUE_THRESHOLD;
      });
    },
    [employee, teamWeights, kpis]
  );

  const actionPriority = useMemo(() => {
    const priorities = new Map<ActionType, number>();
    if (!employee) return priorities;
    const addPriority = (action: ActionType, weight: number) => {
      priorities.set(action, Math.max(priorities.get(action) ?? 0, weight));
    };

    if (failedKpis.length === 0) {
      addPriority('Reward', 100);
      addPriority('Monitor', 80);
      addPriority('Coaching', 70);
      addPriority('Training', 60);
      addPriority('PIP', 50);
      return priorities;
    }

    failedKpis.forEach((kpi) => {
      const issue = getKpiIssue(kpi.label);
      switch (issue) {
        case 'Attendance':
        case 'Booking':
          addPriority('Coaching', 95);
          addPriority('Training', 90);
          addPriority('Monitor', 80);
          break;
        case 'AHT':
          addPriority('Coaching', 95);
          addPriority('Monitor', 90);
          addPriority('Training', 85);
          break;
        case 'Quality':
          addPriority('Training', 95);
          addPriority('Coaching', 90);
          addPriority('Monitor', 80);
          break;
        case 'Rejection':
        case 'Error':
          addPriority('Training', 95);
          addPriority('PIP', 90);
          addPriority('Monitor', 80);
          break;
        case 'Submission':
          addPriority('Training', 95);
          addPriority('Monitor', 90);
          addPriority('Coaching', 80);
          break;
        case 'UTZ':
          addPriority('Monitor', 95);
          addPriority('Coaching', 90);
          break;
        default:
          addPriority('Coaching', 75);
          addPriority('Monitor', 70);
          break;
      }
    });

    addPriority('Reward', 10);
    return priorities;
  }, [employee, failedKpis]);

  const orderedActionTypes = useMemo(() => {
    return [...ACTION_TYPES].sort((a, b) => (actionPriority.get(b.value) ?? 0) - (actionPriority.get(a.value) ?? 0));
  }, [actionPriority]);

  const recommendedActionLabels = useMemo(
    () => orderedActionTypes.slice(0, 3).map((t) => t.label),
    [orderedActionTypes]
  );

  if (!employee) return null;

  const appendRootCause = (line: string) => {
    setRootCauseNote((prev) => {
      const existing = prev.trim();
      if (!existing) return line;
      if (existing.includes(line)) return existing;
      return `${existing}\n${line}`;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!actionText.trim()) {
      setResult({ success: false, message: 'Please describe the action to take.' });
      return;
    }
    setResult(null);

    const creatorLabel = `${currentUser?.name || 'Unknown'} - ${currentUser?.role || localStorage.getItem('pms_user_role') || 'Manager'}`;
    let res;
    if (editAction) {
      res = await updateAction(
        editAction.id,
        {
          action_type: actionType,
          action_text: actionText.trim(),
          root_cause_note: rootCauseNote.trim(),
        },
        { id: employee.id, name: employee.name, team: employee.team },
        month
      );
    } else {
      res = await saveAction({
        employee_id: employee.id,
        employee_name: employee.name,
        team: employee.team,
        month,
        action_type: actionType,
        action_text: actionText.trim(),
        root_cause_note: rootCauseNote.trim(),
        created_by: creatorLabel,
      });
    }

    setResult(res);
    if (res.success) {
      setTimeout(() => {
        onSaved?.();
        onClose();
      }, 1500);
    }
  };

  return (
    <OverlayPortal>
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-900/50 p-0 backdrop-blur-sm sm:p-4"
        onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      >
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-labelledby="employee-action-dialog-title"
          initial={{ scale: 0.95, y: 20 }}
          animate={{ scale: 1, y: 0 }}
          exit={{ scale: 0.95, y: 20 }}
          transition={{ type: 'spring', damping: 20, stiffness: 200 }}
          className="flex h-full max-h-none w-full max-w-lg flex-col overflow-hidden rounded-none border border-[var(--border-medium)] bg-[var(--bg-surface)] shadow-2xl sm:h-auto sm:max-h-[94vh] sm:rounded-2xl"
        >
          {/* Modal Header */}
          <div className="z-10 flex shrink-0 items-center justify-between border-b border-[var(--border-light)] bg-[var(--bg-sunken)] px-6 py-4">
            <div>
              <h3 id="employee-action-dialog-title" className="text-lg font-bold text-[var(--text-primary)]">
                {editAction ? 'Edit Action for ' : ''}{employee.name}
              </h3>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-xs text-[var(--text-secondary)] font-semibold">{employee.team}</span>
                <span className="text-[var(--text-faint)]">·</span>
                <span className={`text-xs font-extrabold ${getScoreColor(employee.score)}`}>
                  {employee.score.toFixed(1)}%
                </span>
                <span className="text-[var(--text-faint)]">·</span>
                <span className={`grade-badge grade-${employee.gradeClass}`}>{employee.gradeClass}</span>
              </div>
            </div>
            <button
              onClick={onClose}
              aria-label="Close"
              className="p-1.5 hover:bg-[var(--bg-sunken)] rounded-lg text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
            >
              <X size={20} />
            </button>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="custom-scrollbar min-h-0 flex-1 space-y-5 overflow-y-auto p-6">
            {/* Auto Root Cause */}
            <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-3 text-sm">
              <span className="text-xs font-bold text-amber-600 dark:text-amber-400 uppercase tracking-wider">Auto Root Cause:</span>
              <p className="font-semibold text-amber-700 dark:text-amber-300 mt-0.5">{employee.rootCauseAuto}</p>
            </div>

            {/* Root Cause Note */}
            <div>
              <label className="block text-xs font-bold text-[var(--text-secondary)] uppercase tracking-wider mb-1.5">
                Root Cause Note (Leader's Analysis)
              </label>
              <textarea
                value={rootCauseNote}
                onChange={(e) => setRootCauseNote(e.target.value)}
                placeholder="Describe the root cause in detail..."
                rows={2}
                className="w-full bg-[var(--bg-sunken)] border border-[var(--border-medium)] rounded-xl px-3.5 py-2.5 text-sm font-medium focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400 transition-all resize-none text-[var(--text-primary)]"
              />
              <div className="mt-2 text-[11px] font-semibold text-[var(--text-muted)]">
                {detectedRootCauseKpis.length > 0 ? (
                  <>Detected KPIs: <span className="text-[var(--text-primary)]">{formatKpiMentions(rootCauseNote)}</span></>
                ) : (
                  <>Detected KPIs: none yet</>
                )}
              </div>
            </div>

            {/* KPI Gaps */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="block text-xs font-bold text-[var(--text-secondary)] uppercase tracking-wider">
                  KPI Gaps
                </label>
                <span className="text-[10px] font-semibold text-[var(--text-faint)]">
                  Tap to add to root cause
                </span>
              </div>
              <div className="space-y-2 max-h-40 overflow-y-auto pr-1">
                {failedKpis.length === 0 ? (
                  <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 px-3 py-2 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                    All KPIs are meeting target.
                  </div>
                ) : failedKpis.map((kpi) => {
                  const isMet = kpi.isLowerBetter ? kpi.actual <= kpi.target : kpi.actual >= kpi.target;
                  const delta = kpi.isLowerBetter ? kpi.actual - kpi.target : kpi.target - kpi.actual;
                  const line = `${kpi.label}: ${formatKpiValue(kpi.label, kpi.actual, kpi.target, kpi.unit)}`;

                  return (
                    <button
                      key={kpi.label}
                      type="button"
                      onClick={() => appendRootCause(line)}
                      className={`w-full text-left rounded-xl border px-3 py-2 text-sm transition-all cursor-pointer ${
                        isMet
                          ? 'border-emerald-500/20 bg-emerald-500/5 text-emerald-700 dark:text-emerald-400'
                          : 'border-rose-500/20 bg-rose-500/5 text-rose-700 dark:text-rose-400 hover:bg-rose-500/10'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <span className="font-bold">{kpi.label}</span>
                        <span className="text-[11px] font-extrabold uppercase tracking-wider">
                          {kpi.isLowerBetter ? 'Higher than target' : 'Below target'}
                        </span>
                      </div>
                      <div className="mt-1 text-[12px] font-semibold text-[var(--text-muted)]">
                        Actual {formatKpiValue(kpi.label, kpi.actual, kpi.target, kpi.unit)}
                      </div>
                      <div className="mt-0.5 text-[10px] font-medium text-[var(--text-faint)]">
                        Delta {delta > 0 ? '+' : ''}{delta.toFixed(1)} {kpi.unit === 'min' ? 'min' : '%'}
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Action Type */}
            <div>
              <label className="block text-xs font-bold text-[var(--text-secondary)] uppercase tracking-wider mb-2">
                Action Type
              </label>
              <div className="grid grid-cols-5 gap-2">
                {orderedActionTypes.map((t) => (
                  <button
                    key={t.value}
                    type="button"
                    onClick={() => setActionType(t.value)}
                    className={`flex flex-col items-center gap-1 py-2 px-1 rounded-xl border-2 transition-all text-xs font-bold cursor-pointer ${
                      actionType === t.value
                        ? COLOR_MAP[t.color]
                        : 'border-[var(--border-light)] bg-[var(--bg-surface)] text-[var(--text-muted)] hover:border-[var(--border-medium)] hover:bg-[var(--bg-sunken)]'
                    }`}
                    >
                      <span className="text-lg leading-none">{t.emoji}</span>
                      <span>{t.label}</span>
                    </button>
                  ))}
              </div>
              <p className="mt-2 text-[11px] font-semibold text-[var(--text-muted)]">
                Recommended for current KPI gaps: {recommendedActionLabels.join(' · ')}
              </p>
            </div>

            {/* Action Text */}
            <div>
              <label className="block text-xs font-bold text-[var(--text-secondary)] uppercase tracking-wider mb-1.5">
                Action Description
              </label>
              <textarea
                value={actionText}
                onChange={(e) => setActionText(e.target.value)}
                placeholder={`Describe the ${actionType} action in detail...`}
                rows={3}
                className="w-full bg-[var(--bg-sunken)] border border-[var(--border-medium)] rounded-xl px-3.5 py-2.5 text-sm font-medium focus:outline-none focus:border-blue-400 focus:ring-1 focus:ring-blue-400 transition-all resize-none text-[var(--text-primary)]"
              />
            </div>

            {/* Result */}
            {result && (
              <div className={`flex items-start gap-2.5 p-3 rounded-xl text-sm font-semibold ${
                result.success
                  ? 'bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 dark:text-emerald-400'
                  : 'bg-red-500/10 border border-red-500/20 text-red-600 dark:text-red-400'
              }`}>
                {result.success
                  ? <CheckCircle2 size={16} className="shrink-0 mt-0.5" />
                  : <AlertCircle size={16} className="shrink-0 mt-0.5" />
                }
                <div>
                  <p>{result.message}</p>
                  {result.success && !result.synced && (
                    <p className="text-xs mt-0.5 opacity-75">Backend offline — saved locally.</p>
                  )}
                </div>
              </div>
            )}

            {/* Submit */}
            <button
              type="submit"
              disabled={isSaving || !!result?.success}
              className="w-full flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-300 text-white font-bold py-3 px-4 rounded-xl text-sm transition-colors shadow-sm cursor-pointer"
            >
              <Save size={16} />
              {isSaving ? 'Saving...' : editAction ? 'Update Action' : 'Save Action'}
            </button>
          </form>
        </motion.div>
      </motion.div>
    </AnimatePresence>
    </OverlayPortal>
  );
};

export default EmployeeActionModal;
