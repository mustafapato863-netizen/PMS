import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Check, Copy, History, Save } from 'lucide-react';
import { API_BASE } from '../../config';
import { useUserRole } from '../../context/RoleContext';

type Line = {
  kpi_key: string;
  label?: string;
  weight: number;
  direction: string;
  target: number | null;
  target_mode: 'workbook' | 'fixed' | string;
  unit?: string;
};

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

type Version = {
  id: string;
  status: string;
  lines: Line[];
  notes?: string | null;
  month_name?: string;
};

const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

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

export function EvaluationSettingsPanel() {
  const { role, fetchWithRole } = useUserRole();
  const isAdmin = role === 'Admin';
  const [scopes, setScopes] = useState<Scope[]>([]);
  const [scopeId, setScopeId] = useState('');
  const [year, setYear] = useState(2026);
  const [month, setMonth] = useState(7);
  const [lines, setLines] = useState<Line[]>([]);
  const [versionId, setVersionId] = useState('');
  const [status, setStatus] = useState('');
  const [notes, setNotes] = useState('');
  const [history, setHistory] = useState<Version[]>([]);
  const [preview, setPreview] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  const scope = scopes.find((item) => item.id === scopeId) || null;
  const blocked = scope != null && scope.readiness !== 'supported';

  const loadCatalog = useCallback(async () => {
    const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/catalog`);
    const data = await readJson(response);
    const next = Array.isArray(data?.scopes) ? data.scopes : [];
    setScopes(next);
    setScopeId((current) => current || next.find((item: Scope) => item.readiness === 'supported')?.id || next[0]?.id || '');
  }, [fetchWithRole]);

  const loadPeriod = useCallback(async () => {
    if (!scopeId) return;
    const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/periods?scope_id=${scopeId}&year=${year}&month=${month}`);
    const data = await readJson(response);
    const versions: Version[] = Array.isArray(data?.versions) ? data.versions : [];
    setHistory(versions);
    const draft = versions.find((item) => item.status === 'draft') || versions.find((item) => item.status === 'approved');
    setVersionId(draft?.id || '');
    setStatus(draft?.status || '');
    setLines(draft?.lines ? draft.lines.map((line) => ({ ...line })) : []);
    setNotes(draft?.notes || '');
  }, [fetchWithRole, month, scopeId, year]);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError('');
    loadCatalog()
      .catch((caught) => active && setError(caught instanceof Error ? caught.message : 'Failed to load evaluation settings'))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [loadCatalog]);

  useEffect(() => {
    if (!scopeId) return;
    setError('');
    loadPeriod().catch((caught) => setError(caught instanceof Error ? caught.message : 'Failed to load the month'));
  }, [loadPeriod, scopeId]);

  const updateLine = (key: string, patch: Partial<Line>) => {
    setLines((current) => current.map((line) => line.kpi_key === key ? { ...line, ...patch } : line));
  };

  const save = async (weightOnly = false) => {
    setError('');
    setMessage('');
    const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/drafts/${versionId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lines, weight_only: weightOnly }),
    });
    const data = await readJson(response);
    setLines(data.lines || lines);
    setMessage(weightOnly ? 'Weight change saved.' : 'Draft saved.');
  };

  const copyPrevious = async () => {
    setError('');
    const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/drafts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope_id: scopeId, year, month, copy_previous: true }),
    });
    const data = await readJson(response);
    setVersionId(data.id);
    setStatus(data.status);
    setLines(data.lines || []);
    setNotes(data.notes || '');
    setMessage(data.notes || 'Previous month copied.');
  };

  const openDraft = async () => {
    setError('');
    const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/drafts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope_id: scopeId, year, month, copy_previous: false }),
    });
    const data = await readJson(response);
    setVersionId(data.id);
    setStatus(data.status);
    setLines(data.lines || []);
    setNotes(data.notes || '');
  };

  const runPreview = async () => {
    setError('');
    const rows = lines.map((line) => ({ kpi_key: line.kpi_key, actual: line.target ?? 0, workbook_target: line.target }));
    const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/drafts/${versionId}/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rows }),
    });
    const data = await readJson(response);
    const first = data.rows?.[0];
    setPreview(first ? `${first.kpi_key} achievement ${(Number(first.achievement) * 100).toFixed(2)}%, score ${data.score}` : 'Preview has no rows.');
  };

  const approve = async () => {
    setError('');
    const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/drafts/${versionId}/approve`, { method: 'POST' });
    const data = await readJson(response);
    setStatus(data.status);
    setMessage('Approved. Existing scores were not recalculated.');
    await loadPeriod();
  };

  const apply = async () => {
    setError('');
    const response = await fetchWithRole(`${API_BASE}/api/settings/evaluation/apply`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope_id: scopeId, year, month }),
    });
    await readJson(response);
    setMessage('Apply updated this month only.');
  };

  const onAction = (action: () => Promise<void>) => {
    action().catch((caught) => setError(caught instanceof Error ? caught.message : 'Evaluation request failed'));
  };

  const scopeLabel = useMemo(() => scope ? `${scope.display_name} · ${scope.performance_level}${scope.position_name ? ` · ${scope.position_name}` : ''}` : 'No scope', [scope]);

  return (
    <div className="min-w-0 space-y-4">
      <header>
        <h2 className="text-xl font-black text-[var(--text-primary)]">Evaluation settings</h2>
        <p className="mt-1 text-xs text-[var(--text-muted)]">Draft a month, preview it, then approve and apply as separate steps. July and August stay independent.</p>
      </header>
      {error && <div role="alert" className="flex items-start gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-xs font-semibold text-red-600"><AlertCircle size={16} />{error}</div>}
      {message && <p className="rounded-xl border border-emerald-500/20 bg-emerald-500/10 px-4 py-3 text-xs font-semibold text-emerald-700" role="status">{message}</p>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="min-w-0 text-xs font-bold text-[var(--text-secondary)]">Evaluation scope
          <select aria-label="Evaluation scope" value={scopeId} onChange={(event) => setScopeId(event.target.value)} className="mt-1 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)]">
            {scopes.map((item) => <option key={item.id} value={item.id}>{item.display_name} · {item.performance_level}{item.position_name ? ` · ${item.position_name}` : ''}{item.readiness === 'supported' ? '' : item.readiness === 'unlinked_baseline' ? ' · unlinked' : ' · blocked'}</option>)}
          </select>
        </label>
        <label className="min-w-0 text-xs font-bold text-[var(--text-secondary)]">Reporting month
          <select aria-label="Reporting month" value={month} onChange={(event) => setMonth(Number(event.target.value))} className="mt-1 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-sm">
            {MONTHS.map((name, index) => <option key={name} value={index + 1}>{name}</option>)}
          </select>
        </label>
        <label className="min-w-0 text-xs font-bold text-[var(--text-secondary)]">Reporting year
          <input aria-label="Reporting year" type="number" value={year} onChange={(event) => setYear(Number(event.target.value))} className="mt-1 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-sm" />
        </label>
        <div className="min-w-0 self-end text-xs text-[var(--text-muted)]">{scopes.length === 0 && loading ? 'Loading scopes…' : scopeLabel}</div>
      </div>
      {blocked && <div role="status" className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-xs text-amber-800">{scope?.block_reason} {scope?.history_note}</div>}
      {!blocked && <div className="flex flex-wrap gap-2">
        <button type="button" onClick={() => onAction(openDraft)} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold">New draft</button>
        <button type="button" onClick={() => onAction(copyPrevious)} className="inline-flex items-center gap-1 rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold"><Copy size={14} />Copy previous month</button>
        <button type="button" onClick={() => onAction(() => save(false))} disabled={!versionId} className="inline-flex items-center gap-1 rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold"><Save size={14} />Save draft</button>
        <button type="button" onClick={() => onAction(() => save(true))} disabled={!versionId} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold">Save weights</button>
        <button type="button" onClick={() => onAction(runPreview)} disabled={!versionId} className="rounded-xl border border-[var(--border-light)] px-3 py-2 text-xs font-bold">Preview</button>
        {isAdmin && <button type="button" onClick={() => onAction(approve)} disabled={!versionId} className="inline-flex items-center gap-1 rounded-xl bg-blue-600 px-3 py-2 text-xs font-bold text-white"><Check size={14} />Approve</button>}
        {isAdmin && <button type="button" onClick={() => onAction(apply)} className="rounded-xl bg-slate-900 px-3 py-2 text-xs font-bold text-white">Apply</button>}
        {!isAdmin && <p className="self-center text-xs text-[var(--text-muted)]">Approval is limited to Admin.</p>}
      </div>}
      {preview && <p className="text-xs text-[var(--text-secondary)]">{preview}</p>}
      {!!notes && <p className="text-xs text-[var(--text-muted)]">{notes}</p>}
      <div className="min-w-0 space-y-3">
        {lines.map((line) => <fieldset key={line.kpi_key} className="min-w-0 rounded-2xl border border-[var(--border-light)] p-3">
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
          {history.map((item) => <li key={item.id}>{item.month_name || MONTHS[month - 1]} · {item.status} · {status === item.status ? 'open' : 'saved'}</li>)}
          {!history.length && <li>No saved versions for this month.</li>}
        </ul>
      </section>
    </div>
  );
}
