import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertCircle, CheckCircle2, Loader2, X } from 'lucide-react';
import { useAuth } from './auth';
import { UploadJobContext } from './uploadJobState';
import { refreshPerformanceData } from '../hooks/usePerformanceData';
import { useProcessingJob, type ProcessingJob } from '../hooks/api/useProcessingJobs';

const terminalStatuses = new Set(['succeeded', 'failed', 'cancelled']);

function UploadProgressNote({
  job,
  isError,
  onDismiss,
}: {
  job?: ProcessingJob;
  isError: boolean;
  onDismiss: () => void;
}) {
  const navigate = useNavigate();
  const status = job?.status;
  const isTerminal = Boolean(status && terminalStatuses.has(status));
  const progress = Math.max(0, Math.min(100, Number(job?.progress) || 0));
  const isFailed = status === 'failed' || status === 'cancelled';
  const isSucceeded = status === 'succeeded';
  const Icon = isFailed ? AlertCircle : isSucceeded ? CheckCircle2 : Loader2;

  let message = 'Connecting to upload status…';
  if (isError && !job) message = 'Could not refresh the upload status. Retrying…';
  else if (status === 'queued') message = 'Upload queued. You can keep working while it processes.';
  else if (status === 'running') message = 'Your file is processing in the background.';
  else if (isSucceeded) {
    const records = Number(job?.result?.records_imported);
    message = Number.isFinite(records) && records > 0
      ? `Upload complete — ${records.toLocaleString()} records are ready.`
      : 'Upload complete — your data is ready.';
  } else if (isFailed) {
    message = job?.error?.message || (status === 'cancelled' ? 'Upload processing was cancelled.' : 'Upload processing failed.');
  }

  const tone = isFailed
    ? 'border-rose-200 bg-rose-50 text-rose-900 dark:border-rose-900/70 dark:bg-rose-950/95 dark:text-rose-100'
    : isSucceeded
      ? 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/70 dark:bg-emerald-950/95 dark:text-emerald-100'
      : 'border-blue-200 bg-white text-slate-900 dark:border-blue-900/70 dark:bg-slate-900 dark:text-slate-100';

  return (
    <aside
      role={isFailed ? 'alert' : 'status'}
      aria-live={isFailed ? 'assertive' : 'polite'}
      className={`fixed bottom-4 left-1/2 z-[10000] w-[min(560px,calc(100vw-24px))] -translate-x-1/2 rounded-2xl border px-4 py-3 shadow-xl backdrop-blur ${tone}`}
    >
      <div className="flex items-start gap-3">
        <Icon size={19} className={`mt-0.5 shrink-0 ${!isTerminal ? 'animate-spin text-blue-600 dark:text-blue-300' : ''}`} />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-bold">Employee PMS upload</p>
          <p className="mt-0.5 text-xs leading-relaxed opacity-80">{message}</p>
          {!isTerminal && (
            <div
              className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
              role="progressbar"
              aria-label="Upload processing progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={progress}
            >
              <div
                className="h-full rounded-full bg-blue-600 transition-[width] duration-500 dark:bg-blue-400"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => navigate('/settings')}
          className="shrink-0 rounded-lg px-2 py-1 text-xs font-bold text-blue-700 hover:bg-blue-500/10 focus-visible:outline-2 focus-visible:outline-blue-500 dark:text-blue-300"
        >
          Uploads
        </button>
        {isTerminal && (
          <button
            type="button"
            onClick={onDismiss}
            aria-label="Dismiss upload status"
            className="shrink-0 rounded-lg p-1 opacity-60 hover:bg-black/5 hover:opacity-100 focus-visible:outline-2 focus-visible:outline-blue-500 dark:hover:bg-white/10"
          >
            <X size={16} />
          </button>
        )}
      </div>
    </aside>
  );
}

export function UploadJobProvider({ children }: { children: ReactNode }) {
  const { currentUser } = useAuth();
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const { data: job, isError } = useProcessingJob(activeJobId || undefined);

  const trackJob = useCallback((jobId: string) => {
    setActiveJobId(jobId);
  }, []);

  const dismissJob = useCallback(() => setActiveJobId(null), []);

  useEffect(() => {
    if (job?.status === 'succeeded') refreshPerformanceData();
  }, [job?.job_id, job?.status]);

  const contextValue = useMemo(() => ({ activeJobId, trackJob }), [activeJobId, trackJob]);

  return (
    <UploadJobContext.Provider value={contextValue}>
      {children}
      {currentUser && activeJobId && <UploadProgressNote job={job} isError={isError} onDismiss={dismissJob} />}
    </UploadJobContext.Provider>
  );
}
