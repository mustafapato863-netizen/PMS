import { ShieldCheck } from 'lucide-react';
import type { User } from '../../../types';
import type { ExecutiveScope } from '../../../features/executive/types';
import { USER_BRANCH_OPTIONS, hasAllTeamsScope } from '../../../lib/access';

const branchLabel = (value: string) => USER_BRANCH_OPTIONS.find((branch) => branch.key === value.toLowerCase())?.label ?? value;
const assignments = (values?: string[], format: (value: string) => string = (value) => value) =>
  [...new Set((values ?? []).map((value) => value.trim()).filter(Boolean))].map(format).join(', ');

/** Explains existing grants and server-composed scope; never changes authorization. */
export default function SummaryScopeWelcome({ role, user, scope }: {
  role: string;
  user: User | null;
  scope?: ExecutiveScope;
}) {
  let description: string;
  if (role === 'Branch Director') {
    const branches = assignments(user?.accessible_branches, branchLabel);
    description = branches
      ? `Your access covers teams and employees in your assigned branches: ${branches}.`
      : 'Your view is limited to your assigned branches. Ask an admin to confirm your branch assignment.';
  } else if (role === 'Regional Manager') {
    const regions = assignments(user?.accessible_regions);
    description = regions
      ? `Your access covers teams and employees in your assigned regions: ${regions}.`
      : 'Your view is limited to your assigned regions. Ask an admin to confirm your region assignment.';
  } else if (role === 'Function Director' || role === 'Function Viewer') {
    const functions = assignments(user?.accessible_functions);
    description = functions
      ? `Your access covers your assigned functions (${functions}) and their teams across branches.`
      : 'Your view is limited to your assigned functions. Ask an admin to confirm your function assignment.';
  } else if (role === 'Manager') {
    const teams = assignments(user?.accessible_teams);
    description = `Your access covers your assigned teams${teams ? ` (${teams})` : ''} and their employees.`;
  } else if (role === 'Employee' || role === 'Agent' || user?.is_self_only) {
    description = 'This summary represents your own performance only.';
  } else {
    description = hasAllTeamsScope(role, user)
      ? 'Your access covers company-wide performance across all authorized regions, branches, functions and teams.'
      : 'This summary includes only the performance data you are authorized to view.';
  }

  const selectedScope = scope ? [
    scope.region && scope.region !== 'All' ? `Region: ${scope.region}` : null,
    scope.branch && scope.branch !== 'All' ? `Branch: ${branchLabel(scope.branch)}` : null,
    scope.function && scope.function !== 'All' ? `Function: ${scope.function}` : null,
    scope.team && scope.team !== 'All' ? `Team: ${scope.team}` : null,
    scope.position && scope.position !== 'All' ? `Role: ${scope.position}` : null,
    scope.performance_level && scope.performance_level !== 'All' ? `Level: ${scope.performance_level}` : 'All performance levels',
  ].filter(Boolean).join(' · ') : null;

  return (
    <div aria-label="About your performance scope" className="mt-2 flex items-start gap-3 rounded-xl border border-[var(--insights-card-border)] bg-[var(--bg-surface)] px-4 py-3 text-sm">
      <ShieldCheck aria-hidden="true" size={20} className="mt-0.5 shrink-0 text-[var(--insights-accent)]" />
      <div className="min-w-0">
        <p className="font-semibold text-[var(--insights-heading)]">Welcome{user?.name?.trim() ? `, ${user.name.trim()}` : ''}.</p>
        <p className="mt-1 leading-relaxed text-[var(--text-secondary)]">{description}</p>
        {selectedScope && <p className="mt-1 text-xs leading-relaxed text-[var(--text-muted)]">Showing: {selectedScope}. Scores and comparisons reflect this scope and the reporting period above.</p>}
      </div>
    </div>
  );
}
