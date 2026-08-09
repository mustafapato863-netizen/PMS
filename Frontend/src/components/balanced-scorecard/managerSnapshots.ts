import type { BscContributor, BscPerson } from '../../hooks/api/useBalancedScorecard';

export interface ManagerSnapshot {
  employeeId: string;
  employeeName: string;
  teamName?: string;
  role?: string;
  score: number | null;
  contribution: number | null;
  topKpi: string | null;
  trend: number | null;
}

export function buildSnapshots(people: BscPerson[], contributors: BscContributor[]): ManagerSnapshot[] {
  const contributorsById = new Map(contributors.map((contributor) => [contributor.employee_id, contributor]));
  const allPeople: BscPerson[] = people.length
    ? people
    : contributors.map((contributor) => ({
        employee_id: contributor.employee_id,
        employee_name: contributor.employee_name,
      }));

  return allPeople.map((person) => {
    const contributor = contributorsById.get(person.employee_id);
    const perspectives = Object.values(contributor?.perspectives ?? {});
    const measured = perspectives.filter((perspective) => perspective.score != null);
    const weight = measured.reduce((sum, perspective) => sum + (perspective.measured_weight ?? 0), 0);
    const rawScore = weight
      ? measured.reduce((sum, perspective) => sum + (perspective.score ?? 0) * (perspective.measured_weight ?? 0), 0) / weight
      : measured.length
        ? measured.reduce((sum, perspective) => sum + (perspective.score ?? 0), 0) / measured.length
        : null;
    const score = contributor?.overall_score != null
      ? Math.min(contributor.overall_score, 100.0)
      : rawScore != null
        ? Math.min(rawScore, 100.0)
        : null;
    const rawContrib = measured.length
      ? measured.reduce((sum, perspective) => sum + (perspective.weighted_contribution ?? 0), 0)
      : null;
    const contribution = rawContrib != null ? Math.min(rawContrib, 1.0) : null;
    const primary = [...measured].sort(
      (a, b) => (b.weighted_contribution ?? b.score ?? 0) - (a.weighted_contribution ?? a.score ?? 0),
    )[0];
    const trends = measured
      .map((perspective) => perspective.trend)
      .filter((trend): trend is number => typeof trend === 'number' && Number.isFinite(trend));

    return {
      employeeId: person.employee_id,
      employeeName: person.employee_name,
      teamName: person.team_name,
      role: person.role || contributor?.role || person.position || contributor?.position,
      score,
      contribution,
      topKpi: primary?.top_kpi_label ?? null,
      trend: trends.length ? trends.reduce((sum, trend) => sum + trend, 0) / trends.length : null,
    };
  });
}
