export interface UploadHistoryItem {
  id: string;
  filename?: string | null;
  uploaded_at?: string | null;
  uploaded_by?: string | null;
  status?: string | null;
  record_count?: number | null;
  team_count?: number | null;
  teams?: string[] | null;
  periods?: string[] | null;
}

export interface ManagementUploadItem extends UploadHistoryItem {
  teams?: string[] | null;
  periods?: string[] | null;
  levels?: string[] | null;
}

export interface KPIWeightItem {
  team?: string | null;
  weights?: Record<string, number> | null;
  scopes?: Array<{
    position?: string | null;
    weights?: Record<string, number> | null;
  }> | null;
}

export interface KPITargetItem {
  team?: string | null;
  targets?: Record<string, number> | null;
  scopes?: Array<{
    position?: string | null;
    targets?: Record<string, number> | null;
  }> | null;
}

export interface TeamConfigItem {
  name: string;
}

export type SettingsSection = 'upload' | 'corrective_actions' | 'kpis' | 'users' | 'teams';
