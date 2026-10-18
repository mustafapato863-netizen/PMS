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

  it('safely catches child errors and renders the enterprise MaintenanceView in error mode', () => {
    render(
      <AppErrorBoundary>
        <ProblemChild shouldThrow={true} />
      </AppErrorBoundary>
    );

    expect(screen.getByText('Application Protected & Recovered')).toBeInTheDocument();
    expect(screen.getByText('Protected Safe Mode')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /try again \/ reconnect/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /return home/i })).toBeInTheDocument();
  });
});
