import { useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertCircle, Check, Copy, History, Save } from 'lucide-react';
import { API_BASE } from '../../config';
import { useUserRole } from '../../context/RoleContext';
import { canAccessSettingsContent } from '../../lib/access';
import {
  MONTHS,
  SAMPLE_PREVIEW_LIMIT,
  SAMPLE_PREVIEW_UNAVAILABLE,
  UNSAVED_PREVIEW_NOTE,
  applyVersion,
  emptyPeriod,
  formatSamplePreview,
  initialReportingPeriod,
  lineSignature,
  previewSampleRows,
  toPeriodData,
  type EvaluationLine,
  type EvaluationPeriodData,
  type EvaluationVersion,
} from './evaluationSettings';

type Selection = { scopeId: string; year: number; month: number };

type Scope = {
  id: string;
  display_name: string;
  performance_level: string;
  position_name: string;
  readiness: string;
  block_reason?: string | null;
  history_note?: string;
  supported?: boolean;
};

async function readJson(response: Response) {
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body?.detail;
    const message = typeof detail === 'string' ? detail : detail?.message || body?.message || 'Evaluation request failed';
    const error = new Error(message) as Error & { conflicts?: Array<{ kpi_key: string; workbook_target: number; approved_target: number }> };
    error.conflicts = detail?.conflicts;
    throw error;
  }
  return body?.data ?? body;
}

function errorText(caught: unknown) {
  return caught instanceof Error ? caught.message : 'Evaluation request failed';
}

function periodQueryKey(scopeId: string, year: number, month: number) {
  return ['evaluation-settings', 'period', scopeId, year, month] as const;
}

function selectionKey(selection: Selection) {
  return `${selection.scopeId}|${selection.year}|${selection.month}`;
}

export function EvaluationSettingsPanel() {
  const queryClient = useQueryClient();
  const { role, fetchWithRole } = useUserRole();
  const isAdmin = canAccessSettingsContent(role);
  const [year, setYear] = useState(() => initialReportingPeriod(window.location.search).year);
  const [month, setMonth] = useState(() => initialReportingPeriod(window.location.search).month);
  const [scopeId, setScopeId] = useState<string | null>(null);
  const [draft, setDraft] = useState<{ key: string; lines: EvaluationLine[] } | null>(null);
  const [preview, setPreview] = useState<{ key: string; text: string } | null>(null);
  const [notice, setNotice] = useState<{ key: string; text: string } | null>(null);
  const [actionError, setActionError] = useState<{ key: string; text: string } | null>(null);
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

  const save = useMutation({
    retry: false,
    mutationFn: async (vars: Selection & { versionId: string; lines: EvaluationLine[]; weightOnly: boolean }) => {
      await queryClient.cancelQueries({ queryKey: periodQueryKey(vars.scopeId, vars.year, vars.month) });
      const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/drafts/${vars.versionId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lines: vars.lines, weight_only: vars.weightOnly }),
      });
      return readJson(response) as Promise<EvaluationVersion>;
    },
    onSuccess: (version, vars) => {
      const key = selectionKey(vars);
      remember(key, (current) => applyVersion(current, { ...version, lines: version.lines || vars.lines }));
      if (!isCurrent(vars)) return;
      setDraft((current) => current?.key === key ? null : current);
      setNotice({ key, text: vars.weightOnly ? 'Weight change saved.' : 'Draft saved.' });
    },
    onError: (caught, vars) => {
      if (isCurrent(vars)) setActionError({ key: selectionKey(vars), text: errorText(caught) });
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
      remember(key, (current) => applyVersion(current, version));
      if (!isCurrent(vars)) return;
      setDraft((current) => current?.key === key ? null : current);
      setPreview(null);
      setNotice({ key, text: vars.copyPrevious ? (version.notes || 'Previous month copied.') : 'Draft opened for this month.' });
    },
    onError: (caught, vars) => {
      if (isCurrent(vars)) setActionError({ key: selectionKey(vars), text: errorText(caught) });
    },
    onSettled: () => { gate.current = false; },
  });

  const previewMutation = useMutation({
    retry: false,
    mutationFn: async (vars: Selection & { versionId: string; lines: EvaluationLine[]; actuals: Record<string, number> }) => {
      const rows = previewSampleRows(vars.lines, vars.actuals);
      if (!rows.length) throw new Error(SAMPLE_PREVIEW_UNAVAILABLE);
      const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/drafts/${vars.versionId}/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ rows }),
      });
      return readJson(response) as Promise<{ score?: unknown; rows?: unknown }>;
    },
    onSuccess: (data, vars) => {
      if (!isCurrent(vars)) return;
      setPreview({ key: selectionKey(vars), text: formatSamplePreview(data) });
    },
    onError: (caught, vars) => {
      if (isCurrent(vars)) setActionError({ key: selectionKey(vars), text: errorText(caught) });
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
      remember(key, (current) => applyVersion(current, version));
      if (!isCurrent(vars)) return;
      setNotice({ key, text: 'Approved. Existing scores were not recalculated.' });
    },
    onError: (caught, vars) => {
      if (isCurrent(vars)) setActionError({ key: selectionKey(vars), text: errorText(caught) });
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
      await readJson(response);
    },
    onSuccess: (_data, vars) => {
      if (isCurrent(vars)) setNotice({ key: selectionKey(vars), text: 'Apply updated this month only.' });
    },
    onError: (caught, vars) => {
      if (isCurrent(vars)) setActionError({ key: selectionKey(vars), text: errorText(caught) });
    },
    onSettled: () => { gate.current = false; },
  });

  const busy = save.isPending || openDraft.isPending || previewMutation.isPending || approve.isPending || apply.isPending;
  const period = periodQuery.data;
  const serverLines = period?.lines ?? [];
  const lines = draft?.key === currentKey ? draft.lines : serverLines;
  const dirty = draft?.key === currentKey && lineSignature(draft.lines) !== lineSignature(serverLines);
  const storedActuals = period?.storedActuals ?? {};
  const hasSampleActuals = previewSampleRows(serverLines, storedActuals).length > 0;
  const periodLoading = Boolean(resolvedScopeId) && periodQuery.isLoading;
  const scope = scopes.find((item) => item.id === resolvedScopeId) || null;
  const blocked = scope != null && scope.readiness !== 'supported';
  const controlsLocked = busy || periodLoading || periodQuery.isError || !period;
  const previewText = preview?.key === currentKey ? preview.text : '';
  const message = notice?.key === currentKey ? notice.text : '';
  const loadError = periodQuery.error instanceof Error ? periodQuery.error.message : catalogQuery.error instanceof Error ? catalogQuery.error.message : '';
  const error = (actionError?.key === currentKey ? actionError.text : '') || loadError;

  const begin = () => {
    if (gate.current || busy) return false;
    gate.current = true;
    setActionError(null);
    return true;
  };

  const updateLine = (key: string, patch: Partial<EvaluationLine>) => {
    const next = lines.map((line) => line.kpi_key === key ? { ...line, ...patch } : line);
    setDraft({ key: currentKey, lines: next });
    setPreview(null);
    setNotice(null);
  };

  const runSave = (weightOnly: boolean) => {
    if (!period?.versionId || !begin()) return;
    save.mutate({ ...selection, versionId: period.versionId, lines, weightOnly });
  };

  const runOpen = (copyPrevious: boolean) => {
    if (!resolvedScopeId || !begin()) return;
    openDraft.mutate({ ...selection, copyPrevious });
  };

  const runPreview = () => {
    if (!period?.versionId || dirty || !hasSampleActuals || !begin()) return;
    previewMutation.mutate({ ...selection, versionId: period.versionId, lines: serverLines, actuals: storedActuals });
  };

  const runApprove = () => {
    if (!period?.versionId || dirty || period.status !== 'draft' || !begin()) return;
    approve.mutate({ ...selection, versionId: period.versionId });
  };

  const runApply = () => {
    if (!resolvedScopeId || !begin()) return;
    apply.mutate(selection);
  };

  if (!isAdmin) {
    return (
      <div className="min-w-0 space-y-4">
        <header>
          <h2 className="text-xl font-black text-[var(--text-primary)]">Evaluation settings</h2>
          <p className="mt-1 text-xs text-[var(--text-muted)]">Draft a month, preview it, then approve and apply as separate steps. July and August stay independent.</p>
        </header>
        <p role="status" className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)] px-4 py-3 text-xs text-[var(--text-secondary)]">Evaluation settings are limited to Admin.</p>
      </div>
    );
  }

  const scopeLabel = scope ? `${scope.display_name} · ${scope.performance_level}${scope.position_name ? ` · ${scope.position_name}` : ''}` : 'No scope';

  return (
    <div className="min-w-0 space-y-4" aria-busy={periodLoading || busy}>
      <header>
        <h2 className="text-xl font-black text-[var(--text-primary)]">Evaluation settings</h2>
        <p className="mt-1 text-xs text-[var(--text-muted)]">Draft a month, preview it, then approve and apply as separate steps. July and August stay independent.</p>
      </header>
      {error && <div role="alert" className="flex items-start gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-xs font-semibold text-red-600"><AlertCircle size={16} />{error}</div>}
      {message && <p className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-xs font-semibold text-emerald-700" role="status">{message}</p>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="min-w-0 text-xs font-bold text-[var(--text-secondary)]">Evaluation scope
          <select aria-label="Evaluation scope" value={resolvedScopeId} onChange={(event) => setScopeId(event.target.value)} className="mt-1 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)]">
            {scopes.map((item) => <option key={item.id} value={item.id}>{item.display_name} · {item.performance_level}{item.position_name ? ` · ${item.position_name}` : ''}{item.readiness === 'supported' ? '' : item.readiness === 'unlinked_baseline' ? ' · unlinked' : ' · blocked'}</option>)}
          </select>
        </label>
        <label className="min-w-0 text-xs font-bold text-[var(--text-secondary)]">Reporting month
          <select aria-label="Reporting month" value={month} onChange={(event) => setMonth(Number(event.target.value))} className="mt-1 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-sm">
            {MONTHS.map((name, index) => <option key={name} value={index + 1}>{name}</option>)}
          </select>
        </label>
        <label className="min-w-0 text-xs font-bold text-[var(--text-secondary)]">Reporting year
          <input aria-label="Reporting year" type="number" min={2000} max={2100} value={year} onChange={(event) => setYear(Number(event.target.value))} className="mt-1 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-sm" />
        </label>
        <div className="min-w-0 self-end text-xs text-[var(--text-muted)]">{scopes.length === 0 && catalogQuery.isPending ? 'Loading scopes…' : scopeLabel}</div>
      </div>
      {blocked && <div role="status" className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-800">{scope?.block_reason} {scope?.history_note}</div>}
      {!blocked && <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => runOpen(false)} disabled={controlsLocked} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:cursor-not-allowed disabled:opacity-50">New draft</button>
        <button type="button" onClick={() => runOpen(true)} disabled={controlsLocked} className="inline-flex items-center gap-1 rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:cursor-not-allowed disabled:opacity-50"><Copy size={14} />Copy previous month</button>
        <button type="button" onClick={() => runSave(false)} disabled={controlsLocked || !period?.versionId} className="inline-flex items-center gap-1 rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:cursor-not-allowed disabled:opacity-50"><Save size={14} />Save draft</button>
        <button type="button" onClick={() => runSave(true)} disabled={controlsLocked || !period?.versionId} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:cursor-not-allowed disabled:opacity-50">Save weights</button>
        <button type="button" onClick={runPreview} disabled={controlsLocked || !period?.versionId || dirty || !hasSampleActuals} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold disabled:cursor-not-allowed disabled:opacity-50">Preview</button>
        <button type="button" onClick={runApprove} disabled={controlsLocked || !period?.versionId || dirty || period?.status !== 'draft'} className="inline-flex items-center gap-1 rounded-xl bg-blue-600 px-3 py-2 text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-50"><Check size={14} />Approve</button>
        <button type="button" onClick={runApply} disabled={controlsLocked} className="rounded-xl bg-slate-900 px-3 py-2 text-xs font-bold text-white disabled:cursor-not-allowed disabled:opacity-50">Apply</button>
      </div>}
      {!blocked && period && <p className="text-xs text-[var(--text-muted)]">{hasSampleActuals ? SAMPLE_PREVIEW_LIMIT : SAMPLE_PREVIEW_UNAVAILABLE}</p>}
      {!blocked && dirty && <p role="status" className="text-xs font-semibold text-[var(--text-secondary)]">{UNSAVED_PREVIEW_NOTE}</p>}
      {previewText && <p className="text-xs text-[var(--text-secondary)]">{previewText}</p>}
      {!!period?.notes && <p className="text-xs text-[var(--text-muted)]">{period.notes}</p>}
      <div className="min-w-0 space-y-3">
        {periodLoading && <p className="text-xs text-[var(--text-muted)]">Loading this month…</p>}
        {!periodLoading && !blocked && lines.map((line) => <fieldset key={line.kpi_key} disabled={busy} className="min-w-0 rounded-2xl border border-[var(--border-light)] p-3 disabled:opacity-60">
          <legend className="px-1 text-xs font-black text-[var(--text-primary)]">{line.label || line.kpi_key}</legend>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <label className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-muted)]">Target
              <input aria-label={`${line.kpi_key} target`} value={line.target ?? ''} onChange={(event) => updateLine(line.kpi_key, { target: event.target.value === '' ? null : Number(event.target.value), target_mode: 'fixed' })} className="mt-1 w-full rounded-lg border border-[var(--border-light)] bg-transparent px-2 py-2 text-sm" />
            </label>
            <label className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-muted)]">Weight
              <input aria-label={`${line.kpi_key} weight`} value={line.weight} onChange={(event) => updateLine(line.kpi_key, { weight: Number(event.target.value) })} className="mt-1 w-full rounded-lg border border-[var(--border-light)] bg-transparent px-2 py-2 text-sm" />
            </label>
            <label className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-muted)]">Direction
              <select aria-label={`${line.kpi_key} direction`} value={line.direction} onChange={(event) => updateLine(line.kpi_key, { direction: event.target.value })} className="mt-1 w-full rounded-lg border border-[var(--border-light)] bg-transparent px-2 py-2 text-sm">
                <option value="higher_better">Higher is better</option>
                <option value="lower_better">Lower is better</option>
              </select>
            </label>
            <label className="text-[10px] font-bold uppercase tracking-wide text-[var(--text-muted)]">Source
              <select aria-label={`${line.kpi_key} source`} value={line.target_mode} onChange={(event) => updateLine(line.kpi_key, { target_mode: event.target.value })} className="mt-1 w-full rounded-lg border border-[var(--border-light)] bg-transparent px-2 py-2 text-sm">
                <option value="workbook">Workbook</option>
                <option value="fixed">Fixed</option>
              </select>
            </label>
          </div>
        </fieldset>)}
      </div>
      <section className="min-w-0">
        <h3 className="mb-2 flex items-center gap-2 text-xs font-black uppercase tracking-wide text-[var(--text-muted)]"><History size={14} />History</h3>
        <ul className="space-y-1 text-xs text-[var(--text-secondary)]">
          {periodLoading && <li>Loading this month…</li>}
          {!periodLoading && (period?.history ?? []).map((item) => <li key={item.id}>{item.month_name || MONTHS[month - 1]} · {item.status} · {period?.status === item.status ? 'open' : 'saved'}</li>)}
          {!periodLoading && !(period?.history ?? []).length && <li>No saved versions for this month.</li>}
        </ul>
      </section>
    </div>
  );
}
