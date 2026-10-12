import type { EvaluationRevision } from '../evaluationSettings';

/**
 * Pure workflow model for the Evaluation settings panel. It reads values the container already has and
 * makes no requests. The disabled expressions in the container and the reasons below mirror each other.
 * Change one, change the other, and the unit tests will show it.
 */

export type EvaluationStatus =
  | 'loading'
  | 'blocked'
  | 'no_version'
  | 'draft_unsaved'
  | 'draft_saved'
  | 'draft_ready_to_approve'
  | 'approved'
  | 'approved_not_applied'
  | 'applied';

export type StatusTone = 'info' | 'warning' | 'good' | 'neutral';

export type StepId = 'edit' | 'preview' | 'approve' | 'apply';

export type StepState = 'done' | 'current' | 'upcoming' | 'locked';

/**
 * The one button that is primary for the current state. Applied has none: the workflow is finished, and Revise is a
 * secondary draft-management action. Open draft is primary only when the month has no version yet.
 */
export type PrimaryAction = 'save' | 'impact' | 'approve' | 'apply' | 'open_draft' | 'none';

export type ApplyMode = 'pending' | 'sync' | 'async' | 'unavailable';

export type WorkflowInput = {
  /** The period request is in flight. */
  loading: boolean;
  /** The scope is not supported for editing. */
  blocked: boolean;
  /** No period data is available: the request failed, or no scope is selected. */
  unavailable: boolean;
  hasVersion: boolean;
  periodStatus: string;
  versionId: string;
  revisions: readonly EvaluationRevision[];
  dirty: boolean;
  inputBlocked: boolean;
  weightTotalInvalid: boolean;
  unsupported: boolean;
  checksumMissing: boolean;
  versionDrift: boolean;
  /** The conflict message is present (the container's conflictText is not empty). */
  conflictPresent: boolean;
  approvalReady: boolean;
  /** The container's controlsLocked: a request is in flight, or the period is not loaded. */
  controlsLocked: boolean;
  applyMode: ApplyMode;
  blockEnqueue: boolean;
};

export type WorkflowStep = {
  id: StepId;
  label: string;
  state: StepState;
  reason?: string;
};

export type WorkflowState = {
  status: EvaluationStatus;
  label: string;
  tone: StatusTone;
  steps: WorkflowStep[];
  primaryAction: PrimaryAction;
  applyAvailable: boolean;
};

/** The reasons, as plain sentences. None repeats a notice the panel already shows word for word. */
export const WORKFLOW_REASONS = {
  wait: 'Wait for the current request to finish.',
  loading: 'Wait for this month to load.',
  notAvailable: 'This scope is not available for editing.',
  openDraft: 'Open a draft for this month first.',
  saveBeforePreview: 'Save your edits before previewing.',
  saveBeforeApprove: 'Save your edits before approving.',
  saveOrDiscardBeforeApply: 'Save or discard your edits before applying.',
  previewBeforeApprove: 'Run Impact preview before approving.',
  approveBeforeApply: 'Approve the draft before applying.',
  unsupported: 'A formula on this draft is not supported, so it cannot be saved or previewed.',
  fixInputs: 'Fix the highlighted values before saving.',
  totalWeight: 'Total weight must be 100% before saving.',
  checksum: 'This draft has no rules checksum yet, so saving is paused.',
  drift: 'A different version is showing for this month. Resolve it before saving.',
  conflict: 'This draft changed after you opened it. Resolve it before saving.',
  applyChecking: 'Checking whether apply is available.',
  applyUnavailable: 'Apply is unavailable right now. Retry the availability check.',
  applyOpen: 'A background apply for this month is open or still being checked.',
} as const;

const STATUS_PRESENTATION: Record<EvaluationStatus, { label: string; tone: StatusTone }> = {
  loading: { label: 'Loading…', tone: 'neutral' },
  blocked: { label: 'Not available', tone: 'warning' },
  no_version: { label: 'No version', tone: 'neutral' },
  draft_unsaved: { label: 'Unsaved edits', tone: 'warning' },
  draft_saved: { label: 'Draft saved', tone: 'info' },
  draft_ready_to_approve: { label: 'Ready to approve', tone: 'good' },
  approved: { label: 'Approved', tone: 'neutral' },
  approved_not_applied: { label: 'Approved, not applied', tone: 'warning' },
  applied: { label: 'Applied', tone: 'good' },
};

export const STEP_LABELS: Record<StepId, string> = {
  edit: 'Edit and save',
  preview: 'Preview impact',
  approve: 'Approve',
  apply: 'Apply',
};

export function applyAvailableFor(applyMode: ApplyMode): boolean {
  return applyMode === 'sync' || applyMode === 'async';
}

/**
 * Applied is claimed only when an active revision points at the approved version. An approved version with
 * other revisions on record, and none active for it, is "not applied". A revisions list that is empty proves
 * neither, because the backend also returns an empty list when the revision table is absent.
 */
function approvedStatus(input: WorkflowInput): EvaluationStatus {
  const activeForVersion = input.revisions.some((item) => item.status === 'active' && item.versionId === input.versionId);
  if (activeForVersion) return 'applied';
  if (input.revisions.length > 0) return 'approved_not_applied';
  return 'approved';
}

export function deriveStatus(input: WorkflowInput): EvaluationStatus {
  if (input.loading) return 'loading';
  if (input.blocked || input.unavailable) return 'blocked';
  if (!input.hasVersion) return 'no_version';
  if (input.periodStatus === 'approved') return approvedStatus(input);
  if (input.periodStatus === 'draft') {
    if (input.dirty) return 'draft_unsaved';
    if (input.approvalReady) return 'draft_ready_to_approve';
    return 'draft_saved';
  }
  return 'no_version';
}

/** Mirrors the Save draft disabled expression, after its status and version checks. */
export function saveBlocker(input: WorkflowInput): string | undefined {
  if (input.controlsLocked) return WORKFLOW_REASONS.wait;
  if (input.unsupported) return WORKFLOW_REASONS.unsupported;
  if (input.inputBlocked) return WORKFLOW_REASONS.fixInputs;
  if (input.weightTotalInvalid) return WORKFLOW_REASONS.totalWeight;
  if (input.checksumMissing) return WORKFLOW_REASONS.checksum;
  if (input.versionDrift) return WORKFLOW_REASONS.drift;
  if (input.conflictPresent) return WORKFLOW_REASONS.conflict;
  return undefined;
}

/** Mirrors the Impact preview disabled expression. */
export function previewBlocker(input: WorkflowInput): string | undefined {
  if (input.controlsLocked) return WORKFLOW_REASONS.wait;
  if (input.dirty) return WORKFLOW_REASONS.saveBeforePreview;
  if (input.unsupported) return WORKFLOW_REASONS.unsupported;
  return undefined;
}

/** Mirrors the Approve disabled expression. */
export function approveBlocker(input: WorkflowInput): string | undefined {
  if (input.controlsLocked) return WORKFLOW_REASONS.wait;
  if (input.dirty) return WORKFLOW_REASONS.saveBeforeApprove;
  if (!input.approvalReady) return WORKFLOW_REASONS.previewBeforeApprove;
  return undefined;
}

/** Mirrors the Apply disabled expression, plus the apply-mode condition that decides whether the button is rendered. */
export function applyBlocker(input: WorkflowInput): string | undefined {
  if (input.applyMode === 'pending') return WORKFLOW_REASONS.applyChecking;
  if (input.applyMode === 'unavailable') return WORKFLOW_REASONS.applyUnavailable;
  if (input.controlsLocked) return WORKFLOW_REASONS.wait;
  if (input.dirty) return WORKFLOW_REASONS.saveOrDiscardBeforeApply;
  if (input.blockEnqueue) return WORKFLOW_REASONS.applyOpen;
  return undefined;
}

function step(id: StepId, state: StepState, reason?: string): WorkflowStep {
  return reason === undefined ? { id, label: STEP_LABELS[id], state } : { id, label: STEP_LABELS[id], state, reason };
}

/** A later step waits on its prerequisites: locked, with the first reason that applies. */
function buildSteps(status: EvaluationStatus, input: WorkflowInput): WorkflowStep[] {
  switch (status) {
    case 'loading':
      return [step('edit', 'upcoming'), step('preview', 'upcoming'), step('approve', 'upcoming'), step('apply', 'upcoming')];
    case 'blocked':
      return [
        step('edit', 'locked', WORKFLOW_REASONS.notAvailable),
        step('preview', 'locked', WORKFLOW_REASONS.notAvailable),
        step('approve', 'locked', WORKFLOW_REASONS.notAvailable),
        step('apply', 'locked', WORKFLOW_REASONS.notAvailable),
      ];
    case 'no_version':
      return [
        step('edit', 'current'),
        step('preview', 'locked', WORKFLOW_REASONS.openDraft),
        step('approve', 'locked', WORKFLOW_REASONS.openDraft),
        step('apply', 'locked', WORKFLOW_REASONS.approveBeforeApply),
      ];
    case 'draft_unsaved':
      return [
        step('edit', 'current', saveBlocker(input)),
        step('preview', 'locked', previewBlocker(input) ?? WORKFLOW_REASONS.saveBeforePreview),
        step('approve', 'locked', approveBlocker(input) ?? WORKFLOW_REASONS.saveBeforeApprove),
        step('apply', 'locked', WORKFLOW_REASONS.approveBeforeApply),
      ];
    case 'draft_saved':
      return [
        step('edit', 'done'),
        step('preview', 'current', previewBlocker(input)),
        step('approve', 'locked', WORKFLOW_REASONS.previewBeforeApprove),
        step('apply', 'locked', WORKFLOW_REASONS.approveBeforeApply),
      ];
    case 'draft_ready_to_approve':
      return [
        step('edit', 'done'),
        step('preview', 'done'),
        step('approve', 'current', approveBlocker(input)),
        step('apply', 'locked', WORKFLOW_REASONS.approveBeforeApply),
      ];
    case 'approved':
    case 'approved_not_applied':
      return [
        step('edit', 'done'),
        step('preview', 'done'),
        step('approve', 'done'),
        step('apply', 'current', applyBlocker(input)),
      ];
    case 'applied':
      return [step('edit', 'done'), step('preview', 'done'), step('approve', 'done'), step('apply', 'done')];
  }
}

function primaryFor(status: EvaluationStatus, applyAvailable: boolean): PrimaryAction {
  switch (status) {
    case 'loading':
    case 'blocked':
      return 'none';
    case 'no_version':
      return 'open_draft';
    case 'draft_unsaved':
      return 'save';
    case 'draft_saved':
      return 'impact';
    case 'draft_ready_to_approve':
      return 'approve';
    case 'approved':
    case 'approved_not_applied':
      return applyAvailable ? 'apply' : 'none';
    case 'applied':
      return 'none';
  }
}

export function deriveWorkflowState(input: WorkflowInput): WorkflowState {
  const status = deriveStatus(input);
  const applyAvailable = applyAvailableFor(input.applyMode);
  const presentation = STATUS_PRESENTATION[status];
  return {
    status,
    label: presentation.label,
    tone: presentation.tone,
    steps: buildSteps(status, input),
    primaryAction: primaryFor(status, applyAvailable),
    applyAvailable,
  };
}
