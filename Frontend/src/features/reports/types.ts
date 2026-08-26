export type ReportType =
  | 'executive'
  | 'team'
  | 'position'
  | 'employee'
  | 'grade_distribution'
  | 'corrective_actions'
  | 'kpi'
  | 'data_quality'
  | 'monthly_uae'
  | 'monthly_egypt'
  | 'team_marketing'
  | 'insights'
  | 'executive_group_summary'
  | 'uae_executive_summary';

export type ReportOutputFormat = 'pptx' | 'pdf' | 'excel';

export interface ReportTemplate {
  type: ReportType;
  category: string;
  name: string;
  description: string;
  formats: Array<'pptx' | 'pdf' | 'excel'>;
  sections: string[];
}

export interface ReportPeriod {
  year: number;
  month: string;
  key: string;
}

export interface ReportEmployeeOption {
  id: string;
  name: string;
  team: string;
  position: string;
  performance_level: string;
  region: string;
}

export interface ReportOptions {
  periods: ReportPeriod[];
  teams: string[];
  regions: string[];
  performance_levels: string[];
  positions: string[];
  employees: ReportEmployeeOption[];
  grades: string[];
  statuses: string[];
  kpis?: string[];
  can_export: boolean;
  role?: string;
  can_view_people?: boolean;
  can_view_actions?: boolean;
  allowed_formats?: ReportOutputFormat[];
}

export interface ReportConfiguration {
  report_type: ReportType;
  report_name: string;
  start_month: string;
  start_year: number;
  end_month?: string | null;
  end_year?: number | null;
  comparison_month?: string | null;
  comparison_year?: number | null;
  region?: string | null;
  team?: string | null;
  position?: string | null;
  performance_level?: string | null;
  employee_id?: string | null;
  grade?: string | null;
  status?: string | null;
  kpi?: string | null;
  severity?: string | null;
  insight_type?: string | null;
  included_sections: string[];
  output_format: ReportOutputFormat;
  slides?: ReportSlideSchema[];
}

export interface BlockConfigSchema {
  settings: Record<string, unknown>;
}

export interface ReportBlockSchema {
  id: string;
  type: string;
  config: BlockConfigSchema;
}

export interface ReportSlideSchema {
  id: string;
  title: string;
  layout: string;
  blocks: ReportBlockSchema[];
}

export interface ReportPreview {
  title: string;
  report_type: ReportType;
  scope: string;
  period: string;
  filters: Record<string, unknown>;
  included_sections: string[];
  summary: Record<string, unknown>;
  record_count: number;
  warnings: string[];
  table_preview: Array<Record<string, unknown>>;
  preview_redacted?: boolean;
  capabilities?: {
    can_view_people: boolean;
    can_view_actions: boolean;
  };
}

export interface GeneratedReport {
  id: string;
  name: string;
  report_type: ReportType;
  scope: string;
  period: string;
  created_by: string;
  created_at: string;
  format: ReportOutputFormat;
  status: 'ready' | 'failed';
  file_name: string;
  record_count: number;
  warning?: string | null;
  configuration: ReportConfiguration;
  download_url: string;
}

export interface SavedReportTemplate {
  id: string;
  name: string;
  report_type: ReportType;
  configuration: ReportConfiguration;
  included_sections: string[];
  preferred_format: ReportOutputFormat;
  visibility: 'private';
  updated_at: string;
}

export interface PaginatedReports {
  items: GeneratedReport[];
  total: number;
  page: number;
  page_size: number;
}

export interface ReportCenterFilters {
  period?: string;
  comparison_period?: string;
  region?: string;
  team?: string;
  performance_level?: string;
  position?: string;
  employee_id?: string;
  grade?: string;
  status?: string;
  kpi?: string;
}

export interface ReportCenterCapabilities {
  role: string;
  can_export: boolean;
  can_view_people: boolean;
  can_view_actions: boolean;
  allowed_formats: ReportOutputFormat[];
}

export interface ReportCenterPeriod {
  key: string;
  month: string;
  year: number;
}

export interface ReportCenterResponse {
  role: string;
  filters: Record<string, string | undefined>;
  period: ReportCenterPeriod | null;
  comparison_period: ReportCenterPeriod | null;
  summary: Record<string, number | string | null | undefined>;
  trend: Array<Record<string, unknown>>;
  team_comparison: Array<Record<string, unknown>>;
  kpi_health: Array<Record<string, unknown>>;
  insights: Record<string, unknown>;
  corrective_actions: {
    total: number;
    open: number;
    by_status: Record<string, number>;
    by_team: Record<string, number>;
    items: Array<Record<string, unknown>>;
  } | null;
  options: ReportOptions;
  capabilities: ReportCenterCapabilities;
  as_of: string;
  data_version: number;
}

export interface ReportCenterRecordsResponse {
  role: string;
  period: ReportCenterPeriod | null;
  comparison_period: ReportCenterPeriod | null;
  filters: Record<string, string | undefined>;
  items: Array<Record<string, unknown>>;
  page_size: number;
  next_cursor: string | null;
  has_more: boolean;
  total: number | null;
  capabilities: ReportCenterCapabilities;
  as_of: string;
  data_version: number;
}

export interface StoryReportScope {
  region?: string | null;
  team?: string | null;
  position?: string | null;
  performance_level?: string | null;
  employee_id?: string | null;
  grade?: string | null;
  status?: string | null;
}

export interface StoryBlockConfig {
  title?: string | null;
  metrics: string[];
  comparison: boolean;
  number_format: 'standard' | 'compact' | 'percent' | 'currency';
  row_limit: number;
  sort_by?: string | null;
  sort_direction: 'asc' | 'desc';
  show_icons: boolean;
  show_subtitle: boolean;
  show_data_labels: boolean;
  show_target: boolean;
  narrative_mode: 'auto' | 'manual' | 'auto_commentary';
  include_evidence: boolean;
  include_recommendations: boolean;
  max_length: number;
  scope_override: Record<string, string>;
}

export interface StoryReportBlock {
  id: string;
  type: string;
  slot: string;
  config: StoryBlockConfig;
}

export interface StoryReportPage {
  id: string;
  title: string;
  layout: string;
  order: number;
  blocks: StoryReportBlock[];
}

export interface GeneratedNarrative {
  block_id: string;
  text: string;
  generated_at: string;
  evidence: string[];
}

export interface StoryReportDefinition {
  slides: StoryReportPage[];
  theme_key: string;
  language: 'en' | 'ar';
  preferred_format: 'pdf';
  story_metadata?: {
    mode: 'standard' | 'full' | 'compact';
    fixed_page_count: number;
    pages_per_team: number;
    outline: string[];
    recommended: boolean;
  };
  narratives: Record<string, GeneratedNarrative>;
}

export interface StoryTemplate {
  id: string;
  name: string;
  template_key: string;
  report_type: ReportType;
  description: string;
  visibility: 'private' | 'organization';
  version: number;
  definition: Omit<StoryReportDefinition, 'narratives'>;
  theme_key: string;
  language: 'en' | 'ar';
  preferred_format: 'pdf';
  is_system_template: boolean;
  updated_at: string | null;
  page_count: number;
}

export interface ManagementCommentary {
  entries: Record<string, string>;
}

export interface StoryReportDraft {
  id: string;
  name: string;
  report_type: ReportType;
  template_id: string | null;
  template_version: number | null;
  owner_user_id: string;
  status: 'editing' | 'generated' | 'archived';
  primary_period: { month: string; year: number };
  comparison_period: { month: string; year: number } | null;
  scope: StoryReportScope;
  definition: StoryReportDefinition;
  management_commentary: ManagementCommentary;
  validation: StoryValidationResult | null;
  version: number;
  last_saved_at: string | null;
  updated_at: string | null;
}

export interface StoryValidationIssue {
  severity: 'error' | 'warning';
  code: string;
  message: string;
  slide_id?: string | null;
  block_id?: string | null;
}

export interface StoryValidationResult {
  valid: boolean;
  issues: StoryValidationIssue[];
  validated_at: string;
}

export interface StoryBlockData {
  block_id: string;
  block_type: string;
  state: 'ready' | 'no_data' | 'incomplete_configuration' | 'permission_denied' | 'source_unavailable';
  data: Record<string, unknown>;
  warnings: string[];
  source_periods: string[];
}

export interface ScoreMovementBridgeData {
  previous_overall_score: number | null;
  current_overall_score: number | null;
  total_score_point_change: number | null;
  comparison_period: string | null;
  current_period: string | null;
  matched_employee_count: number;
  joiner_count: number;
  leaver_count: number;
  kpi_contribution_movements: Array<{ label: string; score_point_change: number }>;
  team_contribution_movements: Array<{ team: string; score_point_change: number }>;
  joiner_effect: number | null;
  leaver_effect: number | null;
  population_scope_mix_effect: number | null;
  configuration_version_effect: number | null;
  missing_incomparable_data_effect: number | null;
  residual: number | null;
  reconciliation_state: 'reconciled' | 'partial' | 'unavailable';
  narrative: string;
  warnings: string[];
}

export interface WeightedKpiImpactRow {
  rank: number;
  key: string;
  name: string;
  team?: string | null;
  position?: string | null;
  actual: number | null;
  previous: number | null;
  target: number | null;
  unit?: string | null;
  direction?: string | null;
  achievement: number | null;
  weight: number | null;
  weighted_contribution: number | null;
  lost_points: number | null;
  score_point_movement: number | null;
}

export interface ManagementAnalysisTableData {
  rows: Array<Record<string, unknown>>;
  row_summary?: { shown?: number; total?: number };
  insufficient_history?: Array<Record<string, unknown>>;
  configuration_issues_excluded?: Array<Record<string, unknown>>;
  groups?: Record<string, Array<Record<string, unknown>>>;
}

export interface StoryPageData {
  slide_id: string;
  blocks: Record<string, StoryBlockData>;
  resolved_at: string;
}

export interface StoryBlockRegistryItem {
  type: string;
  name: string;
  category: string;
  display_category?: string;
  source_page?: string;
  description: string;
  icon: string;
  provider: string;
  slots: string[];
  permissions: string[];
  available?: boolean;
  unavailable_reason?: string | null;
  default?: Record<string, unknown>;
}

export interface StoryLayoutRegistryItem {
  key: string;
  slots: Record<string, string[]>;
  max_blocks: number;
}

export interface StoryRegistry {
  blocks: StoryBlockRegistryItem[];
  layouts: StoryLayoutRegistryItem[];
  categories: string[];
}

export interface StoryGeneratedReport {
  id: string;
  name: string;
  status: 'ready';
  format: 'pdf';
  file_name: string;
  integrity_identifier: string;
  download_url: string;
}
