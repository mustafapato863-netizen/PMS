import { createContext, useContext, type Context } from 'react';
import * as AuthModule from '../../../context/auth';
import { apiFetch } from '../../../lib/apiClient';
import { canAccessPmsAi } from '../../../lib/access';

import type {
  AiCorrectiveActionSuggestionContext,
  AiCorrectiveActionSuggestionPriorAction,
  AiCorrectiveActionSuggestionTrendSummary,
  ObservationStatus,
} from '../../ai/types';

export interface AiSupportingKpiEvidence {
  kpi_key: string;
  kpi_name?: string;
  display_name?: string;
  actual?: number | null;
  target?: number | null;
  unit?: string | null;
  direction?: string | null;
  weight?: number | null;
  achievement_ratio?: number | null;
  achievement_percent?: number | null;
  contributes_to_score?: boolean;
  status?: 'below_target' | 'at_or_above_target' | 'unknown' | null;
  target_status?: string | null;
  measured_months?: number;
  observation_status?: ObservationStatus;
  previous_actual?: number | null;
  previous_period?: string | null;
  projected_agent_score_lift?: number | null;
}

export interface AiCorrectiveActionDraftPayload {
  title: string;
  focus_kpi_key: string;
  focus_kpi_name: string;
  action_type: string;
  action_choice?: string | null;
  follow_up_interval?: string | null;
  official_target_label?: string | null;
  action_milestone_note?: string | null;
  measured_issue: string;
  recommended_steps: string[];
  uncertainty?: string | null;
  approval_status: 'unapproved_draft';
  responsible_role?: string | null;
  recommended_follow_up?: string | null;
  observation_status?: ObservationStatus | null;
  formatted_next_step?: string | null;
}

export interface AiCorrectiveActionSuggestionPayload {
  trace_id?: string | null;
  outcome: 'suggested' | 'insufficient_evidence' | 'model_unavailable' | 'draft_rejected';
  provider_used: 'cloudflare' | 'nvidia' | 'gemini' | 'none';
  fallback_used?: boolean;
  fallback_reason?: string | null;
  validation_errors?: string[];
  repair_attempted?: boolean;
  repair_outcome?: 'not_needed' | 'repaired' | 'rejected' | 'time_exhausted' | 'non_repairable' | null;
  repair_latency_ms?: number | null;
  context?: AiCorrectiveActionSuggestionContext;
  focus_kpi_key?: string | null;
  cohort_in_scope_count?: number | null;
  cohort_measured_count?: number | null;
  cohort_unmeasured_count?: number | null;
  cohort_below_target_count?: number | null;
  cohort_coverage_label?: string | null;
  official_target_label?: string | null;
  measured_actual_label?: string | null;
  measured_facts: string[];
  evidence_limitations: string[];
  supporting_kpis: AiSupportingKpiEvidence[];
  prior_actions?: AiCorrectiveActionSuggestionPriorAction[];
  trend_summary?: AiCorrectiveActionSuggestionTrendSummary | null;
  draft: AiCorrectiveActionDraftPayload | null;
  evidence_next_step?: string | null;
  evidence_next_step_label?: string | null;
  evidence_next_step_role?: string | null;
  evidence_next_step_follow_up?: string | null;
  evidence_next_step_action_type?: string | null;
  evidence_next_step_source?: 'pms_evidence' | null;
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

export function buildAiScopeKey(
  team: string,
  periodKey: string,
  employeeId?: string | null,
  linkedKpiKey?: string | null,
): string {
  return [
    String(team || '').trim(),
    String(periodKey || '').trim(),
    String(employeeId || 'team').trim(),
    String(linkedKpiKey || 'auto').trim(),
  ].join('::');
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

export interface TeamCardKpiRef {
  linkedKpiKey?: string | null;
  targetKpi?: string | null;
  title?: string | null;
}

export interface TeamKpiFocusCandidate {
  kpiKey: string;
  label?: string | null;
  shortLabel?: string | null;
  verdictBadge?: string | null;
}

/**
 * Resolves the focus KPI key for a whole-team action card without falling back
 * to an unrelated or already on-target KPI.
 */
export function resolveTeamCardFocusKpiKey(
  card: TeamCardKpiRef,
  kpis: readonly TeamKpiFocusCandidate[],
  explorerKpiKey?: string | null,
): string | null {
  const explicitKey = card.linkedKpiKey?.trim();
  if (explicitKey) {
    if (kpis.length === 0) {
      return explicitKey;
    }
    const explicitMatch = kpis.find(
      (k) => k.kpiKey.trim().toLowerCase() === explicitKey.toLowerCase(),
    );
    if (explicitMatch) {
      return explicitMatch.kpiKey;
    }
  }

  const targetText = (card.targetKpi ?? '').trim().toLowerCase();
  const titleText = (card.title ?? '').trim().toLowerCase();
  if (kpis.length > 0 && (targetText || titleText)) {
    const candidates: Array<{ token: string; kpi: TeamKpiFocusCandidate }> = [];
    for (const kpi of kpis) {
      for (const rawToken of [kpi.label, kpi.shortLabel, kpi.kpiKey]) {
        const token = (rawToken ?? '').trim().toLowerCase();
        if (token) {
          candidates.push({ token, kpi });
        }
      }
    }
    candidates.sort((a, b) => b.token.length - a.token.length);

    const matched =
      (targetText
        ? candidates.find((c) => targetText.includes(c.token))?.kpi
        : undefined) ??
      (titleText
        ? candidates.find((c) => titleText.includes(c.token))?.kpi
        : undefined);

    if (matched) {
      return matched.verdictBadge !== 'Target Met' ? matched.kpiKey : null;
    }
  }

  const explorerKey = explorerKpiKey?.trim();
  if (explorerKey) {
    const explorerKpi = kpis.find(
      (k) => k.kpiKey.trim().toLowerCase() === explorerKey.toLowerCase(),
    );
    if (explorerKpi && explorerKpi.verdictBadge !== 'Target Met') {
      return explorerKpi.kpiKey;
    }
  }

  return null;
}

function humanizeKpiKeyToken(
  rawKey: string,
  supportingKpis?: readonly { kpi_key?: string | null; display_name?: string | null; kpi_name?: string | null }[],
): string {
  const key = rawKey.trim();
  if (!key) return 'selected KPI';
  const match = supportingKpis?.find(
    (k) => (k.kpi_key ?? '').trim().toLowerCase() === key.toLowerCase(),
  );
  const friendly = match?.display_name?.trim() || match?.kpi_name?.trim();
  if (friendly) return friendly;
  return key
    .replace(/^[AT]\./, '')
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z])([A-Z])/g, '$1 $2')
    .replace(/\s+/g, ' ')
    .trim();
}

const EXACT_REASON_MAP: Record<string, string> = {
  no_complete_kpi_below_target:
    'All measured KPIs for this selection are meeting or above target.',
  no_measured_kpis: 'No measured KPI records are available for this period.',
  no_performance_record_for_period:
    'No performance record was found for this period.',
  no_kpi_values_for_period: 'No KPI values were recorded for this period.',
  multiple_regions_in_period:
    'Multiple region records exist for this period; select a specific team record.',
};

function sanitizeEmbeddedCodeTokens(
  text: string,
  supportingKpis?: readonly { kpi_key?: string | null; display_name?: string | null; kpi_name?: string | null }[],
): string {
  const knownKeys = new Set(
    (supportingKpis ?? [])
      .map((k) => (k.kpi_key ?? '').trim().toLowerCase())
      .filter(Boolean),
  );
  let out = text.replace(
    /\b([a-z][a-z0-9_]*):([a-z0-9_.-]+)\b/gi,
    (full) => formatInsufficientEvidenceReason(full, supportingKpis).replace(/\.$/, ''),
  );
  for (const [code, phrase] of Object.entries(EXACT_REASON_MAP)) {
    if (out.includes(code)) {
      out = out.replaceAll(code, phrase.replace(/\.$/, ''));
    }
  }
  out = out.replace(/\s*\(([a-z0-9]+(?:_[a-z0-9]+)+)\)/gi, (match, token: string) => {
    const lower = token.toLowerCase();
    if (lower === 'employee_ratio') return match;
    if (knownKeys.has(lower) || /_(?:rate|score|count|pct|percent|kpi|time|ratio)$/i.test(lower)) {
      return '';
    }
    return match;
  });
  return out.replace(/\s{2,}/g, ' ').trim();
}

/**
 * Translates backend snake-case insufficient-evidence and limitation codes
 * into clear manager-facing English while leaving natural prose intact.
 */
export function formatInsufficientEvidenceReason(
  reason: string | null | undefined,
  supportingKpis?: readonly { kpi_key?: string | null; display_name?: string | null; kpi_name?: string | null }[],
): string {
  const raw = String(reason ?? '').trim();
  if (!raw) return '';

  if (EXACT_REASON_MAP[raw]) return EXACT_REASON_MAP[raw];

  const colonIdx = raw.indexOf(':');
  if (colonIdx > 0 && /^[a-z0-9_]+$/i.test(raw.slice(0, colonIdx)) && !/\s/.test(raw.slice(0, colonIdx))) {
    const code = raw.slice(0, colonIdx);
    const kpiToken = raw.slice(colonIdx + 1);
    if (!/\s/.test(kpiToken)) {
      const kpiName = humanizeKpiKeyToken(kpiToken, supportingKpis);
      switch (code) {
        case 'linked_kpi_missing_actual_or_target':
          return `Source actual or target value for ${kpiName} is missing — verify source records.`;
        case 'linked_kpi_not_found':
          return `${kpiName} was not found in this period's KPI records.`;
        case 'linked_kpi_not_below_target':
          return `${kpiName} is already at or above target for this period.`;
        case 'unverified_zero_for_kpi':
          return `${kpiName} is recorded as 0.0% without a verified audit or sample count — verify source records first.`;
        case 'zero_with_missing_raw_kpi_data':
          return `${kpiName} shows 0 with missing raw source entries — verify source records.`;
        case 'missing_actual_for_kpi':
          return `Actual value for ${kpiName} is unavailable in source records.`;
        case 'missing_target_for_kpi':
          return `Target for ${kpiName} is not configured for this period.`;
        case 'missing_source_value_for_kpi':
          return `Raw source entry for ${kpiName} is missing.`;
        default: {
          const readableCode = code.replace(/_/g, ' ').trim();
          const sentence = readableCode.charAt(0).toUpperCase() + readableCode.slice(1);
          return kpiName ? `${sentence} (${kpiName}).` : `${sentence}.`;
        }
      }
    }
  }

  if (/^[a-z0-9_]+$/i.test(raw) && raw.includes('_')) {
    const readable = raw.replace(/_/g, ' ').trim();
    return `${readable.charAt(0).toUpperCase() + readable.slice(1)}.`;
  }

  return sanitizeEmbeddedCodeTokens(raw, supportingKpis);
}

/**
 * Normalizes backend `measured_facts` prose so any leaked reason codes or raw
 * `kpi_key` tokens are converted into readable KPI labels before display.
 */
export function formatMeasuredFact(
  fact: string | null | undefined,
  supportingKpis?: readonly { kpi_key?: string | null; display_name?: string | null; kpi_name?: string | null }[],
): string {
  return formatInsufficientEvidenceReason(fact, supportingKpis);
}

const NON_BLOCKING_WARNING_CODE_PREFIXES = [
  'unverified_zero_for_kpi:',
  'zero_with_missing_raw_kpi_data:',
  'missing_actual_for_kpi:',
  'missing_target_for_kpi:',
  'missing_source_value_for_kpi:',
];

export function collectSuggestionNotices(
  payload: Pick<
    AiCorrectiveActionSuggestionPayload,
    'outcome' | 'insufficient_evidence_reasons' | 'evidence_limitations' | 'supporting_kpis'
  >,
): string[] {
  const rawReasons = Array.isArray(payload.insufficient_evidence_reasons)
    ? payload.insufficient_evidence_reasons
    : [];
  const rawLimitations = Array.isArray(payload.evidence_limitations)
    ? payload.evidence_limitations
    : [];
  const hasLimitations = rawLimitations.some((l) => Boolean(String(l ?? '').trim()));

  const filteredReasons =
    payload.outcome !== 'insufficient_evidence' && hasLimitations
      ? rawReasons.filter(
          (r) => !NON_BLOCKING_WARNING_CODE_PREFIXES.some((prefix) => String(r).startsWith(prefix)),
        )
      : rawReasons;

  const combined = [
    ...filteredReasons.map((r) => formatInsufficientEvidenceReason(r, payload.supporting_kpis)),
    ...rawLimitations.map((l) => formatInsufficientEvidenceReason(l, payload.supporting_kpis)),
  ]
    .map((entry) => entry.trim())
    .filter(Boolean);

  const seen = new Set<string>();
  const deduped: string[] = [];
  for (const item of combined) {
    const norm = item.toLowerCase();
    if (!seen.has(norm)) {
      seen.add(norm);
      deduped.push(item);
    }
  }
  return deduped;
}

/** Only a finite score lift calculated from KPI evidence may be presented as a projection. */
export function hasSupportedProjectedImpact(
  projectedScoreLift: number | null | undefined,
): boolean {
  return (
    typeof projectedScoreLift === 'number' &&
    Number.isFinite(projectedScoreLift) &&
    projectedScoreLift > 0
  );
}
