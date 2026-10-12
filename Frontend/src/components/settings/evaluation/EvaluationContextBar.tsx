import { CircleCheck, Info, TriangleAlert, Circle, type LucideIcon } from 'lucide-react';
import type { PerformanceLevel } from '../../../types';
import { MONTHS } from '../evaluationSettings';
import type { StatusTone } from './evaluationWorkflowState';

export type ScopeOption = { id: string; label: string };

export type EvaluationContextBarProps = {
  level: PerformanceLevel;
  levels: readonly PerformanceLevel[];
  onLevelChange: (value: string) => void;
  scopeId: string;
  scopeOptions: ScopeOption[];
  /** Shown as the only option when the level has no scopes. Null when there are scopes. */
  emptyScopeText: string | null;
  scopeDisabled: boolean;
  onScopeChange: (value: string) => void;
  month: number;
  onMonthChange: (value: number) => void;
  year: number;
  onYearChange: (value: number) => void;
  /** The scope count line. It is the panel's only role=status node in this bar. */
  scopeCountText: string;
  status: { label: string; tone: StatusTone };
};

const TONE_ICON: Record<StatusTone, { icon: LucideIcon; className: string }> = {
  info: { icon: Info, className: 'border-blue-500/25 bg-blue-500/10 text-blue-700 dark:text-blue-300' },
  good: { icon: CircleCheck, className: 'border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300' },
  warning: { icon: TriangleAlert, className: 'border-amber-500/30 bg-amber-500/10 text-amber-800 dark:text-amber-300' },
  neutral: { icon: Circle, className: 'border-[var(--border-light)] bg-[var(--bg-sunken)] text-[var(--text-secondary)]' },
};

const SELECT_CLASS = 'mt-1 w-full rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-3 py-2 text-sm text-[var(--text-primary)]';

/**
 * Month status badge. It carries a text label and an icon, so the status is never shown by colour alone.
 * It is a plain element, not a status region, so it does not add a second status node to the panel.
 */
function StatusBadge({ label, tone }: { label: string; tone: StatusTone }) {
  const { icon: Icon, className } = TONE_ICON[tone];
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs font-bold text-[var(--text-secondary)]">
      <span>Month status</span>
      <span data-tone={tone} className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-bold ${className}`}>
        <Icon size={14} aria-hidden="true" />
        {label}
      </span>
    </div>
  );
}

export function EvaluationContextBar(props: EvaluationContextBarProps) {
  const { level, levels, scopeId, scopeOptions, emptyScopeText, scopeDisabled, month, year, scopeCountText, status } = props;
  return (
    <div className="min-w-0 space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <label className="min-w-0 text-xs font-bold text-[var(--text-secondary)]">Performance level
          <select aria-label="Performance level" value={level} onChange={(event) => props.onLevelChange(event.target.value)} className={SELECT_CLASS}>
            {levels.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="min-w-0 text-xs font-bold text-[var(--text-secondary)]">Evaluation scope
          <select aria-label="Evaluation scope" value={scopeId} disabled={scopeDisabled} onChange={(event) => props.onScopeChange(event.target.value)} className={`${SELECT_CLASS} disabled:cursor-not-allowed disabled:opacity-50`}>
            {emptyScopeText !== null && <option value="">{emptyScopeText}</option>}
            {scopeOptions.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}
          </select>
        </label>
        <label className="min-w-0 text-xs font-bold text-[var(--text-secondary)]">Reporting month
          <select aria-label="Reporting month" value={month} onChange={(event) => props.onMonthChange(Number(event.target.value))} className={SELECT_CLASS}>
            {MONTHS.map((name, index) => <option key={name} value={index + 1}>{name}</option>)}
          </select>
        </label>
        <label className="min-w-0 text-xs font-bold text-[var(--text-secondary)]">Reporting year
          <input aria-label="Reporting year" type="number" min={2000} max={2100} value={year} onChange={(event) => props.onYearChange(Number(event.target.value))} className={SELECT_CLASS} />
        </label>
      </div>
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-[var(--text-muted)]" role="status">{scopeCountText}</p>
        <StatusBadge label={status.label} tone={status.tone} />
      </div>
    </div>
  );
}
