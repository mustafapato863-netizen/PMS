import { GRADE_PALETTE, getGradeClassOrNull } from '../../../constants/grades';
import { buildInsightsWalk, dragForWalkStep, leadForWalkStep, type InsightsWalkDepth, type InsightsWalkStep } from '../../../features/insights/insightsWalk';
import type { BasisComparisonContext, InsightDriver, InsightFilters, InsightOptions, InsightRoleSummary } from '../../../features/insights/types';

type TeamRow = {
  team: string;
  current_score: number | null;
  score_change: number | null;
  main_cause?: string | null;
  gap_points?: number | null;
  gap_contribution_percent?: number | null;
  impacted_employees?: number;
  total_employees?: number;
  basis_context?: BasisComparisonContext | null;
};

function formatMovement(movement: number | null): string | null {
  if (movement === null) return null;
  const absolute = Math.abs(movement).toFixed(1);
  if (movement > 0) return `+${absolute}`;
  if (movement < 0) return `−${absolute}`;
  return '0.0';
}

function StepCard({ step, first, onOpen }: { step: InsightsWalkStep; first: boolean; onOpen: () => void }) {
  const grade = getGradeClassOrNull(step.score);
  const palette = grade ? GRADE_PALETTE[grade] : null;
  const movement = formatMovement(step.movement);
  const movementDown = (step.movement ?? 0) < 0;
  const width = step.score === null ? 0 : Math.max(0, Math.min(100, step.score));
  const gap = step.gap === null || step.gap === undefined
    ? null
    : `${step.gap > 0 ? '+' : '−'}${Math.abs(step.gap).toFixed(1)} gap`;
  return (
    <button
      type="button"
      onClick={onOpen}
      className="relative flex min-h-[118px] w-full flex-col gap-3 overflow-hidden rounded-2xl border bg-[var(--bg-raised)] p-4 pl-5 text-left shadow-[var(--insights-summary-shadow)] transition hover:-translate-y-px hover:border-[var(--insights-accent-border)]"
      style={{ borderColor: first && palette ? palette.border : 'var(--insights-card-border)' }}
    >
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-1"
        style={{ background: palette?.solid ?? 'var(--insights-card-border)' }}
      />
      <span className="flex items-start justify-between gap-3">
        <span className="min-w-0">
          {first && step.score !== null && (
            <span className="mb-1 block text-[11px] font-bold uppercase tracking-[0.12em] text-[var(--insights-negative)]">Start here</span>
          )}
          <span className="block truncate text-[15px] font-bold leading-5 text-[var(--insights-heading)]">{step.label}</span>
          {step.facts && <span className="mt-0.5 block text-xs text-[var(--text-muted)]">{step.facts}</span>}
        </span>
        <span className="flex shrink-0 flex-col items-end">
          {palette && grade && (
            <span
              className="rounded-md px-1.5 py-0.5 text-[11px] font-bold"
              style={{ background: palette.background, color: palette.text, border: `1px solid ${palette.border}` }}
            >
              {grade} · {palette.statusLabel}
            </span>
          )}
          <span className="mt-1 text-[26px] font-bold leading-none tabular-nums text-[var(--insights-heading)]">
            {step.score === null ? '—' : `${step.score.toFixed(1)}%`}
          </span>
          {step.score !== null && (
            <span className="mt-1 text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">People average</span>
          )}
        </span>
      </span>
      <span className="mt-auto flex flex-col gap-2">
        <span aria-hidden="true" className="h-1.5 overflow-hidden rounded-full bg-[var(--insights-track)]">
          <span className="block h-full rounded-full" style={{ width: `${width}%`, background: palette?.solid ?? 'var(--text-muted)' }} />
        </span>
        <span className="flex flex-wrap items-center justify-between gap-2 text-xs">
          <span className={`font-semibold tabular-nums ${movement ? (movementDown ? 'text-[var(--insights-negative)]' : 'text-[var(--insights-positive)]') : 'text-[var(--text-muted)]'}`}>
            {movement ? `${movement} vs previous` : 'No movement'}
            {gap ? ` · ${gap}` : ''}
          </span>
        </span>
        <span className="line-clamp-2 text-xs leading-5 text-[var(--text-secondary)]">
          {step.detail ?? 'No measured rows'}
        </span>
        {step.lowestNote && (
          <span className="text-xs leading-5 text-[var(--text-secondary)]">{step.lowestNote}</span>
        )}
        {step.basisNote && (
          <span className="text-xs leading-5 text-[var(--text-secondary)]">{step.basisNote}</span>
        )}
      </span>
    </button>
  );
}

export default function InsightsWalk({
  filters,
  options,
  teamSummaries,
  roleSummaries,
  drivers = [],
  score,
  onCompany,
  onFunction,
  onTeam,
  onRole,
  onFunctionCrumb,
  onTeamCrumb,
}: {
  filters: Pick<InsightFilters, 'teamFunction' | 'team' | 'position'>;
  options: Pick<InsightOptions, 'teams' | 'functions' | 'team_functions'>;
  teamSummaries: TeamRow[];
  roleSummaries: InsightRoleSummary[];
  drivers?: InsightDriver[];
  score: number | null;
  onCompany: () => void;
  onFunction: (name: string) => void;
  onTeam: (name: string) => void;
  onRole: (name: string, team: string | null) => void;
  onFunctionCrumb: () => void;
  onTeamCrumb: () => void;
}) {
  const walk = buildInsightsWalk(filters, options, teamSummaries, roleSummaries);
  const drag = dragForWalkStep(drivers, walk.steps[0]);
  const lead = walk.steps[0] ? leadForWalkStep(walk.steps[0]) : null;
  const currentRole = filters.position
    ? roleSummaries.find((role) => role.role.trim().toLowerCase() === filters.position?.trim().toLowerCase()
      && (!filters.team || role.team.trim().toLowerCase() === filters.team.trim().toLowerCase()))
    : undefined;
  const open = (step: InsightsWalkStep) => {
    if (step.kind === 'function') onFunction(step.label);
    else if (step.kind === 'team') onTeam(step.label);
    else onRole(step.label, step.team);
  };
  const crumbAction = (depth: InsightsWalkDepth, index: number) => {
    if (index === walk.crumbs.length - 1) return undefined;
    if (depth === 'company') return onCompany;
    if (depth === 'function') return onFunctionCrumb;
    if (depth === 'team') return onTeamCrumb;
    return undefined;
  };

  return (
    <nav
      aria-label="Insights walk"
      className="flex flex-col gap-4 rounded-2xl border border-[var(--insights-summary-border)] bg-[var(--insights-summary-bg)] p-4 sm:p-5"
    >
      <div className="flex flex-wrap items-center gap-2">
        <ol className="flex flex-wrap items-center gap-1.5">
          {walk.crumbs.map((crumb, index) => {
            const action = crumbAction(crumb.depth, index);
            const current = index === walk.crumbs.length - 1;
            return (
              <li key={`${crumb.depth}:${crumb.label}`} className="inline-flex items-center gap-1.5">
                {index > 0 && <span aria-hidden="true" className="text-[var(--text-muted)]">/</span>}
                {action ? (
                  <button
                    type="button"
                    onClick={action}
                    className="rounded-full border border-[var(--insights-card-border)] bg-[var(--bg-surface)] px-3 py-1 text-sm font-semibold text-[var(--text-secondary)] hover:border-[var(--insights-accent-border)] hover:text-[var(--insights-heading)]"
                  >
                    {crumb.label}
                  </button>
                ) : (
                  <span
                    aria-current={current ? 'step' : undefined}
                    className="rounded-full bg-[var(--insights-accent-soft)] px-3 py-1 text-sm font-bold text-[var(--insights-accent-text)]"
                  >
                    {crumb.label}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
        {score !== null && (
          <span className="ml-auto text-sm font-bold tabular-nums text-[var(--insights-heading)]">
            This scope {score.toFixed(1)}%
          </span>
        )}
      </div>

      {score === null && (
        <p className="text-sm font-semibold text-[var(--text-secondary)]">No measured rows for this scope.</p>
      )}
      {lead && <p className="text-sm font-semibold text-[var(--insights-heading)]">{lead}</p>}
      {drag && (
        <p className="text-sm text-[var(--text-secondary)]">
          <span className="font-semibold text-[var(--insights-negative)]">Largest drag</span>
          {' '}{drag.driver} · {drag.scope} · −{Math.abs(drag.impact_points).toFixed(1)} pts
        </p>
      )}

      {walk.steps.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {walk.steps.map((step, index) => (
            <li key={`${step.kind}:${step.id}`}>
              <StepCard step={step} first={index === 0} onOpen={() => open(step)} />
            </li>
          ))}
        </ul>
      )}
      {currentRole && walk.depth === 'role' && (
        <p className="text-sm text-[var(--text-secondary)]">
          <span className="font-semibold text-[var(--insights-heading)]">{currentRole.role}</span>
          {currentRole.current_score !== null ? ` is at ${currentRole.current_score.toFixed(1)}%` : ' has no measured score'}
          {`. ${currentRole.affected_employees} of ${currentRole.total_employees} scored below 70. The people are listed below.`}
        </p>
      )}
      {walk.steps.length === 0 && walk.depth !== 'role' && (
        <p className="text-sm text-[var(--text-muted)]">No measured rows at this step.</p>
      )}
    </nav>
  );
}
