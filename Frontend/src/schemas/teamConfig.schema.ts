/**
 * Zod validation schema for team configurations.
 * Ensures all team configs loaded from backend are valid and complete.
 */

import { z } from 'zod';

export const KPIAggregationSchema = z.object({
  method: z.enum(['average', 'sum', 'ratio', 'weighted_average']),
  numerator_col: z.string().optional(),
  denominator_col: z.string().optional(),
  weight_col: z.string().optional(),
}).superRefine((aggregation, context) => {
  if (aggregation.method === 'ratio' && (!aggregation.numerator_col || !aggregation.denominator_col)) {
    context.addIssue({ code: 'custom', message: 'ratio aggregation requires numerator_col and denominator_col' });
  }
  if (aggregation.method === 'weighted_average' && !aggregation.weight_col) {
    context.addIssue({ code: 'custom', message: 'weighted_average aggregation requires weight_col' });
  }
});

const KPIUnitSchema = z.enum([
  '%', 'currency', 'number', 'min',
  'AED', 'count', 'hours', 'sec', 'visits',
]).transform((unit): '%' | 'currency' | 'number' | 'min' => {
  if (unit === 'AED') return 'currency';
  if (unit === 'count' || unit === 'hours' || unit === 'sec' || unit === 'visits') return 'number';
  return unit;
});

/**
 * Single KPI definition within a team config
 */
export const KPISchema = z.object({
  key: z.string().describe('Unique identifier for the KPI (e.g., "Attendance", "Booking")'),
  label: z.string().describe('Display label for the KPI (e.g., "Attendance Rate")'),
  weight: z.number().min(0).max(1).describe('KPI weight in overall score (0-1)'),
  direction: z.enum(['higher_better', 'lower_better']).describe('Whether higher or lower values are better'),
  unit: KPIUnitSchema.describe('Unit of measurement'),
  color: z.string().regex(/^#[0-9A-F]{6}$/i).describe('Hex color code for UI display'),
  actual_col: z.string().describe('Column name for actual value in raw data'),
  target_col: z.string().describe('Column name for target value in raw data'),
  achievement_col: z.string().optional().describe('Column name for achievement ratio'),
  score_target: z.number().nonnegative().optional()
    .describe('Scoring threshold after aggregation when the target column is a source denominator'),
  score_formula: z.enum(['target_ratio', 'baseline_80']).default('target_ratio')
    .describe('How the aggregated actual is converted into target achievement'),
  cap_achievement: z.boolean().default(true)
    .describe('Whether KPI achievement is capped at 100% before applying its weight'),
  volume_unit: z.string().optional().describe('Unit for volume display (optional)'),
  aggregation: KPIAggregationSchema.default({ method: 'average' }).describe('How employee KPI values roll up to the team level'),
});

export type KPI = z.infer<typeof KPISchema>;

const BalancedScorecardPerspectiveSchema = z.object({
  key: z.string(),
  label: z.string(),
  focus: z.string().optional(),
  strategic_objective: z.string().optional(),
  display_order: z.number().optional(),
  icon_key: z.string().optional(),
});

const BalancedScorecardSchema = z.object({
  enabled: z.boolean().optional(),
  perspectives: z.array(BalancedScorecardPerspectiveSchema).optional(),
  strategy_map_links: z.array(z.object({
    from: z.string(),
    to: z.string(),
  })).optional(),
});

const PerformanceLevelConfigSchema = z.object({
  balanced_scorecard: BalancedScorecardSchema.optional(),
  kpis: z.array(KPISchema.extend({
    perspective: z.string().optional(),
    rollup: z.enum(['average', 'sum', 'latest']).optional(),
  })).optional(),
  positions: z.record(z.string(), z.object({
    capping: z.string().optional(),
    kpis: z.array(KPISchema).min(1),
  })).optional(),
});

/**
 * Grade thresholds for a team
 */
export const GradeThresholdsSchema = z.object({
  A: z.number().min(0).max(100),
  B: z.number().min(0).max(100),
  C: z.number().min(0).max(100),
  D: z.number().min(0).max(100),
});

export type GradeThresholds = z.infer<typeof GradeThresholdsSchema>;

/**
 * Complete team configuration
 */
export const TeamConfigSchema = z.object({
  team: z.string().min(1).describe('Team name (e.g., "Inbound", "Sales")'),
  db_name: z.string().min(1).describe('Database/dataset name for this team'),
  region: z.enum(['EGY', 'UAE']).describe('Geographic region'),
  employee_id_col: z.string().describe('Column name for employee ID'),
  employee_name_col: z.string().describe('Column name for employee name'),
  grade_thresholds: GradeThresholdsSchema.describe('Grade thresholds (A, B, C, D)'),
  kpis: z.array(KPISchema).default([]).describe('Root KPI definitions; position-scoped teams may define them under performance_levels.Employee.positions'),
  performance_levels: z.record(z.string(), PerformanceLevelConfigSchema).optional(),
});

export type TeamConfig = z.infer<typeof TeamConfigSchema>;

/**
 * API response wrapper for team configs
 */
export const TeamConfigResponseSchema = z.object({
  success: z.boolean(),
  data: TeamConfigSchema,
});

/**
 * API response wrapper for multiple team configs
 */
export const TeamConfigsResponseSchema = z.object({
  success: z.boolean(),
  data: z.array(TeamConfigSchema),
});

/**
 * Validate a single team config
 * @param config - The config object to validate
 * @returns Validated config or throws ZodError
 */
export function validateTeamConfig(config: unknown): TeamConfig {
  return TeamConfigSchema.parse(config);
}

/**
 * Validate multiple team configs
 * @param configs - Array of config objects to validate
 * @returns Validated configs or throws ZodError
 */
export function validateTeamConfigs(configs: unknown): TeamConfig[] {
  return z.array(TeamConfigSchema).parse(configs);
}

/**
 * Type-safe way to check if a config is valid
 * @param config - The config object to check
 * @returns true if valid, false otherwise
 */
export function isValidTeamConfig(config: unknown): config is TeamConfig {
  const result = TeamConfigSchema.safeParse(config);
  return result.success;
}
