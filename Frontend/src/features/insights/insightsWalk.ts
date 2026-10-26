import { canonicalTeamName } from '../../types';
import { functionOptionsFor, teamBelongsToFunction, type TeamFunctionMap } from './filterCascade';
import type { BasisComparisonContext, InsightDriver, InsightFilters, InsightOptions, InsightRoleSummary } from './types';

export type InsightsWalkDepth = 'company' | 'function' | 'team' | 'role';

export interface InsightsWalkCrumb {
  depth: InsightsWalkDepth;
  label: string;
}

export interface InsightsWalkStep {
  kind: 'function' | 'team' | 'role';
  id: string;
  label: string;
  /** People-average score. For a function, the team that carries the gap, or the lowest team when no share was returned. */
  score: number | null;
  movement: number | null;
  detail: string | null;
  /** Team that carries the function gap, or the lowest team when no share was returned. */
  focus: string | null;
  /** That team's share of the gap. Absent when the API did not send one. */
  focusShare: number | null;
  /** Share used to rank the card. A function uses the sum of its teams. */
  contribution: number | null;
  /** People who scored below 70. */
  belowTarget: number | null;
  /** Shown when the lowest team is not the team that carries the gap. */
  lowestNote: string | null;
  /** Shown when this month's movement is not the same people. */
  basisNote: string | null;
  facts: string | null;
  gap: number | null;
  /** Set when opening a role must also select its team. */
  team: string | null;
}

export interface InsightsWalkModel {
  depth: InsightsWalkDepth;
  crumbs: InsightsWalkCrumb[];
  steps: InsightsWalkStep[];
}

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

const sameName = (left: string, right: string) =>
  canonicalTeamName(left).trim().toLowerCase() === canonicalTeamName(right).trim().toLowerCase();

/** Company, then function, then team, then role. A team can sit directly under company. */
export function insightsWalkDepth(
  filters: Pick<InsightFilters, 'teamFunction' | 'team' | 'position'>,
): InsightsWalkDepth {
  if (filters.position) return 'role';
  if (filters.team) return 'team';
  if (filters.teamFunction) return 'function';
  return 'company';
}

function byScore(left: InsightsWalkStep, right: InsightsWalkStep): number {
  if (left.score === null && right.score === null) return left.label.localeCompare(right.label);
  if (left.score === null) return 1;
  if (right.score === null) return -1;
  return left.score - right.score || left.label.localeCompare(right.label);
}

/** Gap share first. Without one, more people under 70, then the lower score. */
function byExplanation(left: InsightsWalkStep, right: InsightsWalkStep): number {
  const leftShare = left.contribution != null && left.contribution > 0 ? left.contribution : null;
  const rightShare = right.contribution != null && right.contribution > 0 ? right.contribution : null;
  if (leftShare != null || rightShare != null) {
    if (leftShare == null) return 1;
    if (rightShare == null) return -1;
    if (leftShare !== rightShare) return rightShare - leftShare;
  }
  const leftBelow = left.belowTarget ?? -1;
  const rightBelow = right.belowTarget ?? -1;
  if (leftBelow !== rightBelow) return rightBelow - leftBelow;
  return byScore(left, right);
}

function formatShare(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function containsTerm(haystack: string, needle: string): boolean {
  const source = haystack.toLowerCase();
  const target = needle.trim().toLowerCase();
  if (!target) return false;
  let from = 0;
  while (from < source.length) {
    const at = source.indexOf(target, from);
    if (at < 0) return false;
    const before = at === 0 ? '' : source[at - 1];
    const after = source[at + target.length] ?? '';
    const boundary = (char: string) => char === '' || !/[\p{L}\p{N}]/u.test(char);
    if (boundary(before) && boundary(after)) return true;
    from = at + target.length;
  }
  return false;
}

/** The one sentence for the first card. The share is the carrier's, not a function average. */
export function leadForWalkStep(step: InsightsWalkStep): string | null {
  if (step.score === null) return null;
  const score = `${step.score.toFixed(1)}%`;
  if (step.kind === 'function' && step.focus && step.focusShare != null && step.focusShare > 0) {
    return `Start with ${step.label}. ${step.focus} accounts for ${formatShare(step.focusShare)}% of the gap at ${score}.`;
  }
  if (step.contribution != null && step.contribution > 0) {
    return `Start with ${step.label} at ${score}, ${formatShare(step.contribution)}% of the gap.`;
  }
  if (step.kind === 'function' && step.focus) {
    return `Start with ${step.label}. ${step.focus} is the lowest team at ${score}.`;
  }
  return `Start with ${step.label} at ${score}.`;
}

/** Most negative driver that names this step. A drag about somewhere else is omitted. */
export function dragForWalkStep(drivers: InsightDriver[], step: InsightsWalkStep | undefined): InsightDriver | null {
  if (!step) return null;
  const needles = [step.focus, step.label].filter((value): value is string => Boolean(value?.trim()));
  const matched = drivers.filter((driver) => (
    driver.impact_points < 0
    && needles.some((needle) => containsTerm(`${driver.scope} ${driver.driver}`, needle))
  ));
  if (matched.length === 0) return null;
  return [...matched].sort((left, right) => left.impact_points - right.impact_points)[0];
}

function shareOf(row: TeamRow): number {
  return Math.max(row.gap_contribution_percent ?? 0, 0);
}

function basisNote(context?: BasisComparisonContext | null): string | null {
  if (!context) return null;
  if (context.like_for_like && context.membership !== 'changed') return null;
  return context.message?.trim() || 'Compared people changed, so this movement is not the same group.';
}

function teamsInFunction(teams: TeamRow[], teamFunction: string, teamFunctions?: TeamFunctionMap): TeamRow[] {
  return teams.filter((row) => teamBelongsToFunction(row.team, teamFunction, teamFunctions));
}

function rolesForTeams(roles: InsightRoleSummary[], teams: string[]): InsightRoleSummary[] {
  return roles.filter((role) => teams.some((team) => sameName(role.team, team)));
}

function peopleLine(affected: number, total: number): string {
  return `${affected} of ${total} scored below 70`;
}

function teamFacts(row: TeamRow): string | null {
  if (row.total_employees === undefined) return null;
  return peopleLine(row.impacted_employees ?? 0, row.total_employees);
}

function roleStep(role: InsightRoleSummary, team: string | null): InsightsWalkStep {
  return {
    kind: 'role',
    id: `${role.team}:${role.role}`,
    label: role.role,
    score: role.current_score,
    movement: role.movement,
    detail: peopleLine(role.affected_employees, role.total_employees),
    focus: null,
    focusShare: null,
    contribution: null,
    belowTarget: role.affected_employees,
    lowestNote: null,
    basisNote: null,
    facts: null,
    gap: null,
    team,
  };
}

function functionStep(name: string, rows: TeamRow[]): InsightsWalkStep {
  const measured = rows.filter((row) => row.current_score !== null);
  const lowest = [...measured].sort((left, right) => (left.current_score ?? 0) - (right.current_score ?? 0))[0];
  const carrier = [...rows]
    .filter((row) => shareOf(row) > 0)
    .sort((left, right) => shareOf(right) - shareOf(left))[0];
  const subject = carrier ?? lowest;
  const cause = subject?.main_cause?.trim();
  const count = rows.length;
  const shareSum = rows.reduce((sum, row) => sum + shareOf(row), 0);
  const carrierShare = carrier ? shareOf(carrier) : null;
  const differentLowest = Boolean(lowest && subject && !sameName(lowest.team, subject.team));
  return {
    kind: 'function',
    id: name,
    label: name,
    score: subject?.current_score ?? null,
    movement: subject?.score_change ?? null,
    detail: carrier && carrier.current_score !== null
      ? `${carrier.team} · ${carrier.current_score.toFixed(1)}% · ${formatShare(shareOf(carrier))}% of the gap`
      : lowest
        ? `Lowest team · ${lowest.team}${cause ? ` — ${cause}` : ''}`
        : null,
    focus: subject?.team ?? null,
    focusShare: carrierShare,
    contribution: shareSum > 0 ? Math.round(shareSum * 10) / 10 : null,
    belowTarget: rows.reduce((sum, row) => sum + (row.impacted_employees ?? 0), 0) || null,
    lowestNote: differentLowest && lowest?.current_score !== null
      ? `Lowest team · ${lowest.team} at ${lowest.current_score.toFixed(1)}%`
      : null,
    basisNote: basisNote(subject?.basis_context),
    facts: count === 0 ? null : `${count} ${count === 1 ? 'team' : 'teams'}`,
    gap: subject?.gap_points ?? null,
    team: null,
  };
}

/**
 * Next clicks from live workspace rows. Function names come from the scoped
 * option list. Scores come only from team and role summaries the API returned.
 */
export function buildInsightsWalk(
  filters: Pick<InsightFilters, 'teamFunction' | 'team' | 'position'>,
  options: Pick<InsightOptions, 'teams' | 'functions' | 'team_functions'>,
  teamSummaries: TeamRow[],
  roleSummaries: InsightRoleSummary[],
): InsightsWalkModel {
  const depth = insightsWalkDepth(filters);
  const crumbs: InsightsWalkCrumb[] = [{ depth: 'company', label: 'Company' }];
  if (filters.teamFunction) crumbs.push({ depth: 'function', label: filters.teamFunction });
  if (filters.team) crumbs.push({ depth: 'team', label: filters.team });
  if (filters.position) crumbs.push({ depth: 'role', label: filters.position });

  const map = options.team_functions;
  let steps: InsightsWalkStep[] = [];

  if (depth === 'company') {
    steps = functionOptionsFor(options).map((name) =>
      functionStep(name, teamsInFunction(teamSummaries, name, map)),
    );
  } else if (depth === 'function' && filters.teamFunction) {
    const teams = teamsInFunction(teamSummaries, filters.teamFunction, map);
    if (teams.length > 0) {
      steps = teams.map((row) => ({
        kind: 'team' as const,
        id: row.team,
        label: row.team,
        score: row.current_score,
        movement: row.score_change,
        detail: row.main_cause?.trim() ? row.main_cause : null,
        focus: null,
        focusShare: shareOf(row) > 0 ? shareOf(row) : null,
        contribution: shareOf(row) > 0 ? shareOf(row) : null,
        belowTarget: row.impacted_employees ?? null,
        lowestNote: null,
        basisNote: basisNote(row.basis_context),
        facts: [
          shareOf(row) > 0 ? `${formatShare(shareOf(row))}% of the gap` : null,
          teamFacts(row),
        ].filter(Boolean).join(' · ') || null,
        gap: row.gap_points ?? null,
        team: null,
      }));
    } else {
      const memberNames = (options.teams ?? []).filter((team) =>
        teamBelongsToFunction(team, filters.teamFunction as string, map),
      );
      steps = rolesForTeams(roleSummaries, memberNames).map((role) => roleStep(role, role.team));
    }
  } else if (depth === 'team' && filters.team) {
    steps = rolesForTeams(roleSummaries, [filters.team]).map((role) => roleStep(role, null));
  }

  steps.sort(byExplanation);
  return { depth, crumbs, steps };
}
