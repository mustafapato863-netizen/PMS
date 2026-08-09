import { Activity, ArrowUpRight, ClipboardCheck, Timer } from 'lucide-react';
import type { TeamAgentRow } from '../../hooks/usePerformanceData';
import { PRE_APPROVALS_WORKFLOW_LABELS, preApprovalsWorkflowForTeam, type PreApprovalsWorkflowFilter } from '../../types';

interface PreApprovalsWorkflowSummaryProps {
  rows: TeamAgentRow[];
  onWorkflowSelect: (workflow: Exclude<PreApprovalsWorkflowFilter, 'all'>) => void;
}

const WORKFLOWS: Exclude<PreApprovalsWorkflowFilter, 'all'>[] = ['ip_final', 'op_final', 'ip_elective'];

const WORKFLOW_META: Record<Exclude<PreApprovalsWorkflowFilter, 'all'>, { icon: typeof Activity; tone: string; accent: string; glow: string }> = {
  ip_final: {
    icon: Activity,
    tone: 'bg-violet-500/10 text-violet-600 dark:bg-violet-400/15 dark:text-violet-300',
    accent: 'bg-violet-500',
    glow: 'hover:border-violet-300/80 hover:shadow-[0_0_28px_rgba(139,92,246,0.24)] dark:hover:border-violet-400/60 dark:hover:shadow-[0_0_34px_rgba(167,139,250,0.25)]',
  },
  op_final: {
    icon: ClipboardCheck,
    tone: 'bg-blue-500/10 text-blue-600 dark:bg-blue-400/15 dark:text-blue-300',
    accent: 'bg-blue-500',
    glow: 'hover:border-blue-300/80 hover:shadow-[0_0_28px_rgba(59,130,246,0.24)] dark:hover:border-blue-400/60 dark:hover:shadow-[0_0_34px_rgba(96,165,250,0.25)]',
  },
  ip_elective: {
    icon: Timer,
    tone: 'bg-amber-500/10 text-amber-600 dark:bg-amber-400/15 dark:text-amber-300',
    accent: 'bg-amber-500',
    glow: 'hover:border-amber-300/80 hover:shadow-[0_0_28px_rgba(245,158,11,0.24)] dark:hover:border-amber-400/60 dark:hover:shadow-[0_0_34px_rgba(251,191,36,0.25)]',
  },
};

const PreApprovalsWorkflowSummary = ({ rows, onWorkflowSelect }: PreApprovalsWorkflowSummaryProps) => (
  <section className="glass-panel rounded-xl p-4 shadow-sm sm:p-6" aria-labelledby="pre-approvals-workflow-summary">
    <div className="mb-4">
      <h3 id="pre-approvals-workflow-summary" className="heading-3">Workflow Summary</h3>
      <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">
        Workflows use separate KPI definitions and are not pooled into one KPI score.
      </p>
    </div>
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      {WORKFLOWS.map((workflow) => {
        const workflowRows = rows.filter((row) => preApprovalsWorkflowForTeam(row.raw.identity.team) === workflow);
        const average = workflowRows.length > 0
          ? workflowRows.reduce((sum, row) => sum + row.score, 0) / workflowRows.length
          : 0;
        const Icon = WORKFLOW_META[workflow].icon;
        return (
          <button
            key={workflow}
            type="button"
            onClick={() => onWorkflowSelect(workflow)}
            aria-label={`Open ${PRE_APPROVALS_WORKFLOW_LABELS[workflow]} workflow`}
            className={`group relative overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] p-4 text-left transition-all duration-200 hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 ${WORKFLOW_META[workflow].glow}`}
          >
            <span className={`pointer-events-none absolute -right-10 -top-10 h-28 w-28 rounded-full opacity-10 blur-2xl transition-opacity duration-200 group-hover:opacity-30 ${WORKFLOW_META[workflow].accent}`} />
            <div className="flex items-center gap-3">
              <span className={`flex h-10 w-10 items-center justify-center rounded-xl ${WORKFLOW_META[workflow].tone}`}>
                <Icon size={19} />
              </span>
              <div>
                <h4 className="text-sm font-extrabold text-[var(--text-primary)]">{PRE_APPROVALS_WORKFLOW_LABELS[workflow]}</h4>
                <p className="text-xs font-semibold text-[var(--text-muted)]">{workflowRows.length} employees</p>
              </div>
            </div>
            <div className="mt-4 flex items-end justify-between gap-3">
              <div>
                <div className="text-2xl font-extrabold text-[var(--text-primary)]">
                  {workflowRows.length > 0 ? `${average.toFixed(1)}%` : 'No data'}
                </div>
                <p className="mt-1 text-xs font-medium text-[var(--text-secondary)]">Average employee score</p>
              </div>
              <span className="flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border-light)] text-[var(--text-muted)] transition-all duration-200 group-hover:border-current group-hover:text-[var(--text-primary)]" aria-hidden="true">
                <ArrowUpRight size={16} />
              </span>
            </div>
          </button>
        );
      })}
    </div>
  </section>
);

export default PreApprovalsWorkflowSummary;
