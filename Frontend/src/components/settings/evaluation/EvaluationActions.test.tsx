import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { EvaluationActions, type ActionKey, type EvaluationActionsProps } from './EvaluationActions';

/** Builds a record with every action key, so a missing key is a type error rather than a silent gap. */
function everyAction<T>(make: () => T): Record<ActionKey, T> {
  return {
    save: make(),
    impact: make(),
    approve: make(),
    apply: make(),
    new_draft: make(),
    copy_previous: make(),
    revise: make(),
    adopt: make(),
    delete: make(),
  };
}

function props(overrides: Partial<EvaluationActionsProps> = {}): EvaluationActionsProps {
  return {
    primary: 'save',
    approved: false,
    monthApproved: false,
    canDeleteDraft: true,
    applyVisible: false,
    adoptVisible: true,
    disabled: everyAction(() => false),
    onAction: everyAction(() => vi.fn<() => void>()),
    ...overrides,
  };
}

function buttonNames(group: HTMLElement) {
  return within(group).getAllByRole('button').map((button) => button.textContent);
}

function primaryNames() {
  return screen.getAllByRole('button')
    .filter((button) => button.getAttribute('data-variant') === 'primary')
    .map((button) => button.textContent);
}

describe('EvaluationActions groups', () => {
  it('puts Save, Impact, Approve in step order in the workflow group, with Save draft as the only primary', () => {
    render(<EvaluationActions {...props({ primary: 'save' })} />);
    const workflow = screen.getByRole('group', { name: 'Workflow actions' });
    expect(buttonNames(workflow)).toEqual(['Save draft', 'Impact preview', 'Approve']);
    expect(primaryNames()).toEqual(['Save draft']);
  });

  it('keeps the draft management buttons in their own labelled group, away from the workflow group', () => {
    render(<EvaluationActions {...props({ primary: 'save' })} />);
    const management = screen.getByRole('group', { name: 'Draft management' });
    expect(within(management).getByText('Draft management')).toBeInTheDocument();
    expect(buttonNames(management)).toEqual(['New draft', 'Copy previous month', 'Use original upload settings', 'Delete draft']);
    const workflow = screen.getByRole('group', { name: 'Workflow actions' });
    expect(within(workflow).queryByRole('button', { name: 'Delete draft' })).not.toBeInTheDocument();
    expect(within(workflow).queryByRole('button', { name: 'New draft' })).not.toBeInTheDocument();
  });

  it('marks Delete draft as danger and never as primary', () => {
    render(<EvaluationActions {...props({ primary: 'none' })} />);
    expect(screen.getByRole('button', { name: 'Delete draft' })).toHaveAttribute('data-variant', 'danger');
    expect(primaryNames()).toEqual([]);
  });

  it('shows Apply in the workflow group and Revise in draft management for an applied month, with no primary', () => {
    render(<EvaluationActions {...props({ primary: 'none', approved: true, monthApproved: true, canDeleteDraft: false, applyVisible: true })} />);
    expect(buttonNames(screen.getByRole('group', { name: 'Workflow actions' }))).toEqual(['Apply']);
    expect(buttonNames(screen.getByRole('group', { name: 'Draft management' }))).toEqual(['Revise this month', 'Use original upload settings']);
    expect(primaryNames()).toEqual([]);
    expect(screen.getByRole('button', { name: 'Revise this month' })).toHaveAttribute('data-variant', 'secondary');
  });

  it('makes New draft the primary action when the month has no version yet', () => {
    render(<EvaluationActions {...props({ primary: 'open_draft', adoptVisible: false, canDeleteDraft: false })} />);
    expect(buttonNames(screen.getByRole('group', { name: 'Draft management' }))).toEqual(['New draft', 'Copy previous month']);
    expect(primaryNames()).toEqual(['New draft']);
  });

  it('omits the workflow group when no workflow button applies to an approved month', () => {
    render(<EvaluationActions {...props({ primary: 'none', approved: true, monthApproved: true, canDeleteDraft: false, applyVisible: false, adoptVisible: false })} />);
    expect(screen.queryByRole('group', { name: 'Workflow actions' })).not.toBeInTheDocument();
    expect(buttonNames(screen.getByRole('group', { name: 'Draft management' }))).toEqual(['Revise this month']);
  });

  it('uses the disabled map for each button, unchanged', () => {
    const disabled = { ...everyAction(() => false), approve: true };
    render(<EvaluationActions {...props({ primary: 'none', disabled })} />);
    expect(screen.getByRole('button', { name: 'Approve' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Save draft' })).toBeEnabled();
  });

  it('calls only the handler for the button that was pressed', () => {
    const base = props({ primary: 'save' });
    render(<EvaluationActions {...base} />);
    fireEvent.click(screen.getByRole('button', { name: 'Save draft' }));
    expect(base.onAction.save).toHaveBeenCalledTimes(1);
    expect(base.onAction.approve).not.toHaveBeenCalled();
  });
});
