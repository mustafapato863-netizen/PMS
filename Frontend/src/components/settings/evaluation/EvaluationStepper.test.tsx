import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EvaluationStepper } from './EvaluationStepper';
import { STEP_LABELS, type StepId, type StepState, type WorkflowStep } from './evaluationWorkflowState';

const ORDER: StepId[] = ['edit', 'preview', 'approve', 'apply'];

function steps(states: Record<StepId, StepState>, reasons: Partial<Record<StepId, string>> = {}): WorkflowStep[] {
  return ORDER.map((id) => {
    const reason = reasons[id];
    return reason === undefined
      ? { id, label: STEP_LABELS[id], state: states[id] }
      : { id, label: STEP_LABELS[id], state: states[id], reason };
  });
}

describe('EvaluationStepper', () => {
  it('lists the four steps in order under the Evaluation steps name', () => {
    render(<EvaluationStepper steps={steps({ edit: 'done', preview: 'done', approve: 'current', apply: 'locked' })} />);
    const list = screen.getByRole('list', { name: 'Evaluation steps' });
    const items = within(list).getAllByRole('listitem');
    expect(items.map((item) => item.textContent)).toEqual([
      '1. Edit and saveDone',
      '2. Preview impactDone',
      '3. ApproveCurrent step',
      '4. ApplyLocked',
    ]);
  });

  it('marks only the current step with aria-current', () => {
    render(<EvaluationStepper steps={steps({ edit: 'done', preview: 'current', approve: 'upcoming', apply: 'locked' })} />);
    const items = within(screen.getByRole('list', { name: 'Evaluation steps' })).getAllByRole('listitem');
    expect(items.map((item) => item.getAttribute('aria-current'))).toEqual([null, 'step', null, null]);
    expect(items.map((item) => item.getAttribute('data-state'))).toEqual(['done', 'current', 'upcoming', 'locked']);
  });

  it('shows the reason as text for a locked step, so it is not conveyed by colour alone', () => {
    render(<EvaluationStepper steps={steps(
      { edit: 'done', preview: 'done', approve: 'current', apply: 'locked' },
      { apply: 'Approve the draft before applying.' },
    )} />);
    expect(screen.getByText('Approve the draft before applying.')).toBeInTheDocument();
  });

  it('shows no current step and no reason when every step is done', () => {
    render(<EvaluationStepper steps={steps({ edit: 'done', preview: 'done', approve: 'done', apply: 'done' })} />);
    const items = within(screen.getByRole('list', { name: 'Evaluation steps' })).getAllByRole('listitem');
    expect(items.every((item) => item.getAttribute('aria-current') === null)).toBe(true);
    expect(items.every((item) => item.textContent?.endsWith('Done'))).toBe(true);
  });
});
