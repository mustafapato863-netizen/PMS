import { Sparkles } from 'lucide-react';
import { useAiAvailability } from '../../../features/ai/aiAvailabilityContext';

/** Administration control. Visible while AI itself is hidden from every role, including Admin. */
export function AiFeatureSwitch() {
  const { enabled, ready, saving, error, setEnabled } = useAiAvailability();
  const on = ready && enabled;

  return (
    <section
      aria-labelledby="ai-feature-heading"
      className="flex flex-col gap-3 rounded-[16px] border border-[var(--exec-card-border)] bg-[var(--bg-surface)] p-4 shadow-[var(--exec-card-shadow)] sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex min-w-0 items-start gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-[var(--exec-tile-bg)] text-[var(--insights-accent)]">
          <Sparkles size={18} aria-hidden="true" />
        </span>
        <div className="min-w-0 space-y-0.5">
          <h2 id="ai-feature-heading" className="text-sm font-bold tracking-tight text-[var(--insights-heading)]">
            PMS AI
          </h2>
          <p className="text-[13px] leading-5 text-[var(--text-secondary)]">
            {on
              ? 'On for every signed-in role that already has access.'
              : 'Off for every user, including administrators. The assistant, Ask AI, and the PMS AI page stay hidden.'}
          </p>
          {error && <p className="text-xs font-semibold text-rose-600 dark:text-rose-400">{error}</p>}
        </div>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={on}
        aria-label="Enable PMS AI"
        disabled={!ready || saving}
        onClick={() => void setEnabled(!enabled).catch(() => undefined)}
        className={`inline-flex h-9 w-[4.5rem] shrink-0 items-center rounded-full p-1 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary)] disabled:opacity-60 ${
          on ? 'justify-end bg-[var(--sgh-cyan-primary,#00A3E0)]' : 'justify-start bg-[var(--bg-sunken)]'
        }`}
      >
        <span className="sr-only">{on ? 'On' : 'Off'}</span>
        <span className="grid h-7 min-w-7 place-items-center rounded-full bg-white px-1.5 text-[11px] font-bold text-slate-900 shadow-sm">
          {saving ? '…' : on ? 'On' : 'Off'}
        </span>
      </button>
    </section>
  );
}
