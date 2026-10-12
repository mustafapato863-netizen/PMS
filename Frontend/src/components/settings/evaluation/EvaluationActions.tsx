import { Check, Copy, Save, type LucideIcon } from 'lucide-react';
import type { PrimaryAction } from './evaluationWorkflowState';

export type ActionKey = 'save' | 'impact' | 'approve' | 'apply' | 'new_draft' | 'copy_previous' | 'revise' | 'adopt' | 'delete';

/** Workflow buttons, in step order. They sit directly under the stepper, so the indicator and the buttons read as one unit. */
const WORKFLOW_ORDER: readonly ActionKey[] = ['save', 'impact', 'approve', 'apply'];

/** Draft management: opening, copying, revising, switching settings and deleting a draft. Kept apart from the workflow. */
const MANAGEMENT_ORDER: readonly ActionKey[] = ['new_draft', 'copy_previous', 'revise', 'adopt', 'delete'];

const LABEL: Record<ActionKey, string> = {
  save: 'Save draft',
  impact: 'Impact preview',
  approve: 'Approve',
  apply: 'Apply',
  new_draft: 'New draft',
  copy_previous: 'Copy previous month',
  revise: 'Revise this month',
  adopt: 'Use original upload settings',
  delete: 'Delete draft',
};

const ICON: Partial<Record<ActionKey, LucideIcon>> = {
  copy_previous: Copy,
  save: Save,
  approve: Check,
};

/** The one button that gets the primary style for the current state. Delete is always danger and never primary. */
const PRIMARY_ACTION: Partial<Record<PrimaryAction, ActionKey>> = {
  open_draft: 'new_draft',
  save: 'save',
  impact: 'impact',
  approve: 'approve',
  apply: 'apply',
};

const BUTTON_BASE = 'inline-flex items-center gap-1 rounded-xl px-3 py-2 text-xs font-bold focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--sgh-cyan-primary,#00A3E0)] disabled:cursor-not-allowed disabled:opacity-50';

const VARIANT_CLASS = {
  primary: 'bg-blue-600 text-white',
  secondary: 'border border-[var(--border-light)]',
  danger: 'border border-red-500/30 text-red-600',
} as const;

export type EvaluationActionsProps = {
  primary: PrimaryAction;
  approved: boolean;
  monthApproved: boolean;
  canDeleteDraft: boolean;
  applyVisible: boolean;
  adoptVisible: boolean;
  /** Each value is the container's disabled expression for that button, unchanged. */
  disabled: Record<ActionKey, boolean>;
  onAction: Record<ActionKey, () => void>;
};

/**
 * The month's action buttons, in two groups. Which buttons show follows the month's state; which are disabled is
 * decided by the container, so the expressions stay where they were.
 */
export function EvaluationActions({ primary, approved, monthApproved, canDeleteDraft, applyVisible, adoptVisible, disabled, onAction }: EvaluationActionsProps) {
  const visible: Record<ActionKey, boolean> = {
    save: !approved,
    impact: !approved,
    approve: !approved,
    apply: applyVisible,
    new_draft: !monthApproved,
    copy_previous: !monthApproved,
    revise: approved,
    adopt: adoptVisible,
    delete: canDeleteDraft,
  };

  const renderButton = (key: ActionKey) => {
    const variant = key === 'delete' ? 'danger' : PRIMARY_ACTION[primary] === key ? 'primary' : 'secondary';
    const Icon = ICON[key];
    return (
      <button
        key={key}
        type="button"
        data-variant={variant}
        onClick={onAction[key]}
        disabled={disabled[key]}
        className={`${BUTTON_BASE} ${VARIANT_CLASS[variant]}`}
      >
        {Icon && <Icon size={14} aria-hidden="true" />}
        {LABEL[key]}
      </button>
    );
  };

  const workflowKeys = WORKFLOW_ORDER.filter((key) => visible[key]);
  const managementKeys = MANAGEMENT_ORDER.filter((key) => visible[key]);

  return (
    <>
      {workflowKeys.length > 0 && <div role="group" aria-label="Workflow actions" className="flex flex-wrap gap-2">
        {workflowKeys.map(renderButton)}
      </div>}
      {managementKeys.length > 0 && <div role="group" aria-label="Draft management" className="flex flex-wrap items-center gap-2 border-t border-[var(--border-light)] pt-3">
        <p className="w-full text-xs font-bold text-[var(--text-muted)]">Draft management</p>
        {managementKeys.map(renderButton)}
      </div>}
    </>
  );
}
