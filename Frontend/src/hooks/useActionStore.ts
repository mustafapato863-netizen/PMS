/**
 * useActionStore
 * Backend-primary corrective action persistence.
 * Synchronizes with backend /api/corrective-actions.
 */
import { useState, useCallback, useEffect } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ActionPriority, ActionStatus, ActionType, FollowUpState, PMSAction } from '../types';
import { apiFetch } from '../lib/apiClient';
import { useUserRole } from '../context/RoleContext';
import { useAuth } from '../context/auth';
import { summarizeRootCauses } from '../utils/rootCauseInsights';
import type { FollowUpFilters, FollowUpSummary } from '../components/actions/followUpTypes';

const STORAGE_KEY = 'pms_actions_v2';
const DELETED_KEY = 'pms_deleted_actions_v2';

interface BackendActionItem {
  id?: string;
  employee_id?: string | null;
  employee_name?: string | null;
  team?: string | null;
  month?: string;
  manager_action?: string;
  manager_notes?: string;
  timestamp?: string;
  created_by_name?: string;
  created_by_role?: string;
  created_by?: string;
  updated_by?: string;
  status?: ActionStatus;
  due_date?: string | null;
  owner?: { id: string; name: string } | null;
  priority?: ActionPriority | null;
  linked_kpi_key?: string | null;
  plan?: { id: string; name: string } | null;
  completion_note?: string | null;
  completed_at?: string | null;
  is_overdue?: boolean;
  days_to_due?: number | null;
  follow_up_state?: FollowUpState;
}

export interface ActionTrackingInput {
  due_date?: string | null;
  owner_user_id?: string | null;
  priority?: ActionPriority | null;
  linked_kpi_key?: string | null;
  plan_id?: string | null;
}

export interface FollowUpPayload {
  summary: FollowUpSummary;
  actions: PMSAction[];
}

export const actionQueryKeys = {
  all: ['corrective-actions'] as const,
  followUp: (filters: FollowUpFilters) => ['corrective-actions', 'follow-up', filters] as const,
  owners: ['corrective-actions', 'owners'] as const,
};

const ACTION_TYPE_VALUES = ['Coaching', 'Training', 'Reward', 'Monitor', 'PIP'] as const;

// Module-level shared cache and listeners for Backend API data
let cachedActions: PMSAction[] | null = null;
const listeners = new Set<(data: PMSAction[]) => void>();
let isFetching = false;

// ─── Local Storage Helpers ───────────────────────────────────────────────────

function loadLocalActions(): PMSAction[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const all = JSON.parse(raw) as PMSAction[];
    // Strip stale entries that have a null/nan employee_name — these were
    // written before the XLOOKUP-formula baking fix and are now invalid.
    return all.filter(
      (a) => a.employee_name && a.employee_name.trim().toLowerCase() !== 'nan'
    );
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

export function mapBackendAction(item: BackendActionItem): PMSAction {
  let actionType: ActionType = 'Coaching';
  let actionText = item.manager_action || '';
  const sepIdx = actionText.indexOf(': ');
  if (sepIdx > 0) {
    const typeStr = actionText.substring(0, sepIdx);
    actionText = actionText.substring(sepIdx + 2);
    const legacyTypes = ['SOP Review', 'SIP', 'PI', 'Suspension', 'Warning'];
    if (ACTION_TYPE_VALUES.includes(typeStr as ActionType) || legacyTypes.includes(typeStr)) {
      if (typeStr === 'SIP' || typeStr === 'PI' || typeStr === 'Suspension' || typeStr === 'Warning') actionType = 'PIP';
      else if (typeStr === 'SOP Review') actionType = 'Training';
      else actionType = typeStr as ActionType;
    } else {
      actionText = item.manager_action || '';
    }
  }
  const rawName = item.employee_name ?? '';
  return {
    id: item.id || `${item.employee_id || 'plan'}_${item.month}_${item.timestamp}`,
    employee_id: item.employee_id || '',
    employee_name: rawName.trim().toLowerCase() === 'nan' ? '' : rawName,
    team: item.team || '',
    month: item.month || '',
    action_type: actionType,
    action_text: actionText,
    root_cause_note: item.manager_notes || '',
    created_by: item.created_by_name && item.created_by_role ? `${item.created_by_name} - ${item.created_by_role}` : item.created_by || item.updated_by || 'Unknown',
    created_at: item.timestamp || '',
    synced: true,
    status: item.status,
    due_date: item.due_date,
    owner: item.owner,
    priority: item.priority,
    linked_kpi_key: item.linked_kpi_key,
    plan: item.plan,
    completion_note: item.completion_note,
    completed_at: item.completed_at,
    is_overdue: item.is_overdue,
    days_to_due: item.days_to_due,
    follow_up_state: item.follow_up_state,
  };
}

function trackingFrom(input: Partial<ActionTrackingInput> | undefined): ActionTrackingInput | undefined {
  if (!input) return undefined;
  const keys: Array<keyof ActionTrackingInput> = ['due_date', 'owner_user_id', 'priority', 'linked_kpi_key', 'plan_id'];
  if (!keys.some((key) => key in input)) return undefined;
  return {
    due_date: input.due_date,
    owner_user_id: input.owner_user_id,
    priority: input.priority,
    linked_kpi_key: input.linked_kpi_key,
    plan_id: input.plan_id,
  };
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
    // FastAPI exposes this collection route with a trailing slash. Keep it in
    // the request URL so production HTTPS deployments do not follow a
    // redirect to an HTTP Location header and silently fall back to empty
    // local storage.
    const result = await apiFetch<{ success: boolean; data: BackendActionItem[]; message?: string }>(
      '/api/corrective-actions/'
    );
    if (result && result.success && Array.isArray(result.data)) {
      const localByKey = new Map<string, PMSAction>();
      loadLocalActions().forEach((action) => {
        localByKey.set(`${action.employee_id}|${action.month}|${action.action_type}|${action.action_text}`, action);
        localByKey.set(action.id, action);
      });
      cachedActions = result.data.map((item) => {
        const mapped = mapBackendAction(item);
        const localMatch =
          (item.id ? localByKey.get(item.id) : undefined) ||
          localByKey.get(`${mapped.employee_id}|${mapped.month}|${mapped.action_type}|${mapped.action_text}`);
        const rawName = item.employee_name ?? '';
        const safeEmployeeName =
          rawName.trim().toLowerCase() === 'nan' || rawName.trim() === ''
            ? (localMatch?.employee_name || mapped.employee_name)
            : rawName;
        return {
          ...mapped,
          employee_id: mapped.employee_id,
          employee_name: safeEmployeeName || '',
          team: mapped.team || localMatch?.team || '',
          created_by: localMatch?.created_by || mapped.created_by,
          created_at: mapped.created_at || localMatch?.created_at || '',
        };
      });
    } else {
      throw new Error(result?.message || 'Invalid API response');
    }

    // After a successful backend fetch, purge any stale localStorage entries
    // that have invalid (nan/empty) employee names so they cannot reappear.
    const validLocal = loadLocalActions().filter(
      (a) => a.employee_name && a.employee_name.trim().toLowerCase() !== 'nan'
    );
    saveLocalActions(validLocal);

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
  action: PMSAction,
  tracking?: ActionTrackingInput,
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
          ...tracking,
        }),
      }
    );
    return true;
  } catch {
    return false;
  }
}

export async function fetchFollowUp(filters: FollowUpFilters = {}): Promise<FollowUpPayload> {
  const params = new URLSearchParams();
  if (filters.state) params.set('state', filters.state);
  if (filters.team) params.set('team', filters.team);
  if (filters.owner) params.set('owner', filters.owner);
  if (filters.month) params.set('month', filters.month);
  const query = params.toString();
  const result = await apiFetch<{ success: boolean; data: { summary: FollowUpSummary; actions: BackendActionItem[] }; message?: string }>(
    `/api/corrective-actions/follow-up${query ? `?${query}` : ''}`,
  );
  if (!result?.success || !result.data) throw new Error(result?.message || 'Follow-up could not be loaded.');
  return {
    summary: result.data.summary,
    actions: result.data.actions.map((item) => mapBackendAction(item)),
  };
}

export function useFollowUp(filters: FollowUpFilters) {
  return useQuery({
    queryKey: actionQueryKeys.followUp(filters),
    queryFn: () => fetchFollowUp(filters),
  });
}

export function useActionOwners(enabled = true) {
  return useQuery({
    queryKey: actionQueryKeys.owners,
    enabled,
    queryFn: async () => {
      const result = await apiFetch<{ success: boolean; data: Array<{ id: string; name: string; role?: string }> }>('/api/corrective-actions/owners');
      return result?.success ? result.data : [];
    },
  });
}

export function useUpdateActionStatus() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (input: { id: string; status: ActionStatus | string; completion_note?: string; due_date?: string }) => {
      const result = await apiFetch<{ success: boolean; message?: string }>(`/api/corrective-actions/${input.id}/status`, {
        method: 'PATCH',
        body: JSON.stringify({
          status: input.status,
          completion_note: input.completion_note,
          due_date: input.due_date,
        }),
      });
      if (result && result.success === false) throw new Error(result.message || 'Status update failed.');
      return result;
    },
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: actionQueryKeys.all });
      await fetchActions();
    },
  });
}

// ─── Exported Hook ────────────────────────────────────────────────────────────

export interface SaveActionInput extends ActionTrackingInput {
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
        action,
        trackingFrom(input),
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

  const updateStatus = useUpdateActionStatus();
  const updateAction = useCallback(
    async (
      actionId: string,
      updates: Partial<PMSAction> & Partial<ActionTrackingInput>,
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
          updated,
          trackingFrom(updates),
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
          updated,
          trackingFrom(updates),
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
    updateActionStatus: updateStatus.mutateAsync,
    deleteAction,
    getActionsForEmployee,
    getAllActions,
    getMonthStats,
    isSaving,
    deletedActionIds: loadDeletedActionIds(), // expose for timeline filtering
  };
}
