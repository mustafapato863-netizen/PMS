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
    status: 'running' as const,
    progress: 42,
    attempt: 1,
    max_attempts: 3,
    result: null,
    error: null,
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
  const { trackJob } = useUploadJob();

  return (
    <div>
      <p>Upload settings page</p>
      <button type="button" onClick={() => trackJob('job-1')}>Start upload</button>
      <Link to="/dashboard">Go to dashboard</Link>
    </div>
  );
}

describe('UploadJobProvider', () => {
  beforeEach(() => {
    processingJob.data.status = 'running';
    processingJob.data.progress = 42;
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
});
