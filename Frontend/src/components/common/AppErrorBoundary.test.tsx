import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import AppErrorBoundary from './AppErrorBoundary';

function ProblemChild({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) {
    throw new Error('Fatal rendering crash');
  }
  return <div>Application content healthy</div>;
}

describe('AppErrorBoundary', () => {
  const originalConsoleError = console.error;

  beforeEach(() => {
    // Suppress console.error output during deliberate error tests
    console.error = vi.fn();
  });

  afterEach(() => {
    console.error = originalConsoleError;
  });

  it('renders children when no runtime error occurs', () => {
    render(
      <AppErrorBoundary>
        <ProblemChild shouldThrow={false} />
      </AppErrorBoundary>
    );

    expect(screen.getByText('Application content healthy')).toBeInTheDocument();
  });

  it('safely catches child errors and renders the enterprise MaintenanceView in error mode', async () => {
    render(
      <AppErrorBoundary>
        <ProblemChild shouldThrow={true} />
      </AppErrorBoundary>
    );

    // MaintenanceView is lazy-loaded behind <Suspense fallback={null}>, so
    // the fallback can take longer than findByText's 1000 ms default to
    // appear when the machine is loaded. Wait longer instead of failing
    // on a slow chunk import; the requirement is that it renders at all.
    expect(await screen.findByText('Application Protected & Recovered', {}, { timeout: 10000 })).toBeInTheDocument();
    expect(screen.getByText('Protected Safe Mode')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again \/ reconnect/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /return home/i })).toBeInTheDocument();
  });
});
