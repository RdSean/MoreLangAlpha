import { Check } from 'lucide-react';

export type TextbookWorkflowStepStatus = 'pending' | 'in_progress' | 'completed' | 'failed';

export interface TextbookWorkflowStep {
  id: string;
  label: string;
  status: TextbookWorkflowStepStatus;
}

function currentStepIndex(steps: TextbookWorkflowStep[]) {
  const failed = steps.findIndex((step) => step.status === 'failed');
  if (failed >= 0) return failed;
  const inProgress = steps.findIndex((step) => step.status === 'in_progress');
  if (inProgress >= 0) return inProgress;
  const pending = steps.findIndex((step) => step.status === 'pending');
  return pending >= 0 ? pending : steps.length - 1;
}

function stepColor(status: TextbookWorkflowStepStatus) {
  if (status === 'failed') return 'var(--color-loss)';
  return 'var(--color-accent-primary)';
}

export default function TextbookWorkflowStepper({ steps }: { steps: TextbookWorkflowStep[] }) {
  const current = currentStepIndex(steps);
  const currentLabel = steps[current]?.label ?? '';

  return (
    <ol
      aria-label={`教材加工进度：${currentLabel}`}
      className="grid gap-4 sm:grid-cols-4 sm:gap-0"
      data-testid="textbook-workflow-stepper"
    >
      {steps.map((step, index) => {
        const reached = step.status === 'completed' || step.status === 'in_progress' || step.status === 'failed';
        const color = stepColor(step.status);
        return (
          <li key={step.id} className="flex min-w-0 items-center">
            {index > 0 && (
              <div
                aria-hidden="true"
                className="hidden h-px flex-1 sm:block"
                style={{
                  backgroundColor:
                    reached && steps[index - 1]?.status === 'completed'
                      ? 'var(--color-accent-primary)'
                      : 'var(--color-border-default)',
                }}
              />
            )}
            <div className="flex min-w-0 flex-1 items-center gap-3 sm:flex-col sm:gap-2">
              <div
                className="flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold"
                style={{
                  backgroundColor: reached ? color : 'transparent',
                  border: reached ? 'none' : '2px solid var(--color-border-default)',
                  color: reached ? '#fff' : 'var(--color-text-tertiary)',
                }}
              >
                {step.status === 'completed' ? <Check className="size-3.5" aria-hidden="true" /> : index + 1}
              </div>
              <span
                className="truncate text-sm font-medium"
                style={{
                  color: reached ? 'var(--color-text-primary)' : 'var(--color-text-tertiary)',
                }}
              >
                {step.label}
              </span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
