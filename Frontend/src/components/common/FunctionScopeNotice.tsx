import { Lock } from 'lucide-react';
import { Link } from 'react-router-dom';
import { functionSlug } from '../../features/executive/functions';
import type { ExecutiveFunction } from '../../features/executive/types';

/** Shown to a Function Viewer who opens a team / employee outside their functions. */
export default function FunctionScopeNotice({ subject, allowed }: { subject: string; allowed: ExecutiveFunction[] }) {
  return (
    <div role="alert" data-testid="function-scope-notice" className="glass-panel mx-auto mt-[24px] max-w-[560px] rounded-xl p-10 text-center">
      <Lock size={28} className="mx-auto mb-3 text-[var(--text-muted)]" aria-hidden="true" />
      <h3 className="text-lg font-bold text-[var(--text-primary)]">Not in your functions</h3>
      <p className="mt-1 text-sm text-[var(--text-secondary)]">
        {subject} is outside {allowed.length ? allowed.join(', ') : 'your assigned functions'}. Function Viewer access is limited to the functions assigned to your account.
      </p>
      {allowed[0] && (
        <Link to={`/function-summary/${functionSlug(allowed[0])}`} className="mt-4 inline-block text-sm font-semibold text-[var(--insights-accent-text)] hover:underline">
          Back to Function Summary
        </Link>
      )}
    </div>
  );
}
