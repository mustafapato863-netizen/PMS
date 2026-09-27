import type { PMSAction } from '../../types';

export interface FollowUpSummary {
  overdue: number;
  due_soon: number;
  open: number;
  in_progress: number;
  completed_this_month: number;
  completion_rate: number;
}

export interface FollowUpFilters {
  state?: string;
  team?: string;
  owner?: string;
  month?: string;
}

export interface FollowUpPayload {
  summary: FollowUpSummary;
  actions: PMSAction[];
}

export const EMPTY_FOLLOW_UP_SUMMARY: FollowUpSummary = {
  overdue: 0,
  due_soon: 0,
  open: 0,
  in_progress: 0,
  completed_this_month: 0,
  completion_rate: 0,
};
