import { Circle, CircleCheck, CircleDot, Lock, type LucideIcon } from 'lucide-react';
import type { StepState, WorkflowStep } from './evaluationWorkflowState';

const STATE_TEXT: Record<StepState, string> = {
  done: 'Done',
  current: 'Current step',
  upcoming: 'Not started',
  locked: 'Locked',
};

const STATE_ICON: Record<StepState, LucideIcon> = {
  done: CircleCheck,
  current: CircleDot,
  upcoming: Circle,
  locked: Lock,
};

const STATE_CLASS: Record<StepState, string> = {
  done: 'border-emerald-500/20 bg-emerald-500/5 text-emerald-700 dark:text-emerald-300',
  current: 'border-blue-500/40 bg-blue-500/10 text-[var(--text-primary)]',
  upcoming: 'border-[var(--border-light)] text-[var(--text-muted)]',
  locked: 'border-[var(--border-light)] text-[var(--text-muted)]',
};

export type EvaluationStepperProps = {
  steps: readonly WorkflowStep[];
};

/**
 * The four workflow steps in order. The current step carries aria-current, and a locked or blocked step
 * says why in text, so no state is shown by colour alone.
 */
export function EvaluationStepper({ steps }: EvaluationStepperProps) {
  return (
    <ol aria-label="Evaluation steps" className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-4">
      {steps.map((step, index) => {
        const Icon = STATE_ICON[step.state];
        return (
          <li
            key={step.id}
            data-state={step.state}
            aria-current={step.state === 'current' ? 'step' : undefined}
            className={`flex min-w-0 gap-2 rounded-xl border p-3 ${STATE_CLASS[step.state]}`}
          >
            <Icon size={16} aria-hidden="true" className="mt-0.5 shrink-0" />
            <div className="min-w-0">
              <p className="text-xs font-bold">{index + 1}. {step.label}</p>
              <p className="text-xs font-semibold">{STATE_TEXT[step.state]}</p>
              {step.reason && <p className="mt-1 text-xs text-[var(--text-secondary)]">{step.reason}</p>}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
