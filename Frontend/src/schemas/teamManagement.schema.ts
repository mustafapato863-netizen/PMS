/**
 * Team Management Schemas
 * Zod validation schemas for team forms and API responses.
 */

import { z } from 'zod';

// Team configuration schema
export const TeamConfigSchema = z.object({
  name: z
    .string()
    .min(1, 'Team name is required')
    .regex(/^[a-z0-9_]+$/, 'Only lowercase letters, numbers, and underscores'),
  display_name: z.string().min(1, 'Display name is required'),
  region: z.enum(['EGY', 'UAE', 'Other']),
  description: z.string().optional(),
  kpi_keys: z.array(z.string()).min(1, 'At least one KPI is required'),
  kpi_weights: z.record(z.string(), z.number()).refine(
    (weights) => {
      const sum = Object.values(weights).reduce((a, b) => a + b, 0);
      return Math.abs(sum - 1.0) < 0.01;
    },
    'KPI weights must sum to 1.0'
  ),
  team_lead: z.string().optional(),
  team_lead_email: z.string().email('Invalid email').optional().or(z.literal('')),
});

// Team create request
export const TeamCreateRequestSchema = TeamConfigSchema.omit({
  kpi_weights: true,
}).extend({
  kpi_weights: z.record(z.string(), z.number()).optional(),
});

// Team update request (all fields optional)
export const TeamUpdateRequestSchema = TeamConfigSchema.partial();

// Team response
export const TeamResponseSchema = TeamConfigSchema.extend({
  is_active: z.boolean(),
  created_at: z.string().datetime().optional(),
  updated_at: z.string().datetime().optional(),
});

// Team list response
export const TeamListResponseSchema = z.object({
  teams: z.array(TeamResponseSchema),
  total: z.number(),
  active_count: z.number(),
  inactive_count: z.number(),
});

// Team validation response
export const TeamValidationResponseSchema = z.object({
  valid: z.boolean(),
  team_name: z.string(),
  errors: z.array(z.string()).default([]),
  warnings: z.array(z.string()).default([]),
  message: z.string(),
});

// Onboarding step
export const OnboardingStepSchema = z.object({
  step_number: z.number(),
  name: z.string(),
  description: z.string(),
  required: z.boolean().default(true),
  completed: z.boolean().default(false),
  error: z.string().optional(),
});

// Onboarding response
export const OnboardingResponseSchema = z.object({
  team_name: z.string(),
  status: z.enum(['pending', 'in_progress', 'completed', 'failed']),
  current_step: z.number(),
  total_steps: z.number(),
  steps: z.array(OnboardingStepSchema),
  overall_message: z.string(),
  estimated_time_seconds: z.number().optional(),
});

// Type exports
export type TeamConfig = z.infer<typeof TeamConfigSchema>;
export type TeamCreateRequest = z.infer<typeof TeamCreateRequestSchema>;
export type TeamUpdateRequest = z.infer<typeof TeamUpdateRequestSchema>;
export type TeamResponse = z.infer<typeof TeamResponseSchema>;
export type TeamListResponse = z.infer<typeof TeamListResponseSchema>;
export type TeamValidationResponse = z.infer<typeof TeamValidationResponseSchema>;
export type OnboardingStep = z.infer<typeof OnboardingStepSchema>;
export type OnboardingResponse = z.infer<typeof OnboardingResponseSchema>;
