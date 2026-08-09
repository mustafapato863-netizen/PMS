import { useEffect, useState } from 'react';
import { AlertTriangle, ArrowRight, CheckCircle2, ClipboardList, ExternalLink, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import type { InsightItem } from '../../features/insights/types';
import { buildTeamPath } from '../../lib/searchNavigation';
import OverlayPortal from '../common/OverlayPortal';

function metric(value: number | null, unit: string | null) {
  if (value === null || value === undefined) return 'Not available';
  if (unit === '%' && Math.abs(value) <= 1) return `${(value * 100).toFixed(1)}%`;
  if (unit === '%') return `${value.toFixed(1)}%`;
  return `${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}${unit ? ` ${unit}` : ''}`;
}

export default function InsightDetailDrawer({ insight, onClose }: { insight: InsightItem | null; onClose: () => void }) {
  const navigate = useNavigate();
  const [showPlanConfirmation, setShowPlanConfirmation] = useState(false);
  const [draftPrepared, setDraftPrepared] = useState(false);

  useEffect(() => {
    if (!insight) return;
    const onKeyDown = (event: KeyboardEvent) => event.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [insight, onClose]);

  if (!insight) return null;

  const openDashboard = () => {
    if (insight.employee_id) {
      navigate(`/employee/${insight.employee_id}`);
    } else if (insight.team) {
      const params = new URLSearchParams();
      if (insight.performance_level) params.set('performance_level', insight.performance_level);
      if (insight.position) params.set('position', insight.position);
      if (insight.kpi_key) params.set('selected_kpi', insight.kpi_key);
      navigate(`${buildTeamPath(insight.team)}${params.size ? `?${params}` : ''}`);
    }
    onClose();
  };

  return (
    <OverlayPortal>
    <div className="fixed inset-0 z-[100]" role="presentation">
      <button type="button" aria-label="Close insight details" className="absolute inset-0 bg-slate-950/35 backdrop-blur-[2px]" onClick={onClose} />
      <aside role="dialog" aria-modal="true" aria-labelledby="insight-drawer-title" className="absolute inset-y-0 right-0 flex w-full max-w-xl flex-col border-l border-[var(--border-light)] bg-[var(--bg-surface)] shadow-2xl">
        <header className="flex items-start justify-between gap-4 border-b border-[var(--border-light)] p-5 md:p-6">
          <div>
            <span className={`inline-flex rounded-full px-2.5 py-1 text-[11px] font-extrabold uppercase tracking-wide ${insight.severity === 'critical' ? 'bg-red-500/10 text-red-600' : insight.severity === 'risk' ? 'bg-amber-500/10 text-amber-700 dark:text-amber-300' : insight.severity === 'opportunity' ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' : 'bg-blue-500/10 text-blue-600'}`}>{insight.severity}</span>
            <h2 id="insight-drawer-title" className="mt-3 text-xl font-extrabold text-[var(--text-primary)]">{insight.title}</h2>
            <p className="mt-1 text-sm text-[var(--text-muted)]">{insight.scope} · {insight.trend_label}</p>
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className="grid min-h-11 min-w-11 place-items-center rounded-xl text-[var(--text-muted)] hover:bg-[var(--bg-sunken)]"><X size={20} /></button>
        </header>

        <div className="custom-scrollbar flex-1 space-y-6 overflow-y-auto p-5 md:p-6">
          <section>
            <h3 className="text-sm font-extrabold text-[var(--text-primary)]">What happened</h3>
            <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{insight.explanation}</p>
            <div className="mt-3 rounded-xl border border-blue-500/15 bg-blue-500/5 p-3 text-xs text-[var(--text-secondary)]">
              <strong>Why am I seeing this?</strong> {insight.priority_reason}
            </div>
          </section>

          <section className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {[
              ['Current', metric(insight.detail.current_value, insight.detail.unit)],
              ['Previous', metric(insight.detail.previous_value, insight.detail.unit)],
              ['Target', metric(insight.detail.target_value, insight.detail.unit)],
              ['KPI direction', insight.detail.direction?.replace('_', ' ') || 'Not available'],
              ['Overall score impact', insight.detail.impact_points === null ? 'Not available' : `${insight.detail.impact_points > 0 ? '+' : ''}${insight.detail.impact_points.toFixed(1)}%`],
              ['Status', insight.status],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-[var(--border-light)] bg-[var(--bg-sunken)]/50 p-3">
                <p className="text-[10px] font-extrabold uppercase tracking-wide text-[var(--text-faint)]">{label}</p>
                <p className="mt-1 break-words text-sm font-bold capitalize text-[var(--text-primary)]">{value}</p>
              </div>
            ))}
          </section>

          <section>
            <h3 className="text-sm font-extrabold text-[var(--text-primary)]">Supporting evidence</h3>
            <div className="mt-2 divide-y divide-[var(--border-light)] rounded-xl border border-[var(--border-light)]">
              {insight.detail.evidence.map((item) => (
                <div key={`${item.label}-${item.value}`} className="flex items-center justify-between gap-4 px-4 py-3 text-sm">
                  <span className="text-[var(--text-muted)]">{item.label}</span>
                  <strong className="text-right text-[var(--text-primary)]">{item.value}</strong>
                </div>
              ))}
            </div>
          </section>

          {(insight.detail.affected_teams.length > 0 || insight.detail.affected_positions.length > 0 || insight.detail.affected_employees.length > 0) && (
            <section>
              <h3 className="text-sm font-extrabold text-[var(--text-primary)]">Affected scope</h3>
              <div className="mt-2 flex flex-wrap gap-2">
                {[...insight.detail.affected_teams, ...insight.detail.affected_positions, ...insight.detail.affected_employees].map((value) => <span key={value} className="rounded-full bg-[var(--bg-sunken)] px-3 py-1.5 text-xs font-semibold text-[var(--text-secondary)]">{value}</span>)}
              </div>
            </section>
          )}

          {insight.detail.warnings.length > 0 && (
            <section className="rounded-xl border border-amber-500/20 bg-amber-500/10 p-4 text-sm text-amber-800 dark:text-amber-200">
              <div className="flex items-center gap-2 font-extrabold"><AlertTriangle size={17} /> Data-quality warnings</div>
              <ul className="mt-2 space-y-1 pl-5 list-disc">{insight.detail.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
            </section>
          )}

          <section>
            <h3 className="text-sm font-extrabold text-[var(--text-primary)]">Recommended focus</h3>
            <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">{insight.detail.recommended_focus}</p>
          </section>

          {showPlanConfirmation && (
            <section className="rounded-2xl border border-indigo-500/20 bg-indigo-500/5 p-4">
              <div className="flex items-center gap-2 font-extrabold text-[var(--text-primary)]"><ClipboardList size={18} className="text-indigo-600" /> Planning context</div>
              <p className="mt-2 text-xs leading-5 text-[var(--text-muted)]">This prepares context in the current session only. It does not create or save a plan.</p>
              <div className="mt-3 space-y-1 text-sm text-[var(--text-secondary)]">
                {Object.entries(insight.planning_context).filter(([, value]) => value !== null && value !== '').map(([key, value]) => (
                  <p key={key}><span className="capitalize text-[var(--text-muted)]">{key.replaceAll('_', ' ')}:</span> <strong>{value}</strong></p>
                ))}
              </div>
              {!draftPrepared ? (
                <button type="button" onClick={() => { sessionStorage.setItem('pms_planning_draft', JSON.stringify(insight.planning_context)); setDraftPrepared(true); }} className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-xl bg-indigo-600 px-4 text-sm font-bold text-white hover:bg-indigo-700"><CheckCircle2 size={16} /> Confirm and prepare draft</button>
              ) : (
                <div role="status" className="mt-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3">
                  <p className="flex items-center gap-2 text-sm font-bold text-emerald-700 dark:text-emerald-300"><CheckCircle2 size={17} /> Draft context prepared with KPI evidence and recommended action.</p>
                  <button type="button" onClick={() => { onClose(); navigate('/planning'); }} className="mt-3 inline-flex min-h-11 items-center gap-2 rounded-xl bg-indigo-600 px-4 text-sm font-bold text-white hover:bg-indigo-700">Open Planning to assign owner and due date <ArrowRight size={16} /></button>
                </div>
              )}
            </section>
          )}
        </div>

        <footer className="grid gap-2 border-t border-[var(--border-light)] p-4 sm:grid-cols-2">
          <button type="button" disabled={!insight.team && !insight.employee_id} onClick={openDashboard} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl border border-[var(--input-border)] px-4 text-sm font-bold text-[var(--text-secondary)] hover:border-blue-500/40 disabled:cursor-not-allowed disabled:opacity-50"><ExternalLink size={16} /> Open related dashboard</button>
          <button type="button" onClick={() => setShowPlanConfirmation(true)} className="inline-flex min-h-11 items-center justify-center gap-2 rounded-xl bg-blue-600 px-4 text-sm font-bold text-white hover:bg-blue-700">Create Plan <ArrowRight size={16} /></button>
        </footer>
      </aside>
    </div>
    </OverlayPortal>
  );
}
