import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import MaintenanceView from './MaintenanceView';

describe('MaintenanceView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders default scheduled maintenance mode correctly', () => {
    render(<MaintenanceView mode="maintenance" estimatedTime="~20 minutes" />);

    expect(screen.getByText('System Maintenance in Progress')).toBeInTheDocument();
    expect(screen.getByText('Scheduled Maintenance')).toBeInTheDocument();
    expect(screen.getByText('Est: ~20 minutes')).toBeInTheDocument();
    expect(screen.getByText('SGH Hub')).toBeInTheDocument();
    expect(screen.getByText('Performance Intelligence')).toBeInTheDocument();

    // System Services Health Matrix
    expect(screen.getByText('Database')).toBeInTheDocument();
    expect(screen.getByText('Preserved & Intact')).toBeInTheDocument();
    expect(screen.getByText('Security')).toBeInTheDocument();
    expect(screen.getByText('Session Protected')).toBeInTheDocument();
    expect(screen.getByText('Services')).toBeInTheDocument();
    expect(screen.getByText('Optimizing')).toBeInTheDocument();

    // CTAs
    expect(screen.getByRole('button', { name: /try again \/ reconnect/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /return home/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /copy log/i })).toBeInTheDocument();

    // Support footer
    expect(screen.getByText(/support@saudigerman\.com/i)).toBeInTheDocument();
  });

  it('renders unexpected error recovery mode correctly with diagnostics', async () => {
    const user = userEvent.setup();
    const testError = new Error('ChunkLoadError: Failed to fetch dynamically imported module');
    testError.stack = 'Error: ChunkLoadError\n    at Object.test (app.js:1:1)';

    render(
      <MaintenanceView
        mode="error"
        error={testError}
        componentStack="    at InsightsView\n    at AppRoutes"
      />
    );

    expect(screen.getByText('Application Protected & Recovered')).toBeInTheDocument();
    expect(screen.getByText('Protected Safe Mode')).toBeInTheDocument();
    expect(screen.getByText('Standby Recovery')).toBeInTheDocument();

    // Progressive disclosure for diagnostic stack trace
    const diagnosticTrigger = screen.getByRole('button', {
      name: /Diagnostic & Stack Information/i,
    });
    expect(diagnosticTrigger).toBeInTheDocument();

    // Initially collapsed
    expect(screen.queryByText(/ChunkLoadError: Failed to fetch dynamically imported module/i)).not.toBeInTheDocument();

    // Expand accordion
    await user.click(diagnosticTrigger);

    expect(
      await screen.findByText(/ChunkLoadError: Failed to fetch dynamically imported module/i)
    ).toBeInTheDocument();
    expect(screen.getByText(/Component Trace:/i)).toBeInTheDocument();
  });

  it('triggers onRetry when Reconnect button is clicked', async () => {
    const user = userEvent.setup();
    const handleRetry = vi.fn();

    render(<MaintenanceView onRetry={handleRetry} />);

    const retryBtn = screen.getByRole('button', { name: /try again \/ reconnect/i });
    await user.click(retryBtn);

    expect(handleRetry).toHaveBeenCalledTimes(1);
  });

  it('triggers onGoHome when Return Home button is clicked', async () => {
    const user = userEvent.setup();
    const handleGoHome = vi.fn();

    render(<MaintenanceView onGoHome={handleGoHome} />);

    const homeBtn = screen.getByRole('button', { name: /return home/i });
    await user.click(homeBtn);

    expect(handleGoHome).toHaveBeenCalledTimes(1);
  });

  it('copies diagnostic payload to clipboard when Copy Log is clicked', async () => {
    const user = userEvent.setup();
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: {
        writeText: writeTextMock,
      },
      configurable: true,
      writable: true,
    });

    const testError = new Error('Database connection timeout');
    render(<MaintenanceView mode="error" error={testError} />);

    const copyBtn = screen.getByRole('button', { name: /copy log/i });
    await user.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalledTimes(1);
    const clipboardContent = JSON.parse(writeTextMock.mock.calls[0][0]);
    expect(clipboardContent.mode).toBe('error');
    expect(clipboardContent.errorMessage).toBe('Database connection timeout');

    // Button should transition to Copied state
    expect(await screen.findByText('Copied')).toBeInTheDocument();
  });
});
