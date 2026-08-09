import { useCallback, useEffect, useMemo, useState } from 'react';
import { AlertCircle, Search, SlidersHorizontal, Target } from 'lucide-react';
import { API_BASE } from '../../config';
import { useUserRole } from '../../context/RoleContext';
import type { KPITargetItem, KPIWeightItem } from './types';
import { mergeKPIConfig } from './settingsUtils';

export function KPIConfigPanel() {
  const { fetchWithRole } = useUserRole();
  const [weights, setWeights] = useState<KPIWeightItem[]>([]);
  const [targets, setTargets] = useState<KPITargetItem[]>([]);
  const [selectedTeam, setSelectedTeam] = useState('');
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [weightsResponse, targetsResponse] = await Promise.all([
        fetchWithRole(`${API_BASE}/api/settings/weights`),
        fetchWithRole(`${API_BASE}/api/settings/targets`),
      ]);
      if (!weightsResponse.ok || !targetsResponse.ok) throw new Error('Failed to load KPI configuration');
      const [weightResult, targetResult] = await Promise.all([weightsResponse.json(), targetsResponse.json()]);
      setWeights(Array.isArray(weightResult?.data) ? weightResult.data : []);
      setTargets(Array.isArray(targetResult?.data) ? targetResult.data : []);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Failed to load KPI configuration');
    } finally {
      setLoading(false);
    }
  }, [fetchWithRole]);

  useEffect(() => { void Promise.resolve().then(load); }, [load]);

  const configs = useMemo(() => mergeKPIConfig(weights, targets), [weights, targets]);
  const filtered = useMemo(() => configs.filter((item) => item.team.toLowerCase().includes(search.trim().toLowerCase())), [configs, search]);
  const active = configs.find((item) => item.team === selectedTeam) || filtered[0] || configs[0];

  const rows = useMemo(() => {
    if (!active) return [];
    const scopes = active.scopes.length
      ? active.scopes
      : [{ position: null, weights: active.weights, targets: active.targets }];
    return scopes.flatMap((scope) => (
      [...new Set([...Object.keys(scope.weights), ...Object.keys(scope.targets)])]
        .sort()
        .map((kpi) => ({ position: scope.position, kpi, weight: scope.weights[kpi], target: scope.targets[kpi] }))
    ));
  }, [active]);

  return (
    <div className="space-y-6">
      <header><h2 className="text-xl font-black text-[var(--text-primary)]">KPI Configuration</h2><p className="mt-1 text-xs text-[var(--text-muted)]">Select a team to inspect its weights and targets without scanning every configuration.</p></header>
      {error && <div role="alert" className="flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-xs font-semibold text-red-600"><AlertCircle size={16} />{error}</div>}
      <div className="glass-panel grid min-h-[520px] overflow-hidden rounded-3xl border border-[var(--border-light)] shadow-sm lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="border-b border-[var(--border-light)] bg-[var(--bg-sunken)] p-4 lg:border-b-0 lg:border-r">
          <label className="flex items-center gap-2 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2"><Search size={14} className="text-[var(--text-muted)]" /><input aria-label="Search teams" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search teams" className="min-w-0 flex-1 bg-transparent text-xs text-[var(--text-primary)] outline-none" /></label>
          <div className="mt-3 max-h-[440px] space-y-1 overflow-auto">
            {loading && <p className="px-2 py-5 text-xs text-[var(--text-muted)]">Loading teams…</p>}
            {!loading && filtered.map((config) => <button key={config.team} type="button" onClick={() => setSelectedTeam(config.team)} className={`w-full rounded-xl px-3 py-2.5 text-left text-xs font-bold transition-colors ${active?.team === config.team ? 'bg-blue-600 text-white' : 'text-[var(--text-secondary)] hover:bg-[var(--bg-surface)]'}`}>{config.team}</button>)}
            {!loading && !filtered.length && <p className="px-2 py-5 text-xs text-[var(--text-muted)]">No teams found.</p>}
          </div>
        </aside>
        <section className="min-w-0 p-5">
          {active ? <>
            <div className="flex items-center gap-3 border-b border-[var(--border-light)] pb-4"><div className="rounded-xl bg-blue-500/10 p-2 text-blue-600"><SlidersHorizontal size={18} /></div><div><h3 className="text-sm font-black text-[var(--text-primary)]">{active.team}</h3><p className="text-[10px] text-[var(--text-muted)]">{rows.length} configured KPI{rows.length === 1 ? '' : 's'}</p></div></div>
            <div className="mt-4 overflow-hidden rounded-2xl border border-[var(--border-light)]"><table className="w-full text-left text-xs"><thead className="bg-[var(--bg-sunken)] text-[10px] uppercase tracking-wider text-[var(--text-muted)]"><tr><th className="px-4 py-3">Position</th><th className="px-4 py-3">KPI</th><th className="px-4 py-3">Weight</th><th className="px-4 py-3">Target</th></tr></thead><tbody className="divide-y divide-[var(--border-light)]">{rows.map((row) => <tr key={`${row.position || 'team'}:${row.kpi}`}><td className="px-4 py-3 text-[var(--text-muted)]">{row.position || 'All positions'}</td><td className="px-4 py-3 font-bold text-[var(--text-primary)]">{row.kpi}</td><td className="px-4 py-3 text-[var(--text-secondary)]">{row.weight == null ? '—' : `${(row.weight * 100).toFixed(0)}%`}</td><td className="px-4 py-3 text-[var(--text-secondary)]">{row.target ?? '—'}</td></tr>)}{!rows.length && <tr><td colSpan={4} className="px-4 py-10 text-center text-[var(--text-muted)]">No KPI definitions for this team.</td></tr>}</tbody></table></div>
          </> : <div className="flex h-full flex-col items-center justify-center text-center text-[var(--text-muted)]"><Target size={32} /><p className="mt-3 text-sm font-bold">No KPI configuration available</p></div>}
        </section>
      </div>
    </div>
  );
}
