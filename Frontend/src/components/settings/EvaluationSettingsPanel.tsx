import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, Check, Copy, History, Save } from 'lucide-react';
import { API_BASE } from '../../config';
import { refreshPerformanceData } from '../../hooks/usePerformanceData';
import { useUserRole } from '../../context/RoleContext';
import { canAccessSettingsContent } from '../../lib/access';
import {
  MONTHS,
  READ_ONLY_APPROVED_NOTE,
  UNSAVED_PREVIEW_NOTE,
  UNSUPPORTED_FORMULA_NOTE,
  applyVersion,
  emptyPeriod,
  initialReportingPeriod,
  lineFormulaSupported,
  lineSignature,
  monthHasApprovedVersion,
  revisionLabel,
  toPeriodData,
  versionLabel,
  type EvaluationLine,
  type EvaluationPeriodData,
  type EvaluationRevision,
  type EvaluationVersion,
  type PeriodScope,
} from './evaluationSettings';
import {
  WEIGHT_FIELD_HELP,
  WEIGHT_FIELD_LABEL,
  commitLineInputs,
  formatIdentifiedTarget,
  isExplicitPercentUnit,
  inputToStoredTarget,
  numericDraftsDirty,
  savedTargetSummary,
  savedWeightSummary,
  storedTargetToInput,
  storedWeightToInput,
  targetDraftUnchanged,
  targetFieldHelp,
  targetFieldLabel,
  type NumericDrafts,
} from './evaluationInputUnits';
import {
  EVIDENCE_CHANGED_NOTE,
  FIXED_MISMATCH_NOTE,
  ROLLBACK_CONFIRM_NOTE,
  displayNumber,
  formatApplyResult,
  formatKpiLine,
  formatImpactSummary,
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
import { BACKGROUND_CONTINUES_NOTE, CHECKING_APPLY_NOTE, useEvaluationApplyJobs } from './evaluationApplyJobs';

type Selection = { scopeId: string; year: number; month: number };

type Scope = PeriodScope & {
  id: string;
  display_name: string;
  performance_level: string;
  position_name: string;
};

type RequestError = Error & { code?: string };

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

const STALE_SAVE_MESSAGE = 'This draft changed after you opened it. Reload the draft or discard your edits. Nothing was saved.';
const VERSION_DRIFT_MESSAGE = 'This month is showing a different version from the one you started editing. Reload the draft or discard your edits. Saving will not write that other version.';
const MISSING_CHECKSUM_MESSAGE = 'Save is unavailable until this draft has a rules checksum. Reload the month. An empty checksum is not sent.';

function selectionKey(selection: Selection) {
  return `${selection.scopeId}|${selection.year}|${selection.month}`;
}

function rulesChecksum(version: { checksum?: string | null }) {
  return typeof version.checksum === 'string' ? version.checksum.trim() : '';
}

function storeVersion(current: EvaluationPeriodData, version: Partial<EvaluationVersion>): EvaluationPeriodData {
  const applied = applyVersion(current, version);
  const token = rulesChecksum(version);
  const versionId = version.id || applied.versionId;
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
  const [scopeId, setScopeId] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditorState | null>(null);
  const [proof, setProof] = useState<ProofState | null>(null);
  const [page, setPage] = useState(0);
  const [notice, setNotice] = useState<{ key: string; text: string } | null>(null);
  const [actionError, setActionError] = useState<{ key: string; text: string } | null>(null);
  const [rollbackConfirm, setRollbackConfirm] = useState<{ key: string; revisionId: string } | null>(null);
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
  const resolvedScopeId = scopeId ?? scopes.find((item) => item.readiness === 'supported')?.id ?? scopes[0]?.id ?? '';
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
      setActionError({ key: selectionKey(vars), text: errorText(caught) });
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

  const busy = save.isPending || openDraft.isPending || revise.isPending || impact.isPending || approve.isPending || apply.isPending || rollback.isPending || applyJobs.pending;
  const period = periodQuery.data;
  const serverLines = period?.lines ?? [];
  const editorActive = editor?.key === currentKey ? editor : null;
  const lines = editorActive?.lines ?? serverLines;
  const referenceLines = editorActive?.baseLines ?? serverLines;
  const textDrafts = editorActive?.text ?? {};
  const frozenLines = editorActive ? linesFromFrozenBase(editorActive) : null;
  const draftCommit = frozenLines ? commitLineInputs(frozenLines, textDrafts) : null;
  const inputBlocked = Boolean(draftCommit && !draftCommit.ok);
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
  const monthApproved = monthHasApprovedVersion(period);
  const actionsReady = Boolean(period) && !periodLoading && !blocked;
  const comparisons = visibleProof?.comparisons ?? [];
  const comparisonPage = pageSlice(comparisons, page);
  const pendingRollback = rollbackConfirm?.key === currentKey ? period?.revisions.find((item) => item.id === rollbackConfirm.revisionId && item.canRollback) : undefined;

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
    setPage(0);
    setBackgroundNote(leavingOpenJob ? BACKGROUND_CONTINUES_NOTE : null);
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
    if (!period?.versionId || period.status !== 'draft' || unsupported || inputBlocked || checksumMissing || versionDrift || conflictText) return;
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

  return (
    <div className="min-w-0 space-y-4" aria-busy={periodLoading || busy}>
      <header>
        <h2 className="text-xl font-black text-[var(--text-primary)]">Evaluation settings</h2>
        <p className="mt-1 text-xs text-[var(--text-muted)]">Revise an approved month, review the stored impact, then approve and apply as separate steps. July and August stay independent. Supported scopes only.</p>
      </header>
      {error && <div role="alert" className="flex items-start gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-xs font-semibold text-red-600"><AlertCircle size={16} />{error}</div>}
      {message && <p className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-xs font-semibold text-emerald-700" role="status">{message}</p>}
      {applyJobs.mode === 'pending' && <p role="status" className="text-xs text-[var(--text-muted)]">{CHECKING_APPLY_NOTE}</p>}
      {applyJobs.mode === 'unavailable' && <div role="alert" className="space-y-2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-xs font-semibold text-red-600">
        <p>{applyJobs.unavailableMessage}</p>
        <button type="button" onClick={applyJobs.retryAvailability} className="rounded-xl border border-red-500/30 px-3 py-2 text-xs font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary,#00A3E0)]">Retry availability check</button>
      </div>}
      {backgroundNote && <p role="status" className="break-words rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-4 py-3 text-xs text-[var(--text-secondary)]">{backgroundNote}</p>}
      {applyJobs.problem && <div role="alert" className="space-y-2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-xs font-semibold text-red-600">
        <p>{applyJobs.problem}</p>
        <button type="button" onClick={applyJobs.refreshJob} className="rounded-xl border border-red-500/30 px-3 py-2 text-xs font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary,#00A3E0)]">Refresh background apply</button>
      </div>}
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
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="min-w-0 text-xs font-bold text-[var(--text-secondary)]">Evaluation scope
          <select aria-label="Evaluation scope" value={resolvedScopeId} onChange={(event) => changeSelection({ scopeId: event.target.value })} className="mt-1 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)]">
            {scopes.map((item) => {
              const readiness = item.id === resolvedScopeId && !periodLoading && !periodQuery.isError
                ? readinessSource?.readiness ?? item.readiness
                : item.readiness;
              return <option key={item.id} value={item.id}>{item.display_name} · {item.performance_level}{item.position_name ? ` · ${item.position_name}` : ''}{readiness === 'supported' ? '' : readiness === 'unlinked_baseline' ? ' · unlinked' : ' · blocked'}</option>;
            })}
          </select>
        </label>
        <label className="min-w-0 text-xs font-bold text-[var(--text-secondary)]">Reporting month
          <select aria-label="Reporting month" value={month} onChange={(event) => changeSelection({ month: Number(event.target.value) })} className="mt-1 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-sm">
            {MONTHS.map((name, index) => <option key={name} value={index + 1}>{name}</option>)}
          </select>
        </label>
        <label className="min-w-0 text-xs font-bold text-[var(--text-secondary)]">Reporting year
          <input aria-label="Reporting year" type="number" min={2000} max={2100} value={year} onChange={(event) => changeSelection({ year: Number(event.target.value) })} className="mt-1 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-sm" />
        </label>
        <div className="min-w-0 self-end text-xs text-[var(--text-muted)]">{scopes.length === 0 && catalogQuery.isPending ? 'Loading scopes…' : scopeLabel}</div>
      </div>
      {blocked && <div role="status" className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-800">{readinessSource?.block_reason} {readinessSource?.history_note}</div>}
      {actionsReady && <div className="flex flex-wrap gap-2">
        {!monthApproved && <button type="button" onClick={() => runOpen(false)} disabled={controlsLocked} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:cursor-not-allowed disabled:opacity-50">New draft</button>}
        {!monthApproved && <button type="button" onClick={() => runOpen(true)} disabled={controlsLocked} className="inline-flex items-center gap-1 rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:cursor-not-allowed disabled:opacity-50"><Copy size={14} />Copy previous month</button>}
        {approved && <button type="button" onClick={runRevise} disabled={controlsLocked || !period?.versionId} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:cursor-not-allowed disabled:opacity-50">Revise this month</button>}
        {!approved && <button type="button" onClick={runSave} disabled={controlsLocked || !period?.versionId || period?.status !== 'draft' || unsupported || inputBlocked || checksumMissing || versionDrift || Boolean(conflictText)} className="inline-flex items-center gap-1 rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:cursor-not-allowed disabled:opacity-50"><Save size={14} />Save draft</button>}
        {!approved && <button type="button" onClick={runImpact} disabled={controlsLocked || !period?.versionId || period?.status !== 'draft' || dirty || unsupported} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:cursor-not-allowed disabled:opacity-50">Impact preview</button>}
        {!approved && <button type="button" onClick={runApprove} disabled={controlsLocked || !period?.versionId || dirty || period?.status !== 'draft' || !approvalReady} className="inline-flex items-center gap-1 rounded-xl bg-blue-600 px-3 py-2 text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"><Check size={14} />Approve</button>}
        {(applyJobs.mode === 'sync' || applyJobs.mode === 'async') && <button type="button" onClick={runApply} disabled={controlsLocked || period?.status !== 'approved' || dirty || applyJobs.blockEnqueue} className="rounded-xl bg-slate-900 px-3 py-2 text-xs font-bold text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary,#00A3E0)] disabled:cursor-not-allowed disabled:opacity-50">Apply</button>}
      </div>}
      {!blocked && approved && <p role="status" className="text-xs text-[var(--text-secondary)]">{READ_ONLY_APPROVED_NOTE}</p>}
      {!blocked && checksumMissing && <p role="status" className="text-xs font-semibold text-amber-800">{MISSING_CHECKSUM_MESSAGE}</p>}
      {!blocked && conflictText && <p role="status" className="text-xs font-semibold text-[var(--text-secondary)]">{conflictText}</p>}
      {!blocked && conflictText && <div className="flex flex-wrap gap-2">
        <button type="button" onClick={reloadDraft} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold">Reload draft</button>
        <button type="button" onClick={discardDraft} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold">Discard edits</button>
      </div>}
      {!blocked && dirty && <p role="status" className="text-xs font-semibold text-[var(--text-secondary)]">{UNSAVED_PREVIEW_NOTE}</p>}
      {!blocked && unsupported && <p role="status" className="text-xs font-semibold text-amber-800">{UNSUPPORTED_FORMULA_NOTE}</p>}
      {!!period?.sourceVersionId && <p className="text-xs [overflow-wrap:anywhere] text-[var(--text-secondary)]">Source version {period.sourceVersionId}{period.sourceChecksum ? ` · source checksum ${period.sourceChecksum}` : ''}. The source version remains in this month's history.</p>}
      {!!period?.notes && <p className="text-xs text-[var(--text-muted)]">{period.notes}</p>}
      {visibleProof && <section className="min-w-0 space-y-3" aria-label="Impact proof">
        <p className="text-xs text-[var(--text-secondary)]">{formatImpactSummary(visibleProof)}</p>
        {visibleProof.writes === 0 && <p className="text-xs text-[var(--text-muted)]">Impact preview wrote no scores.</p>}
        {visibleProof.rulesChecksum && <p className="text-xs [overflow-wrap:anywhere] text-[var(--text-muted)]">Rules checksum {visibleProof.rulesChecksum}.</p>}
        {visibleProof.conflicts.length > 0 && <div className="space-y-2">
          <p className="text-xs text-[var(--text-secondary)]">{FIXED_MISMATCH_NOTE}</p>
          <p className="text-xs text-[var(--text-muted)]">Mismatch numbers use the explicit unit on that KPI's rule. A missing unit stays on the stored scale.</p>
          <div className="min-w-0 overflow-x-auto">
            <table className="w-full min-w-[36rem] text-left text-xs">
              <caption className="mb-2 text-left text-xs font-bold text-[var(--text-secondary)]">Fixed target mismatches</caption>
              <thead>
                <tr>
                  <th scope="col" className="px-2 py-1">Record</th>
                  <th scope="col" className="px-2 py-1">KPI</th>
                  <th scope="col" className="px-2 py-1">Workbook target</th>
                  <th scope="col" className="px-2 py-1">Approved fixed target</th>
                </tr>
              </thead>
              <tbody>
                {visibleProof.conflicts.map((conflict) => {
                  const rule = lines.find((item) => item.kpi_key === conflict.kpiKey);
                  return (
                    <tr key={`${conflict.recordId || 'record'}-${conflict.kpiKey}`}>
                      <td className="px-2 py-1">{conflict.recordId || '—'}</td>
                      <td className="px-2 py-1">{conflict.kpiKey}</td>
                      <td className="px-2 py-1">{formatIdentifiedTarget(conflict.workbookTarget, rule?.unit)}</td>
                      <td className="px-2 py-1">{formatIdentifiedTarget(conflict.approvedTarget, rule?.unit)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>}
        {comparisons.length > 0 && <div className="space-y-2">
          <div className="min-w-0 overflow-x-auto">
            <table className="w-full min-w-[42rem] text-left text-xs">
              <caption className="mb-2 text-left text-xs font-bold text-[var(--text-secondary)]">Before and after scores</caption>
              <thead>
                <tr>
                  <th scope="col" className="px-2 py-1">Employee</th>
                  <th scope="col" className="px-2 py-1">Before score</th>
                  <th scope="col" className="px-2 py-1">After score</th>
                  <th scope="col" className="px-2 py-1">Before grade</th>
                  <th scope="col" className="px-2 py-1">After grade</th>
                </tr>
              </thead>
              <tbody>
                {comparisonPage.rows.map((row, index) => <tr key={row.recordId || `${row.employeeCode || 'employee'}-${index}`}>
                  <th scope="row" className="px-2 py-1 font-semibold">{row.employeeCode || row.employeeId || '—'}
                    {row.kpis.map((kpi) => <span key={kpi.kpiKey} className="mt-1 block font-normal text-[var(--text-muted)]">{formatKpiLine(kpi)}</span>)}
                  </th>
                  <td className="px-2 py-1">{displayNumber(row.beforeScore)}</td>
                  <td className="px-2 py-1">{displayNumber(row.afterScore)}</td>
                  <td className="px-2 py-1">{row.beforeGrade || '—'}</td>
                  <td className="px-2 py-1">{row.afterGrade || '—'}</td>
                </tr>)}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-[var(--text-muted)]">Page {comparisonPage.page + 1} of {comparisonPage.pages}</p>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => setPage(comparisonPage.page - 1)} disabled={comparisonPage.page === 0} className="rounded-lg border border-[var(--border-light)] px-2 py-1 text-xs font-bold disabled:opacity-50">Previous impact page</button>
            <button type="button" onClick={() => setPage(comparisonPage.page + 1)} disabled={comparisonPage.page >= comparisonPage.pages - 1} className="rounded-lg border border-[var(--border-light)] px-2 py-1 text-xs font-bold disabled:opacity-50">Next impact page</button>
          </div>
        </div>}
      </section>}
      <div className="min-w-0 space-y-3">
        {periodLoading && <p className="text-xs text-[var(--text-muted)]">Loading this month…</p>}
        {!periodLoading && !blocked && lines.map((line) => {
          const supported = lineFormulaSupported(line);
          const locked = busy || approved || !supported;
          const savedLine = referenceLines.find((item) => item.kpi_key === line.kpi_key) ?? line;
          const entry = textDrafts[line.kpi_key];
          const targetValue = entry?.targetText !== undefined ? entry.targetText : storedTargetToInput(savedLine.target, savedLine.unit);
          const weightValue = entry?.weightText !== undefined ? entry.weightText : storedWeightToInput(savedLine.weight);
          const targetProblem = draftProblems.find((item) => item.kpiKey === line.kpi_key && item.field === 'target');
          const weightProblem = draftProblems.find((item) => item.kpiKey === line.kpi_key && item.field === 'weight');
          const unitSuffix = isExplicitPercentUnit(savedLine.unit)
            ? '%'
            : typeof savedLine.unit === 'string' && savedLine.unit.trim()
              ? savedLine.unit.trim()
              : 'as stored';
          const fieldKey = line.kpi_key.replace(/[^A-Za-z0-9_-]/g, '-');
          return (
            <fieldset key={line.kpi_key} disabled={locked} className="min-w-0 rounded-2xl border border-[var(--border-light)] p-3 disabled:opacity-60">
              <legend className="px-1 text-xs font-black text-[var(--text-primary)]">{line.label || line.kpi_key}</legend>
              {!supported && <p role="status" className="mb-2 text-xs text-amber-800">{UNSUPPORTED_FORMULA_NOTE}</p>}
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <label className="text-[10px] font-bold text-[var(--text-muted)]">
                  <span className="uppercase tracking-wide">{targetFieldLabel(savedLine.unit)}</span>
                  <span className="mt-1 flex items-center gap-2">
                    <input aria-label={`${line.kpi_key} target`} aria-describedby={`${fieldKey}-target-help`} aria-invalid={targetProblem ? true : undefined} type="text" inputMode="decimal" autoComplete="off" spellCheck={false} value={targetValue} onChange={(event) => editText(line.kpi_key, 'targetText', event.target.value)} className="w-full rounded-lg border border-[var(--border-light)] bg-transparent px-2 py-2 text-sm normal-case" />
                    <span className="shrink-0 text-xs font-bold normal-case">{unitSuffix}</span>
                  </span>
                  <span id={`${fieldKey}-target-help`} className="mt-1 block font-normal normal-case tracking-normal">{targetFieldHelp(savedLine.unit)} Saved target: {savedTargetSummary(savedLine)}.</span>
                  {targetProblem && <span role="status" className="mt-1 block font-semibold normal-case tracking-normal text-amber-800">{targetProblem.message}</span>}
                </label>
                <label className="text-[10px] font-bold text-[var(--text-muted)]">
                  <span className="uppercase tracking-wide">{WEIGHT_FIELD_LABEL}</span>
                  <span className="mt-1 flex items-center gap-2">
                    <input aria-label={`${line.kpi_key} weight`} aria-describedby={`${fieldKey}-weight-help`} aria-invalid={weightProblem ? true : undefined} type="text" inputMode="decimal" autoComplete="off" spellCheck={false} value={weightValue} onChange={(event) => editText(line.kpi_key, 'weightText', event.target.value)} className="w-full rounded-lg border border-[var(--border-light)] bg-transparent px-2 py-2 text-sm normal-case" />
                    <span className="shrink-0 text-xs font-bold normal-case">%</span>
                  </span>
                  <span id={`${fieldKey}-weight-help`} className="mt-1 block font-normal normal-case tracking-normal">{WEIGHT_FIELD_HELP} Saved weight: {savedWeightSummary(savedLine.weight)}.</span>
                  {weightProblem && <span role="status" className="mt-1 block font-semibold normal-case tracking-normal text-amber-800">{weightProblem.message}</span>}
                </label>
                <label className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-muted)]">Direction
                  {supported ? (
                    <select aria-label={`${line.kpi_key} direction`} value={line.direction} onChange={(event) => updateLine(line.kpi_key, { direction: event.target.value })} className="mt-1 w-full rounded-lg border border-[var(--border-light)] bg-transparent px-2 py-2 text-sm">
                      <option value="higher_better">Higher is better</option>
                      <option value="lower_better">Lower is better</option>
                    </select>
                  ) : <input aria-label={`${line.kpi_key} direction`} value={line.direction} readOnly className="mt-1 w-full rounded-lg border border-[var(--border-light)] bg-transparent px-2 py-2 text-sm" />}
                </label>
                <label className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-muted)]">Source
                  {supported ? (
                    <select aria-label={`${line.kpi_key} source`} value={line.target_mode} onChange={(event) => updateLine(line.kpi_key, { target_mode: event.target.value })} className="mt-1 w-full rounded-lg border border-[var(--border-light)] bg-transparent px-2 py-2 text-sm">
                      <option value="workbook">Workbook</option>
                      <option value="fixed">Fixed</option>
                    </select>
                  ) : <input aria-label={`${line.kpi_key} source`} value={line.target_mode} readOnly className="mt-1 w-full rounded-lg border border-[var(--border-light)] bg-transparent px-2 py-2 text-sm" />}
                </label>
              </div>
            </fieldset>
          );
        })}
      </div>
      {pendingRollback && <div role="group" aria-label="Rollback confirmation" className="space-y-2 rounded-xl border border-[var(--border-light)] p-3">
        <p className="text-xs text-[var(--text-secondary)]">{ROLLBACK_CONFIRM_NOTE}</p>
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={() => runRollback(pendingRollback)} disabled={busy} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:opacity-50">Restore saved values</button>
          <button type="button" onClick={() => setRollbackConfirm(null)} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold">Keep current records</button>
        </div>
      </div>}
      <section className="min-w-0">
        <h3 className="mb-2 flex items-center gap-2 text-xs font-black uppercase tracking-wide text-[var(--text-muted)]"><History size={14} />History</h3>
        <ul className="space-y-2 text-xs [overflow-wrap:anywhere] text-[var(--text-secondary)]">
          {periodLoading && <li>Loading this month…</li>}
          {!periodLoading && (period?.history ?? []).map((item) => <li key={item.id}>{versionLabel(item, monthName)}</li>)}
          {!periodLoading && (period?.revisions ?? []).map((item) => <li key={item.id} className="flex flex-wrap items-center gap-2">
            <span>{revisionLabel(item)}</span>
            {item.canRollback && <button type="button" onClick={() => setRollbackConfirm({ key: currentKey, revisionId: item.id })} disabled={busy} className="rounded-lg border border-[var(--border-light)] px-2 py-1 text-xs font-bold disabled:opacity-50">Rollback</button>}
          </li>)}
          {!periodLoading && !(period?.history ?? []).length && !(period?.revisions ?? []).length && <li>No saved versions for this month.</li>}
        </ul>
      </section>
    </div>
  );
}
