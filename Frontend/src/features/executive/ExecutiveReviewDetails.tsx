import { useState } from 'react';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Layers,
  UserRound,
  Users,
} from 'lucide-react';
import type { PMSAction } from '../../types';
import { useAllTeamActions, type UnifiedTeamAction } from '../../hooks/useActionStore';
import { monthlyKpiRows, type ExecRecord } from './compose';
import { formatKpiValue, slugifyIdentifier } from '../monthlyPresentation/callCenterDeepDiveData';
import { businessTeamName, parseTeamCountry, presentationTeamName } from '../team/countryTeamIdentity';
import { EXECUTIVE_FUNCTIONS } from './functions';
import type { ExecutiveFunction } from './types';
import {
  Chip,
  DirectionTag,
  ExecCard,
  ExecCardHeader,
  GradePill,
  ScoreBar,
  ScoreText,
  SoftEmpty,
  StatusPill,
} from '../../components/executive/v1/ExecPrimitives';
import { FunctionIcon } from '../../components/executive/v1/FunctionCards';
import { getGradeTone } from '../../constants/grades';
import { actionMatchesRecord, isSavedRoleIntervention, sameReviewTeam, type ReviewUnit } from './executiveReviewModel';

export const reviewButtonClass =
  'inline-flex shrink-0 items-center gap-1.5 rounded-[10px] border border-[var(--insights-accent-border)] bg-[var(--pms-grad-panel-info)] px-3 py-1.5 text-xs font-semibold text-[var(--insights-accent-text)] shadow-2xs transition-all hover:brightness-95 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent-ring)]';

const breadcrumbLinkClass =
  'inline-flex items-center gap-1.5 rounded-[8px] px-2.5 py-1 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--exec-chip-bg)] hover:text-[var(--insights-accent-text)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--insights-accent-ring)]';

const breadcrumbCurrentClass =
  'inline-flex items-center rounded-[8px] border border-[var(--insights-accent-border)] bg-[var(--pms-grad-panel-info)] px-2.5 py-1 text-xs font-bold text-[var(--insights-accent-text)]';

const muted = 'text-xs text-[var(--text-muted)]';
const secondaryText = 'text-sm text-[var(--text-secondary)]';

function isExecutiveFunctionName(name: string): name is ExecutiveFunction {
  return EXECUTIVE_FUNCTIONS.some((fn) => fn === name);
}

function decisionStatusTone(status?: string | null): 'success' | 'info' | 'warning' | 'danger' | 'neutral' {
  const normalized = String(status ?? 'Open').trim().toLowerCase();
  if (normalized === 'completed' || normalized === 'closed' || normalized === 'done') return 'success';
  if (normalized === 'in progress' || normalized === 'active') return 'info';
  if (normalized === 'overdue' || normalized === 'blocked') return 'danger';
  if (normalized === 'open' || normalized === 'pending') return 'warning';
  return 'neutral';
}

function matchesTeamPlan(plan: UnifiedTeamAction, record: ExecRecord) {
  const country = parseTeamCountry(record.region);
  return country !== null && parseTeamCountry(plan.region) === country
    && sameReviewTeam(plan.team, record.team, country);
}

function SavedTeamDecision({ item }: { item: UnifiedTeamAction }) {
  const status = item.status || 'Open';
  const meta = [item.target_kpi, item.owner, item.due_date].filter(Boolean).join(' · ');
  return (
    <li className="pms-glass-stage flex flex-col gap-1.5 rounded-[12px] p-3.5">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <span className="text-sm font-semibold text-[var(--insights-heading)]">{item.title}</span>
        <StatusPill tone={decisionStatusTone(status)}>{status}</StatusPill>
      </div>
      {item.scope_description && <p className={secondaryText}>{item.scope_description}</p>}
      {meta && <p className={muted}>{meta}</p>}
    </li>
  );
}

export function ExecutiveFunctionReview({
  name,
  month,
  score,
  records,
  actions,
  units,
  canSeeActions,
  scopeChips = [],
  onOverview,
  onSelectUnit,
}: {
  name: string;
  month: string;
  score: number;
  records: ExecRecord[];
  actions: PMSAction[];
  units: ReviewUnit[];
  canSeeActions: boolean;
  scopeChips?: string[];
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
  const tone = getGradeTone(score);
  const totalPeople = units.reduce((sum, unit) => sum + unit.people, 0);

  return (
    <div className="mx-auto w-full max-w-7xl space-y-4">
      <ExecCard as="section" aria-label={`${name} overview`}>
        <nav aria-label="Analysis breadcrumb" className="flex flex-wrap items-center gap-1.5 border-b border-[var(--insights-row-border)] pb-3">
          <button type="button" className={reviewButtonClass} onClick={onOverview}>
            <ArrowLeft className="size-3.5" aria-hidden="true" />
            <span>Executive Summary</span>
          </button>
          <ChevronRight className="size-3.5 text-[var(--text-muted)]" aria-hidden="true" />
          <span aria-current="page" className={breadcrumbCurrentClass}>{name}</span>
        </nav>

        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0 space-y-2">
            <div className="flex flex-wrap items-center gap-2.5">
              {isExecutiveFunctionName(name) ? (
                <FunctionIcon fn={name} size={36} />
              ) : (
                <span
                  aria-hidden="true"
                  className="flex size-9 shrink-0 items-center justify-center rounded-[10px] border border-[var(--insights-accent-border)] bg-[var(--pms-grad-panel-info)] text-[var(--insights-accent-text)]"
                >
                  <Layers className="size-[18px]" strokeWidth={1.85} />
                </span>
              )}
              <div className="min-w-0">
                <h1 className="text-xl font-bold tracking-[-0.02em] text-[var(--insights-heading)] sm:text-2xl">
                  {name}
                </h1>
                <p className={secondaryText}>
                  {month} · {score.toFixed(1)}% · {priority.length} of {units.length}{' '}
                  {units.length === 1 ? 'team or role needs' : 'teams or roles need'} review
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              <Chip icon={Users}>{totalPeople} {totalPeople === 1 ? 'person' : 'people'}</Chip>
              <Chip>{units.length} {units.length === 1 ? 'unit' : 'units'}</Chip>
              {scopeChips.map((chip) => <Chip key={chip}>{chip}</Chip>)}
            </div>
          </div>

          <div className="pms-glass-stage flex min-w-[240px] flex-col gap-2 rounded-[14px] px-4 py-3.5">
            <div className="flex items-center justify-between gap-3">
              <ScoreText score={score} className="text-[28px] font-bold leading-none tracking-[-0.03em] tabular-nums">
                {score.toFixed(1)}%
              </ScoreText>
              <GradePill score={score} />
            </div>
            <ScoreBar score={score} color={tone.gauge} showThreshold90 />
            <span className={muted}>Target 100% · 90% review threshold</span>
          </div>
        </div>
      </ExecCard>

      <ExecCard aria-label="Priority teams and roles">
        <ExecCardHeader
          icon={showAll ? Users : AlertTriangle}
          iconBg={showAll ? 'var(--insights-accent-soft)' : 'var(--pms-grade-d-badge-bg)'}
          iconColor={showAll ? 'var(--insights-accent-text)' : 'var(--pms-grade-d-text)'}
          title={showAll ? 'All teams and roles' : 'Priority teams and roles'}
          subtitle={
            showAll
              ? 'Every measured team or role in this function, ranked by gap contribution'
              : 'Teams below target and top contributors to the function performance gap'
          }
          action={
            rows.length > priority.length ? (
              <button
                type="button"
                aria-expanded={showAll}
                className={reviewButtonClass}
                onClick={() => setShowAll(!showAll)}
              >
                {showAll ? 'Show priority only' : 'Show all teams'}
              </button>
            ) : undefined
          }
        />

        {visible.length ? (
          <ul className="flex flex-col gap-2.5">
            {visible.map((unit, index) => {
              const isLead = !showAll && index === 0 && unit.score < 90;
              const gapShare = totalImpact > 0 ? `${((impact(unit) / totalImpact) * 100).toFixed(1)}% of gap` : '—';
              return (
                <li
                  key={unit.id}
                  className={`flex flex-col gap-3 rounded-[14px] border px-4 py-3.5 transition-all hover:shadow-sm sm:flex-row sm:items-center sm:justify-between ${
                    isLead
                      ? 'border-[var(--pms-grad-panel-neg-border)]'
                      : 'border-[var(--pms-glass-stage-border)] bg-[var(--pms-glass-stage-bg)]'
                  }`}
                  style={isLead ? { background: 'var(--pms-grad-panel-neg)' } : undefined}
                >
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <button
                        type="button"
                        className="text-left text-sm font-bold text-[var(--insights-heading)] transition-colors hover:text-[var(--insights-accent-text)] hover:underline"
                        onClick={() => onSelectUnit(unit)}
                      >
                        {unit.name}{unit.region ? ` · ${unit.region}` : ''}
                      </button>
                      <GradePill score={unit.score} />
                    </div>
                    <p className="text-xs font-medium text-[var(--text-secondary)]">
                      {unit.bottleneck || 'No measured KPI gap available'}
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center justify-between gap-4 sm:justify-end">
                    <div className="text-left sm:text-right">
                      <div className="flex items-baseline gap-1.5 sm:justify-end">
                        <ScoreText score={unit.score} className="text-[15px] font-bold tabular-nums">
                          {unit.score.toFixed(1)}%
                        </ScoreText>
                        <span className={muted}>
                          · {unit.people} {unit.people === 1 ? 'person' : 'people'}
                        </span>
                      </div>
                      <p className="text-xs font-semibold tabular-nums text-[var(--text-secondary)]">{gapShare}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => onSelectUnit(unit)}
                      className="inline-flex items-center gap-1 whitespace-nowrap text-xs font-bold text-[var(--insights-accent-text)] hover:underline"
                    >
                      <span>Review</span>
                      <ArrowRight className="size-3.5" aria-hidden="true" />
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <SoftEmpty>No teams or roles meet the priority criteria this month.</SoftEmpty>
        )}
      </ExecCard>

      {canSeeActions && (
        <ExecCard aria-label="Function action plan">
          <ExecCardHeader
            icon={ClipboardCheck}
            iconBg="var(--insights-accent-soft)"
            iconColor="var(--insights-accent-text)"
            title="Function Action Plan"
            subtitle="Saved function-wide decisions and per-team decision status for the selected month"
          />

          {teamActions.isError ? (
            <p role="status" className={secondaryText}>Saved team decisions could not be loaded.</p>
          ) : teamActions.isPending ? (
            <p role="status" className={secondaryText}>Loading saved team decisions…</p>
          ) : departmentPlans.length ? (
            <ul className="space-y-2.5">
              {departmentPlans.map((item) => <SavedTeamDecision key={item.id} item={item} />)}
            </ul>
          ) : (
            <SoftEmpty>No function-wide decisions saved for this month.</SoftEmpty>
          )}

          <div className="space-y-2.5 border-t border-[var(--insights-row-border)] pt-4">
            <h3 className="text-sm font-bold text-[var(--insights-heading)]">Decisions by team</h3>
            <ul className="flex flex-col gap-2">
              {[...teams.values()].map(({ record, records: members, name: teamName }) => {
                const teamPlans = savedPlans.filter((item) => !departmentPlanIds.has(item.id) && matchesTeamPlan(item, record));
                const employeeActions = actions.filter((action) => members.some((member) => actionMatchesRecord(action, member)));
                const individualCount = employeeActions.filter((action) => !isSavedRoleIntervention(action)).length;
                const roleCount = employeeActions.length - individualCount;
                const decisions = [...teamPlans, ...employeeActions];
                const counts = new Map<string, number>();
                for (const { status = 'Open' } of decisions) counts.set(status, (counts.get(status) ?? 0) + 1);
                const country = parseTeamCountry(record.region);
                const avgScore = members.reduce((sum, item) => sum + item.score, 0) / Math.max(members.length, 1);
                const matchedUnit =
                  units.find(
                    (unit) =>
                      unit.team &&
                      sameReviewTeam(unit.team, record.team, country) &&
                      (!unit.region || !country || unit.region === country),
                  ) ??
                  (units.length === 1 && units[0].role ? units[0] : undefined);

                return (
                  <li
                    key={JSON.stringify([record.team, country])}
                    className="pms-glass-stage flex flex-wrap items-center justify-between gap-3 rounded-[12px] px-4 py-3"
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <button
                        type="button"
                        className="text-left text-sm font-bold text-[var(--insights-accent-text)] hover:underline"
                        onClick={() =>
                          onSelectUnit(
                            matchedUnit ?? {
                              id: record.team,
                              name: teamName,
                              score: avgScore,
                              people: members.length,
                              team: record.team,
                              region: country ?? undefined,
                            },
                          )
                        }
                      >
                        {teamName}{country ? ` · ${country}` : ''}
                      </button>
                      <GradePill score={avgScore} />
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs font-medium text-[var(--text-secondary)]">
                        {teamActions.isSuccess ? `${teamPlans.length} team · ` : ''}
                        {roleCount > 0 && `${roleCount} role · `}
                        {individualCount} individual
                        {counts.size > 0 && ` · ${[...counts].map(([status, count]) => `${status} ${count}`).join(' · ')}`}
                      </span>
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        </ExecCard>
      )}
    </div>
  );
}

export function ExecutiveEmployeeReview({
  record,
  team,
  functionName,
  actions,
  canSeeActions,
  onOverview,
  onFunction,
  onTeam,
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
  const country = parseTeamCountry(record.region);
  const tone = getGradeTone(record.score);
  const formatMeasurement = (value: number | null, unit: string | null) =>
    formatKpiValue(value, unit === 'currency' ? (country === 'EGY' ? 'EGP' : 'AED') : unit);

  return (
    <div className="mx-auto w-full max-w-7xl space-y-4">
      <ExecCard as="section" aria-label={`${record.name} overview`}>
        <nav aria-label="Analysis breadcrumb" className="flex flex-wrap items-center gap-1.5 border-b border-[var(--insights-row-border)] pb-3">
          <button type="button" className={reviewButtonClass} onClick={onOverview}>
            <ArrowLeft className="size-3.5" aria-hidden="true" />
            <span>Executive Summary</span>
          </button>
          <ChevronRight className="size-3.5 text-[var(--text-muted)]" aria-hidden="true" />
          <button type="button" className={breadcrumbLinkClass} onClick={onFunction}>
            {functionName}
          </button>
          <ChevronRight className="size-3.5 text-[var(--text-muted)]" aria-hidden="true" />
          <button type="button" className={breadcrumbLinkClass} onClick={onTeam}>
            {team}
          </button>
          <ChevronRight className="size-3.5 text-[var(--text-muted)]" aria-hidden="true" />
          <span aria-current="page" className={breadcrumbCurrentClass}>{record.name}</span>
        </nav>

        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0 space-y-2">
            <div className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className="flex size-10 shrink-0 items-center justify-center rounded-[12px] border border-[var(--insights-accent-border)] bg-[var(--pms-grad-panel-info)] text-[var(--insights-accent-text)]"
              >
                <UserRound className="size-5" strokeWidth={1.85} />
              </span>
              <div className="min-w-0">
                <h1 className="text-xl font-bold tracking-[-0.02em] text-[var(--insights-heading)] sm:text-2xl">
                  {record.name}
                </h1>
                <p className={secondaryText}>
                  {record.period.month} {record.period.year} · {record.score.toFixed(1)}%
                  {record.position ? ` · ${record.position}` : ''}
                </p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {country && <Chip>{country}</Chip>}
              <Chip>{team}</Chip>
              {record.level && <Chip>{record.level}</Chip>}
            </div>
          </div>

          <div className="pms-glass-stage flex min-w-[240px] flex-col gap-2 rounded-[14px] px-4 py-3.5">
            <div className="flex items-center justify-between gap-3">
              <ScoreText score={record.score} className="text-[28px] font-bold leading-none tracking-[-0.03em] tabular-nums">
                {record.score.toFixed(1)}%
              </ScoreText>
              <GradePill score={record.score} />
            </div>
            <ScoreBar score={record.score} color={tone.gauge} showThreshold90 />
          </div>
        </div>
      </ExecCard>

      <ExecCard aria-label="Employee KPIs">
        <ExecCardHeader
          icon={BarChart3}
          iconBg="var(--insights-accent-soft)"
          iconColor="var(--insights-accent-text)"
          title="Employee KPIs"
          subtitle={`Measured KPIs for ${record.period.month} ${record.period.year}`}
        />
        {kpis.length ? (
          <ul className="flex flex-col gap-2">
            {kpis.map((kpi) => (
              <li
                key={kpi.kpi_key}
                className="pms-glass-stage flex flex-wrap items-center justify-between gap-3 rounded-[12px] px-4 py-3"
              >
                <div className="flex min-w-0 flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold text-[var(--insights-heading)]">{kpi.kpi_label}</span>
                  <DirectionTag direction={kpi.kpi_direction} />
                </div>
                <div className="flex flex-wrap items-center gap-2.5">
                  <span className="text-xs font-medium tabular-nums text-[var(--text-secondary)]">
                    {formatMeasurement(kpi.actual, kpi.unit)} actual · {formatMeasurement(kpi.target, kpi.unit)} target
                  </span>
                  {kpi.achievement_percent !== null && <GradePill score={kpi.achievement_percent} />}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <SoftEmpty>No measured KPIs for this employee in the selected month.</SoftEmpty>
        )}
      </ExecCard>

      {canSeeActions && (
        <ExecCard aria-label="Individual decisions">
          <ExecCardHeader
            icon={CheckCircle2}
            iconBg="var(--exec-pos-bg)"
            iconColor="var(--exec-pos-text)"
            title="Individual decisions"
            subtitle="Saved coaching and corrective decisions for this employee in the selected month"
          />
          {actions.length ? (
            <ul className="space-y-2.5">
              {actions.map((action) => {
                const status = action.status ?? 'Open';
                const meta = [status, action.owner?.name, action.due_date].filter(Boolean).join(' · ');
                return (
                  <li key={action.id} className="pms-glass-stage flex flex-col gap-1.5 rounded-[12px] p-3.5">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <p className="text-sm font-semibold text-[var(--insights-heading)]">{action.action_text}</p>
                      <StatusPill tone={decisionStatusTone(status)}>{status}</StatusPill>
                    </div>
                    <p className={muted}>{meta}</p>
                  </li>
                );
              })}
            </ul>
          ) : (
            <SoftEmpty>No individual decisions saved for this month.</SoftEmpty>
          )}
        </ExecCard>
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
    return (
      <p role="status" className={`mx-auto max-w-7xl px-4 py-2 ${secondaryText}`}>
        {teamActions.isError ? 'Team decisions could not be loaded.' : 'Loading team decisions…'}
      </p>
    );
  }
  if (overallOnly && !plans.length) return null;
  return (
    <ExecCard aria-label="Saved team decisions" className="mx-auto mt-4 w-full max-w-7xl">
      <ExecCardHeader
        icon={ClipboardCheck}
        iconBg="var(--insights-accent-soft)"
        iconColor="var(--insights-accent-text)"
        title={overallOnly ? 'Overall team decisions' : 'Saved team decisions'}
        subtitle="Saved decisions loaded from the team action store for this scope and month"
      />
      {plans.length ? (
        <ul className="space-y-2.5">
          {plans.map((item) => <SavedTeamDecision key={item.id} item={item} />)}
        </ul>
      ) : (
        <SoftEmpty>No team decisions saved for this month.</SoftEmpty>
      )}
    </ExecCard>
  );
}
