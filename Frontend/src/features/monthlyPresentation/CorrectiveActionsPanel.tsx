import { useMemo, useState } from 'react';
import { AlertTriangle, ClipboardList, Filter, Gauge, Layers, MessageSquareWarning, ShieldCheck, UserCheck, Users } from 'lucide-react';
import { GRADE_PALETTE, getGradeClassOrNull, type GradeClass } from '../../constants/grades';
import {
  MASKED_DETAILS_LABEL, REGION_FUNCTIONS, REGION_LABEL, displayActionState, isHighPerformerAction,
  type DeckAction, type LockedPeriod, type RegionCode,
} from './model';
import type { SlideState, TeamReady } from './deckTypes';
import { NoDataBadge } from './SlideParts';

/**
 * Web-page section under team performance: first the action picture for the whole department (or one
 * function / team), then the action plans per team with the people they are about.
 * Grade A/B performers (or score ≥ 90) are excluded, the same rule as the slides and the PPTX.
 */
export interface CorrectiveActionsPanelProps {
  code: RegionCode;
  period: LockedPeriod;
  actions: DeckAction[];
  teams: TeamReady[];
  kpiLabels: Record<string, string>;
  mask: (name: string | null | undefined) => string;
  masked: boolean;
  state: SlideState;
}

type Scope = { kind: 'all' } | { kind: 'fn'; name: string } | { kind: 'team'; name: string };
const fold = (v: string | null | undefined) => String(v ?? '').trim().toLowerCase();
const plural = (n: number, w: string) => `${n} ${w}${n === 1 ? '' : 's'}`;
const fmtDue = (iso: string | null) => (iso ? new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString('en-GB', { day: '2-digit', month: 'short' }) : '—');
const fmtPct = (v: number | null | undefined) => (v == null || !Number.isFinite(v) ? '—' : `${v.toFixed(1)}%`);
const STATE_ORDER: Record<string, number> = { Overdue: 0, Open: 1, 'In progress': 2, Completed: 3, Cancelled: 4 };

function humanizeKpi(key: string, labels: Record<string, string>): string {
  if (labels[key]) return labels[key];
  const hit = Object.entries(labels).find(([k]) => fold(k) === fold(key));
  if (hit) return hit[1];
  return key.replace(/[_-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function rank(values: Array<string | null | undefined>, limit = 3): Array<{ label: string; count: number }> {
  const map = new Map<string, { label: string; count: number }>();
  values.forEach((v) => {
    const label = String(v ?? '').trim();
    if (!label) return;
    const key = fold(label);
    const cur = map.get(key);
    if (cur) cur.count += 1; else map.set(key, { label, count: 1 });
  });
  return [...map.values()].sort((a, b) => b.count - a.count || a.label.localeCompare(b.label)).slice(0, limit);
}

function GradePill({ grade, score }: { grade?: string | null; score?: number | null }) {
  const g = (['A', 'B', 'C', 'D', 'E'].includes(String(grade ?? '').toUpperCase()) ? String(grade).toUpperCase() : getGradeClassOrNull(score)) as GradeClass | null;
  if (!g) return <NoDataBadge label="No grade" />;
  const p = GRADE_PALETTE[g];
  return <span className="mp-badge" style={{ color: p.text, background: p.background, borderColor: p.border }}>Grade {g}{score != null ? ` · ${fmtPct(score)}` : ''}</span>;
}

function RankList({ icon, title, rows, empty }: { icon: React.ReactNode; title: string; rows: Array<{ label: string; count: number }>; empty: string }) {
  const max = rows[0]?.count ?? 1;
  return (
    <div className="mp-ca-rank">
      <div className="mp-ca-rank-head">{icon}<span>{title}</span></div>
      {rows.length ? (
        <ol>
          {rows.map((r, i) => (
            <li key={r.label}>
              <span className="mp-ca-rank-n">{i + 1}</span>
              <div className="mp-ca-rank-body">
                <div className="mp-ca-rank-line"><b title={r.label}>{r.label}</b><span className="mp-ca-count">{plural(r.count, 'action')}</span></div>
                <div className="mp-ca-track"><span style={{ width: `${Math.max(8, (r.count / max) * 100)}%` }} /></div>
              </div>
            </li>
          ))}
        </ol>
      ) : <p className="mp-muted mp-small">{empty}</p>}
    </div>
  );
}

export function CorrectiveActionsPanel({ code, period, actions, teams, kpiLabels, mask, masked, state }: CorrectiveActionsPanelProps) {
  const [scope, setScope] = useState<Scope>({ kind: 'all' });
  const region = REGION_LABEL[code];
  const fnOfTeam = useMemo(() => {
    const map = new Map<string, string>();
    REGION_FUNCTIONS[code].forEach((f) => f.teams.forEach((t) => map.set(fold(t), f.name)));
    return map;
  }, [code]);

  // Strict rule: Grade A/B performers never appear as corrective-action cases.
  const eligible = useMemo(() => actions.filter((a) => !isHighPerformerAction(a)), [actions]);
  const excluded = actions.length - eligible.length;

  const scoped = useMemo(() => eligible.filter((a) => {
    if (scope.kind === 'all') return true;
    if (scope.kind === 'team') return fold(a.team) === fold(scope.name);
    return fnOfTeam.get(fold(a.team)) === scope.name;
  }), [eligible, scope, fnOfTeam]);

  const scopeLabel = scope.kind === 'all' ? `All departments in ${region}` : scope.kind === 'fn' ? `${scope.name} department` : `${scope.name} team`;
  const people = new Set(scoped.map((a) => a.employee_id || fold(a.employee_name)).filter(Boolean));
  const teamsWith = new Set(scoped.map((a) => fold(a.team)).filter(Boolean));
  const states = scoped.map((a) => displayActionState(a, period.endDate));
  const overdue = states.filter((s) => s === 'Overdue').length;
  const inFlight = states.filter((s) => s === 'Open' || s === 'In progress').length;
  const completed = states.filter((s) => s === 'Completed').length;

  const byType = rank(scoped.map((a) => a.action_type));
  const byTeam = scope.kind === 'team'
    ? rank(scoped.map((a) => (a.employee_name ? mask(a.employee_name) : null)))
    : rank(scoped.map((a) => a.team));
  const byKpi = rank(scoped.map((a) => (a.linked_kpi_key ? humanizeKpi(a.linked_kpi_key, kpiLabels) : null)));
  const byReason = masked ? [] : rank(scoped.map((a) => a.root_cause));

  // Plans grouped by team, worst state first inside each team; teams with overdue items first.
  const groups = useMemo(() => {
    const map = new Map<string, DeckAction[]>();
    scoped.forEach((a) => {
      const key = a.team?.trim() || 'Unassigned team';
      map.set(key, [...(map.get(key) ?? []), a]);
    });
    return [...map.entries()].map(([team, rows]) => {
      const sorted = [...rows].sort((x, y) =>
        (STATE_ORDER[displayActionState(x, period.endDate)] ?? 9) - (STATE_ORDER[displayActionState(y, period.endDate)] ?? 9)
        || String(x.due_date ?? '9999').localeCompare(String(y.due_date ?? '9999')));
      const info = teams.find((t) => fold(t.team) === fold(team));
      const od = rows.filter((a) => displayActionState(a, period.endDate) === 'Overdue').length;
      return { team, rows: sorted, info, overdue: od, people: new Set(rows.map((a) => a.employee_id || fold(a.employee_name)).filter(Boolean)).size };
    }).sort((a, b) => b.overdue - a.overdue || b.rows.length - a.rows.length || a.team.localeCompare(b.team));
  }, [scoped, teams, period.endDate]);

  const scopeValue = scope.kind === 'all' ? 'all' : `${scope.kind}:${scope.name}`;
  const onScope = (v: string) => {
    if (v === 'all') setScope({ kind: 'all' });
    else if (v.startsWith('fn:')) setScope({ kind: 'fn', name: v.slice(3) });
    else setScope({ kind: 'team', name: v.slice(5) });
  };
  const teamActionCount = (team: string) => eligible.filter((a) => fold(a.team) === fold(team)).length;

  return (
    <section className="mp-panel mp-noprint" aria-labelledby="mp-ca-title" data-testid="corrective-actions-panel">
      <header className="mp-panel-head">
        <div className="mp-row">
          <span className="mp-ca-icon" aria-hidden><ShieldCheck size={18} /></span>
          <div>
            <h2 id="mp-ca-title" className="mp-panel-title">Corrective action plans</h2>
            <p className="mp-muted mp-small">{region} · {period.label} · Department overview first, then each team's plans and the people they cover</p>
          </div>
        </div>
        <label className="mp-ca-filter">
          <span className="mp-label"><Filter size={12} aria-hidden /> Department / team</span>
          <select aria-label="Filter corrective actions by department or team" value={scopeValue} onChange={(e) => onScope(e.target.value)} disabled={state.status !== 'ready'}>
            <option value="all">All departments in {region}</option>
            {REGION_FUNCTIONS[code].map((f) => (
              <optgroup key={f.name} label={f.name}>
                <option value={`fn:${f.name}`}>{f.name} · whole department</option>
                {f.teams.map((t) => <option key={t} value={`team:${t}`}>↳ {t} ({teamActionCount(t)})</option>)}
              </optgroup>
            ))}
          </select>
        </label>
      </header>

      {state.status === 'loading' ? (
        <div className="mp-ca-skeleton" role="status" aria-label="Loading corrective actions">
          <div className="mp-ca-kpis">{[0, 1, 2, 3].map((i) => <div key={i} className="mp-skel mp-skel-tile" />)}</div>
          <div className="mp-skel mp-skel-row" /><div className="mp-skel mp-skel-row" /><div className="mp-skel mp-skel-row" />
        </div>
      ) : state.status === 'error' ? (
        <div className="mp-slide-state mp-slide-error" role="alert">
          <p><b>Corrective actions could not be loaded.</b> {state.message}</p>
          {state.retry && <button type="button" className="mp-btn" onClick={state.retry}>Retry</button>}
        </div>
      ) : (
        <>
          <div className="mp-ca-kpis">
            <div className="mp-ca-kpi"><span className="mp-ca-kpi-icon is-blue"><ClipboardList size={18} aria-hidden /></span><div><div className="mp-label">Actions this month</div><div className="mp-ca-kpi-v">{scoped.length}</div><div className="mp-muted mp-small">{inFlight} in flight · {completed} completed</div></div></div>
            <div className="mp-ca-kpi"><span className="mp-ca-kpi-icon is-green"><UserCheck size={18} aria-hidden /></span><div><div className="mp-label">Employees actioned</div><div className="mp-ca-kpi-v">{people.size}</div><div className="mp-muted mp-small">Grade C–E only{excluded ? ` · ${excluded} A/B excluded` : ''}</div></div></div>
            <div className="mp-ca-kpi"><span className="mp-ca-kpi-icon is-violet"><Users size={18} aria-hidden /></span><div><div className="mp-label">Teams with actions</div><div className="mp-ca-kpi-v">{teamsWith.size}</div><div className="mp-muted mp-small">{scopeLabel}</div></div></div>
            <div className={`mp-ca-kpi ${overdue ? 'is-alert' : ''}`}><span className={`mp-ca-kpi-icon ${overdue ? 'is-red' : 'is-amber'}`}><AlertTriangle size={18} aria-hidden /></span><div><div className="mp-label">Overdue</div><div className="mp-ca-kpi-v">{overdue}</div><div className="mp-muted mp-small">Due before {fmtDue(period.endDate)} and not closed</div></div></div>
          </div>

          {scoped.length === 0 ? (
            <div className="mp-empty mp-ca-empty" role="status">
              <ClipboardList size={28} aria-hidden className="mp-muted" />
              <strong>No corrective actions for {scopeLabel.toLowerCase()} in {period.label}</strong>
              <p>No Grade C–E employee in this scope has an action recorded for the locked month.</p>
              <div className="mp-row">
                {scope.kind !== 'all' && <button type="button" className="mp-btn mp-btn-ghost" onClick={() => setScope({ kind: 'all' })}>Show all departments</button>}
                <a className="mp-btn" href="/corrective-actions">Assign corrective action</a>
              </div>
            </div>
          ) : (
            <>
              <h3 className="mp-ca-section">Decision patterns · {scopeLabel}</h3>
              <div className="mp-ca-ranks">
                <RankList icon={<ClipboardList size={14} aria-hidden />} title="Most common action types" rows={byType} empty="No action type recorded." />
                <RankList icon={<Users size={14} aria-hidden />} title={scope.kind === 'team' ? 'People with the most actions' : 'Teams with the most actions'} rows={byTeam} empty="No team recorded." />
                <RankList icon={<Gauge size={14} aria-hidden />} title="Most repeated KPIs" rows={byKpi} empty="No KPI linked to these actions." />
                <RankList icon={<MessageSquareWarning size={14} aria-hidden />} title="Most common reasons" rows={byReason} empty={masked ? MASKED_DETAILS_LABEL : 'No root cause noted.'} />
              </div>

              <h3 className="mp-ca-section"><Layers size={14} aria-hidden /> Action plans by team · who is covered</h3>
              <div className="mp-ca-groups">
                {groups.map((g) => (
                  <article key={g.team} className="mp-ca-group" aria-label={`${g.team} action plan`}>
                    <header className="mp-ca-group-head">
                      <div>
                        <div className="mp-label">{g.info?.fn || fnOfTeam.get(fold(g.team)) || 'Team'}</div>
                        <strong className="mp-ca-group-title">{g.team}</strong>
                      </div>
                      <div className="mp-row">
                        {g.info?.score != null && <span className="mp-muted mp-small">Team score <b>{fmtPct(g.info.score)}</b></span>}
                        <span className="mp-badge mp-ca-neutral">{plural(g.rows.length, 'action')}</span>
                        <span className="mp-badge mp-ca-neutral">{plural(g.people, 'person')}</span>
                        {g.overdue > 0 && <span className="mp-badge mp-act-overdue">{g.overdue} overdue</span>}
                      </div>
                    </header>
                    <div className="mp-ca-table-wrap">
                      <table className="mp-table mp-ca-table">
                        <thead><tr><th>Person</th><th>Performance</th><th>Action plan</th><th>Linked KPI</th><th>Root cause</th><th>Owner</th><th>Status</th><th>Due</th></tr></thead>
                        <tbody>
                          {g.rows.map((a) => {
                            const st = displayActionState(a, period.endDate);
                            return (
                              <tr key={a.id}>
                                <td><b>{a.employee_name ? mask(a.employee_name) : <span className="mp-muted">Team-level plan{a.plan_name && !masked ? ` · ${a.plan_name}` : ''}</span>}</b>{a.employee_id && !masked && <div className="mp-muted mp-small">ID {a.employee_id}</div>}</td>
                                <td>{a.employee_name ? <GradePill grade={a.grade} score={a.score} /> : '—'}</td>
                                <td>
                                  {a.action_type && <span className="mp-chip mp-ca-type">{a.action_type}</span>}
                                  {a.priority === 'High' && <span className="mp-chip mp-ca-high">High</span>}
                                  <div className="mp-ca-action">{masked ? <NoDataBadge label={MASKED_DETAILS_LABEL} /> : a.title}</div>
                                </td>
                                <td>{a.linked_kpi_key ? humanizeKpi(a.linked_kpi_key, kpiLabels) : '—'}</td>
                                <td className="mp-ca-cause">{masked ? <NoDataBadge label={MASKED_DETAILS_LABEL} /> : a.root_cause || <span className="mp-muted">Not noted</span>}</td>
                                <td>{a.owner ? mask(a.owner) : <span className="mp-muted">Unassigned</span>}</td>
                                <td><span className={`mp-badge mp-act-${st.replace(' ', '-').toLowerCase()}`}>{st}</span></td>
                                <td>{fmtDue(a.due_date)}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </article>
                ))}
              </div>
              <p className="mp-muted mp-small mp-ca-foot">Counts include every action status for {period.label} in {region} only. Each KPI counts once per action. Overdue is measured against the end of the locked month, not today. Grade A and Grade B performers are excluded.</p>
            </>
          )}
        </>
      )}
    </section>
  );
}
