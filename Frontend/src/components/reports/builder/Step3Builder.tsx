import { useEffect, useState } from 'react';
import { AlertTriangle, ChevronDown, ChevronUp, Copy, LayoutTemplate, Plus, Settings2, Trash2, X } from 'lucide-react';
import { usePrefetchStoryPage, useStoryPage, useStoryRegistry } from '../../../hooks/api/useReports';
import { useReportBuilderStore } from '../../../store/reportBuilderStore';
import type { StoryBlockConfig, StoryBlockRegistryItem, StoryReportPage } from '../../../features/reports/types';
import { bestLayoutAssignment, compatibleLayoutAssignments } from '../../../features/reports/reportBuilderLayout';
import OverlayPortal from '../../common/OverlayPortal';
import BlockRenderer from './BlockRenderer';
import ContentLibraryModal from './ContentLibraryModal';

const defaultConfig = (defaults?: Record<string, unknown>): StoryBlockConfig => ({
  title: null, metrics: [], comparison: true, number_format: 'standard', row_limit: 10,
  sort_by: null, sort_direction: 'desc', show_icons: true, show_subtitle: true,
  show_data_labels: true, show_target: true, narrative_mode: 'auto', include_evidence: true,
  include_recommendations: true, max_length: 700, scope_override: {}, ...(defaults || {}),
});

function Thumbnail({ page, selected, warning, onClick, onPreload }: { page: StoryReportPage; selected: boolean; warning: boolean; onClick: () => void; onPreload: () => void }) {
  return <button onClick={onClick} onMouseEnter={onPreload} onFocus={onPreload} className="w-full text-left"><div className="mb-1 flex items-center justify-between gap-2"><span className="truncate text-[11px] font-extrabold text-slate-600 dark:text-slate-300">{page.order + 1}. {page.title}</span>{warning && <AlertTriangle size={12} className="shrink-0 text-amber-500" />}</div><div className={`aspect-video overflow-hidden rounded-lg border-2 bg-white p-2 shadow-sm dark:bg-slate-900 ${selected ? 'border-blue-600 ring-2 ring-blue-600/15' : 'border-slate-200 dark:border-slate-700'}`}><div className="mb-1 h-1.5 w-2/3 rounded bg-slate-200 dark:bg-slate-700" /><div className={`grid h-[calc(100%-8px)] gap-1 ${page.blocks.length > 1 ? 'grid-cols-2' : 'grid-cols-1'}`}>{page.blocks.length ? page.blocks.slice(0, 4).map((block) => <span key={block.id} className={`rounded ${block.type.includes('action') ? 'bg-amber-100' : block.type.includes('narrative') || block.type.includes('commentary') ? 'bg-violet-100' : 'bg-blue-100'}`} />) : <span className="grid place-items-center rounded border border-dashed border-slate-200"><LayoutTemplate size={14} className="text-slate-300" /></span>}</div></div></button>;
}

function DeletePageDialog({ page, onCancel, onConfirm }: { page: StoryReportPage; onCancel: () => void; onConfirm: () => void }) {
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') onCancel(); };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [onCancel]);

  return <OverlayPortal><div className="fixed inset-0 z-[70] grid place-items-center bg-slate-950/55 p-4 backdrop-blur-sm" onMouseDown={(event) => { if (event.target === event.currentTarget) onCancel(); }}><section role="alertdialog" aria-modal="true" aria-labelledby="delete-report-page-title" aria-describedby="delete-report-page-description" className="w-full max-w-md overflow-hidden rounded-3xl border border-rose-500/20 bg-[var(--bg-surface)] shadow-2xl">
    <div className="flex items-start gap-4 p-6"><span className="grid h-12 w-12 shrink-0 place-items-center rounded-2xl bg-rose-500/10 text-rose-600"><Trash2 size={21} /></span><div className="min-w-0 flex-1"><div className="flex items-start justify-between gap-3"><div><p className="text-[10px] font-extrabold uppercase tracking-[0.14em] text-rose-600">Remove report page</p><h2 id="delete-report-page-title" className="mt-1 text-xl font-black text-[var(--text-primary)]">Delete “{page.title}”?</h2></div><button type="button" onClick={onCancel} aria-label="Close delete dialog" className="rounded-lg p-1.5 text-[var(--text-muted)] hover:bg-[var(--bg-sunken)]"><X size={18} /></button></div><p id="delete-report-page-description" className="mt-3 text-sm leading-6 text-[var(--text-muted)]">This page and its {page.blocks.length} {page.blocks.length === 1 ? 'block' : 'blocks'} will be removed from the report story. Other pages will keep their order.</p></div></div>
    <div className="flex justify-end gap-2 border-t border-[var(--border-light)] bg-[var(--bg-sunken)]/60 px-6 py-4"><button type="button" autoFocus onClick={onCancel} className="min-h-11 rounded-xl border border-[var(--border-light)] bg-[var(--bg-surface)] px-4 text-sm font-extrabold text-[var(--text-secondary)] hover:bg-[var(--bg-elevated)]">Keep page</button><button type="button" onClick={onConfirm} className="inline-flex min-h-11 items-center gap-2 rounded-xl bg-rose-600 px-5 text-sm font-extrabold text-white shadow-lg shadow-rose-600/15 hover:bg-rose-700"><Trash2 size={16} />Delete page</button></div>
  </section></div></OverlayPortal>;
}

export default function Step3Builder() {
  const store = useReportBuilderStore();
  const { data: registry } = useStoryRegistry();
  const prefetchStoryPage = usePrefetchStoryPage();
  const activePage = store.slides.find((page) => page.id === store.activeSlideId) || null;
  const activeBlock = activePage?.blocks.find((block) => block.id === store.activeBlockId) || null;
  const { data: pageData, isFetching } = useStoryPage(store.draftId || undefined, activePage?.id);
  const [library, setLibrary] = useState<{ slot: string; allowed: string[]; automatic?: boolean; newPage?: boolean } | null>(null);
  const [pageToDelete, setPageToDelete] = useState<StoryReportPage | null>(null);
  const layout = registry?.layouts.find((item) => item.key === activePage?.layout);
  const occupied = new Set(activePage?.blocks.map((block) => block.slot) || []);
  const emptySlots = Object.entries(layout?.slots || {}).filter(([slot]) => !occupied.has(slot));
  const activeBlockMeta = registry?.blocks.find((item) => item.type === activeBlock?.type);
  const pageLayoutAssignments = activePage && registry
    ? compatibleLayoutAssignments(activePage.blocks, registry.layouts, registry.blocks)
    : [];
  const pageLayoutOptions = pageLayoutAssignments.map(({ layout: option }) => option);
  const addableBlocks = activePage && registry ? registry.blocks.filter((meta) => {
    if (meta.available === false) return false;
    const candidate = { id: '__candidate__', type: meta.type, slot: '', config: defaultConfig(meta.default) };
    return Boolean(bestLayoutAssignment([...activePage.blocks, candidate], registry.layouts, registry.blocks, activePage.layout));
  }) : [];
  const newPageBlocks = registry?.blocks.filter((meta) => meta.available !== false && meta.slots.includes('full')) || [];
  const stackedLayout = ['kpi_chart', 'kpi_chart_narrative', 'feedback_status'].includes(activePage?.layout || '');

  useEffect(() => {
    if (!store.draftId || !activePage || !pageData) return;
    const activeIndex = store.slides.findIndex((page) => page.id === activePage.id);
    [store.slides[activeIndex - 1], store.slides[activeIndex + 1]].forEach((page) => {
      if (page) void prefetchStoryPage(store.draftId!, page.id);
    });
  }, [activePage, pageData, prefetchStoryPage, store.draftId, store.slides]);

  const addPage = () => store.addSlide({ id: `page-${crypto.randomUUID()}`, title: 'New Report Page', layout: 'full_width', order: store.slides.length, blocks: [] });
  const addBlock = (meta: StoryBlockRegistryItem) => {
    if (!library) return;
    if (library.newPage) {
      const pageId = `page-${crypto.randomUUID()}`;
      store.addSlide({
        id: pageId,
        title: meta.name,
        layout: 'full_width',
        order: store.slides.length,
        blocks: [{ id: `block-${crypto.randomUUID()}`, type: meta.type, slot: 'full', config: defaultConfig(meta.default) }],
      });
      setLibrary(null);
      return;
    }
    if (!activePage) return;
    const block = { id: `block-${crypto.randomUUID()}`, type: meta.type, slot: library.slot, config: defaultConfig(meta.default) };
    if (library.automatic && registry) {
      const assignment = bestLayoutAssignment([...activePage.blocks, block], registry.layouts, registry.blocks, activePage.layout);
      if (!assignment) return;
      store.updateSlide(activePage.id, { layout: assignment.layout.key, blocks: assignment.blocks });
      store.setActiveBlockId(block.id);
    } else {
      store.addBlock(activePage.id, block);
    }
    setLibrary(null);
  };
  const changeLayout = (value: string) => {
    if (!activePage) return;
    const assignment = pageLayoutAssignments.find(({ layout: option }) => option.key === value);
    if (assignment) store.updateSlide(activePage.id, { layout: value, blocks: assignment.blocks });
  };
  const openAutomaticLibrary = () => {
    if (!addableBlocks.length) return;
    setLibrary({
      slot: 'best available',
      allowed: [...new Set(addableBlocks.map((block) => block.category))],
      automatic: true,
    });
  };
  const openNewPageLibrary = () => setLibrary({
    slot: 'full',
    allowed: [...new Set(newPageBlocks.map((block) => block.category))],
    newPage: true,
  });

  return <div className="grid h-full min-h-[650px] grid-cols-[230px_minmax(0,1fr)_290px] overflow-hidden">
    <aside className="flex min-h-0 flex-col border-r border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-950"><div className="flex items-center justify-between border-b border-slate-200 p-3 dark:border-slate-800"><b className="text-sm text-slate-700 dark:text-slate-200">Pages ({store.slides.length})</b><button onClick={addPage} className="rounded-lg bg-blue-600 p-1.5 text-white" aria-label="Add page"><Plus size={15} /></button></div><div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3">{store.slides.map((page, index) => <div key={page.id} className="group"><Thumbnail page={page} selected={page.id === activePage?.id} warning={Boolean(store.validation?.issues.some((issue) => issue.slide_id === page.id))} onClick={() => store.setActiveSlideId(page.id)} onPreload={() => { void prefetchStoryPage(store.draftId || undefined, page.id); }} /><div className="mt-1 flex justify-end gap-1 opacity-0 transition group-hover:opacity-100 group-focus-within:opacity-100"><button aria-label={`Move ${page.title} up`} disabled={index === 0} onClick={() => store.reorderSlides(index, index - 1)} className="rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:hover:bg-slate-800"><ChevronUp size={13} /></button><button aria-label={`Move ${page.title} down`} disabled={index === store.slides.length - 1} onClick={() => store.reorderSlides(index, index + 1)} className="rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 disabled:opacity-30 dark:hover:bg-slate-800"><ChevronDown size={13} /></button><button aria-label={`Duplicate ${page.title}`} onClick={() => store.duplicateSlide(page.id)} className="rounded p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 dark:hover:bg-slate-800"><Copy size={13} /></button><button aria-label={`Delete ${page.title}`} onClick={() => setPageToDelete(page)} className="rounded p-1 text-rose-500 hover:bg-rose-500/10 hover:text-rose-700"><Trash2 size={13} /></button></div></div>)}</div></aside>
    <main className="min-w-0 overflow-auto p-6"><div className="mx-auto max-w-[1100px]"><div className="mb-3 flex items-center justify-between gap-3"><input value={activePage?.title || ''} onChange={(event) => activePage && store.updateSlide(activePage.id, { title: event.target.value })} className="min-w-0 flex-1 bg-transparent text-lg font-extrabold text-slate-800 outline-none dark:text-white" /><div className="flex items-center gap-2">{activePage && <button type="button" onClick={openAutomaticLibrary} disabled={!addableBlocks.length} className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-2 text-xs font-extrabold text-white transition hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-200 disabled:text-slate-400 dark:disabled:bg-slate-800" title={addableBlocks.length ? 'Add another block to this page' : 'This page has reached the supported block limit'}><Plus size={15} />{addableBlocks.length ? 'Add Block' : 'Page full'}</button>}<button type="button" onClick={openNewPageLibrary} className="flex items-center gap-1.5 rounded-lg border border-blue-500/25 px-3 py-2 text-xs font-extrabold text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-950/30"><Plus size={15} />Block as page</button><label className="sr-only" htmlFor="report-page-layout">Page layout</label><select id="report-page-layout" value={activePage?.layout || ''} onChange={(event) => changeLayout(event.target.value)} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-bold dark:border-slate-700 dark:bg-slate-900">{pageLayoutOptions.map((item) => <option key={item.key} value={item.key}>{item.key.replace(/_/g, ' ')}</option>)}</select>{isFetching && <span className="text-xs text-slate-400">Refreshing data...</span>}</div></div>
      {!activePage ? <div className="grid aspect-video place-items-center rounded-2xl border-2 border-dashed border-slate-300 bg-white"><button onClick={addPage} className="rounded-xl bg-blue-600 px-5 py-3 font-bold text-white">Add first report page</button></div> : <div className="flex aspect-video flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white p-7 shadow-xl dark:border-slate-700 dark:bg-slate-950"><h2 className="border-b border-slate-100 pb-3 text-xl font-black text-slate-900 dark:border-slate-800 dark:text-white">{activePage.title}</h2><div className={`mt-4 grid min-h-0 flex-1 auto-rows-fr gap-4 ${activePage.blocks.length + emptySlots.length > 1 && !stackedLayout ? 'grid-cols-2' : 'grid-cols-1'}`}>{activePage.blocks.map((block, index) => <div key={block.id} className={`min-h-0 ${activePage.layout === 'team_review' && index === 2 ? 'col-span-2' : ''}`}><BlockRenderer block={block} blockData={pageData?.blocks[block.id]} isEditing onSelect={() => store.setActiveBlockId(block.id)} /></div>)}{emptySlots.map(([slot, allowed]) => <button key={slot} onClick={() => setLibrary({ slot, allowed })} className="grid min-h-0 place-items-center rounded-xl border-2 border-dashed border-slate-200 text-xs font-bold text-slate-400 hover:border-blue-400 hover:text-blue-600"><span className="flex items-center gap-2"><Plus size={16} /> Add {slot.replace(/_/g, ' ')} block</span></button>)}</div></div>}</div></main>
    <aside className="overflow-y-auto border-l border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900"><div className="mb-5 flex items-center gap-2"><Settings2 size={17} className="text-blue-600" /><h3 className="font-extrabold text-slate-800 dark:text-white">Block settings</h3></div>{!activeBlock ? <p className="rounded-xl bg-slate-50 p-4 text-sm text-slate-500 dark:bg-slate-800">Select a block on the page to configure it.</p> : <div className="space-y-5"><div><p className="text-sm font-extrabold text-slate-900 dark:text-white">{activeBlockMeta?.name || activeBlock.type}</p><p className="mt-1 text-xs leading-5 text-slate-500">{activeBlockMeta?.description}</p></div><label className="block text-xs font-bold text-slate-600">Custom title<input value={activeBlock.config.title || ''} onChange={(event) => store.updateBlock(activePage!.id, activeBlock.id, { config: { ...activeBlock.config, title: event.target.value || null } })} className="mt-1 w-full rounded-lg border border-slate-200 bg-transparent p-2.5 text-sm outline-none focus:border-blue-500 dark:border-slate-700" /></label><label className="block text-xs font-bold text-slate-600">Maximum rows<input type="number" min={1} max={50} value={activeBlock.config.row_limit} onChange={(event) => store.updateBlock(activePage!.id, activeBlock.id, { config: { ...activeBlock.config, row_limit: Number(event.target.value) } })} className="mt-1 w-full rounded-lg border border-slate-200 bg-transparent p-2.5 text-sm dark:border-slate-700" /></label>{activeBlock.type === 'management_commentary' && <label className="block text-xs font-bold text-slate-600">Management commentary<textarea value={store.commentary.entries[activeBlock.id] || ''} onChange={(event) => store.setCommentary(activeBlock.id, event.target.value)} rows={8} className="mt-1 w-full rounded-lg border border-slate-200 bg-transparent p-3 text-sm leading-6 outline-none focus:border-blue-500 dark:border-slate-700" /></label>}<button onClick={() => store.deleteBlock(activePage!.id, activeBlock.id)} className="flex w-full items-center justify-center gap-2 rounded-lg border border-red-200 py-2 text-sm font-bold text-red-600 hover:bg-red-50"><Trash2 size={15} /> Remove block</button></div>}</aside>
    <ContentLibraryModal isOpen={Boolean(library)} onClose={() => setLibrary(null)} blocks={library?.newPage ? newPageBlocks : addableBlocks.length && library?.automatic ? addableBlocks : registry?.blocks || []} categories={registry?.categories || ['All']} slot={library?.slot || 'full'} allowedCategories={library?.allowed || []} automaticPlacement={Boolean(library?.automatic || library?.newPage)} onAdd={addBlock} />
    {pageToDelete && <DeletePageDialog page={pageToDelete} onCancel={() => setPageToDelete(null)} onConfirm={() => { store.deleteSlide(pageToDelete.id); setPageToDelete(null); }} />}
  </div>;
}
