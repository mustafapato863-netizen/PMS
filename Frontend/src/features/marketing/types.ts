import type { AgentRecord, GradeClass } from '../../types';

export type MarketingRegion = 'All' | 'EGY' | 'UAE';
export type MarketingStatus = 'All' | 'Exceeds' | 'Meets' | 'Below';

export interface MarketingKpiConfig {
  key: string;
  label: string;
  perspective: string;
  weight: number;
  direction: 'higher_better' | 'lower_better';
  unit: string;
  color: string;
  display_order: number;
}

export interface MarketingPositionConfig {
  kpis: MarketingKpiConfig[];
}

export interface MarketingTeamConfig {
  team: string;
  db_name: string;
  region: string;
  grade_thresholds: Record<'A' | 'B' | 'C' | 'D', number>;
  available_positions: string[];
  positions: Record<string, MarketingPositionConfig>;
  performance_level: 'Employee';
}

export interface MarketingPeriod {
  year: number;
  month: string;
  key: string;
  label: string;
  sortValue: number;
}

export interface MarketingFilters {
  year: number;
  month: string;
  region: MarketingRegion;
  position?: string;
}

export interface MarketingKpiAggregate extends MarketingKpiConfig {
  currentPeriodLabel: string | null;
  previousPeriodLabel: string | null;
  averageActual: number | null;
  averageTarget: number | null;
  previousActual: number | null;
  previousTarget: number | null;
  averageAchievement: number | null;
  averageContribution: number | null;
  previousAchievement: number | null;
  achievementDelta: number | null;
  affectedEmployees: number;
  averageGap: number | null;
  baselineActual: number | null;
  baselinePeriodLabel: string | null;
  previousBaselineActual: number | null;
  previousBaselinePeriodLabel: string | null;
  isNewBaseline: boolean;
}

export type PositionDataStatus = 'Active' | 'No Uploaded Data' | 'No Results for Filters';

export interface MarketingPositionSummary {
  position: string;
  employeeCount: number;
  kpiCount: number;
  averageScore: number | null;
  classABPercentage: number;
  classDECount: number;
  scoreDelta: number | null;
  weakestKpi: MarketingKpiAggregate | null;
  dataStatus: PositionDataStatus;
}

export interface MarketingEmployeeRow {
  id: string;
  name: string;
  region: string;
  score: number;
  grade: GradeClass;
  status: Exclude<MarketingStatus, 'All'>;
  scoreDelta: number | null;
  weakestKpi: MarketingKpiAggregate | null;
  record: AgentRecord;
}

export interface MarketingTrendPoint {
  period: string;
  year: number;
  month: string;
  score: number;
  employeeCount: number;
}

export interface MarketingAnalytics {
  currentRecords: AgentRecord[];
  previousRecords: AgentRecord[];
  previousPeriod: MarketingPeriod | null;
  employeeCount: number;
  positionsWithData: number;
  averageScore: number;
  belowTargetCount: number;
  classABPercentage: number;
  classDEPercentage: number;
  employeeDelta: number | null;
  positionCountDelta: number | null;
  scoreDelta: number | null;
  belowTargetDelta: number | null;
  classABDelta: number | null;
  classDEDelta: number | null;
  gradeDistribution: Record<GradeClass, number>;
  positionSummaries: MarketingPositionSummary[];
  kpiAggregates: MarketingKpiAggregate[];
  employeeRows: MarketingEmployeeRow[];
  trend: MarketingTrendPoint[];
}

export type MarketingInsightTone = 'critical' | 'warning' | 'positive' | 'neutral';

export interface MarketingInsight {
  id: string;
  tone: MarketingInsightTone;
  title: string;
  detail: string;
  position?: string;
}
