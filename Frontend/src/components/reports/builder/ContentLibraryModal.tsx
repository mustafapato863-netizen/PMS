import { useMemo, useState } from 'react';
import { Database, LockKeyhole, Search, X } from 'lucide-react';
import type { StoryBlockRegistryItem } from '../../../features/reports/types';

export default function ContentLibraryModal({ isOpen, onClose, blocks, categories, slot, allowedCategories, automaticPlacement = false, onAdd }: {
  isOpen: boolean;
  onClose: () => void;
  blocks: StoryBlockRegistryItem[];
  categories: string[];
  slot: string;
  allowedCategories: string[];
  automaticPlacement?: boolean;
  onAdd: (block: StoryBlockRegistryItem) => void;
}) {
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('All');
  const compatible = useMemo(() => blocks.filter((block) => allowedCategories.includes(block.category)), [allowedCategories, blocks]);
  const visibleCategories = useMemo(() => ['All', ...new Set(compatible.map((block) => block.display_category || block.category))], [compatible]);
  const filtered = useMemo(() => compatible.filter((block) => (category === 'All' || (block.display_category || block.category) === category) && `${block.name} ${block.description} ${block.source_page || ''}`.toLowerCase().includes(search.toLowerCase())), [category, compatible, search]);
  if (!isOpen) return null;
  return <div className="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/55 p-4 backdrop-blur-sm">
    <div className="flex max-h-[85vh] w-full max-w-5xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900">
      <header className="flex items-center justify-between border-b border-slate-200 px-6 py-4 dark:border-slate-700"><div><h2 className="text-xl font-extrabold text-slate-900 dark:text-white">Add PMS block</h2><p className="mt-1 text-sm text-slate-500">{automaticPlacement ? 'Choose another block and the page will use the best compatible multi-block layout.' : <>Only blocks compatible with the <b>{slot}</b> layout slot are shown.</>}</p></div><button onClick={onClose} className="rounded-lg p-2 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="Close block library"><X /></button></header>
      <div className="flex flex-col gap-3 border-b border-slate-200 p-4 md:flex-row dark:border-slate-700"><label className="relative flex-1"><Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={17} /><input autoFocus value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search governed PMS blocks..." className="w-full rounded-xl border border-slate-200 bg-slate-50 py-2.5 pl-10 pr-3 text-sm outline-none focus:border-blue-500 dark:border-slate-700 dark:bg-slate-800" /></label><div className="flex gap-2 overflow-x-auto">{categories.filter((item) => visibleCategories.includes(item)).map((item) => <button key={item} onClick={() => setCategory(item)} className={`whitespace-nowrap rounded-lg px-3 py-2 text-xs font-bold ${category === item ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}`}>{item}</button>)}</div></div>
      <div className="grid min-h-64 flex-1 grid-cols-1 gap-3 overflow-y-auto bg-slate-50/70 p-5 md:grid-cols-2 lg:grid-cols-3 dark:bg-slate-950/40">{filtered.map((block) => <button key={block.type} disabled={block.available === false} onClick={() => onAdd(block)} title={block.unavailable_reason || `Add ${block.name}`} className="rounded-xl border border-slate-200 bg-white p-4 text-left transition hover:border-blue-400 hover:shadow-sm disabled:cursor-not-allowed disabled:opacity-55 dark:border-slate-700 dark:bg-slate-900"><span className="mb-3 flex items-start justify-between"><span className="flex h-9 w-9 items-center justify-center rounded-lg bg-blue-50 text-blue-600 dark:bg-blue-950/40">{block.available === false ? <LockKeyhole size={18} /> : <Database size={18} />}</span><span className={`rounded-full px-2 py-1 text-[9px] font-extrabold uppercase ${block.available === false ? 'bg-amber-100 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300' : 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300'}`}>{block.available === false ? 'Restricted' : 'Live data'}</span></span><h3 className="text-sm font-extrabold text-slate-900 dark:text-white">{block.name}</h3><p className="mt-1 text-xs leading-5 text-slate-500">{block.description}</p><div className="mt-3 flex items-center justify-between gap-2"><span className="rounded bg-slate-100 px-2 py-1 text-[9px] font-bold uppercase text-slate-500 dark:bg-slate-800">{block.display_category || block.category}</span><span className="truncate text-[9px] font-bold text-slate-400">From {block.source_page || 'Report Builder'}</span></div>{block.unavailable_reason && <p className="mt-2 text-[10px] font-semibold text-amber-700 dark:text-amber-300">{block.unavailable_reason}</p>}</button>)}{!filtered.length && <div className="col-span-full grid place-items-center text-sm font-semibold text-slate-400">No compatible block matches this search.</div>}</div>
    </div>
  </div>;
}
