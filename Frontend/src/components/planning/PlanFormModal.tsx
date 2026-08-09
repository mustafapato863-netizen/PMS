import { useMemo, useState } from 'react';
import { ArrowLeft, ArrowRight, CheckCircle2, Loader2, X } from 'lucide-react';
import type { PlanCreatePayload, PlanningOptions } from '../../features/planning/types';
import { useInsightsWorkspace } from '../../hooks/api/useInsightsWorkspace';
import { useCreatePlan } from '../../hooks/api/usePlanning';
import OverlayPortal from '../common/OverlayPortal';

const input = 'min-h-11 w-full rounded-xl border border-[var(--input-border)] bg-[var(--input-bg)] px-3 text-sm text-[var(--input-text)] outline-none focus:ring-2 focus:ring-blue-500/20';
const steps = ['Context', 'Evidence', 'Outcomes', 'Execution', 'Review'];

type Props = {
  options: PlanningOptions;
  onClose: () => void;
  onCreated: (id: string) => void;
};

function readDraft(): Record<string, unknown> {
  try {
    const value = JSON.parse(sessionStorage.getItem('pms_planning_draft') || '{}');
    return value && typeof value === 'object' ? value : {};
  } catch {
    return {};
  }
}

function PlanFormModalContent({ options, onClose, onCreated }: Props) {
  const [draft] = useState(readDraft);
  const dates = useMemo(() => {
    const now = new Date();
    const later = new Date(now);
    later.setDate(later.getDate() + 90);
    return { today: now.toISOString().slice(0, 10), end: later.toISOString().slice(0, 10) };
  }, []);
  const [step, setStep] = useState(1);
  const [error, setError] = useState('');
  const [linked, setLinked] = useState<string[]>(
    draft.source_insight_id ? [String(draft.source_insight_id)] : [],
  );
  const [form, setForm] = useState({
    name: String(draft.title || ''),
    scopeType: draft.employee_id ? 'Employee' : draft.position ? 'Position' : 'Team',
    team: String(draft.team || options.teams[0] || ''),
    level: String(draft.performance_level || options.performance_levels[0] || 'Employee'),
    position: String(draft.position || ''),
    employee: String(draft.employee_id || ''),
    start: dates.today,
    end: dates.end,
    due: dates.end,
    owner: options.owners[0]?.id || '',
    baseline: String(draft.baseline_value ?? ''),
    current: String(draft.current_value ?? draft.baseline_value ?? ''),
    target: String(draft.target_value ?? ''),
    unit: String(draft.unit || '%'),
    direction: String(draft.direction || 'higher_better'),
    reason: '',
    objective: String(draft.suggested_objective || ''),
    kpiKey: String(draft.kpi_key || ''),
    kpiLabel: '',
    action: String(draft.suggested_action || ''),
    milestone: '',
  });

  const insights = useInsightsWorkspace({
    team: form.team,
    performanceLevel: form.level,
    position: form.position || undefined,
    employeeId: form.employee || undefined,
  });
  const create = useCreatePlan();
  const linkedInsight = insights.data?.priority_insights.find((item) => linked.includes(item.id));

  const applyInsightDefaults = () => {
    if (!linkedInsight) return;
    const subject = linkedInsight.title.split(' contributed')[0].split(' is a ')[0].trim();
    setForm((current) => ({
      ...current,
      baseline: current.baseline || (linkedInsight.detail.previous_value == null
        ? linkedInsight.detail.current_value == null ? '' : String(linkedInsight.detail.current_value)
        : String(linkedInsight.detail.previous_value)),
      current: current.current || (linkedInsight.detail.current_value == null ? '' : String(linkedInsight.detail.current_value)),
      target: current.target || (linkedInsight.detail.target_value == null ? '' : String(linkedInsight.detail.target_value)),
      unit: current.unit === '%' && linkedInsight.detail.unit ? linkedInsight.detail.unit : current.unit,
      direction: linkedInsight.detail.direction || current.direction,
      objective: current.objective || `Improve ${subject} performance to the configured target`,
      kpiLabel: current.kpiLabel || subject,
    }));
  };

  const set = (key: keyof typeof form, value: string) => {
    setError('');
    setForm((current) => ({
      ...current,
      [key]: value,
      ...(key === 'baseline' && current.current === '' ? { current: value } : {}),
    }));
    if (['team', 'level', 'position', 'employee'].includes(key)) setLinked([]);
  };

  const validationMessage = (targetStep: number): string | null => {
    if (targetStep === 1) {
      if (form.name.trim().length < 3) return 'Enter a plan name of at least 3 characters.';
      if (!form.team) return 'Select a team.';
      if (!form.level) return 'Select a performance level.';
      if (!form.owner) return 'Select a plan owner.';
      if (form.scopeType === 'Position' && !form.position) return 'Select a position for this plan.';
      if (form.scopeType === 'Employee' && !form.employee) return 'Select an employee for this plan.';
      if (!form.start || !form.end) return 'Select the plan start and end dates.';
      if (form.end < form.start) return 'The plan end date must be on or after its start date.';
    }
    if (targetStep === 2) {
      if (linked.length && !insights.data?.comparison.current) return 'Wait for the linked insight evidence to finish loading.';
      if (linked.length && !linkedInsight) return 'The linked insight is no longer available for the selected scope. Select it again or remove the link.';
      if (!linked.length && !form.reason.trim()) return 'Link an insight or explain why this plan has no linked insight.';
    }
    if (targetStep === 3) {
      if (form.baseline === '' || !Number.isFinite(Number(form.baseline))) return 'Enter a valid baseline value.';
      if (form.current !== '' && !Number.isFinite(Number(form.current))) return 'Enter a valid current value.';
      if (form.target === '' || !Number.isFinite(Number(form.target))) return 'Enter a valid target value.';
      if (Number(form.baseline) === Number(form.target)) return 'The target must be different from the baseline.';
      if (!form.unit.trim()) return 'Enter the outcome unit.';
      if (form.objective.trim().length < 3) return 'Enter a measurable objective of at least 3 characters.';
    }
    if (targetStep === 4) {
      if (!form.due) return 'Select a due date.';
      if (form.due < form.start) return 'The due date must be on or after the plan start date.';
      if (form.action.trim() && form.action.trim().length < 3) return 'The action must contain at least 3 characters.';
      if (form.milestone.trim() && form.milestone.trim().length < 3) return 'The milestone must contain at least 3 characters.';
    }
    return null;
  };

  const next = () => {
    const message = validationMessage(step);
    if (message) {
      setError(message);
      return;
    }
    if (step === 2) applyInsightDefaults();
    setError('');
    setStep((current) => current + 1);
  };

  const submit = async (activate: boolean) => {
    for (let targetStep = 1; targetStep <= 4; targetStep += 1) {
      const message = validationMessage(targetStep);
      if (message) {
        setStep(targetStep);
        setError(message);
        return;
      }
    }

    setError('');
    const current = insights.data?.comparison.current;
    const currentValue = form.current === '' ? Number(form.baseline) : Number(form.current);
    const kpi = form.kpiKey ? {
      kpi_key: form.kpiKey,
      kpi_label: form.kpiLabel || form.kpiKey,
      unit: form.unit,
      direction: form.direction,
      baseline_value: Number(form.baseline),
      target_value: Number(form.target),
      current_value: currentValue,
    } : null;
    const payload: PlanCreatePayload = {
      name: form.name.trim(),
      scope_type: form.scopeType,
      team: form.team,
      performance_level: form.level,
      position_name: form.position || undefined,
      employee_identifier: form.employee || undefined,
      period_start: form.start,
      period_end: form.end,
      due_date: form.due,
      owner_user_id: form.owner,
      baseline_value: Number(form.baseline),
      target_value: Number(form.target),
      current_value: currentValue,
      outcome_unit: form.unit.trim(),
      outcome_direction: form.direction,
      expected_impact: Number(form.target) - Number(form.baseline),
      insight_ids: linked,
      evidence_month: linked.length ? current?.month : undefined,
      evidence_year: linked.length ? current?.year : undefined,
      no_insight_reason: linked.length ? undefined : form.reason.trim(),
      objectives: [{
        name: form.objective.trim(),
        measurement_type: form.kpiKey ? 'kpi' : 'score',
        baseline_value: Number(form.baseline),
        target_value: Number(form.target),
        current_value: currentValue,
        unit: form.unit.trim(),
        direction: form.direction,
        due_date: form.due,
        owner_user_id: form.owner,
        linked_kpi_keys: kpi ? [form.kpiKey] : [],
      }],
      kpis: kpi ? [kpi] : [],
      actions: form.action.trim() ? [{
        title: form.action.trim(),
        description: form.action.trim(),
        action_type: 'Monitor',
        owner_user_id: form.owner,
        due_date: form.due,
        priority: 'Medium',
        objective_index: 0,
        linked_kpi_key: form.kpiKey || undefined,
      }] : [],
      milestones: form.milestone.trim() ? [{
        name: form.milestone.trim(),
        due_date: form.due,
        owner_user_id: form.owner,
      }] : [],
      activate,
    };

    try {
      const result = await create.mutateAsync(payload);
      sessionStorage.removeItem('pms_planning_draft');
      onCreated(result.id);
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : 'Unable to create plan.');
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-950/40 p-3 backdrop-blur-sm md:p-8">
      <div role="dialog" aria-modal="true" aria-label="New performance plan" className="mx-auto flex h-full max-w-3xl flex-col rounded-3xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-2xl">
        <header className="flex items-center justify-between border-b border-[var(--border-light)] p-5">
          <div>
            <h2 className="text-xl font-extrabold">New Plan</h2>
            <p className="text-sm text-[var(--text-muted)]">Step {step} of 5 · {steps[step - 1]}</p>
          </div>
          <button type="button" aria-label="Close new plan" onClick={onClose} className="grid h-11 w-11 place-items-center rounded-xl hover:bg-[var(--bg-sunken)]"><X /></button>
        </header>

        <div className="flex gap-1 px-5 pt-4">
          {steps.map((label, index) => <div key={label} className={`h-1.5 flex-1 rounded-full ${index < step ? 'bg-blue-600' : 'bg-[var(--bg-sunken)]'}`} />)}
        </div>

        <div className="custom-scrollbar flex-1 overflow-y-auto p-5 md:p-7">
          {step === 1 && (
            <div className="grid gap-4 md:grid-cols-2">
              <label>Plan name<input className={input} value={form.name} onChange={(event) => set('name', event.target.value)} /></label>
              <label>Scope type<select className={input} value={form.scopeType} onChange={(event) => set('scopeType', event.target.value)}>{['Team', 'Position', 'Employee', 'Management'].map((value) => <option key={value}>{value}</option>)}</select></label>
              <label>Team<select className={input} value={form.team} onChange={(event) => set('team', event.target.value)}>{options.teams.map((value) => <option key={value}>{value}</option>)}</select></label>
              <label>Performance level<select className={input} value={form.level} onChange={(event) => set('level', event.target.value)}>{options.performance_levels.map((value) => <option key={value}>{value}</option>)}</select></label>
              {form.scopeType === 'Position' && <label>Position<select className={input} value={form.position} onChange={(event) => set('position', event.target.value)}><option value="">Select</option>{options.positions.map((value) => <option key={value}>{value}</option>)}</select></label>}
              {form.scopeType === 'Employee' && <label>Employee<select className={input} value={form.employee} onChange={(event) => set('employee', event.target.value)}><option value="">Select</option>{options.employees.filter((employee) => employee.team === form.team).map((employee) => <option key={employee.id} value={employee.id}>{employee.name}</option>)}</select></label>}
              <label>Owner<select className={input} value={form.owner} onChange={(event) => set('owner', event.target.value)}>{options.owners.map((owner) => <option key={owner.id} value={owner.id}>{owner.name}</option>)}</select></label>
              <label>Start<input type="date" className={input} value={form.start} onChange={(event) => set('start', event.target.value)} /></label>
              <label>End<input type="date" className={input} value={form.end} onChange={(event) => set('end', event.target.value)} /></label>
            </div>
          )}

          {step === 2 && (
            <div>
              <h3 className="font-extrabold">Link evidence</h3>
              <div className="mt-3 max-h-72 space-y-2 overflow-y-auto">
                {insights.data?.priority_insights.slice(0, 8).map((item) => (
                  <label key={item.id} className="flex gap-3 rounded-xl border border-[var(--border-light)] p-3">
                    <input type="checkbox" checked={linked.includes(item.id)} onChange={() => setLinked((current) => current.includes(item.id) ? current.filter((id) => id !== item.id) : [...current, item.id])} />
                    <span><strong>{item.title}</strong><small className="block text-[var(--text-muted)]">{item.explanation}</small></span>
                  </label>
                ))}
              </div>
              {!linked.length && <label className="mt-4 block">Reason for plan without linked insight<textarea className={`${input} min-h-24 py-3`} value={form.reason} onChange={(event) => set('reason', event.target.value)} /></label>}
            </div>
          )}

          {step === 3 && (
            <div className="grid gap-4 md:grid-cols-2">
              <label>Baseline<input type="number" className={input} value={form.baseline} onChange={(event) => set('baseline', event.target.value)} /></label>
              <label>Current result<input type="number" className={input} value={form.current} onChange={(event) => set('current', event.target.value)} /></label>
              <label>Target<input type="number" className={input} value={form.target} onChange={(event) => set('target', event.target.value)} /></label>
              <label>Unit<input className={input} value={form.unit} onChange={(event) => set('unit', event.target.value)} /></label>
              <label>Direction<select className={input} value={form.direction} onChange={(event) => set('direction', event.target.value)}><option value="higher_better">Higher is better</option><option value="lower_better">Lower is better</option></select></label>
              <label className="md:col-span-2">Measurable objective<input className={input} value={form.objective} onChange={(event) => set('objective', event.target.value)} placeholder="Increase score from baseline to target" /></label>
              <label>KPI key (optional)<input className={input} value={form.kpiKey} onChange={(event) => set('kpiKey', event.target.value)} /></label>
              <label>KPI label<input className={input} value={form.kpiLabel} onChange={(event) => set('kpiLabel', event.target.value)} /></label>
            </div>
          )}

          {step === 4 && (
            <div className="grid gap-4">
              <label>First action (optional)<input className={input} value={form.action} onChange={(event) => set('action', event.target.value)} /></label>
              <label>First milestone (optional)<input className={input} value={form.milestone} onChange={(event) => set('milestone', event.target.value)} /></label>
              <label>Due date<input type="date" className={input} value={form.due} onChange={(event) => set('due', event.target.value)} /></label>
            </div>
          )}

          {step === 5 && (
            <div className="space-y-4">
              <div className="rounded-2xl border border-[var(--border-light)] bg-[var(--bg-sunken)] p-5">
                <CheckCircle2 className="text-emerald-600" />
                <h3 className="mt-3 font-extrabold">Review plan</h3>
                <p>{form.name} · {form.team} · {form.start} to {form.end}</p>
                <p className="text-sm text-[var(--text-muted)]">Baseline {form.baseline} {form.unit} → Current {form.current || form.baseline} {form.unit} → Target {form.target} {form.unit}; {linked.length} linked insight(s).</p>
                <p className="mt-2 text-sm text-[var(--text-muted)]">Objective: {form.objective}</p>
              </div>
              <p className="text-sm text-[var(--text-muted)]">Save as Draft keeps the plan inactive. Activate is an explicit choice.</p>
            </div>
          )}

          {error && <p role="alert" className="mt-4 rounded-xl bg-red-500/10 p-3 text-sm font-bold text-red-600">{error}</p>}
        </div>

        <footer className="flex items-center justify-between border-t border-[var(--border-light)] p-4">
          <button type="button" disabled={step === 1} onClick={() => { setError(''); setStep((current) => current - 1); }} className="inline-flex min-h-11 items-center gap-2 rounded-xl border px-4 disabled:opacity-40"><ArrowLeft size={16} />Back</button>
          {step < 5 ? (
            <button type="button" onClick={next} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-blue-600 px-5 font-bold text-white">Next<ArrowRight size={16} /></button>
          ) : (
            <div className="flex gap-2">
              <button type="button" disabled={create.isPending} onClick={() => submit(false)} className="min-h-11 rounded-xl border px-4 font-bold">Save Draft</button>
              <button type="button" disabled={create.isPending} onClick={() => submit(true)} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-blue-600 px-4 font-bold text-white">{create.isPending && <Loader2 size={16} className="animate-spin" />}Activate</button>
            </div>
          )}
        </footer>
      </div>
    </div>
  );
}

export default function PlanFormModal(props: Props) {
  return <OverlayPortal><PlanFormModalContent {...props} /></OverlayPortal>;
}
