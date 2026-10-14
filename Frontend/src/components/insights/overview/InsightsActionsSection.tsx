import { Link } from 'react-router-dom';
import { ClipboardList } from 'lucide-react';
import type { PMSAction } from '../../../types';
import { SectionCard, SectionHeader } from './InsightsOverviewPrimitives';

export interface PersonBelowTarget {
  employee_id: string;
  employee_name: string;
  team: string;
  performance_level: string;
}

/**
 * Corrective actions for the selected KPI in scope. An action is matched to the KPI by its
 * linked_kpi_key and to a person by employee_id. Actions with no linked KPI are counted, not listed.
 */
export default function InsightsActionsSection({
  kpiKey,
  kpiLabel,
  actions,
  team,
  month,
  peopleBelowTarget,
  onAddActionForFirst,
  canAddForPerson,
}: {
  kpiKey: string | null;
  kpiLabel: string | null;
  actions: PMSAction[];
  /** The Team filter, when one is selected. Actions outside it are not shown. */
  team?: string;
  /** The month name of the current period, when known. Actions from other months are not shown. */
  month?: string;
  peopleBelowTarget: PersonBelowTarget[];
  onAddActionForFirst: (person: PersonBelowTarget) => void;
  /** False when a person cannot be opened in the action form from this page. */
  canAddForPerson: (person: PersonBelowTarget) => boolean;
}) {
  const inScope = actions.filter((action) => (!team || action.team === team) && (!month || action.month === month));
  const forKpi = kpiKey ? inScope.filter((action) => action.linked_kpi_key === kpiKey) : [];
  const withoutKpi = inScope.filter((action) => !action.linked_kpi_key).length;
  const employeesWithAction = new Set(forKpi.map((action) => action.employee_id));
  const missing = kpiKey ? peopleBelowTarget.filter((person) => !employeesWithAction.has(person.employee_id)) : [];
  const first = missing[0];

  return (
    <SectionCard labelledBy="insights-actions-title" className="gap-[16px] py-[20px]">
      <SectionHeader
        id="insights-actions-title"
        icon={<ClipboardList size={16} />}
        iconBackground="var(--insights-accent)"
        title="Actions"
        subtitle={kpiLabel ? `Corrective actions recorded for ${kpiLabel} in this scope` : 'Select a KPI to see its corrective actions'}
        action={(
          <Link to="/corrective-actions" className="shrink-0 text-[13px] font-semibold text-blue-600 hover:underline">
            Open follow-up board
          </Link>
        )}
      />
      {kpiKey && forKpi.length === 0 && <p className="text-[13px] text-[var(--text-muted)]">No corrective actions are recorded for this KPI in scope.</p>}
      {kpiKey && forKpi.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-[13px]">
            <thead>
              <tr className="border-b border-[var(--insights-row-border)] text-[12px] font-semibold text-[var(--text-muted)]">
                <th scope="col" className="py-[8px] pr-[12px] font-semibold">Action</th>
                <th scope="col" className="py-[8px] pr-[12px] font-semibold">Employee</th>
                <th scope="col" className="py-[8px] pr-[12px] font-semibold">Status</th>
                <th scope="col" className="py-[8px] pr-[12px] font-semibold">Owner</th>
                <th scope="col" className="py-[8px] font-semibold">Due date</th>
              </tr>
            </thead>
            <tbody>
              {forKpi.map((action) => (
                <tr key={action.id} className="border-b border-[var(--insights-row-border)] last:border-b-0">
                  <td className="py-[8px] pr-[12px] align-top text-[var(--text-primary)]">{action.action_text}</td>
                  <td className="py-[8px] pr-[12px] align-top text-[var(--text-secondary)]">{action.employee_name}</td>
                  <td className="py-[8px] pr-[12px] align-top text-[var(--text-secondary)]">{action.status ?? 'Open'}</td>
                  <td className="py-[8px] pr-[12px] align-top text-[var(--text-secondary)]">{action.owner?.name ?? 'Unassigned'}</td>
                  <td className="py-[8px] align-top">
                    {action.due_date ? (
                      <span className={action.is_overdue ? 'font-semibold text-rose-600 dark:text-rose-400' : 'text-[var(--text-secondary)]'}>
                        {action.due_date}{action.is_overdue ? ' · overdue' : ''}
                      </span>
                    ) : (
                      <span className="text-[var(--text-muted)]">No due date</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {kpiKey && (
        <div className="flex flex-wrap items-center justify-between gap-[12px] border-t border-[var(--insights-row-border)] pt-[12px] text-[13px]">
          <p className="text-[var(--text-secondary)]">
            <strong className="font-semibold tabular-nums text-[var(--text-primary)]">{missing.length}</strong>
            {' '}people below target on {kpiLabel} have no action yet
          </p>
          {first && (
            <button
              type="button"
              disabled={!canAddForPerson(first)}
              onClick={() => onAddActionForFirst(first)}
              className="rounded-[8px] border border-[var(--insights-accent-border)] bg-[var(--insights-accent-soft)] px-[12px] py-[6px] text-[13px] font-semibold text-[var(--insights-accent-text)] disabled:cursor-not-allowed disabled:opacity-60"
            >
              Add action for {first.employee_name}
            </button>
          )}
        </div>
      )}
      {withoutKpi > 0 && (
        <p className="text-[12px] text-[var(--text-muted)]">
          {withoutKpi} {withoutKpi === 1 ? 'action in scope has' : 'actions in scope have'} no linked KPI and {withoutKpi === 1 ? 'is' : 'are'} not shown under a KPI.
        </p>
      )}
    </SectionCard>
  );
}
