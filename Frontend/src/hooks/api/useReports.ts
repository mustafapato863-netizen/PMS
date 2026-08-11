import { useCallback } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';
import type {
  GeneratedReport,
  PaginatedReports,
  ReportConfiguration,
  ReportOptions,
  ReportPreview,
  ReportTemplate,
  SavedReportTemplate,
  StoryGeneratedReport,
  StoryPageData,
  StoryRegistry,
  StoryReportDefinition,
  StoryReportDraft,
  StoryReportScope,
  StoryTemplate,
  StoryValidationResult,
} from '../../features/reports/types';
import { waitForProcessingJob, type ProcessingJobReference } from './useProcessingJobs';

interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
}

export const reportQueryKeys = {
  templates: ['reports', 'templates'] as const,
  options: ['reports', 'options'] as const,
  list: (mine: boolean, page: number) => ['reports', 'list', mine, page] as const,
  saved: ['reports', 'saved'] as const,
  storyTemplates: ['reports', 'story', 'templates'] as const,
  storyRegistry: ['reports', 'story', 'registry'] as const,
  storyDraft: (id: string) => ['reports', 'story', 'draft', id] as const,
  storyPage: (draftId: string, pageId: string) => ['reports', 'story', 'draft', draftId, 'page', pageId] as const,
};

export function useReportTemplates() {
  return useQuery({
    queryKey: reportQueryKeys.templates,
    queryFn: async () => (await apiFetch<ApiResponse<ReportTemplate[]>>('/api/reports/templates')).data,
    staleTime: 10 * 60 * 1000,
  });
}

export function useReportOptions() {
  return useQuery({
    queryKey: reportQueryKeys.options,
    queryFn: async () => (await apiFetch<ApiResponse<ReportOptions>>('/api/reports/options')).data,
    staleTime: 5 * 60 * 1000,
  });
}

export function useGeneratedReports(mine: boolean, page = 1) {
  return useQuery({
    queryKey: reportQueryKeys.list(mine, page),
    queryFn: async () => (
      await apiFetch<ApiResponse<PaginatedReports>>(`/api/reports?mine=${mine}&page=${page}&page_size=10`)
    ).data,
  });
}

export function useSavedReportTemplates() {
  return useQuery({
    queryKey: reportQueryKeys.saved,
    queryFn: async () => (await apiFetch<ApiResponse<SavedReportTemplate[]>>('/api/reports/saved-templates')).data,
  });
}

export function usePreviewReport() {
  return useMutation({
    mutationFn: async (configuration: ReportConfiguration) => (
      await apiFetch<ApiResponse<ReportPreview>>('/api/reports/preview', {
        method: 'POST',
        body: JSON.stringify(configuration),
      })
    ).data,
  });
}

export function useGenerateReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (configuration: ReportConfiguration) => {
      const data = (await apiFetch<ApiResponse<GeneratedReport | ProcessingJobReference>>('/api/reports/generate', {
        method: 'POST',
        body: JSON.stringify(configuration),
      })).data;
      if (!('job_id' in data)) return data;
      const job = await waitForProcessingJob(data.job_id);
      if (job.status !== 'succeeded' || !job.result) {
        throw new Error(job.error?.message || 'Report generation failed.');
      }
      return job.result as unknown as GeneratedReport;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['reports', 'list'] }),
  });
}

export function useDeleteGeneratedReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (reportId: string) => (
      await apiFetch<ApiResponse<{ id: string; name: string }>>(`/api/reports/${reportId}`, {
        method: 'DELETE',
      })
    ).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['reports', 'list'] }),
  });
}

export function useSaveReportTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ templateName, configuration }: { templateName: string; configuration: ReportConfiguration }) => (
      await apiFetch<ApiResponse<{ id: string; name: string }>>('/api/reports/saved-templates', {
        method: 'POST',
        body: JSON.stringify({ template_name: templateName, configuration }),
      })
    ).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: reportQueryKeys.saved }),
  });
}

export function useStoryTemplates() {
  return useQuery({
    queryKey: reportQueryKeys.storyTemplates,
    queryFn: async () => (await apiFetch<ApiResponse<StoryTemplate[]>>('/api/reports/story/templates')).data,
    staleTime: 10 * 60 * 1000,
  });
}

export function useStoryRegistry() {
  return useQuery({
    queryKey: reportQueryKeys.storyRegistry,
    queryFn: async () => (await apiFetch<ApiResponse<StoryRegistry>>('/api/reports/story/registry')).data,
    staleTime: 30 * 60 * 1000,
  });
}

export function useStoryDraft(draftId?: string) {
  return useQuery({
    queryKey: reportQueryKeys.storyDraft(draftId || ''),
    queryFn: async () => (await apiFetch<ApiResponse<StoryReportDraft>>(`/api/reports/story/drafts/${draftId}`)).data,
    enabled: Boolean(draftId),
  });
}

export function useCreateStoryDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: {
      name: string;
      report_type: string;
      template_id: string | null;
      scope: StoryReportScope;
      primary_period: { month: string; year: number };
      comparison_period: { month: string; year: number } | null;
    }) => (await apiFetch<ApiResponse<StoryReportDraft>>('/api/reports/story/drafts', {
      method: 'POST', body: JSON.stringify(payload),
    })).data,
    onSuccess: (draft) => queryClient.setQueryData(reportQueryKeys.storyDraft(draft.id), draft),
  });
}

export function useSaveStoryDraft() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, expectedVersion, name, definition, commentary }: {
      id: string; expectedVersion: number; name?: string; definition?: StoryReportDefinition; commentary?: Record<string, string>;
    }) => (await apiFetch<ApiResponse<StoryReportDraft>>(`/api/reports/story/drafts/${id}`, {
      method: 'PUT',
      body: JSON.stringify({ expected_version: expectedVersion, name, definition, management_commentary: commentary ? { entries: commentary } : undefined }),
    })).data,
    onSuccess: (draft) => queryClient.setQueryData(reportQueryKeys.storyDraft(draft.id), draft),
  });
}

export function useStoryPage(draftId?: string, pageId?: string) {
  return useQuery({
    queryKey: reportQueryKeys.storyPage(draftId || '', pageId || ''),
    queryFn: () => fetchStoryPage(draftId!, pageId!),
    enabled: Boolean(draftId && pageId),
    staleTime: 5 * 60 * 1000,
  });
}

const fetchStoryPage = async (draftId: string, pageId: string) => (
  await apiFetch<ApiResponse<StoryPageData>>(`/api/reports/story/drafts/${draftId}/pages/${pageId}`)
).data;

export function usePrefetchStoryPage() {
  const queryClient = useQueryClient();
  return useCallback((draftId?: string, pageId?: string) => {
    if (!draftId || !pageId) return Promise.resolve();
    return queryClient.prefetchQuery({
      queryKey: reportQueryKeys.storyPage(draftId, pageId),
      queryFn: () => fetchStoryPage(draftId, pageId),
      staleTime: 5 * 60 * 1000,
    });
  }, [queryClient]);
}

export function useValidateStoryDraft() {
  return useMutation({
    mutationFn: async (draftId: string) => (await apiFetch<ApiResponse<StoryValidationResult>>(`/api/reports/story/drafts/${draftId}/validate`, { method: 'POST' })).data,
  });
}

export function useRegenerateStoryNarratives() {
  return useMutation({
    mutationFn: async ({ id, expectedVersion, pageId }: { id: string; expectedVersion: number; pageId?: string }) => (
      await apiFetch<ApiResponse<StoryReportDraft>>(`/api/reports/story/drafts/${id}/narratives/regenerate`, {
        method: 'POST', body: JSON.stringify({ expected_version: expectedVersion, slide_id: pageId }),
      })
    ).data,
  });
}

export function useGenerateStoryPdf() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ id, expectedVersion }: { id: string; expectedVersion: number }) => {
      const data = (await apiFetch<ApiResponse<StoryGeneratedReport | ProcessingJobReference>>(`/api/reports/story/drafts/${id}/generate`, {
        method: 'POST', body: JSON.stringify({ expected_version: expectedVersion, output_format: 'pdf' }),
      })).data;
      if (!('job_id' in data)) return data;
      const job = await waitForProcessingJob(data.job_id);
      if (job.status !== 'succeeded' || !job.result) {
        throw new Error(job.error?.message || 'Presentation PDF generation failed.');
      }
      return job.result as unknown as StoryGeneratedReport;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['reports', 'list'] }),
  });
}

export function useSaveStoryTemplate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ name, templateKey, reportType, definition }: {
      name: string; templateKey: string; reportType: string; definition: StoryReportDefinition;
    }) => (await apiFetch<ApiResponse<StoryTemplate>>('/api/reports/story/templates', {
      method: 'POST',
      body: JSON.stringify({ name, template_key: templateKey, report_type: reportType, description: '', visibility: 'private', definition: { ...definition, narratives: undefined } }),
    })).data,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: reportQueryKeys.storyTemplates }),
  });
}
