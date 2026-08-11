import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../../lib/apiClient';

export type ProcessingJobStatus = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export interface ProcessingJob {
  job_id: string;
  id: string;
  kind: string;
  status: ProcessingJobStatus;
  progress: number;
  attempt: number;
  max_attempts: number;
  result: Record<string, unknown> | null;
  result_type?: string | null;
  result_id?: string | null;
  error?: { code?: string; message?: string } | null;
  created_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  status_url: string;
}

interface ApiResponse<T> {
  success: boolean;
  message: string;
  data: T;
}

export interface ProcessingJobReference {
  job_id: string;
  kind: string;
  status: ProcessingJobStatus;
  progress: number;
  status_url: string;
}

export const processingJobQueryKeys = {
  detail: (jobId: string) => ['processing-jobs', jobId] as const,
};

export async function getProcessingJob(jobId: string): Promise<ProcessingJob> {
  return (await apiFetch<ApiResponse<ProcessingJob>>(`/api/jobs/${encodeURIComponent(jobId)}`)).data;
}

export async function waitForProcessingJob(
  jobId: string,
  onUpdate?: (job: ProcessingJob) => void,
): Promise<ProcessingJob> {
  let delayMs = 500;
  for (let attempt = 0; attempt < 720; attempt += 1) {
    const job = await getProcessingJob(jobId);
    onUpdate?.(job);
    if (job.status === 'succeeded' || job.status === 'failed' || job.status === 'cancelled') return job;
    await new Promise((resolve) => window.setTimeout(resolve, delayMs));
    delayMs = Math.min(5000, Math.round(delayMs * 1.35));
  }
  throw new Error('The background operation is taking longer than expected. Check the job status again.');
}

export function useProcessingJob(jobId?: string) {
  return useQuery({
    queryKey: processingJobQueryKeys.detail(jobId || ''),
    queryFn: () => getProcessingJob(jobId!),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === 'succeeded' || status === 'failed' || status === 'cancelled' ? false : 1500;
    },
  });
}
