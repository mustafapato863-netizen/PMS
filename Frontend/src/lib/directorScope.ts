import type { User } from '../types';

type ScopeUser = Pick<User, 'accessible_branches' | 'accessible_regions' | 'accessible_functions'> | null | undefined;

/** Presentation of existing server grants, never a source of authorization. */
export function directorScope(role: string | null | undefined, user: ScopeUser) {
  const clean = (values?: string[]) => [...new Set((values ?? []).map((value) => value.trim()).filter(Boolean))];
  const branches = clean(user?.accessible_branches).map((value) => value.toLowerCase());
  const regions = clean(user?.accessible_regions);
  const functions = clean(user?.accessible_functions);
  const branchLocked = role === 'Branch Director';
  const regionLocked = role === 'Regional Manager';
  const functionLocked = role === 'Function Director';
  // Multiple assignments remain an aggregate of the server-authorized scope.
  // Never pick the first grant and silently discard the others.
  return {
    branchLocked, regionLocked, functionLocked,
    branch: branchLocked && branches.length === 1 ? branches[0] : undefined,
    region: regionLocked && regions.length === 1 ? regions[0] : undefined,
    branches, regions, functions,
    branchLabel: branches.length ? branches.join(', ') : 'No branch assigned',
    regionLabel: regions.length ? regions.join(', ') : 'No region assigned',
  };
}
