import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { API_BASE } from '../../config';
import { refreshPerformanceData } from '../../hooks/usePerformanceData';
import { useUserRole } from '../../context/RoleContext';
import { canAccessSettingsContent } from '../../lib/access';
import type { PerformanceLevel } from '../../types';
import {
  MONTHS,
  applyVersion,
  contractLabel,
  emptyPeriod,
  initialReportingPeriod,
  lineFormulaSupported,
  lineSignature,
  monthHasApprovedVersion,
  toPeriodData,
  versionFromPayload,
  type EvaluationLine,
  type EvaluationPeriodData,
  type EvaluationRevision,
  type EvaluationVersion,
  type PeriodScope,
} from './evaluationSettings';
import {
  commitLineInputs,
  inputToStoredTarget,
  numericDraftsDirty,
  targetDraftUnchanged,
  type NumericDrafts,
} from './evaluationInputUnits';
import {
  EVIDENCE_CHANGED_NOTE,
  formatApplyResult,
  formatReviseNotice,
  formatRollbackResult,
  invalidateCommittedEvidence,
  invalidateDraftLifecycle,
  isStaleProofCode,
  pageSlice,
  parseImpactProof,
  periodQueryKey,
  proofAuthorizesApproval,
  type ImpactProof,
} from './monthlyCorrection';
import { EvaluationApplyProgress } from './EvaluationApplyProgress';
import { BACKGROUND_CONTINUES_NOTE, useEvaluationApplyJobs } from './evaluationApplyJobs';
import { EvaluationActions } from './evaluation/EvaluationActions';
import { EvaluationAlerts, EvaluationDraftNotes, EvaluationSettingsNotes } from './evaluation/EvaluationNotices';
import { EvaluationConfirmations } from './evaluation/EvaluationConfirmations';
import { EvaluationContextBar } from './evaluation/EvaluationContextBar';
import { EvaluationHistory } from './evaluation/EvaluationHistory';
import { EvaluationImpactProof } from './evaluation/EvaluationImpactProof';
import { EvaluationKpiLines } from './evaluation/EvaluationKpiLines';
import { EvaluationStepper } from './evaluation/EvaluationStepper';
import { MISSING_CHECKSUM_MESSAGE, STALE_SAVE_MESSAGE, VERSION_DRIFT_MESSAGE } from './evaluation/evaluationMessages';
import { deriveWorkflowState } from './evaluation/evaluationWorkflowState';

type Selection = { scopeId: string; year: number; month: number };

type Scope = PeriodScope & {
  id: string;
  display_name: string;
  performance_level: string;
  position_name: string;
};

type MissingIndicator = { kpiKey: string; count: number };
type RequestError = Error & { code?: string; missingIndicators?: MissingIndicator[] };

function missingIndicators(value: unknown): MissingIndicator[] {
  if (!Array.isArray(value)) return [];
  const records = new Map<string, Set<string>>();
  value.forEach((item: unknown, index) => {
    if (!item || typeof item !== 'object' || !('kpi_key' in item) || typeof item.kpi_key !== 'string' || !item.kpi_key.trim()) return;
    const key = item.kpi_key.trim();
    const ids = records.get(key) ?? new Set<string>();
    const id = 'record_id' in item ? item.record_id : undefined;
    ids.add(typeof id === 'string' || typeof id === 'number' ? `record:${id}` : `entry:${index}`);
    records.set(key, ids);
  });
  return [...records].map(([kpiKey, ids]) => ({ kpiKey, count: ids.size }));
}

type ProofState = { key: string; versionId: string; proof: ImpactProof };

type EditorState = {
  key: string;
  versionId: string;
  checksum: string;
  scopeId: string;
  year: number;
  month: number;
  lines: EvaluationLine[];
  baseLines: EvaluationLine[];
  text: NumericDrafts;
};

const EVALUATION_LEVELS: readonly PerformanceLevel[] = ['Employee', 'Managerial', 'Corporate'];

function selectionKey(selection: Selection) {
  return `${selection.scopeId}|${selection.year}|${selection.month}`;
}

function rulesChecksum(version: { checksum?: string | null }) {
  return typeof version.checksum === 'string' ? version.checksum.trim() : '';
}

function storeVersion(current: EvaluationPeriodData, version: unknown): EvaluationPeriodData {
  const parsed = versionFromPayload(version);
  const applied = applyVersion(current, parsed);
  const token = rulesChecksum(parsed);
  const versionId = parsed.id || applied.versionId;
  return {
    ...applied,
    checksum: token,
    history: applied.history.map((item) => item.id === versionId ? { ...item, checksum: token || null } : item),
  };
}

function cloneLines(lines: readonly EvaluationLine[]): EvaluationLine[] {
  return lines.map((line) => ({ ...line }));
}

/** Direction and source edits ride on the lines captured when editing began. */
function linesFromFrozenBase(editor: EditorState): EvaluationLine[] {
  return editor.baseLines.map((base) => {
    const edited = editor.lines.find((line) => line.kpi_key === base.kpi_key);
    if (!edited || (edited.direction === base.direction && edited.target_mode === base.target_mode)) return base;
    return { ...base, direction: edited.direction, target_mode: edited.target_mode };
  });
}

function isDraftConflictCode(code: string | undefined) {
  return code === 'stale_draft' || code === 'draft_precondition_required';
}

async function readJson(response: Response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body?.detail;
    const message = typeof detail === 'string' ? detail : detail?.message || body?.message || 'Evaluation request failed';
    const error = new Error(message) as RequestError;
    if (detail && typeof detail === 'object' && typeof detail.code === 'string') error.code = detail.code;
    if (error.code === 'missing_evidence') error.missingIndicators = missingIndicators(detail.missing_evidence);
    throw error;
  }
  return body?.data ?? body;
}

function errorText(caught: unknown) {
  if (!(caught instanceof Error)) return 'Evaluation request failed';
  const code = (caught as RequestError).code;
  return code ? `${code}: ${caught.message}` : caught.message;
}

export function EvaluationSettingsPanel() {
  const queryClient = useQueryClient();
  const { role, fetchWithRole } = useUserRole();
  const isAdmin = canAccessSettingsContent(role);
  const [year, setYear] = useState(() => initialReportingPeriod(window.location.search).year);
  const [month, setMonth] = useState(() => initialReportingPeriod(window.location.search).month);
  const [level, setLevel] = useState<PerformanceLevel>('Employee');
  const [scopeId, setScopeId] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [proof, setProof] = useState<ProofState | null>(null);
  const [page, setPage] = useState(0);
  const [notice, setNotice] = useState<{ key: string; text: string } | null>(null);
  const [actionError, setActionError] = useState<{ key: string; text: string; missingIndicators?: MissingIndicator[] } | null>(null);
  const [rollbackConfirm, setRollbackConfirm] = useState<{ key: string; revisionId: string } | null>(null);
  const [adoptConfirm, setAdoptConfirm] = useState<{ key: string; versionId: string } | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{ key: string; versionId: string } | null>(null);
  const [conflict, setConflict] = useState<{ key: string; text: string } | null>(null);
  const [backgroundNote, setBackgroundNote] = useState<string | null>(null);
  const gate = useRef(false);
  const catalogQuery = useQuery({
    queryKey: ['evaluation-settings', 'catalog'],
    enabled: isAdmin,
    queryFn: async ({ signal }) => {
      const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/catalog`, { signal });
      const data = await readJson(response);
      return (Array.isArray(data?.scopes) ? data.scopes : []) as Scope[];
    },
  });
  const scopes = catalogQuery.data ?? [];
  // The Overview links here with ?scope=<id>. The id is read once, when the catalog first lists it. An unknown id changes nothing.
  const [pendingScopeId, setPendingScopeId] = useState(() => new URLSearchParams(window.location.search).get('scope')?.trim() || null);
  if (pendingScopeId && catalogQuery.data) {
    const match = catalogQuery.data.find((item) => item.id === pendingScopeId);
    const matchedLevel = EVALUATION_LEVELS.find((item) => item === match?.performance_level);
    setPendingScopeId(null);
    if (match && matchedLevel) {
      setLevel(matchedLevel);
      setScopeId(match.id);
    }
  }
  const levelScopes = useMemo(
    () => (catalogQuery.data ?? []).filter((item) => item.performance_level === level),
    [catalogQuery.data, level],
  );
  const resolvedScopeId = levelScopes.find((item) => item.id === scopeId)?.id
    ?? levelScopes.find((item) => item.readiness === 'supported')?.id
    ?? levelScopes[0]?.id ?? '';
  const selection = useMemo(
    () => ({ scopeId: resolvedScopeId, year, month }),
    [resolvedScopeId, year, month],
  );
  const selectionRef = useRef(selection);
  useLayoutEffect(() => {
    selectionRef.current = selection;
  }, [selection]);
  const currentKey = selectionKey(selection);
  const yearValid = year >= 2000 && year <= 2100;
  const periodQuery = useQuery({
    queryKey: periodQueryKey(resolvedScopeId, year, month),
    enabled: isAdmin && Boolean(resolvedScopeId) && yearValid && month >= 1 && month <= 12,
    queryFn: async ({ signal }) => {
      const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/periods?scope_id=${resolvedScopeId}&year=${year}&month=${month}`, { signal });
      const data = await readJson(response);
      if (signal.aborted) throw new DOMException('The month request was cancelled.', 'AbortError');
      return toPeriodData(data);
    },
  });

  const isCurrent = (vars: Selection) => {
    const current = selectionRef.current;
    return current.scopeId === vars.scopeId && current.year === vars.year && current.month === vars.month;
  };

  const remember = (key: string, updater: (current: EvaluationPeriodData) => EvaluationPeriodData) => {
    const [scope, periodYear, periodMonth] = key.split('|');
    queryClient.setQueryData<EvaluationPeriodData>(periodQueryKey(scope, Number(periodYear), Number(periodMonth)), (current) => updater(current ?? emptyPeriod()));
  };

  const invalidateSettings = (vars: Selection) => {
    invalidateDraftLifecycle(queryClient, vars);
  };

  const invalidateCommitted = (vars: Selection) => {
    invalidateCommittedEvidence(queryClient, vars, refreshPerformanceData);
  };

  const releaseGate = () => { gate.current = false; };
  const applyJobs = useEvaluationApplyJobs({
    active: isAdmin,
    selection,
    selectionReady: Boolean(resolvedScopeId) && yearValid && month >= 1 && month <= 12,
    isCurrent,
    fetchWithRole,
    releaseGate,
    reportError: (vars, text) => {
      if (!isCurrent(vars)) return;
      setActionError({ key: selectionKey(vars), text });
    },
    invalidateCommitted,
  });

  const save = useMutation({
    retry: false,
    mutationFn: async (vars: Selection & { versionId: string; checksum: string; lines: EvaluationLine[] }) => {
      const checksum = vars.checksum.trim();
      if (!checksum) throw new Error(MISSING_CHECKSUM_MESSAGE);
      await queryClient.cancelQueries({ queryKey: periodQueryKey(vars.scopeId, vars.year, vars.month) });
      const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/drafts/${vars.versionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lines: vars.lines, expected_checksum: checksum }),
      });
      return readJson(response) as Promise<EvaluationVersion>;
    },
    onSuccess: (version, vars) => {
      const key = selectionKey(vars);
      remember(key, (current) => storeVersion(current, { ...version, lines: version.lines || vars.lines }));
      if (!isCurrent(vars)) return;
      setEditor((current) => current?.key === key ? null : current);
      setProof(null);
      setConflict(null);
      setNotice({ key, text: 'Draft saved.' });
    },
    onError: (caught, vars) => {
      if (!isCurrent(vars)) return;
      const key = selectionKey(vars);
      const code = (caught as RequestError).code;
      if (isDraftConflictCode(code)) {
        setConflict({ key, text: STALE_SAVE_MESSAGE });
      }
      setActionError({ key, text: errorText(caught) });
    },
    onSettled: () => { gate.current = false; },
  });

  const openDraft = useMutation({
    retry: false,
    mutationFn: async (vars: Selection & { copyPrevious: boolean }) => {
      await queryClient.cancelQueries({ queryKey: periodQueryKey(vars.scopeId, vars.year, vars.month) });
      const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/drafts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope_id: vars.scopeId, year: vars.year, month: vars.month, copy_previous: vars.copyPrevious }),
      });
      return readJson(response) as Promise<EvaluationVersion>;
    },
    onSuccess: (version, vars) => {
      const key = selectionKey(vars);
      remember(key, (current) => storeVersion(current, version));
      if (!isCurrent(vars)) return;
      setEditor((current) => current?.key === key ? null : current);
      setProof(null);
      setConflict(null);
      setNotice({ key, text: vars.copyPrevious ? (version.notes || 'Previous month copied.') : 'Draft opened for this month.' });
    },
    onError: (caught, vars) => {
      if (isCurrent(vars)) setActionError({ key: selectionKey(vars), text: errorText(caught) });
    },
    onSettled: () => { gate.current = false; },
  });

  const revise = useMutation({
    retry: false,
    mutationFn: async (vars: Selection & { versionId: string }) => {
      await queryClient.cancelQueries({ queryKey: periodQueryKey(vars.scopeId, vars.year, vars.month) });
      const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/versions/${vars.versionId}/revise`, { method: 'POST' });
      return readJson(response) as Promise<EvaluationVersion & { resumed?: boolean }>;
    },
    onSuccess: (version, vars) => {
      const key = selectionKey(vars);
      remember(key, (current) => storeVersion(current, version));
      invalidateSettings(vars);
      if (!isCurrent(vars)) return;
      setEditor((current) => current?.key === key ? null : current);
      setProof(null);
      setConflict(null);
      setNotice({ key, text: formatReviseNotice(version) });
    },
    onError: (caught, vars) => {
      if (isCurrent(vars)) setActionError({ key: selectionKey(vars), text: errorText(caught) });
    },
    onSettled: () => { gate.current = false; },
  });

  const impact = useMutation({
    retry: false,
    mutationFn: async (vars: Selection & { versionId: string }) => {
      const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/drafts/${vars.versionId}/impact-preview`, { method: 'POST' });
      return readJson(response);
    },
    onSuccess: (data, vars) => {
      if (!isCurrent(vars)) return;
      const cached = queryClient.getQueryData<EvaluationPeriodData>(periodQueryKey(vars.scopeId, vars.year, vars.month));
      const parsed = parseImpactProof(data);
      if (!cached || cached.versionId !== vars.versionId || !proofAuthorizesApproval(parsed, vars.versionId, vars)) {
        setProof(null);
        setActionError({ key: selectionKey(vars), text: 'Impact preview did not satisfy the approval gate for this saved draft.' });
        return;
      }
      setPage(0);
      setProof({ key: selectionKey(vars), versionId: vars.versionId, proof: parsed });
    },
    onError: (caught, vars) => {
      if (!isCurrent(vars)) return;
      setProof(null);
      setActionError({ key: selectionKey(vars), text: errorText(caught), missingIndicators: (caught as RequestError).missingIndicators });
    },
    onSettled: () => { gate.current = false; },
  });

  const approve = useMutation({
    retry: false,
    mutationFn: async (vars: Selection & { versionId: string }) => {
      await queryClient.cancelQueries({ queryKey: periodQueryKey(vars.scopeId, vars.year, vars.month) });
      const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/drafts/${vars.versionId}/approve`, { method: 'POST' });
      return readJson(response) as Promise<EvaluationVersion>;
    },
    onSuccess: (version, vars) => {
      const key = selectionKey(vars);
      remember(key, (current) => storeVersion(current, version));
      invalidateSettings(vars);
      if (!isCurrent(vars)) return;
      setProof(null);
      setEditor((current) => current?.key === key ? null : current);
      setConflict(null);
      setNotice({ key, text: 'Approved. Existing scores were not recalculated.' });
    },
    onError: (caught, vars) => {
      if (!isCurrent(vars)) return;
      if (isStaleProofCode((caught as RequestError).code)) setProof(null);
      setActionError({ key: selectionKey(vars), text: errorText(caught) });
    },
    onSettled: () => { gate.current = false; },
  });

  const apply = useMutation({
    retry: false,
    mutationFn: async (vars: Selection) => {
      const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scope_id: vars.scopeId, year: vars.year, month: vars.month }),
      });
      return readJson(response);
    },
    onSuccess: (result, vars) => {
      invalidateCommitted(vars);
      if (!isCurrent(vars)) return;
      setNotice({ key: selectionKey(vars), text: formatApplyResult(result) });
    },
    onError: (caught, vars) => {
      if (isCurrent(vars)) setActionError({ key: selectionKey(vars), text: errorText(caught) });
    },
    onSettled: () => { gate.current = false; },
  });

  const rollback = useMutation({
    retry: false,
    mutationFn: async (vars: Selection & { revisionId: string }) => {
      const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/revisions/${vars.revisionId}/rollback`, { method: 'POST' });
      return readJson(response);
    },
    onSuccess: (result, vars) => {
      invalidateCommitted(vars);
      if (!isCurrent(vars)) return;
      setRollbackConfirm(null);
      setNotice({ key: selectionKey(vars), text: formatRollbackResult(result) });
    },
    onError: (caught, vars) => {
      if (!isCurrent(vars)) return;
      const code = (caught as RequestError).code;
      const text = code === 'evidence_changed' ? `${errorText(caught)} ${EVIDENCE_CHANGED_NOTE}` : errorText(caught);
      setActionError({ key: selectionKey(vars), text });
    },
    onSettled: () => { gate.current = false; },
  });

  const adopt = useMutation({
    retry: false,
    mutationFn: async (vars: Selection & { versionId: string; checksum: string }) => {
      const checksum = vars.checksum.trim();
      if (!checksum) throw new Error(MISSING_CHECKSUM_MESSAGE);
      await queryClient.cancelQueries({ queryKey: periodQueryKey(vars.scopeId, vars.year, vars.month) });
      const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/versions/${vars.versionId}/adopt-operational`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm: true, expected_checksum: checksum }),
      });
      return readJson(response) as Promise<EvaluationVersion>;
    },
    onSuccess: (version, vars) => {
      const key = selectionKey(vars);
      remember(key, (current) => storeVersion(current, version));
      invalidateSettings(vars);
      if (!isCurrent(vars)) return;
      setEditor((current) => current?.key === key ? null : current);
      setProof(null);
      setConflict(null);
      setAdoptConfirm(null);
      setNotice({ key, text: 'This month now uses the original upload settings. Approved results stay unchanged until you preview, approve, and Apply. Other months were not changed.' });
    },
    onError: (caught, vars) => {
      if (!isCurrent(vars)) return;
      setActionError({ key: selectionKey(vars), text: errorText(caught) });
    },
    onSettled: () => { gate.current = false; },
  });

  const deleteDraft = useMutation({
    retry: false,
    mutationFn: async (vars: Selection & { versionId: string; checksum: string }) => {
      const checksum = vars.checksum.trim();
      if (!checksum) throw new Error(MISSING_CHECKSUM_MESSAGE);
      await queryClient.cancelQueries({ queryKey: periodQueryKey(vars.scopeId, vars.year, vars.month) });
      const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/drafts/${vars.versionId}?expected_checksum=${encodeURIComponent(checksum)}`, { method: 'DELETE' });
      return readJson(response);
    },
    onSuccess: (_result, vars) => {
      const key = selectionKey(vars);
      invalidateSettings(vars);
      if (!isCurrent(vars)) return;
      setEditor(null);
      setProof(null);
      setConflict(null);
      setDeleteConfirm(null);
      setNotice({ key, text: 'Draft deleted. You can start a new draft.' });
    },
    onError: (caught, vars) => {
      if (!isCurrent(vars)) return;
      const key = selectionKey(vars);
      if (isDraftConflictCode((caught as RequestError).code)) {
        setConflict({ key, text: STALE_SAVE_MESSAGE });
      }
      setDeleteConfirm(null);
      setActionError({ key, text: errorText(caught) });
    },
    onSettled: () => { gate.current = false; },
  });

  const busy = save.isPending || openDraft.isPending || revise.isPending || impact.isPending || approve.isPending || apply.isPending || rollback.isPending || adopt.isPending || deleteDraft.isPending || applyJobs.pending;
  const period = periodQuery.data;
  const serverLines = period?.lines ?? [];
  const editorActive = editor?.key === currentKey ? editor : null;
  const lines = editorActive?.lines ?? serverLines;
  const referenceLines = editorActive?.baseLines ?? serverLines;
  const textDrafts = editorActive?.text ?? {};
  const frozenLines = editorActive ? linesFromFrozenBase(editorActive) : null;
  const draftCommit = frozenLines ? commitLineInputs(frozenLines, textDrafts) : null;
  const inputBlocked = Boolean(draftCommit && !draftCommit.ok);
  const effectiveLines = draftCommit?.ok ? draftCommit.lines : lines;
  const totalWeight = effectiveLines.reduce((sum, line) => sum + line.weight, 0);
  // Match the API's 0.0001 tolerance, allowing floating-point summation noise.
  const weightTotalInvalid = !Number.isFinite(totalWeight) || Math.abs(totalWeight - 1) > 0.0001 + Number.EPSILON;
  const draftProblems = draftCommit && !draftCommit.ok ? draftCommit.errors : [];
  const dirty = editorActive != null && (
    lineSignature(editorActive.lines) !== lineSignature(editorActive.baseLines) || numericDraftsDirty(editorActive.baseLines, textDrafts)
  );
  const versionDrift = Boolean(editorActive && period?.versionId && editorActive.versionId !== period.versionId);
  const activeChecksum = editorActive ? editorActive.checksum.trim() : (period?.checksum ?? '').trim();
  const checksumMissing = Boolean(period?.status === 'draft' && period.versionId && !activeChecksum);
  const conflictText = versionDrift ? VERSION_DRIFT_MESSAGE : conflict?.key === currentKey ? conflict.text : '';
  const periodLoading = Boolean(resolvedScopeId) && periodQuery.isLoading;
  const catalogScope = scopes.find((item) => item.id === resolvedScopeId) || null;
  const readinessSource = period?.scope?.readiness ? period.scope : catalogScope;
  const blocked = readinessSource != null && readinessSource.readiness !== 'supported';
  const unsupported = lines.some((line) => !lineFormulaSupported(line));
  const approved = period?.status === 'approved';
  const controlsLocked = busy || periodLoading || periodQuery.isError || !period;
  const visibleProof = proof?.key === currentKey && proof.versionId === period?.versionId ? proof.proof : null;
  const approvalReady = Boolean(period?.versionId && visibleProof && proofAuthorizesApproval(visibleProof, period.versionId, selection));
  const message = notice?.key === currentKey ? notice.text : '';
  const loadError = periodQuery.error instanceof Error ? periodQuery.error.message : catalogQuery.error instanceof Error ? catalogQuery.error.message : '';
  const error = (actionError?.key === currentKey ? actionError.text : '') || loadError;
  const missing = actionError?.key === currentKey ? actionError.missingIndicators ?? [] : [];
  const monthApproved = monthHasApprovedVersion(period);
  const actionsReady = Boolean(period) && !periodLoading && !blocked;
  const comparisons = visibleProof?.comparisons ?? [];
  const comparisonPage = pageSlice(comparisons, page);
  const pendingRollback = rollbackConfirm?.key === currentKey ? period?.revisions.find((item) => item.id === rollbackConfirm.revisionId && item.canRollback) : undefined;
  const pendingAdopt = adoptConfirm?.key === currentKey && adoptConfirm.versionId === period?.versionId ? adoptConfirm : undefined;
  const pendingDelete = deleteConfirm?.key === currentKey && deleteConfirm.versionId === period?.versionId ? deleteConfirm : undefined;
  const deleteChecksum = (period?.checksum ?? '').trim();
  const canDeleteDraft = Boolean(period?.status === 'draft' && period.versionId);
  const revisionChoice = period?.revisionChoice;
  const canAdopt = Boolean(actionsReady && revisionChoice?.available && revisionChoice.code === 'adopt_operational_upload' && period?.versionId);
  const directionOwned = period?.contract === 'operational_upload';

  const begin = () => {
    if (gate.current || busy) return false;
    gate.current = true;
    setActionError(null);
    return true;
  };

  const changeSelection = (next: Partial<Selection>) => {
    const nextSelection = {
      scopeId: next.scopeId != null ? next.scopeId : selection.scopeId,
      year: next.year != null ? next.year : selection.year,
      month: next.month != null ? next.month : selection.month,
    };
    const leavingOpenJob = selectionKey(nextSelection) !== currentKey && applyJobs.tracksOpenJob;
    if (next.scopeId != null) setScopeId(next.scopeId);
    if (next.year != null) setYear(next.year);
    if (next.month != null) setMonth(next.month);
    setEditor(null);
    setProof(null);
    setConflict(null);
    setRollbackConfirm(null);
    setAdoptConfirm(null);
    setDeleteConfirm(null);
    setPage(0);
    setBackgroundNote(leavingOpenJob ? BACKGROUND_CONTINUES_NOTE : null);
  };

  const changeLevel = (nextLevel: string) => {
    const validLevel = EVALUATION_LEVELS.find((item) => item === nextLevel);
    if (!validLevel || validLevel === level) return;
    if (dirty && !window.confirm('Discard unsaved draft edits and change performance level?')) return;
    const candidates = scopes.filter((item) => item.performance_level === validLevel);
    const nextScope = candidates.find((item) => item.readiness === 'supported') ?? candidates[0];
    changeSelection({ scopeId: nextScope?.id ?? '' });
    setLevel(validLevel);
  };

  const ensureEditor = (current: EditorState | null): EditorState => {
    if (current?.key === currentKey) return current;
    const baseLines = cloneLines(serverLines);
    return {
      key: currentKey,
      versionId: period?.versionId ?? '',
      checksum: (period?.checksum ?? '').trim(),
      scopeId: selection.scopeId,
      year: selection.year,
      month: selection.month,
      lines: cloneLines(baseLines),
      baseLines,
      text: {},
    };
  };

  const reloadDraft = () => {
    const vars = selectionRef.current;
    setEditor(null);
    setProof(null);
    setConflict(null);
    setActionError(null);
    setNotice(null);
    void queryClient.invalidateQueries({ queryKey: periodQueryKey(vars.scopeId, vars.year, vars.month) });
  };

  const discardDraft = () => {
    setEditor(null);
    setProof(null);
    setConflict(null);
    setActionError(null);
  };

  const updateLine = (key: string, patch: Partial<EvaluationLine>) => {
    setEditor((current) => {
      const base = ensureEditor(current);
      return { ...base, lines: base.lines.map((line) => line.kpi_key === key ? { ...line, ...patch } : line) };
    });
    setProof(null);
    setNotice(null);
  };

  const editText = (key: string, field: 'targetText' | 'weightText', value: string) => {
    const line = lines.find((item) => item.kpi_key === key);
    if (!line || busy || approved || !lineFormulaSupported(line)) return;
    setEditor((current) => {
      const base = ensureEditor(current);
      const previous = base.text[key] ?? {};
      const text = { ...base.text, [key]: { ...previous, [field]: value } };
      if (field !== 'targetText') return { ...base, text };
      const baseLine = base.baseLines.find((item) => item.kpi_key === key);
      if (!baseLine) return { ...base, text };
      const unchanged = targetDraftUnchanged(baseLine, value);
      const finiteChange = !unchanged && inputToStoredTarget(value, baseLine.unit).ok;
      const nextLines = base.lines.map((item) => {
        if (item.kpi_key !== key) return item;
        if (unchanged) return { ...item, target_mode: baseLine.target_mode };
        if (finiteChange) return { ...item, target_mode: 'fixed' };
        return item;
      });
      return { ...base, lines: nextLines, text };
    });
    setProof(null);
    setNotice(null);
  };

  const runSave = () => {
    if (!period?.versionId || period.status !== 'draft' || unsupported || inputBlocked || weightTotalInvalid || checksumMissing || versionDrift || conflictText) return;
    const active = editor?.key === currentKey ? editor : null;
    let payload = serverLines;
    let versionId = period.versionId;
    let checksum = (period.checksum ?? '').trim();
    let target = selection;
    if (active) {
      if (
        active.versionId !== period.versionId
        || active.scopeId !== selection.scopeId
        || active.year !== selection.year
        || active.month !== selection.month
      ) {
        setConflict({ key: currentKey, text: VERSION_DRIFT_MESSAGE });
        return;
      }
      const committed = commitLineInputs(linesFromFrozenBase(active), active.text);
      if (!committed.ok) {
        setActionError({ key: currentKey, text: committed.errors.map((item) => item.message).join(' ') });
        return;
      }
      payload = committed.lines;
      versionId = active.versionId;
      checksum = active.checksum.trim();
      target = { scopeId: active.scopeId, year: active.year, month: active.month };
    }
    if (!checksum) {
      setActionError({ key: currentKey, text: MISSING_CHECKSUM_MESSAGE });
      return;
    }
    if (!begin()) return;
    save.mutate({ ...target, versionId, checksum, lines: payload });
  };

  const runOpen = (copyPrevious: boolean) => {
    if (!resolvedScopeId || !period || monthApproved || !begin()) return;
    openDraft.mutate({ ...selection, copyPrevious });
  };

  const runRevise = () => {
    if (!period?.versionId || period.status !== 'approved' || !begin()) return;
    revise.mutate({ ...selection, versionId: period.versionId });
  };

  const runImpact = () => {
    if (!period?.versionId || period.status !== 'draft' || dirty || unsupported || blocked || !begin()) return;
    impact.mutate({ ...selection, versionId: period.versionId });
  };

  const runApprove = () => {
    if (!period?.versionId || period.status !== 'draft' || dirty || unsupported || !approvalReady || !begin()) return;
    approve.mutate({ ...selection, versionId: period.versionId });
  };

  const runApply = () => {
    if (!resolvedScopeId || period?.status !== 'approved' || dirty || blocked || applyJobs.blockEnqueue) return;
    if (!begin()) return;
    if (applyJobs.mode === 'sync') {
      apply.mutate(selection);
      return;
    }
    if (applyJobs.mode === 'async' && applyJobs.enqueue(selection)) return;
    gate.current = false;
  };

  const runCancelApply = () => {
    if (!begin()) return;
    if (!applyJobs.commitCancel()) gate.current = false;
  };

  const runRetryApply = () => {
    if (!applyJobs.actions?.showRetry || !begin()) return;
    if (!applyJobs.commitRetry()) gate.current = false;
  };

  const runRecoverApply = () => {
    if (!applyJobs.actions?.showRecover || !begin()) return;
    if (!applyJobs.commitRecover()) gate.current = false;
  };

  const runRollback = (revision: EvaluationRevision) => {
    if (!revision.canRollback || !begin()) return;
    rollback.mutate({ ...selection, revisionId: revision.id });
  };

  const requestDelete = () => {
    if (!canDeleteDraft || !period?.versionId || controlsLocked || !deleteChecksum) return;
    setActionError(null);
    setDeleteConfirm({ key: currentKey, versionId: period.versionId });
  };

  const runDelete = () => {
    if (!pendingDelete || !period?.versionId || !canDeleteDraft || !deleteChecksum || !begin()) return;
    deleteDraft.mutate({ ...selection, versionId: period.versionId, checksum: deleteChecksum });
  };

  const requestAdopt = () => {
    if (!canAdopt || !period?.versionId || controlsLocked || versionDrift || conflictText) return;
    setActionError(null);
    setAdoptConfirm({ key: currentKey, versionId: period.versionId });
  };

  const runAdopt = () => {
    const current = selectionRef.current;
    const key = selectionKey(current);
    if (!adoptConfirm || adoptConfirm.key !== key || adoptConfirm.versionId !== period?.versionId) return;
    const active = editor?.key === key ? editor : null;
    if (active && (active.versionId !== period?.versionId || active.scopeId !== current.scopeId || active.year !== current.year || active.month !== current.month)) {
      setConflict({ key, text: VERSION_DRIFT_MESSAGE });
      return;
    }
    const checksum = (active?.checksum || period?.checksum || '').trim();
    if (!checksum) {
      setActionError({ key, text: MISSING_CHECKSUM_MESSAGE });
      return;
    }
    if (!begin()) return;
    adopt.mutate({ ...current, versionId: adoptConfirm.versionId, checksum });
  };

  if (!isAdmin) {
    return (
      <div className="min-w-0 space-y-4">
        <header>
          <h2 className="text-xl font-black text-[var(--text-primary)]">Evaluation settings</h2>
          <p className="mt-1 text-xs text-[var(--text-muted)]">Revise an approved month, review the stored impact, then approve and apply as separate steps.</p>
        </header>
        <p role="status" className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-4 py-3 text-xs text-[var(--text-secondary)]">Evaluation settings are limited to Admin.</p>
      </div>
    );
  }

  const scopeLabel = catalogScope ? `${catalogScope.display_name} · ${catalogScope.performance_level}${catalogScope.position_name ? ` · ${catalogScope.position_name}` : ''}` : 'No scope';
  const monthName = MONTHS[month - 1] || '';
  const workflow = deriveWorkflowState({
    loading: catalogQuery.isPending || periodLoading,
    blocked,
    unavailable: periodQuery.isError || !resolvedScopeId || !yearValid,
    hasVersion: Boolean(period?.versionId),
    periodStatus: period?.status ?? '',
    versionId: period?.versionId ?? '',
    revisions: period?.revisions ?? [],
    dirty,
    inputBlocked,
    weightTotalInvalid,
    unsupported,
    checksumMissing,
    versionDrift,
    conflictPresent: Boolean(conflictText),
    approvalReady,
    controlsLocked,
    applyMode: applyJobs.mode,
    blockEnqueue: applyJobs.blockEnqueue,
  });
  // Each disabled expression below is the one the button had before the split. The workflow state mirrors it, and its tests check the mirror.
  const saveDisabled = controlsLocked || !period?.versionId || period?.status !== 'draft' || unsupported || inputBlocked || weightTotalInvalid || checksumMissing || versionDrift || Boolean(conflictText);
  const impactDisabled = controlsLocked || !period?.versionId || period?.status !== 'draft' || dirty || unsupported;
  const approveDisabled = controlsLocked || !period?.versionId || dirty || period?.status !== 'draft' || !approvalReady;
  const reviseDisabled = controlsLocked || !period?.versionId;
  const applyDisabled = controlsLocked || period?.status !== 'approved' || dirty || applyJobs.blockEnqueue;
  const deleteDisabled = controlsLocked || !deleteChecksum;
  const adoptDisabled = controlsLocked || versionDrift || Boolean(conflictText);
  const scopeOptions = levelScopes.map((item) => {
    const readiness = item.id === resolvedScopeId && !periodLoading && !periodQuery.isError
      ? readinessSource?.readiness ?? item.readiness
      : item.readiness;
    const suffix = readiness === 'supported' ? '' : readiness === 'unlinked_baseline' ? ' · unlinked' : ' · blocked';
    return { id: item.id, label: `${item.display_name}${item.position_name ? ` · ${item.position_name}` : ''}${suffix}` };
  });
  const scopeCountText = catalogQuery.isPending
    ? 'Loading scopes…'
    : levelScopes.length === 0
      ? `No evaluation scopes are available for ${level}. Choose another performance level.`
      : `${levelScopes.length} ${levelScopes.length === 1 ? 'scope' : 'scopes'} · ${scopeLabel}`;

  return (
    <div className="min-w-0 space-y-4" aria-busy={periodLoading || busy}>
      <header>
        <h2 className="text-xl font-black text-[var(--text-primary)]">Evaluation settings</h2>
        <p className="mt-1 text-xs text-[var(--text-muted)]">Choose a team and month, then edit targets and weights using its saved performance values. No new upload is needed when those values are available. Other months stay unchanged. Use 0% weight to track an indicator without changing the score.</p>
      </header>
      <EvaluationAlerts
        error={error}
        missing={missing}
        lines={lines}
        message={message}
        applyMode={applyJobs.mode}
        unavailableMessage={applyJobs.unavailableMessage}
        onRetryAvailability={applyJobs.retryAvailability}
        backgroundNote={backgroundNote}
        problem={applyJobs.problem}
        onRefreshJob={applyJobs.refreshJob}
      />
      {applyJobs.presentation && applyJobs.job && applyJobs.actions && <EvaluationApplyProgress
        job={applyJobs.job}
        presentation={applyJobs.presentation}
        actions={applyJobs.actions}
        confirmCancel={applyJobs.confirmCancel}
        busy={busy}
        onArmCancel={applyJobs.armCancel}
        onConfirmCancel={runCancelApply}
        onDismissCancel={applyJobs.dismissCancel}
        onRetry={runRetryApply}
        onRecover={runRecoverApply}
      />}
      <EvaluationContextBar
        level={level}
        levels={EVALUATION_LEVELS}
        onLevelChange={changeLevel}
        scopeId={resolvedScopeId}
        scopeOptions={scopeOptions}
        emptyScopeText={levelScopes.length === 0 ? (catalogQuery.isPending ? 'Loading scopes…' : 'No scopes for this level') : null}
        scopeDisabled={levelScopes.length === 0}
        onScopeChange={(value) => changeSelection({ scopeId: value })}
        month={month}
        onMonthChange={(value) => changeSelection({ month: value })}
        year={year}
        onYearChange={(value) => changeSelection({ year: value })}
        scopeCountText={scopeCountText}
        status={{ label: workflow.label, tone: workflow.tone }}
      />
      <EvaluationSettingsNotes
        blocked={blocked}
        settingsSource={period?.contract ? contractLabel(period.contract) : null}
        monthName={monthName}
        year={year}
        level={level}
        canAdopt={canAdopt}
        blockReason={readinessSource?.block_reason}
        historyNote={readinessSource?.history_note}
      />
      <EvaluationStepper steps={workflow.steps} />
      {actionsReady && <EvaluationActions
        primary={workflow.primaryAction}
        approved={approved}
        monthApproved={monthApproved}
        canDeleteDraft={canDeleteDraft}
        applyVisible={applyJobs.mode === 'sync' || applyJobs.mode === 'async'}
        adoptVisible={!blocked && canAdopt}
        disabled={{
          new_draft: controlsLocked,
          copy_previous: controlsLocked,
          revise: reviseDisabled,
          save: saveDisabled,
          impact: impactDisabled,
          approve: approveDisabled,
          delete: deleteDisabled,
          apply: applyDisabled,
          adopt: adoptDisabled,
        }}
        onAction={{
          new_draft: () => runOpen(false),
          copy_previous: () => runOpen(true),
          revise: runRevise,
          save: runSave,
          impact: runImpact,
          approve: runApprove,
          delete: requestDelete,
          apply: runApply,
          adopt: requestAdopt,
        }}
      />}
      <EvaluationDraftNotes
        blocked={blocked}
        approved={approved}
        checksumMissing={checksumMissing}
        conflictText={conflictText}
        dirty={dirty}
        unsupported={unsupported}
        sourceVersionId={period?.sourceVersionId}
        sourceChecksum={period?.sourceChecksum}
        notes={period?.notes}
        onReload={reloadDraft}
        onDiscard={discardDraft}
      />
      {visibleProof && <EvaluationImpactProof
        proof={visibleProof}
        lines={lines}
        comparisons={comparisons}
        comparisonPage={comparisonPage}
        onPageChange={setPage}
      />}
      <EvaluationKpiLines
        lines={lines}
        referenceLines={referenceLines}
        textDrafts={textDrafts}
        draftProblems={draftProblems}
        totalWeight={totalWeight}
        inputBlocked={inputBlocked}
        weightTotalInvalid={weightTotalInvalid}
        periodLoading={periodLoading}
        blocked={blocked}
        busy={busy}
        approved={approved}
        directionOwned={directionOwned}
        onEditText={editText}
        onUpdateLine={updateLine}
      />
      <EvaluationConfirmations
        adoptPending={Boolean(pendingAdopt)}
        dirty={dirty}
        approved={approved}
        busy={busy}
        monthName={monthName}
        year={year}
        scopeLabel={scopeLabel}
        onConfirmAdopt={runAdopt}
        onKeepAdopt={() => setAdoptConfirm(null)}
        deletePending={Boolean(pendingDelete)}
        onConfirmDelete={runDelete}
        onKeepDraft={() => setDeleteConfirm(null)}
        rollbackRevision={pendingRollback}
        onConfirmRollback={runRollback}
        onKeepRecords={() => setRollbackConfirm(null)}
      />
      <EvaluationHistory
        history={period?.history ?? []}
        revisions={period?.revisions ?? []}
        periodLoading={periodLoading}
        monthName={monthName}
        busy={busy}
        onRequestRollback={(revisionId) => setRollbackConfirm({ key: currentKey, revisionId })}
      />
    </div>
  );
}
