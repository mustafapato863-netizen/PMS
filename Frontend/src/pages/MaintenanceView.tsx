import { useState, useId } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Wrench,
  RefreshCw,
  Home,
  Copy,
  Check,
  ChevronDown,
  ShieldCheck,
  Database,
  Cpu,
  HeartPulse,
  AlertTriangle,
  LifeBuoy,
} from 'lucide-react';

export interface MaintenanceViewProps {
  /** Mode: 'maintenance' for planned downtime, or 'error' for unexpected crash recovery */
  mode?: 'maintenance' | 'error';
  /** Optional custom title */
  title?: string;
  /** Optional custom description */
  description?: string;
  /** Caught error object if in error recovery mode */
  error?: Error | null;
  /** Component stack trace if in error recovery mode */
  componentStack?: string | null;
  /** Callback when user clicks Retry / Refresh */
  onRetry?: () => void;
  /** Callback when user clicks Return to Dashboard */
  onGoHome?: () => void;
  /** Estimated completion time for maintenance mode (e.g. "~15 minutes") */
  estimatedTime?: string;
}

export default function MaintenanceView({
  mode = 'maintenance',
  title,
  description,
  error,
  componentStack,
  onRetry,
  onGoHome,
  estimatedTime = 'Short duration',
}: MaintenanceViewProps) {
  const [isRetrying, setIsRetrying] = useState(false);
  const [copied, setCopied] = useState(false);
  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const diagnosticsId = useId();

  const isErrorMode = mode === 'error' || Boolean(error);

  const displayTitle = title || (isErrorMode
    ? 'Application Protected & Recovered'
    : 'System Maintenance in Progress');

  const displayDescription = description || (isErrorMode
    ? 'The application encountered an unexpected runtime error and immediately transitioned to this safe screen to safeguard your data and system state.'
    : 'We are currently performing scheduled platform enhancements, database optimizations, and system updates to ensure peak performance.');

  const handleRetry = () => {
    setIsRetrying(true);
    if (onRetry) {
      onRetry();
    } else {
      window.location.reload();
    }
  };

  const handleHome = () => {
    if (onGoHome) {
      onGoHome();
    } else {
      window.location.href = '/executive';
    }
  };

  const handleCopyDiagnostics = async () => {
    const diagnosticPayload = {
      timestamp: new Date().toISOString(),
      url: window.location.href,
      userAgent: navigator.userAgent,
      mode,
      errorName: error?.name || 'N/A',
      errorMessage: error?.message || 'N/A',
      stack: error?.stack || 'N/A',
      componentStack: componentStack || 'N/A',
    };

    try {
      await navigator.clipboard.writeText(JSON.stringify(diagnosticPayload, null, 2));
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    } catch {
      // Fallback if clipboard API is blocked
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center p-4 sm:p-6 bg-[var(--bg-base)] text-[var(--text-primary)] transition-colors duration-300 relative overflow-hidden select-none"
      style={{ background: 'var(--bg-base)' }}
    >
      {/* Ambient Radial Lighting & Glowing Blobs */}
      <div
        className="absolute top-1/4 left-1/3 w-[500px] h-[500px] rounded-full bg-blue-500/10 blur-[140px] pointer-events-none"
        aria-hidden="true"
      />
      <div
        className="absolute bottom-1/4 right-1/3 w-[550px] h-[550px] rounded-full bg-indigo-500/10 blur-[150px] pointer-events-none"
        aria-hidden="true"
      />
      <div
        className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[650px] h-[650px] rounded-full bg-sky-500/5 blur-[160px] pointer-events-none"
        aria-hidden="true"
      />

      {/* Main Container */}
      <div className="max-w-2xl w-full text-center relative z-10 py-8">
        {/* Brand Header */}
        <motion.div
          initial={{ opacity: 0, y: -16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="flex items-center justify-center gap-2.5 mb-6"
        >
          <div className="rounded-xl border border-blue-400/20 bg-gradient-to-br from-blue-600 to-indigo-600 p-2 shadow-[0_4px_16px_rgba(37,99,235,0.25)]">
            <HeartPulse size={20} className="text-white" />
          </div>
          <div className="text-left">
            <span className="text-sm font-extrabold tracking-tight text-[var(--text-primary)] block leading-tight">
              SGH Hub
            </span>
            <span className="text-[11px] font-bold uppercase tracking-widest text-blue-600 dark:text-blue-400 block leading-none mt-0.5">
              Performance Intelligence
            </span>
          </div>
        </motion.div>

        {/* Central Enterprise Card */}
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: 8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          transition={{ duration: 0.45, delay: 0.08 }}
          className="rounded-[32px] border border-[var(--border-light)] bg-[var(--bg-surface)]/90 backdrop-blur-xl p-8 sm:p-12 shadow-[0_24px_64px_rgba(15,23,42,0.12)] dark:shadow-[0_24px_64px_rgba(0,0,0,0.40)] text-left"
        >
          {/* Status Badge + Visual Emblem */}
          <div className="flex flex-col sm:flex-row items-center sm:items-start justify-between gap-4 mb-8">
            <div className="relative flex items-center justify-center">
              <div
                className={`absolute inset-0 rounded-2xl blur-lg pointer-events-none ${
                  isErrorMode
                    ? 'bg-rose-500/20'
                    : 'bg-blue-500/20'
                }`}
                aria-hidden="true"
              />
              <div
                className={`relative flex h-16 w-16 sm:h-20 sm:w-20 items-center justify-center rounded-2xl border shadow-inner ${
                  isErrorMode
                    ? 'border-rose-400/30 bg-gradient-to-br from-rose-500 to-amber-600 text-white'
                    : 'border-blue-400/30 bg-gradient-to-br from-blue-600 to-indigo-600 text-white'
                }`}
              >
                {isErrorMode ? (
                  <AlertTriangle className="size-8 sm:size-10 stroke-[1.75]" />
                ) : (
                  <Wrench className="size-8 sm:size-10 stroke-[1.75] animate-pulse" />
                )}
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-center sm:justify-end gap-2">
              <span
                className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold border tracking-wide uppercase ${
                  isErrorMode
                    ? 'border-rose-500/30 bg-rose-500/10 text-rose-600 dark:text-rose-400'
                    : 'border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400'
                }`}
              >
                <span
                  className={`size-2 rounded-full animate-ping ${
                    isErrorMode ? 'bg-rose-500' : 'bg-blue-500'
                  }`}
                />
                {isErrorMode ? 'Protected Safe Mode' : 'Scheduled Maintenance'}
              </span>

              {!isErrorMode && (
                <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-[var(--bg-sunken)] border border-[var(--border-light)] text-[var(--text-muted)]">
                  Est: {estimatedTime}
                </span>
              )}
            </div>
          </div>

          {/* Titles & Descriptions */}
          <div className="text-center sm:text-left mb-8">
            <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-[var(--text-primary)] mb-3">
              {displayTitle}
            </h1>
            <p className="text-sm sm:text-base font-normal text-[var(--text-secondary)] leading-relaxed max-w-xl">
              {displayDescription}
            </p>
          </div>

          {/* System Services Health Matrix */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-8">
            <div className="flex items-center gap-3 p-3.5 rounded-2xl bg-[var(--bg-sunken)]/60 border border-[var(--border-light)]">
              <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                <Database size={18} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[11px] font-bold text-[var(--text-muted)] uppercase tracking-wider">
                  Database
                </div>
                <div className="text-xs font-extrabold text-[var(--text-primary)] truncate flex items-center gap-1">
                  <span className="size-1.5 rounded-full bg-emerald-500 inline-block" />
                  Preserved & Intact
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3 p-3.5 rounded-2xl bg-[var(--bg-sunken)]/60 border border-[var(--border-light)]">
              <div className="p-2 rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400">
                <ShieldCheck size={18} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[11px] font-bold text-[var(--text-muted)] uppercase tracking-wider">
                  Security
                </div>
                <div className="text-xs font-extrabold text-[var(--text-primary)] truncate flex items-center gap-1">
                  <span className="size-1.5 rounded-full bg-blue-500 inline-block" />
                  Session Protected
                </div>
              </div>
            </div>

            <div className="flex items-center gap-3 p-3.5 rounded-2xl bg-[var(--bg-sunken)]/60 border border-[var(--border-light)]">
              <div className="p-2 rounded-xl bg-amber-500/10 text-amber-600 dark:text-amber-400">
                <Cpu size={18} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[11px] font-bold text-[var(--text-muted)] uppercase tracking-wider">
                  Services
                </div>
                <div className="text-xs font-extrabold text-[var(--text-primary)] truncate flex items-center gap-1">
                  <span className="size-1.5 rounded-full bg-amber-500 inline-block animate-pulse" />
                  {isErrorMode ? 'Standby Recovery' : 'Optimizing'}
                </div>
              </div>
            </div>
          </div>

          {/* Action Callouts */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 pt-2">
            <button
              type="button"
              onClick={handleRetry}
              disabled={isRetrying}
              className="flex min-h-12 flex-1 items-center justify-center gap-2 rounded-2xl bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 active:scale-[0.99] text-white text-sm font-extrabold shadow-[0_4px_16px_rgba(37,99,235,0.30)] transition-all disabled:opacity-75 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 cursor-pointer"
            >
              <RefreshCw
                size={16}
                className={isRetrying ? 'animate-spin' : ''}
              />
              <span>{isRetrying ? 'Reconnecting…' : 'Try Again / Reconnect'}</span>
            </button>

            <button
              type="button"
              onClick={handleHome}
              className="flex min-h-12 items-center justify-center gap-2 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] hover:bg-[var(--bg-sunken)] active:scale-[0.99] text-[var(--text-secondary)] hover:text-[var(--text-primary)] text-sm font-extrabold px-6 shadow-sm transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 cursor-pointer"
            >
              <Home size={16} />
              <span>Return Home</span>
            </button>

            <button
              type="button"
              onClick={handleCopyDiagnostics}
              title="Copy diagnostic information for IT support"
              className="flex min-h-12 items-center justify-center gap-2 rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] hover:bg-[var(--bg-sunken)] text-[var(--text-muted)] hover:text-[var(--text-primary)] px-4 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 cursor-pointer"
            >
              {copied ? (
                <>
                  <Check size={16} className="text-emerald-500" />
                  <span className="text-xs font-bold text-emerald-600 dark:text-emerald-400">Copied</span>
                </>
              ) : (
                <>
                  <Copy size={16} />
                  <span className="text-xs font-bold">Copy Log</span>
                </>
              )}
            </button>
          </div>

          {/* Progressive Disclosure: Technical Error Details */}
          {(error || componentStack) && (
            <div className="mt-8 pt-6 border-t border-[var(--border-light)]">
              <button
                type="button"
                onClick={() => setShowDiagnostics((prev) => !prev)}
                aria-expanded={showDiagnostics}
                aria-controls={diagnosticsId}
                className="flex w-full items-center justify-between text-xs font-bold text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors cursor-pointer"
              >
                <span>Diagnostic & Stack Information (For Support)</span>
                <ChevronDown
                  size={14}
                  className={`transition-transform duration-200 ${
                    showDiagnostics ? 'rotate-180' : ''
                  }`}
                />
              </button>

              <AnimatePresence>
                {showDiagnostics && (
                  <motion.div
                    id={diagnosticsId}
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.25 }}
                    className="overflow-hidden mt-3"
                  >
                    <div className="rounded-2xl bg-slate-950 text-slate-200 p-4 font-mono text-[11px] leading-relaxed border border-slate-800 shadow-inner overflow-x-auto max-h-64 select-text">
                      <div className="text-rose-400 font-bold mb-1">
                        {error?.name || 'Error'}: {error?.message || 'Unknown runtime error'}
                      </div>
                      {error?.stack && (
                        <pre className="text-slate-400 whitespace-pre-wrap break-all mt-2">
                          {error.stack}
                        </pre>
                      )}
                      {componentStack && (
                        <div className="mt-3 pt-2 border-t border-slate-800 text-slate-500">
                          <div className="text-[10px] font-bold uppercase text-slate-400 mb-1">
                            Component Trace:
                          </div>
                          <pre className="whitespace-pre-wrap break-all">
                            {componentStack}
                          </pre>
                        </div>
                      )}
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          )}
        </motion.div>

        {/* Footer Support Information */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.4, delay: 0.2 }}
          className="mt-6 flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-[var(--text-muted)] px-2"
        >
          <div className="flex items-center gap-1.5">
            <LifeBuoy size={14} className="text-blue-500" />
            <span>Need assistance? Contact IT Operations at</span>
            <a
              href="mailto:support@saudigerman.com"
              className="font-bold text-blue-600 dark:text-blue-400 hover:underline"
            >
              support@saudigerman.com
            </a>
          </div>

          <div className="font-extrabold tracking-widest uppercase text-[10px] text-[var(--text-faint)]">
            Saudi German Health · PMS 2.0
          </div>
        </motion.div>
      </div>
    </div>
  );
}
