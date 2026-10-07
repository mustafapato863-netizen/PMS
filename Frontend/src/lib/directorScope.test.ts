import { describe, expect, it } from 'vitest';
import { directorScope } from './directorScope';

describe('director filter scope', () => {
  it('locks the grant dimension, not unrelated filters', () => {
    expect(directorScope('Branch Director', { accessible_branches: ['Dubai'] })).toMatchObject({ branchLocked: true, branch: 'dubai', regionLocked: false, functionLocked: false });
    expect(directorScope('Regional Manager', { accessible_regions: ['UAE'] })).toMatchObject({ regionLocked: true, region: 'UAE', branchLocked: false });
    expect(directorScope('Function Director', { accessible_functions: ['RCM'] })).toMatchObject({ functionLocked: true, functions: ['RCM'], branchLocked: false });
  });
  it('does not narrow multiple grants to the first one or mislabel an empty scope as all', () => {
    expect(directorScope('Branch Director', { accessible_branches: ['Dubai', 'Sharjah'] })).toMatchObject({ branch: undefined, branchLabel: 'dubai, sharjah' });
    expect(directorScope('Regional Manager', null)).toMatchObject({ regionLocked: true, region: undefined, regionLabel: 'No region assigned' });
    expect(directorScope('Admin', { accessible_branches: ['dubai'] }).branchLocked).toBe(false);
  });
});
