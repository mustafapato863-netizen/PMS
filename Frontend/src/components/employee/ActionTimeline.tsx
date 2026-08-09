import { useState } from 'react';
import { Clock, User, CheckCircle2, WifiOff, Edit2, Trash2, AlertTriangle, CalendarDays, List } from 'lucide-react';
import type { ActionType, PMSAction } from '../../types';
import { useUserRole } from '../../context/RoleContext';
import { motion, AnimatePresence } from 'framer-motion';

const ACTION_COLORS: Record<string, { bg: string; text: string; dot: string }> = {
  Training:  { bg: 'bg-blue-500/10 border border-blue-500/20',     text: 'text-blue-600 dark:text-blue-400',       dot: 'bg-blue-500' },
  Reward:    { bg: 'bg-emerald-500/10 border border-emerald-500/20', text: 'text-emerald-600 dark:text-emerald-400', dot: 'bg-emerald-500' },
  PIP:       { bg: 'bg-red-500/10 border border-red-500/20',         text: 'text-red-600 dark:text-red-400',         dot: 'bg-red-500' },
  Monitor:   { bg: 'bg-amber-500/10 border border-amber-500/20',     text: 'text-amber-600 dark:text-amber-400',     dot: 'bg-amber-500' },
  Coaching:  { bg: 'bg-purple-500/10 border border-purple-500/20',   text: 'text-purple-600 dark:text-purple-400',   dot: 'bg-purple-500' },
  default:   { bg: 'bg-[var(--bg-sunken)] border border-[var(--border-light)]', text: 'text-[var(--text-secondary)]',     dot: 'bg-[var(--text-muted)]' },
};

interface BackendAction {
  id?: string;
  manager_action: string;
  manager_notes?: string;
  timestamp?: string;
  month?: string;
}

interface ActionTimelineProps {
  employeeId?: string;
  activeMonth?: string;
  localActions: PMSAction[];
  backendActions: BackendAction[];
  isLoading?: boolean;
  onEditAction?: (action: {
    id: string;
    action_type: ActionType;
    action_text: string;
    root_cause_note: string;
  }) => void;
  onDeleteAction?: (actionId: string) => void;
}

function formatCreatedBy(label: string): string {
  const value = label.trim();
  if (!value) return 'Unknown';
  if (value.includes(' - ')) return value;
  if (value === 'Admin' || value === 'Manager' || value === 'Executive' || value === 'Viewer' || value === 'Agent') {
    return `Unknown - ${value}`;
  }
  return value;
}

const ActionTimeline = ({
  activeMonth,
  localActions,
  backendActions,
  isLoading,
  onEditAction,
  onDeleteAction,
}: ActionTimelineProps) => {
  const { role } = useUserRole();
  const canModify = role === 'Admin' || role === 'Manager';
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [filterMode, setFilterMode] = useState<'month' | 'all'>('all');
  // Merge and deduplicate: local actions first, then backend-only
  const combinedActions: Array<{
    id: string;
    type: string;
    text: string;
    note?: string;
    createdBy: string;
    createdAt: string;
    synced: boolean;
    month?: string;
  }> = [
    ...localActions.map((a) => ({
      id: a.id,
      type: a.action_type,
      text: a.action_text,
      note: a.root_cause_note,
      createdBy: a.created_by,
      createdAt: a.created_at,
      synced: a.synced,
      month: a.month,
    })),
    ...backendActions
      .filter((b) => !localActions.some((l) => l.action_text?.includes(b.manager_action?.split(': ')[1] ?? '')))
      .map((b, i) => ({
        id: b.id || `backend-${i}`,
        type: b.manager_action?.split(': ')[0] || 'Coaching',
        text: b.manager_action?.split(': ').slice(1).join(': ') || b.manager_action,
        note: b.manager_notes,
        createdBy: 'Unknown - Manager',
        createdAt: b.timestamp || '',
        synced: true,
        month: b.month,
      })),
  ].sort((a, b) => (b.createdAt > a.createdAt ? 1 : -1));

  // Apply month filter — matches the month the action was ASSIGNED TO, not when it was created
  const filteredActions = filterMode === 'month' && activeMonth
    ? combinedActions.filter((action) => {
        if (!action.month) return false;
        const mLower = action.month.toLowerCase();
        const activeLower = activeMonth.toLowerCase();
        return mLower === activeLower || mLower.startsWith(activeLower.slice(0, 3)) || activeLower.startsWith(mLower.slice(0, 3));
      })
    : combinedActions;

  const actionToDelete = combinedActions.find((a) => a.id === confirmDeleteId);

  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2].map((i) => (
          <div key={i} className="animate-pulse flex gap-3">
            <div className="w-2.5 h-2.5 rounded-full bg-[var(--border-strong)] mt-1.5 shrink-0" />
            <div className="flex-1 space-y-2">
              <div className="h-3 bg-[var(--border-strong)] rounded w-1/3" />
              <div className="h-3 bg-[var(--bg-sunken)] rounded w-2/3" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  const filterToggle = (
    <div className="flex items-center gap-1 p-0.5 bg-[var(--bg-sunken)] rounded-lg border border-[var(--border-light)] mb-4">
      <button
        onClick={() => setFilterMode('month')}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[11px] font-bold transition-all cursor-pointer ${
          filterMode === 'month'
            ? 'bg-blue-600 text-white shadow-sm'
            : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-raised)]'
        }`}
      >
        <CalendarDays size={12} />
        {activeMonth || 'Month'}
      </button>
      <button
        onClick={() => setFilterMode('all')}
        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-[11px] font-bold transition-all cursor-pointer ${
          filterMode === 'all'
            ? 'bg-blue-600 text-white shadow-sm'
            : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-raised)]'
        }`}
      >
        <List size={12} />
        All Actions
      </button>
    </div>
  );

  if (!combinedActions.length) {
    return (
      <div className="text-center py-8">
        <Clock size={28} className="mx-auto text-[var(--border-strong)] mb-2" />
        <p className="text-sm text-[var(--text-secondary)] font-medium">No actions recorded yet.</p>
        <p className="text-xs text-[var(--text-muted)] mt-1">Use the "Add Action" button to record an intervention.</p>
      </div>
    );
  }

  return (
    <div className="relative">
      {/* Filter Toggle */}
      {filterToggle}

      {/* Empty state for filtered view */}
      {filteredActions.length === 0 && (
        <div className="text-center py-6">
          <CalendarDays size={24} className="mx-auto text-[var(--border-strong)] mb-2" />
          <p className="text-sm text-[var(--text-secondary)] font-medium">
            No actions found for {activeMonth}.
          </p>
          <button
            onClick={() => setFilterMode('all')}
            className="text-xs text-blue-600 dark:text-blue-400 font-bold mt-2 hover:underline cursor-pointer"
          >
            View all actions
          </button>
        </div>
      )}

      {/* Timeline line */}
      {filteredActions.length > 0 && (
        <div className="absolute left-[5px] top-2 bottom-2 w-px bg-[var(--border-medium)]" style={{ top: '52px' }} />
      )}

      <div className="space-y-4">
        {filteredActions.map((action) => {
          const cfg = ACTION_COLORS[action.type] || ACTION_COLORS.default;
          const date = action.createdAt
            ? new Date(action.createdAt).toLocaleDateString('en-US', { day: 'numeric', month: 'short', year: 'numeric' })
            : action.month || '';

          return (
            <div key={action.id} className="flex gap-4 pl-5 relative">
              {/* Dot */}
              <div className={`absolute left-0 top-1.5 w-3 h-3 rounded-full ${cfg.dot} ring-2 ring-[var(--bg-surface)] shadow-sm`} />

              <div className={`flex-1 rounded-xl p-3 ${cfg.bg}`}>
                <div className="flex items-start justify-between gap-2 mb-1">
                  <span className={`text-xs font-extrabold uppercase tracking-wide ${cfg.text}`}>
                    {action.type}
                  </span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {!action.synced && (
                      <span title="Not synced to server" className="text-amber-500">
                        <WifiOff size={11} />
                      </span>
                    )}
                    {action.synced && <CheckCircle2 size={11} className="text-emerald-400" />}
                    <span className="text-[10px] text-[var(--text-muted)] font-semibold">{date}</span>
                  </div>
                </div>
                <p className="text-sm font-semibold text-[var(--text-primary)] leading-snug">{action.text}</p>
                {action.month && (
                  <p className="text-xs text-[var(--text-secondary)] mt-1 font-semibold">
                    Decision Month: {action.month}
                  </p>
                )}
                {action.note && (
                  <p className="text-xs text-[var(--text-secondary)] italic mt-1.5 border-t border-[var(--border-light)] pt-1.5 font-medium">
                    Root cause: {action.note}
                  </p>
                )}
                <div className="flex items-center justify-between mt-2 pt-2 border-t border-[var(--border-light)]">
                  <div className="flex items-center gap-1 text-[10px] text-[var(--text-muted)] font-semibold">
                    <User size={9} /> {formatCreatedBy(action.createdBy)}
                  </div>
                  {canModify && (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() =>
                          onEditAction?.({
                            id: action.id,
                            action_type: action.type as ActionType,
                            action_text: action.text,
                            root_cause_note: action.note || '',
                          })
                        }
                        aria-label="Edit Action"
                        className="p-1 text-[var(--text-muted)] hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-500/10 rounded transition-colors cursor-pointer"
                        title="Edit Action"
                      >
                        <Edit2 size={11} />
                      </button>
                      <button
                        onClick={() => setConfirmDeleteId(action.id)}
                        aria-label="Delete Action"
                        className="p-1 text-[var(--text-muted)] hover:text-red-600 dark:hover:text-red-400 hover:bg-red-500/10 rounded transition-colors cursor-pointer"
                        title="Delete Action"
                      >
                        <Trash2 size={11} />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Custom Delete Confirmation Modal */}
      <AnimatePresence>
        {confirmDeleteId && actionToDelete && (
          <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ scale: 0.95, opacity: 0, y: 10 }}
              animate={{ scale: 1, opacity: 1, y: 0 }}
              exit={{ scale: 0.95, opacity: 0, y: 10 }}
              transition={{ type: 'spring', damping: 25, stiffness: 300 }}
              className="bg-[var(--bg-surface)] border border-[var(--border-medium)] rounded-2xl shadow-2xl max-w-sm w-full p-6 text-center space-y-4 relative overflow-hidden"
            >
              {/* Top border highlight */}
              <div className="absolute top-0 left-0 right-0 h-1.5 bg-gradient-to-r from-red-500 to-rose-600" />

              {/* Warning Icon Container */}
              <div className="w-12 h-12 rounded-full bg-rose-500/10 text-rose-600 dark:text-rose-400 flex items-center justify-center mx-auto mt-2">
                <AlertTriangle size={24} />
              </div>

              {/* Title & Desc */}
              <div className="space-y-1">
                <h4 className="text-lg font-extrabold text-[var(--text-primary)]">
                  Delete Action?
                </h4>
                <p className="text-xs text-[var(--text-secondary)] font-semibold leading-relaxed">
                  Are you sure you want to delete this action? This will permanently remove this record from the employee's history.
                </p>
              </div>

              {/* Action Preview Card */}
              <div className="bg-[var(--bg-sunken)] border border-[var(--border-medium)] rounded-xl p-3 text-left">
                <span className="text-[9px] font-bold uppercase tracking-wider text-rose-500">
                  {actionToDelete.type}
                </span>
                <p className="text-xs font-semibold text-[var(--text-secondary)] line-clamp-2 mt-0.5 leading-snug">
                  {actionToDelete.text}
                </p>
              </div>

              {/* Buttons */}
              <div className="flex gap-2 pt-2">
                <button
                  onClick={() => setConfirmDeleteId(null)}
                  className="flex-1 bg-[var(--bg-sunken)] hover:bg-[var(--bg-raised)] border border-[var(--border-medium)] text-[var(--text-primary)] font-bold py-2.5 px-4 rounded-xl text-xs transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={async () => {
                    if (confirmDeleteId) {
                      await onDeleteAction?.(confirmDeleteId);
                      setConfirmDeleteId(null);
                    }
                  }}
                  className="flex-1 bg-gradient-to-r from-red-500 to-rose-600 hover:from-red-600 hover:to-rose-700 text-white font-bold py-2.5 px-4 rounded-xl text-xs transition-colors shadow-sm cursor-pointer"
                >
                  Delete
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default ActionTimeline;
