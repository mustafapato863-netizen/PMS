import { create } from 'zustand';
import type {
  ManagementCommentary,
  ReportConfiguration,
  StoryReportBlock,
  StoryReportDefinition,
  StoryReportDraft,
  StoryReportPage,
  StoryTemplate,
  StoryValidationResult,
} from '../features/reports/types';

export type BuilderStep = 1 | 2 | 3 | 4 | 5;
export type SaveState = 'idle' | 'dirty' | 'saving' | 'saved' | 'error' | 'conflict';

interface ReportBuilderState {
  currentStep: BuilderStep;
  configuration: Partial<ReportConfiguration>;
  activeTemplate: StoryTemplate | null;
  draftId: string | null;
  draftVersion: number;
  reportType: string;
  slides: StoryReportPage[];
  definition: StoryReportDefinition;
  commentary: ManagementCommentary;
  activeSlideId: string | null;
  activeBlockId: string | null;
  saveState: SaveState;
  saveMessage: string | null;
  validation: StoryValidationResult | null;
  setStep: (step: BuilderStep) => void;
  setConfiguration: (config: Partial<ReportConfiguration>) => void;
  setTemplate: (template: StoryTemplate | null) => void;
  loadDraft: (draft: StoryReportDraft, template?: StoryTemplate | null) => void;
  acknowledgeSaved: (draft: StoryReportDraft) => void;
  advanceDraftVersion: (version: number) => void;
  setSaveState: (state: SaveState, message?: string | null) => void;
  addSlide: (slide: StoryReportPage) => void;
  duplicateSlide: (id: string) => void;
  updateSlide: (id: string, slide: Partial<StoryReportPage>) => void;
  deleteSlide: (id: string) => void;
  reorderSlides: (startIndex: number, endIndex: number) => void;
  setActiveSlideId: (id: string | null) => void;
  addBlock: (slideId: string, block: StoryReportBlock) => void;
  updateBlock: (slideId: string, blockId: string, block: Partial<StoryReportBlock>) => void;
  deleteBlock: (slideId: string, blockId: string) => void;
  setActiveBlockId: (id: string | null) => void;
  setCommentary: (blockId: string, value: string) => void;
  reset: () => void;
}

const emptyDefinition: StoryReportDefinition = {
  slides: [], theme_key: 'sgh_default', language: 'en', preferred_format: 'pdf', narratives: {},
};

const initialState = {
  currentStep: 1 as BuilderStep,
  configuration: {},
  activeTemplate: null,
  draftId: null,
  draftVersion: 0,
  reportType: 'executive',
  slides: [],
  definition: emptyDefinition,
  commentary: { entries: {} },
  activeSlideId: null,
  activeBlockId: null,
  saveState: 'idle' as SaveState,
  saveMessage: null,
  validation: null,
};

const normalizeSlides = (slides: StoryReportPage[]) => slides.map((slide, order) => ({ ...slide, order }));

export const useReportBuilderStore = create<ReportBuilderState>((set) => ({
  ...initialState,
  setStep: (currentStep) => set({ currentStep }),
  setConfiguration: (config) => set((state) => ({ configuration: { ...state.configuration, ...config } })),
  setTemplate: (activeTemplate) => set({ activeTemplate }),
  loadDraft: (draft, activeTemplate = null) => set({
    draftId: draft.id,
    draftVersion: draft.version,
    reportType: draft.report_type,
    configuration: {
      report_name: draft.name,
      start_month: draft.primary_period.month,
      start_year: draft.primary_period.year,
      end_month: draft.comparison_period?.month || null,
      end_year: draft.comparison_period?.year || null,
      ...draft.scope,
    },
    definition: draft.definition,
    slides: draft.definition.slides,
    commentary: draft.management_commentary,
    activeTemplate,
    activeSlideId: draft.definition.slides[0]?.id || null,
    activeBlockId: null,
    saveState: 'saved',
    saveMessage: null,
    validation: draft.validation,
    currentStep: 3,
  }),
  acknowledgeSaved: (draft) => set({
    draftVersion: draft.version,
    definition: draft.definition,
    slides: draft.definition.slides,
    commentary: draft.management_commentary,
    saveState: 'saved',
    saveMessage: null,
    validation: draft.validation,
  }),
  advanceDraftVersion: (draftVersion) => set({ draftVersion, saveState: 'dirty', saveMessage: null }),
  setSaveState: (saveState, saveMessage = null) => set({ saveState, saveMessage }),
  addSlide: (slide) => set((state) => {
    const slides = normalizeSlides([...state.slides, slide]);
    return { slides, definition: { ...state.definition, slides }, activeSlideId: slide.id, activeBlockId: null, saveState: 'dirty' };
  }),
  duplicateSlide: (id) => set((state) => {
    const source = state.slides.find((slide) => slide.id === id);
    if (!source) return state;
    const suffix = crypto.randomUUID();
    const clone: StoryReportPage = {
      ...structuredClone(source), id: `page-${suffix}`, title: `${source.title} Copy`, order: source.order + 1,
      blocks: source.blocks.map((block) => ({ ...block, id: `block-${crypto.randomUUID()}` })),
    };
    const slides = [...state.slides]; slides.splice(source.order + 1, 0, clone);
    const normalized = normalizeSlides(slides);
    return { slides: normalized, definition: { ...state.definition, slides: normalized }, activeSlideId: clone.id, activeBlockId: null, saveState: 'dirty' };
  }),
  updateSlide: (id, patch) => set((state) => {
    const slides = state.slides.map((slide) => slide.id === id ? { ...slide, ...patch } : slide);
    return { slides, definition: { ...state.definition, slides }, saveState: 'dirty' };
  }),
  deleteSlide: (id) => set((state) => {
    const slides = normalizeSlides(state.slides.filter((slide) => slide.id !== id));
    return { slides, definition: { ...state.definition, slides }, activeSlideId: state.activeSlideId === id ? (slides[0]?.id || null) : state.activeSlideId, activeBlockId: null, saveState: 'dirty' };
  }),
  reorderSlides: (startIndex, endIndex) => set((state) => {
    const slides = [...state.slides]; const [removed] = slides.splice(startIndex, 1); slides.splice(endIndex, 0, removed);
    const normalized = normalizeSlides(slides);
    return { slides: normalized, definition: { ...state.definition, slides: normalized }, saveState: 'dirty' };
  }),
  setActiveSlideId: (activeSlideId) => set({ activeSlideId, activeBlockId: null }),
  addBlock: (slideId, block) => set((state) => {
    const slides = state.slides.map((slide) => slide.id === slideId ? { ...slide, blocks: [...slide.blocks, block] } : slide);
    return { slides, definition: { ...state.definition, slides }, activeBlockId: block.id, saveState: 'dirty' };
  }),
  updateBlock: (slideId, blockId, patch) => set((state) => {
    const slides = state.slides.map((slide) => slide.id === slideId ? { ...slide, blocks: slide.blocks.map((block) => block.id === blockId ? { ...block, ...patch } : block) } : slide);
    return { slides, definition: { ...state.definition, slides }, saveState: 'dirty' };
  }),
  deleteBlock: (slideId, blockId) => set((state) => {
    const slides = state.slides.map((slide) => slide.id === slideId ? { ...slide, blocks: slide.blocks.filter((block) => block.id !== blockId) } : slide);
    return { slides, definition: { ...state.definition, slides }, activeBlockId: state.activeBlockId === blockId ? null : state.activeBlockId, saveState: 'dirty' };
  }),
  setActiveBlockId: (activeBlockId) => set({ activeBlockId }),
  setCommentary: (blockId, value) => set((state) => ({ commentary: { entries: { ...state.commentary.entries, [blockId]: value } }, saveState: 'dirty' })),
  reset: () => set({ ...initialState, definition: { ...emptyDefinition, slides: [], narratives: {} }, commentary: { entries: {} } }),
}));
