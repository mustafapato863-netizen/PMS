import { createContext, useContext, type Context } from 'react';
import * as AuthModule from '../../../context/auth';
import { apiFetch } from '../../../lib/apiClient';
import { canAccessPmsAi } from '../../../lib/access';

export interface AiSupportingKpiEvidence {
  kpi_key: string;
  kpi_name: string;
  actual?: number | null;
  target?: number | null;
  unit?: string | null;
  achievement_percent?: number | null;
  target_status?: string | null;
  measured_months?: number;
}

export interface AiCorrectiveActionDraftPayload {
  title: string;
  focus_kpi_key: string;
  focus_kpi_name: string;
  action_type: string;
  measured_issue: string;
  recommended_steps: string[];
  uncertainty?: string | null;
  approval_status: 'unapproved_draft';
}

export interface AiCorrectiveActionSuggestionPayload {
  outcome: 'suggested' | 'insufficient_evidence' | 'model_unavailable' | 'draft_rejected';
  provider_used: 'cloudflare' | 'gemini' | 'none';
  fallback_used?: boolean;
  measured_facts: string[];
  evidence_limitations: string[];
  supporting_kpis: AiSupportingKpiEvidence[];
  draft: AiCorrectiveActionDraftPayload | null;
  insufficient_evidence_reasons: string[];
  warning?: string | null;
}

export interface ActionPlanAiRequestParams {
  team: string;
  month: string;
  year: number;
  performanceLevel?: string | null;
  employeeId?: string | null;
  focusKpiKey?: string | null;
  signal?: AbortSignal;
}

export interface ActionPlanAiError {
  message: string;
  status?: number;
}

const FALLBACK_AUTH_CONTEXT = createContext<AuthModule.AuthContextProps | undefined>(undefined);

const READ_ONLY_ACTION_ROLES = new Set([
  'viewer',
  'employee',
  'agent',
  'function viewer',
]);

function resolveAuthContextSafely(): Context<AuthModule.AuthContextProps | undefined> {
  try {
    return AuthModule.AuthContext ?? FALLBACK_AUTH_CONTEXT;
  } catch {
    return FALLBACK_AUTH_CONTEXT;
  }
}

/**
 * Reads AuthContext safely without calling `useAuth()` so standalone unit tests
 * that omit `<AuthProvider>` or partially mock `context/auth` never throw.
 */
export function useCanUseActionPlanAi(presentationMode = false): {
  canEditActions: boolean;
  isAdmin: boolean;
} {
  const auth = useContext(resolveAuthContextSafely());
  if (presentationMode) {
    return { canEditActions: false, isAdmin: false };
  }
  if (auth === undefined) {
    return { canEditActions: true, isAdmin: true };
  }
  if (!auth.currentUser) {
    return { canEditActions: false, isAdmin: false };
  }
  const normalizedRole = String(auth.currentUser.role ?? '').trim().toLowerCase();
  const canEdit = !READ_ONLY_ACTION_ROLES.has(normalizedRole);
  const isAdmin = canAccessPmsAi(auth.currentUser.role);
  return { canEditActions: canEdit, isAdmin };
}

export function parseMonthYearFromLabel(
  monthLabel: string,
  periodKey?: string,
): { month: string; year: number } {
  if (periodKey) {
    const match = /^(\d{4})-(\d{2})$/.exec(periodKey.trim());
    if (match) {
      const monthNames = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December',
      ];
      const idx = Number(match[2]) - 1;
      if (idx >= 0 && idx < 12) {
        return { month: monthNames[idx], year: Number(match[1]) };
      }
    }
  }
  const parts = String(monthLabel || '').trim().split(/\s+/);
  const month = parts[0] || 'September';
  const parsedYear = Number(parts[1]);
  return {
    month,
    year: Number.isFinite(parsedYear) && parsedYear > 2000 ? parsedYear : new Date().getFullYear(),
  };
}

/**
 * Calls POST /api/ai/corrective-action-suggestions with the exact Pydantic schema
 * (`extra="forbid"`): { team, month, year, performance_level, employee_id, linked_kpi_key }.
 */
export async function requestActionPlanAiSuggestion(
  params: ActionPlanAiRequestParams,
): Promise<AiCorrectiveActionSuggestionPayload> {
  const body: Record<string, unknown> = {
    team: params.team.trim(),
    month: params.month.trim(),
    year: params.year,
    employee_id: params.employeeId ? params.employeeId.trim() : null,
    linked_kpi_key: params.focusKpiKey ? params.focusKpiKey.trim() : null,
  };
  if (params.performanceLevel && params.performanceLevel.trim()) {
    body.performance_level = params.performanceLevel.trim();
  }

  const response = await apiFetch<{
    success: boolean;
    message?: string;
    data?: AiCorrectiveActionSuggestionPayload;
  }>('/api/ai/corrective-action-suggestions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: params.signal,
  });

  if (!response?.success || !response.data) {
    throw new Error(response?.message || 'AI recommendation could not be generated.');
  }
  return response.data;
}

export async function enableCorrectiveActionPilotSetting(): Promise<void> {
  await apiFetch('/api/settings/ai-corrective-action-pilot', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled: true }),
  });
}

export function isPilotDisabled403(error: ActionPlanAiError | null | undefined): boolean {
  if (!error || error.status !== 403) return false;
  return /pilot|disabled|enable|settings/i.test(error.message);
}
