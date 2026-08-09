import { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  ArrowLeftRight,
  BarChart3,
  Check,
  Copy,
  History,
  Loader2,
  MoreHorizontal,
  Plus,
  Settings,
  User,
  UserX,
  X,
} from 'lucide-react';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import type { PerformanceLevelFilter, PMSAction } from '../../types';
import { getKPIsForAgent } from '../../types';
import { apiFetch } from '../../lib/apiClient';

type DrawerView = 'performance' | 'history' | 'compare' | null;

interface EmployeeRowActionsProps {
  row: TeamAgentRow;
  role: string;
  month: string;
  performanceLevel: PerformanceLevelFilter;
  teamAverage: number;
  actions: PMSAction[];
  onAddAction: (row: TeamAgentRow) => void;
  onEmployeeChanged?: () => void;
}

interface StandardResponse {
  success: boolean;
  message?: string;
}

const formatKpiValue = (value: number, unit: string) => {
  if (unit === '%') return `${(value * 100).toFixed(1)}%`;
  if (unit === 'min') return `${value.toFixed(1)} min`;
  return value.toLocaleString(undefined, { maximumFractionDigits: 1 });
};

const EmployeeRowActions = ({
  row,
  role,
  month,
  performanceLevel,
  teamAverage,
  actions,
  onAddAction,
  onEmployeeChanged,
}: EmployeeRowActionsProps) => {
  const navigate = useNavigate();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ top: 0, left: 0 });
  const [drawer, setDrawer] = useState<DrawerView>(null);
  const [copyNotice, setCopyNotice] = useState<string | null>(null);
  const [showAssignment, setShowAssignment] = useState(false);
  const [showDeactivate, setShowDeactivate] = useState(false);
  const [assignmentTeam, setAssignmentTeam] = useState(row.team);
  const [assignmentLevel, setAssignmentLevel] = useState(row.performanceLevel);
  const [isSaving, setIsSaving] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);
  const isAdmin = role === 'Admin';
  const canManageActions = role === 'Admin' || role === 'Manager';

  const profileUrl = `/employee/${row.id}?month=${encodeURIComponent(month)}&performance_level=${encodeURIComponent(performanceLevel)}`;
  const kpis = useMemo(() => {
    const source = row.raw.kpi_values?.length
      ? row.raw.kpi_values
          .filter((kpi) => kpi.weight_applied > 0)
          .map((kpi) => ({
            label: kpi.label || kpi.kpi_key,
            actual: kpi.actual_value,
            target: kpi.target_value,
            unit: kpi.unit,
            achievement: Math.min(Math.max(kpi.achievement_ratio, 0), 1) * 100,
            contribution: kpi.contribution * 100,
          }))
      : getKPIsForAgent(row.raw).map((kpi) => ({
          label: kpi.label,
          actual: kpi.actual,
          target: kpi.target,
          unit: kpi.unit,
          achievement: kpi.achievement ?? (
            kpi.isLowerBetter
              ? (kpi.target / Math.max(kpi.actual, 0.01)) * 100
              : (kpi.actual / Math.max(kpi.target, 0.01)) * 100
          ),
          contribution: undefined,
        }));
    return source;
  }, [row.raw]);

  useEffect(() => {
    if (!menuOpen) return;
    const closeMenu = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!menuRef.current?.contains(target) && !buttonRef.current?.contains(target)) {
        setMenuOpen(false);
      }
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMenuOpen(false);
    };
    const closeOnViewportChange = () => setMenuOpen(false);
    document.addEventListener('mousedown', closeMenu);
    document.addEventListener('keydown', closeOnEscape);
    window.addEventListener('resize', closeOnViewportChange);
    window.addEventListener('scroll', closeOnViewportChange, true);
    return () => {
      document.removeEventListener('mousedown', closeMenu);
      document.removeEventListener('keydown', closeOnEscape);
      window.removeEventListener('resize', closeOnViewportChange);
      window.removeEventListener('scroll', closeOnViewportChange, true);
    };
  }, [menuOpen]);

  const toggleMenu = () => {
    if (!menuOpen && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      const width = 272;
      const estimatedHeight = isAdmin ? 390 : 300;
      setMenuPosition({
        left: Math.max(12, Math.min(rect.right - width, window.innerWidth - width - 12)),
        top: rect.bottom + estimatedHeight > window.innerHeight
          ? Math.max(12, rect.top - estimatedHeight - 8)
          : rect.bottom + 8,
      });
    }
    setMenuOpen((open) => !open);
  };

  const openDrawer = (view: Exclude<DrawerView, null>) => {
    setMenuOpen(false);
    setDrawer(view);
  };

  const copyEmployeeId = async () => {
    try {
      await navigator.clipboard.writeText(row.id);
      setCopyNotice('Employee ID copied');
      setMenuOpen(false);
      window.setTimeout(() => setCopyNotice(null), 1800);
    } catch {
      setCopyNotice('Clipboard access was blocked');
      setMenuOpen(false);
      window.setTimeout(() => setCopyNotice(null), 2200);
    }
  };

  const saveAssignment = async () => {
    setIsSaving(true);
    setFeedback(null);
    try {
      const params = new URLSearchParams({ team: assignmentTeam, performance_level: assignmentLevel });
      const response = await apiFetch<StandardResponse>(`/api/employee/${encodeURIComponent(row.id)}/assignment?${params}`, {
        method: 'PUT',
      });
      if (!response.success) throw new Error(response.message || 'Assignment update failed');
      setFeedback('Assignment updated successfully.');
      onEmployeeChanged?.();
      window.setTimeout(() => setShowAssignment(false), 700);
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : 'Assignment update failed');
    } finally {
      setIsSaving(false);
    }
  };

  const deactivateEmployee = async () => {
    setIsSaving(true);
    setFeedback(null);
    try {
      const response = await apiFetch<StandardResponse>(`/api/employee/${encodeURIComponent(row.id)}`, {
        method: 'DELETE',
      });
      if (!response.success) throw new Error(response.message || 'Employee deactivation failed');
      setFeedback('Employee deactivated. Historical performance was preserved.');
      onEmployeeChanged?.();
      window.setTimeout(() => setShowDeactivate(false), 900);
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : 'Employee deactivation failed');
    } finally {
      setIsSaving(false);
    }
  };

  const menuItemClass = 'flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-xs font-bold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-sunken)] hover:text-[var(--text-primary)]';

  return (
    <>
      <button
        ref={buttonRef}
        onClick={toggleMenu}
        className="flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border-medium)] bg-[var(--bg-surface)] text-[var(--text-secondary)] shadow-sm transition-colors hover:border-blue-400 hover:text-blue-600"
        aria-label={`Open actions for ${row.name}`}
        aria-haspopup="menu"
        aria-expanded={menuOpen}
      >
        <MoreHorizontal size={17} />
      </button>

      {copyNotice && createPortal(
        <div className="fixed bottom-5 left-1/2 z-[120] flex -translate-x-1/2 items-center gap-2 rounded-xl bg-slate-950 px-4 py-2.5 text-xs font-bold text-white shadow-xl">
          <Check size={15} className="text-emerald-400" /> {copyNotice}
        </div>,
        document.body,
      )}

      {menuOpen && createPortal(
        <div
          ref={menuRef}
          role="menu"
          className="fixed z-[110] w-[272px] rounded-2xl border border-[var(--border-medium)] bg-[var(--bg-surface)] p-2 shadow-2xl shadow-slate-900/15"
          style={menuPosition}
        >
          <button className={menuItemClass} onClick={() => navigate(profileUrl)} role="menuitem">
            <User size={16} className="text-blue-500" /> View Employee Profile
          </button>
          <button className={menuItemClass} onClick={() => openDrawer('performance')} role="menuitem">
            <BarChart3 size={16} className="text-violet-500" /> View Performance Details
          </button>
          <div className="my-1 border-t border-[var(--border-light)]" />
          {canManageActions && (
            <button className={menuItemClass} onClick={() => { setMenuOpen(false); onAddAction(row); }} role="menuitem">
              <Plus size={16} className="text-emerald-500" /> Add Corrective Action
            </button>
          )}
          <button className={menuItemClass} onClick={() => openDrawer('history')} role="menuitem">
            <History size={16} className="text-amber-500" /> View Action History
          </button>
          <div className="my-1 border-t border-[var(--border-light)]" />
          <button className={menuItemClass} onClick={() => openDrawer('compare')} role="menuitem">
            <ArrowLeftRight size={16} className="text-cyan-500" /> Compare with Team Average
          </button>
          <button className={menuItemClass} onClick={copyEmployeeId} role="menuitem">
            <Copy size={16} className="text-slate-500" /> Copy Employee ID
          </button>
          {isAdmin && (
            <>
              <div className="my-1 border-t border-[var(--border-light)]" />
              <button className={menuItemClass} onClick={() => { setMenuOpen(false); setFeedback(null); setShowAssignment(true); }} role="menuitem">
                <Settings size={16} className="text-blue-500" /> Edit Employee Assignment
              </button>
              <button className={`${menuItemClass} text-rose-600 hover:bg-rose-500/10 hover:text-rose-600`} onClick={() => { setMenuOpen(false); setFeedback(null); setShowDeactivate(true); }} role="menuitem">
                <UserX size={16} /> Deactivate Employee
              </button>
            </>
          )}
        </div>,
        document.body,
      )}

      {drawer && createPortal(
        <div className="fixed inset-0 z-[100] flex justify-end bg-slate-950/35 backdrop-blur-[2px]" onMouseDown={() => setDrawer(null)}>
          <aside className="h-full w-full max-w-md overflow-y-auto border-l border-[var(--border-medium)] bg-[var(--bg-surface)] p-5 shadow-2xl" onMouseDown={(event) => event.stopPropagation()}>
            <div className="mb-6 flex items-start justify-between gap-4">
              <div>
                <p className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-blue-500">{row.id}</p>
                <h3 className="mt-1 text-lg font-extrabold text-[var(--text-primary)]">{row.name}</h3>
                <p className="mt-1 text-xs font-semibold text-[var(--text-secondary)]">{row.team} / {month}</p>
              </div>
              <button onClick={() => setDrawer(null)} className="rounded-lg border border-[var(--border-medium)] p-2 text-[var(--text-secondary)] hover:bg-[var(--bg-sunken)]" aria-label="Close drawer">
                <X size={18} />
              </button>
            </div>

            {drawer === 'performance' && (
              <div className="space-y-3">
                <div className={`score-grade-${row.gradeClass} flex items-center justify-between rounded-2xl border p-4`}>
                  <div>
                    <p className="text-[10px] font-extrabold uppercase tracking-wider opacity-75">Monthly score</p>
                    <p className="mt-1 text-3xl font-black">{row.score.toFixed(1)}%</p>
                  </div>
                  <span className={`grade-badge grade-${row.gradeClass} inline-flex h-10 min-w-10 items-center justify-center rounded-xl px-3 font-extrabold`}>{row.gradeClass}</span>
                </div>
                {kpis.map((kpi) => (
                  <div key={kpi.label} className="rounded-xl border border-[var(--border-light)] p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="text-xs font-extrabold text-[var(--text-primary)]">{kpi.label}</p>
                        <p className="mt-1 text-[11px] font-semibold text-[var(--text-faint)]">Actual {formatKpiValue(kpi.actual, kpi.unit)} / Target {formatKpiValue(kpi.target, kpi.unit)}</p>
                      </div>
                      <div className="text-right">
                        <p className={`text-sm font-extrabold ${kpi.achievement >= 80 ? 'text-emerald-600' : 'text-rose-500'}`}>{kpi.achievement.toFixed(1)}%</p>
                        {kpi.contribution !== undefined && <p className="text-[10px] font-semibold text-[var(--text-faint)]">Contribution {kpi.contribution.toFixed(1)}%</p>}
                      </div>
                    </div>
                    <div className="mt-3 h-2 overflow-hidden rounded-full bg-[var(--bg-sunken)]">
                      <div className={`h-full rounded-full ${kpi.achievement >= 80 ? 'bg-emerald-500' : 'bg-rose-500'}`} style={{ width: `${Math.min(100, Math.max(0, kpi.achievement))}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            )}

            {drawer === 'history' && (
              <div className="space-y-3">
                {actions.length === 0 ? (
                  <div className="rounded-2xl border border-dashed border-[var(--border-medium)] p-8 text-center text-sm font-semibold text-[var(--text-faint)]">No corrective actions recorded.</div>
                ) : actions.map((action) => (
                  <div key={action.id} className="rounded-xl border border-[var(--border-light)] p-4">
                    <div className="flex items-center justify-between gap-3">
                      <span className={`rounded-lg px-2 py-1 text-[10px] font-extrabold action-${action.action_type}`}>{action.action_type}</span>
                      <span className="text-[10px] font-semibold text-[var(--text-faint)]">{new Date(action.created_at).toLocaleDateString()}</span>
                    </div>
                    <p className="mt-3 text-sm font-bold text-[var(--text-primary)]">{action.action_text}</p>
                    <p className="mt-2 text-[11px] font-semibold text-[var(--text-secondary)]">{action.created_by || 'Unknown owner'} / {action.synced ? 'Saved' : 'Pending sync'}</p>
                  </div>
                ))}
              </div>
            )}

            {drawer === 'compare' && (
              <div className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-2xl border border-blue-500/15 bg-blue-500/10 p-4">
                    <p className="text-[10px] font-extrabold uppercase tracking-wider text-blue-500">Employee</p>
                    <p className="mt-2 text-2xl font-black text-blue-600 dark:text-blue-400">{row.score.toFixed(1)}%</p>
                  </div>
                  <div className="rounded-2xl border border-violet-500/15 bg-violet-500/10 p-4">
                    <p className="text-[10px] font-extrabold uppercase tracking-wider text-violet-500">Team average</p>
                    <p className="mt-2 text-2xl font-black text-violet-600 dark:text-violet-400">{teamAverage.toFixed(1)}%</p>
                  </div>
                </div>
                <div className={`rounded-2xl p-4 text-sm font-bold ${row.score >= teamAverage ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400' : 'bg-rose-500/10 text-rose-600 dark:text-rose-400'}`}>
                  {row.score >= teamAverage ? 'Above' : 'Below'} team average by {Math.abs(row.score - teamAverage).toFixed(1)}%.
                </div>
              </div>
            )}
          </aside>
        </div>,
        document.body,
      )}

      {showAssignment && createPortal(
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-[var(--border-medium)] bg-[var(--bg-surface)] p-5 shadow-2xl">
            <div className="flex items-center justify-between">
              <div><h3 className="font-extrabold text-[var(--text-primary)]">Edit Employee Assignment</h3><p className="mt-1 text-xs text-[var(--text-secondary)]">{row.name}</p></div>
              <button onClick={() => setShowAssignment(false)} className="rounded-lg p-2 text-[var(--text-secondary)] hover:bg-[var(--bg-sunken)]"><X size={18} /></button>
            </div>
            <label className="mt-5 block text-xs font-bold text-[var(--text-secondary)]">Team</label>
            <input value={assignmentTeam} onChange={(event) => setAssignmentTeam(event.target.value)} className="mt-2 w-full rounded-xl border border-[var(--border-medium)] bg-[var(--bg-sunken)] px-3 py-2.5 text-sm font-semibold text-[var(--text-primary)] focus:border-blue-500 focus:outline-none" />
            <label className="mt-4 block text-xs font-bold text-[var(--text-secondary)]">Performance level</label>
            <select value={assignmentLevel} onChange={(event) => setAssignmentLevel(event.target.value as TeamAgentRow['performanceLevel'])} className="mt-2 w-full rounded-xl border border-[var(--border-medium)] bg-[var(--bg-sunken)] px-3 py-2.5 text-sm font-semibold text-[var(--text-primary)] focus:border-blue-500 focus:outline-none">
              <option value="Employee">Employee</option><option value="Managerial">Managerial</option><option value="Corporate">Corporate</option>
            </select>
            {feedback && <p className="mt-3 text-xs font-semibold text-[var(--text-secondary)]">{feedback}</p>}
            <button onClick={saveAssignment} disabled={isSaving || !assignmentTeam.trim()} className="mt-5 flex w-full items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50">
              {isSaving && <Loader2 size={16} className="animate-spin" />} Save Assignment
            </button>
          </div>
        </div>, document.body,
      )}

      {showDeactivate && createPortal(
        <div className="fixed inset-0 z-[120] flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-md rounded-2xl border border-rose-500/20 bg-[var(--bg-surface)] p-5 shadow-2xl">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-rose-500/10 text-rose-500"><AlertTriangle size={22} /></div>
            <h3 className="mt-4 text-lg font-extrabold text-[var(--text-primary)]">Deactivate {row.name}?</h3>
            <p className="mt-2 text-sm leading-relaxed text-[var(--text-secondary)]">The employee will be removed from active rosters. Historical performance records and previous corrective actions will not be deleted.</p>
            {feedback && <p className="mt-3 text-xs font-semibold text-[var(--text-secondary)]">{feedback}</p>}
            <div className="mt-5 flex gap-3">
              <button onClick={() => setShowDeactivate(false)} disabled={isSaving} className="flex-1 rounded-xl border border-[var(--border-medium)] px-4 py-2.5 text-sm font-bold text-[var(--text-secondary)]">Cancel</button>
              <button onClick={deactivateEmployee} disabled={isSaving} className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-rose-600 px-4 py-2.5 text-sm font-bold text-white disabled:opacity-50">{isSaving && <Loader2 size={16} className="animate-spin" />} Deactivate</button>
            </div>
          </div>
        </div>, document.body,
      )}
    </>
  );
};

export default EmployeeRowActions;
