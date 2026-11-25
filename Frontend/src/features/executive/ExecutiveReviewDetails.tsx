import { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import type { PMSAction } from '../../types';
import { useAllTeamActions, type UnifiedTeamAction } from '../../hooks/useActionStore';
import { monthlyKpiRows, type ExecRecord } from './compose';
import { formatKpiValue, slugifyIdentifier } from '../monthlyPresentation/callCenterDeepDiveData';
import { businessTeamName, parseTeamCountry, presentationTeamName } from '../team/countryTeamIdentity';

import { actionMatchesRecord, isSavedRoleIntervention, sameReviewTeam, type ReviewUnit } from './executiveReviewModel';

export const reviewButtonClass = 'rounded-lg border border-[var(--exec-card-border)] px-3 py-2 text-sm font-semibold text-[var(--insights-accent-text)] hover:bg-[var(--exec-tile-bg)]';
const panel = 'rounded-xl border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-4 sm:p-5';
const muted = 'text-sm text-[var(--text-secondary)]';

function matchesTeamPlan(plan: UnifiedTeamAction, record: ExecRecord) {
  const country = parseTeamCountry(record.region);
  return country !== null && parseTeamCountry(plan.region) === country
    && sameReviewTeam(plan.team, record.team, country);
}

function SavedTeamDecision({ item }: { item: UnifiedTeamAction }) {
  return (
    <li className="rounded-lg border border-[var(--exec-card-border)] p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <span className="font-semibold">{item.title}</span>
        <span className={muted}>{item.status}</span>
      </div>
      {item.scope_description && <p className={muted}>{item.scope_description}</p>}
      <p className={muted}>{[item.target_kpi, item.owner, item.due_date].filter(Boolean).join(' · ')}</p>
    </li>
  );
}

export function ExecutiveFunctionReview({
  name, month, score, records, actions, units, canSeeActions, onOverview, onSelectUnit,
}: {
  name: string;
  month: string;
  score: number;
  records: ExecRecord[];
  actions: PMSAction[];
  units: ReviewUnit[];
  canSeeActions: boolean;
  onOverview: () => void;
  onSelectUnit: (unit: ReviewUnit) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const teamActions = useAllTeamActions(canSeeActions);
  const period = records[0]?.period;
  const savedPlans = canSeeActions ? (teamActions.data ?? []).filter((item) =>
    item.year === period?.year && item.month.toLowerCase() === period.month.toLowerCase(),
  ) : [];
  const parents = new Set(['rcm', 'call-center']);
  const functionSlug = slugifyIdentifier(name);
  // An overall action on a department's own parent team already has
  // function scope in the existing action store. Child plans retain their team.
  const departmentPlans = parents.has(functionSlug)
    ? savedPlans.filter((item) => item.kind === 'overall_action' && slugifyIdentifier(item.team) === functionSlug &&
        records.some((record) => parseTeamCountry(record.region) === parseTeamCountry(item.region)))
    : [];
  const departmentPlanIds = new Set(departmentPlans.map((item) => item.id));
  const teams = new Map<string, { record: ExecRecord; records: ExecRecord[]; name: string }>();
  for (const record of records) {
    const key = JSON.stringify([businessTeamName(record.team), parseTeamCountry(record.region)]);
    const entry = teams.get(key);
    if (entry) entry.records.push(record);
    else teams.set(key, { record, records: [record], name: presentationTeamName(record.team) });
  }

  const impact = (unit: ReviewUnit) => Math.max(100 - unit.score, 0) * unit.people;
  const totalImpact = units.reduce((total, unit) => total + impact(unit), 0);
  const rows = [...units].sort((a, b) => impact(b) - impact(a) || a.score - b.score || a.name.localeCompare(b.name));
  const priority = rows.filter((unit, index) => unit.score < 90 || (index < 3 && impact(unit) > 0));
  const visible = showAll ? rows : priority;

  return (
    <div className="mx-auto w-full max-w-7xl space-y-4">
      <header className={panel}>
        <nav aria-label="Analysis breadcrumb" className="mb-3 flex flex-wrap items-center gap-2">
          <button type="button" className={reviewButtonClass} onClick={onOverview}>Executive Summary</button>
          <ChevronRight size={15} aria-hidden="true" />
          <span aria-current="page">{name}</span>
        </nav>
        <h1 className="text-xl font-bold">{name}</h1>
        <p className={muted}>{month} · {score.toFixed(1)}% · {priority.length} of {units.length} teams or roles need review</p>
      </header>

      <section className={panel} aria-label="Priority teams and roles">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-bold">{showAll ? 'All teams and roles' : 'Priority teams and roles'}</h2>
          {rows.length > priority.length && <button type="button" className={reviewButtonClass} onClick={() => setShowAll(!showAll)}>
            {showAll ? 'Show priority only' : 'Show all teams and roles'}
          </button>}
        </div>
        {visible.length ? (
          <ul className="divide-y divide-[var(--exec-card-border)]">
            {visible.map((unit) => (
              <li key={unit.id} className="flex flex-wrap items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <button type="button" className="text-left font-semibold text-[var(--insights-accent-text)] hover:underline" onClick={() => onSelectUnit(unit)}>
                    {unit.name}{unit.region ? ` · ${unit.region}` : ''}
                  </button>
                  <p className={muted}>{unit.bottleneck || 'No measured KPI gap available'}</p>
                </div>
                <div className="text-right">
                  <p className="font-semibold tabular-nums">{unit.score.toFixed(1)}% · {unit.people} {unit.people === 1 ? 'person' : 'people'}</p>
                  <p className={muted}>{totalImpact ? `${((impact(unit) / totalImpact) * 100).toFixed(1)}% of gap` : '—'}</p>
                </div>
              </li>
            ))}
          </ul>
        ) : <p className={muted}>No teams or roles meet the priority criteria this month.</p>}
      </section>

      {canSeeActions && (
        <section className={panel} aria-label="Function action plan">
          <h2 className="mb-3 text-base font-bold">Function Action Plan</h2>
          {teamActions.isError ? <p role="status" className={muted}>Saved team decisions could not be loaded.</p>
            : teamActions.isPending ? <p role="status" className={muted}>Loading saved team decisions…</p>
            : departmentPlans.length ? <ul className="space-y-2">{departmentPlans.map((item) => <SavedTeamDecision key={item.id} item={item} />)}</ul>
            : <p className={muted}>No function-wide decisions saved for this month.</p>}
          <h3 className="mb-2 mt-4 text-sm font-bold">Decisions by team</h3>
          <ul className="divide-y divide-[var(--exec-card-border)]">
            {[...teams.values()].map(({ record, records: members, name: teamName }) => {
              const teamPlans = savedPlans.filter((item) => !departmentPlanIds.has(item.id) && matchesTeamPlan(item, record));
              const employeeActions = actions.filter((action) => members.some((member) => actionMatchesRecord(action, member)));
              const individualCount = employeeActions.filter((action) => !isSavedRoleIntervention(action)).length;
              const roleCount = employeeActions.length - individualCount;
              const decisions = [...teamPlans, ...employeeActions];
              const counts = new Map<string, number>();
              for (const { status = 'Open' } of decisions) counts.set(status, (counts.get(status) ?? 0) + 1);
              const country = parseTeamCountry(record.region);
              return (
                <li key={JSON.stringify([record.team, country])} className="flex flex-wrap items-center justify-between gap-2 py-3">
                  <button type="button" className="font-semibold text-[var(--insights-accent-text)] hover:underline" onClick={() => onSelectUnit({
                    id: record.team, name: teamName, score: record.score, people: members.length,
                    team: record.team, region: country ?? undefined,
                  })}>{teamName}{country ? ` · ${country}` : ''}</button>
                  <span className={muted}>
                    {teamActions.isSuccess ? `${teamPlans.length} team · ` : ''}{roleCount > 0 && `${roleCount} role · `}{individualCount} individual
                    {counts.size > 0 && ` · ${[...counts].map(([status, count]) => `${status} ${count}`).join(' · ')}`}
                  </span>
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}

export function ExecutiveEmployeeReview({
  record, team, functionName, actions, canSeeActions, onOverview, onFunction, onTeam,
}: {
  record: ExecRecord;
  team: string;
  functionName: string;
  actions: PMSAction[];
  canSeeActions: boolean;
  onOverview: () => void;
  onFunction: () => void;
  onTeam: () => void;
}) {
  const kpis = monthlyKpiRows([record], []);
  const formatMeasurement = (value: number | null, unit: string | null) =>
    formatKpiValue(value, unit === 'currency' ? (parseTeamCountry(record.region) === 'EGY' ? 'EGP' : 'AED') : unit);
  return (
    <div className="mx-auto w-full max-w-7xl space-y-4">
      <header className={panel}>
        <nav aria-label="Analysis breadcrumb" className="mb-3 flex flex-wrap items-center gap-2">
          <button type="button" className={reviewButtonClass} onClick={onOverview}>Executive Summary</button>
          <button type="button" className={reviewButtonClass} onClick={onFunction}>{functionName}</button>
          <button type="button" className={reviewButtonClass} onClick={onTeam}>{team}</button>
        </nav>
        <h1 className="text-xl font-bold">{record.name}</h1>
        <p className={muted}>{record.period.month} {record.period.year} · {record.score.toFixed(1)}%{record.position ? ` · ${record.position}` : ''}</p>
      </header>
      <section className={panel} aria-label="Employee KPIs">
        <h2 className="mb-3 font-bold">Employee KPIs</h2>
        {kpis.length ? (
          <ul className="divide-y divide-[var(--exec-card-border)]">{kpis.map((kpi) => (
            <li key={kpi.kpi_key} className="flex flex-wrap justify-between gap-2 py-2">
              <span>{kpi.kpi_label}</span>
              <span className={muted}>{formatMeasurement(kpi.actual, kpi.unit)} actual · {formatMeasurement(kpi.target, kpi.unit)} target</span>
            </li>
          ))}</ul>
        ) : <p className={muted}>No measured KPIs for this employee in the selected month.</p>}
      </section>
      {canSeeActions && (
        <section className={panel} aria-label="Individual decisions">
          <h2 className="mb-3 font-bold">Individual decisions</h2>
          {actions.length ? <ul className="space-y-3">{actions.map((action) => (
            <li key={action.id} className="rounded-lg border border-[var(--exec-card-border)] p-3">
              <p className="font-semibold">{action.action_text}</p>
              <p className={muted}>{[action.status ?? 'Open', action.owner?.name, action.due_date].filter(Boolean).join(' · ')}</p>
            </li>
          ))}</ul> : <p className={muted}>No individual decisions saved for this month.</p>}
        </section>
      )}
    </div>
  );
}

export function ExecutiveTeamDecisions({ records, overallOnly = false }: { records: ExecRecord[]; overallOnly?: boolean }) {
  const teamActions = useAllTeamActions(records.length > 0);
  const period = records[0]?.period;
  const plans = (teamActions.data ?? []).filter((item) =>
    (!overallOnly || item.kind === 'overall_action')
    && item.year === period?.year && item.month.toLowerCase() === period.month.toLowerCase()
    && records.some((record) => matchesTeamPlan(item, record)),
  );
  if (teamActions.isPending || teamActions.isError) {
    return <p role="status" className={`mx-auto max-w-7xl px-4 py-2 ${muted}`}>
      {teamActions.isError ? 'Team decisions could not be loaded.' : 'Loading team decisions…'}
    </p>;
  }
  if (overallOnly && !plans.length) return null;
  return (
    <section aria-label="Saved team decisions" className={`mx-auto mt-4 w-full max-w-7xl ${panel}`}>
      <h2 className="mb-3 font-bold">{overallOnly ? 'Overall team decisions' : 'Saved team decisions'}</h2>
      {plans.length ? <ul className="space-y-2">
        {plans.map((item) => <SavedTeamDecision key={item.id} item={item} />)}
      </ul> : <p className={muted}>No team decisions saved for this month.</p>}
    </section>
  );
}
