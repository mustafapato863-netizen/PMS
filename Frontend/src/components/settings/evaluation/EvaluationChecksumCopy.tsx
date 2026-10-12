import { useState } from 'react';
import { Check, Copy } from 'lucide-react';

export type ChecksumCopyProps = {
  /** The full checksum. Copied as-is and shown only if the copy fails. */
  value: string;
  /** The characters shown by default. */
  short: string;
  /** The version the checksum belongs to, for the button's accessible name. */
  subject: string;
};

type CopyState = 'idle' | 'copied' | 'failed';

/**
 * A short checksum with a button that copies the full value. If the browser refuses the copy, the status says so and
 * shows the full value once, so it can still be read. This is a status message, not an alert.
 */
export function ChecksumCopy({ value, short, subject }: ChecksumCopyProps) {
  const [state, setState] = useState<CopyState>('idle');

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setState('copied');
    } catch {
      setState('failed');
    }
  };

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs text-[var(--text-secondary)]">
      <span>Checksum <code className="font-mono text-[var(--text-primary)]">{short}</code></span>
      <button
        type="button"
        onClick={() => void copy()}
        aria-label={`Copy checksum for ${subject}`}
        className="inline-flex min-h-[44px] items-center gap-1 rounded-lg border border-[var(--border-light)] px-2 font-bold text-[var(--text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary,#00A3E0)] lg:!min-h-[32px]"
      >
        {state === 'copied' ? <Check size={12} aria-hidden="true" /> : <Copy size={12} aria-hidden="true" />}
        Copy checksum
      </button>
      {state === 'copied' && <span role="status" className="font-semibold text-emerald-700 dark:text-emerald-300">Copied</span>}
      {state === 'failed' && <span role="status" className="min-w-0 break-all font-semibold text-amber-800 dark:text-amber-300">Copy failed. Full checksum: <code className="font-mono">{value}</code></span>}
    </div>
  );
}
