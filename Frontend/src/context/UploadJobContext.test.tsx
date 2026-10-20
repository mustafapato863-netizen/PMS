import { fireEvent, render, screen } from '@testing-library/react';
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UploadJobProvider } from './UploadJobContext';
import { useUploadJob } from './uploadJobState';

const processingJob = vi.hoisted(() => ({
  data: {
    job_id: 'job-1',
    id: 'job-1',
    kind: 'pms_upload',
    status: 'running' as 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled',
    progress: 42,
    attempt: 1,
    max_attempts: 3,
    result: null as Record<string, unknown> | null,
    error: null as { message?: string } | null,
    status_url: '/api/jobs/job-1',
  },
}));

vi.mock('./auth', () => ({
  useAuth: () => ({ currentUser: { id: 'user-1' } }),
}));

vi.mock('../hooks/api/useProcessingJobs', () => ({
  useProcessingJob: vi.fn(() => ({ data: processingJob.data, isError: false })),
}));

vi.mock('../hooks/usePerformanceData', () => ({
  refreshPerformanceData: vi.fn(),
}));

function UploadPage() {
  const { activeJobId, trackJob } = useUploadJob();

  return (
    <div>
      <p>Upload settings page</p>
      <p data-testid="active-job">{activeJobId ?? 'idle'}</p>
      <button type="button" onClick={() => trackJob('job-1')}>Start upload</button>
      <Link to="/dashboard">Go to dashboard</Link>
    </div>
  );
}

describe('UploadJobProvider', () => {
  beforeEach(() => {
    processingJob.data.status = 'running';
    processingJob.data.progress = 42;
    processingJob.data.result = null;
    processingJob.data.error = null;
  });

  it('keeps the processing note visible after navigating away from the upload page', () => {
    render(
      <MemoryRouter initialEntries={['/settings']}>
        <UploadJobProvider>
          <Routes>
            <Route path="/settings" element={<UploadPage />} />
            <Route path="/dashboard" element={<p>Dashboard page</p>} />
          </Routes>
        </UploadJobProvider>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Start upload' }));
    expect(screen.getByRole('status')).toHaveTextContent('Your file is processing in the background.');
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '42');

    fireEvent.click(screen.getByRole('link', { name: 'Go to dashboard' }));
    expect(screen.getByText('Dashboard page')).toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent('Your file is processing in the background.');
  });

  it('shows sheet header notices when a background upload succeeds or fails', () => {
    processingJob.data.status = 'succeeded';
    processingJob.data.result = {
      records_imported: 1,
      column_warnings: [
        {
          sheet: 'Outbound',
          code: 'unmapped_columns',
          headers: ['Side Note', '<img src=x onerror=alert(1)>'],
          truncated: false,
        },
      ],
    };
    const { container } = render(
      <MemoryRouter initialEntries={['/settings']}>
        <UploadJobProvider>
          <Routes>
            <Route path="/settings" element={<UploadPage />} />
          </Routes>
        </UploadJobProvider>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Start upload' }));

    expect(screen.getByRole('status')).toHaveTextContent('Upload complete — 1 records are ready.');
    expect(screen.getByRole('heading', { name: 'Columns not mapped to scoring' })).toBeInTheDocument();
    expect(screen.getByText('These columns do not change your scoring rules. Review their names in Excel.')).toBeInTheDocument();
    expect(screen.getByText('Outbound: <img src=x onerror=alert(1)>')).toBeInTheDocument();
    expect(container.querySelector('img')).toBeNull();
  });

  it('shows a target conflict notice when a background upload fails', () => {
    processingJob.data.status = 'failed';
    processingJob.data.error = { message: 'Neither value was used as the quality target.' };
    processingJob.data.result = {
      column_warnings: [
        {
          sheet: 'Outbound',
          code: 'ambiguous_alias',
          headers: ['T.Quality%', 'T.Quality Target'],
          truncated: false,
        },
      ],
    };
    render(
      <MemoryRouter initialEntries={['/settings']}>
        <UploadJobProvider>
          <Routes>
            <Route path="/settings" element={<UploadPage />} />
          </Routes>
        </UploadJobProvider>
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByRole('button', { name: 'Start upload' }));

    expect(screen.getByRole('alert')).toHaveTextContent('Neither value was used as the quality target.');
    expect(screen.getByTestId('active-job')).toHaveTextContent('idle');
    expect(screen.getByRole('heading', { name: 'Conflicting target columns' })).toBeInTheDocument();
    expect(screen.getByText('Outbound: T.Quality Target')).toBeInTheDocument();
  });
});
