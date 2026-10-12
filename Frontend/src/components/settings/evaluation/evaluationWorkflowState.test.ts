import { describe, expect, it } from 'vitest';
import type { EvaluationRevision } from '../evaluationSettings';
import {
  WORKFLOW_REASONS,
  applyBlocker,
  approveBlocker,
  deriveStatus,
  deriveWorkflowState,
  previewBlocker,
  saveBlocker,
  type WorkflowInput,
} from './evaluationWorkflowState';

/** A healthy, saved draft that is not yet previewed. Each test overrides only what it is about. */
function input(overrides: Partial<WorkflowInput> = {}): WorkflowInput {
  return {
    loading: false,
    blocked: false,
    unavailable: false,
    hasVersion: true,
    periodStatus: 'draft',
    versionId: 'draft-1',
    revisions: [],
    dirty: false,
    inputBlocked: false,
    weightTotalInvalid: false,
    unsupported: false,
    checksumMissing: false,
    versionDrift: false,
    conflictPresent: false,
    approvalReady: false,
    controlsLocked: false,
    applyMode: 'sync',
    blockEnqueue: false,
    ...overrides,
  };
}

function revision(overrides: Partial<EvaluationRevision> = {}): EvaluationRevision {
  return {
    id: 'revision-1',
    versionId: 'approved-1',
    status: 'active',
    createdAt: '2026-08-01T00:00:00Z',
    affectedCount: 2,
    canRollback: true,
    ...overrides,
  };
}

const APPROVED = { periodStatus: 'approved', versionId: 'approved-1' } as const;

describe('deriveStatus', () => {
  it.each<[string, Partial<WorkflowInput>, string]>([
    ['loading', { loading: true }, 'loading'],
    ['blocked scope', { blocked: true }, 'blocked'],
    ['no data available', { unavailable: true }, 'blocked'],
    ['no version for the month', { hasVersion: false, versionId: '' }, 'no_version'],
    ['unsaved edits', { dirty: true }, 'draft_unsaved'],
    ['saved draft without proof', {}, 'draft_saved'],
    ['saved draft with matching proof', { approvalReady: true }, 'draft_ready_to_approve'],
    ['approved, no revisions on record', APPROVED, 'approved'],
    ['approved, active revision for it', { ...APPROVED, revisions: [revision()] }, 'applied'],
    ['approved, only another version active', { ...APPROVED, revisions: [revision({ versionId: 'approved-0' })] }, 'approved_not_applied'],
    ['approved, its revision rolled back', { ...APPROVED, revisions: [revision({ status: 'rolled_back' })] }, 'approved_not_applied'],
  ])('reports %s as %s', (_name, overrides, expected) => {
    expect(deriveStatus(input(overrides))).toBe(expected);
  });
});

describe('status presentation', () => {
  it.each<[Partial<WorkflowInput>, string, string]>([
    [{ loading: true }, 'Loading…', 'neutral'],
    [{ blocked: true }, 'Not available', 'warning'],
    [{ hasVersion: false, versionId: '' }, 'No version', 'neutral'],
    [{ dirty: true }, 'Unsaved edits', 'warning'],
    [{}, 'Draft saved', 'info'],
    [{ approvalReady: true }, 'Ready to approve', 'good'],
    [APPROVED, 'Approved', 'neutral'],
    [{ ...APPROVED, revisions: [revision({ versionId: 'approved-0' })] }, 'Approved, not applied', 'warning'],
    [{ ...APPROVED, revisions: [revision()] }, 'Applied', 'good'],
  ])('shows the right label and tone for %j', (overrides, label, tone) => {
    const state = deriveWorkflowState(input(overrides));
    expect(state.label).toBe(label);
    expect(state.tone).toBe(tone);
  });
});

describe('never claims applied without proof', () => {
  it('does not say applied for an approved version with no revisions on record', () => {
    expect(deriveWorkflowState(input({ ...APPROVED })).status).not.toBe('applied');
  });

  it('does not say applied when the only active revision belongs to another version', () => {
    const state = deriveWorkflowState(input({ ...APPROVED, revisions: [revision({ versionId: 'approved-0' })] }));
    expect(state.status).toBe('approved_not_applied');
  });

  it('does not say applied when the matching revision was rolled back', () => {
    const state = deriveWorkflowState(input({ ...APPROVED, revisions: [revision({ status: 'rolled_back' })] }));
    expect(state.status).not.toBe('applied');
  });

  it('says applied only when an active revision points at the approved version, for every shape of revisions', () => {
    const shapes: EvaluationRevision[][] = [
      [],
      [revision({ status: 'superseded' })],
      [revision({ status: 'rolled_back' })],
      [revision({ versionId: 'approved-0' })],
      [revision({ versionId: 'approved-0' }), revision({ id: 'revision-2' })],
      [revision()],
      [revision({ status: 'superseded' }), revision({ id: 'revision-2' })],
    ];
    for (const revisions of shapes) {
      const proven = revisions.some((item) => item.status === 'active' && item.versionId === 'approved-1');
      const status = deriveStatus(input({ ...APPROVED, revisions }));
      expect(status === 'applied', JSON.stringify(revisions)).toBe(proven);
    }
  });
});

describe('four-step indicator', () => {
  const stepStates = (state: ReturnType<typeof deriveWorkflowState>) => state.steps.map((item) => item.state);

  it('shows a fresh draft as edit done, preview current, and later steps locked with the reason', () => {
    const state = deriveWorkflowState(input());
    expect(stepStates(state)).toEqual(['done', 'current', 'locked', 'locked']);
    expect(state.steps[2]).toMatchObject({ id: 'approve', reason: WORKFLOW_REASONS.previewBeforeApprove });
    expect(state.steps[3]).toMatchObject({ id: 'apply', reason: WORKFLOW_REASONS.approveBeforeApply });
  });

  it('shows unsaved edits as edit current, with later locks that name the save', () => {
    const state = deriveWorkflowState(input({ dirty: true }));
    expect(stepStates(state)).toEqual(['current', 'locked', 'locked', 'locked']);
    expect(state.steps[1].reason).toBe(WORKFLOW_REASONS.saveBeforePreview);
    expect(state.steps[2].reason).toBe(WORKFLOW_REASONS.saveBeforeApprove);
  });

  it('shows a draft with matching proof as approve current, with apply locked', () => {
    const state = deriveWorkflowState(input({ approvalReady: true }));
    expect(stepStates(state)).toEqual(['done', 'done', 'current', 'locked']);
  });

  it('shows an approved, applied month with every step done', () => {
    expect(stepStates(deriveWorkflowState(input({ ...APPROVED, revisions: [revision()] })))).toEqual(['done', 'done', 'done', 'done']);
  });

  it('shows an approved month not yet applied with apply current', () => {
    const state = deriveWorkflowState(input({ ...APPROVED }));
    expect(stepStates(state)).toEqual(['done', 'done', 'done', 'current']);
    expect(state.steps[3].reason).toBeUndefined();
  });

  it('gives apply the reason it is not available in this environment', () => {
    expect(deriveWorkflowState(input({ ...APPROVED, applyMode: 'unavailable' })).steps[3]).toMatchObject({
      state: 'current',
      reason: WORKFLOW_REASONS.applyUnavailable,
    });
    expect(deriveWorkflowState(input({ ...APPROVED, applyMode: 'pending' })).steps[3].reason).toBe(WORKFLOW_REASONS.applyChecking);
  });

  it('locks every step for a blocked scope, and shows steps as upcoming while the month loads', () => {
    expect(stepStates(deriveWorkflowState(input({ blocked: true })))).toEqual(['locked', 'locked', 'locked', 'locked']);
    expect(stepStates(deriveWorkflowState(input({ loading: true })))).toEqual(['upcoming', 'upcoming', 'upcoming', 'upcoming']);
  });

  it('asks for a draft first when the month has no version', () => {
    const state = deriveWorkflowState(input({ hasVersion: false, versionId: '' }));
    expect(stepStates(state)).toEqual(['current', 'locked', 'locked', 'locked']);
    expect(state.steps[1].reason).toBe(WORKFLOW_REASONS.openDraft);
  });

  it('keeps the apply step locked until the month is approved', () => {
    const state = deriveWorkflowState(input({ dirty: true }));
    expect(state.steps[3]).toMatchObject({ state: 'locked', reason: WORKFLOW_REASONS.approveBeforeApply });
  });
});

describe('lock reasons name the condition in plain words', () => {
  it('names an unsupported formula, a missing checksum and version drift each with its own reason', () => {
    expect(saveBlocker(input({ unsupported: true }))).toBe(WORKFLOW_REASONS.unsupported);
    expect(saveBlocker(input({ checksumMissing: true }))).toBe(WORKFLOW_REASONS.checksum);
    expect(saveBlocker(input({ versionDrift: true }))).toBe(WORKFLOW_REASONS.drift);
  });

  it('names the total weight rule the way the user sees it', () => {
    expect(saveBlocker(input({ weightTotalInvalid: true }))).toBe('Total weight must be 100% before saving.');
  });

  it('names the approval prerequisites in the order the user meets them', () => {
    expect(approveBlocker(input({ dirty: true }))).toBe('Save your edits before approving.');
    expect(approveBlocker(input({ approvalReady: false }))).toBe('Run Impact preview before approving.');
  });

  it('names the approve prerequisite for apply', () => {
    expect(deriveWorkflowState(input()).steps[3].reason).toBe('Approve the draft before applying.');
  });
});

describe('exactly one primary action for each reachable combination', () => {
  const expectedPrimary: Array<[string, Partial<WorkflowInput>, string]> = [
    ['loading', { loading: true }, 'none'],
    ['blocked', { blocked: true }, 'none'],
    ['no version', { hasVersion: false, versionId: '' }, 'open_draft'],
    ['unsaved edits', { dirty: true }, 'save'],
    ['saved draft', {}, 'impact'],
    ['ready to approve', { approvalReady: true }, 'approve'],
    ['approved, not applied', APPROVED, 'apply'],
    ['approved, applied', { ...APPROVED, revisions: [revision()] }, 'none'],
  ];

  it.each(expectedPrimary)('makes %s the %s action', (_name, overrides, primary) => {
    expect(deriveWorkflowState(input(overrides)).primaryAction).toBe(primary);
  });

  it('has no primary action once the month is applied, so nothing invites a new edit', () => {
    const state = deriveWorkflowState(input({ ...APPROVED, revisions: [revision()] }));
    expect(state.status).toBe('applied');
    expect(state.primaryAction).toBe('none');
    expect(state.steps.every((step) => step.state === 'done')).toBe(true);
  });

  it('never makes apply primary when apply is not available here', () => {
    for (const applyMode of ['pending', 'unavailable'] as const) {
      expect(deriveWorkflowState(input({ ...APPROVED, applyMode })).primaryAction).toBe('none');
    }
  });

  it('always picks one action from the known set, over every input combination', () => {
    const known = new Set(['save', 'impact', 'approve', 'apply', 'open_draft', 'none']);
    const flags = [false, true];
    for (const loading of flags) for (const dirty of flags) for (const approvalReady of flags) for (const controlsLocked of flags) {
      for (const periodStatus of ['draft', 'approved']) for (const applyMode of ['sync', 'async', 'pending', 'unavailable'] as const) {
        const state = deriveWorkflowState(input({ loading, dirty, approvalReady, controlsLocked, periodStatus, applyMode, versionId: 'approved-1' }));
        expect(known.has(state.primaryAction)).toBe(true);
      }
    }
  });
});

/**
 * The reasons mirror the container's disabled expressions. For every combination of the inputs that feed them,
 * a reason is present exactly when the button would be disabled.
 */
describe('reasons mirror the disabled expressions', () => {
  const flags = [false, true];

  it('Save draft: a reason exists exactly when the container disables it', () => {
    for (const [controlsLocked, unsupported, inputBlocked, weightTotalInvalid, checksumMissing, versionDrift, conflictPresent] of
      Array.from({ length: 128 }, (_, bits) => [1, 2, 4, 8, 16, 32, 64].map((bit) => (bits & bit) !== 0))) {
      // Container: controlsLocked || !versionId || status !== 'draft' || unsupported || inputBlocked || weightTotalInvalid || checksumMissing || versionDrift || Boolean(conflictText)
      const disabled = controlsLocked || unsupported || inputBlocked || weightTotalInvalid || checksumMissing || versionDrift || conflictPresent;
      const row = input({ controlsLocked, unsupported, inputBlocked, weightTotalInvalid, checksumMissing, versionDrift, conflictPresent });
      expect(Boolean(saveBlocker(row))).toBe(disabled);
    }
  });

  it('Impact preview: a reason exists exactly when the container disables it', () => {
    for (const controlsLocked of flags) for (const dirty of flags) for (const unsupported of flags) {
      // Container: controlsLocked || !versionId || status !== 'draft' || dirty || unsupported
      const disabled = controlsLocked || dirty || unsupported;
      expect(Boolean(previewBlocker(input({ controlsLocked, dirty, unsupported })))).toBe(disabled);
    }
  });

  it('Approve: a reason exists exactly when the container disables it', () => {
    for (const controlsLocked of flags) for (const dirty of flags) for (const approvalReady of flags) {
      // Container: controlsLocked || !versionId || dirty || status !== 'draft' || !approvalReady
      const disabled = controlsLocked || dirty || !approvalReady;
      expect(Boolean(approveBlocker(input({ controlsLocked, dirty, approvalReady })))).toBe(disabled);
    }
  });

  it('Apply: a reason exists exactly when the container disables it, for an available apply', () => {
    for (const controlsLocked of flags) for (const dirty of flags) for (const blockEnqueue of flags) {
      // Container: controlsLocked || status !== 'approved' || dirty || blockEnqueue (rendered only in sync or async mode)
      const disabled = controlsLocked || dirty || blockEnqueue;
      expect(Boolean(applyBlocker(input({ ...APPROVED, applyMode: 'sync', controlsLocked, dirty, blockEnqueue })))).toBe(disabled);
    }
  });
});
