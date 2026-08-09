export interface PerformanceSummaryFilters {
  month?: string;
  region?: string;
  branch?: string;
  team?: string | null;
}

export interface PerformanceSummary<T> {
  totalAgents: number;
  uniqueTeamCount: number;
  averagePerformanceScore: number;
  classABCount: number;
  classABPercentage: number;
  classDECount: number;
  classDEPercentage: number;
  recordsUsed: T[];
  teamsUsed: string[];
  classCounts: { A: number; B: number; C: number; D: number; E: number };
}

export function normalizeTeamName(teamName?: string): string;
export function calculatePerformanceSummary<T>(
  records?: T[],
  filters?: PerformanceSummaryFilters,
): PerformanceSummary<T>;
