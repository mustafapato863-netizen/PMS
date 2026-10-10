import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { EvaluationApplyProgress } from './EvaluationApplyProgress';
import {
  applyJobActions,
  presentApplyJob,
  type ApplyJobSnapshot,
} from './evaluationApplyJobs';

function job(overrides: Partial<ApplyJobSnapshot> = {}): ApplyJobSnapshot {
  return {
    jobId: 'job-1',
    state: 'pending',
    jobStatus: 'queued',
    claimEpoch: 3,
    stagedCount: 1,
    promotedCount: 0,
    stageCursor: 'cursor-secret',
    revisionId: null,
    progress: 0,
    attemptCount: 2,
    expectedCount: 4,
    safeReason: null,
    resumed: false,
    permissions: { cancel: null, retry: null, recover: null },
    ...overrides,
  };
}

function renderCard(snapshot: ApplyJobSnapshot, confirmCancel = false, busy = false) {
  const handlers = {
    onArmCancel: vi.fn(),
    onConfirmCancel: vi.fn(),
    onDismissCancel: vi.fn(),
    onRetry: vi.fn(),
    onRecover: vi.fn(),
  };
  const view = render(
    <EvaluationApplyProgress
      job={snapshot}
      presentation={presentApplyJob(snapshot)}
      actions={applyJobActions(snapshot)}
      confirmCancel={confirmCancel}
      busy={busy}
      {...handlers}
    />,
  );
  return { ...view, ...handlers };
}

describe('EvaluationApplyProgress', () => {
  it('exposes a compact progress bar for a queued job without rendering the cursor', () => {
    const { container } = renderCard(job());
    const bar = screen.getByRole('progressbar');
    expect(bar).toHaveAttribute('aria-valuemin', '0');
    expect(bar).toHaveAttribute('aria-valuemax', '100');
    expect(bar).toHaveAttribute('aria-valuenow', '0');
    expect(bar).toHaveAttribute('aria-valuetext', expect.stringContaining('Queued'));
    expect(bar.firstElementChild).toHaveStyle({ width: '0%' });
    expect(screen.getByText(/Scores are unchanged/)).toBeInTheDocument();
    expect(screen.getByText(/Staged 1 of 4/)).toBeInTheDocument();
    expect(screen.getByText(/Attempt 2/)).toBeInTheDocument();
    const section = container.querySelector('section');
    expect(section?.className).toContain('min-w-0');
    expect(section?.className).toContain('w-full');
    expect(section?.className).toContain('max-w-full');
    expect(container.innerHTML).not.toContain('overflow-x-auto');
    expect(container.innerHTML).not.toContain('min-w-[');
    expect(screen.queryByText('cursor-secret')).not.toBeInTheDocument();
    expect(screen.queryByText(/permission granted/i)).not.toBeInTheDocument();
    for (const icon of container.querySelectorAll('svg')) expect(icon).toHaveAttribute('aria-hidden', 'true');
    expect(screen.getByRole('button', { name: 'Cancel background apply' }).className).toContain('focus-visible:outline');
  });

  it('asks before cancelling and keeps retry hidden until the job has failed or been cancelled', () => {
    const queued = renderCard(job());
    expect(screen.queryByRole('button', { name: 'Retry this job' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel background apply' }));
    expect(queued.onArmCancel).toHaveBeenCalledTimes(1);
    queued.unmount();

    const confirm = renderCard(job(), true);
    const group = screen.getByRole('group', { name: 'Cancel background apply' });
    expect(group).toHaveTextContent(/Scores that are not committed stay unchanged/);
    expect(screen.queryByRole('button', { name: 'Cancel background apply' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Keep this apply' }));
    expect(confirm.onDismissCancel).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole('button', { name: 'Cancel this apply' }));
    expect(confirm.onConfirmCancel).toHaveBeenCalledTimes(1);
  });

  it('offers same-job retry, and explains when another admin must capture a new job', () => {
    const failed = renderCard(job({ state: 'failed', jobStatus: 'failed', safeReason: 'lease_expired', progress: 20 }));
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuemax', '100');
    expect(screen.getByText('Reason lease_expired.')).toBeInTheDocument();
    const retry = screen.getByRole('button', { name: 'Retry this job' });
    expect(retry.className).toContain('inline-flex');
    expect(retry.className).toContain('focus-visible:outline');
    fireEvent.click(retry);
    expect(failed.onRetry).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/does not start a second apply/)).toBeInTheDocument();
    failed.unmount();

    renderCard(job({
      state: 'cancelled',
      jobStatus: 'cancelled',
      permissions: { cancel: null, retry: false, recover: null },
    }));
    expect(screen.queryByRole('button', { name: 'Retry this job' })).not.toBeInTheDocument();
    expect(screen.getByText(/Another admin can cancel the job and apply again/)).toBeInTheDocument();
    expect(screen.queryByText(/permission granted/i)).not.toBeInTheDocument();
  });

  it('recovers a committed revision without offering another apply from this card', () => {
    const waiting = job({
      state: 'promoted',
      jobStatus: 'running',
      revisionId: 'revision-9',
      progress: 90,
      stagedCount: 4,
      promotedCount: 4,
    });
    const view = renderCard(waiting);
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '99');
    expect(screen.getByRole('progressbar').firstElementChild).toHaveStyle({ width: '99%' });
    expect(screen.getByText(/Awaiting acknowledgement/)).toBeInTheDocument();
    expect(screen.getByText(/Rollback remains on the latest revision only/)).toBeInTheDocument();
    expect(screen.getByText(/does not apply the month again/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Acknowledge committed revision' }));
    expect(view.onRecover).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Retry this job' })).not.toBeInTheDocument();
  });

  it('hides an unsafe reason and disables the actions while the card is busy', () => {
    renderCard(job({ state: 'failed', jobStatus: 'failed', safeReason: 'Hidden person name' }), false, true);
    expect(screen.getByText(/failure reason was hidden/)).toBeInTheDocument();
    expect(screen.queryByText('Hidden person name')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry this job' })).toBeDisabled();
  });
});
