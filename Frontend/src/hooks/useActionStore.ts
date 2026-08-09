/**
 * useActionStore
 * Backend-primary corrective action persistence.
 * Synchronizes with backend /api/corrective-actions.
 */
import { useState, useCallback, useEffect } from 'react';
import type { PMSAction, ActionType } from '../types';
import { apiFetch } from '../lib/apiClient';
import { useUserRole } from '../context/RoleContext';
import { useAuth } from '../context/auth';
import { summarizeRootCauses } from '../utils/rootCauseInsights';

const STORAGE_KEY = 'pms_actions_v2';
const DELETED_KEY = 'pms_deleted_actions_v2';

interface BackendActionItem {
  id?: string;
  employee_id: string;
  employee_name: string;
  team: string;
  month: string;
  manager_action?: string;
  manager_notes?: string;
  timestamp?: string;
  created_by_name?: string;
  created_by_role?: string;
  created_by?: string;
  updated_by?: string;
}

// Module-level shared cache and listeners for Backend API data
let cachedActions: PMSAction[] | null = null;
const listeners = new Set<(data: PMSAction[]) => void>();
let isFetching = false;

// ─── Local Storage Helpers ───────────────────────────────────────────────────

function loadLocalActions(): PMSAction[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as PMSAction[]) : [];
  } catch {
    return [];
  }
}

function saveLocalActions(actions: PMSAction[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(actions));
  } catch {
    /* quota exceeded — silently skip */
  }
}

function upsertLocalAction(action: PMSAction): PMSAction[] {
  const all = loadLocalActions();
  const idx = all.findIndex((a) => a.id === action.id);
  if (idx >= 0) {
    all[idx] = action;
  } else {
    all.unshift(action);
  }
  saveLocalActions(all);
  return all;
}

function getRole(): string {
  return localStorage.getItem('pms_user_role') || 'Manager';
}

function loadDeletedActionIds(): string[] {
  try {
    const raw = localStorage.getItem(DELETED_KEY);
    return raw ? (JSON.parse(raw) as string[]) : [];
  } catch {
    return [];
  }
}

function addDeletedActionId(id: string): string[] {
  const all = loadDeletedActionIds();
  if (!all.includes(id)) {
    all.push(id);
    try {
      localStorage.setItem(DELETED_KEY, JSON.stringify(all));
    } catch {
      /* localStorage may be unavailable in private mode */
    }
  }
  return all;
}
// ─── Fetch Actions from Backend ──────────────────────────────────────────────

export async function fetchActions(role?: string) {
  const activeRole = role || getRole();
  if (activeRole === 'Viewer') {
    cachedActions = [];
    listeners.forEach((listener) => listener([]));
    return;
  }
  if (isFetching) return;
  isFetching = true;
  try {
    const result = await apiFetch<{ success: boolean; data: BackendActionItem[]; message?: string }>(
      '/api/corrective-actions'
    );
    if (result && result.success && Array.isArray(result.data)) {
      const localByKey = new Map<string, PMSAction>();
      loadLocalActions().forEach((action) => {
        localByKey.set(`${action.employee_id}|${action.month}|${action.action_type}|${action.action_text}`, action);
        localByKey.set(action.id, action);
      });
      cachedActions = result.data.map((item) => {
        let actionType: ActionType = 'Coaching';
        let actionText = item.manager_action || '';
        
        // Parse "Coaching: action details" if possible
        const sepIdx = actionText.indexOf(': ');
        if (sepIdx > 0) {
          const typeStr = actionText.substring(0, sepIdx);
          actionText = actionText.substring(sepIdx + 2);
          
          const validTypes = ['Coaching', 'Training', 'Reward', 'Monitor', 'PIP'];
          const legacyTypes = ['SOP Review', 'SIP', 'PI', 'Suspension', 'Warning'];
          
          if (validTypes.includes(typeStr) || legacyTypes.includes(typeStr)) {
            if (typeStr === 'SIP' || typeStr === 'PI' || typeStr === 'Suspension' || typeStr === 'Warning') {
              actionType = 'PIP';
            } else if (typeStr === 'SOP Review') {
              actionType = 'Training';
            } else {
              actionType = typeStr as ActionType;
            }
          } else {
            actionText = item.manager_action || ''; // reset to original if not standard type
          }
        }

        const localMatch =
          (item.id ? localByKey.get(item.id) : undefined) ||
          localByKey.get(`${item.employee_id}|${item.month}|${actionType}|${actionText}`);

        return {
          id: item.id || `${item.employee_id}_${item.month}_${item.timestamp}`,
          employee_id: item.employee_id,
          employee_name: item.employee_name,
          team: item.team,
          month: item.month,
          action_type: actionType,
          action_text: actionText,
          root_cause_note: item.manager_notes || '',
          created_by: localMatch?.created_by
            || (item.created_by_name && item.created_by_role ? `${item.created_by_name} - ${item.created_by_role}` : null)
            || item.created_by
            || item.updated_by
            || 'Unknown',
          created_at: item.timestamp,
          synced: true,
        } as PMSAction;
      });
    } else {
      throw new Error(result?.message || 'Invalid API response');
    }
    listeners.forEach((listener) => listener(cachedActions!));
  } catch (error) {
    console.warn('Failed to fetch corrective actions from Backend API. Falling back to local data.', error);
    listeners.forEach((listener) => listener(loadLocalActions()));
  } finally {
    isFetching = false;
  }
}

// ─── API Helpers ─────────────────────────────────────────────────────────────

async function postActionToBackend(
  employeeId: string,
  month: string,
  action: PMSAction
): Promise<boolean> {
  try {
    await apiFetch(
      `/api/employee/${employeeId}/corrective-actions`,
      {
        method: 'POST',
        body: JSON.stringify({
          id: action.id,
          month,
          manager_action: `${action.action_type}: ${action.action_text}`,
          manager_notes: action.root_cause_note,
        }),
      }
    );
    return true;
  } catch {
    return false;
  }
}

// ─── Exported Hook ────────────────────────────────────────────────────────────

export interface SaveActionInput {
  employee_id: string;
  employee_name: string;
  team: string;
  month: string;
  action_type: ActionType;
  action_text: string;
  root_cause_note: string;
  created_by?: string;
}

export interface ActionStoreResult {
  success: boolean;
  synced: boolean;
  message: string;
}
export function useActionStore() {
  const { role } = useUserRole();
  const { currentUser } = useAuth();
  const [actions, setActions] = useState<PMSAction[]>(cachedActions || []);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    const listener = (newActions: PMSAction[]) => {
      setActions(newActions);
    };
    listeners.add(listener);

    fetchActions(role);

    return () => {
      listeners.delete(listener);
    };
  }, [role]);

  const saveAction = useCallback(
    async (input: SaveActionInput): Promise<ActionStoreResult> => {
      setIsSaving(true);

      const action: PMSAction = {
        id: `${input.employee_id}_${input.month}_${Date.now()}`,
        employee_id: input.employee_id,
        employee_name: input.employee_name,
        team: input.team,
        month: input.month,
        action_type: input.action_type,
        action_text: input.action_text,
        root_cause_note: input.root_cause_note,
        created_by: input.created_by || `${currentUser?.name || 'Unknown'} - ${currentUser?.role || getRole()}`,
        created_at: new Date().toISOString(),
        synced: false,
      };

      // Try backend first
      const synced = await postActionToBackend(
        input.employee_id,
        input.month,
        action
      );
      action.synced = synced;

      // Always cache locally as fallback
      upsertLocalAction(action);

      // Reload actions list from backend
      await fetchActions();

      setIsSaving(false);

      return {
        success: true,
        synced,
        message: synced
          ? 'Action saved successfully.'
          : 'Saved locally. Will sync when online.',
      };
    },
    [currentUser]
  );

  const updateAction = useCallback(
    async (
      actionId: string,
      updates: Partial<PMSAction>,
      employeeInfo?: { id: string; name: string; team: string },
      monthStr?: string
    ): Promise<ActionStoreResult> => {
      setIsSaving(true);

      const all = loadLocalActions();
      const idx = all.findIndex((a) => a.id === actionId);

      if (idx >= 0) {
        // Local action update
        const existing = all[idx];
        const updated = {
          ...existing,
          action_type: updates.action_type ?? existing.action_type,
          action_text: updates.action_text ?? existing.action_text,
          root_cause_note: updates.root_cause_note ?? existing.root_cause_note,
          synced: false,
        };
        all[idx] = updated;
        saveLocalActions(all);

        // Try syncing to backend
        const synced = await postActionToBackend(
          updated.employee_id,
          updated.month,
          updated
        );
        updated.synced = synced;

        // Re-save with updated synced status
        const all2 = loadLocalActions();
        const idx2 = all2.findIndex((a) => a.id === actionId);
        if (idx2 >= 0) {
          all2[idx2] = updated;
          saveLocalActions(all2);
        }

        // Reload actions list from backend
        await fetchActions();

        setIsSaving(false);
        return {
          success: true,
          synced,
          message: 'Action updated successfully.',
        };
      } else if (employeeInfo && monthStr) {
        // Backend action update: overwrite using original ID
        const updated: PMSAction = {
          id: actionId,
          employee_id: employeeInfo.id,
          employee_name: employeeInfo.name,
          team: employeeInfo.team,
          month: monthStr,
          action_type: updates.action_type || 'Coaching',
          action_text: updates.action_text || '',
          root_cause_note: updates.root_cause_note || '',
          created_by: `${currentUser?.name || employeeInfo?.name || 'Unknown'} - ${currentUser?.role || getRole()}`,
          created_at: new Date().toISOString(),
          synced: false,
        };

        const synced = await postActionToBackend(
          employeeInfo.id,
          monthStr,
          updated
        );
        updated.synced = synced;

        upsertLocalAction(updated);

        // Reload actions list from backend
        await fetchActions();

        setIsSaving(false);
        return {
          success: true,
          synced,
          message: 'Action updated successfully.',
        };
      }

      setIsSaving(false);
      return {
        success: false,
        synced: false,
        message: 'Action not found.',
      };
    },
    [currentUser]
  );

  const deleteAction = useCallback(async (actionId: string, employeeId?: string): Promise<boolean> => {
    // Add to deleted blacklist
    addDeletedActionId(actionId);

    // Also remove from local actions
    const all = loadLocalActions();
    const filtered = all.filter((a) => a.id !== actionId);
    saveLocalActions(filtered);

    // Call backend delete route
    if (employeeId) {
      try {
        await apiFetch(`/api/employee/${employeeId}/corrective-actions/${actionId}`, {
          method: 'DELETE',
        });
        
        // Reload actions list from backend
        await fetchActions();
        
        return true;
      } catch {
        return false;
      }
    }
    return true;
  }, []);

  const getActionsForEmployee = useCallback((employeeId: string): PMSAction[] => {
    const deletedIds = loadDeletedActionIds();
    return actions.filter(
      (a) => a.employee_id === employeeId && !deletedIds.includes(a.id)
    );
  }, [actions]);

  const getAllActions = useCallback((): PMSAction[] => {
    const deletedIds = loadDeletedActionIds();
    return actions.filter((a) => !deletedIds.includes(a.id));
  }, [actions]);

  const getMonthStats = useCallback(
    (monthStr: string) => {
      const deletedIds = loadDeletedActionIds();
      const filteredActions = actions.filter(
        (a) => a.month === monthStr && !deletedIds.includes(a.id)
      );
      return summarizeRootCauses(filteredActions);
    },
    [actions]
  );

  return {
    saveAction,
    updateAction,
    deleteAction,
    getActionsForEmployee,
    getAllActions,
    getMonthStats,
    isSaving,
    deletedActionIds: loadDeletedActionIds(), // expose for timeline filtering
  };
}
