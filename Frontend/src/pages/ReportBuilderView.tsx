import './PageEnhancements.css';
import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, ArrowRight, Check, Cloud, Loader2, Save } from 'lucide-react';
import { useSaveStoryDraft, useSaveStoryTemplate, useStoryDraft } from '../hooks/api/useReports';
import { useReportBuilderStore, type BuilderStep } from '../store/reportBuilderStore';
import Step1Scope from '../components/reports/builder/Step1Scope';
import Step2Template from '../components/reports/builder/Step2Template';
import Step3Builder from '../components/reports/builder/Step3Builder';
import Step4Review from '../components/reports/builder/Step4Review';
import Step5Export from '../components/reports/builder/Step5Export';
import { PageLoadingSkeleton } from '../components/common/SkeletonLoader';
import { validateReportScope, type ScopeValidationErrors } from '../features/reports/reportBuilderValidation';

const STEPS = ['Scope', 'Template', 'Build Report', 'Review', 'Export PDF'];

export default function ReportBuilderView() {
  const { reportId } = useParams();
  const routeKey = reportId || 'new';
  const navigate = useNavigate();
  const loadedId = useRef<string | null>(null);
  const initializedRoute = useRef<string | null>(null);
  const { data: serverDraft, isLoading, error } = useStoryDraft(reportId);
  const saveDraft = useSaveStoryDraft();
  const saveTemplate = useSaveStoryTemplate();
  const [scopeErrors, setScopeErrors] = useState<ScopeValidationErrors>({});
  const state = useReportBuilderStore();
  const { reset, loadDraft, setSaveState, acknowledgeSaved, advanceDraftVersion } = state;
  const saveDraftAsync = saveDraft.mutateAsync;

  useLayoutEffect(() => {
    if (initializedRoute.current !== routeKey) {
      if (!reportId) { reset(); loadedId.current = null; }
      initializedRoute.current = routeKey;
    }
  }, [reportId, reset, routeKey]);

  useEffect(() => {
    if (serverDraft && loadedId.current !== serverDraft.id) {
      loadDraft(serverDraft);
      loadedId.current = serverDraft.id;
    }
  }, [loadDraft, serverDraft]);

  useEffect(() => {
    if (state.saveState !== 'dirty' || !state.draftId || saveDraft.isPending) return;
    const savingDefinition = state.definition;
    const savingCommentary = state.commentary;
    const savingName = state.configuration.report_name;
    const timer = window.setTimeout(async () => {
      setSaveState('saving');
      try {
        const draft = await saveDraftAsync({
          id: state.draftId!, expectedVersion: state.draftVersion,
          name: state.configuration.report_name, definition: state.definition,
          commentary: state.commentary.entries,
        });
        const latest = useReportBuilderStore.getState();
        if (latest.definition === savingDefinition && latest.commentary === savingCommentary && latest.configuration.report_name === savingName) acknowledgeSaved(draft);
        else advanceDraftVersion(draft.version);
      } catch (saveError) {
        const message = saveError instanceof Error ? saveError.message : 'Autosave failed';
        setSaveState(message.includes('409') || message.toLowerCase().includes('updated elsewhere') ? 'conflict' : 'error', message);
      }
    }, 900);
    return () => window.clearTimeout(timer);
  }, [acknowledgeSaved, advanceDraftVersion, saveDraft.isPending, saveDraftAsync, setSaveState, state.saveState, state.draftId, state.draftVersion, state.definition, state.commentary, state.configuration.report_name]);

  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => { if (state.saveState === 'dirty' || state.saveState === 'saving') { event.preventDefault(); event.returnValue = ''; } };
    window.addEventListener('beforeunload', warn); return () => window.removeEventListener('beforeunload', warn);
  }, [state.saveState]);

  const next = () => {
    if (state.currentStep === 1) {
      const errors = validateReportScope(state.configuration);
      setScopeErrors(errors);
      if (Object.keys(errors).length) {
        window.requestAnimationFrame(() => document.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus());
        return;
      }
    }
    if (state.currentStep === 2 && !state.draftId) return;
    if (state.currentStep === 3 && state.slides.length === 0) return;
    if (state.currentStep < 5) state.setStep((state.currentStep + 1) as BuilderStep);
    else navigate('/reports');
  };
  const back = () => state.currentStep > 1 ? state.setStep((state.currentStep - 1) as BuilderStep) : navigate('/reports');
  const saveAsTemplate = async () => {
    if (!state.draftId) return;
    const name = window.prompt('Template name', `${state.configuration.report_name || 'Monthly Review'} Template`)?.trim();
    if (!name) return;
    const key = `${name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_|_$/g, '')}_${Date.now()}`;
    await saveTemplate.mutateAsync({ name, templateKey: key, reportType: state.reportType, definition: state.definition });
  };

  if (reportId && isLoading && !state.draftId) return <PageLoadingSkeleton variant="builder" label="Opening report workspace" />;
  if (reportId && error && !state.draftId) return <div className="m-8 rounded-2xl border border-red-200 bg-red-50 p-6 text-red-700"><b>Unable to load this report draft.</b><p className="mt-2 text-sm">{error.message}</p></div>;

  const saveStatus = {
    idle: null,
    dirty: <><Cloud size={14} /> Waiting to save</>,
    saving: <><Loader2 size={14} className="animate-spin" /> Saving</>,
    saved: <><Check size={14} /> Saved</>,
    error: <><AlertTriangle size={14} /> Save failed</>,
    conflict: <><AlertTriangle size={14} /> Version conflict - reload required</>,
  }[state.saveState];

  return <div className="rf-builder-shell flex h-[calc(100vh-2rem)] min-h-[720px] w-full flex-col overflow-hidden rounded-2xl border border-[var(--border-light)] bg-[var(--bg-surface)] shadow-sm">
    <header className="rf-builder-header flex min-h-16 items-center justify-between gap-4 border-b border-[var(--border-light)] bg-[var(--bg-surface)] px-5">
      <div className="flex items-center gap-4"><button onClick={back} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Back"><ArrowLeft size={19} /></button>
        <div className="hidden items-center gap-2 lg:flex">{STEPS.map((label, index) => { const id = index + 1; return <div key={label} className="flex items-center gap-2"><button onClick={() => id <= state.currentStep && state.setStep(id as BuilderStep)} className={`flex items-center gap-2 text-xs font-extrabold ${id === state.currentStep ? 'text-blue-600' : id < state.currentStep ? 'text-slate-700 dark:text-slate-300' : 'text-slate-400'}`}><span className={`grid h-6 w-6 place-items-center rounded-full border ${id <= state.currentStep ? 'border-blue-600 bg-blue-600 text-white' : 'border-slate-300'}`}>{id}</span>{label}</button>{id < 5 && <span className="h-px w-7 bg-slate-200" />}</div>; })}</div>
      </div>
      <div className="flex items-center gap-3">
        {saveStatus && <span title={state.saveMessage || undefined} className={`hidden items-center gap-1.5 text-xs font-bold sm:flex ${state.saveState === 'error' || state.saveState === 'conflict' ? 'text-red-600' : 'text-emerald-600'}`}>{saveStatus}</span>}
        {state.draftId && <button onClick={saveAsTemplate} disabled={saveTemplate.isPending} className="hidden items-center gap-2 rounded-xl border border-slate-200 px-3 py-2 text-sm font-bold text-slate-600 hover:bg-slate-50 md:flex"><Save size={15} /> Save as Template</button>}
        <button onClick={next} disabled={state.saveState === 'saving' || state.saveState === 'conflict'} className="flex items-center gap-2 rounded-xl bg-blue-600 px-4 py-2 text-sm font-extrabold text-white hover:bg-blue-700 disabled:opacity-50">{state.currentStep === 5 ? 'Finish' : 'Next'}<ArrowRight size={16} /></button>
      </div>
    </header>
    <main className="min-h-0 flex-1 overflow-auto bg-slate-50/70 dark:bg-slate-950/40">
      {state.currentStep === 1 && <Step1Scope validationErrors={scopeErrors} />}{state.currentStep === 2 && <Step2Template />}{state.currentStep === 3 && <Step3Builder />}{state.currentStep === 4 && <Step4Review />}{state.currentStep === 5 && <Step5Export />}
    </main>
  </div>;
}
