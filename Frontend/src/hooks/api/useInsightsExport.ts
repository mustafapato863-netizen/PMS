import { useState } from 'react';
import type { InsightFilters, InsightsWorkspace } from '../../features/insights/types';
import { apiTeamParam } from '../../features/insights/filterCascade';
import { API_BASE } from '../../config';
import { waitForProcessingJob } from './useProcessingJobs';

export interface UseInsightsExportOptions {
  filters: InsightFilters;
  workspace?: InsightsWorkspace | null;
  effectivePeriod: string;
  fetchWithRole: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
}

export function useInsightsExport({
  filters,
  workspace,
  effectivePeriod,
  fetchWithRole,
}: UseInsightsExportOptions) {
  const [exportState, setExportState] = useState<'idle' | 'exporting' | 'error'>('idle');
  const [exportError, setExportError] = useState<string | null>(null);

  const handleExport = async () => {
    const period = workspace?.options.periods.find((item) => item.key === effectivePeriod);
    if (!period) {
      setExportState('error');
      setExportError('The selected Insights period is unavailable for export.');
      return;
    }
    setExportState('exporting');
    setExportError(null);
    try {
      const response = await fetchWithRole(`${API_BASE}/api/reports/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          report_type: 'insights',
          report_name: `Insights - ${period.month} ${period.year}`,
          start_month: period.month,
          start_year: period.year,
          region: filters.region || null,
          branch: filters.branch || null,
          team: apiTeamParam(filters) || null,
          position: filters.position || null,
          performance_level: filters.performanceLevel || null,
          employee_id: filters.employeeId || null,
          kpi: filters.kpi || null,
          severity: filters.severity || null,
          insight_type: filters.insightType || null,
          included_sections: ['summary', 'team_breakdown', 'kpi_breakdown', 'details'],
          output_format: 'pptx',
        }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail || 'PowerPoint export failed.');
      }
      const responseBody = await response.json();
      let generatedReport = responseBody.data as { download_url?: string; file_name?: string; job_id?: string };
      if (generatedReport?.job_id) {
        const job = await waitForProcessingJob(generatedReport.job_id);
        if (job.status !== 'succeeded' || !job.result) {
          throw new Error(job.error?.message || 'PowerPoint generation failed.');
        }
        generatedReport = job.result as typeof generatedReport;
      }
      if (!generatedReport?.download_url) {
        throw new Error('The generated PowerPoint download is unavailable.');
      }
      const downloadUrl = generatedReport.download_url.startsWith('http')
        ? generatedReport.download_url
        : `${API_BASE}${generatedReport.download_url}`;
      const fileResponse = await fetchWithRole(downloadUrl);
      if (!fileResponse.ok) throw new Error('The generated PowerPoint could not be downloaded.');
      const blob = await fileResponse.blob();
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = generatedReport.file_name || `insights-${period.year}-${period.month}.pptx`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      setExportState('idle');
    } catch (error) {
      setExportState('error');
      setExportError(error instanceof Error ? error.message : 'PowerPoint export failed.');
    }
  };

  return {
    exportState,
    exportError,
    handleExport,
  };
}
